# Ce fichier ajoute un nouveau script ZSH dans le dossier scripts/.
# Modifications proposées :
# 1) Création de scripts/getip.zsh (script zsh autonome).
# 2) Le fichier contient une aide, un exemple d'option et des instructions pour l'exécuter.
#
# Commandes recommandées pour tester :
#   chmod +x scripts/getip.zsh
#   ./scripts/getip.zsh --help
#
# NOTE: Ce fichier est autonome — il n'édite aucun fichier existant.

#!/usr/bin/env zsh
set -euo pipefail

print_help() {
  cat <<'EOF'
Usage: getip.zsh [--help] [--example ARG]

Description:
  Exemple de script ZSH ajouté dans scripts/.

Options:
  --help        Affiche cette aide.
  --example ARG Montre comment traiter un argument.
EOF
}

main() {
  if [[ "${1:-}" == "--help" ]]; then
    print_help
    return 0
  fi

  if [[ "${1:-}" == "--example" ]]; then
    if [[ -z "${2:-}" ]]; then
      echo "Erreur: --example nécessite un argument" >&2
      return 2
    fi
    echo "Argument example: $2"
    return 0
  fi

  echo "Bonjour depuis scripts/getip.zsh"
}

# Si le script est exécuté directement, lance main.
# En zsh, ZSH_EVAL_CONTEXT contient des informations sur le contexte d'évaluation.
if [[ "${ZSH_EVAL_CONTEXT:-}" == *file* || "${ZSH_EVAL_CONTEXT:-}" == *toplevel* ]]; then
  main "$@"
fi
