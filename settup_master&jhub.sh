
############ SETUP JHUB
# create storage class

cd /home/ding/config/Lobot
wget https://raw.githubusercontent.com/Queens-School-of-Computing/Lobot/dev/storageclass.yaml
/home/ding/config/Lobot/kubectl create -f storageclass.yaml

cd /home/ding/config
wget 
# create storage class
# wget https://raw.githubusercontent.com/L1NNA/L1NNA-peppapig/master/config.yaml
# sed -i -e 's/peppa-tkn/'$(openssl rand -hex 32)'/g' ./config.yaml
# read -p "Enter slack notification web nook: " SLACK_WEBHOOK
# sed -i -e 's,peppa-webhook,'$SLACK_WEBHOOK',g' ./config.yaml


helm repo add jupyterhub https://jupyterhub.github.io/helm-chart/
helm repo update

# Suggested values: advanced users of Kubernetes and Helm should feel
# free to use different values.
RELEASE=jhub ;NAMESPACE=jhub ; helm upgrade --install $RELEASE jupyterhub/jupyterhub --namespace $NAMESPACE --version=0.9.0   --values config.yaml

# to remove install/cancel
# helm delete $RELEASE --purge --no-hooks

# to upgrade
# RELEASE=jhub ;NAMESPACE=jhub ;  helm upgrade $RELEASE jupyterhub/jupyterhub --version=0.9.0  --values config.yaml --recreate-pods

echo 'done'
echo 'to update with any new changes in config.yaml:'
# docs for config: https://jupyterhub-kubespawner.readthedocs.io/en/latest/spawner.html
echo 'helm upgrade $RELEASE jupyterhub/jupyterhub --version=0.9.0  --values config.yaml --recreate-pods'

# install longhorn v1.2.3
apt-get install open-iscsi
helm repo add longhorn https://charts.longhorn.io
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

