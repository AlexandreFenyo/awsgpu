#!/bin/zsh

date

echo stopping Weaviate:
./scripts/stop-weaviate.sh

echo starting Weaviate:
./scripts/start-weaviate.sh

echo converting document:
./src/pipeline-advanced/convert_to_markdown.py $HOME/CCTP/CCTP2.docx

echo creating chunks for text content:
./src/pipeline-advanced/create_chunks.py $HOME/CCTP/CCTP2.docx.md

echo creating chunks for headings:
./src/pipeline-advanced/create_headings_chunks.py $HOME/CCTP/CCTP2.docx.md

echo removing embeddings cache:
rm -f $HOME/CCTP/CCTP2.docx.md.chunks.jq.paraphrase-xlm-r-multilingual-v1.emb_cache.jsonl

echo creating embeddings for text content:
./src/pipeline-advanced/create_embeddings.py --no-heading-embeddings $HOME/CCTP/CCTP2.docx.md.chunks.jq

echo updating Weaviate for text content:
./src/pipeline-advanced/update_weaviate.py $HOME/CCTP/CCTP2.docx.md.chunks.jq.embeddings.ndjson

echo creating embeddings for headings:
./src/pipeline-advanced/create_embeddings.py $HOME/CCTP/CCTP2.docx.md.headings.chunks.jq

echo updating Weaviate for headings:
./src/pipeline-advanced/update_weaviate.py -c rag_headings_chunks $HOME/CCTP/CCTP2.docx.md.headings.chunks.jq.embeddings.ndjson

echo collecting chunks for text content:
./src/pipeline-advanced/search_chunks.py "Les CPAM sont-elles publiques ou privées ?"

echo collecting chunks for headings:
./src/pipeline-advanced/search_chunks.py -c rag_headings_chunks "Les CPAM sont-elles publiques ou privées ?"

date
