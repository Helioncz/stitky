"""Datový model.

Multi-tenant: každá elektrofirma je `Tenant`. Všechny její záznamy nesou
`tenant_id` (přímo nebo přes rozvaděč) a aplikace je vždy filtruje podle
přihlášeného uživatele – viz `app.security.get_owned`.

Vydaná revize (`Revision`) je neměnná: obsahuje zmrazený snapshot všech údajů
a PDF s SHA-256. Další úprava rozvaděče znamená novou revizi, staré zůstávají
v archivu (LVD/EMC: uchovávat 10 let od uvedení na trh).
"""
import secrets
from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _token() -> str:
    return secrets.token_urlsafe(16)


class Tenant(Base):
    """Elektrofirma = výrobce rozvaděče uváděný na dokumentech."""
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    ico: Mapped[str] = mapped_column(String(20), default="")
    dic: Mapped[str] = mapped_column(String(20), default="")
    street: Mapped[str] = mapped_column(String(200), default="")
    city: Mapped[str] = mapped_column(String(100), default="")
    zip: Mapped[str] = mapped_column(String(10), default="")
    country: Mapped[str] = mapped_column(String(60), default="Česká republika")
    email: Mapped[str] = mapped_column(String(200), default="")
    phone: Mapped[str] = mapped_column(String(50), default="")
    web: Mapped[str] = mapped_column(String(200), default="")
    logo_key: Mapped[str] = mapped_column(String(300), default="")
    signer_name: Mapped[str] = mapped_column(String(200), default="")
    signer_position: Mapped[str] = mapped_column(String(200), default="jednatel")
    issue_place: Mapped[str] = mapped_column(String(100), default="")
    serial_prefix: Mapped[str] = mapped_column(String(20), default="R")
    next_serial: Mapped[int] = mapped_column(Integer, default=1)
    # Přepis výchozích norem (čísla edic) – viz app.domain.standards
    standards_override: Mapped[dict] = mapped_column(JSON, default=dict)
    # Arch etiket pro tisk štítku – {"preset", rozměry, offset_x/y}, viz app.domain.label_sheets
    label_sheet: Mapped[dict | None] = mapped_column(JSON, default=dict)
    # Další volná pozice na rozpracovaném archu {"row", "col"}
    label_next: Mapped[dict | None] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    users: Mapped[list["User"]] = relationship(back_populates="tenant")

    @property
    def address_line(self) -> str:
        parts = [self.street, " ".join(p for p in (self.zip, self.city) if p)]
        return ", ".join(p for p in parts if p)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(200), unique=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(20), default="technik")  # owner | admin | technik
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    tenant: Mapped[Tenant] = relationship(back_populates="users")

    @property
    def is_admin(self) -> bool:
        return self.role in ("owner", "admin")


class Customer(Base):
    """Odběratel rozvaděče (zákazník elektrofirmy)."""
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    ico: Mapped[str] = mapped_column(String(20), default="")
    address: Mapped[str] = mapped_column(String(300), default="")
    email: Mapped[str] = mapped_column(String(200), default="")
    phone: Mapped[str] = mapped_column(String(50), default="")


class Switchboard(Base):
    """Rozvaděč (sestava NN dle ČSN EN IEC 61439)."""
    __tablename__ = "switchboards"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"))
    public_token: Mapped[str] = mapped_column(String(40), unique=True, default=_token)

    serial_number: Mapped[str] = mapped_column(String(50))           # výrobní číslo
    designation: Mapped[str] = mapped_column(String(50), default="RH")  # označení (RH, RE, R1…)
    type_designation: Mapped[str] = mapped_column(String(100), default="")  # typové označení
    name: Mapped[str] = mapped_column(String(200), default="")       # popis („Hlavní rozvaděč RD“)
    site: Mapped[str] = mapped_column(String(300), default="")       # místo instalace / akce
    order_number: Mapped[str] = mapped_column(String(50), default="")  # číslo zakázky
    standard_part: Mapped[str] = mapped_column(String(10), default="3")  # "2" = PSC, "3" = DBO
    manufacture_date: Mapped[date | None] = mapped_column(Date, default=date.today)

    # ── Charakteristiky rozhraní (ČSN EN IEC 61439-1 čl. 5) ──
    un_v: Mapped[float | None] = mapped_column(Float, default=400)       # jmenovité napětí Un
    ue_v: Mapped[float | None] = mapped_column(Float, default=230)       # jmenovité pracovní napětí obvodu Ue
    ui_v: Mapped[float | None] = mapped_column(Float, default=500)       # jmenovité izolační napětí Ui
    uimp_kv: Mapped[float | None] = mapped_column(Float, default=4)      # jmenovité impulzní výdržné napětí
    fn_hz: Mapped[float | None] = mapped_column(Float, default=50)
    phases: Mapped[str] = mapped_column(String(20), default="3+N+PE")
    earthing_system: Mapped[str] = mapped_column(String(20), default="TN-C-S")
    ina_a: Mapped[float | None] = mapped_column(Float)                   # jmenovitý proud sestavy InA
    icc_ka: Mapped[float | None] = mapped_column(Float)                  # podmíněný zkratový proud Icc
    icw_ka: Mapped[float | None] = mapped_column(Float)                  # krátkodobý výdržný proud Icw (PSC)
    ipk_ka: Mapped[float | None] = mapped_column(Float)                  # vrcholový výdržný proud Ipk (PSC)
    rdf: Mapped[float | None] = mapped_column(Float)                     # součinitel soudobosti
    ip_code: Mapped[str] = mapped_column(String(10), default="IP40")
    ip_code_open: Mapped[str] = mapped_column(String(10), default="IP20")  # s otevřenými dveřmi
    ik_code: Mapped[str] = mapped_column(String(10), default="IK07")
    location: Mapped[str] = mapped_column(String(20), default="vnitřní")   # vnitřní | venkovní
    installation: Mapped[str] = mapped_column(String(20), default="pevná")  # pevná | přemístitelná
    mounting: Mapped[str] = mapped_column(String(40), default="nástěnná")   # nástěnná | zapuštěná | stojanová
    pollution_degree: Mapped[int | None] = mapped_column(Integer, default=2)
    emc_environment: Mapped[str] = mapped_column(String(5), default="A/B")
    internal_form: Mapped[str] = mapped_column(String(10), default="1")     # forma vnitřního oddělení
    protection_class: Mapped[str] = mapped_column(String(10), default="I")  # I | II
    operated_by: Mapped[str] = mapped_column(String(40), default="laik")    # laik | poučená osoba | znalá osoba
    enclosure_manufacturer: Mapped[str] = mapped_column(String(100), default="")
    enclosure_type: Mapped[str] = mapped_column(String(100), default="")
    width_mm: Mapped[int | None] = mapped_column(Integer)
    height_mm: Mapped[int | None] = mapped_column(Integer)
    depth_mm: Mapped[int | None] = mapped_column(Integer)
    weight_kg: Mapped[float | None] = mapped_column(Float)
    supply_cable: Mapped[str] = mapped_column(String(100), default="")
    notes: Mapped[str] = mapped_column(Text, default="")

    # Kusová zkouška (čl. 11) – {"items": {kód: {"result": "OK", "value": ""}}, "tested_by", "test_date", "instrument", "insulation_mohm"}
    routine_test: Mapped[dict] = mapped_column(JSON, default=dict)
    # Poslední návrh AI z fotek: {"model", "at", "devices": [...], "notes", "enclosure"} – technik ho převezme do přístrojů
    ai_proposal: Mapped[dict] = mapped_column(JSON, default=dict)

    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    customer: Mapped[Customer | None] = relationship()
    devices: Mapped[list["Device"]] = relationship(
        back_populates="switchboard", cascade="all, delete-orphan", order_by="Device.position"
    )
    photos: Mapped[list["Photo"]] = relationship(back_populates="switchboard", cascade="all, delete-orphan")
    revisions: Mapped[list["Revision"]] = relationship(
        back_populates="switchboard", cascade="all, delete-orphan", order_by="Revision.number"
    )

    __table_args__ = (UniqueConstraint("tenant_id", "serial_number", name="uq_switchboard_serial"),)

    @property
    def standard_label(self) -> str:
        return {"2": "výkonový rozvaděč (PSC)", "3": "rozvodnice pro laiky (DBO)"}.get(self.standard_part, "")

    @property
    def latest_revision(self) -> "Revision | None":
        return self.revisions[-1] if self.revisions else None

    @property
    def latest_locked(self) -> "Revision | None":
        """Poslední zamčená revize – jen ta platí navenek (zákazník, QR)."""
        return next((r for r in reversed(self.revisions) if r.locked_at), None)

    @property
    def open_revision(self) -> "Revision | None":
        """Vygenerovaná, ale ještě nezamčená revize (lze ji přegenerovat)."""
        r = self.latest_revision
        return r if r and not r.locked_at else None


DEVICE_KINDS = {
    "MCB": "jistič",
    "RCD": "proudový chránič",
    "RCBO": "chránič s jističem",
    "MCCB": "kompaktní jistič",
    "SWITCH": "vypínač / odpínač",
    "FUSE": "pojistkový odpínač",
    "SPD": "přepěťová ochrana",
    "CONTACTOR": "stykač",
    "RELAY": "relé / modul",
    "METER": "elektroměr / měřidlo",
    "TERMINAL": "svorkovnice",
    "OTHER": "jiné",
}


class Device(Base):
    """Přístroj osazený v rozvaděči."""
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    switchboard_id: Mapped[int] = mapped_column(ForeignKey("switchboards.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    designation: Mapped[str] = mapped_column(String(20), default="")   # -Q1, -FA1, -F3
    feeds_from: Mapped[str] = mapped_column(String(20), default="")    # označení nadřazeného přístroje
    kind: Mapped[str] = mapped_column(String(20), default="MCB")
    manufacturer: Mapped[str] = mapped_column(String(100), default="")
    type_code: Mapped[str] = mapped_column(String(100), default="")
    poles: Mapped[str] = mapped_column(String(10), default="1")         # 1, 1+N, 2, 3, 3+N, 4
    rated_current_a: Mapped[float | None] = mapped_column(Float)
    curve: Mapped[str] = mapped_column(String(5), default="")          # B, C, D, gG…
    breaking_capacity_ka: Mapped[float | None] = mapped_column(Float)   # Icn / Icu
    residual_ma: Mapped[float | None] = mapped_column(Float)            # IΔn
    rcd_type: Mapped[str] = mapped_column(String(10), default="")      # AC, A, F, B
    circuit_label: Mapped[str] = mapped_column(String(200), default="")  # „Zásuvky kuchyň“
    cable: Mapped[str] = mapped_column(String(100), default="")        # CYKY-J 3x2,5
    phase: Mapped[str] = mapped_column(String(10), default="")         # L1 | L2 | L3 | 3F
    source: Mapped[str] = mapped_column(String(10), default="manual")  # manual | ai | catalog
    ai_confidence: Mapped[float | None] = mapped_column(Float)
    catalog_id: Mapped[int | None] = mapped_column(ForeignKey("catalog_devices.id", ondelete="SET NULL"))

    switchboard: Mapped[Switchboard] = relationship(back_populates="devices")

    @property
    def kind_label(self) -> str:
        return DEVICE_KINDS.get(self.kind, self.kind)

    @property
    def rating_text(self) -> str:
        parts = []
        if self.curve and self.rated_current_a:
            parts.append(f"{self.curve}{_num(self.rated_current_a)}")
        elif self.rated_current_a:
            parts.append(f"{_num(self.rated_current_a)} A")
        if self.residual_ma:
            parts.append(f"{_num(self.residual_ma)} mA" + (f" typ {self.rcd_type}" if self.rcd_type else ""))
        if self.poles:
            parts.append(f"{self.poles}P")
        if self.breaking_capacity_ka:
            parts.append(f"{_num(self.breaking_capacity_ka)} kA")
        return ", ".join(parts)


class CatalogDevice(Base):
    """Katalog ověřených přístrojů. tenant_id NULL = sdílený pro všechny firmy."""
    __tablename__ = "catalog_devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    manufacturer: Mapped[str] = mapped_column(String(100))
    type_code: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(20), default="MCB")
    poles: Mapped[str] = mapped_column(String(10), default="1")
    rated_current_a: Mapped[float | None] = mapped_column(Float)
    curve: Mapped[str] = mapped_column(String(5), default="")
    breaking_capacity_ka: Mapped[float | None] = mapped_column(Float)
    residual_ma: Mapped[float | None] = mapped_column(Float)
    rcd_type: Mapped[str] = mapped_column(String(10), default="")
    datasheet_url: Mapped[str] = mapped_column(String(500), default="")
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    times_used: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (UniqueConstraint("tenant_id", "manufacturer", "type_code", name="uq_catalog_device"),)


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    switchboard_id: Mapped[int] = mapped_column(ForeignKey("switchboards.id", ondelete="CASCADE"), index=True)
    storage_key: Mapped[str] = mapped_column(String(300))
    mime_type: Mapped[str] = mapped_column(String(50), default="image/jpeg")
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    switchboard: Mapped[Switchboard] = relationship(back_populates="photos")


class Revision(Base):
    """Revize dokumentace rozvaděče.

    Vygenerovaná revize je otevřená (lze ji přegenerovat pod stejným číslem). Zamknutím
    (`locked_at`) se stane neměnnou a platnou navenek – zákazník, QR, katalog.
    """
    __tablename__ = "revisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    switchboard_id: Mapped[int] = mapped_column(ForeignKey("switchboards.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)  # vygenerováno
    issued_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    note: Mapped[str] = mapped_column(Text, default="")
    snapshot: Mapped[dict] = mapped_column(JSON)

    switchboard: Mapped[Switchboard] = relationship(back_populates="revisions")
    issued_by: Mapped[User | None] = relationship(foreign_keys=[issued_by_id])
    locked_by: Mapped[User | None] = relationship(foreign_keys=[locked_by_id])
    documents: Mapped[list["Document"]] = relationship(back_populates="revision", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("switchboard_id", "number", name="uq_revision_number"),)


DOCUMENT_KINDS = {
    "bundle": "Kompletní dokumentace",
    "eu_doc": "EU prohlášení o shodě",
    "interface": "Charakteristiky rozhraní",
    "schematic": "Schéma zapojení",
    "manual": "Návod k použití a montáži",
    "routine_test": "Protokol o kusové zkoušce",
    "label": "Výrobní štítek",
}


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    revision_id: Mapped[int] = mapped_column(ForeignKey("revisions.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    storage_key: Mapped[str] = mapped_column(String(300))
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(Integer)

    revision: Mapped[Revision] = relationship(back_populates="documents")

    @property
    def kind_label(self) -> str:
        return DOCUMENT_KINDS.get(self.kind, self.kind)


def _num(v: float) -> str:
    return f"{v:g}".replace(".", ",")
