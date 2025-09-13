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

ssh $IP -i $HOME/.ssh/fenyo-aws.pem -l root 'mkdir -p /home/fenyo/.ssh ; cp /root/.ssh/authorized_keys /home/fenyo/.ssh ; chown -R fenyo.fenyo /home/fenyo/.ssh ; chmod 700 /home/fenyo/.ssh ; chmod 600 /home/fenyo/.ssh/authorized_keys'

ssh $IP -i $HOME/.ssh/fenyo-aws.pem -l root 'curl -fsSL https://ollama.com/install.sh | sh'

ssh $IP -i $HOME/.ssh/fenyo-aws.pem -l root 'systemctl stop ollama'
ssh $IP -i $HOME/.ssh/fenyo-aws.pem -l root 'parted -s /dev/nvme1n1 mklabel gpt mkpart primary ext4 1MiB 100% ; partprobe /dev/nvme1n1 ; mkfs.ext4 -L data /dev/nvme1n1p1 ; mkdir /space ; mount /dev/nvme1n1p1 /space ; mv /usr/share/ollama /space ; ln -s /space/ollama /usr/share'
ssh $IP -i $HOME/.ssh/fenyo-aws.pem -l root 'systemctl start ollama'

#ssh $IP -i $HOME/.ssh/fenyo-aws.pem -l root 'ollama pull gpt-oss:120b'
#ssh $IP -i $HOME/.ssh/fenyo-aws.pem -l root 'ollama pull codestral:22b'

exit 0

ssh $IP -i $HOME/.ssh/fenyo-aws.pem -l fenyo 'rm -rf stable-diffusion-webui ; git clone https://github.com/AUTOMATIC1111/stable-diffusion-webui.git'
ssh $IP -i $HOME/.ssh/fenyo-aws.pem -l fenyo 'cd stable-diffusion-webui ; nohup ./webui.sh > webui.sh.log 2>&1 &'
ssh $IP -i $HOME/.ssh/fenyo-aws.pem -l fenyo 'wget https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors ; mv sd_xl_base_1.0.safetensors stable-diffusion-webui/models/Stable-diffusion'

