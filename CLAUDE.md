# Pravidla pro práci na projektu Štítky

- Odpovídej česky, stručně.
- Multi-tenant: každý dotaz na data firmy musí filtrovat `tenant_id` (použij `get_owned`). Nový endpoint = test izolace.
- Šablony dokumentů (`templates/docs`) pracují jen se snapshotem, nikdy s ORM objekty – vydané revize se musí dát znovu vykreslit.
- Vydané revize a jejich PDF nikdy neměň ani nemaž.
- Texty prohlášení, norem a návodu měň jen po potvrzení – mají právní váhu.
- Před commitem spusť `.venv\Scripts\python -m pytest -q`.
