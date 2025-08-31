#!/bin/zsh
echo Content-type: text/html
echo
date
cd /var/www
source $HOME/.zshrc
./scripts/launch-pipeline-advanced.sh 2>&1
