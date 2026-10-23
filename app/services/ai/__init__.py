"""Rozpoznání přístrojů a skříně z fotek rozvaděče.

Poskytovatel se volí přes AI_PROVIDER (gemini | claude). Oba vrací stejný
formát (viz PROMPT). Výsledek je vždy jen NÁVRH – technik ho v aplikaci zkontroluje.
"""
from app.config import settings

from .prompt import PROMPT, normalize_devices, normalize_enclosure, normalize_nameplate


def recognize(images: list[tuple[bytes, str]]) -> tuple[dict, str]:
    """images = [(data, mime_type)]. Vrací ({devices, enclosure, nameplate, notes}, použitý model)."""
    if settings.ai_provider == "claude":
        from . import claude as provider
    else:
        from . import gemini as provider
    raw, model = provider.recognize(images, PROMPT)
    return {
        "devices": normalize_devices(raw),
        "enclosure": normalize_enclosure(raw),
        "nameplate": normalize_nameplate(raw),
        "notes": str((raw or {}).get("notes") or "").strip()[:1000],
    }, model
