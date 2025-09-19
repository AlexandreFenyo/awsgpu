#!/bin/zsh

for step in {1..3}
do
    echo "$1" > /tmp/oquery.txt
    echo "Répondez à la question en vous appuyant sur le texte suivant, soyez très détaillé pour ne rien oublier, ne rajoutez pas un résumé de la réponse :" >> /tmp/oquery.txt
    cat ../awsgpu-docs/collection/documents-pre/memoire_af_short_part"$step".md >> /tmp/oquery.txt
    ./scripts/oquery.sh 192.168.0.21 gpt-oss:20b 128000 /tmp/oquery.txt > /tmp/oquery-ans"$step".txt
    echo step "$step"/3 done.
done

echo "$1" > /tmp/oquery.txt
echo "Répondez à la question en vous appuyant sur le texte suivant, soyez très détaillé pour ne rien oublier :" >> /tmp/oquery.txt
cat /tmp/oquery-ans{1,2,3}.txt >> /tmp/oquery.txt
./scripts/oquery.sh 192.168.0.21 gpt-oss:20b 128000 /tmp/oquery.txt
