# Guia 02 - Validação Funcional (Fase a)

Antes de orquestrar a aplicação no Kubernetes, é recomendável validar o funcionamento da arquitetura e as regras de negócio em um ambiente simplificado usando o **Docker Compose**. Isso atende à Fase (a) do projeto.

## 1. Subindo o Ambiente Local

Na raiz do projeto, execute:

```bash
# Constrói as imagens e sobe os containers em background
docker compose up -d --build
```

O Docker Compose iniciará 7 containers:
- `postgres`: Banco de dados relacional.
- `keycloak`: Servidor de identidade.
- `authorization`, `patient-data`, `data-transform`: Microsserviços gRPC.
- `api-gateway`: Ponto de entrada REST.
- `frontend`: Interface Web.

Para verificar se tudo está rodando:
```bash
docker compose ps
```

## 2. Acessando a Aplicação

Abra o navegador em: **http://localhost:8081**

Você verá a tela de login do Portal Clínico. Use as seguintes credenciais de teste (todas possuem a senha `pspd123`):

| Usuário | Perfil | Permissões |
| --- | --- | --- |
| `med.cardoso` | Médico | Acesso FULL a seus pacientes |
| `est.oliveira` | Estagiário | Acesso PARTIAL aos pacientes supervisionados por med.cardoso |
| `pesq.ramos` | Pesquisador | Acesso ANONYMIZED/AGGREGATED às coortes DIABETES e HIPERTENSAO |

### Testando Regras (Manualmente)
1. Faça login como **Médico** (`med.cardoso`) e clique em "Resumo clínico". Você verá o CPF e a data de nascimento do paciente.
2. Saia e faça login como **Estagiário** (`est.oliveira`). No resumo clínico do mesmo paciente, o CPF não estará presente e a data de nascimento terá virado uma faixa etária (ex: "60+").
3. Tente acessar o resumo clínico de um paciente de outro médico (ex: altere o ID no campo para `P000002`). O sistema retornará erro 403 (Acesso Negado).
4. Faça login como **Pesquisador** (`pesq.ramos`). Em "Coorte", você verá uma lista de pacientes sem nomes e com IDs modificados (hashes).

## 3. Validação Funcional Automatizada

O projeto inclui um script que testa todas as regras de autorização, anonimização e endpoints de forma automatizada.

Execute no terminal:
```bash
./scripts/validate-functional.sh
```

**Saída esperada:**
O script fará dezenas de requisições à API Gateway validando os status HTTP (200, 401, 403) e o conteúdo dos JSONs (presença ou ausência de campos sensíveis conforme o perfil). No final, exibirá `Validação funcional COMPLETA ✔`.

## 4. Encerrando o Ambiente

Após validar, derrube o ambiente do Docker Compose para liberar as portas para o Kubernetes:

```bash
docker compose down -v
```

> **Nota sobre o `-v`:** Isso apaga o volume do banco de dados local. Não se preocupe, o script de inicialização do K8S recriará a massa de dados.
