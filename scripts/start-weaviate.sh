#!/bin/zsh

# Launch the Docker daemon

if test $HOST = Mac-mini-de-Alexandre.local
then
	open -a Docker
fi

if test $HOST = W11
then
	/mnt/c/Program\ Files/Docker/Docker/Docker\ Desktop.exe
fi

# Create and start the Weaviate container, with a fresh database

rm -rf /tmp/weaviate
mkdir -p /tmp/weaviate
docker volume rm weaviate_data
docker run -d --name weaviate -p 8080:8080 -p 50051:50051 -e GRPC_ENABLED=true -e GRPC_PORT=50051 -e QUERY_DEFAULTS_LIMIT=50 -e AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=true -e PERSISTENCE_DATA_PATH=/tmp/weaviate -v weaviate_data:/tmp/weaviate semitechnologies/weaviate:latest
