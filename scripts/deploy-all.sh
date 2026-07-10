#!/usr/bin/env bash
# ============================================================
# deploy-all.sh — Implanta a aplicação completa no cluster K8S
#   1. namespace + secrets
#   2. ConfigMaps (scripts SQL e realm do Keycloak)
#   3. PostgreSQL, Keycloak
#   4. Microsserviços, Gateway, Frontend
#   5. ServiceMonitors (se o Prometheus Operator existir)
#
# Uso: ./scripts/deploy-all.sh
# ============================================================
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> 1/5 Namespace e credenciais"
kubectl apply -f k8s/00-namespace.yaml

echo "==> 2/5 ConfigMaps (SQL init + realm Keycloak)"
kubectl -n hospital create configmap db-init \
  --from-file=database/01-schema.sql \
  --from-file=database/02-seed.sql \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n hospital create configmap keycloak-realm \
  --from-file=keycloak/realm-hospital.json \
  --dry-run=client -o yaml | kubectl apply -f -

echo "==> 3/5 PostgreSQL e Keycloak"
kubectl apply -f k8s/10-postgres.yaml
kubectl apply -f k8s/20-keycloak.yaml

echo "    Aguardando PostgreSQL ficar pronto..."
kubectl -n hospital rollout status statefulset/postgres --timeout=300s
echo "    Aguardando Keycloak ficar pronto (pode levar ~2 min)..."
kubectl -n hospital rollout status deployment/keycloak --timeout=600s

echo "==> 4/5 Microsserviços, API Gateway e Frontend"
kubectl apply -f k8s/30-microservices.yaml
kubectl apply -f k8s/31-gateway-frontend.yaml
kubectl -n hospital rollout status deployment/authorization --timeout=300s
kubectl -n hospital rollout status deployment/patient-data --timeout=300s
kubectl -n hospital rollout status deployment/data-transform --timeout=300s
kubectl -n hospital rollout status deployment/api-gateway --timeout=300s
kubectl -n hospital rollout status deployment/frontend --timeout=300s

echo "==> 5/5 ServiceMonitors (Prometheus)"
if kubectl get crd servicemonitors.monitoring.coreos.com >/dev/null 2>&1; then
  kubectl apply -f k8s/50-servicemonitors.yaml
else
  echo "    AVISO: CRD ServiceMonitor não encontrada."
  echo "    Instale o kube-prometheus-stack (scripts/setup-cluster.sh) e aplique:"
  echo "    kubectl apply -f k8s/50-servicemonitors.yaml"
fi

echo
echo "============================================================"
echo "Aplicação implantada!"
kubectl -n hospital get pods -o wide
echo
echo "Acessos (via NodePort mapeado pelo kind):"
echo "  Frontend:    http://localhost:30080"
echo "  API Gateway: http://localhost:30800/docs"
echo "  Keycloak:    http://localhost:30880  (admin / admin123)"
echo
echo "Usuários de teste (senha pspd123): med.cardoso, est.oliveira, pesq.ramos ..."
echo "HPA (fase autoscaling): kubectl apply -f k8s/40-hpa.yaml"
echo "============================================================"
