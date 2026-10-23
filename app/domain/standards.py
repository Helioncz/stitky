"""Směrnice, nařízení vlády a normy uváděné v EU prohlášení o shodě.

Čísla edic norem se mění – firma si je může přepsat v Nastavení
(`Tenant.standards_override`, klíč = `code`). Výchozí hodnoty je potřeba
jednou ověřit proti aktuálnímu seznamu harmonizovaných norem (Úřední věstník EU)
a ČSN online.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Directive:
    code: str
    eu: str
    cz: str


DIRECTIVES = [
    Directive("LVD", "Směrnice Evropského parlamentu a Rady 2014/35/EU (elektrická zařízení nízkého napětí)",
              "nařízení vlády č. 118/2016 Sb."),
    Directive("EMC", "Směrnice Evropského parlamentu a Rady 2014/30/EU (elektromagnetická kompatibilita)",
              "nařízení vlády č. 117/2016 Sb."),
    Directive("RoHS", "Směrnice Evropského parlamentu a Rady 2011/65/EU ve znění (EU) 2015/863 (omezení nebezpečných látek)",
              "nařízení vlády č. 481/2012 Sb."),
]

LAW = "zákon č. 90/2016 Sb., o posuzování shody stanovených výrobků při jejich dodávání na trh"


@dataclass(frozen=True)
class Standard:
    code: str
    title: str
    directives: tuple[str, ...]
    parts: tuple[str, ...] = ("2", "3")  # pro které části 61439 se uvádí


DEFAULT_STANDARDS = [
    Standard("ČSN EN IEC 61439-1:2021", "Rozváděče nízkého napětí – Část 1: Všeobecná pravidla", ("LVD", "EMC")),
    Standard("ČSN EN IEC 61439-2:2021", "Rozváděče nízkého napětí – Část 2: Výkonové rozváděče", ("LVD", "EMC"), ("2",)),
    Standard("ČSN EN 61439-3:2012", "Rozváděče nízkého napětí – Část 3: Rozvodnice určené k provozování laiky (DBO)",
             ("LVD", "EMC"), ("3",)),
    Standard("ČSN EN IEC 63000:2019", "Technická dokumentace pro posuzování elektrických a elektronických výrobků "
                                      "s ohledem na omezení nebezpečných látek", ("RoHS",)),
]


def standards_for(part: str, override: dict | None = None) -> list[dict]:
    """Normy pro danou část 61439. `override` = {výchozí kód: nový kód} z nastavení firmy."""
    override = override or {}
    out = []
    for s in DEFAULT_STANDARDS:
        if part not in s.parts:
            continue
        out.append({"code": override.get(s.code) or s.code, "title": s.title, "directives": list(s.directives)})
    return out


def main_standard(part: str, override: dict | None = None) -> str:
    """Norma, na kterou se odkazuje výrobní štítek (čl. 6.1 d)."""
    return next(s["code"] for s in standards_for(part, override) if "61439-" + part in s["code"])


# Kusová zkouška dle ČSN EN IEC 61439-1 čl. 11
ROUTINE_TEST_ITEMS = [
    ("11.2", "Stupeň ochrany krytem (IP)"),
    ("11.3", "Vzdušné vzdálenosti a povrchové cesty"),
    ("11.4", "Ochrana před úrazem el. proudem a spojitost ochranných obvodů"),
    ("11.5", "Vestavění vestavných přístrojů"),
    ("11.6", "Vnitřní elektrické obvody a spojení (dotažení spojů)"),
    ("11.7", "Svorky pro vnější vodiče"),
    ("11.8", "Mechanická funkce"),
    ("11.9", "Dielektrické vlastnosti (izolační odpor / zkouška napětím)"),
    ("11.10", "Zapojení, provozní funkce a funkce (vč. zkoušky chráničů)"),
]
