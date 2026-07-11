#!/usr/bin/env python3
"""
API Gateway (FastAPI)

Responsabilidades (conforme a especificação do projeto):
  (i)   receber requisições REST do frontend;
  (ii)  validar tokens JWT emitidos pelo Keycloak (assinatura RS256 via JWKS);
  (iii) encaminhar as requisições aos microsserviços internos via gRPC
        (Authorization -> PatientData -> DataTransform);
  (iv)  consolidar as respostas (JSON FHIR) e devolvê-las ao cliente.

Também expõe:
  POST /auth/login  -> proxy do Resource Owner Password Grant do Keycloak,
                       simplificando o frontend e os testes de carga.
  GET  /metrics     -> métricas Prometheus.
  GET  /healthz     -> liveness/readiness probe.
"""
import os
import time
import json
import logging
from contextlib import asynccontextmanager

import grpc
import httpx
import jwt
from jwt import PyJWKClient
from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from pydantic import BaseModel

import hospital_pb2
import hospital_pb2_grpc

logging.basicConfig(level=logging.INFO, format="%(asctime)s [gateway] %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ------------------------------ configuração ------------------------------
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://keycloak:8080")           # uso interno (validação/token)
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "hospital")
KEYCLOAK_CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "hospital-frontend")
AUTHZ_ADDR = os.getenv("AUTHZ_ADDR", "authorization:50051")
PATIENT_ADDR = os.getenv("PATIENT_ADDR", "patient-data:50051")
TRANSFORM_ADDR = os.getenv("TRANSFORM_ADDR", "data-transform:50051")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "account")
JWT_VERIFY_AUD = os.getenv("JWT_VERIFY_AUD", "false").lower() == "true"

ISSUER_URL = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}"
JWKS_URL = f"{ISSUER_URL}/protocol/openid-connect/certs"
TOKEN_URL = f"{ISSUER_URL}/protocol/openid-connect/token"

# ------------------------------- métricas ---------------------------------
HTTP_REQUESTS = Counter("http_requests_total", "Requisições HTTP recebidas",
                        ["method", "route", "status"])
HTTP_LATENCY = Histogram("http_request_duration_seconds", "Duração das requisições HTTP",
                         ["method", "route"],
                         buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10])
INFLIGHT = Gauge("http_requests_in_flight", "Requisições em andamento")
GRPC_CLIENT_ERRORS = Counter("grpc_client_errors_total", "Erros em chamadas gRPC de saída",
                             ["target"])
AUTH_FAILURES = Counter("auth_failures_total", "Falhas de autenticação JWT", ["reason"])

# ------------------------------ canais gRPC -------------------------------
channels = {}
stubs = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    opts = [("grpc.lb_policy_name", "round_robin"),
            ("grpc.keepalive_time_ms", 30000)]
    channels["authz"] = grpc.aio.insecure_channel(AUTHZ_ADDR, options=opts)
    channels["patient"] = grpc.aio.insecure_channel(PATIENT_ADDR, options=opts)
    channels["transform"] = grpc.aio.insecure_channel(TRANSFORM_ADDR, options=opts)
    stubs["authz"] = hospital_pb2_grpc.AuthorizationServiceStub(channels["authz"])
    stubs["patient"] = hospital_pb2_grpc.PatientDataServiceStub(channels["patient"])
    stubs["transform"] = hospital_pb2_grpc.DataTransformServiceStub(channels["transform"])
    log.info("Canais gRPC criados: authz=%s patient=%s transform=%s",
             AUTHZ_ADDR, PATIENT_ADDR, TRANSFORM_ADDR)
    yield
    for ch in channels.values():
        await ch.close()


app = FastAPI(title="Hospital Universitário — API Gateway", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

security = HTTPBearer(auto_error=False)
_jwks_client = None


def jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(JWKS_URL, cache_keys=True)
    return _jwks_client


# --------------------------- middleware métricas ---------------------------
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    route = request.url.path
    # normaliza IDs para não explodir a cardinalidade das métricas
    parts = route.split("/")
    norm = "/".join("{id}" if p.startswith(("P0", "E0", "hash")) else p for p in parts)
    start = time.time()
    INFLIGHT.inc()
    try:
        response = await call_next(request)
        status = response.status_code
    except Exception:
        status = 500
        raise
    finally:
        INFLIGHT.dec()
        if norm not in ("/metrics", "/healthz"):
            HTTP_REQUESTS.labels(request.method, norm, str(status)).inc()
            HTTP_LATENCY.labels(request.method, norm).observe(time.time() - start)
    return response


# ------------------------------ autenticação -------------------------------
class UserContext(BaseModel):
    username: str
    role: str


ROLES = {"MEDICO", "ESTAGIARIO", "PESQUISADOR"}


def get_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> UserContext:
    """Valida o JWT (assinatura, expiração, emissor) e extrai username/role."""
    if credentials is None:
        AUTH_FAILURES.labels(reason="missing_token").inc()
        raise HTTPException(401, "Token não informado")
    token = credentials.credentials
    try:
        key = jwks_client().get_signing_key_from_jwt(token).key
        options = {"verify_aud": JWT_VERIFY_AUD}
        claims = jwt.decode(token, key, algorithms=["RS256"],
                            audience=JWT_AUDIENCE if JWT_VERIFY_AUD else None,
                            options=options)
    except jwt.ExpiredSignatureError:
        AUTH_FAILURES.labels(reason="expired").inc()
        raise HTTPException(401, "Token expirado")
    except Exception as exc:  # noqa: BLE001
        AUTH_FAILURES.labels(reason="invalid").inc()
        raise HTTPException(401, f"Token inválido: {exc}")

    username = claims.get("preferred_username", "")
    role = None
    if username.startswith("med."): role = "MEDICO"
    elif username.startswith("est."): role = "ESTAGIARIO"
    elif username.startswith("pes."): role = "PESQUISADOR"
    
    if not role:
        AUTH_FAILURES.labels(reason="no_role").inc()
        raise HTTPException(403, "Usuário sem papel válido (MEDICO/ESTAGIARIO/PESQUISADOR)")
    return UserContext(username=username, role=role)


async def authorize(user: UserContext, query_type: str,
                    patient_id: str = "", cohort_code: str = "") -> hospital_pb2.AccessResponse:
    """Consulta o Authorization Service; converte DENY em HTTP 403."""
    try:
        resp = await stubs["authz"].CheckAccess(hospital_pb2.AccessRequest(
            username=user.username, role=user.role, query_type=query_type,
            patient_id=patient_id, cohort_code=cohort_code))
    except grpc.aio.AioRpcError as exc:
        GRPC_CLIENT_ERRORS.labels(target="authorization").inc()
        raise HTTPException(502, f"Authorization service indisponível: {exc.code().name}")
    if not resp.allowed:
        raise HTTPException(403, f"Acesso negado: {resp.reason}")
    return resp


def fhir_response(payload: str) -> Response:
    return Response(content=payload, media_type="application/fhir+json")


async def call(stub_name: str, method: str, request_msg):
    """Chama um método gRPC com contabilização de erros."""
    try:
        return await getattr(stubs[stub_name], method)(request_msg)
    except grpc.aio.AioRpcError as exc:
        GRPC_CLIENT_ERRORS.labels(target=stub_name).inc()
        if exc.code() == grpc.StatusCode.NOT_FOUND:
            raise HTTPException(404, exc.details())
        raise HTTPException(502, f"{stub_name} indisponível: {exc.code().name}")


# --------------------------------- rotas -----------------------------------
class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/auth/login")
async def login(body: LoginRequest):
    """Proxy do fluxo Resource Owner Password Grant do Keycloak."""
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(TOKEN_URL, data={
            "grant_type": "password",
            "client_id": KEYCLOAK_CLIENT_ID,
            "username": body.username,
            "password": body.password,
            "scope": "openid"
        })
    if r.status_code != 200:
        log.error(f"Keycloak falhou: status={r.status_code}, body={r.text}")
        AUTH_FAILURES.labels(reason="login_failed").inc()
        raise HTTPException(401, "Usuário ou senha inválidos")
    data = r.json()
    if "id_token" in data:
        data["access_token"] = data["id_token"]
    return data


@app.get("/api/me")
async def me(user: UserContext = Depends(get_user)):
    return {"username": user.username, "role": user.role}


@app.get("/api/patients")
async def list_patients(user: UserContext = Depends(get_user)):
    authz = await authorize(user, "ListaPacientes")
    data = await call("patient", "ListPatients", hospital_pb2.CaregiverRequest(
        username=user.username, role=user.role, supervisor=authz.supervisor))
    fhir = await call("transform", "TransformPatientList",
                      hospital_pb2.TransformPatientListRequest(
                          data=data, access_level=authz.access_level))
    return fhir_response(fhir.json)


@app.get("/api/patients/{patient_id}/summary")
async def patient_summary(patient_id: str, user: UserContext = Depends(get_user)):
    authz = await authorize(user, "ResumoClinico", patient_id=patient_id)
    data = await call("patient", "GetPatientSummary",
                      hospital_pb2.PatientRequest(patient_id=patient_id))
    fhir = await call("transform", "TransformSummary",
                      hospital_pb2.TransformSummaryRequest(
                          data=data, access_level=authz.access_level))
    return fhir_response(fhir.json)


@app.get("/api/patients/{patient_id}/history")
async def patient_history(patient_id: str, user: UserContext = Depends(get_user)):
    authz = await authorize(user, "HistoricoClinico", patient_id=patient_id)
    data = await call("patient", "GetPatientHistory",
                      hospital_pb2.PatientRequest(patient_id=patient_id))
    fhir = await call("transform", "TransformEvents",
                      hospital_pb2.TransformEventsRequest(
                          data=data, access_level=authz.access_level, bundle_type="history"))
    return fhir_response(fhir.json)


@app.get("/api/patients/{patient_id}/labs")
async def patient_labs(patient_id: str, user: UserContext = Depends(get_user)):
    authz = await authorize(user, "Exames", patient_id=patient_id)
    data = await call("patient", "GetPatientLabs",
                      hospital_pb2.PatientRequest(patient_id=patient_id))
    fhir = await call("transform", "TransformEvents",
                      hospital_pb2.TransformEventsRequest(
                          data=data, access_level=authz.access_level, bundle_type="labs"))
    return fhir_response(fhir.json)


@app.get("/api/patients/{patient_id}/medications")
async def patient_medications(patient_id: str, user: UserContext = Depends(get_user)):
    authz = await authorize(user, "Medicamentos", patient_id=patient_id)
    data = await call("patient", "GetPatientMedications",
                      hospital_pb2.PatientRequest(patient_id=patient_id))
    fhir = await call("transform", "TransformEvents",
                      hospital_pb2.TransformEventsRequest(
                          data=data, access_level=authz.access_level, bundle_type="medications"))
    return fhir_response(fhir.json)


@app.get("/api/research/projects")
async def research_projects(user: UserContext = Depends(get_user)):
    await authorize(user, "Projetos")
    data = await call("patient", "GetProjects",
                      hospital_pb2.ResearcherRequest(username=user.username))
    return {"projects": [{
        "project_id": p.project_id, "title": p.title,
        "condition_code": p.condition_code, "status": p.status,
        "valid_until": p.valid_until} for p in data.projects]}


@app.get("/api/research/cohort/{condition_code}")
async def research_cohort(condition_code: str, user: UserContext = Depends(get_user)):
    authz = await authorize(user, "Coorte", cohort_code=condition_code.upper())
    data = await call("patient", "GetCohort",
                      hospital_pb2.CohortRequest(condition_code=condition_code.upper()))
    fhir = await call("transform", "TransformCohort",
                      hospital_pb2.TransformCohortRequest(
                          data=data, access_level=authz.access_level))
    return fhir_response(fhir.json)


@app.get("/api/research/cohort/{condition_code}/stats")
async def research_cohort_stats(condition_code: str, user: UserContext = Depends(get_user)):
    authz = await authorize(user, "EstatisticasCoorte", cohort_code=condition_code.upper())
    data = await call("patient", "GetCohortStats",
                      hospital_pb2.CohortRequest(condition_code=condition_code.upper()))
    fhir = await call("transform", "TransformStats",
                      hospital_pb2.TransformStatsRequest(
                          data=data, access_level=authz.access_level))
    return fhir_response(fhir.json)


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
