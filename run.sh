#!/usr/bin/env sh
set -eu
python -m uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
