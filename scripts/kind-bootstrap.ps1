$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ClusterName = if ($env:CLUSTER_NAME) { $env:CLUSTER_NAME } else { "futbot" }

Write-Host "==> Creating kind cluster '$ClusterName' (if missing)..."
$existing = kind get clusters 2>$null
if ($existing -notcontains $ClusterName) {
    kind create cluster --name $ClusterName --config "$Root\k8s\kind-cluster.yaml"
} else {
    Write-Host "    Cluster already exists, skipping create."
}

Write-Host "==> Installing ingress-nginx..."
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml
kubectl wait --namespace ingress-nginx `
    --for=condition=ready pod `
    --selector=app.kubernetes.io/component=controller `
    --timeout=120s

Write-Host "==> Applying FutBot infra (kustomize dev overlay)..."
kubectl apply -k "$Root\k8s\overlays\dev"

Write-Host "==> Waiting for infra pods..."
kubectl wait --namespace futbot --for=condition=ready pod --all --timeout=180s

Write-Host "Done. Infra is running in namespace 'futbot'."
Write-Host "  kubectl get pods -n futbot"
