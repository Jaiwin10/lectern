#!/usr/bin/env bash
# One-command start: installs what is missing, builds the UI, runs on http://localhost:8420
set -euo pipefail
cd "$(dirname "$0")"

[ -f .env ] || { cp .env.example .env; echo "Created .env. Add an API key to it, then run ./start.sh again."; exit 1; }

if [ ! -x backend/.venv/bin/python ]; then
  echo "Setting up Python environment…"
  python3 -m venv backend/.venv
  backend/.venv/bin/pip install -q -r backend/requirements.txt
fi

if [ ! -d frontend/dist ] || [ -n "$(find frontend/src -newer frontend/dist -print -quit)" ]; then
  echo "Building the interface…"
  (cd frontend && { [ -d node_modules ] || npm install --silent; } && npm run build --silent)
fi

echo "Lectern is running at http://localhost:8420"
cd backend && exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8420}"
