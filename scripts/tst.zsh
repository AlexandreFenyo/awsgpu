#!/usr/bin/env zsh
# scripts/tst.zsh
# Script de test rapide pour le dépôt — créé par l'assistant.
# Utilisation : ./scripts/tst.zsh
set -euo pipefail

# Se déplacer à la racine du dépôt (suppose que le script se trouve dans scripts/)
cd "$(dirname -- "$0")/.." || exit 1

echo "Repository root: $(pwd)"

# Afficher la version de Python si disponible
if command -v python3 >/dev/null 2>&1; then
  echo "Python: $(python3 --version)"
fi

# Exécuter pytest s'il est installé
if command -v pytest >/dev/null 2>&1; then
  echo "Running pytest..."
  pytest -q
else
  echo "pytest not found; nothing to run."
fi
