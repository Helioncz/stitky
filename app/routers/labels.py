"""Tisk výrobního štítku na arch etiket na zvolenou pozici."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.domain import label_sheets
from app.models import Switchboard, User
from app.security import admin_user, current_user, get_owned
from app.services import documents, pdf
from app.web import flash, redirect, render, to_float

router = APIRouter()


def _snapshot(sb: Switchboard, user: User) -> dict:
    """Štítek z poslední vygenerované revize (odpovídá PDF); bez revize z aktuálních údajů."""
    rev = sb.latest_revision
    return rev.snapshot if rev else documents.build_snapshot(sb, user.tenant, None)


def _pdf_response(html: str, filename: str) -> Response:
    return Response(pdf.html_to_pdf(html), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{filename}"'})


@router.get("/sb/{sb_id}/label")
def label_page(request: Request, sb_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    sb = get_owned(db, Switchboard, sb_id, user)
    sheet = label_sheets.sheet_for(user.tenant.label_sheet)
    nxt = user.tenant.label_next or {}
    row, col = nxt.get("row", 1), nxt.get("col", 1)
    if row > sheet["rows"] or col > sheet["cols"]:
        row, col = 1, 1
    return render(request, "label_print.html", user=user, sb=sb, sheet=sheet, row=row, col=col,
                  rev=sb.latest_revision)


@router.get("/sb/{sb_id}/label.pdf")
def label_pdf(sb_id: int, row: int = 1, col: int = 1, count: int = 1, user: User = Depends(current_user),
              db: Session = Depends(get_db)):
    sb = get_owned(db, Switchboard, sb_id, user)
    sheet = label_sheets.sheet_for(user.tenant.label_sheet)
    try:
        pos = label_sheets.positions(sheet, row, col, min(max(count, 1), 100))
    except ValueError:
        raise HTTPException(400, "Pozice mimo arch") from None
    html = documents.render_label_sheet(_snapshot(sb, user), sheet, pos)
    nr, nc = label_sheets.next_after(sheet, pos[-1])
    user.tenant.label_next = {"row": nr, "col": nc}
    db.commit()
    return _pdf_response(html, f"stitek_{sb.serial_number}_r{row}s{col}.pdf")


@router.get("/settings/label-test.pdf")
def label_test(user: User = Depends(current_user)):
    sheet = label_sheets.sheet_for(user.tenant.label_sheet)
    return _pdf_response(documents.render_label_sheet(None, sheet, [], calibration=True), "zkusebni_arch.pdf")


@router.post("/settings/label-sheet")
async def save_label_sheet(request: Request, user: User = Depends(admin_user), db: Session = Depends(get_db)):
    form = await request.form()
    preset = str(form.get("preset") or label_sheets.DEFAULT)
    stored: dict = {"preset": preset if preset in label_sheets.PRESETS or preset == "custom" else label_sheets.DEFAULT}
    base = label_sheets.PRESETS.get(stored["preset"], {})
    for f in label_sheets.FIELDS:
        v = to_float(form.get(f))
        # ukládáme jen odchylky od předvolby (offsety vždy) – změna předvolby pak nepřebijí staré rozměry
        if v is not None and (f.startswith("offset") or stored["preset"] == "custom" or base.get(f) != v):
            stored[f] = v
    user.tenant.label_sheet = stored
    user.tenant.label_next = {"row": 1, "col": 1}
    db.commit()
    flash(request, "Arch etiket uložen. Vytiskněte zkušební arch a porovnejte ho s etiketami proti světlu.")
    return redirect("/settings#stitky")
