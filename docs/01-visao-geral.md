# Guia 01 - Visão Geral e Arquitetura

Este projeto atende à proposta da disciplina de PSPD para criação de um sistema de monitoramento e observabilidade focado em dados de saúde.

## Arquitetura Proposta vs Implementada

A especificação do projeto (Figuras 1 e 2 do PDF) exigia uma API Gateway recebendo requisições HTTP, consultando um Authorization Service, buscando dados no Patient Data Service e os transformando via Data Transform Service, devolvendo o resultado em JSON (HL7/FHIR).

### Stack Tecnológica Escolhida e Justificativas

1. **API Gateway (FastAPI)**
   - **Justificativa:** O FastAPI é extremamente performático para chamadas assíncronas (I/O bound). Ele recebe requisições HTTP REST do frontend, valida o token JWT gerado pelo Keycloak localmente (sem precisar de chamadas de rede extras) e atua como cliente gRPC assíncrono para os demais microsserviços.
   - **Métricas:** Expõe `/metrics` (Prometheus) com a duração das requisições HTTP, taxa de erros e falhas de autenticação.

2. **Microsserviços Internos (gRPC em Python)**
   - **Serviços:** `authorization`, `patient-data`, `data-transform`.
   - **Justificativa:** A comunicação entre os microsserviços utiliza gRPC (HTTP/2 + Protobuf) por ser mais eficiente, ter menor payload (binário) e contratos estritos (`hospital.proto`), reduzindo latência em um cenário de alto tráfego.
   - **Métricas:** Cada serviço expõe uma porta HTTP dedicada (`9100`) servindo métricas do Prometheus via biblioteca `prometheus-client`.

3. **Autenticação (Keycloak)**
   - **Justificativa:** Padrão de mercado para IAM (Identity and Access Management). Implementa OAuth2 e OpenID Connect. O Frontend redireciona o usuário (ou captura credenciais via password grant) e recebe um JWT. O Gateway valida a assinatura do JWT via chave pública do Keycloak.

4. **Banco de Dados (PostgreSQL)**
   - **Justificativa:** Banco relacional robusto. O projeto inclui um script em Python (`database/generate_seed.py`) que gerou uma massa de dados sintética de 200 pacientes com mais de 1000 registros clínicos associados, garantindo que os testes de carga tenham dados reais para processar.

5. **Frontend (HTML/JS + Nginx)**
   - **Justificativa:** Uma Single Page Application leve que facilita a demonstração. O Nginx atua como proxy reverso para o Gateway, contornando problemas de CORS e simplificando o acesso em qualquer ambiente (Docker Compose ou Kubernetes).

6. **Infraestrutura (Kubernetes + kind)**
   - **Justificativa:** O `kind` permite criar um cluster K8S multinó local usando containers Docker como nós. A topologia foi definida como 1 control-plane (master) e 3 workers, atendendo estritamente ao requisito da disciplina.

7. **Monitoramento (Prometheus + Grafana)**
   - **Justificativa:** A stack `kube-prometheus-stack` (via Helm) instala toda a infraestrutura necessária (Prometheus Operator, Alertmanager, Grafana, Node Exporter, kube-state-metrics). Usamos *ServiceMonitors* customizados para raspar métricas de negócio dos nossos microsserviços.

## Regras de Negócio e Autorização (RBAC)

O sistema implementa as seguintes regras:
- **Médicos (`MEDICO`):** Acesso total (FULL) apenas aos pacientes vinculados a eles.
- **Estagiários (`ESTAGIARIO`):** Acesso parcial (PARTIAL) aos pacientes sob sua supervisão. O `data-transform` remove o CPF e substitui a data de nascimento exata por uma faixa etária.
- **Pesquisadores (`PESQUISADOR`):** Acesso a coortes de pacientes aprovadas em seus projetos.
  - O endpoint de coorte devolve dados anonimizados (ANONYMIZED), removendo nomes, contatos e aplicando hash nos IDs.
  - O endpoint de estatísticas devolve dados agregados (AGGREGATED) via recurso FHIR `MeasureReport`.

Na próxima etapa, veremos como rodar a aplicação localmente via Docker Compose para validar essas regras.
