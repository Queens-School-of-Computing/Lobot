#!/bin/sh
# install driver first, if this is a gpu node: 
# curl https://raw.githubusercontent.com/L1NNA/L1NNA-peppapig/master/setup_driver.sh | bash
# then:
# curl https://raw.githubusercontent.com/L1NNA/L1NNA-peppapig/master/setup_master.sh | bash

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
# distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
# for 20.04 LTS 
# see https://github.com/NVIDIA/nvidia-docker/issues/1204
distribution=ubuntu19.10
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list

sudo apt-get update && sudo apt-get install -y nvidia-docker2

sudo apt-get install -y --allow-unauthenticated kubelet kubeadm kubectl kubernetes-cni
sudo apt-mark hold kubelet kubeadm kubectl

sudo groupadd docker
sudo usermod -aG docker $USER

sudo systemctl enable docker && sudo systemctl start docker
sudo systemctl enable kubelet && sudo systemctl start kubelet

# fix docker cgroup: https://github.com/kubernetes/kubernetes/issues/43805#issuecomment-907734385
# https://stackoverflow.com/questions/43794169/docker-change-cgroup-driver-to-systemd
sudo curl https://raw.githubusercontent.com/L1NNA/L1NNA-peppapig/master/deamon.json > /etc/docker/daemon.json 
sudo systemctl restart docker
# sudo kubeadm init --apiserver-advertise-address=$1
sudo kubeadm init --pod-network-cidr=10.244.0.0/16
# - kubeadm docs
# There are pod network implementations where the master also plays a role in allocating a set of network address space for each node. 
# When using flannel as the pod network (described in step 3), specify --pod-network-cidr=10.244.0.0/16. 
# This is not required for any other networks besides Flannel.


sudo cp /etc/kubernetes/admin.conf $HOME/
sudo chown $(id -u):$(id -g) $HOME/admin.conf
export KUBECONFIG=$HOME/admin.conf

# fix cid error https://github.com/kubernetes/kubernetes/issues/48798#issuecomment-630397355
kubectl apply -f https://raw.githubusercontent.com/coreos/flannel/master/Documentation/kube-flannel.yml
sudo systemctl restart kubelet

# enalbe pod deployment on master node: [optional, but needed for our setup]
# for multi-node setup, we cannot use this otherwise the other nodes cannot join
kubectl taint nodes --all node-role.kubernetes.io/master-

# install helm:
curl https://raw.githubusercontent.com/kubernetes/helm/master/scripts/get | bash
kubectl --namespace kube-system create serviceaccount tiller
kubectl create clusterrolebinding tiller --clusterrole cluster-admin --serviceaccount=kube-system:tiller
helm init --service-account tiller --history-max 100 --wait --upgrade
helm version
# the client/serve version may be unsynced. 'upgrade' to remove such possibility

# set docker default runtime to nvidia-runtime (on gpu node)
# sudo apt-get install -y jq
# jq '."default-runtime"="nvidia"' /etc/docker/daemon.json | sudo tee /etc/docker/daemon.json

# for ubuntu 20.04
sudo curl https://raw.githubusercontent.com/L1NNA/L1NNA-peppapig/master/deamon.json > /etc/docker/daemon.json 
sudo systemctl restart docker
export KUBECONFIG=$HOME/admin.conf

# install nvidia device plugin
kubectl create -f https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/v0.6.0/nvidia-device-plugin.yml

# label node with GPU device
sudo docker info | grep nvidia && kubectl label nodes `kubectl get nodes -o=custom-columns=NAME:.metadata.name | sed -n '1!p'` hardware-type=NVIDIAGPU

# label node with specific GPU model
for pod in `kubectl get pods -n kube-system -o=custom-columns=NAME:.metadata.name | grep nvidia-device-plugin-daemonset`; do
	gpu=$(kubectl exec -it -n kube-system $pod -- nvidia-smi -q | \
		grep 'Product Name' | head -n 1)

	label=$(echo $gpu | cut -d ':' -f 2 | xargs | tr '\r' '' | xargs )
	label=$(echo ${label// /-})

	node=$(kubectl get pod -n kube-system $pod \
		-o=custom-columns=NODE:.spec.nodeName | tail -n 1)

	kubectl label nodes ${node} "nvidia.com/brand=${label}"
	kubectl label nodes ${node} hardware-type=NVIDIAGPU
done


# test run:
kubectl run gpu-test --rm -t -i --restart=Never --image=nvidia/cuda --limits=nvidia.com/gpu=1 nvidia-smi

# install dashboard: (added a dashboard serviceaccount to access the cluster)
kubectl apply -f https://raw.githubusercontent.com/kubernetes/dashboard/v2.0.0/aio/deploy/recommended.yaml
kubectl create serviceaccount dashboard -n default
kubectl create clusterrolebinding dashboard-admin -n default --clusterrole=cluster-admin --serviceaccount=default:dashboard
# to get seceret: 
# kubectl get secret $(kubectl get serviceaccount dashboard -o jsonpath="{.secrets[0].name}") -o jsonpath="{.data.token}" | base64 --decode
# visit dashboard you will need: (with ssh tunnel)
# kubectl proxy
# then visit: http://127.0.0.1:8001/api/v1/namespaces/kubernetes-dashboard/services/https:kubernetes-dashboard:/proxy/#/overview?namespace=default
# to remove: kubectl delete namespace kubernetes-dashboard


# install prometheus+grafana for monitoring
kubectl apply --filename https://raw.githubusercontent.com/giantswarm/prometheus/master/manifests-all.yaml
# visit: kubectl port-forward --namespace monitoring service/grafana 8001:3000 
# with ssh tunnel 8001
# default usr: admin/admin
# to remove: kubectl delete namespace monitoring

# list all pods
kubectl get pods --all-namespaces


# done
echo 'finished. you need to manually add export KUBECONFIG=$HOME/admin.conf to your .bashrc to use kubectl'

# setup roles on master: kubectl create clusterrolebinding cluster-system-anonymons --clusterrole cluster-admin --user system:anonymous
# worker node joining: https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/create-cluster-kubeadm/#join-nodes
# https://www.serverlab.ca/tutorials/containers/kubernetes/how-to-add-workers-to-kubernetes-clusters/

