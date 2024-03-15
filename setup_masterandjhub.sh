# Aaron Visser - Mar 15 2024
# adjusted documentation to setup a development (second) cluster
# This was originally in a script to be run all at once, but I've never been able to do that, and just run things step by step

# Note: some of the components (especially the old versions of Kubernetes we are using don't seem to be hosted anymore? To investigate

# official upgrade guide from Kubernetes 1.23 to 1.24 here https://v1-24.docs.kubernetes.io/docs/tasks/administer-cluster/kubeadm/kubeadm-upgrade/
# docker engine support removed in 1.24? https://kubernetes.io/blog/2022/03/31/ready-for-dockershim-removal/
# https://www.binwang.me/2023-05-22-Upgrade-Kubernetes-from-1.23-to-1.24.html



# AV - old documentation, note the path, this is the original L1nna github
# install driver first, if this is a gpu node: 
# curl https://raw.githubusercontent.com/L1NNA/L1NNA-peppapig/master/setup_driver.sh | bash
# then:
# curl https://raw.githubusercontent.com/L1NNA/L1NNA-peppapig/master/setup_master.sh | bash


# if existing master, you need to basically reset it from scratch. *****CAREFUL, THIS WILL REMOVE EVERYTHING *******
# I've commented it out because it's such a huge operation, it will ask you to verify.
####### sudo kubeadm reset


# AV - google changed where it was hosting repos
##sudo bash -c 'apt-get update && apt-get install -y apt-transport-https
##curl -s https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key add -
##cat <<EOF >/etc/apt/sources.list.d/kubernetes.list
##deb http://apt.kubernetes.io/ kubernetes-xenial main
##EOF
##chmod 644 /etc/apt/sources.list.d/kubernetes.list
##apt-get update'


# get the public signing key for the Kubernetes repo, the version doesn't matter in the url
# https://kubernetes.io/blog/2023/08/15/pkgs-k8s-io-introduction/
sudo apt-get update && apt-get install -y apt-transport-https
sudo curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.28/deb/Release.key | sudo gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg

# in the next line, see the major version you want to get. The cluster as of Mar 2024 was at 1.23.9, but 1.23 is no longer hosted by google, so we have to go to 1.24
# Google's latest is 1.29, so we have some work to do.
sudo echo "deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.24/deb/ /" | sudo tee /etc/apt/sources.list.d/kubernetes.list
sudo chmod 644 /etc/apt/sources.list.d/kubernetes.list



# disable swap on the master node (sorry!, kube requires, supposing kub is the only thing we run on the server)
sudo swapoff -a  
sudo sed -i '/ swap / s/^/#/' /etc/fstab

# AV - k8s 1.23 required a older version of docker, make sure you don't install the latest
# This will have to get changed
#sudo apt-get install -y --allow-unauthenticated docker.io
apt-get install -y --allow-unauthenticated docker.io='20.10.21-0ubuntu1~20.04.2'


# AV - this has changed in recent releases see https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html
# nvidia-docke has been deprecated https://github.com/NVIDIA/nvidia-docker?tab=readme-ov-file
# distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
# for 20.04 LTS 
# see https://github.com/NVIDIA/nvidia-docker/issues/1204
distribution=ubuntu19.10
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list

sudo apt-get update && sudo apt-get install -y nvidia-docker2

# AV - specifically mention versions because this is the version the main cluster is on
# AV - 1.23 is no longer hosted, existing cluster nodes will have 1.23 because they are cached, but new baremetal/vms won't be able to use it

# existing nodes
sudo apt-mark unhold kubelet kubeadm kubectl
sudo apt-get install -y --allow-unauthenticated  kubelet='1.23.9-00' kubectl='1.23.9-00' kubeadm='1.23.9-00' kubernetes-cni
sudo apt-mark hold kubelet kubeadm kubectl

#new nodes with minor version specified, major version set in sources.list.d
sudo apt-mark unhold kubelet kubeadm kubectl
sudo apt-get install -y --allow-unauthenticated  kubelet='1.24.0-2.1' kubectl='1.24.0-2.1' kubeadm='1.24.0-2.1' kubernetes-cni
sudo apt-mark hold kubelet kubeadm kubectl

#new nodes, latest minor version, major version set in sources.list.d
sudo apt-mark unhold kubelet kubeadm kubectl
sudo apt-get install -y --allow-unauthenticated  kubelet kubectl kubeadm kubernetes-cni
sudo apt-mark hold kubelet kubeadm kubectl


# fix docker cgroup: https://github.com/kubernetes/kubernetes/issues/43805#issuecomment-907734385
# https://stackoverflow.com/questions/43794169/docker-change-cgroup-driver-to-systemd
sudo curl https://raw.githubusercontent.com/L1NNA/L1NNA-peppapig/master/deamon.json > /etc/docker/daemon.json 
sudo systemctl restart docker
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

# enable pod deployment on master node: [optional, but needed for our setup]
# for multi-node setup, we cannot use this otherwise the other nodes cannot join
kubectl taint nodes --all node-role.kubernetes.io/master-

# install helm:
curl https://raw.githubusercontent.com/kubernetes/helm/master/scripts/get | bash
kubectl --namespace kube-system create serviceaccount tiller
kubectl create clusterrolebinding tiller --clusterrole cluster-admin --serviceaccount=kube-system:tiller
helm init --service-account tiller --history-max 100 --wait --upgrade
helm version
# the client/serve version may be unsynced. 'upgrade' to remove such possibility

# install nvidia device plugin
# if the master node doesn't have a gpu, don't need this
kubectl create -f https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/v0.6.0/nvidia-device-plugin.yml


# AV - didn't install dashboard atm.
# AV - BEGIN DID NOT INSTALL
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

# AV - didn't install this
# install prometheus+grafana for monitoring
kubectl apply --filename https://raw.githubusercontent.com/giantswarm/prometheus/master/manifests-all.yaml
# visit: kubectl port-forward --namespace monitoring service/grafana 8001:3000 
# with ssh tunnel 8001
# default usr: admin/admin
# to remove: kubectl delete namespace monitoring

# AV - END DID NOT INSTALL


# list all pods
kubectl get pods --all-namespaces


# done
echo 'finished. you need to manually add export KUBECONFIG=$HOME/admin.conf to your .bashrc to use kubectl'

############ SETUP JHUB
# create storage class

cd /home/ding/config/Lobot
wget https://raw.githubusercontent.com/Queens-School-of-Computing/Lobot/dev/storageclass.yaml
/home/ding/config/Lobot/kubectl create -f storageclass.yaml

cd /home/ding/config
wget https://raw.githubusercontent.com/Queens-School-of-Computing/Lobot/dev/config_dev.yaml.bk
wget https://raw.githubusercontent.com/Queens-School-of-Computing/Lobot/dev/config_dev_hubonly.yaml.bk

# get OAUTH clientID and clientsecret from github and replace in config_dev.yaml.bk and config_dev_hubonly.bk
# https://github.com/organizations/Queens-School-of-Computing/settings/applications
cp config_dev.yaml.bk config_dev.yaml
cp config_dev_hubonly.bk config_dev_hubonly.yaml
# edit clientid and clientsecret


# setup hooks for slack (we don't do this)
# wget https://raw.githubusercontent.com/L1NNA/L1NNA-peppapig/master/config.yaml
# sed -i -e 's/peppa-tkn/'$(openssl rand -hex 32)'/g' ./config.yaml
# read -p "Enter slack notification web nook: " SLACK_WEBHOOK
# sed -i -e 's,peppa-webhook,'$SLACK_WEBHOOK',g' ./config.yaml

# add jupyterhub
helm repo add jupyterhub https://jupyterhub.github.io/helm-chart/
helm repo update

# setup jhub
# in the config file it defines the hub image to use, and the webfiles for the launcher, they are pulled from git in the hub_templates_bt4 folder
RELEASE=jhub ;NAMESPACE=jhub ; helm upgrade --install $RELEASE jupyterhub/jupyterhub --namespace $NAMESPACE --version=0.9.0   --values config_dev_hubonly.yaml

# once you have another worker node with a gpu and are ready to use the config with images with gpu and gpu driver
# RELEASE=jhub ;NAMESPACE=jhub ;  helm upgrade $RELEASE jupyterhub/jupyterhub --version=0.9.0  --values config_dev.yaml --recreate-pods

# to remove install/cancel
# helm delete $RELEASE --purge --no-hooks
# docs for config: https://jupyterhub-kubespawner.readthedocs.io/en/latest/spawner.html

# install longhorn v1.2.3
apt-get install open-iscsi
helm repo add longhorn https://charts.longhorn.io
# the version of longhorn we are using is 1.2.3, you have to specifiy the version in the helm install command
# https://stackoverflow.com/questions/51200917/how-to-install-a-specific-chart-version
helm install longhorn/longhorn --name longhorn --namespace longhorn-system --set service.ui.nodePort=30001 --set service.ui.type=NodePort --version v1.2.3


# edit nginx
ngix server block for reverse proxy:
```
# vim /etc/nginx/sites-available/yourapp.com
server {
    listen 80;
    server_name yourapp.com; # or server_name subdomain.yourapp.com;

    location / {
        proxy_pass http://localhost:8888;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Host $http_host;
        proxy_set_header X-NginX-Proxy true;
        # https://github.com/jupyterhub/jupyterhub/issues/2284
        proxy_set_header X-Scheme $scheme;

        # Enables WS support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_redirect off;
    }
}
# sudo ln -s /etc/nginx/sites-available/your_domain /etc/nginx/sites-enabled/
```

https: https://www.digitalocean.com/community/tutorials/how-to-secure-nginx-with-let-s-encrypt-on-ubuntu-20-04

```
# for default redict:
server {
        listen 80 default_server;
        listen [::]:80 default_server;
        server_name _;
        return 301 https://p.l1nna.com;
}
```
