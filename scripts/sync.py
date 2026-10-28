"""Collect recent Deezer plays into the database.

Usage:
    python -m scripts.sync                 # fetch + store + enrich (default 120 s budget)
    python -m scripts.sync --no-enrich     # fetch + store only
    python -m scripts.sync --enrich-only   # only resume metadata/genre enrichment
    python -m scripts.sync --enrich-budget 600
    python -m scripts.sync --library       # force a refresh of favorite albums & playlists
    python -m scripts.sync --no-library    # skip favorites & playlists

Exit code 1 when the cookie is invalid or the history cannot be fetched, so that
GitHub Actions marks the run as failed and sends an email.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from core.config import get_settings, redact, setup_logging
from core.db import get_engine, init_db
from core.deezer_gw import DeezerAPIError, DeezerAuthError, DeezerGatewayClient, DeezerHistorySource
from core.excel import write_exports
from core.library import refresh_library
from core.sync import run_enrichment, run_sync

log = logging.getLogger("sync")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DatAtlaSonore sync")
    parser.add_argument("--no-enrich", action="store_true", help="skip metadata/genre enrichment")
    parser.add_argument("--enrich-only", action="store_true", help="only run enrichment")
    parser.add_argument("--enrich-budget", type=float, default=120, help="max seconds spent enriching")
    parser.add_argument("--library", action="store_true", help="force refresh of favorite albums & playlists")
    parser.add_argument("--no-library", action="store_true", help="skip favorite albums & playlists")
    parser.add_argument("--no-excel", action="store_true", help="do not rewrite the Excel copies")
    args = parser.parse_args(argv)

    setup_logging()
    settings = get_settings()
    if (os.environ.get("GITHUB_ACTIONS") and settings.database_url.startswith("sqlite")
            and os.environ.get("DEEZER_STATS_STORAGE") != "git"):
        # The runner's disk is wiped after each run: writing to SQLite there would lose everything.
        log.error("No storage configured: set DEEZER_STATS_STORAGE=git (database kept in the repo) "
                  "or a DATABASE_URL secret. Refusing to write to a throwaway SQLite file.")
        return 1
    engine = init_db(get_engine(settings.database_url))
    log.info("Database: %s", engine.url.render_as_string(hide_password=True))

    if args.enrich_only:
        run_enrichment(engine, args.enrich_budget)
        write_excel(engine, args, settings)
        return 0

    try:
        client = DeezerGatewayClient()
        result = run_sync(engine, DeezerHistorySource(client), enrich=False)
    except DeezerAuthError as exc:
        log.error("DEEZER COOKIE PROBLEM: %s", redact(exc))
        return 1
    except DeezerAPIError as exc:
        log.error("Deezer internal API error: %s (raw response saved in logs/)", redact(exc))
        return 1
    except Exception as exc:
        log.error("Sync failed: %s: %s", type(exc).__name__, redact(exc))
        return 1

    if not args.no_library:
        refresh_library(engine, client, force=args.library)
    if not args.no_enrich:
        run_enrichment(engine, args.enrich_budget)
    write_excel(engine, args, settings)

    # Deezer only exposes the most recent plays (100): "read" is that window, not a limit of the app.
    print(f"OK: read Deezer's {result.fetched} most recent plays (the window Deezer exposes); "
          f"{result.inserted} new stored, {result.fetched - result.inserted} already in the database.")
    if result.gap_warning:
        print(f"WARNING: {result.gap_warning}")
    return 0


def write_excel(engine, args, settings) -> None:
    """Keep Excel copies of the history and library next to the project (local runs only)."""
    if args.no_excel or os.environ.get("GITHUB_ACTIONS") or not settings.excel_dir:
        return
    try:
        paths = write_exports(engine, settings.excel_dir, settings.timezone)
        print("Excel:", " | ".join(str(p) for p in paths))
    except PermissionError:
        log.warning("Excel files are open in Excel: close them to let the sync update them.")
    except Exception as exc:
        log.warning("Excel export failed: %s", redact(exc))


if __name__ == "__main__":
    sys.exit(main())
