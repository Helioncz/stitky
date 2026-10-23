"""Jednopólové schéma zapojení jako SVG, vygenerované ze seznamu přístrojů.

Strom se staví z pole `feeds_from`: přístroje bez nadřazeného (kromě hlavního)
visí na hlavní přípojnici. Značky jsou zjednodušené podle ČSN EN 60617.
"""
from html import escape

LEAF_W = 58
SYMBOL_H = 40
LABEL_H = 26
LEAF_TEXT_H = 150
STROKE = 'stroke="#000" stroke-width="1.2" fill="none"'
# Značky kreslené obdélníkem (označení přístroje se píše vedle, ne přes ně)
BOX_KINDS = {"SPD", "METER", "RELAY", "OTHER"}


def _symbol(kind: str, cx: float, y: float) -> str:
    """Značka přístroje v oblasti y..y+SYMBOL_H, přívod nahoře, vývod dole."""
    top, bot = y, y + SYMBOL_H
    blade = (f'<line x1="{cx}" y1="{top}" x2="{cx}" y2="{top + 12}" {STROKE}/>'
             f'<line x1="{cx}" y1="{top + 30}" x2="{cx}" y2="{bot}" {STROKE}/>'
             f'<line x1="{cx}" y1="{top + 30}" x2="{cx - 9}" y2="{top + 13}" {STROKE}/>')
    cross = (f'<line x1="{cx - 3}" y1="{top + 9}" x2="{cx + 3}" y2="{top + 15}" {STROKE}/>'
             f'<line x1="{cx + 3}" y1="{top + 9}" x2="{cx - 3}" y2="{top + 15}" {STROKE}/>')
    oval = f'<ellipse cx="{cx}" cy="{top + 35}" rx="7" ry="3" {STROKE}/>'
    box = lambda text: (  # noqa: E731
        f'<line x1="{cx}" y1="{top}" x2="{cx}" y2="{top + 8}" {STROKE}/>'
        f'<rect x="{cx - 12}" y="{top + 8}" width="24" height="24" {STROKE}/>'
        f'<text x="{cx}" y="{top + 23}" font-size="7" text-anchor="middle">{text}</text>'
        f'<line x1="{cx}" y1="{top + 32}" x2="{cx}" y2="{bot}" {STROKE}/>'
    )
    if kind in ("MCB", "MCCB"):
        return blade + cross
    if kind == "RCD":
        return blade + oval
    if kind == "RCBO":
        return blade + cross + oval
    if kind == "SWITCH":
        return blade + f'<line x1="{cx - 4}" y1="{top + 12}" x2="{cx + 4}" y2="{top + 12}" {STROKE}/>'
    if kind == "CONTACTOR":
        return blade + f'<path d="M{cx - 4},{top + 12} a4,4 0 0 0 8,0" {STROKE}/>'
    if kind == "FUSE":
        return (f'<line x1="{cx}" y1="{top}" x2="{cx}" y2="{bot}" {STROKE}/>'
                f'<rect x="{cx - 5}" y="{top + 8}" width="10" height="24" {STROKE}/>')
    if kind == "SPD":
        return (box("SPD").replace(f'y2="{bot}"', f'y2="{top + 36}"')
                + f'<line x1="{cx - 8}" y1="{top + 36}" x2="{cx + 8}" y2="{top + 36}" {STROKE}/>'
                + f'<line x1="{cx - 5}" y1="{top + 38.5}" x2="{cx + 5}" y2="{top + 38.5}" {STROKE}/>'
                + f'<line x1="{cx - 2}" y1="{top + 41}" x2="{cx + 2}" y2="{top + 41}" {STROKE}/>')
    if kind == "METER":
        return box("kWh")
    if kind == "TERMINAL":
        return (f'<line x1="{cx}" y1="{top}" x2="{cx}" y2="{bot}" {STROKE}/>'
                f'<circle cx="{cx}" cy="{top + 20}" r="3" fill="#fff" stroke="#000" stroke-width="1.2"/>')
    return box(escape(kind[:4]))


def build_tree(devices: list, main) -> tuple[object | None, dict[int, list]]:
    by_desig = {d.designation: d for d in devices if d.designation}
    children: dict[int, list] = {}
    for d in devices:
        if d is main:
            continue
        parent = by_desig.get(d.feeds_from) if d.feeds_from else None
        if parent is None or parent is d:
            parent = main
        if parent is None:
            continue
        children.setdefault(id(parent), []).append(d)
    for lst in children.values():
        lst.sort(key=lambda x: x.position)
    return main, children


def _width(node, children) -> float:
    kids = children.get(id(node), [])
    return max(LEAF_W, sum(_width(k, children) for k in kids)) if kids else LEAF_W


def _depth(node, children) -> int:
    kids = children.get(id(node), [])
    return 1 + (max(_depth(k, children) for k in kids) if kids else 0)


def _render(node, children, x0: float, y: float, out: list[str]) -> float:
    w = _width(node, children)
    kids = children.get(id(node), [])
    cx = x0 + w / 2
    out.append(f'<line x1="{cx}" y1="{y}" x2="{cx}" y2="{y + 10}" {STROKE}/>')
    out.append(_symbol(node.kind, cx, y + 10))
    ty = y + 10 + SYMBOL_H
    rating = node.rating_text.split(", ")
    label_dx = 14 if node.kind in BOX_KINDS else 3
    out.append(f'<text x="{cx + label_dx}" y="{y + 22}" font-size="7.5" font-weight="bold">'
               f'{escape(node.designation)}</text>')
    out.append(f'<text x="{cx}" y="{ty + 9}" font-size="6.5" text-anchor="middle">'
               f'{escape(" ".join(rating[:2]))}</text>')
    out.append(f'<text x="{cx}" y="{ty + 17}" font-size="5.5" text-anchor="middle" fill="#444">'
               f'{escape((node.manufacturer + " " + node.type_code).strip()[:22])}</text>')
    by = ty + LABEL_H
    if kids:
        out.append(f'<line x1="{cx}" y1="{ty + 20}" x2="{cx}" y2="{by}" {STROKE}/>')
        xs = []
        x = x0
        for k in kids:
            kw = _width(k, children)
            xs.append(x + kw / 2)
            _render(k, children, x, by, out)
            x += kw
        out.append(f'<line x1="{min(xs)}" y1="{by}" x2="{max(xs)}" y2="{by}" stroke="#000" stroke-width="2.4"/>')
    else:
        out.append(f'<line x1="{cx}" y1="{ty + 20}" x2="{cx}" y2="{by + 4}" {STROKE}/>')
        out.append(f'<path d="M{cx - 3},{by} L{cx},{by + 6} L{cx + 3},{by} Z" fill="#000"/>')
        lines = [node.circuit_label, " ".join(p for p in (node.cable, node.phase) if p)]
        for i, text in enumerate(l for l in lines if l):
            out.append(f'<text transform="translate({cx + 3 + i * 9},{by + 12}) rotate(90)" font-size="7">'
                       f'{escape(text[:40])}</text>')
    return w


def render_svg(sb, main) -> str:
    devices = list(sb.devices)
    if not devices or main is None:
        return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 60">'
                '<text x="10" y="30" font-size="12">Schéma nelze sestavit – chybí hlavní přístroj.</text></svg>')
    root, children = build_tree(devices, main)
    width = _width(root, children) + 40
    depth = _depth(root, children)
    top = 46
    height = top + depth * (10 + SYMBOL_H + LABEL_H) + LEAF_TEXT_H
    out: list[str] = []
    supply = " · ".join(p for p in (sb.supply_cable, sb.phases, sb.earthing_system,
                                    f"{sb.un_v:g} V" if sb.un_v else "", f"{sb.fn_hz:g} Hz" if sb.fn_hz else "") if p)
    out.append(f'<text x="{20 + _width(root, children) / 2}" y="16" font-size="8" text-anchor="middle">'
               f'Přívod: {escape(supply)}</text>')
    out.append(f'<line x1="{20 + _width(root, children) / 2}" y1="22" x2="{20 + _width(root, children) / 2}" '
               f'y2="{top}" {STROKE}/>')
    _render(root, children, 20, top, out)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" '
            f'font-family="Arial, Helvetica, sans-serif">' + "".join(out) + "</svg>")
