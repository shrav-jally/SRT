#!/usr/bin/env bash
set -euo pipefail

###############################################################################
# Ensure Ruff is installed (first try pipx, fall back to pip --user).
###############################################################################
if ! command -v ruff >/dev/null 2>&1; then
  echo "⇢ Ruff not found on PATH – installing…"
  if command -v pipx >/dev/null 2>&1; then
    # install into an isolated environment if pipx is present
    pipx install --quiet ruff
  else
    # otherwise install into the current (or user-level) Python environment
    pip install --quiet --upgrade --user ruff
  fi
fi

###############################################################################
# 1 – Python formatting (calls Ruff + Black, etc.)
###############################################################################
sh scripts/format.sh

###############################################################################
# 2 – ESLint autofix inside the Next.js app
###############################################################################
(cd ui && npm run fix-lint)

###############################################################################
# 3 – Restage any files changed by the fixers so the commit includes them
###############################################################################
git add -u
