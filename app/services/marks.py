"""Grafické značky na dokumentech: QR kód a označení CE (inline SVG)."""
import io

import qrcode
import qrcode.image.svg


def qr_svg(data: str) -> str:
    img = qrcode.make(data, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=1)
    buf = io.BytesIO()
    img.save(buf)
    svg = buf.getvalue().decode()
    return svg[svg.index("<svg"):]


def _half_annulus(cx: float, cy: float, r_out: float, r_in: float) -> str:
    return (f"M{cx},{cy - r_out} A{r_out},{r_out} 0 0 0 {cx},{cy + r_out} "
            f"L{cx},{cy + r_in} A{r_in},{r_in} 0 0 1 {cx},{cy - r_in} Z")


def ce_mark_svg() -> str:
    """Označení CE podle konstrukce z přílohy II rozhodnutí 768/2008/ES (zjednodušeně).

    Na štítku musí mít výšku min. 5 mm a zachované proporce – SVG se jen škáluje.
    """
    r_out, r_in = 50, 37
    c = _half_annulus(50, 50, r_out, r_in)
    e = _half_annulus(118, 50, r_out, r_in)
    bar = f"M{118 - r_out + 4},{50 - 6.5} H118 V{50 + 6.5} H{118 - r_out + 4} Z"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 100">'
            f'<path d="{c} {e}" fill="#000"/><path d="{bar}" fill="#000"/></svg>')
