#!/bin/sh
# curl https://raw.githubusercontent.com/L1NNA/L1NNA-peppapig/master/setup_jhub.sh | bash
# make sure kubectl will work
export KUBECONFIG=$HOME/admin.conf


# create storage class
wget https://raw.githubusercontent.com/L1NNA/L1NNA-peppapig/master/config.yaml
sed -i -e 's/peppa-tkn/'$(openssl rand -hex 32)'/g' ./config.yaml

read -p "Enter slack notification web nook: " SLACK_WEBHOOK
sed -i -e 's,peppa-webhook,'$SLACK_WEBHOOK',g' ./config.yaml


helm repo add jupyterhub https://jupyterhub.github.io/helm-chart/
helm repo update

# Suggested values: advanced users of Kubernetes and Helm should feel
# free to use different values.
RELEASE=jhub
NAMESPACE=jhub

helm upgrade --install $RELEASE jupyterhub/jupyterhub \
  --namespace $NAMESPACE  \
  --version=0.9.0 \
  --values config.yaml

echo 'done'
echo 'to update with any new changes in config.yaml:'
# docs for config: https://jupyterhub-kubespawner.readthedocs.io/en/latest/spawner.html
echo 'helm upgrade $RELEASE jupyterhub/jupyterhub --version=0.9.0  --values config.yaml --recreate-pods'




