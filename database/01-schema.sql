-- ============================================================
-- Esquema do pseudo-prontuário eletrônico do Hospital Universitário
-- Banco: PostgreSQL 16
-- Executado automaticamente na inicialização do contêiner
-- (montado em /docker-entrypoint-initdb.d/)
-- ============================================================

-- Tabela de pacientes: dados cadastrais (identificadores diretos)
CREATE TABLE IF NOT EXISTS patients (
    patient_id   VARCHAR(10) PRIMARY KEY,        -- ex.: P000001
    full_name    VARCHAR(120) NOT NULL,
    birth_date   DATE NOT NULL,
    gender       VARCHAR(10) NOT NULL,           -- male | female
    city         VARCHAR(80) NOT NULL,
    state        CHAR(2) NOT NULL,
    cpf          CHAR(14) NOT NULL,              -- 000.000.000-00
    cns          CHAR(15) NOT NULL               -- Cartão Nacional de Saúde
);

-- Atendimentos (consultas, internações, emergências...)
CREATE TABLE IF NOT EXISTS encounters (
    encounter_id   VARCHAR(12) PRIMARY KEY,      -- ex.: E00000001
    patient_id     VARCHAR(10) NOT NULL REFERENCES patients(patient_id),
    start_date     DATE NOT NULL,
    end_date       DATE,
    encounter_type VARCHAR(20) NOT NULL,         -- Ambulatorial | Emergencia | Internacao | Retorno
    department     VARCHAR(40) NOT NULL          -- Cardiologia | Endocrinologia | ...
);

-- Eventos clínicos: condições, observações (exames) e medicações
CREATE TABLE IF NOT EXISTS clinical_events (
    event_id     VARCHAR(12) PRIMARY KEY,        -- ex.: EV00000001
    patient_id   VARCHAR(10) NOT NULL REFERENCES patients(patient_id),
    encounter_id VARCHAR(12) REFERENCES encounters(encounter_id),
    event_type   VARCHAR(15) NOT NULL,           -- CONDITION | OBSERVATION | MEDICATION
    event_code   VARCHAR(30) NOT NULL,           -- DIABETES | HBA1C | METFORMINA ...
    description  VARCHAR(160) NOT NULL,
    event_date   DATE NOT NULL,
    value        NUMERIC(10,2),                  -- preenchido p/ OBSERVATION e MEDICATION
    unit         VARCHAR(20)
);

-- Vínculos entre profissionais (médicos/estagiários) e pacientes
CREATE TABLE IF NOT EXISTS user_patient_assignments (
    assignment_id SERIAL PRIMARY KEY,
    username      VARCHAR(60) NOT NULL,          -- ex.: med.cardoso, est.oliveira
    patient_id    VARCHAR(10) NOT NULL REFERENCES patients(patient_id),
    link_type     VARCHAR(15) NOT NULL,          -- medico | estagiario
    supervisor    VARCHAR(60),                   -- para estagiário: username do médico supervisor
    status        VARCHAR(15) NOT NULL DEFAULT 'Ativo'  -- Ativo | Inativo
);

-- Projetos de pesquisa aprovados/expirados/suspensos
CREATE TABLE IF NOT EXISTS projects (
    project_id     VARCHAR(10) PRIMARY KEY,      -- ex.: PRJ01
    title          VARCHAR(160) NOT NULL,
    researcher     VARCHAR(60) NOT NULL,         -- username do pesquisador
    condition_code VARCHAR(30) NOT NULL,         -- igual ao event_code de clinical_events
    status         VARCHAR(15) NOT NULL,         -- Aprovado | Expirado | Suspenso
    valid_until    DATE NOT NULL
);

-- Índices para as consultas mais frequentes (desempenho sob carga)
CREATE INDEX IF NOT EXISTS idx_encounters_patient      ON encounters(patient_id);
CREATE INDEX IF NOT EXISTS idx_events_patient          ON clinical_events(patient_id);
CREATE INDEX IF NOT EXISTS idx_events_code             ON clinical_events(event_code);
CREATE INDEX IF NOT EXISTS idx_events_type             ON clinical_events(event_type);
CREATE INDEX IF NOT EXISTS idx_assignments_username    ON user_patient_assignments(username);
CREATE INDEX IF NOT EXISTS idx_assignments_supervisor  ON user_patient_assignments(supervisor);
CREATE INDEX IF NOT EXISTS idx_projects_researcher     ON projects(researcher);
