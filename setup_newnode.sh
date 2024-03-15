
## Adding a new node (storage, compute or gpu) to the department's cluster that's been designed by Prof Steven Ding is fairly straightforward. It certainly isn't 2 lines like Steven said, but it's close.

## 1. Install OS. It doesn't have to be bare metal, it could be a VM. To date, we've only used Ubuntu 20.04 and 22.04.

## 2. Setup Nvidia Drivers. Steven says that any version should work. All existing nodes in the stack are using version 4.70, the current release from Nvidia is 5.15 (for the A40 series).
## * You can check the current version of the nvidia driver on their website.
## * In Ubuntu, you can check the available versions to install by typing the command
# sudo ubuntu-drivers list
## * And then you can install the one you want by  (I showed 470 because that's the one that the stack is mostly using, as of Nov 4 2022, the current is 515)
## sudo apt install nvidia-driver-470

# 3. Now you have to install the prerequisites like kubernates and docker.


sudo bash -c 'apt-get update && apt-get install -y apt-transport-https
curl -s https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key add -
cat <<EOF >/etc/apt/sources.list.d/kubernetes.list
deb http://apt.kubernetes.io/ kubernetes-xenial main
EOF
apt-get update'

sudo chmod 644 /etc/apt/sources.list.d/kubernetes.list
sudo apt-get update

# disable swap on the master node (sorry!, kube requires, supposing kub is the only thing we run on the server)
sudo swapoff -a  
sudo sed -i '/ swap / s/^/#/' /etc/fstab

sudo apt-get install -y --allow-unauthenticated docker.io
 distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
# for 20.04 LTS 
# see https://github.com/NVIDIA/nvidia-docker/issues/1204
# distribution=ubuntu19.10
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list

sudo apt-get update && sudo apt-get install -y nvidia-docker2

# The current stack needs version 1.23.3--00
sudo apt-get install -y --allow-unauthenticated kubelet=1.23.3-00 kubeadm=1.23.3-00 kubectl=1.23.3-00 kubernetes-cni
sudo apt-mark hold kubelet kubeadm kubectl

sudo groupadd docker
$user=croot
sudo usermod -aG docker $user

sudo systemctl enable docker && sudo systemctl start docker
sudo systemctl enable kubelet && sudo systemctl start kubelet

# fix docker cgroup: https://github.com/kubernetes/kubernetes/issues/43805#issuecomment-907734385
# https://stackoverflow.com/questions/43794169/docker-change-cgroup-driver-to-systemd
sudo curl https://raw.githubusercontent.com/L1NNA/L1NNA-peppapig/master/deamon.json > /etc/docker/daemon.json 
sudo systemctl restart docker

# install iscsi
sudo apt-get install open-iscsi

# new disk:
sudo lsblk -o NAME,FSTYPE,SIZE,MOUNTPOINT,LABEl
sudo parted -s --align optimal /dev/sdb -- mklabel gpt  mkpart primary ext4 0% 100%
sudo mkfs.ext4 /dev/sdb1
sudo mkdir -p /mnt/sdb/
# get UUID
 sudo blkid

sudo vim /etc/fstab
# add: UUID=81b527a6-94c7-4663-8c58-d9ff1f74bd47 /mnt/sdb ext4 defaults 0 0
sudo mount -a

# reboot



#################
# now on the master node (lobot), run the following command in the ding user
kubeadm token create --print-join-command

# a command with parameters will be printed, copy that and run it on the new node
# it will look something like
# kubeadm join 130.15.15.128:6443 --token 80e3qa.1xwl44yql5l08t7c --discovery-token-ca-cert-hash sha256:6d61b815f83bfb8970602729c3ba9ebabc403d8167eb405bb0574f84ed269641 
# once you run that command, hopefully it will join.
# now tags have to be added to the new node. Do this on the master node lobot
# you can get the list of nodes with
kubectl get node --all-namespaces

# and you can show details about the node
kubectl describe node NODENAMEHERE

# you can see the pod status on the node
kubectl get pod -o wide --all-namespaces | grep NODENAMEHERE

# and logs on the individual pods  (in the below example pod and pod instance are longhorn-system and longhorn-manager-1h542)
kubectl logs -n PODNAME PODINSTANCE

# add lab tag
kubectl label nodes NODENAMEHERE lab=devlab

# add gpu tag, there is a script here that you can look at how it's automatically done.
# https://github.com/Queens-School-of-Computing/Lobot/blob/master/setup_master.sh#L88
kubectl label nodes $nodename hardware-type=NVIDIAGPU
# find the PODNAME name of the nvidia daemon, look for the pod name
kubectl get pod -A -o wide | grep nvidia | grep $nodename

# get the product name of the GPUs
gpu=$(kubectl exec -it -n kube-system NVIDIAPODNAME — nvidia-smi -q | grep ‘Product Name’ | head -n 1)
#label=$(echo $gpu | cut -d ‘:’ -f 2 | tr -d ‘\r’ | tr ” ” “-” )
# seems to add a – at the start?
label=NVIDIA-RTX-A5000
#kubectl label nodes ${nodename} nvidia.com/brand=NVIDIA-A40
kubectl label nodes ${nodename} “nvidia.com/brand=${label}“

# Now reboot your new node and check to see if it's joined successfully! Enjoy!
