#!/bin/zsh

date

echo stopping Weaviate:
./scripts/stop-weaviate.sh

echo starting Weaviate:
./scripts/start-weaviate.sh

echo converting document:
./src/pipeline/convert_to_markdown.py $HOME/CCTP/CCTP2.docx

echo creating chunks:
./src/pipeline-advanced/create_chunks.py $HOME/CCTP/CCTP2.docx.md

echo creating embeddings:
rm -f $HOME/CCTP/CCTP2.docx.md.chunks.jq.paraphrase-xlm-r-multilingual-v1.emb_cache.jsonl
./src/pipeline-advanced/create_embeddings.py $HOME/CCTP/CCTP2.docx.md.chunks.jq

echo updating Weaviate:
./src/pipeline-advanced/update_weaviate.py $HOME/CCTP/CCTP2.docx.md.chunks.jq.embeddings.ndjson

echo making request:
./src/pipeline-advanced/search_chunks.py "Les CPAM sont-elles publiques ou privées ?"

date
