#!/usr/bin/env bash
# setup.sh — one-shot get-go setup for Virtual Biotech Scientist.
#
# Installs the Python package + dev deps, installs `uv` (for the ToolUniverse
# MCP server via `uvx`), and prints how to finish wiring ToolUniverse into Claude
# Code and how to enable Claude Science. Safe to re-run.
#
# NOTE: this repo is currently docs + scaffolding — no application code has landed
# yet. This installs the dependency set so you can start building. Runnable demos
# (arena, CSO spine) arrive with the code.
#
# Usage:
#   bash scripts/setup.sh            # core install (deps + tooling)
#   bash scripts/setup.sh --tools    # also pip-install ToolUniverse into the venv
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-python3}"
echo "==> Python: $($PY --version)"

# 1. venv
if [ ! -d .venv ]; then
  echo "==> creating .venv"
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
. .venv/bin/activate
python -m pip -q install --upgrade pip

# 2. package + dev extras (metadata-only wheel today; installs the dep set)
echo "==> installing virtual-biotech-scientist (.[dev])"
pip -q install -e '.[dev]'

# 3. uv / uvx — used to launch the ToolUniverse MCP server (uvx tooluniverse)
if ! command -v uvx >/dev/null 2>&1; then
  echo "==> installing uv (provides uvx)"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
echo "==> uv: $(command -v uvx || echo 'NOT on PATH — add ~/.local/bin')"

# 4. optional: install ToolUniverse itself into the venv (the `tu` CLI + SDK).
#    The MCP server does NOT need this — uvx fetches it on demand — but the CLI does.
if [ "${1:-}" = "--tools" ]; then
  echo "==> installing ToolUniverse into the venv (.[tools]) — this is large"
  pip install -e '.[tools]'
fi

cat <<'EOF'

==> Core setup complete.

Verify the environment (no keys needed):
  . .venv/bin/activate
  python -c "import scanpy, anndata, numpy, pandas; print('deps OK')"

  # Runnable demos (arena, CSO spine) and their tests arrive with the code —
  # this repo is docs + scaffolding today.

Wire ToolUniverse into Claude Code (the evidence layer):
  claude plugin marketplace add mims-harvard/ToolUniverse
  claude plugin install tooluniverse@tooluniverse
  # or use the checked-in .mcp.json (uvx tooluniverse) directly.
  # Keep context small with compact mode: tooluniverse-smcp --compact-mode

Go --live (optional): cp .env.example .env  &&  fill ANTHROPIC_API_KEY

Enable Claude Science (desktop app): see docs/SETUP.md.
EOF
