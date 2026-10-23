"""Dopočet a kontrola charakteristik rozhraní z osazených přístrojů.

Výpočty jsou NÁVRH pro technika – hodnoty na dokumentech jsou vždy ty, které
technik potvrdí ve formuláři. Kontroly vrací varování, ne chyby: odpovědnost
za prohlášení nese výrobce rozvaděče.
"""
from dataclasses import dataclass, field

PROTECTIVE_KINDS = {"MCB", "RCBO", "MCCB", "FUSE"}
INCOMING_KINDS = {"MCB", "MCCB", "SWITCH", "FUSE", "RCBO"}

# Jmenovitý součinitel soudobosti (RDF) dle počtu hlavních vývodů.
# 61439-1 tab. 101 (výkonové rozváděče) a 61439-3 tab. 101 (DBO) – orientační,
# výrobce může deklarovat jinou hodnotu ověřenou návrhem.
_RDF_TABLE = {
    "2": [(3, 0.9), (5, 0.8), (9, 0.7), (10**6, 0.6)],
    "3": [(3, 0.8), (5, 0.7), (9, 0.6), (10**6, 0.5)],
}


@dataclass
class Analysis:
    main_device: object | None = None
    outgoing: list = field(default_factory=list)
    suggested_ina: float | None = None
    suggested_icc: float | None = None
    suggested_rdf: float | None = None
    warnings: list[str] = field(default_factory=list)


def find_main_device(devices: list) -> object | None:
    """Hlavní přístroj = bez nadřazeného, typicky první v pořadí a s největším proudem."""
    roots = [d for d in devices if not d.feeds_from and d.kind in INCOMING_KINDS]
    if not roots:
        return None
    roots.sort(key=lambda d: (d.position, -(d.rated_current_a or 0)))
    return roots[0]


def outgoing_circuits(devices: list, main) -> list:
    """Koncové jisticí prvky (vývody) – ochranné přístroje, které nic dalšího nenapájejí."""
    feeders = {d.feeds_from for d in devices if d.feeds_from}
    return [
        d for d in devices
        if d is not main and d.kind in PROTECTIVE_KINDS and d.designation not in feeders
    ]


def suggest_rdf(part: str, n_circuits: int) -> float | None:
    if n_circuits < 2:
        return 1.0 if n_circuits == 1 else None
    for limit, value in _RDF_TABLE.get(part, _RDF_TABLE["2"]):
        if n_circuits <= limit:
            return value
    return None


def analyze(sb) -> Analysis:
    devices = list(sb.devices)
    a = Analysis()
    a.main_device = find_main_device(devices)
    a.outgoing = outgoing_circuits(devices, a.main_device)

    if a.main_device and a.main_device.rated_current_a:
        a.suggested_ina = a.main_device.rated_current_a

    capacities = [d.breaking_capacity_ka for d in devices if d.kind in PROTECTIVE_KINDS and d.breaking_capacity_ka]
    if capacities:
        a.suggested_icc = min(capacities)

    a.suggested_rdf = suggest_rdf(sb.standard_part, len(a.outgoing))
    a.warnings = check(sb, a)
    return a


def check(sb, a: Analysis) -> list[str]:
    w: list[str] = []
    devices = list(sb.devices)
    designations = [d.designation for d in devices if d.designation]

    if not devices:
        w.append("Rozvaděč nemá žádné přístroje.")
        return w
    if a.main_device is None:
        w.append("Nelze určit hlavní přístroj – zadejte přístroj bez „napájeno z“.")

    dup = sorted({x for x in designations if designations.count(x) > 1})
    if dup:
        w.append("Duplicitní označení přístrojů: " + ", ".join(dup))
    unknown = sorted({d.feeds_from for d in devices if d.feeds_from and d.feeds_from not in designations})
    if unknown:
        w.append("„Napájeno z“ odkazuje na neexistující přístroj: " + ", ".join(unknown))

    if not sb.ina_a:
        w.append("Není vyplněn jmenovitý proud sestavy InA.")
    elif a.main_device and a.main_device.rated_current_a and sb.ina_a > a.main_device.rated_current_a:
        w.append(f"InA ({sb.ina_a:g} A) je vyšší než jmenovitý proud hlavního přístroje "
                 f"({a.main_device.rated_current_a:g} A).")

    if not sb.icc_ka:
        w.append("Není vyplněn podmíněný zkratový proud Icc.")
    elif a.suggested_icc and sb.icc_ka > a.suggested_icc:
        w.append(f"Icc ({sb.icc_ka:g} kA) je vyšší než nejnižší vypínací schopnost přístrojů "
                 f"({a.suggested_icc:g} kA) – doložte kaskádu/back-up ochranu dle výrobce.")

    missing_icn = [d.designation or d.type_code for d in devices
                   if d.kind in PROTECTIVE_KINDS and not d.breaking_capacity_ka]
    if missing_icn:
        w.append("U jisticích přístrojů chybí vypínací schopnost: " + ", ".join(missing_icn))

    if sb.standard_part == "3":
        # Omezení rozsahu ČSN EN 61439-3 (DBO)
        if sb.ina_a and sb.ina_a > 250:
            w.append("DBO (61439-3): InA nesmí překročit 250 A – zvažte 61439-2.")
        big = [d.designation for d in a.outgoing if (d.rated_current_a or 0) > 125]
        if big:
            w.append("DBO (61439-3): vývody nad 125 A nejsou přípustné: " + ", ".join(big))
        if sb.ue_v and sb.ue_v > 300:
            w.append("DBO (61439-3): Ue proti zemi max. 300 V AC – zkontrolujte Ue.")
        if sb.operated_by != "laik":
            w.append("DBO je určena k obsluze laiky – zkontrolujte pole „obsluha“.")

    if not sb.ip_code:
        w.append("Není vyplněn stupeň krytí IP.")

    rt = sb.routine_test or {}
    items = rt.get("items") or {}
    if not rt.get("test_date") or not rt.get("tested_by"):
        w.append("Kusová zkouška: chybí datum nebo jméno zkoušejícího.")
    nok = [code for code, it in items.items() if (it or {}).get("result") == "NOK"]
    if nok:
        w.append("Kusová zkouška nevyhověla v bodech: " + ", ".join(nok) + " – dokumentaci nelze vydat.")
    return w


def blocking(warnings: list[str]) -> bool:
    """Varování, se kterými nelze vydat prohlášení o shodě."""
    return any("nelze vydat" in x or "žádné přístroje" in x for x in warnings)
