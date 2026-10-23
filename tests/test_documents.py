import hashlib

from app.domain import characteristics
from app.services import documents, storage

from .conftest import make_switchboard, make_tenant


def test_analysis_suggests_values(db):
    t, _ = make_tenant(db, email="a1@test.cz")
    sb = make_switchboard(db, t, serial="A-1")
    a = characteristics.analyze(sb)
    assert a.main_device.designation == "-Q1"
    assert a.suggested_ina == 40
    assert a.suggested_icc == 6
    # vývody = koncové jisticí přístroje: F2, F3, F4, F5 (F1 je chránič, FA1 svodič)
    assert sorted(d.designation for d in a.outgoing) == ["-F2", "-F3", "-F4", "-F5"]
    assert a.suggested_rdf == 0.7  # DBO, 4 vývody


def test_warnings_for_dbo_limits(db):
    t, _ = make_tenant(db, email="a2@test.cz")
    sb = make_switchboard(db, t, serial="A-2")
    sb.ina_a, sb.icc_ka = 300, 10
    a = characteristics.analyze(sb)
    text = " ".join(a.warnings)
    assert "250 A" in text
    assert "vypínací schopnost" in text


def test_all_documents_render_html(db):
    t, u = make_tenant(db, email="a3@test.cz")
    sb = make_switchboard(db, t, serial="A-3")
    snap = documents.build_snapshot(sb, t, None)
    for kind in ["bundle", *documents.DOC_ORDER, "label"]:
        html = documents.render_html(kind, snap)
        assert sb.serial_number in html, kind
    eu = documents.render_html("eu_doc", snap)
    assert "2014/35/EU" in eu and "118/2016" in eu and "výhradní odpovědnost" in eu
    assert "ČSN EN 61439-3" in eu  # DBO
    assert "<svg" in documents.render_html("schematic", snap)


def test_issue_revision_creates_pdfs(db):
    t, u = make_tenant(db, email="a4@test.cz")
    sb = make_switchboard(db, t, serial="A/4")
    rev = documents.issue_revision(db, sb, u, note="první vydání")
    assert rev.number == 0
    kinds = {d.kind for d in rev.documents}
    assert kinds == {"bundle", "eu_doc", "interface", "schematic", "routine_test", "manual", "label"}
    for d in rev.documents:
        data = storage.load(d.storage_key)
        assert data.startswith(b"%PDF")
        assert hashlib.sha256(data).hexdigest() == d.sha256
    rev2 = documents.issue_revision(db, sb, u)
    assert rev2.number == 1
