#!/bin/zsh

mktemp /tmp/question-XXXXXXXXXX | read PREFIX
rm -f $PREFIX
rm -f $PREFIX.prompt

echo "Vous êtes un assistant expert en informatique, qui travaille à la Sécurité Sociale en France (nommée CNAM : Caisse Nationale d'Assurance Maladie). Utilisez uniquement le contexte fourni ci-dessous pour répondre aux questions, contexte qui est constitué de chunks, extraits de divers documents. Citez les chunks (en écrivant par exemple 'référence file.xlsx-42'), lorsque vous vous référez à leur contenu, qui est dans cet exemple [[CHUNK (ID: "file.xlsx-42") Texte: ceci est le texte du chunk...]]. Si le contexte est insuffisant, dites-le et proposez des questions de clarification. Soyez clair, structuré et concis. Une fois les réponses fournies, proposez une nouvelle réponse à partir de ce que vous connaissez, sans reprendre les informations déjà indiquées dans les chunks.\n\nContexte concaténé :" >> $PREFIX.prompt

cat $1 | while read -r CHUNK
do
    echo -E $CHUNK | jq -r .chunk_id | read -r CHUNK_ID
    echo -E $CHUNK | sed 's/\\/\\\\/g' | read -r CHUNK
    echo -E $CHUNK | jq -r .text | read -r CHUNK_TEXT
    echo -E $CHUNK_TEXT | sed 's/\\/\n/g' | read -r CHUNK_TEXT
    echo -E $CHUNK_TEXT | sed 's/* /- /g' | read -r CHUNK_TEXT

    cat >> $PREFIX.prompt <<EOF
[[CHUNK (ID: "$CHUNK_ID")
Texte:
$CHUNK_TEXT
]]

EOF
done

echo "Voici les questions :\n$2" >> $PREFIX.prompt

PROMPT_CONTENT=`cat $PREFIX.prompt`

REQUEST=$(jq -nc --arg content "$PROMPT_CONTENT" '{"model": "gpt-5-nano", "messages": [{"role": "user", "content": $content}]}')

curl https://api.openai.com/v1/chat/completions -H "Content-Type: application/json" -H "Authorization: Bearer ${OPENAIAPIKEY}" -d "$REQUEST" > $PREFIX.prompt.answer
cat $PREFIX.prompt.answer | jq -r '.choices[0].message.content'

