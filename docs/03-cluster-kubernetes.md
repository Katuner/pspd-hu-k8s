# Guia 03 - Configuração do Cluster Kubernetes (Fase b)

Esta seção atende à exigência de criação de um cluster Kubernetes com **1 nó mestre e 3 nós workers**. Utilizaremos o `kind` (Kubernetes in Docker).

## 1. Pré-requisitos

Certifique-se de ter instalado:
- [Docker](https://docs.docker.com/get-docker/)
- [kind](https://kind.sigs.k8s.io/docs/user/quick-start/#installation)
- [kubectl](https://kubernetes.io/docs/tasks/tools/)
- [Helm](https://helm.sh/docs/intro/install/) (Gerenciador de pacotes do K8S, usado para instalar o Prometheus/Grafana)

## 2. Criação do Cluster e Instalação da Infraestrutura

O projeto possui um script automatizado que:
1. Lê o arquivo `k8s/kind-cluster.yaml` e cria o cluster com a topologia exigida.
2. Instala o `metrics-server` (necessário para o autoscaling - HPA).
3. Instala a stack de monitoramento (`kube-prometheus-stack`) via Helm.
4. Instala o Kubernetes Dashboard.

Execute:
```bash
./scripts/setup-cluster.sh
```

> **Atenção:** A instalação da stack do Prometheus pode demorar alguns minutos. O script aguardará a conclusão.

Verifique os nós do cluster:
```bash
kubectl get nodes
```
*Você deve ver 1 nó control-plane e 3 nós workers.*

## 3. Construção e Carga das Imagens

Como estamos usando o `kind` localmente, precisamos construir as imagens Docker e carregá-las para dentro dos nós do cluster (para não depender de um registry externo como o DockerHub).

Execute:
```bash
./scripts/build-images.sh --kind
```
*O parâmetro `--kind` garante que, após o build, as imagens sejam importadas para o cluster.*

## 4. Implantação da Aplicação

Agora, aplicaremos os manifests Kubernetes (arquivos YAML em `k8s/`) para criar o Namespace, Secrets, ConfigMaps, Deployments e Services.

Execute:
```bash
./scripts/deploy-all.sh
```

O script implantará os componentes em ordem e aguardará todos os Pods ficarem prontos (`Running`).

## 5. Acessando a Aplicação no Cluster

O cluster `kind` foi configurado para mapear portas NodePort para o seu `localhost`.

- **Frontend da Aplicação:** http://localhost:30080
- **API Gateway (Swagger UI):** http://localhost:30800/docs
- **Keycloak:** http://localhost:30880
- **Grafana:** http://localhost:30900 (Admin: `admin` / Senha: `pspd123`)
- **Prometheus:** http://localhost:30990

Acesse o Frontend no navegador e confirme que a aplicação está operando normalmente, agora dentro do Kubernetes.
