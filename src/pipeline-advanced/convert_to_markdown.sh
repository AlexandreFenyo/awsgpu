#!/bin/zsh

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

ts-node ./src/pipeline-advanced/convert_to_markdown.ts "$INPUT_FILE"
src/pipeline-advanced/html_to_markdown.py "$INPUT_FILE".html
