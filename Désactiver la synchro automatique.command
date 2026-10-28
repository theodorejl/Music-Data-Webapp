#!/bin/bash
# Double-click: stop the background Deezer sync.
cd "$(dirname "$0")" || exit 1
.venv/bin/python -m scripts.autosync_macos uninstall
read -r -p "Appuie sur Entrée pour fermer…"
