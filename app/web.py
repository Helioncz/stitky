"""Sdílené věci pro webové stránky: šablony, flash zprávy, převody formulářů."""
from pathlib import Path

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.models import DEVICE_KINDS, DOCUMENT_KINDS
from app.services.documents import czdate, num

templates = Jinja2Templates(directory=Path(__file__).resolve().parent / "templates")
templates.env.filters["num"] = num
templates.env.filters["czdate"] = czdate
templates.env.globals.update(DEVICE_KINDS=DEVICE_KINDS, DOCUMENT_KINDS=DOCUMENT_KINDS)


def flash(request: Request, message: str, kind: str = "ok") -> None:
    request.session.setdefault("flash", []).append([kind, message])


def render(request: Request, name: str, **ctx):
    messages = request.session.pop("flash", [])
    return templates.TemplateResponse(request, name, {"messages": messages, **ctx})


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


def to_float(v) -> float | None:
    if v is None or str(v).strip() == "":
        return None
    try:
        return float(str(v).replace(",", ".").replace(" ", ""))
    except ValueError:
        return None


def to_int(v) -> int | None:
    f = to_float(v)
    return int(f) if f is not None else None
