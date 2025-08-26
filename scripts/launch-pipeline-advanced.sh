#!/bin/zsh

date

echo stopping Weaviate:
./scripts/stop-weaviate.sh

echo starting Weaviate:
./scripts/start-weaviate.sh

echo adding first document:
./scripts/launch-pipeline-advanced-add-file.sh ../awsgpu-docs/CCTP.docx

echo adding new document:
./scripts/launch-pipeline-advanced-add-file.sh -n ../awsgpu-docs/CCTP-accueil.docx

date
