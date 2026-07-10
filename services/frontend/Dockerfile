# Frontend estático servido por nginx.
# O nginx.conf é um TEMPLATE (diretório templates/ da imagem oficial):
# o entrypoint executa envsubst substituindo ${GATEWAY_UPSTREAM} e
# ${DNS_RESOLVER} antes de iniciar o nginx.
FROM nginx:1.27-alpine

# Valores padrão (docker-compose): DNS embutido do Docker + serviço api-gateway
# No Kubernetes, sobrescrever DNS_RESOLVER com o ClusterIP do kube-dns
# (por padrão 10.96.0.10) via variável de ambiente no Deployment.
ENV GATEWAY_UPSTREAM=api-gateway:8000 \
    DNS_RESOLVER=127.0.0.11

COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY html/ /usr/share/nginx/html/

EXPOSE 80
