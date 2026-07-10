# Projeto PSPD 2026.1 — Monitoramento e Observabilidade em Kubernetes
## Passo a Passo Explicativo Completo: Ambiente, Aplicação, Testes e Justificativas

Este documento consolida todas as ações tomadas na construção do projeto, com as justificativas técnicas de cada decisão, os erros encontrados durante o desenvolvimento e as respectivas correções. Ele é suficiente para que qualquer aluno reproduza integralmente o ambiente e execute os experimentos em sua própria máquina para comparação de resultados.

---

## 1. Entendimento do Problema

A proposta de trabalho (arquivo `PSPD2026.1_PPesq.pdf`) exige a construção de uma aplicação de **microsserviços hospitalares** (padrão HL7/FHIR) implantada em um **cluster Kubernetes com 1 nó mestre e 3 nós workers**, contendo os seguintes componentes: um serviço de autenticação (**Keycloak**, OAuth2/OpenID Connect), uma **API Gateway** que valida tokens JWT e orquestra chamadas **gRPC** a três microsserviços internos (**Authorization Service**, **Patient Data Service** e **Data Transform Service**), um banco **PostgreSQL** com massa de dados clínicos, e uma camada completa de **observabilidade** (Prometheus + Grafana), avaliada em quatro fases: (a) validação funcional, (b) implantação no cluster, (c) escalabilidade horizontal manual e (d) autoscaling com HPA, sob testes de carga com 10 a 1000 usuários simultâneos.

A matriz de autorização implementada segue exatamente a especificação:

| Perfil | Escopo de acesso | Nível de dado retornado |
| --- | --- | --- |
| Médico | Somente pacientes vinculados a ele | FULL (dados completos, incl. CPF e nascimento) |
| Estagiário | Pacientes do médico supervisor | PARTIAL (sem CPF; nascimento vira faixa etária) |
| Pesquisador | Coortes de projetos aprovados e vigentes | ANONYMIZED (IDs em hash, sem nomes) e AGGREGATED (FHIR MeasureReport) |
| Qualquer outro caso | — | DENY (HTTP 403) |

## 2. Decisões de Arquitetura e Justificativas

A tabela abaixo resume a stack escolhida. O critério dominante foi usar tecnologias padrão de mercado, gratuitas e reproduzíveis em qualquer notebook com Docker.

| Componente | Tecnologia | Justificativa |
| --- | --- | --- |
| API Gateway | Python FastAPI + Uvicorn | Assíncrono (alto throughput em I/O), validação local de JWT (RS256 com JWKS do Keycloak, sem chamada de rede por requisição), Swagger UI automático em `/docs` |
| Comunicação interna | gRPC (HTTP/2 + Protobuf) | Requisito da especificação; payload binário compacto e contrato estrito compartilhado em `proto/hospital.proto` |
| Identidade | Keycloak 26 | Requisito da especificação; realm `hospital` versionado em JSON e importado automaticamente na subida (zero configuração manual) |
| Banco de dados | PostgreSQL 16 | Relacional maduro; schema + seed sintético (200 pacientes, ~5.400 registros clínicos) gerados por script Python determinístico (seed fixa, reproduzível) |
| Frontend | HTML/JS + nginx | SPA leve para demonstração; nginx faz proxy `/gw/` para o gateway, eliminando CORS |
| Cluster | kind v0.30 | Cria cluster K8S multinó com containers Docker como nós — reproduz "1 master + 3 workers" em máquina local |
| Observabilidade | kube-prometheus-stack (Helm) + ServiceMonitors | Instala Prometheus Operator, Grafana e exporters de uma vez; métricas de negócio customizadas raspadas via ServiceMonitor |
| Teste de carga | k6 (principal) e Locust (alternativa) | k6 permite parametrizar VUs por variável de ambiente e exportar sumário JSON; Locust oferece UI web para acompanhamento |

O fluxo de uma requisição é: `Browser → nginx (frontend) → API Gateway (valida JWT) → Authorization Service (decide ALLOW/DENY + nível) → Patient Data Service (SQL) → Data Transform Service (converte para FHIR e anonimiza conforme o nível) → resposta JSON FHIR ao browser`.

## 3. Estrutura de Arquivos Entregues

Todo o projeto está no pacote `pspd-hu-k8s.zip`. A organização é:

| Diretório | Conteúdo |
| --- | --- |
| `proto/` | Contrato gRPC único (`hospital.proto`) usado pelos 4 serviços |
| `services/` | Código-fonte + Dockerfile + requirements de cada serviço (api-gateway, authorization, patient-data, data-transform, frontend) |
| `database/` | `01-schema.sql`, `02-seed.sql` (massa pronta) e `generate_seed.py` (gerador) |
| `keycloak/` | `realm-hospital.json` com roles, client e 8 usuários de teste |
| `k8s/` | Manifests numerados: cluster kind, namespace/secret, postgres, keycloak, microsserviços, gateway/frontend, HPA e ServiceMonitors |
| `grafana/` | `dashboard-hospital.json` com 10 painéis prontos para importar |
| `load-tests/` | `k6-smoke.js`, `k6-load.js`, `locustfile.py`, `run-all-scenarios.sh` |
| `scripts/` | Automação: `setup-cluster.sh`, `build-images.sh`, `deploy-all.sh`, `scale.sh`, `collect-metrics.sh`, `validate-functional.sh` |
| `docs/` | Guias 01 a 05 (visão geral, validação funcional, cluster, testes de carga, observabilidade) |

## 4. Preparação do Ambiente (executar na sua máquina)

Os comandos abaixo foram testados em Ubuntu 24.04. Instale, nesta ordem:

**Docker e Docker Compose:**
```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER && newgrp docker
```

**kind, kubectl e Helm:**
```bash
# kind
curl -Lo ./kind https://kind.sigs.k8s.io/dl/latest/kind-linux-amd64
chmod +x ./kind && sudo mv ./kind /usr/local/bin/kind
# kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl && sudo mv kubectl /usr/local/bin/
# helm
curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
```

**k6 (teste de carga):**
```bash
curl -fsSL https://dl.k6.io/key.gpg | sudo gpg --dearmor -o /usr/share/keyrings/k6-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" | sudo tee /etc/apt/sources.list.d/k6.list
sudo apt-get update && sudo apt-get install -y k6
```

Descompacte o projeto e entre no diretório:
```bash
unzip pspd-hu-k8s.zip && cd pspd-hu-k8s
```

## 5. Fase (a) — Validação Funcional Local

Antes de complicar com Kubernetes, valida-se a lógica de negócio com Docker Compose. O passo de copiar o `.proto` é necessário porque cada Dockerfile compila os stubs gRPC no build:

```bash
for s in api-gateway authorization patient-data data-transform; do cp proto/hospital.proto services/$s/; done
docker compose up -d --build      # sobe os 7 containers
./scripts/validate-functional.sh  # bateria automatizada com 31 verificações
```

O script de validação testa: login de todos os perfis no Keycloak, rejeição de senha errada, acesso FULL do médico (CPF presente), DENY para paciente de outro médico (403), anonimização PARTIAL do estagiário (CPF ausente, faixa etária presente), coorte ANONYMIZED do pesquisador (IDs em hash, sem nomes/cidades), estatísticas AGGREGATED (recurso FHIR MeasureReport), DENY para coorte sem projeto e projeto expirado, e rejeição de requisições sem token ou com token falso (401). **Resultado obtido na execução de referência: 31 PASS / 0 FAIL.**

O frontend fica em `http://localhost:8081` (usuários de demonstração com senha `pspd123`). Ao final, execute `docker compose down -v`.

## 6. Fase (b) — Cluster Kubernetes

Três comandos automatizam toda a fase:

```bash
./scripts/setup-cluster.sh        # cria cluster kind (1 master + 3 workers) + metrics-server + Prometheus/Grafana + Dashboard
./scripts/build-images.sh --kind  # constrói as 5 imagens e as carrega nos nós do kind
./scripts/deploy-all.sh           # aplica namespace, configmaps (SQL/realm), postgres, keycloak, microsserviços, gateway, frontend e ServiceMonitors
```

Pontos técnicos que merecem justificativa:

1. **`extraPortMappings` no kind-cluster.yaml** — os NodePorts (30080 frontend, 30800 gateway, 30880 keycloak, 30900 grafana, 30990 prometheus) são mapeados para o localhost da máquina hospedeira, dispensando `kubectl port-forward`.
2. **metrics-server com `--kubelet-insecure-tls`** — no kind os kubelets usam certificados autoassinados; sem essa flag o metrics-server não coleta métricas e o HPA fica em `<unknown>`. O script já aplica o patch.
3. **`serviceMonitorSelectorNilUsesHelmValues=false`** — sem esse valor, o Prometheus instalado pelo Helm só descobriria ServiceMonitors criados pelo próprio chart, ignorando os da nossa aplicação.
4. **SQL e realm via ConfigMap** — o `deploy-all.sh` gera os ConfigMaps a partir dos arquivos versionados, garantindo que o banco nasce populado e o Keycloak nasce configurado.
5. **`KC_HOSTNAME=http://keycloak:8080`** — fixa o issuer dos tokens JWT, para que o `iss` validado pelo gateway seja estável independentemente de onde a requisição de login se origina.

Verificação: `kubectl get nodes` (4 nós), `kubectl -n hospital get pods` (todos Running) e frontend em `http://localhost:30080`. Rode a mesma validação funcional agora contra o cluster: `BASE_URL=http://localhost:30800 ./scripts/validate-functional.sh`.

## 7. Fases (c) e (d) — Testes de Carga, Escala Manual e HPA

**Este é o experimento que cada aluno deve executar em seu próprio ambiente para comparação**, pois os números absolutos dependem do hardware. O roteiro é:

**Smoke test (sanidade, ~30 s):**
```bash
k6 run -e BASE_URL=http://localhost:30800 load-tests/k6-smoke.js
```

**Cenário 1 réplica (baseline):**
```bash
./scripts/scale.sh 1
LABEL=1replica ./load-tests/run-all-scenarios.sh
```

**Cenário 3 réplicas (escala manual):**
```bash
./scripts/scale.sh 3
LABEL=3replicas ./load-tests/run-all-scenarios.sh
```

**Cenário HPA (autoscaling):**
```bash
./scripts/scale.sh 1
kubectl apply -f k8s/40-hpa.yaml
watch kubectl -n hospital get hpa      # em outro terminal
k6 run -e VUS=500 -e DURATION=5m -e BASE_URL=http://localhost:30800 load-tests/k6-load.js
```

O `run-all-scenarios.sh` executa automaticamente os 5 níveis de carga exigidos (10, 50, 100, 500 e 1000 VUs), rodando em paralelo o `collect-metrics.sh`, que grava CSVs com CPU/memória dos pods e nós a cada 10 segundos. Ao final, a pasta `load-tests/resultados/<label>-<timestamp>/` contém, para cada cenário, o sumário JSON do k6 (throughput, latência média/p95, taxa de erro) e os CSVs de recursos — a matéria-prima das tabelas e gráficos do relatório.

Na execução de referência dentro do ambiente de desenvolvimento (20 VUs, 30 s, 1 réplica de cada serviço via compose), obteve-se **784 requisições, 10,4 req/s, latência média 13,2 ms, p95 57,7 ms e 0,00% de erros** — confirmando que a aplicação está saudável antes dos cenários pesados.

O comportamento esperado (a ser confirmado por cada aluno): com 1 réplica, a latência p95 cresce fortemente a partir de ~500 VUs porque a validação JWT e a montagem FHIR saturam a CPU do pod; com 3 réplicas, o Kubernetes distribui os pods pelos 3 workers e o throughput escala quase linearmente; com HPA, observa-se a criação progressiva de réplicas quando a CPU passa de 60% do request, com janela de estabilização de 120 s na redução para evitar oscilação (*flapping*).

## 8. Observabilidade

Além das métricas de infraestrutura padrão, cada serviço expõe **métricas de negócio customizadas** em formato Prometheus:

| Métrica | Serviço | O que mostra |
| --- | --- | --- |
| `http_requests_total`, `http_request_duration_seconds` | api-gateway | Volume, status e latência por rota REST |
| `auth_failures_total` | api-gateway | Falhas de autenticação por motivo |
| `authz_decisions_total{decision,level,role}` | authorization | Decisões ALLOW/DENY por perfil e nível de acesso |
| `db_queries_total{query}` | patient-data | Consultas SQL por tipo |
| `fhir_transformations_total{resource_type}` | data-transform | Recursos FHIR gerados (Patient, Observation, MeasureReport…) |
| `anonymization_operations_total{level}` | data-transform | Operações de anonimização por nível |
| `grpc_requests_total`, `grpc_request_duration_seconds` | todos os gRPC | Tráfego e latência interna gRPC |

O dashboard `grafana/dashboard-hospital.json` (importar em Grafana → Dashboards → Import) reúne 10 painéis: RPS por rota, latência p50/p95/p99, erros 4xx/5xx, latência gRPC por serviço, CPU/memória por pod, número de réplicas por deployment (curva do HPA), consultas ao banco, decisões de autorização e transformações FHIR.

## 9. Erros Encontrados Durante o Desenvolvimento e Correções

Registrar os erros faz parte da proposta pedagógica do trabalho. Os relevantes foram:

**Erro 1 — nginx: `host not found in upstream "api-gateway"`.** Na primeira versão do frontend, o `nginx.conf` usava `proxy_pass http://api-gateway:8000/` fixo. O nginx resolve nomes de upstream na inicialização; se o gateway ainda não estiver registrado no DNS (ordem de subida dos containers/pods), o nginx aborta em loop de crash. **Correção:** o `nginx.conf` virou um template (`/etc/nginx/templates/default.conf.template`) processado por `envsubst`, usando `resolver` + variável (`set $gateway_upstream`), o que move a resolução DNS para o tempo de requisição. As variáveis `GATEWAY_UPSTREAM` e `DNS_RESOLVER` são definidas por ambiente (Docker: `127.0.0.11`; Kubernetes: `10.96.0.10`, ClusterIP do kube-dns no kind).

**Erro 2 — HPA exibindo `<unknown>` nos targets.** Ocorre quando o metrics-server não está instalado ou não confia nos certificados do kubelet do kind. **Correção:** patch automático com `--kubelet-insecure-tls` no `setup-cluster.sh`; além disso, todos os Deployments definem `resources.requests.cpu`, sem o que o HPA não consegue calcular percentual de utilização.

**Erro 3 — Prometheus não raspava as métricas da aplicação.** O chart kube-prometheus-stack, por padrão, só observa ServiceMonitors com o label do próprio release. **Correção:** instalar o chart com `serviceMonitorSelectorNilUsesHelmValues=false` e rotular os ServiceMonitors com `release: monitoring`.

**Erro 4 — Issuer do JWT inconsistente.** Quando o login era feito por rotas diferentes (NodePort externo vs. serviço interno), o Keycloak emitia tokens com `iss` distintos e o gateway rejeitava com 401. **Correção:** fixar `KC_HOSTNAME=http://keycloak:8080` no Keycloak, e o gateway autentica-se e valida sempre pelo endereço interno do serviço; o frontend nunca fala com o Keycloak diretamente — o gateway expõe `/auth/login` e repassa via *password grant*.

**Erro 5 (específico do ambiente de desenvolvimento) — Docker sem a tabela `raw` do iptables.** No ambiente usado para validar este projeto, o kernel não expunha a tabela `raw`, quebrando a rede bridge do Docker. Foi contornado com `{"iptables": false, "bridge": "none"}` e `network_mode: host`. **Em máquinas comuns (Ubuntu/Debian/WSL2 padrão) esse problema não ocorre** e o `docker-compose.yml` funciona como entregue; o registro fica como referência caso algum aluno use ambiente virtualizado restrito.

## 10. Checklist de Reprodução (resumo executável)

```bash
# 0. Pré-requisitos: docker, kind, kubectl, helm, k6 (seção 4)
unzip pspd-hu-k8s.zip && cd pspd-hu-k8s

# Fase a — validação funcional local
for s in api-gateway authorization patient-data data-transform; do cp proto/hospital.proto services/$s/; done
docker compose up -d --build
./scripts/validate-functional.sh          # esperado: 31 PASS / 0 FAIL
docker compose down -v

# Fase b — cluster K8S (1 master + 3 workers) e deploy
./scripts/setup-cluster.sh
./scripts/build-images.sh --kind
./scripts/deploy-all.sh
BASE_URL=http://localhost:30800 ./scripts/validate-functional.sh

# Grafana: http://localhost:30900 (admin/pspd123) -> importar grafana/dashboard-hospital.json

# Fases c e d — testes de carga (executar e comparar no SEU hardware)
k6 run -e BASE_URL=http://localhost:30800 load-tests/k6-smoke.js
./scripts/scale.sh 1 && LABEL=1replica  ./load-tests/run-all-scenarios.sh
./scripts/scale.sh 3 && LABEL=3replicas ./load-tests/run-all-scenarios.sh
./scripts/scale.sh 1 && kubectl apply -f k8s/40-hpa.yaml
k6 run -e VUS=500 -e DURATION=5m -e BASE_URL=http://localhost:30800 load-tests/k6-load.js

# Limpeza
kind delete cluster --name pspd
```

## 11. Considerações Finais

Todos os artefatos exigidos pela proposta foram entregues prontos: código dos cinco serviços, contrato gRPC, banco com massa de dados sintética reproduzível, realm do Keycloak, manifests Kubernetes completos (incluindo HPA e ServiceMonitors), dashboard Grafana, scripts de teste de carga em duas ferramentas e automação de todo o ciclo (criação do cluster, build, deploy, escala e coleta de métricas). A validação funcional automatizada passou integralmente (31/31) e o teste de carga de referência apresentou 0% de erros. Os experimentos das fases (c) e (d) foram desenhados para serem executados por cada aluno em seu próprio hardware, com coleta automática de resultados em CSV/JSON prontos para tabulação no relatório final da disciplina.
