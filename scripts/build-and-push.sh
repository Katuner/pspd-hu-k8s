#!/usr/bin/env bash
# ============================================================
# build-and-push.sh — Faz o build e envia as imagens Docker
# para um repositório público (ex: Docker Hub).
# ============================================================
set -euo pipefail
cd "$(dirname "$0")/.."

DOCKER_USERNAME="${DOCKER_USERNAME:-}"

if [[ -z "$DOCKER_USERNAME" ]]; then
  echo "Username não pode ser vazio. Cancelando."
  exit 1
fi

echo "Assumindo que você já está logado no Docker Hub."


echo "Copiando o arquivo .proto para os serviços (caso não tenha sido feito)..."
for s in api-gateway authorization patient-data data-transform; do 
  cp proto/hospital.proto services/$s/
done

echo "==> Fazendo BUILD das imagens..."
docker build -t "$DOCKER_USERNAME/api-gateway:1.0" services/api-gateway
docker build -t "$DOCKER_USERNAME/authorization:1.0" services/authorization
docker build -t "$DOCKER_USERNAME/patient-data:1.0" services/patient-data
docker build -t "$DOCKER_USERNAME/data-transform:1.0" services/data-transform
docker build -t "$DOCKER_USERNAME/frontend:1.0" services/frontend

echo "==> Fazendo PUSH das imagens para o Docker Hub ($DOCKER_USERNAME)..."
docker push "$DOCKER_USERNAME/api-gateway:1.0"
docker push "$DOCKER_USERNAME/authorization:1.0"
docker push "$DOCKER_USERNAME/patient-data:1.0"
docker push "$DOCKER_USERNAME/data-transform:1.0"
docker push "$DOCKER_USERNAME/frontend:1.0"

echo "============================================================"
echo "Imagens enviadas com sucesso!"
echo "Agora rode o script de deploy:"
echo "DOCKER_USERNAME=$DOCKER_USERNAME ./scripts/deploy-grupo5.sh"
echo "============================================================"
