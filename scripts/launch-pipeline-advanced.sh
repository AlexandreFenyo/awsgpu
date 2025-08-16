#!/bin/zsh

date

echo stopping Weaviate:
./scripts/stop-weaviate.sh

echo starting Weaviate:
./scripts/start-weaviate.sh

#echo converting document:
#./src/pipeline/convert_to_markdown.py $HOME/CCTP/CCTP2.docx

#echo creating chunks:
#./src/pipeline-advanced/create_chunks.py $HOME/CCTP/CCTP2.docx.md

echo creating embeddings:
./src/pipeline-advanced/create_embeddings.py $HOME/CCTP/CCTP2.docx.md.chunks.jq

exit 0

echo updating Weaviate:
./src/pipeline/update_weaviate.py $HOME/CCTP/CCTP2.docx.md.chunks.jq.embeddings.ndjson

echo making request:
./src/pipeline/search_chunks.py "Les CPAM sont-elles publiques ou privées ?"

date
