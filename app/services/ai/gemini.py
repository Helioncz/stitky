"""Gemini vision. Zkouší modely v pořadí (GEMINI_MODELS), vyčerpané přeskočí."""
import json
import logging
import re
import time

from google import genai
from google.genai import types

from app.config import settings

logger = logging.getLogger(__name__)
_exhausted: set[str] = set()  # modely s vyčerpanou denní kvótou (na proces)


def recognize(images: list[tuple[bytes, str]], prompt: str) -> tuple[dict, str]:
    if not settings.gemini_api_key:
        raise RuntimeError("Chybí GEMINI_API_KEY v .env")
    client = genai.Client(api_key=settings.gemini_api_key)
    parts = [types.Part.from_bytes(data=data, mime_type=mime) for data, mime in images]
    cfg = types.GenerateContentConfig(response_mime_type="application/json", temperature=0)
    last: Exception | None = None
    for model in [m for m in settings.gemini_models if m not in _exhausted]:
        for attempt in range(3):
            try:
                res = client.models.generate_content(model=model, contents=[*parts, prompt], config=cfg)
                return json.loads(res.text), model
            except json.JSONDecodeError as exc:
                last = exc
                break
            except Exception as exc:  # noqa: BLE001 – SDK hází různé typy
                last = exc
                msg = str(exc)
                logger.warning("Gemini %s pokus %d: %s", model, attempt + 1, msg[:200])
                if "404" in msg or "NOT_FOUND" in msg:
                    break
                if "RESOURCE_EXHAUSTED" in msg and re.search(r"PerDay|per day|free_tier_requests", msg, re.I):
                    _exhausted.add(model)
                    break
                if "429" in msg or "RESOURCE_EXHAUSTED" in msg or "503" in msg:
                    m = re.search(r"retry[^0-9]*(\d+)", msg, re.I)
                    time.sleep(min(int(m.group(1)) if m else 10 * (attempt + 1), 60))
                    continue
                break
    raise RuntimeError(f"Rozpoznání selhalo: {last}")
