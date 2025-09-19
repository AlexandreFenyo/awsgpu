#!/bin/zsh

help() {
    cat <<EOF
$1 [-h | --help]
    display this help message
$1 start-weaviate
    start the weaviate container
$1 stop-weaviate
    stop the weaviate container
EOF
}

if test "$#" -eq 0
then
    help "$0"
    exit 0
fi

case "$1" in
    -h | --help)
	help
	return 0
	;;
esac

