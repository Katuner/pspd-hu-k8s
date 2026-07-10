# Guia 04 - Escalabilidade e Testes de Carga (Fases c e d)

Nesta etapa, submeteremos a aplicação a testes de carga utilizando a ferramenta [k6](https://k6.io/) (há também uma versão em Locust disponível em `load-tests/locustfile.py` se preferir). O objetivo é comparar o comportamento do sistema com 1 réplica, com 3 réplicas (escala manual) e com autoscaling (HPA).

## 1. Instalação da Ferramenta de Teste

Para instalar o k6 (Linux/Debian):
```bash
sudo gpg -k
sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" | sudo tee /etc/apt/sources.list.d/k6.list
sudo apt-get update
sudo apt-get install k6
```
*(Para Windows/Mac, consulte a [documentação do k6](https://k6.io/docs/get-started/installation/).)*

## 2. O Script de Teste (`k6-load.js`)

O script `load-tests/k6-load.js` simula o comportamento real do sistema:
- Possui "Virtual Users" (VUs) com perfis ponderados (Médicos fazem mais requisições que Pesquisadores).
- Os VUs fazem login, obtêm o JWT e executam chamadas aleatórias (lista de pacientes, resumos, coortes).
- Possui um *think time* (pausa de 0.5 a 2.5s) entre as requisições para simular um humano lendo a tela.

## 3. Fase (c): Escalabilidade Horizontal Manual

### Cenário Base (1 Réplica)
Certifique-se de que há apenas 1 réplica de cada serviço:
```bash
./scripts/scale.sh 1
```

Execute a bateria completa de testes (10, 50, 100, 500 e 1000 VUs). O script `run-all-scenarios.sh` fará isso automaticamente e salvará as métricas de CPU/Memória e o sumário do k6 em uma pasta `resultados/`:
```bash
LABEL=1replica ./load-tests/run-all-scenarios.sh
```

### Cenário Escalado (3 Réplicas)
Aumente manualmente o número de réplicas para distribuir a carga entre os nós workers do cluster:
```bash
./scripts/scale.sh 3
```

Execute a bateria novamente:
```bash
LABEL=3replicas ./load-tests/run-all-scenarios.sh
```

**Análise esperada:** Compare os arquivos gerados. No cenário de 3 réplicas, o *throughput* (requisições por segundo) com 500 e 1000 VUs deve ser maior, e a latência (p95) deve ser menor, pois a carga de CPU (conversão FHIR e validação JWT) foi distribuída.

## 4. Fase (d): Autoscaling (HPA)

O Horizontal Pod Autoscaler ajusta dinamicamente o número de réplicas baseado no uso de CPU.

Primeiro, volte para 1 réplica e aplique as regras do HPA:
```bash
./scripts/scale.sh 1
kubectl apply -f k8s/40-hpa.yaml
```

Acompanhe o status do HPA em outro terminal:
```bash
watch kubectl -n hospital get hpa
```

Execute um teste de carga contínuo (ex: 500 VUs por 5 minutos):
```bash
k6 run -e VUS=500 -e DURATION=5m -e BASE_URL=http://localhost:30800 load-tests/k6-load.js
```

**Análise esperada:** 
1. Conforme a carga entra, o uso de CPU (`TARGETS`) ultrapassará 60%.
2. O HPA criará novos pods (`REPLICAS` aumentará de 1 até o limite de 10).
3. A latência da aplicação, que inicialmente pode subir, começará a cair à medida que os novos pods entrarem em operação.
4. Após o fim do teste, o HPA aguardará um tempo de estabilização (*scaleDown stabilizationWindow*) e reduzirá as réplicas gradativamente.

> **Dica:** Abra o Grafana (http://localhost:30900) durante este teste. O painel "Quantidade de pods por deployment" mostrará a curva do autoscaling em tempo real.
