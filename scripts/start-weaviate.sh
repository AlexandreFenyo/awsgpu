#!/bin/zsh

open -a Docker
rm -rf /tmp/weaviate
mkdir -p /tmp/weaviate
docker volume rm weaviate_data
docker run -d --name weaviate -p 8080:8080 -p 50051:50051 -e GRPC_ENABLED=true -e GRPC_PORT=50051 -e QUERY_DEFAULTS_LIMIT=50 -e AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=true -e PERSISTENCE_DATA_PATH=/tmp/weaviate -v weaviate_data:/tmp/weaviate semitechnologies/weaviate:latest
# docker run -d --name weaviate -p 8080:8080 -p 50051:50051 -e CLUSTER_HOSTNAME=localhost -e GRPC_ENABLED=true -e GRPC_PORT=50051 -e QUERY_DEFAULTS_LIMIT=50 -e AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=true -e PERSISTENCE_DATA_PATH=/tmp/weaviate -v weaviate_data:/tmp/weaviate semitechnologies/weaviate:latest
