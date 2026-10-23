"""Společný prompt a normalizace výstupu AI."""
import re

from app.models import DEVICE_KINDS

PROMPT = """Jsi zkušený elektrotechnik (revizní technik). Na fotkách je rozvaděč nízkého napětí.
Rozpoznej VŠECHNY osazené přístroje na DIN lištách, po lištách shora dolů a na každé liště
zleva doprava. Čti popisky přímo z přístrojů (výrobce, typové označení, jmenovitý proud,
charakteristika, vypínací schopnost v rámečku, IΔn, typ chrániče) i ze štítkového pruhu nad lištou.

Vrať POUZE JSON:
{"devices": [
  {"row": 1,
   "designation": "označení přístroje přesně podle štítku/popisku na fotce (F2, -Q1, KM1…), jinak \\"\\"",
   "is_main": false,
   "kind": "MCB|RCD|RCBO|MCCB|SWITCH|FUSE|SPD|CONTACTOR|RELAY|METER|TERMINAL|OTHER",
   "manufacturer": "Eaton|ABB|Schneider Electric|OEZ|Hager|Siemens|Legrand|ELKO EP|…",
   "type_code": "typové označení PŘEČTENÉ z přístroje, např. PL6-C16/1, iC60N, HRN-54",
   "poles": "1|1+N|2|3|3+N|4",
   "rated_current_a": 16, "curve": "B|C|D|gG|", "breaking_capacity_ka": 6,
   "residual_ma": 30, "rcd_type": "AC|A|F|B|",
   "circuit_label": "popis funkce/vývodu ze štítkového pruhu, bez označení přístroje",
   "confidence": 0.0-1.0,
   "note": "co bylo nejisté (česky), jinak vynech"}
],
 "enclosure": {"manufacturer": "", "series": "např. Plexo³, Mini Pragma, Gemini", "catalog_number": "",
               "rows": 3, "modules": 54, "material": "plast|kov", "door": "průhledné|plné|bez dveří",
               "mounting": "nástěnná|zapuštěná|stojanová", "ip_code": "IP65 jen je-li na skříni uvedeno",
               "width_mm": null, "height_mm": null, "depth_mm": null},
 "nameplate": {"present": false, "manufacturer": "", "serial_number": "", "text": "přepis výrobního štítku rozvaděče"},
 "notes": "celkové poznámky česky (nečitelné přístroje, zakryté části, prázdné pozice)"}

Pravidla:
- NIKDY si nevymýšlej. Typové označení, které na fotce nepřečteš, nech "" (případně do note napiš
  odhad řady). Neznámá čísla dej null. Nejistota = nižší confidence.
- Vícepólový přístroj je JEDEN záznam s poles (počítej páčky/šířku: 1 modul = 1 pól u jističů).
- breaking_capacity_ka je číslo v rámečku na jističi (6000 → 6, 10000 → 10).
- Rozliš stykač/relé (cívka A1-A2, často „iCT“, „ERC“, přepínač 0-1-auto = CONTACTOR) od vypínače
  (SWITCH, jen ruční páčka bez cívky).
- is_main = true u JEDNOHO přístroje, kterým se rozvaděč odpojuje od přívodu (hlavní vypínač/jistič,
  často s nápisem „HLAVNÍ VYPÍNAČ“). Pozor: může být na libovolné liště, i dole.
- Samolepky a nápisy, které nepatří ke konkrétnímu přístroji (např. „HLAVNÍ VYPÍNAČ ZÁLOHY“ pod lištou),
  zmiň v note příslušného přístroje, nevkládej je do circuit_label jiných přístrojů.
- Svorky a propojovací lišty vypisuj jen jako samostatné svorkovnice (TERMINAL) bez parametrů.
- Rozměry skříně odhadni z počtu modulů a řad (1 modul = 18 mm), jen pokud si nejsi jistý typem.
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


def _str(v, n: int = 200) -> str:
    return str(v or "").strip()[:n]


def normalize_designation(v) -> str:
    d = re.sub(r"\s+", "", _str(v, 20)).upper()
    if not re.fullmatch(r"-?[A-Z]{1,3}\d{1,3}", d):
        return ""
    return d if d.startswith("-") else "-" + d


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
            "designation": normalize_designation(d.get("designation")),
            "is_main": bool(d.get("is_main")),
            "kind": kind,
            "manufacturer": _str(d.get("manufacturer"), 100),
            "type_code": _str(d.get("type_code"), 100),
            "poles": _str(d.get("poles") or "1", 10),
            "rated_current_a": _float(d.get("rated_current_a")),
            "curve": _str(d.get("curve")).upper()[:5],
            "breaking_capacity_ka": icn,
            "residual_ma": _float(d.get("residual_ma")),
            "rcd_type": _str(d.get("rcd_type")).upper()[:10],
            "circuit_label": _str(d.get("circuit_label")),
            "confidence": _float(d.get("confidence")),
            "note": _str(d.get("note"), 300),
        })
    return out


def normalize_enclosure(raw: dict) -> dict:
    e = (raw or {}).get("enclosure") or {}
    ip = _str(e.get("ip_code"), 10).upper().replace(" ", "")
    return {
        "manufacturer": _str(e.get("manufacturer"), 100),
        "series": _str(e.get("series"), 100),
        "catalog_number": _str(e.get("catalog_number"), 50),
        "rows": _float(e.get("rows")),
        "modules": _float(e.get("modules")),
        "material": _str(e.get("material"), 20),
        "door": _str(e.get("door"), 30),
        "mounting": _str(e.get("mounting"), 40),
        "ip_code": ip if re.fullmatch(r"IP\d[\dX]", ip) else "",
        "width_mm": _float(e.get("width_mm")),
        "height_mm": _float(e.get("height_mm")),
        "depth_mm": _float(e.get("depth_mm")),
    }


def normalize_nameplate(raw: dict) -> dict:
    n = (raw or {}).get("nameplate") or {}
    return {"present": bool(n.get("present")), "manufacturer": _str(n.get("manufacturer"), 100),
            "serial_number": _str(n.get("serial_number"), 50), "text": _str(n.get("text"), 500)}
