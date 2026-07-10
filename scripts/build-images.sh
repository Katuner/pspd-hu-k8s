#!/usr/bin/env bash
# ============================================================
# build-images.sh — Constrói as 5 imagens Docker da aplicação
# e (opcionalmente) as carrega no cluster kind.
#
# Uso:
#   ./scripts/build-images.sh          # apenas build
#   ./scripts/build-images.sh --kind   # build + kind load
# ============================================================
set -euo pipefail
cd "$(dirname "$0")/.."

TAG="${TAG:-1.0}"
CLUSTER="${CLUSTER:-pspd}"

echo "==> Preparando contexto de build (copiando hospital.proto para cada serviço)"
for svc in api-gateway authorization patient-data data-transform; do
  cp proto/hospital.proto "services/${svc}/hospital.proto"
done

echo "==> Construindo imagens (tag ${TAG})"
docker build -t hospital/api-gateway:${TAG}    services/api-gateway
docker build -t hospital/authorization:${TAG}  services/authorization
docker build -t hospital/patient-data:${TAG}   services/patient-data
docker build -t hospital/data-transform:${TAG} services/data-transform
docker build -t hospital/frontend:${TAG}       services/frontend

if [[ "${1:-}" == "--kind" ]]; then
  echo "==> Carregando imagens no cluster kind '${CLUSTER}'"
  kind load docker-image \
    hospital/api-gateway:${TAG} \
    hospital/authorization:${TAG} \
    hospital/patient-data:${TAG} \
    hospital/data-transform:${TAG} \
    hospital/frontend:${TAG} \
    --name "${CLUSTER}"
fi

echo "==> Concluído."
docker images | grep hospital/
