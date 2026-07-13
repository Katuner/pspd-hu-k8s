# Guia de Reprodução dos Testes de Carga

Este documento descreve o passo a passo para que os membros da equipe possam reproduzir os testes de carga e escalabilidade realizados no projeto (utilizando K6, Kubernetes e Grafana).

## Pré-requisitos
- Ter o **`kubectl`** instalado no seu terminal.
- Ter o arquivo de configuração **`kubeconfig-grupo-5.yaml`** na raiz do projeto (usado para autenticação no cluster).
- Ter o executável do K6 (**`k6.exe`**) na raiz do projeto (para usuários Windows).
- Acesso ao **Grafana** para observabilidade: `https://grafana.kiriland.unb.br` (Usuário: `admgrp05` | Senha: `123456`).

---

## Passo 1: Subir a Aplicação (Baseline - 1 Réplica)
Para iniciar os serviços com apenas 1 réplica (cenário de Baseline), execute na raiz do projeto:

```bash
kubectl apply -f k8s-grupo5/30-microservices.yaml --kubeconfig=kubeconfig-grupo-5.yaml
```

Verifique se todos os pods estão com status `Running`:
```bash
kubectl get pods -n grupo-5 --kubeconfig=kubeconfig-grupo-5.yaml -w
```
*(Pressione `Ctrl+C` para sair do modo de acompanhamento `watch`).*

---

## Passo 2: Executar o Teste de Carga (K6)
Para simplificar a execução no Windows, criamos um script em PowerShell.

1. Abra o **PowerShell** na raiz do projeto.
2. Execute o script:
   ```powershell
   .\run-k6.ps1
   ```
3. O script irá perguntar a quantidade de usuários simultâneos (VUs). Você pode começar testando com **100**, depois **500** e **1000**, conforme detalhado no `RELATORIO_PROJETO.md`.

**Se quiser rodar o comando manualmente (sem o script):**
```powershell
$env:BASE_URL = "https://kiriland.unb.br/grupo5"
.\k6.exe run -e VUS=100 -e BASE_URL=$env:BASE_URL -e DURATION=1m load-tests\k6-load.js
```

---

## Passo 3: Teste de Escalabilidade Horizontal Manual (3 Réplicas)
Para testar a resiliência e a melhoria de latência, escale manualmente os *Deployments* para 3 réplicas:

```bash
kubectl scale deployment api-gateway --replicas=3 -n grupo-5 --kubeconfig=kubeconfig-grupo-5.yaml
kubectl scale deployment authorization-service --replicas=3 -n grupo-5 --kubeconfig=kubeconfig-grupo-5.yaml
kubectl scale deployment patient-data-service --replicas=3 -n grupo-5 --kubeconfig=kubeconfig-grupo-5.yaml
kubectl scale deployment data-transform-service --replicas=3 -n grupo-5 --kubeconfig=kubeconfig-grupo-5.yaml
```

> **Aviso:** Lembrando que reduzimos os limites de CPU (`limits.cpu`) dos manifestos `.yaml` para burlar a cota estrita de `ResourceQuotas` do cluster e permitir a subida das 3 réplicas simultâneas.

Aguarde os novos pods subirem e, em seguida, **repita o Passo 2** injetando uma carga de **500** ou **1000** VUs para comparar a queda da latência.

---

## Passo 4: Autoscaling com HPA (Horizontal Pod Autoscaler)
Para observar o Kubernetes criando e destruindo pods automaticamente baseado no tráfego e limite de 60% de CPU:

1. Aplique o manifesto do HPA:
   ```bash
   kubectl apply -f k8s-grupo5/40-hpa.yaml --kubeconfig=kubeconfig-grupo-5.yaml
   ```
2. Em um terminal separado, deixe o comando abaixo rodando para acompanhar o número de réplicas em tempo real:
   ```bash
   kubectl get hpa -n grupo-5 --kubeconfig=kubeconfig-grupo-5.yaml -w
   ```
3. Em outro terminal, **repita o Passo 2** rodando o script `run-k6.ps1` com uma carga pesada (ex: 500 VUs).
4. Volte ao terminal do HPA e observe a coluna `REPLICAS` aumentar gradualmente. Ao finalizar o script do k6, após um tempo, as réplicas começarão a diminuir.

---

## Passo 5: Acompanhamento no Grafana
Durante as execuções do K6 (Passos 2, 3 e 4), deixe a aba do **Grafana** aberta nos dashboards. Observe ativamente:
- **Throughput:** Aumento no número de requisições por segundo.
- **Latência:** Tempo de resposta disparando com 1 réplica sob alta carga (500+ VUs) e despencando após escalar para 3 réplicas.
- **CPU/Memória:** O comportamento dos recursos acompanhando as requisições.
- **Erros HTTP/TCP:** Observe se estão ocorrendo falhas por timeout (conexões rejeitadas) nos testes de 1000 VUs.

kubectl port-forward svc/frontend 8080:80 -n grupo-5 --kubeconfig=kubeconfig-grupo-5.yaml