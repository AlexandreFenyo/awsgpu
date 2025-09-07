#!/bin/zsh

for i in {paraphrase-xlm-r-multilingual-v1,intfloat/multilingual-e5-large,BAAI/bge-multilingual-gemma2,sentence-transformers/sentence-t5-xl,sentence-transformers/all-mpnet-base-v2}
do
echo $i
echo "- 1 vs 2"
./src/pipeline-advanced/get_emb_distance.py -m $i "$1" "$2" | jq -r .distance
echo "- 1 vs 3"
./src/pipeline-advanced/get_emb_distance.py -m $i "$1" "$3" | jq -r .distance
echo
done

