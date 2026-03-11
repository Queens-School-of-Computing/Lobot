# Cluster Setup Guide

![](https://raw.githubusercontent.com/Queens-School-of-Computing/Lobot/newcluster/assets/images/newsetupbanner.jpg)

Aaron Visser — Created: April 2025 (original documentation ~2021)\
Updated: March 2026 — two-file config, apply-config.sh, Lobot tools section

Also see: [Helpful Kubernetes Cluster / Lobot Commands](https://newsocdocs.cs.queensu.ca/socdocs.wp/helpful-kubernetes-cluster-lobot-commands/)

---

## Overview

Instructions for setting up a new cluster from scratch or adding new worker nodes
to an existing cluster. Most steps apply to all nodes; control-plane-only steps
are clearly marked.

**Node types:**
- **Control plane** — runs the Kubernetes API server, JupyterHub, nginx. One per cluster.
- **Worker node** — runs user pods. May or may not have GPUs.

---

## Step 1 — Install Ubuntu Server 24.04

Standard Ubuntu Server 24.04 install. No special options required.

> Most commands below should be run as `croot` (or `sudo` where indicated).

---

## Step 2 — NVIDIA Driver (GPU nodes only)

Skip this section for non-GPU nodes.

```bash
# Check what drivers are available
sudo ubuntu-drivers list

# Install the current recommended driver
sudo apt update
sudo apt install nvidia-driver-580-open -y

# Hold the driver version to prevent updates from killing running workloads
sudo apt-mark hold nvidia-driver-580-open
```

If the driver is not in the apt repository, install manually:

```bash
cd /root
sudo wget https://us.download.nvidia.com/tesla/570.133.20/nvidia-driver-local-repo-ubuntu2404-570.133.20_1.0-1_amd64.deb
sudo dpkg -i nvidia-driver-local-repo-ubuntu2404-570.133.20_1.0-1_amd64.deb
sudo cp /var/nvidia-driver-local-repo-ubuntu2404-570.133.20/nvidia-driver-local-BB6607B3-keyring.gpg /usr/share/keyrings/
sudo apt update
sudo apt install nvidia-driver-580-open -y
sudo apt-mark hold nvidia-driver-580-open
```

**If NVIDIA fails to start (e.g. A100 80G cards with dmesg errors):**
Edit `/etc/default/grub` and add kernel flags, then reboot:
```
GRUB_CMDLINE_LINUX_DEFAULT="pci=nocrs pci=realloc=off"
```
Reference: https://support.hpe.com/hpesc/public/docDisplay?docId=a00112218en_us

---

## Step 3 — System Packages and Configuration

```bash
# Disable multipathd (required for Longhorn)
sudo systemctl stop multipathd.socket
sudo systemctl stop multipathd.service
sudo systemctl disable multipathd

# Install required packages
sudo apt install nfs-common ntp fail2ban open-iscsi -y
sudo systemctl status ntp
sudo systemctl status fail2ban
sudo ntpq -p
```

---

## Step 4 — Hostname and /etc/hosts

```bash
# For the control plane, use the FQDN. For worker nodes, short name is fine.
sudo hostnamectl set-hostname hostnamehere
exec bash

# Add all cluster hosts to /etc/hosts
sudo vi /etc/hosts
```

Add the following (search-and-replace `hostnamehere` with the actual hostname):

```
127.0.1.1       hostnamehere.cs.queensu.ca hostnamehere hostnamehere.computing.cs.queensu.ca
130.15.1.7      ad01 ad01.cs.queensu.ca ad01.computing.cs.queensu.ca
130.15.6.201    lobot.cs.queensu.ca lobot
130.15.3.225    lobot-dev.cs.queensu.ca lobot-dev
```

> In vi: `:%s/hostnamehere/newhostname/g`

> **Important:** Put the FQDN before the short name on the `127.0.1.1` line.
> If the short name appears first, `hostname` will return the short name and
> `apply-config.sh` / `sync_groups.sh` cluster detection will break.

---

## Step 5 — Disable Swap

Kubernetes does not support swap. This is not optional.

```bash
sudo swapoff -a
sudo vi /etc/fstab   # comment out the swap line
```

---

## Step 6 — Kernel Parameters

```bash
sudo tee /etc/modules-load.d/containerd.conf <<EOF
overlay
br_netfilter
EOF

sudo modprobe overlay
sudo modprobe br_netfilter

sudo tee /etc/sysctl.d/kubernetes.conf <<EOF
net.bridge.bridge-nf-call-ip6tables = 1
net.bridge.bridge-nf-call-iptables = 1
net.ipv4.ip_forward = 1
EOF

sudo sysctl --system
```

---

## Step 7 — containerd and Docker

```bash
sudo apt-get update
sudo apt-get install ca-certificates curl -y
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Add croot to the docker group
sudo usermod -aG docker $USER

# Configure containerd to use systemd cgroup
containerd config default | sudo tee /etc/containerd/config.toml >/dev/null 2>&1
sudo sed -i 's/SystemdCgroup \= false/SystemdCgroup \= true/g' /etc/containerd/config.toml

sudo systemctl restart containerd.service
sudo systemctl restart docker.service
sudo systemctl enable docker.service
sudo systemctl enable containerd.service
```

---

## Step 8 — Kubernetes Packages

```bash
curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.34/deb/Release.key | \
  sudo gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
sudo chmod 644 /etc/apt/keyrings/kubernetes-apt-keyring.gpg

echo 'deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.34/deb/ /' | \
  sudo tee /etc/apt/sources.list.d/kubernetes.list
sudo chmod 644 /etc/apt/sources.list.d/kubernetes.list

sudo apt update
sudo apt install -y kubelet kubeadm kubectl
sudo apt-mark hold kubelet kubeadm kubectl
```

> To upgrade to a different minor version later, update the version in
> `/etc/apt/sources.list.d/kubernetes.list` before `apt update`.

---

## Step 9 — Worker Node: Join the Cluster

> **Setting up a new control plane?** Skip ahead to [Step 12](#step-12--initialize-the-control-plane)
> and return here once the control plane is running and worker nodes are ready to join.

**Wait until the control plane is fully set up before running this.**

Get the join command from the control plane:

```bash
kubeadm token create --print-join-command
```

Run the output of that command on the new worker node.

---

## Step 10 — Worker Node: Labels and Configuration

Run these on the **control plane** after the node joins.

```bash
nodename=NODENAMEHERE

# Verify the node joined
kubectl describe node $nodename
kubectl get pod -o wide --all-namespaces | grep $nodename

# Add lab label (used by resource collector for grouping)
kubectl label nodes $nodename lab=lobot_a16

# Add GPU labels
kubectl label nodes $nodename hardware-type=NVIDIAGPU

# Set the NVIDIA brand label (pick the correct one)
# label=NVIDIA-A16
# label=NVIDIA-RTX-PRO-6000-Blackwell-Server-Edition
# label=NVIDIA-H100-NVL
# label=NVIDIA-A40
# label=NVIDIA-RTX-A5000
# label=NVIDIA-RTX-A6000
# label=NVIDIA-A100-80GB-PCIe
label=NVIDIA-A16
kubectl label nodes $nodename nvidia.com/brand=$label

# If time slicing is needed for this node (e.g. A16 — see Extras section)
kubectl label node $nodename nvidia.com/device-plugin.config=a16
```

---

## Step 11 — Storage Setup (Worker Nodes)

### Single drive

```bash
sudo lsblk -o NAME,FSTYPE,SIZE,MOUNTPOINT,LABEL

sudo parted -s --align optimal /dev/sdb -- mklabel gpt mkpart primary ext4 0% 100%
sudo mkfs.ext4 /dev/sdb1
sudo mkdir -p /mnt/sdb/

# Get UUID
sudo blkid

sudo vim /etc/fstab
# Add: UUID=xxxx-xxxx /mnt/sdb ext4 defaults 0 0

sudo mount -a
```

### Software RAID 5

```bash
sudo mdadm --create --verbose /dev/md0 --level=5 --raid-devices=4 \
  /dev/sda1 /dev/sdb1 /dev/sdc1 /dev/sdd1

sudo mkfs.ext4 /dev/md0
sudo mkdir -p /media/dataraid5/
# Add to /etc/fstab as above
```

---

## ─── CONTROL PLANE ONLY ───────────────────────────────────────────────────

## Step 12 — Initialize the Control Plane

```bash
sudo kubeadm init --pod-network-cidr=10.244.0.0/16 \
  --control-plane-endpoint=lobot-dev.cs.queensu.ca

mkdir -p $HOME/.kube
sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
sudo chown $(id -u):$(id -g) $HOME/.kube/config

# Deploy Flannel CNI
kubectl apply -f https://github.com/flannel-io/flannel/releases/latest/download/kube-flannel.yml
sudo systemctl restart kubelet
```

---

## Step 13 — Helm

```bash
curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/master/scripts/get-helm-3 \
  && chmod 700 get_helm.sh \
  && ./get_helm.sh
```

---

## Step 14 — NVIDIA GPU Operator

```bash
kubectl create ns gpu-operator
kubectl label --overwrite ns gpu-operator pod-security.kubernetes.io/enforce=privileged

helm repo add nvidia https://helm.ngc.nvidia.com/nvidia && helm repo update

# Install GPU operator without the driver (drivers are installed on the host)
helm install --wait --generate-name \
  -n gpu-operator --create-namespace \
  nvidia/gpu-operator \
  --version=v25.10.0 --set driver.enabled=false

# To remove:
# helm delete -n gpu-operator $(helm list -n gpu-operator | grep gpu-operator | awk '{print $1}')
```

---

## Step 15 — Clone Lobot Repo

```bash
cd /opt
sudo git clone https://github.com/Queens-School-of-Computing/Lobot.git -b newcluster
sudo chown -R croot:croot /opt/Lobot

# Install Python dependencies needed by Lobot tools
sudo apt install python3-pip -y
pip3 install requests pyyaml
```

---

## Step 16 — JupyterHub Config (First Time)

The JupyterHub config uses two files:
- `config.yaml` — shared base config with secrets
- `config-env.yaml` — environment-specific overrides (image tag, URLs, announcement key)

`apply-config.sh` generates both files. But on **first-time setup** you need to
seed `config.yaml` with the real secrets since the template has `xxx` placeholders.

> **Before starting:** retrieve the four secrets from **Passbolt → "Lobot"**:
> - `proxy.secretToken` — or generate a new one: `openssl rand -hex 32`
> - `hub.services.group-manager.api_token`
> - `hub.config.GitHubOAuthenticator.client_id`
> - `hub.config.GitHubOAuthenticator.client_secret`

```bash
cd /opt/Lobot

# Copy the base template
cp config.yaml.bk config.yaml

# Replace all four xxx placeholders with the values from Passbolt
vi config.yaml

# Generate config-env.yaml (auto-detects prod vs dev from hostname)
# Also re-applies secrets to the latest template from GitHub going forward
sudo bash tools/apply-config.sh

# Review both output files
# config.yaml      — base config with secrets
# config-env.yaml  — env overrides for this cluster
```

> For all future config updates, just run `sudo bash /opt/Lobot/tools/apply-config.sh`.
> See [apply-config.md](apply-config.md) for full documentation.

---

## Step 17 — Longhorn

```bash
apt-get install open-iscsi
helm repo add longhorn https://charts.longhorn.io
helm repo update

# Install Longhorn v1.9.2
helm install longhorn longhorn/longhorn \
  --namespace longhorn-system \
  --set service.ui.nodePort=30001 \
  --set service.ui.type=NodePort \
  --create-namespace \
  --version v1.9.2

# Restrict direct port access (proxy via nginx with htpasswd instead)
sudo iptables -t raw -A PREROUTING -p tcp --dport 30001 ! -s 127.0.0.1 -j DROP

# Make iptables rules persistent
sudo apt install iptables-persistent
sudo netfilter-persistent save
```

**Longhorn Settings (via UI after install):**
- Change storage overprovisioning to **100%** (default 200% is dangerous — has caused disks to fill and corrupt)
- BackupTarget: `s3://longhornbackup@us-east-1/`
- BackupTargetCredentialSecret: `minio-secret`

```bash
# Copy minio secret from innovate
scp aaron@innovate.cs.queensu.ca:miniosecret.yaml ./
kubectl apply -f miniosecret.yaml
```

**Upgrading Longhorn:**
You can only upgrade one minor version at a time (1.8.x → 1.9.x, not 1.6.x → 1.9.x).
Review patch notes before upgrading: https://longhorn.io/docs/1.9.2/deploy/upgrade/longhorn-manager/

```bash
helm upgrade longhorn longhorn/longhorn --namespace longhorn-system --version 1.9.2
```

---

## Step 18 — Deploy JupyterHub

```bash
helm repo add jupyterhub https://jupyterhub.github.io/helm-chart/
helm repo update

kubectl create namespace jhub

# Initial deploy: hub-only config (no user image, confirms the hub comes up cleanly)
RELEASE=jhub; NAMESPACE=jhub
helm upgrade --install $RELEASE jupyterhub/jupyterhub \
  --namespace $NAMESPACE \
  --version=4.0.0-beta.2 \
  --values /opt/Lobot/config_hubonly.yaml.bk \
  --timeout=60m

# Once GPU worker nodes are ready, upgrade to the full config (both values files required)
RELEASE=jhub; NAMESPACE=jhub
helm upgrade --cleanup-on-fail $RELEASE jupyterhub/jupyterhub \
  --namespace $NAMESPACE \
  --version=4.0.0-beta.2 \
  --values /opt/Lobot/config.yaml \
  --values /opt/Lobot/config-env.yaml \
  --timeout=60m
```

---

## Step 19 — Post-JupyterHub: Lobot Tools

### Create the group-manager API token secret

Required by `sync_groups.sh` to authenticate with the JupyterHub API.
The token value must match `hub.services.group-manager.api_token` in `config.yaml`.

```bash
kubectl create secret generic group-manager-token -n jhub \
  --from-literal=JUPYTERHUB_API_TOKEN=<api-token-from-passbolt>
```

### Sync JupyterHub groups

Run this after JupyterHub is up, and any time `group-roles.yaml` is updated.

```bash
cd /opt/Lobot/tools

export API_URL="https://$(hostname)/hub/api"
export GROUP_ROLES_URL=$(python3 -c \
  "import yaml; print(yaml.safe_load(open('/opt/Lobot/config-env.yaml'))['hub']['extraEnv']['LOBOT_GROUP_ROLES_URL'])")

./sync_groups.sh --dry-run --verbose   # preview
./sync_groups.sh                        # apply
```

See [sync_groups.md](sync_groups.md) for full documentation.

### Pre-pull the singleuser image

Large images (10GB+) should be pre-pulled to all nodes before deploying with the full
config to avoid Helm timeout or pod scheduling delays.

```bash
IMAGE_TAG=$(python3 -c \
  "import yaml; print(yaml.safe_load(open('/opt/Lobot/config-env.yaml'))['singleuser']['image']['tag'])")
IMAGE="queensschoolofcomputingdocker/gpu-jupyter-latest:${IMAGE_TAG}"

cd /opt/Lobot/tools
./image-pull.sh -i "$IMAGE" --dry-run   # check which nodes need the pull
./image-pull.sh -i "$IMAGE"             # pull to all nodes
```

See [IMAGE-MANAGEMENT.md](IMAGE-MANAGEMENT.md) for full documentation.

### Resource collector (cluster status page)

The resource collector publishes live CPU/GPU/memory availability to `/allocationstatus`
(served by nginx). It requires the `kubectl-view-allocations` binary.

```bash
# Install Python dependency
pip3 install pandas

# Download kubectl-view-allocations
# Find latest release: https://github.com/davidB/kubectl-view-allocations/releases
wget https://github.com/davidB/kubectl-view-allocations/releases/latest/download/kubectl-view-allocations_linux_amd64 \
  -O /opt/Lobot/kubectl-view-allocations
chmod +x /opt/Lobot/kubectl-view-allocations

# Install and start as a systemd service
sudo cp /opt/Lobot/tools/resource-collector.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now resource-collector

# Verify it's running
sudo systemctl status resource-collector

# Follow logs
sudo journalctl -u resource-collector -f
```

---

## Step 20 — nginx

```bash
sudo apt install nginx
```

Create the server block (replace `lobot-dev.cs.queensu.ca` with the actual hostname):

```nginx
# /etc/nginx/sites-available/lobot-dev.cs.queensu.ca

server {
    server_name lobot-dev.cs.queensu.ca;

    location / {
        proxy_pass http://localhost:30080;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Host $http_host;
        proxy_set_header X-NginX-Proxy true;
        proxy_set_header X-Scheme $scheme;

        # Required for real-time SSE (spawn progress log) and WebSocket support
        proxy_buffering off;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        proxy_redirect off;
        client_max_body_size 500M;
    }

    location /longhorn/ {
        allow 130.15.1.0/24;
        allow 130.15.2.0/24;
        allow 130.15.3.0/24;
        allow 130.15.4.0/24;
        allow 130.15.5.0/24;
        allow 130.15.6.0/24;
        allow 130.15.7.0/24;
        deny all;

        auth_basic "Longhorn Admin";
        auth_basic_user_file /etc/nginx/.htpasswd-longhorn;

        proxy_pass http://127.0.0.1:30001/;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Prefix /longhorn;

        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_redirect off;
    }

    location = /longhorn {
        return 301 /longhorn/;
    }

    location /status-embed {
        alias /opt/Lobot/status-embed;
        try_files $uri /status-embed.html =404;
        allow 130.15.1.13;
        allow 130.15.1.50;
        deny all;
    }

    location /allocationstatus {
        alias /opt/Lobot/resource_collector_data;
        try_files $uri /index.html =404;
    }

    location /assets {
        alias /opt/Lobot/assets;
    }

    # Hub down (upgrade/restart) → friendly maintenance page
    error_page 502 503 504 /maintenance.html;
    location = /maintenance.html {
        root /opt/Lobot/assets;
        internal;
    }

    error_page 404 500 /50x.html;
    location = /50x.html {
        root /var/www/html;
        internal;
    }

    client_max_body_size 500M;

    listen 443 ssl; # managed by Certbot
    ssl_certificate /etc/letsencrypt/live/lobot-dev.cs.queensu.ca/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/lobot-dev.cs.queensu.ca/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
}

server {
    if ($host = lobot-dev.cs.queensu.ca) {
        return 301 https://$host$request_uri;
    }
    server_name lobot-dev.cs.queensu.ca;
    listen 80;
    return 404;
}
```

```bash
# Enable the site
sudo ln -s /etc/nginx/sites-available/lobot-dev.cs.queensu.ca /etc/nginx/sites-enabled/

# Set up htpasswd files for protected pages
sudo htpasswd -c /etc/nginx/.htpasswd lobotstatus         # password in Passbolt
sudo htpasswd -c /etc/nginx/.htpasswd-longhorn longhornadmin  # password in Passbolt
```

---

## Step 21 — TLS (Certbot)

Ensure ports 80 and 443 are open on the perimeter firewall before running.

```bash
certbot --nginx -d lobot-dev.cs.queensu.ca
```

Reference: https://www.digitalocean.com/community/tutorials/how-to-secure-nginx-with-let-s-encrypt-on-ubuntu-20-04

---

## Step 22 — Move Lobot Directory and Final Config

```bash
# If you set up in ~/.kube/Lobot during install, move it to /opt
sudo mv /home/croot/.kube/Lobot /opt/

# Copy kubeconfig into Lobot dir for reference
sudo cp -i /etc/kubernetes/admin.conf /opt/Lobot
sudo chown croot:croot /opt/Lobot/admin.conf

# Add to .bashrc if needed
echo 'export KUBECONFIG=$HOME/.kube/config' >> ~/.bashrc
```

---

## Firewall Rules (Control Plane)

```bash
sudo ufw allow from any to any port 80
sudo ufw allow from any to any port 443
sudo ufw allow from any to any port 6443
sudo ufw allow from any to any port 10250
sudo ufw allow from any to any port 10256
sudo ufw allow from any to any port 10259
sudo ufw allow from any to any port 10257
sudo ufw allow from any to any port 2379:2380 proto tcp

# Allow Longhorn UI access from campus subnets only
for subnet in 130.15.1 130.15.2 130.15.3 130.15.4 130.15.5 130.15.6 130.15.7; do
  sudo ufw allow from ${subnet}.0/24 to any port 30001
done
```

---

## Optional: Kubernetes Dashboard

```bash
helm repo add kubernetes-dashboard https://kubernetes.github.io/dashboard/
helm upgrade --install kubernetes-dashboard kubernetes-dashboard/kubernetes-dashboard \
  --create-namespace --namespace kubernetes-dashboard

mkdir $HOME/.kube/yamls && cd $HOME/.kube/yamls

# dashboard-adminuser.yaml
kubectl apply -f - <<EOF
apiVersion: v1
kind: ServiceAccount
metadata:
  name: admin-user
  namespace: kubernetes-dashboard
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: admin-user
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: cluster-admin
subjects:
- kind: ServiceAccount
  name: admin-user
  namespace: kubernetes-dashboard
---
apiVersion: v1
kind: Secret
metadata:
  name: admin-user
  namespace: kubernetes-dashboard
  annotations:
    kubernetes.io/service-account.name: "admin-user"
type: kubernetes.io/service-account-token
EOF

# Get the login token
kubectl get secret admin-user -n kubernetes-dashboard -o jsonpath={".data.token"} | base64 -d

# Forward the dashboard (then open https://localhost:8443)
kubectl -n kubernetes-dashboard port-forward svc/kubernetes-dashboard-kong-proxy 8443:443

# To remove:
# kubectl delete namespace kubernetes-dashboard
```

---

## Optional: Robusta Monitoring

```bash
helm repo add robusta https://robusta-charts.storage.googleapis.com && helm repo update
# Configuration is on innovate
scp aaron@innovate.cs.queensu.ca:generated_values.yaml ./
helm install robusta robusta/robusta -f ./generated_values.yaml --set clusterName=CLUSTERNAMEHERE
```

---

## Extras

### GPU Time Slicing (e.g. A16)

On the A16 server, time slicing is required to allow more than one GPU to be requested
(likely due to the large number of GPUs in the server).

```bash
kubectl apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: time-slicing-config-fine
data:
  a16: |-
    version: v1
    flags:
      migStrategy: none
    sharing:
      timeSlicing:
        resources:
        - name: nvidia.com/gpu
          replicas: 4
EOF

kubectl patch clusterpolicies.nvidia.com/cluster-policy \
  -n gpu-operator --type merge \
  -p '{"spec": {"devicePlugin": {"config": {"name": "time-slicing-config-fine"}}}}'

# Label the specific node to enable time slicing on it
kubectl label node floppy nvidia.com/device-plugin.config=a16

# Check events
kubectl get events -n gpu-operator --sort-by='.lastTimestamp'

# Apply changes to the config
kubectl apply -n gpu-operator -f time-slicing-config-fine.yaml

# Restart the device plugin daemonset to pick up changes
kubectl rollout restart -n gpu-operator daemonset/nvidia-device-plugin-daemonset
```

---

### Proxmox PCIe Passthrough (Multi-GPU, e.g. A16)

```bash
# Expand root volume
lvresize -l +100%FREE /dev/pve/root
resize2fs /dev/mapper/pve-root

# Enable IOMMU and hugepages (AMD CPU; add intel_iommu=on for Intel)
vi /etc/default/grub
# GRUB_CMDLINE_LINUX_DEFAULT="quiet iommu=pt initcall_blacklist=sysfb_init hugepagesz=1G default_hugepagesz=2M"
update-grub

# Blacklist host GPU drivers
vi /etc/modprobe.d/blacklist.conf
# blacklist nouveau
# blacklist nvidia
# blacklist nvidiafd
# blacklist nvidia_drm

# Get PCI IDs for the GPU (same card type = same ID)
lspci -nn | grep "NVIDIA"
# e.g. 10de:25b6 for A16

vi /etc/modprobe.d/vfio.conf
# options vfio-pci ids=10de:25b6

update-initramfs -u -k all
reboot

# Verify
dmesg | grep -i vfio
dmesg | grep 'remapping'
lspci -nnk
```

> **Note:** When passing through multiple GPUs (A16), do not select BAR and PCI
> in advanced options — it breaks the network adapter. Set VM CPU type to `host`.
