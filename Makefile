
all:
	@cat Makefile

build:
	@docker build -t fenyoa/rag -f docker/Dockerfile .

run:
	@docker run -d --name rag --rm -p 8123:80 fenyoa/rag

run-interactive:
	@docker run --name rag --rm -t -i -p 8123:80 -v /mnt/c/Alex/git/awsgpu/docker/tst.cgi:/usr/lib/cgi-bin/tst.cgi fenyoa/rag

shell:
	@docker exec -t -i rag zsh

stop:
	-@docker stop rag

rm:
	-@docker rm rag

stop-rm: stop rm

rmi:
	@docker rmi fenyoa/rag
