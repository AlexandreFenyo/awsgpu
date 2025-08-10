#!/usr/bin/env zsh
# Liste les instances AWS dont le tag Name commence par un préfixe (par défaut "awsgpu").
#
# Usage:
#   ./scripts/listinstances.zsh [--help] [--prefix PREFIX] [--region REGION]
#
# Options:
#   --help           Affiche cette aide.
#   --prefix PREFIX  Préfixe utilisé pour identifier les VMs (défaut: awsgpu).
#   --region REGION  Région AWS (défaut: eu-west-3).
#
# Le script source scripts/aws_vm_config.env s'il existe pour reprendre la
# configuration (KEY_NAME, AWS_REGION, VM_NAME_PREFIX, ...).
#
# Dépendances: aws CLI v2.
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
Usage: listinstances.zsh [--help] [--prefix PREFIX] [--region REGION]

Liste les instances AWS dont le tag Name commence par PREFIX (défaut: awsgpu).
Affiche NAME, INSTANCE_ID, STATE et IP (publique si disponible sinon privée).
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

  # Rechercher les instances dont le tag Name commence par le préfixe
  # On récupère Name, InstanceId, State.Name, PublicIpAddress, PrivateIpAddress en sortie text
  local aws_out
  if ! aws_out="$(aws ec2 describe-instances \
      --region "$AWS_REGION" \
      --filters "Name=tag:Name,Values=${VM_NAME_PREFIX}*" \
      --query 'Reservations[].Instances[].[Tags[?Key==`Name`]|[0].Value, InstanceId, State.Name, PublicIpAddress, PrivateIpAddress]' \
      --output text)"; then
    echo "Erreur: échec de la requête AWS. Vérifiez vos credentials et la région." >&2
    return 3
  fi

  # Si aucune instance trouvée, aws_out sera vide
  if [[ -z "${aws_out:-}" ]]; then
    echo "Aucune instance trouvée pour le préfixe '${VM_NAME_PREFIX}' dans la région ${AWS_REGION}."
    return 0
  fi

  # Afficher un tableau lisible
  printf "%s\t%s\t%s\t%s\n" "NAME" "INSTANCE_ID" "STATE" "IP"
  # aws_out est en sortie text : Name<TAB>InstanceId<TAB>State<TAB>PublicIp<TAB>PrivateIp
  echo "$aws_out" | while IFS=$'\t' read -r name inst_id state pub priv; do
    ip="$pub"
    if [[ -z "${ip:-}" ]]; then
      ip="$priv"
    fi
    # Normaliser les valeurs vides en "-"
    [[ -z "${name:-}" ]] && name="-"
    [[ -z "${inst_id:-}" ]] && inst_id="-"
    [[ -z "${state:-}" ]] && state="-"
    [[ -z "${ip:-}" ]] && ip="-"
    printf "%s\t%s\t%s\t%s\n" "$name" "$inst_id" "$state" "$ip"
  done

  return 0
}

# Si le script est exécuté directement (ou si ZSH_EVAL_CONTEXT est absent), lance main.
if [[ -z "${ZSH_EVAL_CONTEXT:-}" || "${ZSH_EVAL_CONTEXT:-}" == *file* || "${ZSH_EVAL_CONTEXT:-}" == *toplevel* ]]; then
  main "$@"
fi
