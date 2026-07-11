#!/usr/bin/env bash
# ============================================================
# deploy-grupo5.sh — Faz o deploy da aplicação no cluster K8S da
# disciplina (Namespace: grupo-5).
# Uso: DOCKER_USERNAME=seu_usuario ./scripts/deploy-grupo5.sh
# ============================================================
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ -z "${DOCKER_USERNAME:-}" ]]; then
  echo "Erro: Variável DOCKER_USERNAME não definida."
  echo "Uso correto: DOCKER_USERNAME=seu_usuario ./scripts/deploy-grupo5.sh"
  exit 1
fi

export KUBECONFIG="$(pwd)/kubeconfig-grupo-5.yaml"

echo "==> 1/4 Aplicando credenciais do Banco de Dados..."
kubectl apply -f k8s-grupo5/01-secret.yaml

echo "==> 2/4 Aplicando Microsserviços e Gateway..."
# Usamos sed para substituir DOCKER_USERNAME nos manifestos temporariamente antes de aplicar
sed "s/DOCKER_USERNAME/$DOCKER_USERNAME/g" k8s-grupo5/30-microservices.yaml | kubectl apply -f -
sed "s/DOCKER_USERNAME/$DOCKER_USERNAME/g" k8s-grupo5/31-gateway-frontend.yaml | kubectl apply -f -

echo "==> 3/4 Aguardando os Pods subirem..."
kubectl rollout status deployment/authorization -n grupo-5 --timeout=300s
kubectl rollout status deployment/patient-data -n grupo-5 --timeout=300s
kubectl rollout status deployment/data-transform -n grupo-5 --timeout=300s
kubectl rollout status deployment/api-gateway -n grupo-5 --timeout=300s
kubectl rollout status deployment/frontend -n grupo-5 --timeout=300s

echo "==> 4/4 Implantação concluída!"
kubectl get pods -n grupo-5 -o wide

echo ""
echo "Sua aplicação deve estar rodando em: https://kiriland.unb.br/grupo5"
echo "Lembre-se: Para testar o Autoscaler (HPA) na fase correspondente do projeto, rode:"
echo "kubectl apply -f k8s-grupo5/40-hpa.yaml"
echo "============================================================"
