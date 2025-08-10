#!/usr/bin/env zsh
# scripts/tst.zsh
# Quick test script for repository — created by assistant.
# Usage: ./scripts/tst.zsh
set -euo pipefail

# Move to repository root (assumes script lives in scripts/)
cd "$(dirname -- "$0")/.." || exit 1

echo "Repository root: $(pwd)"

# Show Python version if available
if command -v python3 >/dev/null 2>&1; then
  echo "Python: $(python3 --version)"
fi

# Run pytest if it's installed
if command -v pytest >/dev/null 2>&1; then
  echo "Running pytest..."
  pytest -q
else
  echo "pytest not found; nothing to run."
fi
