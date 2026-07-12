#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLUSTER_NAME="${CLUSTER_NAME:-futbot}"

echo "==> Creating kind cluster '${CLUSTER_NAME}' (if missing)..."
if ! kind get clusters 2>/dev/null | grep -qx "${CLUSTER_NAME}"; then
  kind create cluster --name "${CLUSTER_NAME}" --config "${ROOT}/k8s/kind-cluster.yaml"
else
  echo "    Cluster already exists, skipping create."
fi

echo "==> Installing ingress-nginx..."
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml
kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=120s

echo "==> Applying FutBot infra (kustomize dev overlay)..."
kubectl apply -k "${ROOT}/k8s/overlays/dev"

echo "==> Waiting for infra pods..."
kubectl wait --namespace futbot --for=condition=ready pod --all --timeout=180s

echo "Done. Infra is running in namespace 'futbot'."
echo "  kubectl get pods -n futbot"
echo "  docker compose -f docker-compose.infra.yml up -d   # optional local compose alternative"
