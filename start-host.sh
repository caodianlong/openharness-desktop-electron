#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST_DIR="${HOST_DIR:-$ROOT_DIR/apps/host-python}"
PYTHON_BIN="${PYTHON_BIN:-$HOST_DIR/.venv/bin/python3}"
HOST_MODULE="${HOST_MODULE:-host_mvp.ws_server:app}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8789}"
LOG_LEVEL="${LOG_LEVEL:-info}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python executable not found: $PYTHON_BIN" >&2
  exit 1
fi

cd "$HOST_DIR"
export PYTHONPATH="${PYTHONPATH:-src}"
export PORT
export OPENHARNESS_REPO_ROOT="${OPENHARNESS_REPO_ROOT:-$ROOT_DIR}"
export OPENHARNESS_VENDOR_SRC="${OPENHARNESS_VENDOR_SRC:-$ROOT_DIR/vendor/OpenHarness/src}"
export OPENHARNESS_CONFIG_DIR="${OPENHARNESS_CONFIG_DIR:-$ROOT_DIR/.tmp/openharness-config}"
export OPENHARNESS_DATA_DIR="${OPENHARNESS_DATA_DIR:-$ROOT_DIR/.tmp/openharness-data}"
mkdir -p "$OPENHARNESS_CONFIG_DIR" "$OPENHARNESS_DATA_DIR"

exec "$PYTHON_BIN" -m uvicorn "$HOST_MODULE" \
  --host "$HOST" \
  --port "$PORT" \
  --log-level "$LOG_LEVEL"
