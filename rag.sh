#!/bin/zsh

if test -z "$1" -o "$1" = '-h' -o "$1" = '--help'
then
    cat <<EOF
add FILENAME
  add a new file
EOF
    $0 help
    exit 0
fi

# ./rag.sh add /tmp/CCTP_af.docx => CCTP_af.docx.html.md
if test "$1" = 'add'
then
    test -z "$2" && echo Error: must give a FILENAME && exit 1
    SHORTFILENAME=$(echo "$2" | sed 's%.*/%%')
    ls ../awsgpu-docs/collection | egrep "^$SHORTFILENAME" | wc -l | read NFILES
    test "$NFILES" -gt 0 && echo Error: some files already exist starting with this name "'$SHORTFILENAME'" && exit 1
    echo "copy file '$2' to ../awsgpu-docs/collection"
    cp "$2" ../awsgpu-docs/collection || exit 1

    # lancer via WS : ./src/pipeline-advanced/convert_to_markdown.sh ../awsgpu-docs/collection/CCTP_af.docx
    SHORTFILENAMEB64=$(echo -n $SHORTFILENAME | base64)
    curl "http://127.0.0.1:8123/cgi-bin/ws.cgi/markdown?filename=$SHORTFILENAMEB64"
    exit 0
fi

# ./rag.sh images CCTP_af.docx => CCTP_af.docx.html.md.converted.md
if test "$1" = 'images'
then
    test -z "$2" && echo Error: must give a FILENAME && exit 1
    SHORTFILENAME=$(echo "$2" | sed 's%.*/%%')

    # lancer via WS : ./src/pipeline-advanced/describe_images.py -l ../awsgpu-docs/collection/CCTP_af.docx.html.md
    SHORTFILENAMEB64=$(echo -n $SHORTFILENAME | base64)
    curl "http://127.0.0.1:8123/cgi-bin/ws.cgi/images?filename=$SHORTFILENAMEB64"
    exit 0
fi

# ./rag.sh chunks CCTP_af.docx => CCTP_af.docx.html.md.converted.md.chunks.jq.embeddings.ndjson
if test "$1" = 'embeddings'
then
    test -z "$2" && echo Error: must give a FILENAME && exit 1
    SHORTFILENAME=$(echo "$2" | sed 's%.*/%%')

    # lancer via WS :
    # ./src/pipeline-advanced/create_chunks.py ../awsgpu-docs/collection/CCTP_af.docx.html.md.converted.md
    # ./src/pipeline-advanced/create_embeddings.py ../awsgpu-docs/collection/CCTP_af.docx.html.md.converted.md.chunks.jq
    # ./src/pipeline-advanced/update_weaviate.py ../awsgpu-docs/collection/CCTP_af.docx.html.md.converted.md.chunks.jq.embeddings.ndjson
    SHORTFILENAMEB64=$(echo -n $SHORTFILENAME | base64)
    curl "http://127.0.0.1:8123/cgi-bin/ws.cgi/embeddings?filename=$SHORTFILENAMEB64"
    exit 0
fi

curl "http://127.0.0.1:8123/cgi-bin/ws.cgi/$1"
