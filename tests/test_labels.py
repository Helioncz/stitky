import re

from fastapi.testclient import TestClient

from app.domain import label_sheets as ls
from app.main import app


def test_positions_and_next():
    sheet = ls.sheet_for({"preset": "avery_j4776"})
    assert (sheet["cols"], sheet["rows"]) == (2, 6)
    # 2. řada, 2. zleva + 3 kusy → pokračuje na další řadu
    assert ls.positions(sheet, 2, 2, 3) == [(2, 2), (3, 1), (3, 2)]
    # na konci archu se nepřetéká
    assert ls.positions(sheet, 6, 2, 5) == [(6, 2)]
    assert ls.next_after(sheet, (3, 2)) == (4, 1)
    assert ls.next_after(sheet, (6, 2)) == (1, 1)


def test_cell_box_geometry_and_layout():
    sheet = ls.sheet_for({"preset": "avery_j4776", "offset_x": 1.0})
    box = ls.cell_box(sheet, 2, 2)
    assert box["left"] == 4.65 + 99.1 + 2.5 + 1.0
    assert abs(box["top"] - (21.6 + 42.3)) < 1e-9
    assert box["layout"] == "compact"
    # rozvržení přesně vyplní etiketu
    assert abs(box["dw"] * box["scale"] - 99.1) < 1e-9 and abs(box["dh"] * box["scale"] - 42.3) < 1e-9
    assert ls.cell_box(ls.sheet_for({"preset": "a4_2x4"}), 1, 1)["layout"] == "large"


def test_label_print_flow():
    c = TestClient(app)
    c.post("/signup", data={"company": "Tisk s.r.o.", "name": "T", "email": "tisk@test.cz", "password": "heslo1234"})
    r = c.post("/sb/new")
    sb_id = int(re.search(r"/sb/(\d+)", str(r.url)).group(1))
    page = c.get(f"/sb/{sb_id}/label")
    assert page.status_code == 200 and "J4776" in page.text
    pdf = c.get(f"/sb/{sb_id}/label.pdf?row=2&col=2&count=2")
    assert pdf.content.startswith(b"%PDF")
    # 2 kusy od 2/2 obsadí 2/2 a 3/1 → další volná 3/2 se předvyplní
    nxt = c.get(f"/sb/{sb_id}/label").text
    assert 'id="row" value="3"' in nxt and 'id="col" value="2"' in nxt
    assert c.get(f"/sb/{sb_id}/label.pdf?row=9&col=1").status_code == 400
    assert c.get("/settings/label-test.pdf").content.startswith(b"%PDF")
    # vlastní nastavení archu
    c.post("/settings/label-sheet", data={"preset": "avery_l6133", "offset_x": "0,5"})
    assert 'id="row" value="1"' in c.get(f"/sb/{sb_id}/label").text
    assert "L6133" in c.get("/settings").text
