-- ============================================================
-- MIGRACIÓN 001: Schema Neon — Mapa Industrial Argentina
-- Tablas operacionales y geometría.
-- oede_empleo NO está aquí → va en DuckDB local (data/analytics.db)
-- ============================================================

-- Extensiones necesarias (PostGIS para geometría y georef)
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;


-- ─────────────────────────────────────────────────────────────
-- TABLA: factory_events
-- Eventos de cierre (alimentado desde news DB o CSV manual)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS factory_events (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  empresa               VARCHAR(255) NOT NULL,
  localidad_raw         VARCHAR(255),       -- nombre tal como viene de la fuente
  localidad_norm        VARCHAR(255),       -- normalizado por georef-ar
  codgeo_prov           CHAR(2),            -- '06'
  codgeo_depto          CHAR(5),            -- '06270' ← clave de join con OEDE
  lat                   DECIMAL(10, 8),
  lng                   DECIMAL(11, 8),
  location              GEOGRAPHY(POINT, 4326),  -- columna PostGIS
  empleados_afectados   INTEGER,
  clae2                 CHAR(2),            -- sector AFIP de la fábrica (manufactura: 10-33)
  fecha_evento          DATE,
  tipo_evento           VARCHAR(50),        -- 'cierre', 'suspension', 'reduccion'
  fuente_url            TEXT,
  fuente_nombre         VARCHAR(100),       -- 'CEPA', 'IPA', 'periodico', etc.
  ingested_at           TIMESTAMPTZ DEFAULT NOW(),
  ingested_from         VARCHAR(255)        -- nombre del archivo fuente
);

-- Trigger: mantener `location` sincronizado cuando se cargan lat/lng
CREATE OR REPLACE FUNCTION sync_factory_location()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.lat IS NOT NULL AND NEW.lng IS NOT NULL THEN
    NEW.location = ST_SetSRID(ST_MakePoint(NEW.lng, NEW.lat), 4326)::geography;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_sync_factory_location
  BEFORE INSERT OR UPDATE OF lat, lng
  ON factory_events
  FOR EACH ROW EXECUTE FUNCTION sync_factory_location();

CREATE INDEX IF NOT EXISTS factory_events_location_gix ON factory_events USING GIST (location);
CREATE INDEX IF NOT EXISTS factory_events_codgeo_depto ON factory_events (codgeo_depto);
CREATE INDEX IF NOT EXISTS factory_events_fecha ON factory_events (fecha_evento);


-- ─────────────────────────────────────────────────────────────
-- TABLA: geo_departamentos
-- Geometría departamentos (cargada una vez desde INDEC shapefile)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS geo_departamentos (
  codgeo_depto          CHAR(5) PRIMARY KEY,
  nombre_depto          VARCHAR(255),
  codgeo_prov           CHAR(2),
  nombre_prov           VARCHAR(255),
  geom                  GEOMETRY(MULTIPOLYGON, 4326)
);
CREATE INDEX IF NOT EXISTS geo_departamentos_geom_gix ON geo_departamentos USING GIST (geom);


-- ─────────────────────────────────────────────────────────────
-- TABLA: event_weights
-- Pesos calculados por evento × período (output de compute_weights)
-- El denominador (puestos_total_depto) viene de DuckDB.oede_empleo
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS event_weights (
  event_id              UUID REFERENCES factory_events(id) ON DELETE CASCADE,
  periodo               DATE,
  puestos_total_depto   INTEGER,
  ratio_dependencia     DECIMAL(8, 6),      -- empleados_afectados / puestos_total_depto
  multiplicador         DECIMAL(4, 2),      -- según CLAE2
  peso_final            DECIMAL(8, 6),      -- ratio × multiplicador, capped 1.0
  computed_at           TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (event_id, periodo)
);


-- ─────────────────────────────────────────────────────────────
-- TABLA: pipeline_runs
-- Audit log de cada ingesta (Neon Y DuckDB).
-- Accesible desde GitHub Actions via DATABASE_URL.
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pipeline_runs (
  id                    SERIAL PRIMARY KEY,
  source                VARCHAR(50),        -- 'oede', 'indec_geo', 'eventos'
  destination           VARCHAR(20),        -- 'neon' o 'duckdb'
  filename              VARCHAR(255),
  file_sha256           CHAR(64),           -- para detectar duplicados
  records_inserted      INTEGER,
  records_updated       INTEGER,
  status                VARCHAR(20),        -- 'success', 'error', 'skipped'
  error_message         TEXT,
  ran_at                TIMESTAMPTZ DEFAULT NOW()
);
