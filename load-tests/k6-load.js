// ============================================================
// k6-load.js — Teste de carga da aplicação do Hospital Universitário
//
// Simula o comportamento real dos três perfis de usuário
// (médico, estagiário, pesquisador) contra a API Gateway.
//
// Uso (número de usuários simultâneos via variável VUS):
//   k6 run -e VUS=10   -e BASE_URL=http://localhost:30800 k6-load.js
//   k6 run -e VUS=50   ...
//   k6 run -e VUS=100  ...
//   k6 run -e VUS=500  ...
//   k6 run -e VUS=1000 ...
//
// Exportando resultados para análise posterior:
//   k6 run -e VUS=100 --summary-export=resultados/k6-100vus.json k6-load.js
// ============================================================
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:30800';
const VUS = parseInt(__ENV.VUS || '10');
const DURATION = __ENV.DURATION || '3m';

// Métricas customizadas (além das nativas http_req_duration etc.)
const errorRate = new Rate('app_error_rate');
const loginTime = new Trend('login_duration', true);
const queryTime = new Trend('query_duration', true);

export const options = {
  stages: [
    { duration: '30s', target: VUS },   // rampa de subida
    { duration: DURATION, target: VUS }, // carga sustentada
    { duration: '15s', target: 0 },     // rampa de descida
  ],
  thresholds: {
    http_req_failed: ['rate<0.05'],           // taxa de erro < 5%
    http_req_duration: ['p(95)<2000'],        // p95 < 2s
  },
};

// Perfis de usuário com as consultas que cada um realiza
const PROFILES = [
  {
    username: 'med.cardoso', role: 'MEDICO', weight: 4,
    queries: [
      '/api/patients',
      '/api/patients/P000001/summary',
      '/api/patients/P000005/history',
      '/api/patients/P000009/labs',
      '/api/patients/P000013/medications',
    ],
  },
  {
    username: 'med.souza', role: 'MEDICO', weight: 2,
    queries: ['/api/patients', '/api/patients/P000002/summary', '/api/patients/P000006/labs'],
  },
  {
    username: 'est.oliveira', role: 'ESTAGIARIO', weight: 2,
    queries: ['/api/patients', '/api/patients/P000001/summary', '/api/patients/P000005/labs'],
  },
  {
    username: 'pesq.ramos', role: 'PESQUISADOR', weight: 2,
    queries: [
      '/api/research/projects',
      '/api/research/cohort/DIABETES/stats',
      '/api/research/cohort/HIPERTENSAO/stats',
    ],
  },
];

// Expande por peso para sorteio ponderado
const WEIGHTED = PROFILES.flatMap(p => Array(p.weight).fill(p));

// Cache de tokens por VU (evita logar a cada iteração; token dura 1h)
const tokens = {};

function getToken(profile) {
  const key = profile.username;
  if (tokens[key] && Date.now() < tokens[key].exp) return tokens[key].value;
  const start = Date.now();
  const res = http.post(`${BASE_URL}/auth/login`,
    JSON.stringify({ username: profile.username, password: 'pspd123' }),
    { headers: { 'Content-Type': 'application/json' }, tags: { name: 'login' } });
  loginTime.add(Date.now() - start);
  const ok = check(res, { 'login 200': r => r.status === 200 });
  errorRate.add(!ok);
  if (!ok) return null;
  const token = res.json('access_token');
  tokens[key] = { value: token, exp: Date.now() + 50 * 60 * 1000 };
  return token;
}

export default function () {
  const profile = WEIGHTED[Math.floor(Math.random() * WEIGHTED.length)];
  const token = getToken(profile);
  if (!token) { sleep(1); return; }

  const path = profile.queries[Math.floor(Math.random() * profile.queries.length)];
  const start = Date.now();
  const res = http.get(`${BASE_URL}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
    tags: { name: path.replace(/P\d+/, 'P{id}') },
  });
  queryTime.add(Date.now() - start);

  const ok = check(res, {
    'status 200': r => r.status === 200,
    'corpo não vazio': r => r.body && r.body.length > 2,
  });
  errorRate.add(!ok);

  sleep(Math.random() * 2 + 0.5);  // think time: 0,5–2,5 s
}

export function handleSummary(data) {
  const m = data.metrics;
  const line = [
    `VUs=${VUS}`,
    `reqs=${m.http_reqs ? m.http_reqs.values.count : 0}`,
    `throughput=${m.http_reqs ? m.http_reqs.values.rate.toFixed(1) : 0}/s`,
    `lat_avg=${m.http_req_duration ? m.http_req_duration.values.avg.toFixed(1) : 0}ms`,
    `lat_p95=${m.http_req_duration ? m.http_req_duration.values['p(95)'].toFixed(1) : 0}ms`,
    `err=${m.http_req_failed ? (m.http_req_failed.values.rate * 100).toFixed(2) : 0}%`,
  ].join('  ');
  console.log('\n===== RESUMO DO CENÁRIO =====\n' + line + '\n=============================');
  return { stdout: JSON.stringify(data, null, 2).slice(0, 0) + '' , [`summary-${VUS}vus.json`]: JSON.stringify(data, null, 2) };
}
