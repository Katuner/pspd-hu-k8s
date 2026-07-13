# 🚀 Guia de Bolso para a Apresentação (Resumo Técnico)

Se o professor fizer perguntas técnicas difíceis, este é o roteiro exato de **TUDO** que enfrentamos e como resolvemos. Leia e entenda os conceitos abaixo para dominar a apresentação.

---

## 1. O Problema de Concorrência do API Gateway (Event Loop Block)
**O que aconteceu:** Nos primeiros testes, o API Gateway estava engasgando muito rápido.
**A causa técnica:** O Gateway foi feito em `FastAPI`, que é assíncrono (`async def`). Porém, as chamadas para os microsserviços via gRPC eram **síncronas** (bloqueantes). No Python, quando você faz uma chamada de rede síncrona dentro de uma função `async`, você **trava a thread principal (Event Loop)**. O Gateway ficava congelado esperando o gRPC responder e não aceitava novas requisições.
**A Solução:** Usamos a biblioteca `asyncio` e a função `await asyncio.to_thread(stub.Metodo, request)`. Isso jogou a chamada gRPC bloqueante para uma *Thread Pool* em segundo plano, liberando o Event Loop do FastAPI para continuar aceitando centenas de conexões simultâneas.

---

## 2. O Bug do PostgreSQL e a Imagem Docker (Erro de Tipagem)
**O que aconteceu:** Quando jogamos carga na rota de "Estatísticas de Coorte", a taxa de erro foi para quase 70% e a rede travou.
**A causa técnica:** O serviço `patient-data` tentou executar uma query SQL usando a função de média `AVG(value)` na tabela `clinical_events`. O problema é que a coluna `value` estava tipada como *String* (VARCHAR), e o PostgreSQL disparou a exceção: `function avg(character varying) does not exist`. Isso estourou as threads dos workers do gRPC.
**A Solução:** 
1. Abrimos o código Python (`server.py`) e alteramos a query para forçar a conversão de tipo: `AVG(CAST(value AS numeric))`.
2. Como estávamos no Kubernetes, não bastava salvar o arquivo. Tivemos que **recompilar a imagem Docker** do microsserviço (`docker build`), enviar para o Docker Hub (`docker push vinialves2020/patient-data:1.3`) e atualizar o `.yaml` do cluster para puxar a versão 1.3 corrigida.

---

## 3. O Desafio da Cota de CPU (ResourceQuotas) e Escalabilidade
**O que aconteceu:** Na Fase C, tentamos escalar tudo para 3 réplicas (`kubectl scale`), mas os pods do API Gateway não subiam, ficavam travados no status `Pending` e continuávamos com 1 réplica.
**A causa técnica:** O professor configurou uma regra de segurança no namespace `grupo-5` chamada **ResourceQuota**, impondo um teto máximo rígido de CPU (`limits.cpu: 6`). Como o nosso `api-gateway` exigia a reserva teórica de 1 CPU inteira, e os outros serviços também exigiam suas fatias, a soma de 3 réplicas de tudo passava de 6 CPUs. O Kubernetes, por segurança, bloqueou a criação.
**A Solução (DevOps Hack):** Fomos no Grafana e provamos que o consumo *real* de CPU dos pods durante os testes era ínfimo (menos de 0.2 CPU). Então, editamos os arquivos `.yaml` e **reduzimos pela metade** os `requests` e `limits` de todos os contêineres. Ao "encolher" o tamanho teórico dos pods, conseguimos enganar a restrição e couberam perfeitamente 3 réplicas de todos os serviços na cota de 6 CPUs!

---

## 4. Análise dos Testes de Carga (Onde fica o Gargalo?)
Se o professor perguntar: *"Onde estava o gargalo da aplicação de vocês?"*

**Resposta:**
1. **Com 1 Réplica (Baseline):** O gargalo foi a **Saturação de Conexões (TCP Sockets)**. O consumo de CPU ficou baixíssimo, mas o sistema formou fila. O NGINX Ingress e o único pod do API Gateway não davam conta de abrir tantas conexões simultâneas com o k6, resultando no aumento da latência (de 200ms para 2200ms) e timeouts.
2. **Com 3 Réplicas:** O balanceamento de carga interno do Kubernetes distribuiu o tráfego. A latência caiu pela metade (1200ms) e o throughput subiu.
3. **Ponto de Quebra (1000 VUs):** Aqui atingimos o "Teto Físico" da infraestrutura. Como reduzimos os limites de CPU dos pods para caber na cota (solução do item 3), a avalanche de 1000 usuários causou **CPU Throttling** (o Kubernetes pausa os contêineres por milissegundos para não estourar o limite rígido) e a rede da UnB recusou 60% das conexões por falta de portas livres (`connectex: A connection attempt failed`). 

---

## 5. Ferramentas Utilizadas (Resumo Rápido)
* **K6 (Javascript):** Ferramenta escrita em Go para injeção pesada de tráfego (Virtual Users).
* **Prometheus:** Coletor de métricas (Time-Series Database) que fazia *scraping* (coleta) da rota `:9100/metrics` de todos os nossos pods.
* **Grafana:** Painel de visualização que consultava o Prometheus para plotar os gráficos usando a linguagem PromQL.
* **HPA (Horizontal Pod Autoscaler):** Configurado para escalar sozinho de 1 a 10 pods caso o uso de CPU chegasse a 60%.
* **Secrets:** Usamos objetos opacos do Kubernetes gravados em Base64 para injetar a senha do banco de dados no ambiente, sem expor no código-fonte.
