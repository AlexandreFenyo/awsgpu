#!/bin/zsh

date

echo stopping Weaviate:
./scripts/stop-weaviate.sh

echo starting Weaviate:
./scripts/start-weaviate.sh

echo converting document:
./src/pipeline/convert_to_markdown.py $HOME/CCTP/CCTP.docx

echo creating chunks:
./src/pipeline/create_chunks.py $HOME/CCTP/CCTP.docx.md

echo creating embeddings:
./src/pipeline/create_embeddings.py $HOME/CCTP/CCTP.docx.md.chunks.jq

echo updating Weaviate:
./src/pipeline/update_weaviate.py $HOME/CCTP/CCTP.docx.md.chunks.jq.embeddings.ndjson

echo making request:
./src/pipeline/search_chunks.py "Qu'est-ce que la CNAM ?"

date
