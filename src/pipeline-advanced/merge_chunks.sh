#!/bin/zsh

# Options:
# -n: dry-run (do not call curl, print REQUEST JSON instead)
DRY_RUN=0
while getopts "n" opt; do
  case "$opt" in
    n) DRY_RUN=1 ;;
    *) ;;
  esac
done
shift $((OPTIND-1))

# After options, expect: <chunks_file> <questions>
CHUNKS_FILE="$1"
QUESTIONS="$2"

mktemp /tmp/question-XXXXXXXXXX | read PREFIX
rm -f "$PREFIX.prompt"

echo "Vous êtes un assistant expert en informatique, qui travaille à la Sécurité Sociale en France (nommée CNAM : Caisse Nationale d'Assurance Maladie). Utilisez uniquement le contexte fourni ci-dessous pour répondre aux questions, contexte qui est constitué de chunks, extraits de divers documents. Citez les chunks utilisés en les écrivant entre parenthèses, par exemple comme ceci '(référence: \"file.xlsx-42\")', lorsque vous vous référez à leur contenu, qui est dans cet exemple '[[CHUNK (ID: \"file.xlsx-42\") Texte: ceci est le texte du chunk...]]'. Si le contexte est insuffisant, dites-le et proposez des questions de clarification. Soyez clair, structuré et concis. Une fois les réponses fournies, proposez une nouvelle réponse à partir de ce que vous connaissez, sans reprendre les informations déjà indiquées dans les chunks.\n\nContexte concaténé :" >> $PREFIX.prompt

cat "$CHUNKS_FILE" | while read -r CHUNK
do
    CHUNK_ID=$(echo -E $CHUNK | jq -r .chunk_id)
    CHUNK_TEXT=$(echo -E $CHUNK | jq -r .text)
    cat >> $PREFIX.prompt <<EOF
[[CHUNK (ID: "$CHUNK_ID")
Texte:
$CHUNK_TEXT
]]

EOF
done

echo "Voici les questions :\n$QUESTIONS" >> "$PREFIX.prompt"

PROMPT_CONTENT=`cat "$PREFIX.prompt"`

REQUEST=$(jq -nc --arg content "$PROMPT_CONTENT" '{"model": "gpt-5-mini", "messages": [{"role": "user", "content": $content}]}')

echo
echo -n "Input tokens: "
echo "$REQUEST" | ./src/pipeline-advanced/count_tokens.py
echo

if (( DRY_RUN )); then
  echo "$REQUEST"
  exit 0
fi

curl https://api.openai.com/v1/chat/completions -H "Content-Type: application/json" -H "Authorization: Bearer ${OPENAIAPIKEY}" -d "$REQUEST" > "$PREFIX.prompt.answer"
cat "$PREFIX.prompt.answer" | jq -r '.choices[0].message.content'
