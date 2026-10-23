"""Převod návrhu AI na přístroje rozvaděče: označení, napájení a doplnění z katalogu.

Heuristika napájení odpovídá běžné rozvodnici: první vypínač/hlavní jistič je
hlavní přístroj; jističe za chráničem na stejné liště jsou napájené z něj,
dokud nepřijde další chránič, RCBO nebo nová lišta. Technik to pak zkontroluje.
"""
from sqlalchemy.orm import Session

from app.models import Device, Switchboard
from app.services import catalog

_PREFIX = {"SWITCH": "Q", "MCCB": "Q", "MCB": "F", "RCD": "F", "RCBO": "F", "FUSE": "F", "SPD": "FA",
           "CONTACTOR": "K", "RELAY": "K", "METER": "P", "TERMINAL": "X", "OTHER": "A"}
_CATALOG_FIELDS = ("kind", "poles", "rated_current_a", "curve", "breaking_capacity_ka", "residual_ma", "rcd_type")
_MAIN_KINDS = ("SWITCH", "MCCB", "FUSE", "MCB")


def apply(db: Session, sb: Switchboard, proposed: list[dict], replace: bool) -> int:
    if replace:
        sb.devices.clear()
        db.flush()
    existing = list(sb.devices)
    counters: dict[str, int] = {}
    for d in existing:
        p = d.designation.lstrip("-").rstrip("0123456789")
        n = d.designation.lstrip("-")[len(p):]
        if n.isdigit():
            counters[p] = max(counters.get(p, 0), int(n))

    main = next((d for d in existing if not d.feeds_from), None)
    main_des = main.designation if main else ""
    current_rcd: str = ""
    current_row = None
    pos = max((d.position for d in existing), default=-1) + 1

    for item in proposed:
        dev = Device(position=pos, source="ai", ai_confidence=item.get("confidence"))
        pos += 1
        for f in ("kind", "manufacturer", "type_code", "poles", "rated_current_a", "curve", "breaking_capacity_ka",
                  "residual_ma", "rcd_type", "circuit_label"):
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

        prefix = _PREFIX.get(dev.kind, "A")
        counters[prefix] = counters.get(prefix, 0) + 1
        dev.designation = f"-{prefix}{counters[prefix]}"

        row = item.get("row")
        if row != current_row:
            current_rcd, current_row = "", row
        if not main_des and dev.kind in _MAIN_KINDS:
            main_des = dev.designation  # první vhodný přístroj = hlavní, bez napájení
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
        sb.devices.append(dev)
    db.flush()
    return len(proposed)
