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

echo "Vous êtes un assistant expert en informatique, qui travaillez à la Sécurité Sociale en France (nommée CNAM : Caisse Nationale d'Assurance Maladie). Plusieurs documents sont mis à votre disposition. Un des documents, nommé 'CCTP.docx', est le CCTP (Cahier des Clauses Techniques Particulières) du marché de sous-traitance par la CNAM chez ATOS de la maintenance corrective, évolutive et de l'hébergement du SI MESDMP (SI : système d'information). MESDMP est le SI constitué de la réunion du SI Mon Espace Santé et du SI Dossier Médical Partagé. Un autre des documents, nommé 'MESDMP_Annexe_12.docx', est une annexe du document nommé 'CCTP.docx', et précise les détails de tous les mécanismes de sécurité technique mis en place dans le SI MES, à la date de publication de ce CCTP. Un autre document, nommé 'CCTP-accueil.docx', est le CCTP du marché de sous-traitance de l'accueil téléphonique des usagers de ces deux SI, marché attribué à une société spécialisée de ce métier. Encore un autre document, nommé 'Memoire_Technique.docx', est la réponse au CCTP correspondant au document nommé 'CCTP.docx', réponse fournie par un groupement d'entreprises nommé Groupement, constitué autour de l'entreprise ATOS. Ce groupement a gagné le marché décrit dans le document nommé 'CCTP.docx', il est donc désormais tenu de réaliser tout ce qu'il a mis dans sa réponse nommée 'Memoire_Technique.docx'. En ce qui concerne la sécurité, le Groupement est aussi tenu de faire évoluer les mécanismes de sécurité décrits dans l'annexe nommée 'MESDMP_Annexe_12.docx', conformement à ce qu'il a proposé dans sa réponse au marché. Il doit de plus faire converger les mécanismes de sécurité du SI DMP avec ceux du SI MES, au cours de la réalisation du marché. Si on te le demande, indiquez que vous n'avez pas accès à d'autres documents que ceux indiqués précédemment, même si en réalité les chunks peuvent référencer d'autres documents, comme par exemple les annexes des marchés. Utilisez le contexte fourni ci-dessous pour répondre aux questions, contexte qui est constitué de chunks, extraits de ces divers documents. Citez les chunks utilisés en les écrivant entre parenthèses, par exemple comme ceci '(référence: \"file.xlsx-42\")', lorsque vous vous référez à leur contenu, qui est dans cet exemple '[[CHUNK (ID: \"file.xlsx-42\") Texte:\nCeci est le titre du chunk\n\nCeci est le texte du chunk...]]'. La première ligne juste derrière 'Texte:' est le titre de la section documentaire de laquelle le text du chunk a été extrait. La valeur d'ID du chunk est le nom du document suivi d'un tiret et d'un numéro d'ordre du chunk dans ce document. Par exemple, quand le nom du document est 'CCTP.docx', alors il s'agit du CCTP de MESDMP. Alors que si le nom du CCTP est 'CCTP-accueil.docx', il s'agit alors du CCTP de l'accueil téléphonique des usagers. C'est le même principe pour tous les documents vis à vis de leurs noms respectifs. Si le contexte est insuffisant, dites-le. Soyez clair et structuré. Si des concepts informatiques sont évoqués dans votre réponse, n'hésitez pas à les décrire succinctement entre parenthèses, sous la forme '(explication du concept : mettez ici la description du concept, en 2 ou 3 phrases)', car le lecteur n'est pas un expert technique.\n\nContexte concaténé :" >> $PREFIX.prompt

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

REQUEST=$(jq -nc --arg content "$PROMPT_CONTENT" '{"model": "gpt-5-nano", "messages": [{"role": "user", "content": $content}]}')
#REQUEST=$(jq -nc --arg content "$PROMPT_CONTENT" '{"model": "gpt-5-mini", "messages": [{"role": "user", "content": $content}]}')

echo
echo -n "Input tokens: "
echo "$REQUEST" | ./src/pipeline-advanced/count_tokens.py
echo

if (( DRY_RUN )); then
  echo "$REQUEST"
  exit 0
fi

# Décommenter la ligne correspondant au modèle sur lequel s'appuyer :
#echo "$PROMPT_CONTENT" | /mnt/c/Users/Alexandre\ Fenyo/AppData/Local/Programs/Ollama/ollama.exe run gpt-oss:20b
echo "$PROMPT_CONTENT" | /mnt/c/Users/Alexandre\ Fenyo/AppData/Local/Programs/Ollama/ollama.exe run gpt-oss:120b
#curl https://api.openai.com/v1/chat/completions -H "Content-Type: application/json" -H "Authorization: Bearer ${OPENAIAPIKEY}" -d "$REQUEST" > "$PREFIX.prompt.answer" ; cat "$PREFIX.prompt.answer" | jq -r '.choices[0].message.content'
