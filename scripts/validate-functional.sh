#!/usr/bin/env bash
# ============================================================
# validate-functional.sh — Validação funcional (fase a)
# Testa autenticação, autorização (ALLOW/DENY), anonimização
# (FULL/PARTIAL/ANONYMIZED/AGGREGATED) e conversão HL7/FHIR.
#
# Uso:
#   ./scripts/validate-functional.sh                      # docker-compose local
#   BASE_URL=http://localhost:30800 ./scripts/validate-functional.sh  # cluster K8S
# ============================================================
set -uo pipefail
BASE_URL="${BASE_URL:-http://localhost:8000}"
PASS=0; FAIL=0

say()  { printf "\n\033[1;34m== %s ==\033[0m\n" "$1"; }
ok()   { printf "  \033[32m[PASS]\033[0m %s\n" "$1"; PASS=$((PASS+1)); }
bad()  { printf "  \033[31m[FAIL]\033[0m %s\n" "$1"; FAIL=$((FAIL+1)); }

login() {  # $1=username -> imprime access_token
  curl -s -X POST "$BASE_URL/auth/login" -H 'Content-Type: application/json' \
    -d "{\"username\":\"$1\",\"password\":\"PseudoPEP2026!\"}" |
    sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p'
}

http_code() {  # $1=path $2=token
  curl -s -o /tmp/vf_body -w '%{http_code}' "$BASE_URL$1" -H "Authorization: Bearer $2"
}

expect() {  # $1=descricao $2=path $3=token $4=status_esperado
  local code; code=$(http_code "$2" "$3")
  if [[ "$code" == "$4" ]]; then ok "$1 (HTTP $code)"; else bad "$1 (esperado $4, obtido $code)"; fi
}

body_has()    { grep -q "$1" /tmp/vf_body && ok "$2" || bad "$2"; }
body_lacks()  { grep -q "$1" /tmp/vf_body && bad "$2" || ok "$2"; }

say "1. Autenticação via Keycloak (OAuth2 password grant)"
MED=$(login med.cardoso);   [[ -n "$MED"  ]] && ok "login med.cardoso"  || bad "login med.cardoso"
EST=$(login est.oliveira);  [[ -n "$EST"  ]] && ok "login est.oliveira" || bad "login est.oliveira"
PESQ=$(login pesq.ramos);   [[ -n "$PESQ" ]] && ok "login pesq.ramos"   || bad "login pesq.ramos"
PESQ2=$(login pesq.telles); [[ -n "$PESQ2" ]] && ok "login pesq.telles" || bad "login pesq.telles"
BADLOGIN=$(login med.cardoso_senhaerrada); [[ -z "$BADLOGIN" ]] && ok "login inválido rejeitado" || bad "login inválido aceito"

say "2. Médico — acesso FULL a pacientes vinculados"
expect "lista de pacientes"          "/api/patients"                    "$MED" 200
expect "resumo clínico P000001"      "/api/patients/P000001/summary"    "$MED" 200
body_has '"resourceType": "Bundle"'  "resposta em FHIR Bundle"
body_has '2.16.840.1.113883.13.237'  "FULL: CPF presente"
body_has '"birthDate"'               "FULL: data de nascimento presente"
expect "histórico clínico"           "/api/patients/P000001/history"    "$MED" 200
expect "exames laboratoriais"        "/api/patients/P000001/labs"       "$MED" 200
expect "medicamentos"                "/api/patients/P000001/medications" "$MED" 200
expect "DENY paciente de outro médico" "/api/patients/P000002/summary"  "$MED" 403

say "3. Estagiário — acesso PARTIAL (anonimização parcial)"
expect "resumo clínico supervisionado" "/api/patients/P000001/summary"  "$EST" 200
body_lacks '2.16.840.1.113883.13.237' "PARTIAL: CPF removido"
body_lacks '"birthDate"'              "PARTIAL: data exata de nascimento removida"
body_has 'faixa-etaria'               "PARTIAL: faixa etária presente"
expect "DENY paciente não supervisionado" "/api/patients/P000002/summary" "$EST" 403

say "4. Pesquisador — ANONYMIZED / AGGREGATED"
expect "lista de projetos"            "/api/research/projects"                 "$PESQ" 200
expect "coorte DIABETES (anonimizada)" "/api/research/cohort/DIABETES"         "$PESQ" 200
body_has '"id": "hash'                "ANONYMIZED: identificador pseudonimizado"
body_lacks '"name"'                   "ANONYMIZED: nomes removidos"
body_lacks '"city"'                   "ANONYMIZED: cidade removida"
expect "estatísticas agregadas"       "/api/research/cohort/DIABETES/stats"    "$PESQ" 200
body_has 'MeasureReport'              "AGGREGATED: recurso FHIR MeasureReport"
body_has 'distribuicaoSexo'           "AGGREGATED: distribuição por sexo"
expect "DENY coorte sem projeto"      "/api/research/cohort/ASMA/stats"        "$PESQ" 403
expect "DENY projeto expirado (PNEUMONIA)" "/api/research/cohort/PNEUMONIA/stats" "$PESQ2" 403

say "5. Segurança do gateway (JWT)"
CODE=$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/api/patients")
[[ "$CODE" == "401" ]] && ok "requisição sem token rejeitada (401)" || bad "sem token: esperado 401, obtido $CODE"
CODE=$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/api/patients" -H "Authorization: Bearer token-falso")
[[ "$CODE" == "401" ]] && ok "token inválido rejeitado (401)" || bad "token falso: esperado 401, obtido $CODE"

say "RESULTADO"
echo "  PASS: $PASS | FAIL: $FAIL"
[[ $FAIL -eq 0 ]] && echo "  Validação funcional COMPLETA ✔" || { echo "  Há falhas a corrigir ✘"; exit 1; }
