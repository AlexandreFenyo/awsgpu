#!/bin/zsh

date

echo stopping Weaviate:
./scripts/stop-weaviate.sh

echo starting Weaviate:
./scripts/start-weaviate.sh

echo adding first document:
./scripts/launch-pipeline-advanced-add-file.sh ../awsgpu-docs/CCTP.docx

echo adding new document: ../awsgpu-docs/CCTP-accueil.docx
./scripts/launch-pipeline-advanced-add-file.sh -n ../awsgpu-docs/CCTP-accueil.docx

echo adding new document directly from MarkDown: ../awsgpu-docs/MESDMP_Annexe_12.docx
./scripts/launch-pipeline-advanced-add-file.sh -n -m ../awsgpu-docs/MESDMP_Annexe_12.docx

echo adding new document directly from MarkDown: ../awsgpu-docs/Memoire_Technique.docx
./scripts/launch-pipeline-advanced-add-file.sh -n -m ../awsgpu-docs/Memoire_Technique.docx

date
