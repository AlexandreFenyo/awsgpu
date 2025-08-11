#!/bin/zsh

ssh root@$(./scripts/get-ip.zsh | tail -1 | cut -f4) -i $HOME/.ssh/fenyo-aws.pem -g -L 7860:127.0.0.1:7860 'echo http://127.0.0.1:7860; sleep 10000'


