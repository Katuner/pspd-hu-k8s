#!/usr/bin/env python3
"""
Data Transform Service (gRPC)

Responsável por:
  1. Converter os dados brutos em recursos HL7/FHIR (Patient, Encounter,
     Condition, Observation, MedicationRequest) empacotados em um Bundle.
  2. Aplicar as regras de anonimização conforme o nível de acesso:
       FULL       -> todos os campos
       PARTIAL    -> iniciais do nome, faixa etária, sem CPF/CNS
       ANONYMIZED -> id pseudonimizado (hash), sem nome/CPF/CNS/cidade
       AGGREGATED -> somente valores agregados
  3. Montar estatísticas agregadas para pesquisadores.

Expõe métricas Prometheus em HTTP na porta 9100 (/metrics).
"""
import os
import json
import time
import hashlib
import logging
from concurrent import futures
from datetime import date

import grpc
from prometheus_client import start_http_server, Counter, Histogram

import hospital_pb2
import hospital_pb2_grpc

logging.basicConfig(level=logging.INFO, format="%(asctime)s [data-transform] %(levelname)s %(message)s")
log = logging.getLogger(__name__)

GRPC_REQUESTS = Counter("grpc_requests_total", "Total de chamadas gRPC recebidas",
                        ["service", "method", "code"])
GRPC_LATENCY = Histogram("grpc_request_duration_seconds", "Duração das chamadas gRPC",
                         ["service", "method"])
FHIR_TRANSFORMS = Counter("fhir_transformations_total",
                          "Recursos FHIR gerados", ["resource_type"])
ANON_OPS = Counter("anonymization_operations_total",
                   "Operações de anonimização aplicadas", ["level"])

HASH_SALT = os.getenv("HASH_SALT", "pspd2026")


# ----------------------- utilidades de anonimização -----------------------
def pseudonymize(patient_id: str) -> str:
    """Gera identificador pseudonimizado estável (hashNNN...)."""
    digest = hashlib.sha256(f"{HASH_SALT}:{patient_id}".encode()).hexdigest()[:8]
    return f"hash{digest}"


def initials(full_name: str) -> str:
    return ". ".join(p[0].upper() for p in full_name.split() if p) + "."


def age_from(birth_date: str) -> int:
    b = date.fromisoformat(birth_date)
    today = date.today()
    return today.year - b.year - ((today.month, today.day) < (b.month, b.day))


def age_band(birth_date: str) -> str:
    a = age_from(birth_date)
    if a < 18:
        return "0-17"
    if a < 40:
        return "18-39"
    if a < 60:
        return "40-59"
    return "60+"


# ----------------------- construção de recursos FHIR -----------------------
def fhir_patient(p: hospital_pb2.Patient, level: str) -> dict:
    """Converte um registro de paciente em recurso FHIR conforme o nível."""
    ANON_OPS.labels(level=level).inc()
    FHIR_TRANSFORMS.labels(resource_type="Patient").inc()

    if level == "FULL":
        return {
            "resourceType": "Patient",
            "id": p.patient_id,
            "identifier": [
                {"system": "urn:oid:2.16.840.1.113883.13.237", "value": p.cpf},   # CPF
                {"system": "urn:oid:2.16.840.1.113883.13.236", "value": p.cns},   # CNS
            ],
            "name": [{"text": p.full_name}],
            "birthDate": p.birth_date,
            "gender": p.gender,
            "address": [{"city": p.city, "state": p.state, "country": "BR"}],
        }
    if level == "PARTIAL":
        return {
            "resourceType": "Patient",
            "id": p.patient_id,
            "name": [{"text": initials(p.full_name)}],
            "gender": p.gender,
            "extension": [{
                "url": "http://hospital.local/fhir/StructureDefinition/faixa-etaria",
                "valueString": age_band(p.birth_date)}],
            "address": [{"city": p.city, "state": p.state, "country": "BR"}],
        }
    # ANONYMIZED
    return {
        "resourceType": "Patient",
        "id": pseudonymize(p.patient_id),
        "gender": p.gender,
        "extension": [{
            "url": "http://hospital.local/fhir/StructureDefinition/faixa-etaria",
            "valueString": age_band(p.birth_date)}],
        "address": [{"state": p.state, "country": "BR"}],
    }


def patient_ref(p: hospital_pb2.Patient, level: str) -> str:
    return f"Patient/{pseudonymize(p.patient_id) if level == 'ANONYMIZED' else p.patient_id}"


def fhir_encounter(e: hospital_pb2.Encounter, p, level: str) -> dict:
    FHIR_TRANSFORMS.labels(resource_type="Encounter").inc()
    return {
        "resourceType": "Encounter",
        "id": e.encounter_id,
        "status": "finished",
        "class": {"code": e.encounter_type},
        "serviceType": {"text": e.department},
        "subject": {"reference": patient_ref(p, level)},
        "period": {"start": e.start_date, "end": e.end_date or e.start_date},
    }


def fhir_event(ev: hospital_pb2.ClinicalEvent, p, level: str) -> dict:
    """Converte um evento clínico no recurso FHIR adequado."""
    ref = {"reference": patient_ref(p, level)}
    if ev.event_type == "CONDITION":
        FHIR_TRANSFORMS.labels(resource_type="Condition").inc()
        return {
            "resourceType": "Condition",
            "id": ev.event_id,
            "code": {"coding": [{"code": ev.event_code}], "text": ev.description},
            "subject": ref,
            "recordedDate": ev.event_date,
        }
    if ev.event_type == "OBSERVATION":
        FHIR_TRANSFORMS.labels(resource_type="Observation").inc()
        return {
            "resourceType": "Observation",
            "id": ev.event_id,
            "status": "final",
            "code": {"coding": [{"code": ev.event_code}], "text": ev.description},
            "subject": ref,
            "effectiveDateTime": ev.event_date,
            "valueQuantity": {"value": ev.value, "unit": ev.unit} if ev.has_value else None,
        }
    FHIR_TRANSFORMS.labels(resource_type="MedicationRequest").inc()
    return {
        "resourceType": "MedicationRequest",
        "id": ev.event_id,
        "status": "active",
        "intent": "order",
        "medicationCodeableConcept": {"coding": [{"code": ev.event_code}], "text": ev.description},
        "subject": ref,
        "authoredOn": ev.event_date,
        "dosageInstruction": [{"text": f"{ev.value:g} {ev.unit}"}] if ev.has_value else [],
    }


def bundle(entries: list) -> dict:
    return {
        "resourceType": "Bundle",
        "type": "collection",
        "total": len(entries),
        "entry": [{"resource": r} for r in entries if r is not None],
    }


def clean(obj):
    """Remove chaves None recursivamente (para FHIR mais limpo)."""
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [clean(i) for i in obj]
    return obj


def timed(method_name):
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
                GRPC_REQUESTS.labels("data-transform", method_name, code).inc()
                GRPC_LATENCY.labels("data-transform", method_name).observe(time.time() - start)
        return inner
    return wrapper


class DataTransformServicer(hospital_pb2_grpc.DataTransformServiceServicer):

    @timed("TransformPatientList")
    def TransformPatientList(self, request, context):
        level = request.access_level
        resources = [fhir_patient(p, level) for p in request.data.patients]
        return hospital_pb2.FhirResponse(json=json.dumps(clean(bundle(resources)), ensure_ascii=False))

    @timed("TransformSummary")
    def TransformSummary(self, request, context):
        level = request.access_level
        d = request.data
        resources = [fhir_patient(d.patient, level)]
        if d.last_encounter.encounter_id:
            resources.append(fhir_encounter(d.last_encounter, d.patient, level))
        for ev in list(d.conditions) + list(d.last_observations) + list(d.active_medications):
            resources.append(fhir_event(ev, d.patient, level))
        return hospital_pb2.FhirResponse(json=json.dumps(clean(bundle(resources)), ensure_ascii=False))

    @timed("TransformEvents")
    def TransformEvents(self, request, context):
        level = request.access_level
        d = request.data
        resources = [fhir_patient(d.patient, level)]
        resources += [fhir_event(ev, d.patient, level) for ev in d.events]
        return hospital_pb2.FhirResponse(json=json.dumps(clean(bundle(resources)), ensure_ascii=False))

    @timed("TransformCohort")
    def TransformCohort(self, request, context):
        # Pesquisador: sempre ANONYMIZED — um recurso Patient pseudonimizado
        # seguido das últimas observações de cada paciente da coorte.
        level = "ANONYMIZED"
        resources = []
        for item in request.data.patients:
            resources.append(fhir_patient(item.patient, level))
            resources += [fhir_event(o, item.patient, level) for o in item.observations]
        return hospital_pb2.FhirResponse(json=json.dumps(clean(bundle(resources)), ensure_ascii=False))

    @timed("TransformStats")
    def TransformStats(self, request, context):
        # AGGREGATED: valores totalizados em um recurso FHIR MeasureReport simplificado
        s = request.data
        total = s.total_patients or 1
        FHIR_TRANSFORMS.labels(resource_type="MeasureReport").inc()
        ANON_OPS.labels(level="AGGREGATED").inc()

        def pct(n):
            return round(100.0 * n / total, 1)

        report = {
            "resourceType": "MeasureReport",
            "status": "complete",
            "type": "summary",
            "measure": f"Cohort/{s.condition_code}",
            "period": {"start": "2021-01-01", "end": str(date.today())},
            "group": [
                {"code": {"text": "totalPacientes"},
                 "population": [{"count": s.total_patients}]},
                {"code": {"text": "distribuicaoSexo"},
                 "stratifier": [{"stratum": [
                     {"value": {"text": k}, "population": [{"count": v}],
                      "measureScore": {"value": pct(v), "unit": "%"}}
                     for k, v in s.gender_distribution.items()]}]},
                {"code": {"text": "distribuicaoFaixaEtaria"},
                 "stratifier": [{"stratum": [
                     {"value": {"text": k}, "population": [{"count": v}],
                      "measureScore": {"value": pct(v), "unit": "%"}}
                     for k, v in sorted(s.age_distribution.items())]}]},
                {"code": {"text": "departamentosMaisUsados"},
                 "stratifier": [{"stratum": [
                     {"value": {"text": k}, "population": [{"count": v}]}
                     for k, v in sorted(s.department_distribution.items(),
                                        key=lambda kv: -kv[1])]}]},
                {"code": {"text": "mediasExames"},
                 "stratifier": [{"stratum": [
                     {"value": {"text": k}, "measureScore": {"value": v}}
                     for k, v in s.observation_averages.items()]}]},
            ],
        }
        return hospital_pb2.FhirResponse(json=json.dumps(clean(report), ensure_ascii=False))


def serve():
    start_http_server(int(os.getenv("METRICS_PORT", "9100")))
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=int(os.getenv("GRPC_WORKERS", "10"))))
    hospital_pb2_grpc.add_DataTransformServiceServicer_to_server(DataTransformServicer(), server)
    port = int(os.getenv("GRPC_PORT", "50051"))
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    log.info("Data Transform Service ouvindo gRPC em :%s", port)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
