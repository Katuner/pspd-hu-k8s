#!/usr/bin/env bash
# ============================================================
# setup-cluster.sh — Cria o cluster kind (1 master + 3 workers)
# e instala os componentes de infraestrutura:
#   - metrics-server        (necessário para HPA e kubectl top)
#   - kube-prometheus-stack (Prometheus + Grafana + exporters)
#   - Kubernetes Dashboard  (interface web do cluster)
#
# Pré-requisitos: docker, kind, kubectl, helm (ver guia de instalação)
# Uso: ./scripts/setup-cluster.sh
# ============================================================
set -euo pipefail
cd "$(dirname "$0")/.."

CLUSTER="${CLUSTER:-pspd}"

# ------------------------------------------------------------
# 1. Cluster kind: 1 control-plane + 3 workers
# ------------------------------------------------------------
if kind get clusters | grep -q "^${CLUSTER}$"; then
  echo "==> Cluster kind '${CLUSTER}' já existe. Pulando criação."
else
  echo "==> Criando cluster kind '${CLUSTER}' (1 master + 3 workers)..."
  kind create cluster --name "${CLUSTER}" --config k8s/kind-cluster.yaml --wait 120s
fi
kubectl cluster-info --context "kind-${CLUSTER}"
kubectl get nodes -o wide

# ------------------------------------------------------------
# 2. metrics-server (com --kubelet-insecure-tls, exigido no kind
#    porque os kubelets usam certificados autoassinados)
# ------------------------------------------------------------
echo "==> Instalando metrics-server..."
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
kubectl -n kube-system patch deployment metrics-server --type=json \
  -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'

# ------------------------------------------------------------
# 3. kube-prometheus-stack (Prometheus Operator + Grafana)
#    Release "monitoring" — os ServiceMonitors da aplicação usam
#    o label release=monitoring para serem descobertos.
# ------------------------------------------------------------
echo "==> Instalando kube-prometheus-stack via Helm..."
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null
helm repo update >/dev/null
helm upgrade --install monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace \
  --set grafana.adminPassword=pspd123 \
  --set grafana.service.type=NodePort \
  --set grafana.service.nodePort=30900 \
  --set prometheus.service.type=NodePort \
  --set prometheus.service.nodePort=30990 \
  --set prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false \
  --set prometheus.prometheusSpec.podMonitorSelectorNilUsesHelmValues=false \
  --set prometheus.prometheusSpec.retention=2d \
  --wait --timeout 15m

# ------------------------------------------------------------
# 4. Kubernetes Dashboard (interface web de monitoramento do cluster)
# ------------------------------------------------------------
echo "==> Instalando Kubernetes Dashboard..."
kubectl apply -f https://raw.githubusercontent.com/kubernetes/dashboard/v2.7.0/aio/deploy/recommended.yaml

# ServiceAccount admin para login no Dashboard
kubectl apply -f - <<'EOF'
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
EOF

echo
echo "============================================================"
echo "Cluster pronto!"
echo "  - Nós:              kubectl get nodes"
echo "  - Grafana:          http://localhost:30900  (admin / pspd123)"
echo "  - Prometheus:       http://localhost:30990"
echo "  - Dashboard token:  kubectl -n kubernetes-dashboard create token admin-user"
echo "  - Dashboard acesso: kubectl proxy  ->"
echo "    http://localhost:8001/api/v1/namespaces/kubernetes-dashboard/services/https:kubernetes-dashboard:/proxy/"
echo "Próximo passo: ./scripts/build-images.sh --kind && ./scripts/deploy-all.sh"
echo "============================================================"
