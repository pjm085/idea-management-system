#!/usr/bin/env sh
set -eu
if [ ! -x ".venv/bin/python" ]; then
  echo "Virtual environment not found. Create it using: python3 -m venv .venv" >&2
  exit 1
fi
exec .venv/bin/python app.py
