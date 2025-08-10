#!/bin/zsh

./scripts/get-ip.zsh | tail -1 | cut -f4 | read IP

echo $IP
ssh $IP -i $HOME/.ssh/fenyo-aws.pem -l ubuntu -o StrictHostKeyChecking=no 'sudo su -c "apt update -y"'
ssh $IP -i $HOME/.ssh/fenyo-aws.pem -l ubuntu -o StrictHostKeyChecking=no 'sudo su -c "apt upgrade -y"'
ssh $IP -i $HOME/.ssh/fenyo-aws.pem -l ubuntu -o StrictHostKeyChecking=no 'sudo su -c "sed -i s/^.*ssh-rsa/ssh-rsa/ /root/.ssh/authorized_keys"'

#ssh $IP -i $HOME/.ssh/fenyo-aws.pem -l root id

ssh $IP -i $HOME/.ssh/fenyo-aws.pem -l root 'apt install -y zsh'

ssh $IP -i $HOME/.ssh/fenyo-aws.pem -l root 'deluser fenyo'
yes '' | ssh $IP -i $HOME/.ssh/fenyo-aws.pem -l root 'adduser --disabled-password --shell /bin/zsh fenyo'
ssh $IP -i $HOME/.ssh/fenyo-aws.pem -l root 'touch /home/fenyo/.zshrc ; chown fenyo.fenyo /home/fenyo/.zshrc'

