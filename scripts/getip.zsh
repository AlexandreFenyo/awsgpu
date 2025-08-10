# Affiche l'IPv4 (publique si disponible, sinon privée) des instances AWS
# créées par scripts/create-aws-vm.zsh (tag Name commençant par VM_NAME_PREFIX).
#
# Usage:
#   ./scripts/getip.zsh [--help] [--prefix PREFIX] [--region REGION] [--public-only]
#
# Options:
#   --help         Affiche cette aide.
#   --prefix PREFIX  Préfixe utilisé pour identifier les VMs (par défaut awsgpu).
#   --region REGION  Région AWS (par défaut eu-west-3).
#   --public-only   N'affiche que les adresses IPv4 publiques.
#
# Le script source scripts/aws_vm_config.env s'il existe pour reprendre la
# configuration (KEY_NAME, AWS_REGION, VM_NAME_PREFIX, ...).
#
# Exemples:
#   chmod +x scripts/getip.zsh
#   ./scripts/getip.zsh --prefix awsgpu --region eu-west-3
#
# Dépendances: aws CLI v2 et python3 (pour parser la sortie JSON).

#!/usr/bin/env zsh
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
Usage: getip.zsh [--help] [--prefix PREFIX] [--region REGION] [--public-only]

Affiche l'IPv4 (publique si disponible, sinon privée) des instances AWS
créées par create-aws-vm.zsh (tag Name commençant par PREFIX).

Options:
  --help           Affiche cette aide.
  --prefix PREFIX  Préfixe utilisé pour identifier les VMs (défaut: awsgpu).
  --region REGION  Région AWS (défaut: eu-west-3).
  --public-only    N'affiche que les adresses IPv4 publiques.
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
  local PUBLIC_ONLY=0

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
      --public-only)
        PUBLIC_ONLY=1
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
  require_cmd python3

  # Rechercher les instances dont le tag Name commence par le préfixe
  # On reprend les états utilisés par create-aws-vm.zsh (pending,running,stopping,stopped)
  local aws_out
  if ! aws_out="$(aws ec2 describe-instances \
      --region "$AWS_REGION" \
      --filters "Name=tag:Name,Values=${VM_NAME_PREFIX}*" "Name=instance-state-name,Values=pending,running,stopping,stopped" \
      --output json)"; then
    echo "Erreur: échec de la requête AWS. Vérifiez vos credentials et la région." >&2
    return 3
  fi

  # Si aucune instance trouvée, la sortie JSON contient Reservations=[]
  if python3 - <<'PY' <<<"$aws_out"
import sys, json
data = json.load(sys.stdin)
# Vérifier s'il y a au moins une instance
for r in data.get("Reservations", []):
    if r.get("Instances"):
        sys.exit(0)
# aucune instance
sys.exit(1)
PY
  then
    :
  else
    echo "Aucune instance trouvée pour le préfixe '${VM_NAME_PREFIX}' dans la région ${AWS_REGION}."
    return 0
  fi

  # Parser et afficher: Name, InstanceId, State, IP (publique si disponible sinon privée)
  printf "%s\t%s\t%s\t%s\n" "NAME" "INSTANCE_ID" "STATE" "IP"
  python3 - <<'PY' <<<"$aws_out"
import sys, json
data = json.load(sys.stdin)
for r in data.get("Reservations", []):
    for i in r.get("Instances", []):
        inst_id = i.get("InstanceId", "")
        state = i.get("State", {}).get("Name", "")
        pub = i.get("PublicIpAddress")
        priv = i.get("PrivateIpAddress")
        name = ""
        for t in i.get("Tags", []):
            if t.get("Key") == "Name":
                name = t.get("Value", "")
                break
        # Choix de l'IP: publique si présente sinon privée, sinon vide
        ip = pub if pub else priv if priv else ""
        print("\t".join([name or "-", inst_id or "-", state or "-", ip or "-"]))
PY

  # Si --public-only, filtrer pour n'afficher que celles ayant une IP publique
  if [[ $PUBLIC_ONLY -eq 1 ]]; then
    # Réexécuter la même requête mais ne garder que les lignes avec une IP publique
    echo ""
    echo "Instances avec IP publique:"
    echo "NAME	INSTANCE_ID	STATE	PUBLIC_IP"
    python3 - <<'PY' <<<"$aws_out"
import sys, json
data = json.load(sys.stdin)
for r in data.get("Reservations", []):
    for i in r.get("Instances", []):
        pub = i.get("PublicIpAddress")
        if not pub:
            continue
        inst_id = i.get("InstanceId", "")
        state = i.get("State", {}).get("Name", "")
        name = ""
        for t in i.get("Tags", []):
            if t.get("Key") == "Name":
                name = t.get("Value", "")
                break
        print("\t".join([name or "-", inst_id or "-", state or "-", pub]))
PY
  fi

  return 0
}

# Si le script est exécuté directement, lance main.
if [[ "${ZSH_EVAL_CONTEXT:-}" == *file* || "${ZSH_EVAL_CONTEXT:-}" == *toplevel* ]]; then
  main "$@"
fi
