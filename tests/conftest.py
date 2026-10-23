import os
import sys
import tempfile
from datetime import date
from pathlib import Path

import pytest

_tmp = tempfile.mkdtemp(prefix="stitky-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp, 'test.db').as_posix()}"
os.environ["DATA_DIR"] = _tmp
os.environ["GEMINI_API_KEY"] = ""
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal, init_db  # noqa: E402
from app.models import Device, Switchboard, Tenant, User  # noqa: E402
from app.security import hash_password  # noqa: E402

init_db()


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.close()


def make_tenant(db, name="Helion test s.r.o.", email="owner@test.cz") -> tuple[Tenant, User]:
    t = Tenant(name=name, ico="12345678", street="Testovací 1", city="Brno", zip="602 00",
               signer_name="Jan Novák", signer_position="jednatel", issue_place="Brno")
    db.add(t)
    db.flush()
    u = User(tenant_id=t.id, email=email, name="Jan Novák", password_hash=hash_password("heslo123"), role="owner")
    db.add(u)
    db.commit()
    return t, u


def make_switchboard(db, tenant: Tenant, serial="R2026-0001") -> Switchboard:
    sb = Switchboard(tenant_id=tenant.id, serial_number=serial, designation="RD", name="Rozvodnice RD",
                     site="RD Novákovi, Brno", ina_a=25, icc_ka=6, rdf=0.6, supply_cable="CYKY-J 5x10",
                     manufacture_date=date(2026, 10, 23), weight_kg=6.5, width_mm=400, height_mm=500, depth_mm=110,
                     routine_test={"test_date": "2026-10-23", "tested_by": "Jan Novák", "instrument": "MI 3152",
                                   "insulation_mohm": ">500",
                                   "items": {"11.2": {"result": "OK", "value": ""}, "11.9": {"result": "OK", "value": ">500 MΩ"}}})
    db.add(sb)
    db.flush()
    rows = [
        ("-Q1", "", "SWITCH", "Eaton", "IS-40/3", "3", 40, "", None, None),
        ("-FA1", "-Q1", "SPD", "Eaton", "SPBT12-280/4", "4", None, "", None, None),
        ("-F1", "-Q1", "RCD", "Eaton", "PF7-40/4/003", "4", 40, "", 10, 30),
        ("-F2", "-F1", "MCB", "Eaton", "PL6-B10/1", "1", 10, "B", 6, None),
        ("-F3", "-F1", "MCB", "Eaton", "PL6-B16/1", "1", 16, "B", 6, None),
        ("-F4", "-F1", "MCB", "Eaton", "PL6-C16/3", "3", 16, "C", 6, None),
        ("-F5", "-Q1", "RCBO", "Eaton", "PFL6-16/1N/B/003", "1+N", 16, "B", 6, 30),
    ]
    for i, (des, ff, kind, man, typ, poles, inn, curve, icn, idn) in enumerate(rows):
        db.add(Device(switchboard_id=sb.id, position=i, designation=des, feeds_from=ff, kind=kind, manufacturer=man,
                      type_code=typ, poles=poles, rated_current_a=inn, curve=curve, breaking_capacity_ka=icn,
                      residual_ma=idn, rcd_type="A" if idn else "", circuit_label=f"Okruh {des}",
                      cable="CYKY-J 3x2,5" if kind in ("MCB", "RCBO") else ""))
    db.commit()
    db.refresh(sb)
    return sb
