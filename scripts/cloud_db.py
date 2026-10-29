"""Share the SQLite database through the GitHub repository (branch `data`).

Usage:
    python -m scripts.cloud_db pull   # fetch the published database, keep local-only rows
    python -m scripts.cloud_db push   # publish the local database (one commit; a copy published
                                      # meanwhile by another machine is merged in first)
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy.engine import make_url

from core.cloud_db import publish, pull
from core.config import ROOT, get_settings, redact


def _db_path() -> Path:
    url = make_url(get_settings().database_url)
    if url.get_backend_name() != "sqlite" or not url.database:
        raise SystemExit("cloud_db works with a SQLite DATABASE_URL only.")
    return Path(url.database)


def main() -> int:
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        if action == "pull":
            print(pull(_db_path(), ROOT))
        elif action == "push":
            print(publish(_db_path(), ROOT))
        else:
            print(__doc__)
            return 2
    except Exception as exc:
        print(f"cloud_db {action} failed: {redact(exc)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
