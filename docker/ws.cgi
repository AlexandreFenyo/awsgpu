#!/bin/zsh

# curl http://127.0.0.1:8123/cgi-bin/ws.cgi/help

echo Content-type: text/html
echo

export WEAVIATE_HOST=weaviate-rag
export OLLAMA_HOST=host.docker.internal

#echo -n "start time: "
#date

cd /var/www
source $HOME/.zshrc

case "$PATH_INFO" in
    /help) # display help
	cat $0 | egrep -v 'cat.*sed' | egrep '\s/.*)' | tr '/)' '  ' | sed 's/ *//' | sed 's/ *# */\n    /'
	;;

    /clear) # clear Weaviate
	./src/pipeline-advanced/init_or_reset_collection.py 2>&1
	;;

    /ps) # dump process list
	ps -fauxgww
	;;

    /kill-all) # kill background processes
	ps -fax | grep -v /usr/sbin/apache2 | awk '{ print $1; }' | fgrep -v $$ | fgrep -v PID | xargs /usr/bin/kill -9
	;;
    
    /sleep) # fork a sleep for 1 hour, to help debugging
	nohup sleep 3600 >& /dev/null &
	;;
    
    /launch-pipeline-advanced) # run launch-pipeline-advanced.sh
	./scripts/launch-pipeline-advanced.sh 2>&1
	;;

    /markdown) # convert a file to Markdown
	FILENAME=$(echo $QUERY_STRING | sed 's/&/\n/' | egrep '^filename=' | sed 's/^filename=//' | base64 -d)
	echo "converting file: $FILENAME"
	./src/pipeline-advanced/convert_to_markdown.sh ../awsgpu-docs/collection/"$FILENAME" 2>&1
	;;

    /images) # convert Markdown images to text
	FILENAME=$(echo $QUERY_STRING | sed 's/&/\n/' | egrep '^filename=' | sed 's/^filename=//' | base64 -d)
	echo "converting images from file: $FILENAME"
	./src/pipeline-advanced/describe_images.py -l ../awsgpu-docs/collection/"$FILENAME".html.md 2>&1
	;;

    /embeddings) # create chunks and embeddings, then update Weaviate
	FILENAME=$(echo $QUERY_STRING | sed 's/&/\n/' | egrep '^filename=' | sed 's/^filename=//' | base64 -d)
	echo "creatings chunks from file: $FILENAME"
	./src/pipeline-advanced/create_chunks.py ../awsgpu-docs/collection/"$FILENAME".html.md.converted.md 2>&1
	echo "creatings embeddings from file: $FILENAME"
	rm -f ../awsgpu-docs/collection/"$FILENAME".html.md.converted.md.chunks.jq.paraphrase-xlm-r-multilingual-v1.emb_cache.jsonl 2>&1
	./src/pipeline-advanced/create_embeddings.py ../awsgpu-docs/collection/"$FILENAME".html.md.converted.md.chunks.jq 2>&1
	echo "updating Weaviate from file: $FILENAME"
	./src/pipeline-advanced/update_weaviate.py ../awsgpu-docs/collection/"$FILENAME".html.md.converted.md.chunks.jq.embeddings.ndjson 2>&1
	;;

    *)
	echo "Err: command '$PATH_INFO' not found (use .../ws.cgi/help)" 2>&1
	;;
esac

#echo -n "end time: "
#date
#echo END.

exit 0
