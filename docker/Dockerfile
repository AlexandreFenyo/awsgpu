
FROM ubuntu:24.04
LABEL maintainer="alex@fenyo.net"
ENV TERM=vt100
ENV LANG=C.UTF-8
ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /var/www
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends software-properties-common ca-certificates curl wget iproute2 net-tools less zsh apache2 vim inetutils-telnet inetutils-ping npm nodejs ts-node dnsutils inkscape imagemagick && add-apt-repository ppa:deadsnakes/ppa -y && apt-get update && apt-get install -y --no-install-recommends python3.13 python3.13-venv python3-pip dnsutils && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.13 1
RUN chsh -s /bin/zsh
RUN echo "alias ls='ls -F'" >> $HOME/.zshrc
COPY pyproject.toml poetry.toml poetry.lock package.json package-lock.json .
COPY src src
COPY scripts scripts
RUN chown -R www-data:www-data /var/www
RUN chsh -s /bin/zsh www-data
RUN su www-data -c 'curl -sSL https://install.python-poetry.org | python3 -'
RUN ln -s /var/www/.local/bin/poetry /usr/local/bin
RUN su www-data -c 'poetry install --no-root'
RUN su www-data -c 'echo "$(poetry env activate)" > $HOME/.zshrc'
RUN echo "alias ls='ls -F'" >> /var/www/.zshrc
RUN mkdir -p /var/run/apache2 /var/log/apache2 && chown -R www-data:www-data /var/log/apache2 /var/run
ENV APACHE_RUN_USER=www-data
ENV APACHE_RUN_GROUP=www-data
ENV APACHE_LOG_DIR=/var/log/apache2
ENV APACHE_RUN_DIR=/var/run/apache2
ENV APACHE_PID_FILE=/var/run/apache2/apache2.pid
RUN cp /etc/apache2/mods-available/cgi.load /etc/apache2/mods-enabled
RUN sed -i 's%#Include conf-available/serve-cgi-bin.conf%Include conf-available/serve-cgi-bin.conf%' /etc/apache2/sites-enabled/000-default.conf
COPY docker/tst.cgi /usr/lib/cgi-bin/tst.cgi
COPY docker/ws.cgi /usr/lib/cgi-bin/ws.cgi
RUN chmod +x /usr/lib/cgi-bin/tst.cgi /usr/lib/cgi-bin/ws.cgi
RUN su www-data -c 'npm ci'
EXPOSE 80
CMD ["apache2ctl", "-D", "FOREGROUND"]
