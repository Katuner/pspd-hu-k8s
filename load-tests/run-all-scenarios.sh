#!/usr/bin/env bash
# ============================================================
# run-all-scenarios.sh — Executa a bateria completa de testes
# de carga (10, 50, 100, 500 e 1000 VUs) coletando também as
# métricas de CPU/memória dos pods durante cada cenário.
#
# Uso:
#   ./run-all-scenarios.sh                        # cenário padrão
#   LABEL=3replicas ./run-all-scenarios.sh        # rotula os resultados
#   BASE_URL=http://IP:30800 ./run-all-scenarios.sh
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"

BASE_URL="${BASE_URL:-http://localhost:30800}"
LABEL="${LABEL:-baseline}"
DURATION="${DURATION:-3m}"
OUTDIR="resultados/${LABEL}-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUTDIR"

echo "==> Resultados serão gravados em ${OUTDIR}"
echo "==> Alvo: ${BASE_URL} | duração de cada cenário: ${DURATION}"

for VUS in 10 50 100 500 1000; do
  echo
  echo "############################################################"
  echo "# Cenário: ${VUS} usuários simultâneos"
  echo "############################################################"

  # coleta de métricas dos pods em paralelo (duração + rampas + margem)
  ../scripts/collect-metrics.sh "${OUTDIR}/metrics-${VUS}vus" 260 &
  COLLECT_PID=$!

  k6 run -e VUS="${VUS}" -e BASE_URL="${BASE_URL}" -e DURATION="${DURATION}" \
     --summary-export="${OUTDIR}/k6-summary-${VUS}vus.json" \
     k6-load.js | tee "${OUTDIR}/k6-output-${VUS}vus.txt"

  wait "$COLLECT_PID" || true
  mv "summary-${VUS}vus.json" "${OUTDIR}/" 2>/dev/null || true

  echo "==> Aguardando 60 s para o sistema estabilizar antes do próximo cenário..."
  sleep 60
done

echo
echo "==> Bateria concluída. Resultados em ${OUTDIR}/"
ls -la "$OUTDIR"
