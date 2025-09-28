
GITDIR=/mnt/c/Alex/git

all:
	@cat Makefile

build:
	@docker build -t fenyoa/rag -f docker/Dockerfile .

run: create-network
	@docker run -d --name rag --rm --network weaviate-rag-network -p 8123:80 -v $(GITDIR)/awsgpu-docs:/var/awsgpu-docs -v $(GITDIR)/awsgpu/docker/tst.cgi:/usr/lib/cgi-bin/tst.cgi -v $(GITDIR)/awsgpu/docker/ws.cgi:/usr/lib/cgi-bin/ws.cgi -v $(GITDIR)/awsgpu/scripts:/var/www/scripts -v $(GITDIR)/awsgpu/src:/var/www/src fenyoa/rag

run-interactive: create-network
	@docker run --name rag --rm --network weaviate-rag-network --add-host=host.docker.internal:host-gateway -t -i -p 8123:80 -v $(GITDIR)/awsgpu-docs:/var/awsgpu-docs -v $(GITDIR)/awsgpu/docker/tst.cgi:/usr/lib/cgi-bin/tst.cgi -v $(GITDIR)/awsgpu/docker/ws.cgi:/usr/lib/cgi-bin/ws.cgi fenyoa/rag

# W11% docker network create -d bridge weaviate-rag-network

create-network:
	-@docker network create -d bridge weaviate-rag-network

run-weaviate: create-network
# ports exposés: 8080 et 50051
	@docker run -d --name weaviate-rag --network weaviate-rag-network --add-host=host.docker.internal:host-gateway -e GRPC_ENABLED=true -e GRPC_PORT=50051 -e QUERY_DEFAULTS_LIMIT=50 -e AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=true -e PERSISTENCE_DATA_PATH=/tmp/weaviate -v weaviate-rag-data:/tmp/weaviate semitechnologies/weaviate:latest

start-weaviate:
	@docker start weaviate-rag

stop-weaviate:
	-@docker stop weaviate-rag

rm-weaviate:
	-@docker rm weaviate-rag
	-@docker volume rm weaviate-rag-data

stop-rm-weaviate: stop-weaviate rm-weaviate

shell:
	@echo should run: su - www-data
	@docker exec -t -i rag zsh

stop:
	-@docker stop rag

rm:
	-@docker rm rag

stop-rm: stop rm

rmi:
	@docker rmi fenyoa/rag

install-front:
	npm init -y
	npm install react react-dom && npm install -D typescript esbuild @types/react @types/react-dom
	python3 -m pip install flask

front:
	npx esbuild src/front/chat.ts --bundle --outfile=src/front/chat.js --format=iife --target=es2020 --minify

run-back: front
	rm -f src/front/prompt-do-not-edit.txt
	cp ../awsgpu-docs/prompt.txt src/front/prompt-do-not-edit.txt
	#echo > src/front/prompt-do-not-edit.txt
	cp ../awsgpu-docs/prompt2.txt src/front/prompt2-do-not-edit.txt
	#echo > src/front/prompt2-do-not-edit.txt
	cp ../awsgpu-docs/prompt-nofilter.txt src/front/prompt-nofilter-do-not-edit.txt
	cp ../awsgpu-docs/prompt2-nofilter.txt src/front/prompt2-nofilter-do-not-edit.txt
	cp ../awsgpu-docs/system.txt src/front/system.txt
	#echo > src/front/system.txt
	cp ../awsgpu-docs/system-DO.txt src/front/system-DO.txt
	cp ../awsgpu-docs/system-SB.txt src/front/system-SB.txt
	python3 src/front/server.py -s

run-back-mcp: front
	cp ../awsgpu-docs/system.txt src/front/system.txt
	OLLAMA_URL=http://127.0.0.1:8000/api/chat python3 src/front/server.py -v

run-mcp-bridge:
	ollama-mcp-bridge --config MCP/mcp-config.json --ollama-url http://192.168.0.21:11434

test:
	@echo $(GITDIR)
