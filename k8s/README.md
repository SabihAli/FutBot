# Kubernetes manifests

## Prerequisites

- [kind](https://kind.sigs.k8s.io/)
- kubectl
- kustomize (built into kubectl 1.14+)

## Bootstrap local cluster

**Windows (PowerShell):**

```powershell
.\scripts\kind-bootstrap.ps1
```

**Linux / macOS:**

```bash
chmod +x scripts/kind-bootstrap.sh
./scripts/kind-bootstrap.sh
```

This creates a `futbot` kind cluster, installs ingress-nginx, and applies infra (Postgres, Redis, MinIO, Qdrant) to namespace `futbot`.

## Manual apply

```bash
kubectl apply -k k8s/overlays/dev
kubectl get pods -n futbot
```

## Docker Compose alternative

For local dev without Kubernetes:

```bash
docker compose -f docker-compose.infra.yml up -d
```

Connection defaults: [`.env.example`](../.env.example) (copy to `.env`)
