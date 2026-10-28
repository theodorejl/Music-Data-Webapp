#!/bin/bash
# Double-click to sync the latest Deezer plays, then open the app in the browser.
cd "$(dirname "$0")" || exit 1
URL="http://localhost:8501"

if [ ! -x .venv/bin/python ]; then
  echo "Environnement .venv introuvable : suis l'étape 1 du README."
  read -r -p "Appuie sur Entrée pour fermer…"
  exit 1
fi

# Already running? Just open the browser.
if curl -s "$URL/_stcore/health" >/dev/null 2>&1; then
  echo "L'app tourne déjà : ouverture du navigateur."
  open "$URL"
  exit 0
fi

echo "Synchro des dernières écoutes Deezer…"
.venv/bin/python -m scripts.sync --enrich-budget 30 || echo "⚠️  Synchro échouée (l'app s'ouvre quand même)."

echo
echo "Lancement de l'app…"
.venv/bin/streamlit run app/Home.py --server.port 8501 --server.headless true &
APP_PID=$!
trap 'kill $APP_PID 2>/dev/null' EXIT

# Wait until the app answers (max 60 s), then open the browser ourselves:
# Streamlit's own auto-open does not work reliably from a double-clicked script.
for _ in $(seq 1 60); do
  if curl -s "$URL/_stcore/health" >/dev/null 2>&1; then
    open "$URL"
    echo
    echo "✅ App ouverte sur $URL"
    echo "   Pour l'arrêter : ferme cette fenêtre ou double-clique sur « Arrêter l'app »."
    break
  fi
  if ! kill -0 $APP_PID 2>/dev/null; then
    echo "❌ L'app n'a pas pu démarrer (voir le message ci-dessus)."
    read -r -p "Appuie sur Entrée pour fermer…"
    exit 1
  fi
  sleep 1
done

wait $APP_PID
