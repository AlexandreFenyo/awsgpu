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
    SHORTFILENAMEB64=$(echo -n $SHORTFILENAME | base64 -w 0)
    curl "http://127.0.0.1:8123/cgi-bin/ws.cgi/markdown?filename=$SHORTFILENAMEB64"
    exit 0
fi

# ./rag.sh purge CCTP_af.docx
if test "$1" = 'purge'
then
    test -z "$2" && echo Error: must give a FILENAME && exit 1
    SHORTFILENAME=$(echo "$2" | sed 's%.*/%%')
    # lancer via WS : ./src/pipeline-advanced/purge.sh CCTP_af.docx
    SHORTFILENAMEB64=$(echo -n $SHORTFILENAME | base64 -w 0)
    curl "http://127.0.0.1:8123/cgi-bin/ws.cgi/purge?filename=$SHORTFILENAMEB64"
    exit 0
fi

# ./rag.sh images CCTP_af.docx => CCTP_af.docx.html.md.converted.md
if test "$1" = 'images'
then
    test -z "$2" && echo Error: must give a FILENAME && exit 1
    SHORTFILENAME=$(echo "$2" | sed 's%.*/%%')

    # lancer via WS : ./src/pipeline-advanced/describe_images.py -l ../awsgpu-docs/collection/CCTP_af.docx.html.md
    SHORTFILENAMEB64=$(echo -n $SHORTFILENAME | base64 -w 0)
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
    SHORTFILENAMEB64=$(echo -n $SHORTFILENAME | base64 -w 0)
    curl "http://127.0.0.1:8123/cgi-bin/ws.cgi/embeddings?filename=$SHORTFILENAMEB64"
    exit 0
fi

# ./rag.sh request QUESTION
if test "$1" = 'request'
then
    test -z "$2" && echo Error: must give a question && exit 1
    REQUEST=$(echo "$2" | sed 's%.*/%%')

    # lancer via WS :
    # ./scripts/request.sh -r "Décris-moi ... ?"
    REQUESTB64=$(echo -n $REQUEST | base64 -w 0)
    curl "http://127.0.0.1:8123/cgi-bin/ws.cgi/request?request=$REQUESTB64"
    exit 0
fi

# ./rag.sh request-openai QUESTION
if test "$1" = 'request-openai'
then
    test -z "$2" && echo Error: must give a question && exit 1
    REQUEST=$(echo "$2" | sed 's%.*/%%')

    # lancer via WS :
    # ./scripts/request.sh -o -r "Décris-moi ... ?"
    REQUESTB64=$(echo -n $REQUEST | base64 -w 0)
    APIKEYB64=$(echo -n $OPENAIAPIKEY | base64 -w 0)
    curl "http://127.0.0.1:8123/cgi-bin/ws.cgi/request-openai?request=$REQUESTB64&apikey=$APIKEYB64"
    exit 0
fi

# ./rag.sh request-embeddings QUESTION
if test "$1" = 'request-embeddings'
then
    test -z "$2" && echo Error: must give a question && exit 1
    REQUEST=$(echo "$2" | sed 's%.*/%%')

    # lancer via WS :
    # ./scripts/request.sh -n "Décris-moi ... ?"
    REQUESTB64=$(echo -n $REQUEST | base64 -w 0)
    curl "http://127.0.0.1:8123/cgi-bin/ws.cgi/request-embeddings?request=$REQUESTB64"
    exit 0
fi

# ./rag.sh request-embeddings-reranked QUESTION
if test "$1" = 'request-embeddings-reranked'
then
    test -z "$2" && echo Error: must give a question && exit 1
    REQUEST=$(echo "$2" | sed 's%.*/%%')

    # lancer via WS :
    # ./scripts/request.sh -n -r "Décris-moi ... ?"
    REQUESTB64=$(echo -n $REQUEST | base64 -w 0)
    curl "http://127.0.0.1:8123/cgi-bin/ws.cgi/request-embeddings-reranked?request=$REQUESTB64"
    exit 0
fi

curl "http://127.0.0.1:8123/cgi-bin/ws.cgi/$1"
