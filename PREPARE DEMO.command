#!/usr/bin/env bash
# Double-click once before presenting (takes ~5 minutes). Makes the live demo instant and free.
cd "$(dirname "$0")/backend" && .venv/bin/python scripts/prewarm.py
echo; read -n 1 -s -r -p "Press any key to close."
