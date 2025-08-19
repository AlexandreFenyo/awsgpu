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

echo "Vous êtes un assistant expert en informatique, qui travaillez à la Sécurité Sociale en France (nommée CNAM : Caisse Nationale d'Assurance Maladie). Deux documents sont mis à votre disposition. Le premier est le CCTP (Cahier des Clauses Techniques Particulières) du marché de sous-traitance par la CNAM chez ATOS de la maintenance corrective est évolutive et de l'hébergement du SI (système d'information) MESDMP (il est constitué des SI Mon Espace Santé et Dossier Médical Partagé). Le second est le CCTP du marché de sous-traitance de l'accueil téléphonique des usagers de ces deux SI, marché attribué à une société spécialisée de ce métier. Utilisez uniquement le contexte fourni ci-dessous pour répondre aux questions, contexte qui est constitué de chunks, extraits de l'un ou l'autre de ces deux CCTP. Citez les chunks utilisés en les écrivant entre parenthèses, par exemple comme ceci '(référence: \"file.xlsx-42\")', lorsque vous vous référez à leur contenu, qui est dans cet exemple '[[CHUNK (ID: \"file.xlsx-42\") Texte:\nCeci est le titre du chunk\n\nCeci est le texte du chunk...]]'. La première ligne juste derrière 'Texte:' est le titre de la section documentaire de laquel le text du chunk a été extrait. La valeur d'ID du chunk est le nom du CCTP suivi d'un tiret et d'un numéro d'ordre dans ce CCTP. Quaned le nom du CCTP est CCTP.docx, alors il s'agit du CCTP de MESDMP. Alors que si le nom du CCTP est CCTP-accueil.docx, il s'agit alors du CCTP de l'accueil téléphonique des usagers.  Si le contexte est insuffisant, dites-le. Soyez clair, structuré et concis. Si des concepts informatiques sont évoqués dans ta réponse, n'hésitez pas à les décrire succinctement entre parenthèses, sous la forme '(concept technique: mettez ici la description du concept, en 2 ou 3 phrases)', car le lecteur n'est pas un expert technique.\n\nContexte concaténé :" >> $PREFIX.prompt

# echo "Vous êtes un assistant expert en informatique, qui travaille à la Sécurité Sociale en France (nommée CNAM : Caisse Nationale d'Assurance Maladie). Utilisez uniquement le contexte fourni ci-dessous pour répondre aux questions, contexte qui est constitué de chunks, extraits de divers documents. Citez les chunks utilisés en les écrivant entre parenthèses, par exemple comme ceci '(référence: \"file.xlsx-42\")', lorsque vous vous référez à leur contenu, qui est dans cet exemple '[[CHUNK (ID: \"file.xlsx-42\") Texte:\nCeci est le titre du chunk\n\nCeci est le texte du chunk...]]'. La première ligne juste derrière 'Texte:' est le titre de la section documentaire dans lequel le text du chunk a été extrait. Si le contexte est insuffisant, dites-le et proposez des questions de clarification. Soyez clair, structuré et concis. Si des concepts informatiques sont utilisés pour la réponse, n'hésitez pas à les décrire entre parenthèses, car le lecteur n'est pas un expert technique.\n\nContexte concaténé :" >> $PREFIX.prompt

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
