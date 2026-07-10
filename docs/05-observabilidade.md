# Guia 05 - Observabilidade e Métricas

A observabilidade é um dos pilares deste projeto. Ela permite entender não apenas a saúde da infraestrutura (CPU, Memória), mas também o comportamento do negócio (Quantos acessos negados? Quantos recursos FHIR gerados?).

## 1. Importando o Dashboard no Grafana

O script `setup-cluster.sh` já instalou o Prometheus e o Grafana.
1. Acesse **http://localhost:30900** (Admin: `admin` / Senha: `pspd123`).
2. No menu lateral esquerdo, vá em **Dashboards** > **Import**.
3. Clique em **Upload JSON file** e selecione o arquivo `grafana/dashboard-hospital.json` presente na raiz deste projeto.
4. Selecione a fonte de dados `Prometheus` (já configurada pelo Helm) e clique em Import.

## 2. Entendendo os Painéis (Panels)

O Dashboard possui 10 painéis divididos em três categorias:

### Métricas de Tráfego (Gateway)
- **Requisições por segundo:** Mostra o volume de chamadas HTTP (throughput) divididas por rota (`/api/patients`, `/auth/login`, etc).
- **Latência HTTP:** Percentis 50 (mediana), 95 e 99. Essencial para avaliar a degradação do serviço sob carga.
- **Erros HTTP:** Conta erros 4xx (acesso negado, não autorizado) e 5xx (falhas internas do servidor).

### Métricas de Negócio (Customizadas)
Nossos microsserviços expõem métricas específicas de negócio via porta 9100. Os `ServiceMonitors` em `k8s/50-servicemonitors.yaml` ensinam o Prometheus a raspá-las.
- **Decisões de autorização:** Gráfico gerado pelo serviço `authorization`. Mostra a taxa de decisões ALLOW vs DENY, divididas pelo nível de anonimização (FULL, PARTIAL, ANONYMIZED, AGGREGATED).
- **Transformações FHIR:** Gráfico gerado pelo serviço `data-transform`. Mostra quantos recursos FHIR (`Patient`, `Observation`, `MeasureReport`) estão sendo construídos por segundo.
- **Consultas ao Banco:** Gráfico gerado pelo serviço `patient-data`. Mostra o tipo de consulta SQL executada.

### Métricas de Infraestrutura
- **Uso de CPU e Memória por Pod:** Permite identificar gargalos e justificar as ações do HPA.
- **Quantidade de pods por deployment:** Visualiza o efeito prático do Horizontal Pod Autoscaler ao longo do tempo.

## 3. Explorando o Prometheus Diretamente

Caso queira fazer consultas customizadas com PromQL, acesse a interface do Prometheus em **http://localhost:30990**.

Exemplos de queries interessantes para testar:
```promql
# Taxa total de requisições gRPC bem sucedidas
sum(rate(grpc_requests_total{code="OK"}[1m])) by (service)

# Quantas anonimizações parciais (remoção de CPF) ocorreram nos últimos 5 minutos
increase(anonymization_operations_total{level="PARTIAL"}[5m])
```
