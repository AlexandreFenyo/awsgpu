#!/bin/zsh

if test -z "$1"
then
    $0 help
    exit 0
fi

curl "http://127.0.0.1:8123/cgi-bin/ws.cgi/$1"
