"""Společný prompt a normalizace výstupu AI."""
import re

from app.models import DEVICE_KINDS

PROMPT = """Jsi zkušený elektrotechnik (revizní technik). Na fotkách je rozvaděč nízkého napětí.
Rozpoznej VŠECHNY osazené přístroje na DIN lištách a v rozvaděči, v pořadí po lištách
shora dolů a na každé liště zleva doprava. Čti popisky přímo z přístrojů (výrobce, typové
označení, jmenovitý proud, charakteristika, vypínací schopnost v rámečku, IΔn, typ chrániče).
Pokud je na fotce popisek vývodu (štítek pod přístrojem), přepiš ho do circuit_label.

Vrať POUZE JSON:
{"devices": [
  {"row": 1, "kind": "MCB|RCD|RCBO|MCCB|SWITCH|FUSE|SPD|CONTACTOR|RELAY|METER|TERMINAL|OTHER",
   "manufacturer": "Eaton|ABB|Schneider Electric|OEZ|Hager|Siemens|Legrand|…",
   "type_code": "přesné typové označení z přístroje, např. PL6-C16/1 nebo LTN-16C-1",
   "poles": "1|1+N|2|3|3+N|4",
   "rated_current_a": 16, "curve": "B|C|D|gG|", "breaking_capacity_ka": 6,
   "residual_ma": 30, "rcd_type": "AC|A|F|B|",
   "circuit_label": "", "confidence": 0.0-1.0,
   "note": "co bylo nejisté (česky), jinak vynech"}
],
 "enclosure": {"manufacturer": "", "type": "", "modules": null},
 "notes": "celkové poznámky česky (např. nečitelné přístroje, zakryté části)"}

Pravidla:
- Neznámé hodnoty dej null nebo "", NIKDY si je nevymýšlej. Raději nižší confidence.
- Vícepólový přístroj je JEDEN záznam s poles, ne víc záznamů.
- breaking_capacity_ka je číslo v rámečku na jističi (např. 6000 → 6, 10000 → 10).
- Svorky, propojovací lišty a záslepky nevypisuj, jen pokud jde o samostatnou svorkovnici přívodu.
"""

_KIND_ALIASES = {"RCCB": "RCD", "FI": "RCD", "ISOLATOR": "SWITCH", "DISCONNECTOR": "SWITCH", "SVODIC": "SPD"}


def _float(v):
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace(",", ".").strip())
    except ValueError:
        m = re.search(r"\d+(?:[.,]\d+)?", str(v))
        return float(m.group().replace(",", ".")) if m else None


def normalize_devices(raw: dict) -> list[dict]:
    out = []
    for i, d in enumerate((raw or {}).get("devices") or []):
        kind = str(d.get("kind") or "OTHER").upper()
        kind = _KIND_ALIASES.get(kind, kind)
        if kind not in DEVICE_KINDS:
            kind = "OTHER"
        icn = _float(d.get("breaking_capacity_ka"))
        if icn and icn >= 1000:  # model občas vrátí 6000 místo 6
            icn = icn / 1000
        out.append({
            "position": i + 1,
            "row": d.get("row"),
            "kind": kind,
            "manufacturer": str(d.get("manufacturer") or "").strip(),
            "type_code": str(d.get("type_code") or "").strip(),
            "poles": str(d.get("poles") or "1").strip(),
            "rated_current_a": _float(d.get("rated_current_a")),
            "curve": str(d.get("curve") or "").strip().upper()[:5],
            "breaking_capacity_ka": icn,
            "residual_ma": _float(d.get("residual_ma")),
            "rcd_type": str(d.get("rcd_type") or "").strip().upper()[:10],
            "circuit_label": str(d.get("circuit_label") or "").strip(),
            "confidence": _float(d.get("confidence")),
            "note": str(d.get("note") or "").strip(),
        })
    return out
