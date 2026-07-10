// ============================================================
// k6-smoke.js — Smoke test: valida rapidamente (1 VU, ~30 s) que
// todos os endpoints e perfis funcionam antes dos testes pesados.
//
//   k6 run -e BASE_URL=http://localhost:30800 k6-smoke.js
// ============================================================
import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:30800';

export const options = { vus: 1, iterations: 1 };

function login(username) {
  const res = http.post(`${BASE_URL}/auth/login`,
    JSON.stringify({ username, password: 'pspd123' }),
    { headers: { 'Content-Type': 'application/json' } });
  check(res, { [`login ${username}`]: r => r.status === 200 });
  return res.status === 200 ? res.json('access_token') : null;
}

function get(path, token, name, expected = 200) {
  const res = http.get(`${BASE_URL}${path}`, { headers: { Authorization: `Bearer ${token}` } });
  check(res, { [name]: r => r.status === expected });
  return res;
}

export default function () {
  // ---------- MÉDICO: acesso FULL ----------
  const med = login('med.cardoso');
  get('/api/patients', med, 'medico lista pacientes');
  get('/api/patients/P000001/summary', med, 'medico resumo clinico');
  get('/api/patients/P000001/history', med, 'medico historico');
  get('/api/patients/P000001/labs', med, 'medico exames');
  get('/api/patients/P000001/medications', med, 'medico medicamentos');
  // paciente de outro médico -> DENY (403)
  get('/api/patients/P000002/summary', med, 'medico DENY paciente de outro', 403);

  // ---------- ESTAGIÁRIO: acesso PARTIAL ----------
  const est = login('est.oliveira');
  get('/api/patients', est, 'estagiario lista pacientes');
  const r = get('/api/patients/P000001/summary', est, 'estagiario resumo (PARTIAL)');
  check(r, {
    'resposta PARTIAL sem CPF': resp => !resp.body.includes('urn:oid:2.16.840.1.113883.13.237'),
  });

  // ---------- PESQUISADOR: ANONYMIZED / AGGREGATED ----------
  const pesq = login('pesq.ramos');
  get('/api/research/projects', pesq, 'pesquisador projetos');
  const coorte = get('/api/research/cohort/DIABETES', pesq, 'pesquisador coorte anonimizada');
  check(coorte, {
    'coorte sem nomes reais': resp => !resp.body.includes('"name"'),
    'coorte com ids hash': resp => resp.body.includes('hash'),
  });
  get('/api/research/cohort/DIABETES/stats', pesq, 'pesquisador estatisticas agregadas');
  // coorte sem projeto aprovado -> DENY (403)
  get('/api/research/cohort/ASMA/stats', pesq, 'pesquisador DENY coorte sem projeto', 403);
  // projeto expirado (PRJ04 de pesq.telles) -> DENY
  const pesq2 = login('pesq.telles');
  get('/api/research/cohort/PNEUMONIA/stats', pesq2, 'pesquisador DENY projeto expirado', 403);

  sleep(1);
}
