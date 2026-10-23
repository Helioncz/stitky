"""Veřejná stránka rozvaděče (QR kód na štítku) – bez přihlášení.

Přístup chrání jen náhodný token v URL; zobrazuje pouze ZAMČENÉ revize,
nikdy nezamčenou revizi, rozpracovaný koncept ani fotky.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Document, Switchboard
from app.services import storage
from app.web import render

router = APIRouter()


def _by_token(db: Session, token: str) -> Switchboard:
    sb = db.scalar(select(Switchboard).where(Switchboard.public_token == token))
    if sb is None or not sb.latest_locked:
        raise HTTPException(404, "Dokumentace nenalezena")
    return sb


@router.get("/d/{token}")
def public_page(request: Request, token: str, db: Session = Depends(get_db)):
    sb = _by_token(db, token)
    rev = sb.latest_locked
    older = [r for r in sb.revisions if r.locked_at and r.id != rev.id]
    return render(request, "public.html", sb=sb, rev=rev, older=older, tenant=rev.snapshot["tenant"])


@router.get("/d/{token}/{doc_id}")
def public_doc(token: str, doc_id: int, db: Session = Depends(get_db)):
    sb = _by_token(db, token)
    doc = db.get(Document, doc_id)
    if doc is None or doc.revision.switchboard_id != sb.id or not doc.revision.locked_at:
        raise HTTPException(404)
    filename = doc.storage_key.rsplit("/", 1)[-1]
    return Response(storage.load(doc.storage_key), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{filename}"'})
