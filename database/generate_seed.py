#!/usr/bin/env python3
"""
Gerador de dados sintéticos para o pseudo-prontuário eletrônico.

Produz o arquivo 02-seed.sql com:
  - 1.000 pacientes
  - ~2.500 atendimentos (encounters)
  - ~9.000 eventos clínicos (condições, observações, medicações)
  - vínculos médico/estagiário-paciente
  - projetos de pesquisa (aprovados, expirados e suspensos)

A geração é determinística (seed fixa) para que todos os grupos
reproduzam exatamente o mesmo banco de dados.

Uso:  python3 generate_seed.py > 02-seed.sql   (ou apenas python3 generate_seed.py)
"""
import random
from datetime import date, timedelta

random.seed(42)  # determinístico: todos geram o mesmo banco

FIRST_NAMES_M = ["João", "Carlos", "Pedro", "Lucas", "Marcos", "Rafael", "André",
                 "Felipe", "Gustavo", "Ricardo", "Paulo", "Bruno", "Eduardo",
                 "Fernando", "Antônio", "José", "Miguel", "Daniel", "Tiago", "Vitor"]
FIRST_NAMES_F = ["Maria", "Ana", "Juliana", "Fernanda", "Camila", "Patrícia",
                 "Aline", "Bruna", "Carla", "Débora", "Elaine", "Gabriela",
                 "Helena", "Isabela", "Larissa", "Mariana", "Natália", "Paula",
                 "Renata", "Sofia"]
LAST_NAMES = ["Silva", "Santos", "Oliveira", "Souza", "Rodrigues", "Ferreira",
              "Almeida", "Pereira", "Lima", "Gomes", "Costa", "Ribeiro",
              "Martins", "Carvalho", "Rocha", "Dias", "Nascimento", "Andrade",
              "Moreira", "Nunes"]
CITIES = [("Brasília", "DF"), ("Goiânia", "GO"), ("Taguatinga", "DF"),
          ("Ceilândia", "DF"), ("Gama", "DF"), ("Luziânia", "GO"),
          ("Formosa", "GO"), ("Planaltina", "DF"), ("Sobradinho", "DF"),
          ("Águas Lindas", "GO")]
DEPARTMENTS = ["Cardiologia", "Endocrinologia", "Pediatria", "Clinica Geral",
               "Nefrologia", "Pneumologia", "Neurologia", "Ortopedia"]
ENCOUNTER_TYPES = ["Ambulatorial", "Emergencia", "Internacao", "Retorno"]

CONDITIONS = [
    ("DIABETES", "Diabetes Mellitus Tipo 2"),
    ("HIPERTENSAO", "Hipertensão Arterial Sistêmica"),
    ("OBESIDADE", "Obesidade Grau I-III"),
    ("PNEUMONIA", "Pneumonia Bacteriana"),
    ("ASMA", "Asma Brônquica"),
    ("DPOC", "Doença Pulmonar Obstrutiva Crônica"),
    ("INSUF_CARDIACA", "Insuficiência Cardíaca Congestiva"),
    ("DISLIPIDEMIA", "Dislipidemia Mista"),
]
OBSERVATIONS = [
    ("HBA1C", "Hemoglobina Glicada (HbA1c)", 5.0, 12.0, "%"),
    ("GLICEMIA", "Glicemia de Jejum", 70, 260, "mg/dL"),
    ("IMC", "Índice de Massa Corporal", 18.0, 42.0, "kg/m2"),
    ("PA_SISTOLICA", "Pressão Arterial Sistólica", 100, 190, "mmHg"),
    ("PA_DIASTOLICA", "Pressão Arterial Diastólica", 60, 120, "mmHg"),
    ("CREATININA", "Creatinina Sérica", 0.5, 3.5, "mg/dL"),
    ("COLESTEROL_LDL", "Colesterol LDL", 60, 220, "mg/dL"),
]
MEDICATIONS = [
    ("METFORMINA", "Metformina 850 mg", 850, "mg"),
    ("INSULINA_NPH", "Insulina NPH 10 UI", 10, "UI"),
    ("LOSARTANA", "Losartana 50 mg", 50, "mg"),
    ("ENALAPRIL", "Enalapril 20 mg", 20, "mg"),
    ("SINVASTATINA", "Sinvastatina 40 mg", 40, "mg"),
    ("HIDROCLOROTIAZIDA", "Hidroclorotiazida 25 mg", 25, "mg"),
    ("SALBUTAMOL", "Salbutamol 100 mcg", 100, "mcg"),
    ("AMOXICILINA", "Amoxicilina 500 mg", 500, "mg"),
]

# usuários (devem coincidir com os usuários criados no Keycloak)
DOCTORS = ["med.cardoso", "med.souza", "med.lima", "med.ferreira"]
INTERNS = {"est.oliveira": "med.cardoso", "est.santos": "med.souza"}
RESEARCHERS = ["pesq.ramos", "pesq.telles"]

N_PATIENTS = 1000


def esc(s: str) -> str:
    return s.replace("'", "''")


def rnd_date(start_year=2021, end_year=2025) -> date:
    start = date(start_year, 1, 1)
    end = date(end_year, 12, 31)
    return start + timedelta(days=random.randint(0, (end - start).days))


lines = ["-- Dados sintéticos gerados por generate_seed.py (seed=42). NÃO editar manualmente.",
         "BEGIN;"]

# ---------------- patients ----------------
patients = []
for i in range(1, N_PATIENTS + 1):
    pid = f"P{i:06d}"
    gender = random.choice(["male", "female"])
    first = random.choice(FIRST_NAMES_M if gender == "male" else FIRST_NAMES_F)
    name = f"{first} {random.choice(LAST_NAMES)} {random.choice(LAST_NAMES)}"
    birth = rnd_date(1940, 2007)
    city, state = random.choice(CITIES)
    cpf = f"{random.randint(100,999)}.{random.randint(100,999)}.{random.randint(100,999)}-{random.randint(10,99)}"
    cns = f"{random.randint(700000000000000, 799999999999999)}"
    patients.append((pid, gender, birth))
    lines.append(
        "INSERT INTO patients VALUES "
        f"('{pid}','{esc(name)}','{birth}','{gender}','{esc(city)}','{state}','{cpf}','{cns}');"
    )

# ---------------- encounters + clinical_events ----------------
enc_seq = 0
ev_seq = 0
patient_conditions = {}
for pid, gender, birth in patients:
    n_enc = random.randint(1, 4)
    conds = random.sample(CONDITIONS, k=random.randint(1, 3))
    patient_conditions[pid] = [c[0] for c in conds]
    for _ in range(n_enc):
        enc_seq += 1
        eid = f"E{enc_seq:08d}"
        start = rnd_date(2022, 2025)
        etype = random.choice(ENCOUNTER_TYPES)
        end = start + timedelta(days=random.randint(0, 10)) if etype == "Internacao" else start
        dept = random.choice(DEPARTMENTS)
        lines.append(
            "INSERT INTO encounters VALUES "
            f"('{eid}','{pid}','{start}','{end}','{etype}','{dept}');"
        )
        # condição diagnosticada no atendimento
        code, desc = random.choice(conds)
        ev_seq += 1
        lines.append(
            "INSERT INTO clinical_events VALUES "
            f"('EV{ev_seq:08d}','{pid}','{eid}','CONDITION','{code}','{esc(desc)}','{start}',NULL,NULL);"
        )
        # 1-3 observações (exames)
        for obs in random.sample(OBSERVATIONS, k=random.randint(1, 3)):
            ocode, odesc, vmin, vmax, unit = obs
            ev_seq += 1
            val = round(random.uniform(vmin, vmax), 1)
            lines.append(
                "INSERT INTO clinical_events VALUES "
                f"('EV{ev_seq:08d}','{pid}','{eid}','OBSERVATION','{ocode}','{esc(odesc)}','{start}',{val},'{unit}');"
            )
        # 0-2 medicações
        for med in random.sample(MEDICATIONS, k=random.randint(0, 2)):
            mcode, mdesc, dose, unit = med
            ev_seq += 1
            lines.append(
                "INSERT INTO clinical_events VALUES "
                f"('EV{ev_seq:08d}','{pid}','{eid}','MEDICATION','{mcode}','{esc(mdesc)}','{start}',{dose},'{unit}');"
            )

# ---------------- user_patient_assignments ----------------
# cada médico recebe uma fatia de pacientes; estagiários herdam parte dos pacientes do supervisor
for idx, (pid, _, _) in enumerate(patients):
    doctor = DOCTORS[idx % len(DOCTORS)]
    lines.append(
        "INSERT INTO user_patient_assignments (username, patient_id, link_type, supervisor, status) VALUES "
        f"('{doctor}','{pid}','medico',NULL,'Ativo');"
    )

for intern, supervisor in INTERNS.items():
    sup_idx = DOCTORS.index(supervisor)
    # estagiário acompanha 60 pacientes do supervisor
    count = 0
    for idx, (pid, _, _) in enumerate(patients):
        if idx % len(DOCTORS) == sup_idx:
            lines.append(
                "INSERT INTO user_patient_assignments (username, patient_id, link_type, supervisor, status) VALUES "
                f"('{intern}','{pid}','estagiario','{supervisor}','Ativo');"
            )
            count += 1
            if count >= 60:
                break

# ---------------- projects ----------------
projects = [
    ("PRJ01", "Perfil glicêmico de pacientes diabéticos do HUB", RESEARCHERS[0], "DIABETES", "Aprovado", "2027-12-31"),
    ("PRJ02", "Hipertensão arterial e desfechos cardiovasculares", RESEARCHERS[0], "HIPERTENSAO", "Aprovado", "2026-12-31"),
    ("PRJ03", "Obesidade em adultos jovens", RESEARCHERS[1], "OBESIDADE", "Aprovado", "2027-06-30"),
    ("PRJ04", "Pneumonias comunitárias — estudo retrospectivo", RESEARCHERS[1], "PNEUMONIA", "Expirado", "2024-12-31"),
    ("PRJ05", "DPOC e tabagismo", RESEARCHERS[0], "DPOC", "Suspenso", "2026-10-01"),
]
for p in projects:
    lines.append(
        "INSERT INTO projects VALUES "
        f"('{p[0]}','{esc(p[1])}','{p[2]}','{p[3]}','{p[4]}','{p[5]}');"
    )

lines.append("COMMIT;")

with open("02-seed.sql", "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")

print(f"02-seed.sql gerado: {N_PATIENTS} pacientes, {enc_seq} atendimentos, {ev_seq} eventos clínicos.")
