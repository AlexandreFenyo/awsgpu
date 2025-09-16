#!/usr/bin/env zsh
# Interroge un serveur Ollama via HTTP avec un modèle et une taille de contexte
# Utilisation: scripts/oquery.sh <ip_ollama> <modele> <taille_contexte> <fichier>
# Exemple:     scripts/oquery.sh 127.0.0.1 llama3 4096 prompt.txt

set -e
set -u
set -o pipefail
IFS=$'\n\t'

usage() {
  cat <<'EOF' >&2
Usage: scripts/oquery.sh <ip> <modele> <num_ctx> <fichier>
Description: Interroge un serveur Ollama à l'IP donnée avec le modèle et la taille de contexte spécifiés,
en envoyant le texte contenu dans le fichier au point d'API /api/generate (stream=false).

Paramètres:
  <ip>         Adresse IP du serveur Ollama (ex: 127.0.0.1). Vous pouvez aussi fournir http://ip:11434.
  <modele>     Nom du modèle LLM (ex: llama3, mistral, ...).
  <num_ctx>    Taille de contexte (entier strictement positif).
  <fichier>    Chemin du fichier dont le contenu sera envoyé comme prompt.

Options:
  -h, --help   Affiche cette aide.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -ne 4 ]]; then
  echo "Erreur: nombre d'arguments invalide." >&2
  usage
  exit 1
fi

IP="$1"
MODEL="$2"
NUM_CTX="$3"
FILE="$4"

# Vérifications basiques
if ! command -v curl >/dev/null 2>&1; then
  echo "Erreur: 'curl' est requis mais introuvable dans le PATH." >&2
  exit 2
fi

if [[ ! -r "$FILE" ]]; then
  echo "Erreur: fichier '$FILE' introuvable ou illisible." >&2
  exit 2
fi

# NUM_CTX doit être un entier > 0
if [[ ! "$NUM_CTX" == <-> ]]; then
  echo "Erreur: num_ctx doit être un entier positif." >&2
  exit 2
fi
if (( NUM_CTX <= 0 )); then
  echo "Erreur: num_ctx doit être > 0." >&2
  exit 2
fi

# Construction de l'URL de base
if [[ "$IP" == http://* || "$IP" == https://* ]]; then
  BASE_URL="${IP}"
else
  BASE_URL="http://${IP}:11434"
fi
ENDPOINT="${BASE_URL%/}/api/generate"

# Fonction utilitaire pour échapper en JSON une chaîne lue sur stdin
json_escape() {
  if command -v jq >/dev/null 2>&1; then
    jq -Rs .
  elif command -v python3 >/dev/null 2>&1; then
    python3 - <<'PY'
import sys, json
data = sys.stdin.read()
print(json.dumps(data))
PY
  else
    echo "Erreur: 'jq' ou 'python3' est requis pour l'échappement JSON." >&2
    exit 2
  fi
}

# Préparer les champs JSON
MODEL_JSON=$(printf '%s' "$MODEL" | json_escape)
PROMPT_JSON=$(json_escape < "$FILE")

# Corps JSON de la requête
DATA=$(printf '{"model":%s,"prompt":%s,"stream":false,"options":{"num_ctx":%d}}' \
  "$MODEL_JSON" "$PROMPT_JSON" "$NUM_CTX")

# Appel HTTP
set +e
HTTP_RESPONSE=$(curl -sS --connect-timeout 5 --max-time 600 --fail-with-body \
  -H 'Content-Type: application/json' \
  -d "$DATA" \
  "$ENDPOINT" 2>&1)
STATUS=$?
set -e

if [[ $STATUS -ne 0 ]]; then
  echo "Erreur lors de l'appel à Ollama:" >&2
  echo "$HTTP_RESPONSE" >&2
  echo "" >&2
  echo "Endpoint: $ENDPOINT" >&2
  exit $STATUS
fi

# Affichage de la réponse (contenu du champ 'response' si possible)
if command -v jq >/dev/null 2>&1; then
  printf '%s' "$HTTP_RESPONSE" | jq -r '.response // empty'
elif command -v python3 >/dev/null 2>&1; then
  printf '%s' "$HTTP_RESPONSE" | python3 - <<'PY'
import sys, json
try:
    obj = json.load(sys.stdin)
    out = obj.get('response', '')
    sys.stdout.write(out)
except Exception:
    # Si parsing JSON échoue, renvoyer la réponse brute
    sys.stdout.write(sys.stdin.read())
PY
else
  # Sans jq ni python3, afficher le JSON brut
  printf '%s\n' "$HTTP_RESPONSE"
fi
