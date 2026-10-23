"""Hesla, přihlášení a izolace dat mezi firmami (tenanty)."""
import hashlib
import hmac
import secrets

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Switchboard, User

_N, _R, _P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, digest = stored.split("$")
        calc = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p))
        return hmac.compare_digest(calc.hex(), digest)
    except (ValueError, TypeError):
        return False


class LoginRequired(Exception):
    """Zachytí handler v main.py a přesměruje na /login."""


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    uid = request.session.get("uid")
    user = db.get(User, uid) if uid else None
    if not user or not user.active:
        request.session.clear()
        raise LoginRequired()
    return user


def admin_user(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "Jen pro správce firmy")
    return user


def get_owned(db: Session, model, obj_id: int, user: User):
    """Načte záznam a ověří, že patří firmě uživatele. Jinak 404 (ne 403 – neprozrazujeme existenci)."""
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(404)
    tenant_id = getattr(obj, "tenant_id", None)
    if tenant_id is None and hasattr(obj, "switchboard_id"):
        tenant_id = db.get(Switchboard, obj.switchboard_id).tenant_id
    if tenant_id != user.tenant_id:
        raise HTTPException(404)
    return obj
