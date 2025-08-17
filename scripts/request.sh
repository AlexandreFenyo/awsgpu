#!/bin/zsh

# Options:
# -n: dry-run (propagate to merge step)
DRY_RUN=0
while getopts "n" opt; do
  case "$opt" in
    n) DRY_RUN=1 ;;
    *) ;;
  esac
done
shift $((OPTIND-1))
QUESTION="$*"

date

mktemp /tmp/chunks-XXXXXXXXXX | read PREFIX

echo searching chunks:
./src/pipeline-advanced/search_chunks.py "$QUESTION" > $PREFIX.jsonl

echo
echo making request:
if [ $DRY_RUN -eq 1 ]; then
  ./src/pipeline-advanced/merge_chunks.sh -n $PREFIX.jsonl "$QUESTION"
else
  ./src/pipeline-advanced/merge_chunks.sh $PREFIX.jsonl "$QUESTION"
fi

date
