#!/usr/bin/env bash
# ============================================================
# scale.sh — Ajusta o número de réplicas dos serviços da aplicação
# (fase c — escalabilidade horizontal).
#
# Uso:
#   ./scripts/scale.sh 1     # cenário base: 1 réplica de cada
#   ./scripts/scale.sh 3     # cenário escalado: 3 réplicas de cada
# ============================================================
set -euo pipefail
REPLICAS="${1:-1}"

for d in api-gateway authorization patient-data data-transform; do
  kubectl -n hospital scale deployment/"$d" --replicas="$REPLICAS"
done

echo "==> Aguardando rollout..."
for d in api-gateway authorization patient-data data-transform; do
  kubectl -n hospital rollout status deployment/"$d" --timeout=300s
done

echo "==> Distribuição dos pods pelos nós:"
kubectl -n hospital get pods -o wide
