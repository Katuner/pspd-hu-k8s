#!/usr/bin/env bash
# ============================================================
# collect-metrics.sh — Coleta snapshots de CPU/memória dos pods
# e nós a cada 10 s durante um teste de carga, gravando em CSV.
#
# Uso:
#   ./scripts/collect-metrics.sh resultados/cenario1 300
#     (grava por 300 segundos no diretório resultados/cenario1)
# ============================================================
set -euo pipefail
OUTDIR="${1:-resultados/$(date +%Y%m%d-%H%M%S)}"
DURATION="${2:-300}"
INTERVAL=10

mkdir -p "$OUTDIR"
PODS_CSV="$OUTDIR/pods-metrics.csv"
NODES_CSV="$OUTDIR/nodes-metrics.csv"
HPA_CSV="$OUTDIR/hpa-status.csv"

echo "timestamp,pod,cpu_millicores,memory_mib" > "$PODS_CSV"
echo "timestamp,node,cpu_millicores,cpu_pct,memory_mib,memory_pct" > "$NODES_CSV"
echo "timestamp,hpa,targets,min,max,replicas" > "$HPA_CSV"

END=$((SECONDS + DURATION))
echo "==> Coletando métricas por ${DURATION}s em ${OUTDIR} (Ctrl+C para parar)"
while [ $SECONDS -lt $END ]; do
  TS=$(date +%H:%M:%S)
  kubectl -n hospital top pods --no-headers 2>/dev/null | \
    awk -v ts="$TS" '{gsub("m","",$2); gsub("Mi","",$3); print ts","$1","$2","$3}' >> "$PODS_CSV" || true
  kubectl top nodes --no-headers 2>/dev/null | \
    awk -v ts="$TS" '{gsub("m","",$2); gsub("%","",$3); gsub("Mi","",$4); gsub("%","",$5); print ts","$1","$2","$3","$4","$5}' >> "$NODES_CSV" || true
  kubectl -n hospital get hpa --no-headers 2>/dev/null | \
    awk -v ts="$TS" '{print ts","$1","$3","$4","$5","$6}' >> "$HPA_CSV" || true
  sleep $INTERVAL
done
echo "==> Coleta encerrada. Arquivos em ${OUTDIR}/"
