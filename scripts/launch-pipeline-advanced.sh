#!/bin/zsh

date

#echo stopping Weaviate:
./scripts/stop-weaviate.sh

#echo starting Weaviate:
./scripts/start-weaviate.sh

echo init or reset collection:
./src/pipeline-advanced/init_or_reset_collection.py

#echo adding: CCTP.docx
#./scripts/add-file.sh ../awsgpu-docs/collection/CCTP.docx

echo adding: CCTP_accueil.docx
./scripts/add-file.sh ../awsgpu-docs/collection/CCTP_accueil.docx

#echo adding new document directly from MarkDown: ../awsgpu-docs/MESDMP_Annexe_12.docx
#./scripts/add-file.sh -m ../awsgpu-docs/MESDMP_Annexe_12.docx

#echo adding new document directly from MarkDown: ../awsgpu-docs/Memoire_Technique.docx
#./scripts/add-file.sh -m ../awsgpu-docs/Memoire_Technique.docx

date
