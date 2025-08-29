#!/usr/bin/env zsh
# Script non interactif pour créer une VM EC2 GPU chez AWS (aws-cli v2)
# Le script lit les variables depuis scripts/aws_vm_config.env (si présent).
# Par défaut :
#   - région : eu-west-3
#   - AMI : dernier "Deep Learning AMI ... PyTorch 2.7" sous Ubuntu disponible
#   - instance type : g4dn.xlarge
# La paire de clés (KEY_NAME) doit être définie dans le fichier de config ou en variable d'environnement.
#
# Le script crée un security group autorisant tout le trafic (IPv4 + IPv6),
# lance une instance et affiche l'instance-id et l'IP publique.
#
# Attention : autoriser tout le trafic est dangereux en production. Utilisez avec précaution.

set -euo pipefail

# Chemin vers le fichier de configuration (modifiable)
CONFIG_FILE="$(dirname "$0")/aws_vm_config.env"
if [[ -f "$CONFIG_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$CONFIG_FILE"
fi

# Valeurs par défaut
: "${AWS_REGION:=eu-west-3}"
: "${INSTANCE_TYPE:=g4dn.xlarge}"
: "${AMI_NAME_PATTERN:=Deep Learning AMI*PyTorch 2.7*Ubuntu*}"
: "${SG_NAME_PREFIX:=awsgpu-sg}"
: "${VM_NAME_PREFIX:=awsgpu}"

# Mode dry-run (ne crée rien chez AWS)
DRY_RUN=0

# Parse simple args (seul --dry-run|-n est géré)
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run|-n)
      DRY_RUN=1
      shift
      ;;
    --help|-h)
      echo "Usage: $0 [--dry-run|-n]"
      echo ""
      echo "Options:"
      echo "  --dry-run, -n    Ne crée aucun objet chez AWS; affiche ce qui serait fait."
      exit 0
      ;;
    *)
      # autres arguments ignorés (le script est non interactif)
      break
      ;;
  esac
done

# KEY_NAME doit être fourni (sauf en dry-run)
if [[ $DRY_RUN -eq 0 && -z "${KEY_NAME:-}" ]]; then
  echo "Erreur: KEY_NAME n'est pas défini. Mettez-le dans $CONFIG_FILE ou exportez KEY_NAME." >&2
  exit 1
fi

timestamp="$(date +%Y%m%d-%H%M)"
VM_NAME="${VM_NAME_PREFIX}-${timestamp}"
SG_NAME="${SG_NAME_PREFIX}-${timestamp}"

CREATED_SG_ID=""
CREATED_INSTANCE_ID=""
CREATED_SUBNET_ID=""

cleanup_on_error() {
  local rc=$?
  if [[ $rc -ne 0 ]]; then
    echo "Une erreur est survenue (code $rc). Nettoyage..."
    if [[ -n "$CREATED_INSTANCE_ID" && "$CREATED_INSTANCE_ID" != "None" ]]; then
      echo "Suppression de l'instance $CREATED_INSTANCE_ID..."
      aws ec2 terminate-instances --instance-ids "$CREATED_INSTANCE_ID" --region "$AWS_REGION" >/dev/null 2>&1 || true
      aws ec2 wait instance-terminated --instance-ids "$CREATED_INSTANCE_ID" --region "$AWS_REGION" >/dev/null 2>&1 || true
    fi
    if [[ -n "$CREATED_SUBNET_ID" ]]; then
      echo "Suppression du subnet $CREATED_SUBNET_ID..."
      aws ec2 delete-subnet --subnet-id "$CREATED_SUBNET_ID" --region "$AWS_REGION" >/dev/null 2>&1 || true
    fi
    if [[ -n "$CREATED_SG_ID" ]]; then
      echo "Suppression du security group $CREATED_SG_ID..."
      aws ec2 delete-security-group --group-id "$CREATED_SG_ID" --region "$AWS_REGION" >/dev/null 2>&1 || true
    fi
    echo "Nettoyage terminé."
  fi
  return $rc
}
trap cleanup_on_error EXIT

# Trouver le VPC par défaut dans la région
VPC_ID="$(aws ec2 describe-vpcs --region "$AWS_REGION" --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)"
if [[ -z "$VPC_ID" || "$VPC_ID" == "None" ]]; then
  echo "Impossible de trouver le VPC par défaut dans la région $AWS_REGION" >&2
  exit 1
fi

echo "VPC par défaut : $VPC_ID"

# Vérifier s'il existe déjà une instance dont le nom commence par le préfixe
# On considère toutes les instances comme bloquantes, sauf celles en état "terminated".
echo "Recherche d'instances existantes avec le préfixe $VM_NAME_PREFIX (tous états sauf 'terminated')..."
if ! EXISTING_INSTANCES="$(aws ec2 describe-instances --region "$AWS_REGION" --filters "Name=tag:Name,Values=${VM_NAME_PREFIX}*" --query 'Reservations[].Instances[?State.Name!=`terminated`].InstanceId' --output text)"; then
  echo "Erreur: échec de la requête AWS lors de la vérification des instances existantes." >&2
  exit 1
fi
if [[ -n "$EXISTING_INSTANCES" && "$EXISTING_INSTANCES" != "None" ]]; then
  echo "Une instance existante (état ≠ terminated) avec un nom commençant par $VM_NAME_PREFIX a été trouvée :"
  echo "$EXISTING_INSTANCES"
  echo "Aucune action effectuée."
  exit 0
fi

# Créer (ou réutiliser) le security group
echo "Vérification du security group $SG_NAME..."
SG_ID="$(aws ec2 describe-security-groups --region "$AWS_REGION" --filters Name=group-name,Values="$SG_NAME" Name=vpc-id,Values="$VPC_ID" --query 'SecurityGroups[0].GroupId' --output text || true)"
if [[ -n "$SG_ID" && "$SG_ID" != "None" ]]; then
  echo "Security group existant trouvé : $SG_ID"
  CREATED_SG_ID=""
else
  if [[ $DRY_RUN -eq 0 ]]; then
    echo "Création du security group $SG_NAME..."
    SG_ID="$(aws ec2 create-security-group --group-name "$SG_NAME" --description "All traffic allowed (created by create-aws-vm.zsh)" --vpc-id "$VPC_ID" --region "$AWS_REGION" --query 'GroupId' --output text)"
    CREATED_SG_ID="$SG_ID"
    echo "Security group créé : $SG_ID"
  else
    echo "[DRY-RUN] would create security group: $SG_NAME in VPC $VPC_ID"
    # Ne pas renseigner CREATED_SG_ID pour éviter tout cleanup
    CREATED_SG_ID=""
    SG_ID="DRY-RUN-SG"
  fi
fi

# Autoriser tout le trafic entrant et sortant (IPv4 + IPv6)
echo "Autorisation du trafic (ingress + egress) pour $SG_ID..."
if [[ $DRY_RUN -eq 0 ]]; then
  aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --ip-permissions 'IpProtocol=-1,IpRanges=[{CidrIp=0.0.0.0/0}],Ipv6Ranges=[{CidrIpv6=::/0}]' --region "$AWS_REGION" || true
  aws ec2 authorize-security-group-egress --group-id "$SG_ID" --ip-permissions 'IpProtocol=-1,IpRanges=[{CidrIp=0.0.0.0/0}],Ipv6Ranges=[{CidrIpv6=::/0}]' --region "$AWS_REGION" || true
else
  echo "[DRY-RUN] would: aws ec2 authorize-security-group-ingress --group-id $SG_ID --ip-permissions 'IpProtocol=-1,IpRanges=[{CidrIp=0.0.0.0/0}],Ipv6Ranges=[{CidrIpv6=::/0}]' --region $AWS_REGION"
  echo "[DRY-RUN] would: aws ec2 authorize-security-group-egress --group-id $SG_ID --ip-permissions 'IpProtocol=-1,IpRanges=[{CidrIp=0.0.0.0/0}],Ipv6Ranges=[{CidrIpv6=::/0}]' --region $AWS_REGION"
fi

# Trouver l'AMI si AMI_ID non fourni
if [[ -z "${AMI_ID:-}" ]]; then
    echo "Recherche de l'AMI correspondant au pattern : $AMI_NAME_PATTERN"
  AMI_ID="$(aws ec2 describe-images --region "$AWS_REGION" --owners amazon --filters Name=name,Values="$AMI_NAME_PATTERN" Name=state,Values=available --query 'Images | sort_by(@,&CreationDate)[-1].ImageId' --output text || true)"
  if [[ -z "$AMI_ID" || "$AMI_ID" == "None" ]]; then
    # fallback : sans propriétaire
    AMI_ID="$(aws ec2 describe-images --region "$AWS_REGION" --filters Name=name,Values="$AMI_NAME_PATTERN" Name=state,Values=available --query 'Images | sort_by(@,&CreationDate)[-1].ImageId' --output text || true)"
  fi
  if [[ -z "$AMI_ID" || "$AMI_ID" == "None" ]]; then
    echo "Erreur: impossible de trouver une AMI correspondant à : $AMI_NAME_PATTERN" >&2
    exit 1
  fi
fi

echo "AMI choisie : $AMI_ID"

# Lancer l'instance (choix ou création d'un subnet si nécessaire)
echo "Détermination d'un subnet dans le VPC $VPC_ID..."
SUBNET_ID="$(aws ec2 describe-subnets --region "$AWS_REGION" --filters Name=vpc-id,Values="$VPC_ID" --query 'Subnets[0].SubnetId' --output text || true)"
if [[ -z "$SUBNET_ID" || "$SUBNET_ID" == "None" ]]; then
  echo "Aucun subnet trouvé dans le VPC $VPC_ID. Création d'un subnet..."
  VPC_CIDR="$(aws ec2 describe-vpcs --vpc-ids "$VPC_ID" --region "$AWS_REGION" --query 'Vpcs[0].CidrBlock' --output text)"
  # Construire un CIDR /24 à partir du CIDR du VPC en prenant les trois premiers octets
  SUBNET_CIDR="$(echo "$VPC_CIDR" | awk -F'/' '{print $1}' | awk -F. '{print $1"."$2"."$3".0/24"}')"
  AZ="$(aws ec2 describe-availability-zones --region "$AWS_REGION" --query 'AvailabilityZones[0].ZoneName' --output text)"
  if [[ $DRY_RUN -eq 0 ]]; then
    SUBNET_ID="$(aws ec2 create-subnet --vpc-id "$VPC_ID" --cidr-block "$SUBNET_CIDR" --availability-zone "$AZ" --region "$AWS_REGION" --query 'Subnet.SubnetId' --output text)"
    CREATED_SUBNET_ID="$SUBNET_ID"
    echo "Subnet créé : $SUBNET_ID ($SUBNET_CIDR) dans AZ $AZ"
    aws ec2 modify-subnet-attribute --subnet-id "$SUBNET_ID" --map-public-ip-on-launch --region "$AWS_REGION"
  else
    echo "[DRY-RUN] would create subnet in VPC $VPC_ID with CIDR $SUBNET_CIDR in AZ $AZ"
    CREATED_SUBNET_ID=""
    SUBNET_ID="DRY-RUN-SUBNET"
  fi
fi

echo "Lancement de l'instance ($INSTANCE_TYPE) avec la key ${KEY_NAME:-<no-key>} dans le subnet $SUBNET_ID..."
if [[ $DRY_RUN -eq 0 ]]; then
  INSTANCE_ID="$(aws ec2 run-instances --region "$AWS_REGION" --image-id "$AMI_ID" --count 1 --instance-type "$INSTANCE_TYPE" --key-name "$KEY_NAME" --security-group-ids "$SG_ID" --subnet-id "$SUBNET_ID" --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$VM_NAME}]" --query 'Instances[0].InstanceId' --output text)"
  if [[ -z "$INSTANCE_ID" || "$INSTANCE_ID" == "None" ]]; then
    echo "Erreur : lancement de l'instance a échoué" >&2
    exit 1
  fi
  CREATED_INSTANCE_ID="$INSTANCE_ID"
  echo "Instance lancée : $INSTANCE_ID"
else
  echo "[DRY-RUN] would run: aws ec2 run-instances --region $AWS_REGION --image-id $AMI_ID --count 1 --instance-type $INSTANCE_TYPE --key-name ${KEY_NAME:-<not-set>} --security-group-ids $SG_ID --subnet-id $SUBNET_ID --tag-specifications ResourceType=instance,Tags=[{Key=Name,Value=$VM_NAME}]"
  CREATED_INSTANCE_ID=""
fi

if [[ $DRY_RUN -eq 0 ]]; then
  # Attendre que l'instance soit running
  echo "Attente du passage en état 'running'..."
  aws ec2 wait instance-running --instance-ids "$INSTANCE_ID" --region "$AWS_REGION"

  # Récupérer IP publique
  PUBLIC_IP="$(aws ec2 describe-instances --region "$AWS_REGION" --instance-ids "$INSTANCE_ID" --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)"
  echo "Instance $INSTANCE_ID est running."
  echo "Nom : $VM_NAME"
  echo "Security Group : $SG_ID"
  echo "IP publique : $PUBLIC_IP"
else
  echo "[DRY-RUN] instance would be created with:"
  echo "  AMI: $AMI_ID"
  echo "  INSTANCE_TYPE: $INSTANCE_TYPE"
  echo "  KEY_NAME: ${KEY_NAME:-<not set>}"
  echo "  SECURITY_GROUP: $SG_ID"
  echo "  SUBNET: $SUBNET_ID"
  echo "  NAME: $VM_NAME"
fi

# Succès, enlever le trap cleanup
trap - EXIT
exit 0
