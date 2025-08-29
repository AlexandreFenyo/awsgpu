#!/bin/zsh

echo stopping Weaviate:
./scripts/stop-weaviate.sh

echo starting Weaviate:
./scripts/start-weaviate.sh

INPUT_FILE=../awsgpu-docs/CCTP.docx

echo converting document:
./src/pipeline-advanced/convert_to_markdown.py $INPUT_FILE

echo creating chunks for text content:
./src/pipeline-advanced/create_chunks.py $INPUT_FILE.md

#echo removing embeddings cache:
#rm -f $INPUT_FILE.md.chunks.jq.paraphrase-xlm-r-multilingual-v1.emb_cache.jsonl

#echo creating embeddings for text content:
#./src/pipeline-advanced/create_embeddings.py $INPUT_FILE.md.chunks.jq

#echo updating Weaviate for text content:
#./src/pipeline-advanced/update_weaviate.py $INPUT_FILE.md.chunks.jq.embeddings.ndjson
