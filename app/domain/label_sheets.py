"""Archy samolepicích etiket pro tisk výrobního štítku na konkrétní pozici.

Rozměry v mm. Štítek je navržený na 105 × 74 mm; na menší etiketu se úměrně zmenší.
Firma si v Nastavení vybere předvolbu nebo zadá vlastní rozměry a doladí posun
tiskárny (offset_x/offset_y – tiskárny běžně tisknou o 0,5–2 mm vedle).
"""

PRESETS: dict[str, dict] = {
    # Rozložení archů 99,1 × 42,3 mm dle šablony Avery (L7177/J8177): okraj nahoře 21,6, vlevo 4,65, mezera 2,5 mm
    "avery_j4776": {"name": "Avery Zweckform J4776 – 12 etiket 99,1 × 42,3 mm (2 × 6), odolné PET, INKOUST",
                    "page_w": 210, "page_h": 297, "cols": 2, "rows": 6, "label_w": 99.1, "label_h": 42.3,
                    "margin_left": 4.65, "margin_top": 21.6, "gap_x": 2.5, "gap_y": 0},
    "avery_l7913": {"name": "Avery Zweckform L7913 / L4776 – 12 etiket 99,1 × 42,3 mm (2 × 6), odolné PE/PET, jen LASER",
                    "page_w": 210, "page_h": 297, "cols": 2, "rows": 6, "label_w": 99.1, "label_h": 42.3,
                    "margin_left": 4.65, "margin_top": 21.6, "gap_x": 2.5, "gap_y": 0},
    "a4_2x4": {"name": "A4 – 8 etiket 105 × 74,25 mm (2 × 4, bez okrajů)",
               "page_w": 210, "page_h": 297, "cols": 2, "rows": 4, "label_w": 105, "label_h": 74.25,
               "margin_left": 0, "margin_top": 0, "gap_x": 0, "gap_y": 0},
    "a4_2x5": {"name": "A4 – 10 etiket 105 × 57 mm (2 × 5)",
               "page_w": 210, "page_h": 297, "cols": 2, "rows": 5, "label_w": 105, "label_h": 57,
               "margin_left": 0, "margin_top": 6, "gap_x": 0, "gap_y": 0},
    "a4_2x7": {"name": "A4 – 14 etiket 99,1 × 38,1 mm (2 × 7, typ L7163)",
               "page_w": 210, "page_h": 297, "cols": 2, "rows": 7, "label_w": 99.1, "label_h": 38.1,
               "margin_left": 4.65, "margin_top": 15.15, "gap_x": 2.5, "gap_y": 0},
    "avery_l6133": {"name": "Avery Zweckform L6133 – 24 etiket 70 × 37 mm (3 × 8), stříbrné PET, jen ČB LASER",
                    "page_w": 210, "page_h": 297, "cols": 3, "rows": 8, "label_w": 70, "label_h": 37,
                    "margin_left": 0, "margin_top": 0.5, "gap_x": 0, "gap_y": 0},
    "a4_1x1": {"name": "A4 – celý list (štítek v levém horním rohu)",
               "page_w": 210, "page_h": 297, "cols": 1, "rows": 1, "label_w": 105, "label_h": 74,
               "margin_left": 10, "margin_top": 10, "gap_x": 0, "gap_y": 0},
}
DEFAULT = "avery_j4776"
FIELDS = ("page_w", "page_h", "cols", "rows", "label_w", "label_h", "margin_left", "margin_top", "gap_x", "gap_y",
          "offset_x", "offset_y")
# Dvě rozvržení štítku: (minimální návrhová šířka, návrhová výška) v mm. Zmenšovat velký štítek na malou
# etiketu nejde – písmo by bylo nečitelné – proto má malá etiketa vlastní kompaktní rozvržení.
# Výška určuje měřítko, šířka se dopočítá z etikety (rozvržení je na šířku pružné).
LAYOUTS = {"large": (95.0, 74.0), "compact": (62.0, 37.0)}


def sheet_for(stored: dict | None) -> dict:
    """Arch z nastavení firmy (předvolba + vlastní úpravy) doplněný o výchozí hodnoty."""
    stored = stored or {}
    base = dict(PRESETS.get(stored.get("preset") or DEFAULT, PRESETS[DEFAULT]))
    base.update({"offset_x": 0.0, "offset_y": 0.0})
    for f in FIELDS:
        if stored.get(f) not in (None, ""):
            base[f] = stored[f]
    base["cols"], base["rows"] = int(base["cols"]), int(base["rows"])
    base["preset"] = stored.get("preset") or DEFAULT
    if base["preset"] not in PRESETS:
        base["name"] = "Vlastní rozměry"
    return base


def positions(sheet: dict, row: int, col: int, count: int) -> list[tuple[int, int]]:
    """Pozice (řada, sloupec; od 1) pro `count` štítků od zvolené pozice, po řádcích zleva doprava.

    Nevejde-li se vše na arch, vrátí jen tolik, kolik zbývá do konce archu.
    """
    start = (row - 1) * sheet["cols"] + (col - 1)
    total = sheet["cols"] * sheet["rows"]
    if not (0 <= start < total):
        raise ValueError("Pozice mimo arch")
    return [(i // sheet["cols"] + 1, i % sheet["cols"] + 1) for i in range(start, min(start + max(count, 1), total))]


def next_after(sheet: dict, last: tuple[int, int]) -> tuple[int, int]:
    """Další volná pozice po posledním vytištěném štítku (po konci archu zase od začátku)."""
    i = (last[0] - 1) * sheet["cols"] + last[1]
    if i >= sheet["cols"] * sheet["rows"]:
        return 1, 1
    return i // sheet["cols"] + 1, i % sheet["cols"] + 1


def layout_for(w: float, h: float) -> str:
    """Velké rozvržení jen tam, kde se vejde aspoň na 90 %; jinak kompaktní."""
    lw, lh = LAYOUTS["large"]
    return "large" if w >= lw * 0.9 and h >= lh * 0.9 else "compact"


def fit(w: float, h: float) -> dict:
    """Rozvržení pro etiketu w × h mm: měřítko podle výšky (nebo šířky, je-li úzká) a návrhové rozměry,
    které po zvětšení/zmenšení přesně vyplní etiketu."""
    layout = layout_for(w, h)
    lw_min, lh = LAYOUTS[layout]
    scale = min(h / lh, w / lw_min)
    return {"layout": layout, "scale": scale, "dw": w / scale, "dh": h / scale}


def cell_box(sheet: dict, row: int, col: int) -> dict:
    """Poloha etikety na listu (mm) + rozvržení, které ji vyplní."""
    left = sheet["margin_left"] + (col - 1) * (sheet["label_w"] + sheet["gap_x"]) + sheet["offset_x"]
    top = sheet["margin_top"] + (row - 1) * (sheet["label_h"] + sheet["gap_y"]) + sheet["offset_y"]
    return {"row": row, "col": col, "left": left, "top": top, "w": sheet["label_w"], "h": sheet["label_h"],
            **fit(sheet["label_w"], sheet["label_h"])}
