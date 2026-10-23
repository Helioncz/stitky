"""Konfigurace aplikace z proměnných prostředí (.env)."""
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _models(raw: str) -> list[str]:
    return [m.strip() for m in raw.split(",") if m.strip()]


@dataclass(frozen=True)
class Settings:
    secret_key: str = os.getenv("SECRET_KEY", "dev-nebezpecny-klic-zmenit")
    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{(BASE_DIR / 'data' / 'app.db').as_posix()}")
    data_dir: Path = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
    # Registrace nové firmy (tenantu) z přihlašovací stránky. Na ostrém provozu
    # se dá vypnout a firmy zakládat jen ručně.
    allow_signup: bool = os.getenv("ALLOW_SIGNUP", "true").lower() == "true"
    https_only_cookies: bool = os.getenv("HTTPS_ONLY_COOKIES", "false").lower() == "true"

    ai_provider: str = os.getenv("AI_PROVIDER", "gemini")  # gemini | claude (připraveno)
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_models: list[str] = field(default_factory=lambda: _models(
        os.getenv("GEMINI_MODELS", "gemini-3.8-flash,gemini-3.7-flash,gemini-3.5-flash,gemini-flash-latest,gemini-2.5-flash")
    ))
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    claude_model: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
