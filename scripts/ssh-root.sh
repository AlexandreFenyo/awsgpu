#!/bin/zsh

ssh root@$(./scripts/get-ip.zsh | tail -1 | cut -f4) -i $HOME/.ssh/fenyo-aws.pem

