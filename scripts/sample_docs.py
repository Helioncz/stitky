"""Vykreslí ukázkovou dokumentaci (bez zápisu do ostré DB) do složky z argumentu.

    python scripts/sample_docs.py output/ukazka
"""
import os
import sys
import tempfile
from pathlib import Path

out_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "output/ukazka")
tmp = tempfile.mkdtemp(prefix="stitky-sample-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(tmp, 's.db').as_posix()}"
os.environ["DATA_DIR"] = tmp
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.conftest import SessionLocal, make_switchboard, make_tenant  # noqa: E402

from app.services import documents  # noqa: E402

db = SessionLocal()
tenant, user = make_tenant(db)
sb = make_switchboard(db, tenant)
snap = documents.build_snapshot(sb, tenant, 0, issued_by=user)
out_dir.mkdir(parents=True, exist_ok=True)
for kind, data in documents.render_pdfs(snap).items():
    (out_dir / f"{kind}.pdf").write_bytes(data)
print("Hotovo:", out_dir.resolve())
