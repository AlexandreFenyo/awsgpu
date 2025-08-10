#!/usr/bin/env zsh
# Démarre l'instance AWS dont le tag Name commence par un préfixe (par défaut "awsgpu")
# Comportement :
#  - Vérifie qu'il existe exactement UNE instance dont le tag Name commence par le préfixe.
#  - Si ce n'est pas le cas, affiche une erreur et liste les instances trouvées.
#  - Si une seule instance est trouvée, lance aws ec2 start-instances sur son instance-id
#    et attend qu'elle passe à l'état "running".
#
# Usage:
#   ./scripts/start.zsh [--help] [--prefix PREFIX] [--region REGION]
#
# Options:
#   --help           Affiche cette aide.
#   --prefix PREFIX  Préfixe utilisé pour identifier la VM (défaut: awsgpu).
#   --region REGION  Région AWS (défaut: eu-west-3).
#
# Le script source scripts/aws_vm_config.env s'il existe pour reprendre la
# configuration (KEY_NAME, AWS_REGION, VM_NAME_PREFIX, ...).
#
# Dépendances: aws CLI v2.
#
# Commandes recommandées pour tester :
#   chmod +x scripts/start.zsh
#   ./scripts/start.zsh --help

set -euo pipefail

# Charger la config si elle existe (même fichier utilisé par create-aws-vm.zsh)
CONFIG_FILE="$(dirname "$0")/aws_vm_config.env"
if [[ -f "$CONFIG_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$CONFIG_FILE"
fi

# Valeurs par défaut (si non définies dans le fichier de config)
: "${AWS_REGION:=eu-west-3}"
: "${VM_NAME_PREFIX:=awsgpu}"

print_help() {
  cat <<'EOF'
Usage: start.zsh [--help] [--prefix PREFIX] [--region REGION]

Démarre l'instance AWS dont le tag Name commence par PREFIX (défaut: awsgpu).
Le script vérifie qu'il n'y a qu'une seule instance correspondant au préfixe avant de la démarrer.
EOF
}

# Vérifie la présence d'une commande
require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Erreur: la commande '$1' est requise mais introuvable." >&2
    exit 2
  fi
}

main() {
  # Parse arguments simples
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --help)
        print_help
        return 0
        ;;
      --prefix)
        shift
        if [[ -z "${1:-}" ]]; then
          echo "Erreur: --prefix nécessite un argument" >&2
          return 2
        fi
        VM_NAME_PREFIX="$1"
        ;;
      --region)
        shift
        if [[ -z "${1:-}" ]]; then
          echo "Erreur: --region nécessite un argument" >&2
          return 2
        fi
        AWS_REGION="$1"
        ;;
      *)
        echo "Option inconnue: $1" >&2
        print_help
        return 2
        ;;
    esac
    shift
  done

  require_cmd aws

  # Récupérer les instances correspondant au préfixe (tous états)
  # On récupère Name, InstanceId, State.Name en sortie text
  local aws_out
  if ! aws_out="$(aws ec2 describe-instances \
      --region "$AWS_REGION" \
      --filters "Name=tag:Name,Values=${VM_NAME_PREFIX}*" \
      --query 'Reservations[].Instances[].[Tags[?Key==`Name`]|[0].Value, InstanceId, State.Name]' \
      --output text)"; then
    echo "Erreur: échec de la requête AWS. Vérifiez vos credentials et la région." >&2
    return 3
  fi

  # Supprimer lignes vides et compter les lignes non-vides
  local non_empty
  non_empty="$(echo "$aws_out" | sed '/^\s*$/d')"

  if [[ -z "${non_empty:-}" ]]; then
    echo "Aucune instance trouvée pour le préfixe '${VM_NAME_PREFIX}' dans la région ${AWS_REGION}."
    return 1
  fi

  local count
  count="$(echo "$non_empty" | wc -l | tr -d '[:space:]')"

  if [[ "$count" -ne 1 ]]; then
    echo "Erreur: attendu exactement 1 instance dont le nom commence par '${VM_NAME_PREFIX}', trouvé : $count" >&2
    echo ""
    printf "%s\t%s\t%s\n" "NAME" "INSTANCE_ID" "STATE"
    echo "$non_empty"
    return 2
  fi

  # Extraire l'instance-id de la seule ligne
  local instance_id
  instance_id="$(echo "$non_empty" | awk '{print $2}')"
  if [[ -z "${instance_id:-}" ]]; then
    echo "Erreur: impossible d'extraire l'instance-id." >&2
    return 4
  fi

  echo "Instance unique trouvée : $instance_id. Démarrage en cours..."
  if ! aws ec2 start-instances --instance-ids "$instance_id" --region "$AWS_REGION" >/dev/null; then
    echo "Erreur: l'appel start-instances a échoué." >&2
    return 5
  fi

  echo "Requête envoyée. Attente de l'état 'running'..."
  if ! aws ec2 wait instance-running --instance-ids "$instance_id" --region "$AWS_REGION"; then
    echo "Erreur: attente de l'état 'running' a échoué ou a été interrompue." >&2
    return 6
  fi

  # Récupérer l'IP publique si disponible
  local public_ip
  public_ip="$(aws ec2 describe-instances --instance-ids "$instance_id" --region "$AWS_REGION" --query 'Reservations[0].Instances[0].PublicIpAddress' --output text || true)"
  echo "Instance démarrée : $instance_id"
  if [[ -n "${public_ip:-}" && "${public_ip}" != "None" ]]; then
    echo "IP publique : $public_ip"
  fi

  return 0
}

# Si le script est exécuté directement (ou si ZSH_EVAL_CONTEXT est absent), lance main.
if [[ -z "${ZSH_EVAL_CONTEXT:-}" || "${ZSH_EVAL_CONTEXT:-}" == *file* || "${ZSH_EVAL_CONTEXT:-}" == *toplevel* ]]; then
  main "$@"
fi
