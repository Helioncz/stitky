"""HTML → PDF přes Playwright (Chromium). Funguje stejně na Windows i v Dockeru.

Volat jen ze synchronního kódu (FastAPI sync endpoint běží ve vlákně) –
sync API Playwrightu nejde použít uvnitř běžící asyncio smyčky.
"""
from playwright.sync_api import sync_playwright


def html_to_pdf(html: str) -> bytes:
    return html_many_to_pdf([html])[0]


def html_many_to_pdf(htmls: list[str]) -> list[bytes]:
    """Víc dokumentů jedním spuštěním prohlížeče. Velikost stránky určuje CSS @page."""
    out = []
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        try:
            page = browser.new_page()
            for html in htmls:
                page.set_content(html, wait_until="load")
                out.append(page.pdf(print_background=True, prefer_css_page_size=True))
        finally:
            browser.close()
    return out
