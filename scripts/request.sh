#!/bin/zsh

# Options:
# -n: dry-run (propagate to merge step)
DRY_RUN=0
RERANK=0
OPENAI_LLM=0

while getopts "nhro" opt; do
  case "$opt" in
      n) DRY_RUN=1 ;;
      r) RERANK=1 ;;
      o) OPENAI_LLM=1 ;;
      h) echo 'Usage: request.sh [-h] [-n] [-r] [-o] REQUEST' ; exit 0 ;;
    *) ;;
  esac
done
shift $((OPTIND-1))
QUESTION="$*"

date

mktemp /tmp/chunks-XXXXXXXXXX | read PREFIX

if [ $RERANK -eq 0 ]; then
  echo "collecting 50 chunks for text content:"
  ./src/pipeline-advanced/search_chunks.py "$QUESTION" > $PREFIX.jsonl
else
  echo "collecting 200 chunks for text content:"
  ./src/pipeline-advanced/search_chunks.py -k 500 "$QUESTION" > $PREFIX.initial-ranking.jsonl
  echo "reranking 200 chunks:"
  ./src/pipeline-advanced/rerank.py "$QUESTION" $PREFIX.initial-ranking.jsonl
  echo "filtering 50 best chunks:"
  head -50 $PREFIX.initial-ranking.jsonl.reranked.jq > $PREFIX.jsonl
fi
echo $PREFIX.jsonl

echo -n "updating chunks (adding titles): "
./src/pipeline-advanced/process_chunks_add_title.py $PREFIX.jsonl

echo
echo making request:
if [ $DRY_RUN -eq 1 ]; then
if [ $OPENAI_LLM -eq 1 ]; then
    ./src/pipeline-advanced/merge_chunks.sh -n -o $PREFIX.jsonl.embeddings.ndjson "$QUESTION"
  else
    ./src/pipeline-advanced/merge_chunks.sh -n $PREFIX.jsonl.embeddings.ndjson "$QUESTION"
  fi
else
if [ $OPENAI_LLM -eq 1 ]; then
    ./src/pipeline-advanced/merge_chunks.sh -o $PREFIX.jsonl.embeddings.ndjson "$QUESTION"
  else
    ./src/pipeline-advanced/merge_chunks.sh $PREFIX.jsonl.embeddings.ndjson "$QUESTION"
  fi
fi

date
