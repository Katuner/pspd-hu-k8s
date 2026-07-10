"""
locustfile.py — Alternativa ao k6 para os testes de carga (Locust).

Uso com interface web:
    locust -f locustfile.py --host http://localhost:30800
    # abrir http://localhost:8089 e configurar usuários/spawn rate

Uso headless (exemplo com 100 usuários):
    locust -f locustfile.py --host http://localhost:30800 \
           --headless -u 100 -r 20 -t 3m --csv resultados/locust-100
"""
import random
from locust import HttpUser, task, between


PASSWORD = "pspd123"


class BaseUser(HttpUser):
    abstract = True
    wait_time = between(0.5, 2.5)
    username_kc = None

    def on_start(self):
        resp = self.client.post("/auth/login", json={
            "username": self.username_kc, "password": PASSWORD},
            name="/auth/login")
        if resp.status_code == 200:
            self.token = resp.json()["access_token"]
        else:
            self.token = None

    @property
    def auth(self):
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}


class MedicoUser(BaseUser):
    weight = 4
    username_kc = "med.cardoso"

    @task(2)
    def lista_pacientes(self):
        self.client.get("/api/patients", headers=self.auth, name="/api/patients")

    @task(3)
    def resumo_clinico(self):
        pid = f"P{random.choice([1, 5, 9, 13, 17]):06d}"
        self.client.get(f"/api/patients/{pid}/summary", headers=self.auth,
                        name="/api/patients/{id}/summary")

    @task(2)
    def exames(self):
        pid = f"P{random.choice([1, 5, 9, 13, 17]):06d}"
        self.client.get(f"/api/patients/{pid}/labs", headers=self.auth,
                        name="/api/patients/{id}/labs")

    @task(1)
    def historico(self):
        pid = f"P{random.choice([1, 5, 9]):06d}"
        self.client.get(f"/api/patients/{pid}/history", headers=self.auth,
                        name="/api/patients/{id}/history")


class EstagiarioUser(BaseUser):
    weight = 2
    username_kc = "est.oliveira"

    @task(2)
    def lista_pacientes(self):
        self.client.get("/api/patients", headers=self.auth, name="/api/patients")

    @task(2)
    def resumo_parcial(self):
        pid = f"P{random.choice([1, 5, 9, 13]):06d}"
        self.client.get(f"/api/patients/{pid}/summary", headers=self.auth,
                        name="/api/patients/{id}/summary")


class PesquisadorUser(BaseUser):
    weight = 2
    username_kc = "pesq.ramos"

    @task(1)
    def projetos(self):
        self.client.get("/api/research/projects", headers=self.auth,
                        name="/api/research/projects")

    @task(3)
    def estatisticas(self):
        code = random.choice(["DIABETES", "HIPERTENSAO"])
        self.client.get(f"/api/research/cohort/{code}/stats", headers=self.auth,
                        name="/api/research/cohort/{code}/stats")

    @task(1)
    def coorte(self):
        self.client.get("/api/research/cohort/DIABETES", headers=self.auth,
                        name="/api/research/cohort/{code}")
