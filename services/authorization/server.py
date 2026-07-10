#!/usr/bin/env python3
"""
Authorization Service (gRPC)

Responsável por decidir se um usuário pode realizar uma consulta e em qual
nível de acesso (FULL, PARTIAL, ANONYMIZED, AGGREGATED), consultando as
tabelas user_patient_assignments e projects no PostgreSQL:

  - MEDICO      -> só acessa pacientes vinculados a ele    => ALLOW + FULL
  - ESTAGIARIO  -> só acessa pacientes supervisionados     => ALLOW + PARTIAL
  - PESQUISADOR -> só acessa coortes de projetos aprovados
                   e vigentes                              => ALLOW + ANONYMIZED
                   (consultas de estatística)              => ALLOW + AGGREGATED
  - qualquer outro caso                                    => DENY

Expõe métricas Prometheus em HTTP na porta 9100 (/metrics).
"""
import os
import time
import logging
from concurrent import futures
from datetime import date

import grpc
import psycopg2
import psycopg2.pool
from prometheus_client import start_http_server, Counter, Histogram

import hospital_pb2
import hospital_pb2_grpc

logging.basicConfig(level=logging.INFO, format="%(asctime)s [authz] %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ----------------------------- métricas -----------------------------
GRPC_REQUESTS = Counter(
    "grpc_requests_total", "Total de chamadas gRPC recebidas",
    ["service", "method", "code"])
GRPC_LATENCY = Histogram(
    "grpc_request_duration_seconds", "Duração das chamadas gRPC",
    ["service", "method"])
AUTHZ_DECISIONS = Counter(
    "authz_decisions_total", "Decisões de autorização tomadas",
    ["decision", "level", "role"])
DB_QUERIES = Counter("db_queries_total", "Consultas SQL executadas", ["query"])

DB_CONFIG = dict(
    host=os.getenv("DB_HOST", "postgres"),
    port=int(os.getenv("DB_PORT", "5432")),
    dbname=os.getenv("DB_NAME", "hospital"),
    user=os.getenv("DB_USER", "hospital"),
    password=os.getenv("DB_PASSWORD", "hospital123"),
)

POOL = None


def get_pool():
    """Cria o pool de conexões sob demanda (com tentativas de reconexão)."""
    global POOL
    if POOL is None:
        POOL = psycopg2.pool.SimpleConnectionPool(1, 10, **DB_CONFIG)
    return POOL


def query(sql: str, params: tuple, metric: str):
    """Executa uma consulta devolvendo todas as linhas."""
    DB_QUERIES.labels(query=metric).inc()
    pool = get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        pool.putconn(conn)


# Tipos de consulta que envolvem um paciente específico
PATIENT_QUERIES = {"ResumoClinico", "HistoricoClinico", "Exames", "Medicamentos"}
# Tipos de consulta de pesquisa
RESEARCH_QUERIES = {"Coorte", "EstatisticasCoorte", "Projetos"}


class AuthorizationServicer(hospital_pb2_grpc.AuthorizationServiceServicer):

    def CheckAccess(self, request, context):
        start = time.time()
        code = "OK"
        try:
            resp = self._decide(request)
            AUTHZ_DECISIONS.labels(
                decision="ALLOW" if resp.allowed else "DENY",
                level=resp.access_level or "NONE",
                role=request.role).inc()
            return resp
        except Exception as exc:  # noqa: BLE001
            code = "INTERNAL"
            log.exception("Erro em CheckAccess")
            context.abort(grpc.StatusCode.INTERNAL, str(exc))
        finally:
            GRPC_REQUESTS.labels("authorization", "CheckAccess", code).inc()
            GRPC_LATENCY.labels("authorization", "CheckAccess").observe(time.time() - start)

    # ------------------------- regras de negócio -------------------------
    def _decide(self, req) -> hospital_pb2.AccessResponse:
        role = req.role.upper()

        if role == "MEDICO":
            return self._decide_medico(req)
        if role == "ESTAGIARIO":
            return self._decide_estagiario(req)
        if role == "PESQUISADOR":
            return self._decide_pesquisador(req)

        return hospital_pb2.AccessResponse(
            allowed=False, access_level="", reason=f"Papel desconhecido: {req.role}")

    def _decide_medico(self, req):
        if req.query_type == "ListaPacientes":
            return hospital_pb2.AccessResponse(
                allowed=True, access_level="FULL",
                reason="Médico pode listar seus próprios pacientes")
        if req.query_type in PATIENT_QUERIES:
            rows = query(
                "SELECT 1 FROM user_patient_assignments "
                "WHERE username=%s AND patient_id=%s AND link_type='medico' AND status='Ativo'",
                (req.username, req.patient_id), "check_medico_vinculo")
            if rows:
                return hospital_pb2.AccessResponse(
                    allowed=True, access_level="FULL",
                    reason="Paciente vinculado ao médico")
            return hospital_pb2.AccessResponse(
                allowed=False, access_level="",
                reason="Paciente não vinculado a este médico")
        return hospital_pb2.AccessResponse(
            allowed=False, access_level="",
            reason=f"Consulta '{req.query_type}' não permitida para médicos")

    def _decide_estagiario(self, req):
        if req.query_type == "ListaPacientes":
            return hospital_pb2.AccessResponse(
                allowed=True, access_level="PARTIAL",
                reason="Estagiário pode listar pacientes supervisionados")
        if req.query_type in PATIENT_QUERIES:
            rows = query(
                "SELECT supervisor FROM user_patient_assignments "
                "WHERE username=%s AND patient_id=%s AND link_type='estagiario' AND status='Ativo'",
                (req.username, req.patient_id), "check_estagiario_vinculo")
            if rows:
                return hospital_pb2.AccessResponse(
                    allowed=True, access_level="PARTIAL",
                    reason="Paciente em atividade supervisionada",
                    supervisor=rows[0][0] or "")
            return hospital_pb2.AccessResponse(
                allowed=False, access_level="",
                reason="Paciente não está em atividade supervisionada deste estagiário")
        return hospital_pb2.AccessResponse(
            allowed=False, access_level="",
            reason=f"Consulta '{req.query_type}' não permitida para estagiários")

    def _decide_pesquisador(self, req):
        if req.query_type == "Projetos":
            return hospital_pb2.AccessResponse(
                allowed=True, access_level="AGGREGATED",
                reason="Pesquisador pode listar seus próprios projetos")
        if req.query_type in {"Coorte", "EstatisticasCoorte"}:
            rows = query(
                "SELECT status, valid_until FROM projects "
                "WHERE researcher=%s AND condition_code=%s",
                (req.username, req.cohort_code), "check_projeto")
            if not rows:
                return hospital_pb2.AccessResponse(
                    allowed=False, access_level="",
                    reason="Pesquisador não possui projeto para esta condição clínica")
            status, valid_until = rows[0]
            if status != "Aprovado":
                return hospital_pb2.AccessResponse(
                    allowed=False, access_level="",
                    reason=f"Projeto com status '{status}' (não aprovado)")
            if valid_until < date.today():
                return hospital_pb2.AccessResponse(
                    allowed=False, access_level="",
                    reason=f"Projeto expirado em {valid_until}")
            level = "AGGREGATED" if req.query_type == "EstatisticasCoorte" else "ANONYMIZED"
            return hospital_pb2.AccessResponse(
                allowed=True, access_level=level,
                reason="Projeto aprovado e vigente")
        return hospital_pb2.AccessResponse(
            allowed=False, access_level="",
            reason=f"Consulta '{req.query_type}' não permitida para pesquisadores")


def serve():
    metrics_port = int(os.getenv("METRICS_PORT", "9100"))
    grpc_port = int(os.getenv("GRPC_PORT", "50051"))
    start_http_server(metrics_port)
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=int(os.getenv("GRPC_WORKERS", "10"))))
    hospital_pb2_grpc.add_AuthorizationServiceServicer_to_server(AuthorizationServicer(), server)
    server.add_insecure_port(f"[::]:{grpc_port}")
    server.start()
    log.info("Authorization Service ouvindo gRPC em :%s e métricas em :%s", grpc_port, metrics_port)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
