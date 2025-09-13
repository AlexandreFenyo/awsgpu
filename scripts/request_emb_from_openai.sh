#!/bin/zsh
set -euo pipefail

# Options:
# -n: dry-run (propagate to merge step)
# -r: enable reranking pipeline
# -o: use OpenAI LLM in merge step
DRY_RUN=0
RERANK=0
OPENAI_LLM=0

usage() {
  echo 'Usage: request.sh [-h] [-n] [-r] [-o] REQUEST'
}

while getopts "nhro" opt; do
  case "$opt" in
    n) DRY_RUN=1 ;;
    r) RERANK=1 ;;
    o) OPENAI_LLM=1 ;;
    h) usage; exit 0 ;;
    *) usage; exit 2 ;;
  esac
done
shift $((OPTIND-1))
QUESTION="$*"

if [[ -z "$QUESTION" ]]; then
  usage
  exit 1
fi

date

# Crée un fichier temporaire de préfixe pour tous les artefacts de cette exécution.
PREFIX=$(mktemp /tmp/chunks-XXXXXXXXXX)
JSONL="${PREFIX}.jsonl"

if [[ $RERANK -eq 0 ]]; then
  echo "collecting 50 chunks for text content:"
  ./src/pipeline-advanced/search_chunks.py --openai "$QUESTION" > "$JSONL"
else
    echo error: can not rerank locally with embeddings from OpenAI
    exit 1
  #echo "collecting 500 candidate chunks for text content:"
  #./src/pipeline-advanced/search_chunks.py --openai -k 500 "$QUESTION" > "${PREFIX}.initial-ranking.jsonl"
  #echo "reranking candidate chunks:"
  #./src/pipeline-advanced/rerank.py "$QUESTION" "${PREFIX}.initial-ranking.jsonl"
  #echo "filtering 50 best chunks:"
  #head -50 "${PREFIX}.initial-ranking.jsonl.reranked.jq" > "$JSONL"
fi
echo "$JSONL"

echo -n "updating chunks (adding titles): "
./src/pipeline-advanced/process_chunks_add_title.py "$JSONL"

echo
echo "making request:"

typeset -a merge_args
merge_args=()
if [[ $DRY_RUN -eq 1 ]]; then
  merge_args+=(-n)
fi
if [[ $OPENAI_LLM -eq 1 ]]; then
  merge_args+=(-o)
fi

./src/pipeline-advanced/merge_chunks.sh "${merge_args[@]}" "${JSONL}.embeddings.ndjson" "$QUESTION"

date
