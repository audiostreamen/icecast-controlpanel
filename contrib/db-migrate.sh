#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -z "${DB_URL:-}" ]]; then
  # Try to read from /etc/default/ingest-admin
  if [[ -r /etc/default/ingest-admin ]]; then
    # shellcheck disable=SC1091
    source /etc/default/ingest-admin || true
  fi
fi

if [[ -z "${DB_URL:-}" ]]; then
  echo "DB_URL is not set. Example: mysql+pymysql://user:pass@host/ingest_admin?charset=utf8mb4" >&2
  exit 2
fi

VENV="venv/bin"
if [[ ! -x "$VENV/alembic" ]]; then
  echo "Installing Alembic in virtualenv..."
  "$VENV/pip" install -r requirements.txt >/dev/null
fi

export DB_URL
case "${1:-upgrade}" in
  revision)
    shift
    "$VENV/alembic" revision --autogenerate -m "${*:-update}"
    ;;
  upgrade)
    "$VENV/alembic" upgrade head
    ;;
  downgrade)
    "$VENV/alembic" downgrade -1
    ;;
  history)
    "$VENV/alembic" history
    ;;
  *)
    echo "Usage: $0 [revision|upgrade|downgrade|history]" >&2
    exit 2
    ;;
esac

echo "Done."

