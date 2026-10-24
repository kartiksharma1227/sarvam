#!/usr/bin/env bash
# One-time setup: Python env for the backend, Node packages for the renderer, and .env.
set -e
cd "$(dirname "$0")"
if command -v uv >/dev/null; then
  uv venv backend/.venv --python 3.12 && uv pip install --python backend/.venv/bin/python -r backend/requirements.txt
else
  python3.12 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements.txt
fi
(cd renderer && npm install)
[ -f .env ] || cp .env.example .env
echo "Done. Fill in SARVAM_API_KEY and OPENAI_API_KEY in .env, then see README.md (Run)."
