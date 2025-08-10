#!/usr/bin/env zsh
# Arrête/termine les instances AWS créées par scripts/create-aws-vm.zsh
#
# Usage:
#   ./scripts/stop.zsh [--help] [--prefix PREFIX] [--region REGION] [--yes]
#
# Options:
#   --help           Affiche cette aide.
#   --prefix PREFIX  Préfixe utilisé pour identifier les VMs (défaut: awsgpu).
#   --region REGION  Région AWS (défaut: eu-west-3).
#   --yes            Ne pas demander de confirmation interactif.
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
Usage: stop.zsh [--help] [--prefix PREFIX] [--region REGION] [--yes]

Arrête/termine les instances AWS créées par create-aws-vm.zsh (tag Name commençant par PREFIX).

Options:
  --help           Affiche cette aide.
  --prefix PREFIX  Préfixe utilisé pour identifier les VMs (défaut: awsgpu).
  --region REGION  Région AWS (défaut: eu-west-3).
  --yes            Ne pas demander de confirmation interactive.
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
  local AUTO_YES=0

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
      --yes)
        AUTO_YES=1
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

  # Récupérer les informations utiles des instances correspondant au préfixe
  # sortie text : Name<TAB>InstanceId<TAB>State<TAB>PublicIp<TAB>PrivateIp
  local aws_out
  if ! aws_out="$(aws ec2 describe-instances \
      --region "$AWS_REGION" \
      --filters "Name=tag:Name,Values=${VM_NAME_PREFIX}*" "Name=instance-state-name,Values=pending,running,stopping,stopped" \
      --query 'Reservations[].Instances[].[Tags[?Key==`Name`]|[0].Value, InstanceId, State.Name, PublicIpAddress, PrivateIpAddress]' \
      --output text)"; then
    echo "Erreur: échec de la requête AWS. Vérifiez vos credentials et la région." >&2
    return 3
  fi

  if [[ -z "${aws_out:-}" ]]; then
    echo "Aucune instance trouvée pour le préfixe '${VM_NAME_PREFIX}' dans la région ${AWS_REGION}."
    return 0
  fi

  # Afficher un tableau lisible
  printf "%s\t%s\t%s\t%s\n" "NAME" "INSTANCE_ID" "STATE" "IP"
  echo "$aws_out" | while IFS=$'\t' read -r name inst_id state pub priv; do
    ip="$pub"
    if [[ -z "${ip:-}" ]]; then
      ip="$priv"
    fi
    [[ -z "${name:-}" ]] && name="-"
    [[ -z "${inst_id:-}" ]] && inst_id="-"
    [[ -z "${state:-}" ]] && state="-"
    [[ -z "${ip:-}" ]] && ip="-"
    printf "%s\t%s\t%s\t%s\n" "$name" "$inst_id" "$state" "$ip"
  done

  # Construire la liste des instance-ids à terminer
  # extraire la seconde colonne
  local ids
  ids="$(echo "$aws_out" | awk '{print $2}' | tr '\n' ' ' | sed -e 's/  */ /g' -e 's/^ *//' -e 's/ *$//')"

  if [[ -z "${ids:-}" ]]; then
    echo "Aucune instance-id valide trouvée à terminer."
    return 0
  fi

  echo ""
  echo "Instances à terminer : $ids"

  if [[ $AUTO_YES -eq 0 ]]; then
    printf "Confirmez-vous la terminaison des instances ci-dessus ? [y/N] "
    # read -r is POSIX; zsh provides read builtin
    read -r reply
    if [[ ! "$reply" =~ ^[Yy]$ ]]; then
      echo "Abandon."
      return 0
    fi
  fi

  # Terminer les instances
  echo "Envoi de la demande de terminaison..."
  if ! aws ec2 terminate-instances --instance-ids $ids --region "$AWS_REGION" >/dev/null; then
    echo "Erreur: l'appel terminate-instances a échoué." >&2
    return 4
  fi

  echo "Requête envoyée. Attente de l'état 'terminated'..."
  if ! aws ec2 wait instance-terminated --instance-ids $ids --region "$AWS_REGION"; then
    echo "Erreur: attente de la terminaison a échoué ou a été interrompue." >&2
    return 5
  fi

  echo "Instances terminées : $ids"
  return 0
}

# Si le script est exécuté directement (ou si ZSH_EVAL_CONTEXT est absent), lance main.
if [[ -z "${ZSH_EVAL_CONTEXT:-}" || "${ZSH_EVAL_CONTEXT:-}" == *file* || "${ZSH_EVAL_CONTEXT:-}" == *toplevel* ]]; then
  main "$@"
fi
