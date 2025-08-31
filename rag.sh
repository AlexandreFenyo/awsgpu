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

if test "$1" = 'add'
then
    test -z "$2" && echo Error: must give a FILENAME && exit 1
    SHORTFILENAME=$(echo "$2" | sed 's%.*/%%')
    ls ../awsgpu-docs/collection | egrep "^$SHORTFILENAME" | wc -l | read NFILES
    test "$NFILES" -gt 0 && echo Error: some files already exist starting with this name "'$SHORTFILENAME'" && exit 1
    echo "copy file '$2' to ../awsgpu-docs/collection"
    cp "$2" ../awsgpu-docs/collection || exit 1

    # lancer via WS : ./scripts/launch-pipeline-advanced-add-file.sh -m ../awsgpu-docs/collection/CCTP.docx
    SHORTFILENAMEB64=$(echo -n $SHORTFILENAME | base64)
    curl "http://127.0.0.1:8123/cgi-bin/ws.cgi/markdown?filename=$SHORTFILENAMEB64&truc=toto"
    
    
    exit 0
fi

curl "http://127.0.0.1:8123/cgi-bin/ws.cgi/$1"
