# L1NNA cluster setup

### Setup Master Node

Install GPU driver:
```
curl https://raw.githubusercontent.com/L1NNA/L1NNA-peppapig/master/setup_driver.sh | bash
```
Install Kubernetes stack + Nvidia runtime + monitoring stack:
```
curl https://raw.githubusercontent.com/L1NNA/L1NNA-peppapig/master/setup_master.sh | bash
```
Partition new hardrive into equal parititions and mount them to /media/ (labeled with a class of either sm/md/lg)
```
sudo lsblk -o NAME,FSTYPE,SIZE,MOUNTPOINT,LABEl
sudo wipefs -a /dev/sdx
python3 par.py /dev/sdx 4 md
sudo vim /etc/fstab
[editing]
sudo mount -a
```
Statically provision persistent volumes (based on each partitions under /media/)
```
curl https://raw.githubusercontent.com/L1NNA/L1NNA-peppapig/master/setup_storage.sh | bash
```
Setup Jupyter hub (this will take a while as we need to compile a new docker image):
```
curl https://raw.githubusercontent.com/L1NNA/L1NNA-peppapig/master/setup_jhub.sh | bash
## debug: 
##   kubectl logs $(kubectl get pods -n jhub | grep hub | awk '{print $1;}') -n jhub --follow
## re-start hub service pod: 
##   kubectl delete pod $(kubectl get pods -n jhub | grep hub | awk '{print $1;}') -n jhub
## print log:  
##   kubectl logs $(kubectl get pods -n jhub | grep hub | awk '{print $1;}') -n jhub --follow
## update config.yaml:
##   RELEASE=jhub ; NAMESPACE=jhub ; helm upgrade $RELEASE jupyterhub/jupyterhub --version=0.9.0  --values config.yaml --recreate-pods
## update/add shared volumn:
##   kubectl apply -f  shared_pvc.yaml
```



### ngnix & https:

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



### Kubectl/Helm Cheatsheet

preset:
```
export KUBECONFIG=$HOME/admin.conf
```

get/describe:
```
kubectl get,describe nodes --show-labels
kubectl get,describe pods --all-namespaces
kubectl get,describe pods -n kube-system
kubectl get,describe services,pv,pvc --all-namespaces
```
proxy/forward:
```
kubectl proxy --address='0.0.0.0'
kubectl port-forward --namespace monitoring service/grafana 8001:3000 (8001=>3000)
```

delete:
```
kubectl delete namespace monitoring
helm delete xxxx --purge
```

dashboard:

http://127.0.0.1:8001/api/v1/namespaces/kubernetes-dashboard/services/https:kubernetes-dashboard:/proxy/#/overview?namespace=default
```
kubectl get secret $(kubectl get serviceaccount dashboard -o jsonpath="{.secrets[0].name}") -o jsonpath="{.data.token}" | base64 --decode

```

New pvc:
```
kubectl create -f shared_pvc.yaml

```

### Minio

Tenant UI:

https://github.com/minio/direct-csi/blob/master/docs/cli.md


```
kubectl minio proxy -n minio-operator
```

### Longhorn

```bash
apt-get install open-iscsi

helm repo add longhorn https://charts.longhorn.io
helm repo update
helm install longhorn/longhorn --name longhorn --namespace longhorn-system --set service.ui.nodePort=30001 --set service.ui.type=NodePort

kubectl -n longhorn-system  rollout restart deploy

#check if all pods are good:
kubectl -n longhorn-system get daemonset


# new disk:
sudo lsblk -o NAME,FSTYPE,SIZE,MOUNTPOINT,LABEl
sudo parted -s --align optimal /dev/sdb -- mklabel gpt  mkpart primary ext4 0% 100%
sudo mkfs.ext4 /dev/sdb1
sudo mkdir -p /media/sdb/
sudo vim /etc/fstab
# add: /dev/sdb1 /media/sdb ext4 defaults 0 0
sudo mount -a

# then go to the web ui and add disk to node
```


