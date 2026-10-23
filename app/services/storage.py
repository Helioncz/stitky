"""Úložiště souborů (fotky, loga, vydaná PDF).

Klíče jsou relativní cesty `t{tenant}/...`. Zatím lokální disk (DATA_DIR/files),
na serveru je to Docker volume se zálohou. Rozhraní je připravené na výměnu
za Supabase Storage / S3 – stačí implementovat stejné tři metody.
"""
from pathlib import Path

from app.config import settings

_ROOT = settings.data_dir / "files"


def _path(key: str) -> Path:
    p = (_ROOT / key).resolve()
    if _ROOT.resolve() not in p.parents:
        raise ValueError("Neplatný klíč úložiště")
    return p


def save(key: str, data: bytes) -> str:
    p = _path(key)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return key


def load(key: str) -> bytes:
    return _path(key).read_bytes()


def exists(key: str) -> bool:
    return bool(key) and _path(key).is_file()
