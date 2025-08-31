
GITDIR=/mnt/c/Alex/git

all:
	@cat Makefile

build:
	@docker build -t fenyoa/rag -f docker/Dockerfile .

run: create-network
	@docker run -d --name rag --rm --network weaviate-rag-network -p 8123:80 -v $(GITDIR)/awsgpu-docs:/var/awsgpu-docs -v $(GITDIR)/awsgpu/docker/tst.cgi:/usr/lib/cgi-bin/tst.cgi -v $(GITDIR)/awsgpu/docker/ws.cgi:/usr/lib/cgi-bin/ws.cgi fenyoa/rag

run-interactive: create-network
	@docker run --name rag --rm --network weaviate-rag-network -t -i -p 8123:80 -v $(GITDIR)/awsgpu-docs:/var/awsgpu-docs -v $(GITDIR)/awsgpu/docker/tst.cgi:/usr/lib/cgi-bin/tst.cgi -v $(GITDIR)/awsgpu/docker/ws.cgi:/usr/lib/cgi-bin/ws.cgi fenyoa/rag

# W11% docker network create -d bridge weaviate-rag-network

create-network:
	-@docker network create -d bridge weaviate-rag-network

run-weaviate: create-network
# ports exposés: 8080 et 50051
	@docker run -d --name weaviate-rag --network weaviate-rag-network -e GRPC_ENABLED=true -e GRPC_PORT=50051 -e QUERY_DEFAULTS_LIMIT=50 -e AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=true -e PERSISTENCE_DATA_PATH=/tmp/weaviate -v weaviate-rag-data:/tmp/weaviate semitechnologies/weaviate:latest

stop-weaviate:
	-@docker stop weaviate-rag

rm-weaviate:
	-@docker rm weaviate-rag
	-@docker volume rm weaviate-rag-data

stop-rm-weaviate: stop-weaviate rm-weaviate

shell:
	@docker exec -t -i rag zsh

stop:
	-@docker stop rag

rm:
	-@docker rm rag

stop-rm: stop rm

rmi:
	@docker rmi fenyoa/rag

test:
	@echo $(GITDIR)

