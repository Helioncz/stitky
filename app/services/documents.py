"""Sestavení dokumentace rozvaděče a vydání revize.

Šablony v templates/docs pracují VÝHRADNĚ se snapshotem (čistý dict), ne s ORM
objekty. Snapshot se při vydání uloží do revize, takže archivovanou revizi lze
kdykoli přesně znovu vykreslit, i když se mezitím změnil rozvaděč nebo firma.
"""
import base64
import hashlib
from datetime import date, datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.domain import characteristics, standards
from app.models import DOCUMENT_KINDS, Document, Revision, Switchboard, Tenant, User
from app.services import catalog, marks, pdf, schematic, storage

TEMPLATES = Path(__file__).resolve().parent.parent / "templates" / "docs"
DOC_ORDER = ["eu_doc", "interface", "schematic", "routine_test", "manual"]


def num(v, digits: int | None = None) -> str:
    if v is None or v == "":
        return "–"
    if isinstance(v, (int, float)):
        s = f"{v:.{digits}f}" if digits is not None else f"{v:g}"
        return s.replace(".", ",")
    return str(v)


def czdate(v) -> str:
    if not v:
        return "–"
    if isinstance(v, str):
        v = date.fromisoformat(v[:10])
    return f"{v.day}. {v.month}. {v.year}"


env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html"]))
env.filters["num"] = num
env.filters["czdate"] = czdate

_SB_FIELDS = [
    "serial_number", "designation", "type_designation", "name", "site", "order_number", "standard_part",
    "un_v", "ue_v", "ui_v", "uimp_kv", "fn_hz", "phases", "earthing_system", "ina_a", "icc_ka", "icw_ka",
    "ipk_ka", "rdf", "ip_code", "ip_code_open", "ik_code", "location", "installation", "mounting",
    "pollution_degree", "emc_environment", "internal_form", "protection_class", "operated_by",
    "enclosure_manufacturer", "enclosure_type", "width_mm", "height_mm", "depth_mm", "weight_kg",
    "supply_cable", "notes",
]
_DEV_FIELDS = [
    "position", "designation", "feeds_from", "kind", "manufacturer", "type_code", "poles", "rated_current_a",
    "curve", "breaking_capacity_ka", "residual_ma", "rcd_type", "circuit_label", "cable", "phase",
]
_TENANT_FIELDS = [
    "name", "ico", "dic", "street", "city", "zip", "country", "email", "phone", "web",
    "signer_name", "signer_position", "issue_place",
]


def _logo_data_uri(tenant: Tenant) -> str:
    if not storage.exists(tenant.logo_key):
        return ""
    ext = tenant.logo_key.rsplit(".", 1)[-1].lower()
    mime = {"svg": "image/svg+xml", "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(ext, f"image/{ext}")
    return f"data:{mime};base64," + base64.b64encode(storage.load(tenant.logo_key)).decode()


def public_url(sb: Switchboard) -> str:
    return f"{settings.public_base_url}/d/{sb.public_token}"


def build_snapshot(sb: Switchboard, tenant: Tenant, revision_number: int | None,
                   issued_by: User | None = None, issued_at: datetime | None = None) -> dict:
    analysis = characteristics.analyze(sb)
    issued_at = issued_at or datetime.now(timezone.utc)
    devices = []
    for d in sb.devices:
        row = {f: getattr(d, f) for f in _DEV_FIELDS}
        row["kind_label"] = d.kind_label
        row["rating_text"] = d.rating_text
        devices.append(row)
    sbd = {f: getattr(sb, f) for f in _SB_FIELDS}
    sbd["standard_label"] = sb.standard_label
    sbd["manufacture_date"] = sb.manufacture_date.isoformat() if sb.manufacture_date else None
    sbd["customer"] = ({"name": sb.customer.name, "address": sb.customer.address, "ico": sb.customer.ico}
                       if sb.customer else None)
    sbd["outgoing_count"] = len(analysis.outgoing)
    sbd["main_device"] = analysis.main_device.designation if analysis.main_device else ""
    rt = dict(sb.routine_test or {})
    rt_items = rt.get("items") or {}
    rt["rows"] = [{"code": c, "title": t, **(rt_items.get(c) or {"result": "", "value": ""})}
                  for c, t in standards.ROUTINE_TEST_ITEMS]
    override = tenant.standards_override or {}
    return {
        "version": 1,
        "revision": revision_number,
        "issued_at": issued_at.isoformat(),
        "issued_by": issued_by.name if issued_by else "",
        "tenant": {**{f: getattr(tenant, f) for f in _TENANT_FIELDS}, "address_line": tenant.address_line,
                   "logo": _logo_data_uri(tenant)},
        "sb": sbd,
        "devices": devices,
        "routine_test": rt,
        "directives": [d.__dict__ for d in standards.DIRECTIVES],
        "law": standards.LAW,
        "standards": standards.standards_for(sb.standard_part, override),
        "main_standard": standards.main_standard(sb.standard_part, override),
        "warnings": analysis.warnings,
        "schematic_svg": schematic.render_svg(sb, analysis.main_device),
        "public_url": public_url(sb),
        "qr_svg": marks.qr_svg(public_url(sb)),
        "ce_svg": marks.ce_mark_svg(),
    }


def render_html(kind: str, snap: dict) -> str:
    if kind == "bundle":
        return env.get_template("bundle.html").render(s=snap, kinds=DOC_ORDER, titles=DOCUMENT_KINDS)
    if kind == "label":
        return env.get_template("label.html").render(s=snap)
    if kind not in DOC_ORDER:
        raise KeyError(kind)
    return env.get_template("page.html").render(s=snap, kind=kind, titles=DOCUMENT_KINDS)


def render_pdfs(snap: dict) -> dict[str, bytes]:
    kinds = ["bundle", *DOC_ORDER, "label"]
    return dict(zip(kinds, pdf.html_many_to_pdf([render_html(k, snap) for k in kinds])))


def issue_revision(db: Session, sb: Switchboard, user: User, note: str = "") -> Revision:
    analysis = characteristics.analyze(sb)
    if characteristics.blocking(analysis.warnings):
        raise ValueError("Dokumentaci nelze vydat: " + "; ".join(analysis.warnings))
    last = db.scalar(select(func.max(Revision.number)).where(Revision.switchboard_id == sb.id))
    number = 0 if last is None else last + 1
    snap = build_snapshot(sb, user.tenant, number, issued_by=user)
    files = render_pdfs(snap)

    rev = Revision(switchboard_id=sb.id, number=number, issued_by_id=user.id, note=note, snapshot=snap)
    db.add(rev)
    db.flush()
    base = f"t{sb.tenant_id}/sb{sb.id}/rev{number:02d}"
    safe_serial = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in sb.serial_number)
    for kind, data in files.items():
        key = storage.save(f"{base}/{safe_serial}_{kind}_rev{number:02d}.pdf", data)
        db.add(Document(revision_id=rev.id, kind=kind, storage_key=key,
                        sha256=hashlib.sha256(data).hexdigest(), size=len(data)))
    catalog.learn(db, sb.tenant_id, list(sb.devices))
    db.commit()
    return rev


def next_serial(tenant: Tenant) -> str:
    serial = f"{tenant.serial_prefix}{date.today().year}-{tenant.next_serial:04d}"
    tenant.next_serial += 1
    return serial
