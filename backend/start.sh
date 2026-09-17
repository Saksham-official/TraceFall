#!/bin/sh
set -eu

alembic upgrade head
python -m app.cli load-labels
python -m app.worker &

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
