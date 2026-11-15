#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PYTHON="${GAMST_MCP_PYTHON:-$ROOT/.venv-mcp/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  [[ "${GAMST_MCP_AUTO_SETUP:-1}" == "1" ]] || { echo "MCP environment missing: run setup_environment or set GAMST_MCP_PYTHON" >&2; exit 2; }
  BASE_PYTHON="${GAMST_MCP_BASE_PYTHON:-python3}"
  "$BASE_PYTHON" -m venv "$ROOT/.venv-mcp"
  "$ROOT/.venv-mcp/bin/python" -m pip install -r "$ROOT/requirements-mcp.txt"
  PYTHON="$ROOT/.venv-mcp/bin/python"
fi
exec "$PYTHON" -m gamst_bench.mcp_server "$@"
