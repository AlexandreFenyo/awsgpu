#!/bin/zsh

# curl http://127.0.0.1:8123/cgi-bin/ws.cgi/help

echo Content-type: text/html
echo

export WEAVIATE_HOST=weaviate-rag
export OLLAMA_HOST=host.docker.internal

date
cd /var/www
source $HOME/.zshrc

case "$PATH_INFO" in
    /help)
	echo /ps /kill-all /sleep /launch-pipeline-advanced /update-weaviate
	;;
    /ps)
	ps -fauxgww
	;;

    /kill-all)
	ps -fax | grep -v /usr/sbin/apache2 | awk '{ print $1; }' | fgrep -v $$ | fgrep -v PID | xargs /usr/bin/kill -9
	;;
    
    /sleep)
	nohup sleep 3600 >& /dev/null &
	;;
    
    /launch-pipeline-advanced)
	./scripts/launch-pipeline-advanced.sh 2>&1
	;;

    /update-weaviate)
	touch FICHIER
	./src/pipeline-advanced/update_weaviate.py FICHIER 2>&1
	;;

    *)
	echo 'Err: command not found (use .../ws.cgi/help)' 2>&1
	;;
esac

echo END.
exit 0
