from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import init_db
from app.services.csv_import_service import (
    IMPORT_ORDER,
    ImportDatabaseError,
    ImportValidationError,
    import_csv,
)


def main() -> int:
    init_db()
    for filename in IMPORT_ORDER:
        path = ROOT / "dataset" / filename
        try:
            report = import_csv(path)
        except (ImportDatabaseError, ImportValidationError) as exc:
            print(f"Import stopped at {filename}: {exc}", file=sys.stderr)
            return 1
        print(report.message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
