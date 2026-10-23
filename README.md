# Štítky – povinná dokumentace rozvaděčů NN

SaaS pro elektrofirmy: z fotky rozvaděče (AI rozpozná přístroje) nebo ručního zadání vygeneruje
kompletní dokumentaci dle ČSN EN IEC 61439 a archivuje ji po revizích.

**Výstupy pro každý rozvaděč** (PDF, zvlášť i jako kompletní balík):
EU prohlášení o shodě · Charakteristiky rozhraní · Jednopólové schéma zapojení ·
Protokol o kusové zkoušce (čl. 11) · Návod k použití a montáži · Výrobní štítek 105×74 mm s QR a CE.

## Postup práce
1. **Nový rozvaděč** → přidělí se výrobní číslo (prefix + rok + pořadí).
2. **Fotky** → *Rozpoznat přístroje (AI)* → kontrola návrhu → *Převzít do přístrojů*.
3. **Přístroje** – doladit označení, „napájeno z“ (strom schématu), popisy vývodů a kabely.
4. **Údaje** – *Převzít návrh* (InA, Icc, RDF z přístrojů), krytí, skříň, rozměry.
5. **Kusová zkouška** – výsledky, izolační odpor.
6. **Kontrola a vydání** – varování (limity DBO, Icc vs. Icn…), náhledy, *Vydat revizi*.
   Vydaná revize je zamčená (snapshot + PDF + SHA-256). Změna = nová revize.
   Potvrzené přístroje se uloží do katalogu firmy – příště je AI/našeptávač doplní ověřené.

Zákazník se přes QR na štítku dostane na `/d/<token>` – vidí jen vydané revize.

## Lokálně
```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m playwright install chromium
copy .env.example .env      # doplnit SECRET_KEY a GEMINI_API_KEY
.venv\Scripts\uvicorn app.main:app --reload
```
Otevřít http://localhost:8000 → *Založit účet* (první firma). Testy: `.venv\Scripts\python -m pytest -q`.
Ukázková PDF bez databáze: `.venv\Scripts\python scripts\sample_docs.py output\ukazka`.

## Architektura
| Část | Kde |
|---|---|
| FastAPI + Jinja2, session cookie | `app/main.py`, `app/routers/` |
| Datový model (multi-tenant, `tenant_id` všude) | `app/models.py`, izolace `app/security.py:get_owned` |
| Normy, směrnice, kusová zkouška | `app/domain/standards.py` |
| Dopočty a kontroly (InA, Icc, RDF, limity DBO) | `app/domain/characteristics.py` |
| Snapshot → HTML → PDF (Playwright/Chromium) | `app/services/documents.py`, `templates/docs/` |
| Schéma SVG ze stromu `feeds_from` | `app/services/schematic.py` |
| AI (Gemini, připraven Claude) | `app/services/ai/` |
| Návrh AI → přístroje (označení, napájení, katalog) | `app/services/proposal.py`, `catalog.py` |

DB: lokálně SQLite, na serveru `DATABASE_URL` na Postgres (Supabase). Soubory: `DATA_DIR/files`
(Docker volume – zálohovat!).

## Nasazení (Hetzner, vedle NapojSiSám)
```bash
git clone https://github.com/Helioncz/stitky.git /opt/stitky && cd /opt/stitky
cp .env.example .env   # SECRET_KEY, GEMINI_API_KEY, PUBLIC_BASE_URL=https://dokumentace.helion.cz, DATABASE_URL
docker compose up -d --build
# Caddy: přidat deploy/Caddyfile.snippet, cron: deploy/autodeploy.sh
```

## Před ostrým provozem (TODO)
- Ověřit edice norem v Nastavení proti aktuálnímu seznamu harmonizovaných norem.
- Právní kontrola textu prohlášení a návodu (odpovědnost nese výrobce rozvaděče).
- Migrace DB (Alembic) místo `create_all`, zálohy volume a DB.
- Obnova zapomenutého hesla e-mailem (SMTP), omezení pokusů o přihlášení.
- Schéma: více listů u velkých rozvaděčů, vícepólové kreslení, svorkovnice.
