#!/bin/zsh

echo Content-type: text/html
echo

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
	WEAVIATE_HOST=weaviate-rag ./src/pipeline-advanced/update_weaviate.py FICHIER 2>&1
	;;

    *)
	echo Err: command not found 2>&1
	;;
esac

echo END.
exit 0
