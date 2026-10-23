import io
import re

from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.models import Switchboard
from app.services import proposal

from .conftest import make_switchboard, make_tenant


def _client(email: str, company: str = "Firma") -> TestClient:
    c = TestClient(app)
    r = c.post("/signup", data={"company": company, "ico": "1", "name": "Technik", "email": email,
                                "password": "heslo1234"})
    assert r.status_code == 200, r.text
    return c


def _new_sb(c: TestClient) -> int:
    r = c.post("/sb/new")
    return int(re.search(r"/sb/(\d+)", str(r.url)).group(1))


def db_token(sb_id: int) -> str:
    from app.db import SessionLocal
    with SessionLocal() as s:
        return s.get(Switchboard, sb_id).public_token


def test_login_required():
    c = TestClient(app)
    r = c.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login")


def test_full_flow_and_isolation():
    c = _client("flow@test.cz", "Elektro Flow s.r.o.")
    c.post("/settings", data={"name": "Elektro Flow s.r.o.", "street": "Hlavní 1", "city": "Praha", "zip": "11000",
                              "signer_name": "Petr Technik", "signer_position": "jednatel", "serial_prefix": "EF"})
    sb_id = _new_sb(c)
    page = c.get(f"/sb/{sb_id}").text
    assert "Předvyplněný návrh" in page and "Riso &gt; 500 MΩ" in page   # kusová zkouška předvyplněna

    c.post(f"/sb/{sb_id}/devices", data={
        "d_designation": ["-Q1", "-F1", "-F2", ""], "d_feeds_from": ["", "-Q1", "-F1", ""],
        "d_kind": ["SWITCH", "RCD", "MCB", "MCB"], "d_manufacturer": ["OEZ", "OEZ", "OEZ", ""],
        "d_type_code": ["MSO-32-3", "LFN-40-4-030AC", "LTN-16B-1", ""], "d_poles": ["3", "4", "1", "1"],
        "d_rated_current_a": ["32", "40", "16", ""], "d_curve": ["", "", "B", ""],
        "d_breaking_capacity_ka": ["", "10", "10", ""], "d_residual_ma": ["", "30", "", ""],
        "d_rcd_type": ["", "AC", "", ""], "d_circuit_label": ["", "", "Zásuvky", ""], "d_cable": ["", "", "CYKY 3x2,5", ""],
        "d_phase": ["", "", "L1", ""], "d_source": ["manual"] * 4, "d_ai_confidence": [""] * 4,
    })
    c.post(f"/sb/{sb_id}/suggestions")
    # s předvyplněnou zkouškou jde vygenerovat, ale ne zamknout
    c.post(f"/sb/{sb_id}/generate")
    pre_rev = int(re.search(r'/revision/(\d+)/lock', c.get(f"/sb/{sb_id}").text).group(1))
    assert "jen předvyplněný návrh" in c.post(f"/revision/{pre_rev}/lock").text
    c.post(f"/sb/{sb_id}/routine-test", data={"test_date": "2026-10-23", "tested_by": "Petr", "r_11.2": "OK",
                                              "instrument": "Metrel MI 3152"})
    # další nový rozvaděč převezme měřák z poslední uložené zkoušky
    assert "Metrel MI 3152" in c.get(f"/sb/{_new_sb(c)}").text
    page = c.get(f"/sb/{sb_id}").text
    assert "EF2026-0001" in page and "MSO-32-3" in page

    assert "EU prohlášení o shodě" in c.get(f"/sb/{sb_id}/preview/eu_doc").text
    r = c.post(f"/sb/{sb_id}/generate", data={"note": "test"})
    assert "Vygenerována revize 00" in r.text and "nezamčeno" in r.text
    doc_id = int(re.search(r'href="/doc/(\d+)"', r.text).group(1))
    assert c.get(f"/doc/{doc_id}").content.startswith(b"%PDF")

    # nezamčená revize: zákazník nic nevidí, katalog se zatím neučí
    token = db_token(sb_id)
    assert TestClient(app).get(f"/d/{token}").status_code == 404
    assert c.get("/catalog/search?q=LTN-16").json() == []

    # přegenerování otevřené revize = stejné číslo
    r = c.post(f"/sb/{sb_id}/generate")
    assert "Vygenerována revize 00" in r.text and "revize 01" not in r.text.lower()

    # změna údajů po vygenerování → zamčení odmítnuto
    c.post(f"/sb/{sb_id}", data={"site": "Změněná akce"})
    rev_id = int(re.search(r'/revision/(\d+)/lock', c.get(f"/sb/{sb_id}").text).group(1))
    r = c.post(f"/revision/{rev_id}/lock")
    assert "nejdřív dokumentaci vygenerujte znovu" in r.text
    c.post(f"/sb/{sb_id}/generate")
    r = c.post(f"/revision/{rev_id}/lock")
    assert "zamčena a archivována" in r.text
    assert "Vygenerovat PDF – revize 01" in r.text   # další generování = nová revize

    # katalog se naučil potvrzené přístroje
    hits = c.get("/catalog/search?q=LTN-16").json()
    assert hits and hits[0]["verified"] and hits[0]["breaking_capacity_ka"] == 10

    # veřejná stránka přes token
    pub = TestClient(app).get(f"/d/{token}")
    assert pub.status_code == 200 and "EF2026-0001" in pub.text

    # jiná firma nevidí nic
    other = _client("other@test.cz", "Cizí firma")
    assert other.get(f"/sb/{sb_id}").status_code == 404
    assert other.get(f"/doc/{doc_id}").status_code == 404
    assert other.post(f"/sb/{sb_id}/delete").status_code == 404
    assert "EF2026" not in other.get("/").text


def test_photo_upload_and_delete_draft():
    c = _client("photo@test.cz")
    sb_id = _new_sb(c)
    buf = io.BytesIO()
    Image.new("RGB", (4000, 3000), "white").save(buf, "JPEG")
    r = c.post(f"/sb/{sb_id}/photos", files=[("files", ("rozvadec.jpg", buf.getvalue(), "image/jpeg"))])
    photo_id = int(re.search(r'/photos/(\d+)"', r.text).group(1))
    img = Image.open(io.BytesIO(c.get(f"/photos/{photo_id}").content))
    assert max(img.size) == 2400
    assert c.post(f"/sb/{sb_id}/delete").status_code == 200
    assert c.get(f"/sb/{sb_id}").status_code == 404


def test_recognize_runs_in_background(monkeypatch):
    import time

    from app.services import ai

    calls = {"n": 0}

    def fake(images):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("503 UNAVAILABLE")
        time.sleep(0.3)
        return {"devices": [{"row": 1, "kind": "MCB", "manufacturer": "OEZ", "type_code": "LTE B16", "system": "AC",
                             "designation": "", "is_main": True, "confidence": 0.9}],
                "rows": {"1": "AC"}, "enclosure": {}, "nameplate": {}, "notes": ""}, "fake-model"

    monkeypatch.setattr(ai, "recognize", fake)
    c = _client("bg@test.cz")
    sb_id = _new_sb(c)
    buf = io.BytesIO()
    Image.new("RGB", (100, 80), "white").save(buf, "JPEG")
    c.post(f"/sb/{sb_id}/photos", files=[("files", ("a.jpg", buf.getvalue(), "image/jpeg"))])

    def wait():
        for _ in range(50):
            s = c.get(f"/sb/{sb_id}/recognize/status").json()["status"]
            if s != "running":
                return s
            time.sleep(0.1)
        return "timeout"

    c.post(f"/sb/{sb_id}/recognize")          # vrátí se hned, AI běží na pozadí
    assert wait() == "error"
    assert "503 UNAVAILABLE" in c.get(f"/sb/{sb_id}").text
    c.post(f"/sb/{sb_id}/recognize")
    assert wait() == "done"
    page = c.get(f"/sb/{sb_id}").text
    assert "LTE B16" in page and "fake-model" in page and "Rozpoznání se nepovedlo" not in page


def test_proposal_designations_and_feeds(db):
    t, _ = make_tenant(db, email="prop@test.cz")
    sb = make_switchboard(db, t, serial="P-1")
    proposed = [
        {"row": 1, "kind": "SWITCH", "manufacturer": "Eaton", "type_code": "IS-40/3", "rated_current_a": 40},
        {"row": 1, "kind": "RCD", "manufacturer": "Eaton", "type_code": "PF7-40/4/003"},
        {"row": 1, "kind": "MCB", "manufacturer": "Eaton", "type_code": "PL6-B10/1"},
        {"row": 2, "kind": "MCB", "manufacturer": "Eaton", "type_code": "PL6-B16/1"},
        {"row": 2, "kind": "SPD", "manufacturer": "Eaton", "type_code": "SPBT12"},
    ]
    proposal.apply(db, sb, proposed, replace=True)
    db.commit()
    sb = db.get(Switchboard, sb.id)
    got = [(d.designation, d.feeds_from) for d in sb.devices]
    assert got == [("-Q1", ""), ("-F1", "-Q1"), ("-F2", "-F1"), ("-F3", "-Q1"), ("-FA1", "-Q1")]


def test_pv_switchboard_dc_row_is_separate(db):
    """FVE rozvaděč: lišta 1 = DC (svodiče PV, svorky), lišta 2 = AC. DC se nesmí napájet z AC."""
    from app.domain import characteristics
    from app.services import documents
    t, _ = make_tenant(db, email="pv@test.cz")
    sb = make_switchboard(db, t, serial="PV-1")
    proposed = [
        {"row": 1, "kind": "TERMINAL"},
        {"row": 1, "kind": "SPD", "manufacturer": "Mersen", "type_code": "SP12-SK1000V-PV", "rated_voltage_v": 1000},
        {"row": 1, "kind": "SPD", "manufacturer": "Mersen", "type_code": "SP12-SK1000V-PV", "system": "AC"},
        {"row": 2, "kind": "MCB", "rated_current_a": 16, "poles": "3", "breaking_capacity_ka": 6},
        {"row": 2, "kind": "SPD", "type_code": "FLP-12,5 V"},
        {"row": 2, "kind": "MCB", "rated_current_a": 6, "breaking_capacity_ka": 6},
    ]
    proposal.apply(db, sb, proposed, replace=True, row_systems={"1": "DC", "2": "AC"})
    db.commit()
    sb = db.get(Switchboard, sb.id)
    dc = [d for d in sb.devices if d.is_dc]
    ac = [d for d in sb.devices if not d.is_dc]
    assert len(dc) == 3 and all(d.feeds_from == "" for d in dc)  # technikova volba lišty má přednost před AI
    main = characteristics.find_main_device(list(sb.devices))
    assert main in ac and main.rated_current_a == 16
    assert all(d.feeds_from == main.designation for d in ac if d is not main)

    sb.dc_un_v, sb.ui_v, sb.standard_part = 1000, 500, "3"
    warnings = " ".join(characteristics.analyze(sb).warnings)
    assert "Ui sestavy (500 V)" in warnings and "DBO" in warnings and "Isc" in warnings
    assert "chybí jmenovité DC napětí" in warnings  # druhý svodič bez napětí

    snap = documents.build_snapshot(sb, t, None)
    assert "DC – FV pole, max. 1000 V DC" in snap["schematic_svg"]
    assert "pod napětím i po vypnutí AC" in documents.render_html("manual", snap)
    assert "1000 V DC" in documents.render_html("interface", snap)


def test_proposal_uses_photo_labels_and_main_on_bottom_row(db):
    """Rozvaděč FVE (Strunk): označení ze štítkového pruhu, hlavní vypínač až na 3. liště."""
    t, _ = make_tenant(db, email="strunk@test.cz")
    sb = make_switchboard(db, t, serial="S-1")
    proposed = [
        {"row": 1, "designation": "-F2", "kind": "MCB", "rated_current_a": 6},
        {"row": 1, "designation": "-K1", "kind": "RELAY"},
        {"row": 1, "designation": "", "kind": "MCB", "rated_current_a": 20},   # bez popisku
        {"row": 2, "designation": "-KM1", "kind": "CONTACTOR"},
        {"row": 3, "designation": "-Q0", "kind": "SWITCH", "is_main": True, "poles": "4"},
    ]
    proposal.apply(db, sb, proposed, replace=True)
    changed = proposal.apply_enclosure(sb, {"manufacturer": "Legrand", "series": "Plexo³", "modules": 54,
                                            "ip_code": "IP65", "width_mm": 460})
    db.commit()
    sb = db.get(Switchboard, sb.id)
    got = [(d.designation, d.feeds_from) for d in sb.devices]
    assert got[0] == ("-Q0", "")
    assert ("-F2", "-Q0") in got and ("-KM1", "-Q0") in got and ("-F1", "-Q0") in got
    assert sb.enclosure_manufacturer == "Legrand" and "54 modulů" in sb.enclosure_type
    assert sb.ip_code == "IP65" and "ip_code" in changed
    assert sb.width_mm == 400  # už vyplněné pole se nepřepisuje
