#!/usr/bin/env bash
# Football Intelligence OS — one-command start. Backend :8077, website :5188. Opens the browser automatically.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
URL="http://localhost:5188/"

up() { curl -s -m 2 -o /dev/null "$1"; }

cd "$ROOT/backend"
[ -d .venv ] || { echo "Installing backend (first time only)…"; python3 -m venv .venv && .venv/bin/pip install -q -r requirements-dev.txt; }
[ -f .env ] || cp .env.example .env
if up http://localhost:8077/health; then
  echo "✓ Backend already running"
else
  echo "Starting backend…"
  .venv/bin/uvicorn app.main:app --port 8077 > "$ROOT/backend.log" 2>&1 &
fi

cd "$ROOT/frontend"
[ -d node_modules ] || { echo "Installing website (first time only)…"; npm install; }
if up http://localhost:5188; then
  echo "✓ Website already running"
else
  echo "Starting website…"
  npx vite > "$ROOT/frontend.log" 2>&1 &
fi

echo -n "Waiting for servers"
for i in $(seq 1 60); do
  if up http://localhost:8077/health && up http://localhost:5188; then break; fi
  echo -n "."; sleep 1
done
echo
if up http://localhost:8077/health && up http://localhost:5188; then
  echo "✅ READY → $URL"
  open "$URL" 2>/dev/null || true
  echo "Keep this window open. Close it (or press Ctrl+C) to stop."
  wait
else
  echo "❌ Something did not start. See backend.log and frontend.log in $ROOT"
fi
