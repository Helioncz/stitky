"""Nastavení firmy (údaje výrobce na dokumentech), normy a uživatelé."""
import io

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.domain import label_sheets
from app.domain.standards import DEFAULT_STANDARDS
from app.models import User
from app.security import admin_user, current_user, hash_password
from app.services import storage
from app.web import flash, redirect, render, to_int

router = APIRouter()

TENANT_FIELDS = ["name", "ico", "dic", "street", "city", "zip", "country", "email", "phone", "web",
                 "signer_name", "signer_position", "issue_place", "serial_prefix"]


@router.get("/settings")
def settings_page(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    users = db.scalars(select(User).where(User.tenant_id == user.tenant_id).order_by(User.name)).all()
    return render(request, "settings.html", user=user, t=user.tenant, users=users, standards=DEFAULT_STANDARDS,
                  sheet=label_sheets.sheet_for(user.tenant.label_sheet), sheet_presets=label_sheets.PRESETS)


@router.post("/settings")
async def save_settings(request: Request, user: User = Depends(admin_user), db: Session = Depends(get_db)):
    form = await request.form()
    t = user.tenant
    for f in TENANT_FIELDS:
        if f in form:
            setattr(t, f, str(form[f]).strip())
    nxt = to_int(form.get("next_serial"))
    if nxt and nxt > 0:
        t.next_serial = nxt
    t.standards_override = {s.code: str(form.get(f"std_{i}", "")).strip()
                            for i, s in enumerate(DEFAULT_STANDARDS)
                            if str(form.get(f"std_{i}", "")).strip() not in ("", s.code)}
    db.commit()
    flash(request, "Nastavení uloženo.")
    return redirect("/settings")


@router.post("/settings/logo")
def upload_logo(request: Request, file: UploadFile = File(...), user: User = Depends(admin_user),
                db: Session = Depends(get_db)):
    raw = file.file.read()
    name = (file.filename or "").lower()
    if name.endswith(".svg"):
        key = storage.save(f"t{user.tenant_id}/logo.svg", raw)
    else:
        try:
            img = Image.open(io.BytesIO(raw))
            img.thumbnail((800, 400))
            buf = io.BytesIO()
            img.save(buf, "PNG")
        except Exception:  # noqa: BLE001
            flash(request, "Logo musí být obrázek (PNG, JPG nebo SVG).", "error")
            return redirect("/settings")
        key = storage.save(f"t{user.tenant_id}/logo.png", buf.getvalue())
    user.tenant.logo_key = key
    db.commit()
    flash(request, "Logo nahráno.")
    return redirect("/settings")


@router.get("/settings/logo")
def logo(user: User = Depends(current_user)):
    key = user.tenant.logo_key
    if not storage.exists(key):
        return Response(status_code=404)
    return Response(storage.load(key), media_type="image/svg+xml" if key.endswith(".svg") else "image/png")


@router.post("/settings/users")
def add_user(request: Request, email: str = Form(...), name: str = Form(...), password: str = Form(...),
             role: str = Form("technik"), user: User = Depends(admin_user), db: Session = Depends(get_db)):
    email = email.strip().lower()
    if db.scalar(select(User).where(func.lower(User.email) == email)):
        flash(request, "Uživatel s tímto e-mailem už existuje.", "error")
        return redirect("/settings#uzivatele")
    if len(password) < 8:
        flash(request, "Heslo musí mít aspoň 8 znaků.", "error")
        return redirect("/settings#uzivatele")
    db.add(User(tenant_id=user.tenant_id, email=email, name=name.strip(), password_hash=hash_password(password),
                role=role if role in ("admin", "technik") else "technik"))
    db.commit()
    flash(request, f"Uživatel {email} přidán.")
    return redirect("/settings#uzivatele")


@router.post("/settings/users/{uid}/toggle")
def toggle_user(request: Request, uid: int, user: User = Depends(admin_user), db: Session = Depends(get_db)):
    other = db.get(User, uid)
    if other is None or other.tenant_id != user.tenant_id or other.id == user.id or other.role == "owner":
        flash(request, "Tohoto uživatele nelze změnit.", "error")
        return redirect("/settings#uzivatele")
    other.active = not other.active
    db.commit()
    return redirect("/settings#uzivatele")


@router.post("/settings/password")
def change_password(request: Request, password: str = Form(...), user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    if len(password) < 8:
        flash(request, "Heslo musí mít aspoň 8 znaků.", "error")
    else:
        user.password_hash = hash_password(password)
        db.commit()
        flash(request, "Heslo změněno.")
    return redirect("/settings")
