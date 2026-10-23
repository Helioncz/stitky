"""Claude vision – připraveno pro porovnání s Gemini.

Zapnutí: `pip install anthropic`, v .env AI_PROVIDER=claude a ANTHROPIC_API_KEY.
"""
import base64
import json
import re

from app.config import settings


def recognize(images: list[tuple[bytes, str]], prompt: str) -> tuple[dict, str]:
    if not settings.anthropic_api_key:
        raise RuntimeError("Chybí ANTHROPIC_API_KEY v .env")
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    content = [
        {"type": "image", "source": {"type": "base64", "media_type": mime, "data": base64.b64encode(data).decode()}}
        for data, mime in images
    ]
    content.append({"type": "text", "text": prompt})
    msg = client.messages.create(model=settings.claude_model, max_tokens=8000,
                                 messages=[{"role": "user", "content": content}])
    text = "".join(b.text for b in msg.content if b.type == "text")
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise RuntimeError("Claude nevrátil JSON")
    return json.loads(m.group()), settings.claude_model
