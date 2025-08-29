
FROM ubuntu:24.04
LABEL maintainer="alex@fenyo.net"
ENV TERM=vt100
ENV LANG=C.UTF-8
ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends software-properties-common ca-certificates curl wget iproute2 net-tools less zsh && add-apt-repository ppa:deadsnakes/ppa -y && apt-get update && apt-get install -y --no-install-recommends python3.13 python3.13-venv python3-pip && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.13 1
RUN curl -sSL https://install.python-poetry.org | python3 -
RUN mkdir files
COPY files files
RUN cp files/pyproject.toml files/poetry.toml files/poetry.lock .
RUN ln -s /root/.local/bin/poetry /usr/local/bin
RUN poetry install --no-root
RUN cp -rp files/{scripts,src} .
RUN $(poetry env activate)
