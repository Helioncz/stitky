"""Rozpoznání přístrojů z fotek rozvaděče.

Poskytovatel se volí přes AI_PROVIDER (gemini | claude). Oba vrací stejný
formát: seznam přístrojů zleva doprava, shora dolů (viz PROMPT).
Výsledek je vždy jen NÁVRH – technik ho v aplikaci zkontroluje.
"""
from app.config import settings

from .prompt import PROMPT, normalize_devices


def recognize(images: list[tuple[bytes, str]]) -> tuple[list[dict], str]:
    """images = [(data, mime_type)]. Vrací (přístroje, použitý model)."""
    if settings.ai_provider == "claude":
        from . import claude as provider
    else:
        from . import gemini as provider
    raw, model = provider.recognize(images, PROMPT)
    return normalize_devices(raw), model
