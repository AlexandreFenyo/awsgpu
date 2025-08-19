#!/bin/zsh

date

echo stopping Weaviate:
./scripts/stop-weaviate.sh

echo starting Weaviate:
./scripts/start-weaviate.sh

echo adding first document:
./scripts/launch-pipeline-advanced-add-file.sh $HOME/CCTP/CCTP.docx

echo adding new document:
./scripts/launch-pipeline-advanced-add-file.sh -n $HOME/CCTP/CCTP-accueil.docx

date
