"""Import older plays from Deezer's personal-data export (.xlsx).

Usage:
    python -m scripts.import_deezer_export "chemin/vers/deezer-data.xlsx"
    python -m scripts.import_deezer_export fichier.xlsx --dry-run      # preview only
    python -m scripts.import_deezer_export fichier.xlsx --tz Europe/Zurich

--tz: timezone of the dates in the file when they carry none (default: UTC).
Safe to run several times: plays already in the database are skipped.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy.orm import Session

from core.config import get_settings, setup_logging
from core.db import get_engine, init_db
from core.deezer_export import find_history_sheet, import_rows, parse_rows


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("path", type=Path)
    p.add_argument("--tz", default="UTC")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    setup_logging()
    if not args.path.exists():
        print(f"File not found: {args.path}")
        return 1
    try:
        sheet, mapping, df = find_history_sheet(args.path)
    except ValueError as exc:
        print(exc)
        return 1
    print(f"Sheet '{sheet}': {len(df)} rows. Columns used: {mapping}")
    rows = parse_rows(df, mapping, args.tz)
    if rows:
        print(f"{len(rows)} plays from {min(r.played_at for r in rows):%Y-%m-%d} to {max(r.played_at for r in rows):%Y-%m-%d}")
    engine = init_db(get_engine(get_settings().database_url))
    with Session(engine) as session:
        report = import_rows(session, rows, dry_run=args.dry_run,
                             progress=lambda i, n: print(f"  {i}/{n} rows…", flush=True))
        if args.dry_run:
            session.rollback()
        else:
            session.commit()
    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Inserted: {report.inserted} | already there: "
          f"{report.duplicates} | not found on Deezer: {report.unresolved}")
    for ex in report.unresolved_examples:
        print("   not found:", ex)
    return 0


if __name__ == "__main__":
    sys.exit(main())
