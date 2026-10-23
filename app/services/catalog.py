"""Katalog přístrojů: dohledání podle typu a učení z vydaných rozvaděčů.

Co technik ve vydané revizi potvrdil, se uloží do katalogu firmy (verified).
Příští rozpoznání z fotky stejného typu pak převezme ověřené parametry
místo toho, co AI přečetla – méně chyb i méně dotazů.
"""
import re

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import CatalogDevice, Device

_FIELDS = ("kind", "poles", "rated_current_a", "curve", "breaking_capacity_ka", "residual_ma", "rcd_type")


def norm(code: str) -> str:
    return re.sub(r"[\s\-_/.]", "", (code or "").upper())


def lookup(db: Session, tenant_id: int, manufacturer: str, type_code: str) -> CatalogDevice | None:
    key = norm(type_code)
    if not key:
        return None
    rows = db.scalars(select(CatalogDevice).where(
        or_(CatalogDevice.tenant_id == tenant_id, CatalogDevice.tenant_id.is_(None)))).all()
    hits = [r for r in rows if norm(r.type_code) == key
            and (not manufacturer or not r.manufacturer or norm(r.manufacturer) == norm(manufacturer))]
    # vlastní ověřené > sdílené ověřené > ostatní
    hits.sort(key=lambda r: (not r.verified, r.tenant_id is None, -r.times_used))
    return hits[0] if hits else None


def search(db: Session, tenant_id: int, q: str, limit: int = 15) -> list[CatalogDevice]:
    key = norm(q)
    rows = db.scalars(select(CatalogDevice).where(
        or_(CatalogDevice.tenant_id == tenant_id, CatalogDevice.tenant_id.is_(None)))
        .order_by(CatalogDevice.times_used.desc())).all()
    return [r for r in rows if key in norm(r.type_code) or key in norm(r.manufacturer)][:limit]


def learn(db: Session, tenant_id: int, devices: list[Device]) -> None:
    """Uloží potvrzené přístroje (po vydání revize) do katalogu firmy."""
    for d in devices:
        if not d.type_code or d.kind in ("TERMINAL", "OTHER"):
            continue
        cat = db.scalar(select(CatalogDevice).where(
            CatalogDevice.tenant_id == tenant_id, CatalogDevice.manufacturer == d.manufacturer,
            CatalogDevice.type_code == d.type_code))
        if cat is None:
            cat = CatalogDevice(tenant_id=tenant_id, manufacturer=d.manufacturer, type_code=d.type_code, times_used=0)
            db.add(cat)
        for f in _FIELDS:
            setattr(cat, f, getattr(d, f))
        cat.verified = True
        cat.times_used = (cat.times_used or 0) + 1
