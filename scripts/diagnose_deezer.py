"""Diagnostic: test the internal Deezer methods with your cookie and show raw answers.

Usage: python -m scripts.diagnose_deezer

Useful if the sync suddenly breaks (Deezer changed its internal API). The cookie
itself is never printed. Full answers are written to logs/diagnose_*.json.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

from core.config import get_settings, redact
from core.deezer_gw import DeezerAuthError, DeezerGatewayClient, extract_history_items

CANDIDATES = [
    ("user.getSongsHistory", lambda uid: {"USER_ID": uid, "nb": 100, "start": 0}),
    ("deezer.pageProfile", lambda uid: {"USER_ID": uid, "tab": "history", "nb": 100}),
    ("user.getHistory", lambda uid: {"USER_ID": uid}),
]


def main() -> int:
    settings = get_settings()
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    try:
        client = DeezerGatewayClient()
        client.login()
    except DeezerAuthError as exc:
        print("Cookie problem:", redact(exc))
        return 1
    print(f"Logged in. USER_ID={client.user_id}\n")
    for method, body in CANDIDATES:
        data = client.call(method, body(client.user_id))
        path = settings.log_dir / f"diagnose_{method}.json"
        path.write_text(redact(json.dumps(data, ensure_ascii=False, indent=1)), encoding="utf-8")
        try:
            items = extract_history_items(data)
            ts = [int(i["TS"]) for i in items if "TS" in i]
            span = ""
            if ts:
                old = datetime.fromtimestamp(min(ts), tz=timezone.utc)
                new = datetime.fromtimestamp(max(ts), tz=timezone.utc)
                span = f" from {old:%Y-%m-%d %H:%M} to {new:%Y-%m-%d %H:%M} UTC"
            print(f"[OK]   {method}: {len(items)} plays{span}")
            if items:
                print("       fields:", ", ".join(sorted(k for k in items[0] if not k.startswith("FILESIZE"))))
        except Exception as exc:
            print(f"[FAIL] {method}: {redact(exc)}")
        print(f"       raw answer: {path}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
