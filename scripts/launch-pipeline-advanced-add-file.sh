#!/bin/zsh

# Options:
# -n: do not create collection nor schema, when processing a new document
# -m: do not convert document to markdown, start from the md file
NEW_DOC=""
NO_CONVERT=""
while getopts "nmh" opt; do
  case "$opt" in
      n) NEW_DOC="-n" ;;
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
    ./src/pipeline-advanced/convert_to_markdown.py $INPUT_FILE
fi

echo creating chunks for text content:
./src/pipeline-advanced/create_chunks.py $INPUT_FILE.md

#echo creating chunks for headings:
#./src/pipeline-advanced/create_headings_chunks.py $INPUT_FILE.md

echo removing embeddings cache:
rm -f $INPUT_FILE.md.chunks.jq.paraphrase-xlm-r-multilingual-v1.emb_cache.jsonl

echo creating embeddings for text content:
./src/pipeline-advanced/create_embeddings.py $INPUT_FILE.md.chunks.jq

echo updating Weaviate for text content:
if test -z "$NEW_DOC"
then
    ./src/pipeline-advanced/update_weaviate.py $INPUT_FILE.md.chunks.jq.embeddings.ndjson
else
    ./src/pipeline-advanced/update_weaviate.py -n $INPUT_FILE.md.chunks.jq.embeddings.ndjson
fi

#echo creating embeddings for headings:
#./src/pipeline-advanced/create_embeddings.py $HOME/CCTP/CCTP.docx.md.headings.chunks.jq

#echo updating Weaviate for headings:
#./src/pipeline-advanced/update_weaviate.py -c rag_headings_chunks $HOME/CCTP/CCTP.docx.md.headings.chunks.jq.embeddings.ndjson

#echo collecting chunks for text content:
#mktemp /tmp/retrieved-chunks-XXXXXXXXXX | read PREFIX
#./src/pipeline-advanced/search_chunks.py "Les CPAM sont-elles publiques ou privées ?" > $PREFIX.ndjson

#echo updating chunks: adding titles
#./src/pipeline-advanced/process_chunks_add_title.py $PREFIX.ndjson

#echo collecting chunks for headings:
#./src/pipeline-advanced/search_chunks.py -c rag_headings_chunks "Les CPAM sont-elles publiques ou privées ?" > $PREFIX.headings.ndjson

date

