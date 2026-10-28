#!/bin/bash
# Double-click to stop the Deezer Stats app.
cd "$(dirname "$0")" || exit 1

pkill -f "scripts.dev_server" 2>/dev/null  # the supervisor first, so it does not restart the app
if pkill -f "streamlit run app/Home.py"; then
  echo "App arrêtée."
else
  echo "L'app n'était pas lancée."
fi
sleep 2
osascript -e 'tell application "Terminal" to close (every window whose name contains "Arrêter l")' >/dev/null 2>&1 &
