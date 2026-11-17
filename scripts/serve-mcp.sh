#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
# Run outside the repository cwd so the local mcp/ config directory cannot
# shadow the third-party Python mcp package. Add the repository after
# site-packages so imports resolve to the installed MCP library first.
cd /tmp
exec "$ROOT/.venv-mcp/bin/python" -c 'import runpy, sys; sys.path.append(sys.argv[1]); sys.argv = ["gamst-mcp", *sys.argv[2:]]; runpy.run_module("gamst_bench.mcp_server", run_name="__main__")' "$ROOT" "$@"
