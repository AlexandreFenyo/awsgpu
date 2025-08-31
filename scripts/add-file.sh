#!/bin/zsh

# Options:
# -m: do not convert document to markdown, start from the md file
NO_CONVERT=""
while getopts "nmh" opt; do
  case "$opt" in
      m) NO_CONVERT="-m" ;;
      h) echo 'Usage: "$0" [-h] [-n] [-m] DOCUMENT' ; exit 0 ;;
    *) ;;
  esac
done
shift $((OPTIND-1))

if ! test -n "$1"
then
    echo 'error: no file name'
    exit 1
fi

INPUT_FILE=$1

if test -z "$NO_CONVERT"
then
    echo converting document:
    ./src/pipeline-advanced/convert_to_markdown.sh $INPUT_FILE

    echo converting images:
    ./src/pipeline-advanced/describe_images.py -t $INPUT_FILE.html.md
fi

echo creating chunks for text content:
./src/pipeline-advanced/create_chunks.py $INPUT_FILE.html.md.converted.md

echo removing embeddings cache:
rm -f $INPUT_FILE.docx.html.md.converted.md.chunks.jq.paraphrase-xlm-r-multilingual-v1.emb_cache.jsonl

echo creating embeddings for text content:
./src/pipeline-advanced/create_embeddings.py $INPUT_FILE.html.md.converted.md.chunks.jq

echo updating Weaviate for text content:
./src/pipeline-advanced/update_weaviate.py $INPUT_FILE.html.md.converted.md.chunks.jq.embeddings.ndjson

