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

echo "Récupération de la base publiée sur GitHub…"
# Publishing without the published copy merged in would replace it and lose its plays:
# when the pull fails, the sync stays local and nothing is published.
PULLED=1
.venv/bin/python -m scripts.cloud_db pull || {
  PULLED=0
  echo "⚠️  Base GitHub indisponible : on continue avec la base locale."
}
echo "Synchro des dernières écoutes Deezer…"
if .venv/bin/python -m scripts.sync --enrich-budget 30; then
  if [ "$PULLED" = 1 ]; then
    .venv/bin/python -m scripts.cloud_db push || echo "⚠️  Publication sur GitHub impossible (réessaie plus tard)."
  else
    echo "⚠️  Publication sur GitHub sautée (la base publiée n'a pas pu être récupérée) : réessaie plus tard."
  fi
else
  echo "⚠️  Synchro échouée (l'app s'ouvre quand même)."
fi

echo
echo "Lancement de l'app…"
# The supervisor keeps the app up through code, settings and library changes (no relaunch needed).
.venv/bin/python -m scripts.dev_server --port 8501 &
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
