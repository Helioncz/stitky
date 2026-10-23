"""Přihlášení, odhlášení a registrace nové firmy (tenantu)."""
from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Tenant, User
from app.security import hash_password, verify_password
from app.web import flash, redirect, render

router = APIRouter()


def _safe_next(url: str) -> str:
    return url if url.startswith("/") and not url.startswith("//") else "/"


@router.get("/login")
def login_form(request: Request, next: str = "/"):
    return render(request, "login.html", next=_safe_next(next), allow_signup=settings.allow_signup)


@router.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...), next: str = Form("/"),
          db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(func.lower(User.email) == email.strip().lower()))
    if not user or not user.active or not verify_password(password, user.password_hash):
        flash(request, "Nesprávný e-mail nebo heslo.", "error")
        return redirect(f"/login?next={_safe_next(next)}")
    request.session.clear()
    request.session["uid"] = user.id
    return redirect(_safe_next(next))


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return redirect("/login")


@router.get("/signup")
def signup_form(request: Request):
    if not settings.allow_signup:
        return redirect("/login")
    return render(request, "signup.html")


@router.post("/signup")
def signup(request: Request, company: str = Form(...), ico: str = Form(""), name: str = Form(...),
           email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    if not settings.allow_signup:
        return redirect("/login")
    email = email.strip().lower()
    if len(password) < 8:
        flash(request, "Heslo musí mít aspoň 8 znaků.", "error")
        return redirect("/signup")
    if db.scalar(select(User).where(func.lower(User.email) == email)):
        flash(request, "Uživatel s tímto e-mailem už existuje.", "error")
        return redirect("/signup")
    tenant = Tenant(name=company.strip(), ico=ico.strip(), signer_name=name.strip())
    db.add(tenant)
    db.flush()
    user = User(tenant_id=tenant.id, email=email, name=name.strip(), password_hash=hash_password(password),
                role="owner")
    db.add(user)
    db.commit()
    request.session.clear()
    request.session["uid"] = user.id
    flash(request, "Firma založena. Doplňte prosím údaje výrobce – objeví se na všech dokumentech.")
    return redirect("/settings")
