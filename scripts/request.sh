#!/bin/zsh

date

echo searching chunks:
./src/pipeline-advanced/search_chunks.py $1 > /tmp/chunks.txt

echo
echo making request:
./src/pipeline-advanced/merge_chunks.sh /tmp/chunks.txt $1

date
