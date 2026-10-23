"""Štítky – generátor povinné dokumentace rozvaděčů NN.

Spuštění lokálně:  uvicorn app.main:app --reload
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import BASE_DIR, settings
from app.db import init_db
from app.routers import auth, labels, public, settings as settings_router, switchboards
from app.security import LoginRequired

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Štítky – dokumentace rozvaděčů", docs_url=None, redoc_url=None, lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, session_cookie="stitky",
                   same_site="lax", https_only=settings.https_only_cookies, max_age=14 * 24 * 3600)
app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")

app.include_router(auth.router)
app.include_router(labels.router)
app.include_router(public.router)
app.include_router(settings_router.router)
app.include_router(switchboards.router)


@app.exception_handler(LoginRequired)
async def _login_required(request: Request, _exc: LoginRequired):
    return RedirectResponse(f"/login?next={request.url.path}", status_code=303)


@app.get("/health")
def health() -> dict:
    return {"ok": True}
