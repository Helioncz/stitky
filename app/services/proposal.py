"""Převod návrhu AI na přístroje rozvaděče: označení, napájení, katalog a skříň.

- Označení: když AI přečetla označení ze štítkového pruhu (F2, KM1…), použije se;
  jinak (často popisky chybí) se přístroj očísluje podle druhu (-Q1, -F1, -FA1…).
- Hlavní přístroj: ten, který AI označila is_main; jinak první vypínač/kompaktní jistič;
  jinak první jisticí přístroj.
- Napájení: jističe za chráničem na stejné liště jsou napájené z něj, dokud nepřijde
  další chránič, RCBO nebo nová lišta; ostatní z hlavního přístroje. Technik to pak zkontroluje.
"""
from sqlalchemy.orm import Session

from app.models import Device, Switchboard
from app.services import catalog

_PREFIX = {"SWITCH": "Q", "MCCB": "Q", "MCB": "F", "RCD": "F", "RCBO": "F", "FUSE": "F", "SPD": "FA",
           "CONTACTOR": "K", "RELAY": "K", "METER": "P", "TERMINAL": "X", "OTHER": "A"}
_CATALOG_FIELDS = ("kind", "poles", "rated_current_a", "curve", "breaking_capacity_ka", "residual_ma", "rcd_type")
_DEVICE_FIELDS = ("kind", "manufacturer", "type_code", "poles", "rated_current_a", "curve", "breaking_capacity_ka",
                  "residual_ma", "rcd_type", "circuit_label")


def _pick_main(items: list[dict]) -> int | None:
    for pred in (lambda d: d.get("is_main"),
                 lambda d: d["kind"] in ("SWITCH", "MCCB"),
                 lambda d: d["kind"] in ("MCB", "FUSE")):
        idx = next((i for i, d in enumerate(items) if pred(d)), None)
        if idx is not None:
            return idx
    return None


def apply(db: Session, sb: Switchboard, proposed: list[dict], replace: bool) -> int:
    if replace:
        sb.devices.clear()
        db.flush()
    existing = list(sb.devices)
    used = {d.designation for d in existing if d.designation}
    used |= {p["designation"] for p in proposed if p.get("designation")}
    counters: dict[str, int] = {}

    def auto_designation(kind: str) -> str:
        prefix = _PREFIX.get(kind, "A")
        while True:
            counters[prefix] = counters.get(prefix, 0) + 1
            des = f"-{prefix}{counters[prefix]}"
            if des not in used:
                used.add(des)
                return des

    main_existing = next((d for d in existing if not d.feeds_from), None)
    main_idx = None if main_existing else _pick_main(proposed)
    pos = max((d.position for d in existing), default=-1) + 1
    taken: set[str] = {d.designation for d in existing if d.designation}

    devices: list[Device] = []
    for item in proposed:
        dev = Device(position=pos, source="ai", ai_confidence=item.get("confidence"))
        pos += 1
        for f in _DEVICE_FIELDS:
            if item.get(f) not in (None, ""):
                setattr(dev, f, item[f])
        cat = catalog.lookup(db, sb.tenant_id, dev.manufacturer, dev.type_code)
        if cat is not None and cat.verified:
            for f in _CATALOG_FIELDS:
                if getattr(cat, f) not in (None, ""):
                    setattr(dev, f, getattr(cat, f))
            dev.manufacturer = dev.manufacturer or cat.manufacturer
            dev.catalog_id = cat.id
            dev.source = "catalog"
        des = item.get("designation") or ""
        dev.designation = des if des and des not in taken else auto_designation(dev.kind)
        taken.add(dev.designation)
        devices.append(dev)

    main_des = main_existing.designation if main_existing else (
        devices[main_idx].designation if main_idx is not None else "")
    current_rcd, current_row = "", None
    for item, dev in zip(proposed, devices):
        if item.get("row") != current_row:
            current_rcd, current_row = "", item.get("row")
        if dev.designation == main_des:
            dev.feeds_from = ""
        elif dev.kind == "RCD":
            dev.feeds_from = main_des
            current_rcd = dev.designation
        elif dev.kind == "RCBO":
            dev.feeds_from = main_des
            current_rcd = ""
        elif dev.kind in ("MCB", "FUSE") and current_rcd:
            dev.feeds_from = current_rcd
        else:
            dev.feeds_from = main_des
    # hlavní přístroj první – schéma i tabulka začínají přívodem
    devices.sort(key=lambda d: (d.designation != main_des, d.position))
    for i, dev in enumerate(devices, start=pos - len(devices)):
        dev.position = i
        sb.devices.append(dev)
    db.flush()
    return len(proposed)


def apply_enclosure(sb: Switchboard, enc: dict) -> list[str]:
    """Doplní údaje skříně z odhadu AI – jen prázdná pole, nic nepřepisuje. Vrací změněná pole."""
    changed = []

    def fill(field: str, value) -> None:
        if value in (None, "", 0):
            return
        if getattr(sb, field) in (None, ""):
            setattr(sb, field, value)
            changed.append(field)

    fill("enclosure_manufacturer", enc.get("manufacturer"))
    typ = " ".join(p for p in (enc.get("series"), enc.get("catalog_number")) if p)
    if enc.get("modules"):
        typ = f"{typ}, {enc['modules']:g} modulů".strip(", ")
    fill("enclosure_type", typ)
    for f in ("width_mm", "height_mm", "depth_mm"):
        fill(f, int(enc[f]) if enc.get(f) else None)
    # IP jen pokud je na skříni uvedeno – výchozí IP40 je jen předvolba, ne údaj technika
    if enc.get("ip_code") and sb.ip_code in ("", "IP40"):
        sb.ip_code = enc["ip_code"]
        changed.append("ip_code")
    if enc.get("mounting") in ("nástěnná", "zapuštěná", "stojanová") and sb.mounting != enc["mounting"]:
        sb.mounting = enc["mounting"]
        changed.append("mounting")
    return changed
