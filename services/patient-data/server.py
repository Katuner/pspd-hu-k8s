#!/usr/bin/env python3
"""
Patient Data Service (gRPC)

Responsável por todas as consultas SQL ao pseudo-prontuário eletrônico
(PostgreSQL). Devolve dados brutos — a anonimização/transformação FHIR é
feita pelo Data Transform Service.

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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [patient-data] %(levelname)s %(message)s")
log = logging.getLogger(__name__)

GRPC_REQUESTS = Counter("grpc_requests_total", "Total de chamadas gRPC recebidas",
                        ["service", "method", "code"])
GRPC_LATENCY = Histogram("grpc_request_duration_seconds", "Duração das chamadas gRPC",
                         ["service", "method"])
DB_QUERIES = Counter("db_queries_total", "Consultas SQL executadas", ["query"])
DB_LATENCY = Histogram("db_query_duration_seconds", "Duração das consultas SQL", ["query"])

DB_CONFIG = dict(
    host=os.getenv("DB_HOST", "postgres"),
    port=int(os.getenv("DB_PORT", "5432")),
    dbname=os.getenv("DB_NAME", "hospital"),
    user=os.getenv("DB_USER", "hospital"),
    password=os.getenv("DB_PASSWORD", "hospital123"),
)

POOL = None


def get_pool():
    global POOL
    if POOL is None:
        POOL = psycopg2.pool.SimpleConnectionPool(2, int(os.getenv("DB_POOL_MAX", "15")), **DB_CONFIG)
    return POOL


def query(sql: str, params: tuple, metric: str):
    DB_QUERIES.labels(query=metric).inc()
    start = time.time()
    pool = get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        pool.putconn(conn)
        DB_LATENCY.labels(query=metric).observe(time.time() - start)


def row_to_patient(row) -> hospital_pb2.Patient:
    return hospital_pb2.Patient(
        patient_id=row[0], full_name=row[1], birth_date=str(row[2]),
        gender=row[3], city=row[4], state=row[5], cpf=row[6], cns=row[7])


def row_to_event(row) -> hospital_pb2.ClinicalEvent:
    return hospital_pb2.ClinicalEvent(
        event_id=row[0], patient_id=row[1], encounter_id=row[2] or "",
        event_type=row[3], event_code=row[4], description=row[5],
        event_date=str(row[6]),
        value=float(row[7]) if row[7] is not None else 0.0,
        unit=row[8] or "", has_value=row[7] is not None)


PATIENT_COLS = "patient_id, full_name, birth_date, gender, city, state, cpf, cns"
EVENT_COLS = "event_id, patient_id, encounter_id, event_type, event_code, description, event_date, value, unit"


def timed(method_name):
    """Decorator: instrumenta cada RPC com contadores e histograma."""
    def wrapper(fn):
        def inner(self, request, context):
            start = time.time()
            code = "OK"
            try:
                return fn(self, request, context)
            except Exception as exc:  # noqa: BLE001
                code = "INTERNAL"
                log.exception("Erro em %s", method_name)
                context.abort(grpc.StatusCode.INTERNAL, str(exc))
            finally:
                GRPC_REQUESTS.labels("patient-data", method_name, code).inc()
                GRPC_LATENCY.labels("patient-data", method_name).observe(time.time() - start)
        return inner
    return wrapper


class PatientDataServicer(hospital_pb2_grpc.PatientDataServiceServicer):

    @timed("ListPatients")
    def ListPatients(self, request, context):
        if request.role.upper() == "ESTAGIARIO":
            rows = query(
                f"SELECT {PATIENT_COLS} FROM patients WHERE patient_id IN "
                "(SELECT patient_id FROM user_patient_assignments "
                " WHERE username=%s AND link_type='estagiario' AND status='Ativo') "
                "ORDER BY patient_id LIMIT 200",
                (request.username,), "list_patients_estagiario")
        else:
            rows = query(
                f"SELECT {PATIENT_COLS} FROM patients WHERE patient_id IN "
                "(SELECT patient_id FROM user_patient_assignments "
                " WHERE username=%s AND link_type='medico' AND status='Ativo') "
                "ORDER BY patient_id LIMIT 200",
                (request.username,), "list_patients_medico")
        return hospital_pb2.PatientList(patients=[row_to_patient(r) for r in rows])

    @timed("GetPatientSummary")
    def GetPatientSummary(self, request, context):
        prows = query(f"SELECT {PATIENT_COLS} FROM patients WHERE patient_id=%s",
                      (request.patient_id,), "get_patient")
        if not prows:
            context.abort(grpc.StatusCode.NOT_FOUND, "Paciente não encontrado")
        patient = row_to_patient(prows[0])

        erows = query(
            "SELECT encounter_id, patient_id, start_date, end_date, encounter_type, department "
            "FROM encounters WHERE patient_id=%s ORDER BY start_date DESC LIMIT 1",
            (request.patient_id,), "last_encounter")
        last_enc = hospital_pb2.Encounter()
        if erows:
            r = erows[0]
            last_enc = hospital_pb2.Encounter(
                encounter_id=r[0], patient_id=r[1], start_date=str(r[2]),
                end_date=str(r[3]) if r[3] else "", encounter_type=r[4], department=r[5])

        conds = query(
            f"SELECT DISTINCT ON (event_code) {EVENT_COLS} FROM clinical_events "
            "WHERE patient_id=%s AND event_type='CONDITION' ORDER BY event_code, event_date DESC",
            (request.patient_id,), "conditions")
        obs = query(
            f"SELECT DISTINCT ON (event_code) {EVENT_COLS} FROM clinical_events "
            "WHERE patient_id=%s AND event_type='OBSERVATION' ORDER BY event_code, event_date DESC",
            (request.patient_id,), "last_observations")
        meds = query(
            f"SELECT DISTINCT ON (event_code) {EVENT_COLS} FROM clinical_events "
            "WHERE patient_id=%s AND event_type='MEDICATION' ORDER BY event_code, event_date DESC",
            (request.patient_id,), "active_medications")

        return hospital_pb2.PatientSummary(
            patient=patient, last_encounter=last_enc,
            conditions=[row_to_event(r) for r in conds],
            last_observations=[row_to_event(r) for r in obs],
            active_medications=[row_to_event(r) for r in meds])

    def _events(self, patient_id, event_type=None, metric="events"):
        prows = query(f"SELECT {PATIENT_COLS} FROM patients WHERE patient_id=%s",
                      (patient_id,), "get_patient")
        if not prows:
            return None
        if event_type:
            rows = query(
                f"SELECT {EVENT_COLS} FROM clinical_events "
                "WHERE patient_id=%s AND event_type=%s ORDER BY event_date",
                (patient_id, event_type), metric)
        else:
            rows = query(
                f"SELECT {EVENT_COLS} FROM clinical_events "
                "WHERE patient_id=%s ORDER BY event_date",
                (patient_id,), metric)
        return hospital_pb2.ClinicalEventList(
            patient=row_to_patient(prows[0]),
            events=[row_to_event(r) for r in rows])

    @timed("GetPatientHistory")
    def GetPatientHistory(self, request, context):
        result = self._events(request.patient_id, None, "history")
        if result is None:
            context.abort(grpc.StatusCode.NOT_FOUND, "Paciente não encontrado")
        return result

    @timed("GetPatientLabs")
    def GetPatientLabs(self, request, context):
        result = self._events(request.patient_id, "OBSERVATION", "labs")
        if result is None:
            context.abort(grpc.StatusCode.NOT_FOUND, "Paciente não encontrado")
        return result

    @timed("GetPatientMedications")
    def GetPatientMedications(self, request, context):
        result = self._events(request.patient_id, "MEDICATION", "medications")
        if result is None:
            context.abort(grpc.StatusCode.NOT_FOUND, "Paciente não encontrado")
        return result

    @timed("GetCohort")
    def GetCohort(self, request, context):
        rows = query(
            f"SELECT {PATIENT_COLS} FROM patients WHERE patient_id IN "
            "(SELECT DISTINCT patient_id FROM clinical_events "
            " WHERE event_type='CONDITION' AND event_code=%s) "
            "ORDER BY patient_id LIMIT 500",
            (request.condition_code,), "cohort_patients")
        cohort = hospital_pb2.CohortData(condition_code=request.condition_code)
        for r in rows:
            patient = row_to_patient(r)
            obs = query(
                f"SELECT DISTINCT ON (event_code) {EVENT_COLS} FROM clinical_events "
                "WHERE patient_id=%s AND event_type='OBSERVATION' ORDER BY event_code, event_date DESC",
                (patient.patient_id,), "cohort_observations")
            cohort.patients.append(hospital_pb2.CohortPatientData(
                patient=patient, observations=[row_to_event(o) for o in obs]))
        return cohort

    @timed("GetCohortStats")
    def GetCohortStats(self, request, context):
        stats = hospital_pb2.CohortStats(condition_code=request.condition_code)
        base = ("(SELECT DISTINCT patient_id FROM clinical_events "
                "WHERE event_type='CONDITION' AND event_code=%s)")

        total = query(f"SELECT COUNT(*) FROM patients WHERE patient_id IN {base}",
                      (request.condition_code,), "stats_total")
        stats.total_patients = total[0][0]

        for g, n in query(
                f"SELECT gender, COUNT(*) FROM patients WHERE patient_id IN {base} GROUP BY gender",
                (request.condition_code,), "stats_gender"):
            stats.gender_distribution[g] = n

        for faixa, n in query(
                "SELECT CASE "
                " WHEN EXTRACT(YEAR FROM AGE(birth_date)) < 18 THEN '0-17' "
                " WHEN EXTRACT(YEAR FROM AGE(birth_date)) < 40 THEN '18-39' "
                " WHEN EXTRACT(YEAR FROM AGE(birth_date)) < 60 THEN '40-59' "
                " ELSE '60+' END AS faixa, COUNT(*) "
                f"FROM patients WHERE patient_id IN {base} GROUP BY faixa",
                (request.condition_code,), "stats_age"):
            stats.age_distribution[faixa] = n

        for dept, n in query(
                "SELECT department, COUNT(*) FROM encounters "
                f"WHERE patient_id IN {base} GROUP BY department ORDER BY COUNT(*) DESC",
                (request.condition_code,), "stats_department"):
            stats.department_distribution[dept] = n

        for code, avg in query(
                "SELECT event_code, ROUND(AVG(value),2) FROM clinical_events "
                f"WHERE event_type='OBSERVATION' AND patient_id IN {base} GROUP BY event_code",
                (request.condition_code,), "stats_obs_avg"):
            stats.observation_averages[code] = float(avg)

        return stats

    @timed("GetProjects")
    def GetProjects(self, request, context):
        rows = query(
            "SELECT project_id, title, researcher, condition_code, status, valid_until "
            "FROM projects WHERE researcher=%s ORDER BY project_id",
            (request.username,), "projects")
        return hospital_pb2.ProjectList(projects=[
            hospital_pb2.Project(
                project_id=r[0], title=r[1], researcher=r[2],
                condition_code=r[3], status=r[4], valid_until=str(r[5]))
            for r in rows])


def serve():
    start_http_server(int(os.getenv("METRICS_PORT", "9100")))
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=int(os.getenv("GRPC_WORKERS", "10"))))
    hospital_pb2_grpc.add_PatientDataServiceServicer_to_server(PatientDataServicer(), server)
    port = int(os.getenv("GRPC_PORT", "50051"))
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    log.info("Patient Data Service ouvindo gRPC em :%s", port)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
