-- ============================================================
-- Sistema de Antigüedad y Ascensos de Grado
-- Esquema de base de datos (SQLite)
-- ============================================================
-- Principios de diseño:
--  * Nunca se borra información físicamente (soft-delete con "activo").
--  * Toda tabla mutable tiene fecha_carga / fecha_modif + usuario.
--  * auditoria registra CADA cambio (insert/update/soft-delete) con
--    el valor anterior y el nuevo, en formato JSON, con timestamp.
--  * Claves foráneas activas y validadas (PRAGMA foreign_keys=ON en db.py).
-- ============================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------
-- AGENTES: ficha básica de cada persona (legajo = N_doc)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agentes (
    n_doc               INTEGER PRIMARY KEY,
    apellido_nombre     TEXT NOT NULL,
    nivel_actual        TEXT,           -- Niv (A-F) al momento de importar
    grado_actual        INTEGER,        -- gra al momento de importar
    activo              INTEGER NOT NULL DEFAULT 1,  -- 1=activo, 0=baja
    origen              TEXT DEFAULT 'importado',     -- importado | manual
    -- Clasificación por régimen de contratación (Decreto 1421/02):
    vinculado_1421      INTEGER NOT NULL DEFAULT 0,  -- 1 si aparece en alguna tabla de origen 1421
    tiene_baja_1421     INTEGER NOT NULL DEFAULT 0,  -- 1 si CONTRATADOS registra Fecha de baja
    cuenta_1421         INTEGER NOT NULL DEFAULT 0,  -- 1 = vinculado_1421=1 AND tiene_baja_1421=0 (el que usan los reportes)
    motivo_clasif_1421  TEXT,                        -- explicación legible de la clasificación
    dependencia_1421    TEXT,                        -- dependencia del contrato 1421 vigente
    contrato_desde_1421 TEXT,                        -- fecha desde del contrato 1421 vigente
    contrato_hasta_1421 TEXT,                         -- fecha hasta del contrato 1421 vigente
    fecha_carga         TEXT NOT NULL DEFAULT (datetime('now')),
    fecha_modif         TEXT NOT NULL DEFAULT (datetime('now')),
    usuario_modif       TEXT
);

-- ---------------------------------------------------------------
-- PERIODOS_ANTIGUEDAD: cada tramo de antigüedad reconocido
-- (en el Ministerio o en organismos anteriores). Un agente puede
-- tener varios períodos. Cada uno se puede marcar si cuenta o no
-- para el cómputo de ascenso de grado.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS periodos_antiguedad (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    n_doc               INTEGER NOT NULL REFERENCES agentes(n_doc),
    fecha_desde         TEXT NOT NULL,     -- ISO 'YYYY-MM-DD'
    fecha_hasta         TEXT,              -- NULL = vigente a la fecha de corte
    organismo           TEXT,              -- dependencia / organismo de ese tramo
    cuenta_ascenso       INTEGER NOT NULL DEFAULT 1,  -- 1=cuenta, 0=no cuenta
    observaciones       TEXT,
    origen              TEXT DEFAULT 'importado',      -- importado | manual
    activo              INTEGER NOT NULL DEFAULT 1,     -- soft-delete
    fecha_carga         TEXT NOT NULL DEFAULT (datetime('now')),
    fecha_modif         TEXT NOT NULL DEFAULT (datetime('now')),
    usuario_carga        TEXT,
    usuario_modif        TEXT,
    tipo_prestacion      TEXT,              -- tipo de servicio anterior (ej. 'Priv', 'Pas') importado de Nac_Priv
    suma_apn             INTEGER NOT NULL DEFAULT 1,  -- 1=suma para Antigüedad en la Administración Pública Nacional
    planta_nac           TEXT,              -- planta/organismo de origen (importado de Nac_Priv)
    motivo_baja          TEXT,
    CHECK (fecha_hasta IS NULL OR fecha_hasta >= fecha_desde)
);

CREATE INDEX IF NOT EXISTS idx_periodos_ndoc ON periodos_antiguedad(n_doc);

-- ---------------------------------------------------------------
-- CONFIG_AGENTE: parámetros individuales de cómputo por agente
-- (cada agente puede tener un criterio distinto, según lo pedido)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS config_agente (
    n_doc                       INTEGER PRIMARY KEY REFERENCES agentes(n_doc),
    fecha_inicio_conteo_grado   TEXT,   -- override: desde cuándo se cuenta el grado
    fecha_cierre_conteo         TEXT,   -- fecha tope hasta la cual se computa
    grado_base                  INTEGER NOT NULL DEFAULT 0,  -- grado de partida (si no arranca en 0)
    observaciones               TEXT,
    fecha_modif                 TEXT NOT NULL DEFAULT (datetime('now')),
    usuario_modif                TEXT
);

-- ---------------------------------------------------------------
-- TITULOS: títulos de cada agente (incluye título de grado
-- universitario -> id_niv = 'U')
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS titulos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    n_doc               INTEGER NOT NULL REFERENCES agentes(n_doc),
    id_niv              TEXT,             -- nivel educativo (U=universitario/grado, etc)
    titulo              TEXT,
    institucion         TEXT,
    fecha_egreso        TEXT,
    fecha_titulacion    TEXT,
    es_titulo_grado     INTEGER NOT NULL DEFAULT 0,  -- 1 si id_niv='U' (título de grado)
    observaciones       TEXT,
    activo              INTEGER NOT NULL DEFAULT 1,
    fecha_carga         TEXT NOT NULL DEFAULT (datetime('now')),
    origen              TEXT DEFAULT 'importado'
);

CREATE INDEX IF NOT EXISTS idx_titulos_ndoc ON titulos(n_doc);

-- ---------------------------------------------------------------
-- CALCULOS_ASCENSO: caché/histórico de cada corrida de cálculo,
-- para poder auditar "qué dijo el sistema" en cada 31/12.
-- No reemplaza el cálculo en vivo, es un registro histórico.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS calculos_ascenso (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    n_doc                   INTEGER NOT NULL REFERENCES agentes(n_doc),
    anio_evaluado           INTEGER NOT NULL,       -- año evaluado al 31/12
    antiguedad_computable_dias INTEGER NOT NULL,
    antiguedad_computable_texto TEXT NOT NULL,       -- "X años Y meses Z días"
    grados_acumulados       INTEGER NOT NULL,
    grados_anio_anterior    INTEGER NOT NULL,
    asciende                INTEGER NOT NULL,        -- 1/0
    grados_nuevos           INTEGER NOT NULL DEFAULT 0,
    fecha_efectiva_ascenso  TEXT,                     -- 1/1/(anio_evaluado+1) si asciende
    fecha_corrida           TEXT NOT NULL DEFAULT (datetime('now')),
    usuario_corrida          TEXT
);

CREATE INDEX IF NOT EXISTS idx_calculos_ndoc_anio ON calculos_ascenso(n_doc, anio_evaluado);

-- ---------------------------------------------------------------
-- AUDITORIA: bitácora inmutable de TODO cambio en datos críticos.
-- Nunca se borra ni se edita. Es la garantía de trazabilidad total.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS auditoria (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tabla           TEXT NOT NULL,
    operacion       TEXT NOT NULL,     -- INSERT | UPDATE | SOFT_DELETE
    registro_id     TEXT NOT NULL,     -- pk afectada (n_doc, id, etc)
    valor_anterior  TEXT,              -- JSON
    valor_nuevo     TEXT,              -- JSON
    usuario         TEXT,
    timestamp       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_auditoria_tabla_reg ON auditoria(tabla, registro_id);

-- ---------------------------------------------------------------
-- METADATA: parámetros generales del sistema (ej. fecha de corte
-- vigente, versión de esquema, etc.)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS metadata (
    clave   TEXT PRIMARY KEY,
    valor   TEXT NOT NULL
);
