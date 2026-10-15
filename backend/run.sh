#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

export MODEL_DIR="${MODEL_DIR:-$(cd .. && pwd)/ChildGait-Video}"
export CHILDGAIT_ROOT="${CHILDGAIT_ROOT:-$MODEL_DIR}"
export ASSESS_MODE="${ASSESS_MODE:-}"
export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-8000}"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install -U pip
  pip install -r requirements.txt
else
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

echo "ChildGait API  MODEL_DIR=$MODEL_DIR  ASSESS_MODE=${ASSESS_MODE:-auto}  http://$HOST:$PORT"
exec uvicorn server:app --host "$HOST" --port "$PORT"
