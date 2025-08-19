#!/bin/zsh

# Options:
# -n: dry-run (propagate to merge step)
DRY_RUN=0
while getopts "nh" opt; do
  case "$opt" in
      n) DRY_RUN=1 ;;
      h) echo 'Usage: request.sh [-h] [-n] REQUEST' ; exit 0 ;;
    *) ;;
  esac
done
shift $((OPTIND-1))
QUESTION="$*"

date

mktemp /tmp/chunks-XXXXXXXXXX | read PREFIX

echo -n "collecting chunks for text content: "
./src/pipeline-advanced/search_chunks.py "$QUESTION" > $PREFIX.jsonl
echo $PREFIX.jsonl

#echo -n "collecting chunks for headings: "
#./src/pipeline-advanced/search_chunks.py -c rag_headings_chunks "$QUESTION" > $PREFIX.headings.jsonl
#echo $PREFIX.headings.jsonl

echo -n "updating chunks (adding titles): "
./src/pipeline-advanced/process_chunks_add_title.py $PREFIX.jsonl

echo
echo making request:
if [ $DRY_RUN -eq 1 ]; then
  ./src/pipeline-advanced/merge_chunks.sh -n $PREFIX.jsonl.embeddings.ndjson "$QUESTION"
else
  ./src/pipeline-advanced/merge_chunks.sh $PREFIX.jsonl.embeddings.ndjson "$QUESTION"
fi

date
