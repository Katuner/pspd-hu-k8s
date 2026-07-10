# Hospital Universitário — Portal Clínico (HL7/FHIR)

Projeto desenvolvido para a disciplina de **Programação para Sistemas Paralelos e Distribuídos (PSPD)**.
Implementa uma arquitetura de microsserviços em Kubernetes focada em **Monitoramento e Observabilidade** para dados de saúde (HL7/FHIR).

## Estrutura do Projeto

```
pspd-hu-k8s/
├── database/         # Schemas SQL e script gerador de massa de dados (seed)
├── docker-compose.yml# Orquestração local para validação funcional rápida
├── docs/             # Guias passo a passo explicativos detalhados
├── grafana/          # Dashboards pré-configurados do Grafana
├── k8s/              # Manifests Kubernetes (Deployments, HPA, Prometheus)
├── keycloak/         # Configuração e Realm de autenticação (OAuth2/OIDC)
├── load-tests/       # Scripts de teste de carga (k6 e Locust)
├── proto/            # Contratos gRPC compartilhados (.proto)
├── scripts/          # Automação (build, deploy, scale, testes, validação)
└── services/         # Código-fonte da aplicação
    ├── api-gateway/    # FastAPI (REST, validação JWT, proxy gRPC)
    ├── authorization/  # Microsserviço gRPC (RBAC, regras de negócio)
    ├── data-transform/ # Microsserviço gRPC (Conversão HL7/FHIR, Anonimização)
    ├── frontend/       # Interface Web SPA (HTML/JS) servida via Nginx
    └── patient-data/   # Microsserviço gRPC (Acesso ao PostgreSQL)
```

## Documentação e Guias

A documentação foi dividida em guias passo a passo para facilitar o entendimento e a reprodução do ambiente por qualquer aluno. Leia na seguinte ordem:

1. **[Guia 01 - Visão Geral e Arquitetura](docs/01-visao-geral.md)**: Entenda o fluxo de dados, a stack tecnológica escolhida e as justificativas para cada decisão.
2. **[Guia 02 - Validação Funcional (Docker Compose)](docs/02-validacao-funcional.md)**: Como subir a aplicação localmente (fase *a*) e testar as regras de autorização e anonimização.
3. **[Guia 03 - Configuração do Cluster Kubernetes](docs/03-cluster-kubernetes.md)**: Como criar o cluster *kind* com 1 master e 3 workers, instalar o Prometheus/Grafana e fazer o deploy da aplicação (fase *b*).
4. **[Guia 04 - Escalabilidade e Testes de Carga](docs/04-escalabilidade-testes.md)**: Como rodar os testes de carga (k6/Locust) e analisar o comportamento do sistema com escala manual e automática via HPA (fases *c* e *d*).
5. **[Guia 05 - Observabilidade e Métricas](docs/05-observabilidade.md)**: Como interpretar o Dashboard do Grafana, métricas customizadas de negócio e de infraestrutura.

## Requisitos de Ambiente

Para reproduzir este projeto, seu ambiente precisa de:
- **Docker** e **Docker Compose**
- **kind** (Kubernetes in Docker)
- **kubectl** e **Helm**
- **k6** (ou Python + Locust) para testes de carga
- **bash**, **curl**

> **Nota:** Todos os comandos e instalações estão detalhados no *Guia 03* e *Guia 04*.
