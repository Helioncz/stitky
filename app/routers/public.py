"""Veřejná stránka rozvaděče (QR kód na štítku) – bez přihlášení.

Přístup chrání jen náhodný token v URL; zobrazuje pouze VYDANÉ revize,
nikdy rozpracovaný koncept ani fotky.
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
    if sb is None or not sb.revisions:
        raise HTTPException(404, "Dokumentace nenalezena")
    return sb


@router.get("/d/{token}")
def public_page(request: Request, token: str, db: Session = Depends(get_db)):
    sb = _by_token(db, token)
    return render(request, "public.html", sb=sb, rev=sb.latest_revision, tenant=sb.latest_revision.snapshot["tenant"])


@router.get("/d/{token}/{doc_id}")
def public_doc(token: str, doc_id: int, db: Session = Depends(get_db)):
    sb = _by_token(db, token)
    doc = db.get(Document, doc_id)
    if doc is None or doc.revision.switchboard_id != sb.id:
        raise HTTPException(404)
    filename = doc.storage_key.rsplit("/", 1)[-1]
    return Response(storage.load(doc.storage_key), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{filename}"'})
