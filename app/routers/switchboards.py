"""Rozvaděče: seznam, editace, přístroje, fotky + AI, kusová zkouška, vydání a archiv."""
import io
import logging
import threading
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from PIL import Image, ImageOps
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db import SessionLocal, get_db
from app.domain import characteristics, standards
from app.models import Customer, Device, Document, Photo, Revision, Switchboard, User
from app.security import current_user, get_owned
from app.services import ai, catalog, documents, proposal, storage
from app.web import flash, redirect, render, to_float, to_int

router = APIRouter()
logger = logging.getLogger(__name__)

TEXT_FIELDS = [
    "designation", "type_designation", "name", "site", "order_number", "standard_part", "phases",
    "earthing_system", "ip_code", "ip_code_open", "ik_code", "location", "installation", "mounting",
    "emc_environment", "internal_form", "protection_class", "operated_by", "enclosure_manufacturer",
    "enclosure_type", "supply_cable", "notes", "dc_earthing",
]
FLOAT_FIELDS = ["un_v", "ue_v", "ui_v", "uimp_kv", "fn_hz", "ina_a", "icc_ka", "icw_ka", "ipk_ka", "rdf", "weight_kg",
                "dc_un_v", "dc_isc_a"]
INT_FIELDS = ["pollution_degree", "width_mm", "height_mm", "depth_mm", "dc_inputs"]
MAX_PHOTO_PX = 2400


def routine_test_proposal(db: Session, user: User) -> dict:
    """Návrh kusové zkoušky: měřák a hodnoty z poslední uložené zkoušky firmy, jinak obvyklé hodnoty.

    Je označený "prefilled" – dokud ho technik neuloží, nejde revizi zamknout.
    """
    last = None
    for sb in db.scalars(select(Switchboard).where(Switchboard.tenant_id == user.tenant_id)
                         .order_by(Switchboard.updated_at.desc()).limit(30)):
        rt = sb.routine_test or {}
        if rt.get("items") and not rt.get("prefilled"):
            last = rt
            break
    last = last or {}
    last_items = last.get("items") or {}
    items = {code: {"result": "OK",
                    "value": (last_items.get(code) or {}).get("value") or standards.ROUTINE_TEST_DEFAULT_VALUES.get(code, "")}
             for code, _ in standards.ROUTINE_TEST_ITEMS}
    return {"prefilled": True, "tested_by": user.name, "test_date": date.today().isoformat(),
            "instrument": last.get("instrument", ""),
            "insulation_mohm": last.get("insulation_mohm") or standards.ROUTINE_TEST_DEFAULT_INSULATION,
            "items": items}


def _customers(db: Session, user: User) -> list[Customer]:
    return db.scalars(select(Customer).where(Customer.tenant_id == user.tenant_id).order_by(Customer.name)).all()


def _set_customer(db: Session, sb: Switchboard, user: User, name: str, address: str) -> None:
    name = name.strip()
    if not name:
        sb.customer_id = None
        return
    cust = db.scalar(select(Customer).where(Customer.tenant_id == user.tenant_id, Customer.name == name))
    if cust is None:
        cust = Customer(tenant_id=user.tenant_id, name=name, address=address.strip())
        db.add(cust)
        db.flush()
    elif address.strip():
        cust.address = address.strip()
    sb.customer_id = cust.id


@router.get("/")
def dashboard(request: Request, q: str = "", user: User = Depends(current_user), db: Session = Depends(get_db)):
    stmt = (select(Switchboard).outerjoin(Customer).where(Switchboard.tenant_id == user.tenant_id)
            .order_by(Switchboard.updated_at.desc()))
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Switchboard.serial_number.ilike(like), Switchboard.name.ilike(like),
                              Switchboard.site.ilike(like), Switchboard.designation.ilike(like),
                              Switchboard.order_number.ilike(like), Customer.name.ilike(like)))
    return render(request, "dashboard.html", user=user, items=db.scalars(stmt.limit(200)).all(), q=q)


@router.post("/sb/new")
def create(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    tenant = user.tenant
    sb = Switchboard(tenant_id=tenant.id, serial_number=documents.next_serial(tenant), created_by_id=user.id,
                     manufacture_date=date.today(), routine_test=routine_test_proposal(db, user))
    db.add(sb)
    db.commit()
    flash(request, f"Založen rozvaděč {sb.serial_number}. Nahrajte fotky nebo zadejte přístroje.")
    return redirect(f"/sb/{sb.id}")


@router.post("/sb/{sb_id}/copy")
def copy(request: Request, sb_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    src = get_owned(db, Switchboard, sb_id, user)
    sb = Switchboard(tenant_id=user.tenant_id, serial_number=documents.next_serial(user.tenant),
                     created_by_id=user.id, manufacture_date=date.today(), customer_id=src.customer_id)
    for f in TEXT_FIELDS + FLOAT_FIELDS + INT_FIELDS:
        setattr(sb, f, getattr(src, f))
    sb.routine_test = routine_test_proposal(db, user)
    for d in src.devices:
        sb.devices.append(Device(**{c.key: getattr(d, c.key) for c in Device.__table__.columns
                                    if c.key not in ("id", "switchboard_id")}))
    db.add(sb)
    db.commit()
    flash(request, f"Vytvořena kopie {sb.serial_number} (bez fotek a revizí).")
    return redirect(f"/sb/{sb.id}")


@router.post("/sb/{sb_id}/delete")
def delete(request: Request, sb_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    sb = get_owned(db, Switchboard, sb_id, user)
    if sb.latest_locked:
        flash(request, "Rozvaděč se zamčenou dokumentací nelze smazat – je součástí archivu.", "error")
        return redirect(f"/sb/{sb.id}")
    db.delete(sb)
    db.commit()
    flash(request, "Koncept rozvaděče smazán.")
    return redirect("/")


@router.get("/sb/{sb_id}")
def detail(request: Request, sb_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    sb = get_owned(db, Switchboard, sb_id, user)
    analysis = characteristics.analyze(sb)
    rt = sb.routine_test or {}
    if not rt.get("items"):  # starší rozvaděč bez zkoušky – ukážeme návrh (uloží se až tlačítkem)
        rt = routine_test_proposal(db, user)
    rt_items = rt.get("items") or {}
    open_rev = sb.open_revision
    stale = bool(open_rev) and documents.data_hash(
        documents.build_snapshot(sb, user.tenant, open_rev.number)) != open_rev.snapshot.get("data_hash")
    return render(request, "switchboard.html", user=user, sb=sb, a=analysis, customers=_customers(db, user),
                  open_rev=open_rev, stale=stale, ai_running=_recognize_running(sb.ai_proposal), rt=rt,
                  rt_rows=[(c, t, rt_items.get(c) or {}) for c, t in standards.ROUTINE_TEST_ITEMS],
                  blocking=characteristics.blocking(analysis.warnings),
                  public_url=documents.public_url(sb))


@router.post("/sb/{sb_id}")
async def save(request: Request, sb_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    sb = get_owned(db, Switchboard, sb_id, user)
    form = await request.form()
    serial = str(form.get("serial_number", "")).strip()
    if serial and serial != sb.serial_number:
        clash = db.scalar(select(Switchboard).where(Switchboard.tenant_id == user.tenant_id,
                                                    Switchboard.serial_number == serial))
        if clash:
            flash(request, f"Výrobní číslo {serial} už má jiný rozvaděč.", "error")
            return redirect(f"/sb/{sb.id}")
        sb.serial_number = serial
    for f in TEXT_FIELDS:
        if f in form:
            setattr(sb, f, str(form[f]).strip())
    for f in FLOAT_FIELDS:
        if f in form:
            setattr(sb, f, to_float(form[f]))
    for f in INT_FIELDS:
        if f in form:
            setattr(sb, f, to_int(form[f]))
    if form.get("manufacture_date"):
        sb.manufacture_date = date.fromisoformat(str(form["manufacture_date"]))
    _set_customer(db, sb, user, str(form.get("customer_name", "")), str(form.get("customer_address", "")))
    db.commit()
    flash(request, "Údaje uloženy.")
    return redirect(f"/sb/{sb.id}#udaje")


@router.post("/sb/{sb_id}/suggestions")
def apply_suggestions(request: Request, sb_id: int, user: User = Depends(current_user),
                      db: Session = Depends(get_db)):
    sb = get_owned(db, Switchboard, sb_id, user)
    a = characteristics.analyze(sb)
    changed = []
    for field, value in (("ina_a", a.suggested_ina), ("icc_ka", a.suggested_icc), ("rdf", a.suggested_rdf)):
        if value is not None and getattr(sb, field) != value:
            setattr(sb, field, value)
            changed.append(field)
    db.commit()
    flash(request, "Převzaty navržené hodnoty: " + (", ".join(changed) if changed else "nic se nezměnilo"))
    return redirect(f"/sb/{sb.id}#udaje")


DEVICE_TEXT = ["designation", "feeds_from", "kind", "manufacturer", "type_code", "poles", "curve", "rcd_type",
               "circuit_label", "cable", "phase", "source", "system"]
DEVICE_FLOAT = ["rated_current_a", "breaking_capacity_ka", "residual_ma", "ai_confidence", "rated_voltage_v", "din_row"]


@router.post("/sb/{sb_id}/devices")
async def save_devices(request: Request, sb_id: int, user: User = Depends(current_user),
                       db: Session = Depends(get_db)):
    """Tabulka přístrojů se ukládá celá – co ve formuláři chybí, bylo smazáno."""
    sb = get_owned(db, Switchboard, sb_id, user)
    form = await request.form()
    cols = {f: form.getlist(f"d_{f}") for f in DEVICE_TEXT + DEVICE_FLOAT}
    n = len(cols["kind"])
    sb.devices.clear()
    db.flush()
    for i in range(n):
        dev = Device(position=i)
        for f in DEVICE_TEXT:
            setattr(dev, f, str(cols[f][i]).strip() if i < len(cols[f]) else "")
        for f in DEVICE_FLOAT:
            setattr(dev, f, to_float(cols[f][i]) if i < len(cols[f]) else None)
        dev.source = dev.source or "manual"
        dev.system = "DC" if dev.system == "DC" else "AC"
        dev.din_row = int(dev.din_row) if dev.din_row else None
        if not (dev.type_code or dev.designation or dev.rated_current_a):
            continue  # prázdný řádek
        sb.devices.append(dev)
    db.commit()
    flash(request, f"Uloženo {len(sb.devices)} přístrojů.")
    return redirect(f"/sb/{sb.id}#pristroje")


@router.post("/sb/{sb_id}/routine-test")
async def save_routine_test(request: Request, sb_id: int, user: User = Depends(current_user),
                            db: Session = Depends(get_db)):
    sb = get_owned(db, Switchboard, sb_id, user)
    form = await request.form()
    items = {code: {"result": str(form.get(f"r_{code}", "")), "value": str(form.get(f"v_{code}", "")).strip()}
             for code, _ in standards.ROUTINE_TEST_ITEMS}
    sb.routine_test = {
        "test_date": str(form.get("test_date", "")),
        "tested_by": str(form.get("tested_by", "")).strip(),
        "instrument": str(form.get("instrument", "")).strip(),
        "insulation_mohm": str(form.get("insulation_mohm", "")).strip(),
        "items": items,
    }
    db.commit()
    flash(request, "Kusová zkouška uložena.")
    return redirect(f"/sb/{sb.id}#zkouska")


# ── Fotky a AI ─────────────────────────────────────────────────────────────

def _normalize_image(data: bytes) -> tuple[bytes, str]:
    """Otočí podle EXIF, zmenší na max. 2400 px a uloží jako JPEG (menší úložiště i AI dotaz)."""
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
    img.thumbnail((MAX_PHOTO_PX, MAX_PHOTO_PX))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=88)
    return buf.getvalue(), "image/jpeg"


@router.post("/sb/{sb_id}/photos")
def upload_photos(request: Request, sb_id: int, files: list[UploadFile] = File(...),
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    sb = get_owned(db, Switchboard, sb_id, user)
    count = 0
    for f in files:
        raw = f.file.read()
        if not raw:
            continue
        try:
            data, mime = _normalize_image(raw)
        except Exception:  # noqa: BLE001 – nečitelný obrázek
            flash(request, f"Soubor {f.filename} není obrázek.", "error")
            continue
        photo = Photo(switchboard_id=sb.id, storage_key="", mime_type=mime)
        db.add(photo)
        db.flush()
        photo.storage_key = storage.save(f"t{sb.tenant_id}/sb{sb.id}/photos/{photo.id}.jpg", data)
        count += 1
    db.commit()
    if count:
        flash(request, f"Nahráno fotek: {count}. Teď můžete spustit rozpoznání přístrojů.")
    return redirect(f"/sb/{sb.id}#fotky")


@router.get("/photos/{photo_id}")
def photo(photo_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = get_owned(db, Photo, photo_id, user)
    return Response(storage.load(p.storage_key), media_type=p.mime_type,
                    headers={"Cache-Control": "private, max-age=86400"})


@router.post("/photos/{photo_id}/delete")
def delete_photo(request: Request, photo_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = get_owned(db, Photo, photo_id, user)
    sb_id = p.switchboard_id
    db.delete(p)
    db.commit()
    return redirect(f"/sb/{sb_id}#fotky")


RECOGNIZE_STALE_S = 300  # „running“ starší než 5 min = zaseknuté (např. restart serveru)


def _recognize_running(prop: dict) -> bool:
    if (prop or {}).get("status") != "running":
        return False
    started = datetime.fromisoformat(prop.get("started"))
    return (datetime.now(timezone.utc) - started).total_seconds() < RECOGNIZE_STALE_S


def _recognize_job(sb_id: int) -> None:
    """Běží ve vlákně na pozadí – AI trvá desítky sekund a na mobilu by se požadavek přerušil."""
    db = SessionLocal()
    try:
        sb = db.get(Switchboard, sb_id)
        prev = dict(sb.ai_proposal or {})
        try:
            images = [(storage.load(p.storage_key), p.mime_type) for p in sb.photos]
            result, model = ai.recognize(images)
            for d in result["devices"]:
                cat = catalog.lookup(db, sb.tenant_id, d["manufacturer"], d["type_code"])
                d["catalog"] = bool(cat and cat.verified)
            sb.ai_proposal = {"status": "done", "model": model, "at": datetime.now(timezone.utc).isoformat(), **result}
        except Exception as exc:  # noqa: BLE001
            logger.exception("Rozpoznání rozvaděče %s selhalo", sb_id)
            sb.ai_proposal = {**prev, "status": "error", "error": str(exc)[:500]}
        db.commit()
    finally:
        db.close()


@router.post("/sb/{sb_id}/recognize")
def recognize(request: Request, sb_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    sb = get_owned(db, Switchboard, sb_id, user)
    if not sb.photos:
        flash(request, "Nejdřív nahrajte fotky rozvaděče.", "error")
        return redirect(f"/sb/{sb.id}#fotky")
    if _recognize_running(sb.ai_proposal):
        return redirect(f"/sb/{sb.id}#fotky")
    prev = {k: v for k, v in (sb.ai_proposal or {}).items() if k not in ("status", "error", "started")}
    sb.ai_proposal = {**prev, "status": "running", "started": datetime.now(timezone.utc).isoformat()}
    db.commit()
    threading.Thread(target=_recognize_job, args=(sb.id,), daemon=True).start()
    return redirect(f"/sb/{sb.id}#fotky")


@router.get("/sb/{sb_id}/recognize/status")
def recognize_status(sb_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    sb = get_owned(db, Switchboard, sb_id, user)
    prop = sb.ai_proposal or {}
    status = "running" if _recognize_running(prop) else ("stale" if prop.get("status") == "running" else
                                                         prop.get("status") or "")
    return JSONResponse({"status": status})


@router.post("/sb/{sb_id}/proposal")
async def apply_proposal(request: Request, sb_id: int, user: User = Depends(current_user),
                         db: Session = Depends(get_db)):
    sb = get_owned(db, Switchboard, sb_id, user)
    form = await request.form()
    mode = str(form.get("mode", "replace"))
    devices = (sb.ai_proposal or {}).get("devices") or []
    if not devices:
        flash(request, "Není co převzít.", "error")
        return redirect(f"/sb/{sb.id}#fotky")
    # soustava po lištách potvrzená technikem (AI ji z fotky spolehlivě nepozná)
    row_systems = {k[len("sys_row_"):]: ("DC" if str(v) == "DC" else "AC")
                   for k, v in form.items() if k.startswith("sys_row_")}
    n = proposal.apply(db, sb, devices, replace=(mode == "replace"), row_systems=row_systems)
    if "DC" in row_systems.values():
        flash(request, "Rozvaděč má DC část – v části 3 doplňte Uoc max, Isc a počet vstupů, zkontrolujte Ui "
                       "a druh sestavy (FV DC nad 300 V = výkonový rozvaděč 61439-2).")
    enc_changed = proposal.apply_enclosure(sb, sb.ai_proposal.get("enclosure") or {})
    db.commit()
    msg = f"Převzato {n} přístrojů. Zkontrolujte označení, „napájeno z“ a parametry."
    if enc_changed:
        msg += " Doplněny údaje skříně – zkontrolujte je v části 3."
    flash(request, msg)
    return redirect(f"/sb/{sb.id}#pristroje")


@router.get("/catalog/search")
def catalog_search(q: str = "", user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = catalog.search(db, user.tenant_id, q) if len(q.strip()) >= 2 else []
    return JSONResponse([{
        "manufacturer": r.manufacturer, "type_code": r.type_code, "kind": r.kind, "poles": r.poles,
        "rated_current_a": r.rated_current_a, "curve": r.curve, "breaking_capacity_ka": r.breaking_capacity_ka,
        "residual_ma": r.residual_ma, "rcd_type": r.rcd_type, "verified": r.verified,
    } for r in rows])


# ── Dokumenty ──────────────────────────────────────────────────────────────

@router.get("/sb/{sb_id}/preview/{kind}", response_class=HTMLResponse)
def preview(sb_id: int, kind: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    sb = get_owned(db, Switchboard, sb_id, user)
    snap = documents.build_snapshot(sb, user.tenant, None, issued_by=user)
    try:
        return HTMLResponse(documents.render_html(kind, snap))
    except KeyError:
        raise HTTPException(404) from None


@router.post("/sb/{sb_id}/generate")
def generate(request: Request, sb_id: int, note: str = Form(""), user: User = Depends(current_user),
             db: Session = Depends(get_db)):
    sb = get_owned(db, Switchboard, sb_id, user)
    try:
        rev = documents.generate_revision(db, sb, user, note=note.strip())
    except ValueError as exc:
        db.rollback()
        flash(request, str(exc), "error")
        return redirect(f"/sb/{sb.id}#vydani")
    flash(request, f"Vygenerována revize {rev.number:02d}. Zkontrolujte PDF a pak revizi zamkněte.")
    return redirect(f"/sb/{sb.id}#vydani")


@router.post("/revision/{rev_id}/lock")
def lock(request: Request, rev_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rev = db.get(Revision, rev_id)
    if rev is None:
        raise HTTPException(404)
    sb = get_owned(db, Switchboard, rev.switchboard_id, user)
    try:
        documents.lock_revision(db, rev, user)
    except ValueError as exc:
        db.rollback()
        flash(request, str(exc), "error")
        return redirect(f"/sb/{sb.id}#vydani")
    flash(request, f"Revize {rev.number:02d} zamčena a archivována. Zákazník ji teď vidí přes QR kód.")
    return redirect(f"/sb/{sb.id}#vydani")


@router.get("/doc/{doc_id}")
def download(doc_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    doc = db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(404)
    get_owned(db, Switchboard, doc.revision.switchboard_id, user)
    filename = doc.storage_key.rsplit("/", 1)[-1]
    return Response(storage.load(doc.storage_key), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{filename}"'})


@router.get("/revision/{rev_id}/snapshot")
def revision_snapshot(rev_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rev = db.get(Revision, rev_id)
    if rev is None:
        raise HTTPException(404)
    get_owned(db, Switchboard, rev.switchboard_id, user)
    data = {k: v for k, v in rev.snapshot.items() if not k.endswith("_svg")}
    data.get("tenant", {}).pop("logo", None)
    return JSONResponse(data)
