#!/bin/bash
# Double-click: sync Deezer every 30 minutes in the background (app closed, Mac on).
cd "$(dirname "$0")" || exit 1
.venv/bin/python -m scripts.autosync_macos install
echo
echo "Première synchro en cours… (20 s)"
sleep 20
.venv/bin/python -m scripts.autosync_macos status
echo
read -r -p "Appuie sur Entrée pour fermer…"
