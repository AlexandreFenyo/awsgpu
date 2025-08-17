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

echo searching chunks:
./src/pipeline-advanced/search_chunks.py "$QUESTION" > /tmp/chunks.txt

echo
echo making request:
if [ $DRY_RUN -eq 1 ]; then
  ./src/pipeline-advanced/merge_chunks.sh -n /tmp/chunks.txt "$QUESTION"
else
  ./src/pipeline-advanced/merge_chunks.sh /tmp/chunks.txt "$QUESTION"
fi

date
