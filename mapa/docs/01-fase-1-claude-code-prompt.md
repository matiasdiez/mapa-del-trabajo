# Proyecto: Mapa Industrial Argentina — Monitor de Cierres

## Contexto del proyecto

Estoy construyendo un mapa web interactivo que visualiza el cierre de fábricas
en Argentina, ponderado por impacto local relativo (no absoluto). El objetivo
es que un cierre en un pueblo pequeño donde representa el 20% del empleo formal
sea visualmente más relevante que un cierre equivalente en tamaño en una ciudad
industrial grande.

El mapa debe:
- Mostrar una superficie KDE ponderada sobre el territorio argentino
- Permitir navegar históricamente con un slider temporal (datos desde 2014)
- Tener una capa de puntos/burbujas para eventos documentados (cierres individuales)
- Actualizarse cuando se carguen datos nuevos manualmente

## Decisión de diseño: carga de datos manual

Todas las fuentes de datos externas (OEDE, geometría INDEC, eventos de noticias)
se cargan de forma **manual e intencional**, no mediante scraping automático de URLs.

Razones:
- Las URLs de datos gubernamentales argentinos cambian con frecuencia
- La validación humana de datos antes de ingresarlos es necesaria
- Permite QA antes de que los datos impacten el mapa publicado

**Flujo de trabajo operativo:**
1. El operador descarga el archivo (CSV, shapefile, GeoJSON) manualmente
2. Lo deposita en la carpeta `data/incoming/<fuente>/`
3. Ejecuta el comando de ingesta: `python -m pipeline ingest --source oede --file <ruta>`
4. El pipeline valida, procesa, hace upsert en Neon y archiva el archivo
5. Si hay eventos nuevos o datos nuevos, ejecuta: `python -m pipeline build-tiles`
6. El comando de tiles genera PMTiles y los sube a Cloudflare R2

GitHub Actions **no** descarga datos externos. Sólo puede dispararse manualmente
(`workflow_dispatch`) para ejecutar `build-tiles` si ya hay datos nuevos en la base de datos.

## Stack técnico — decisiones tomadas

**Backend / datos — arquitectura híbrida:**

| Componente | Tecnología | Qué almacena |
|---|---|---|
| Base operacional | Neon (PostgreSQL + PostGIS) | `factory_events`, `geo_departamentos`, `event_weights`, `pipeline_runs` |
| Base analítica | DuckDB (archivo local `data/analytics.db`) | `oede_empleo`, cualquier CSV/XLS grande |
| Tiles | Cloudflare R2 (PMTiles estáticos) | `kde.pmtiles`, `eventos.pmtiles`, `departamentos.pmtiles` |

Neon: datos operacionales y geometría. Accesible desde cualquier lugar (local + GitHub Actions).
DuckDB: datos analíticos grandes (OEDE, futuras fuentes CSV/XLS). Solo corre localmente.
GitHub Actions: solo necesita DATABASE_URL (Neon) + credenciales R2. No necesita DuckDB.

**Python pipeline con CLI:** procesamiento, cálculo de pesos, KDE, generación de tiles.
**Tippecanoe:** generación de PMTiles desde GeoJSON.

**Frontend:**
- Astro + Svelte
- MapLibre GL JS (open source, sin API key)
- pmtiles JS: cliente para leer tiles desde R2

## Por qué esta separación

Neon tiene un límite de 500MB en el tier gratuito. El OEDE completo (todos los sectores
desde 2014) supera ese límite. DuckDB no tiene límite de almacenamiento y es extremadamente
eficiente para consultas analíticas sobre CSV/Parquet sin necesidad de servidor.

La regla es simple:
- **¿Dato operacional pequeño o geometría?** → Neon
- **¿CSV o XLS grande?** → DuckDB
- **¿Tiles para el frontend?** → R2

## Fuentes de datos — dónde descargarlas

Ninguna URL se hardcodea como endpoint de descarga automática. Se documentan
como referencia para el operador:

| Fuente | Dónde descargar | Formato | Frecuencia |
|--------|-----------------|---------|------------|
| OEDE empleo por departamento | argentina.gob.ar/trabajo/estadisticas/oede-estadisticas-provinciales | CSV | Trimestral |
| OEDE empleo por departamento (alternativo) | datos.produccion.gob.ar → "Puestos de trabajo por departamento/partido y sector" | CSV | Mensual (cuando disponible) |
| Geometría departamentos INDEC | geoservicios.indec.gov.ar/codgeo → descargas | SHP / GeoJSON | Una vez (Censo 2022) |
| Geometría provincias INDEC | mismo portal | SHP / GeoJSON | Una vez |
| Eventos de cierre (news DB) | export desde la base de datos del proyecto de noticias | CSV / JSON | A demanda |
| Nomenclador CLAE | datos.produccion.gob.ar → "Nomenclador CLAE" | CSV | Una vez (rara vez cambia) |

## Estructura de carpetas del proyecto

```
mapa-industrial-ar/
│
├── pipeline/                        # Python: ETL + pesos + KDE + tiles
│   ├── __init__.py
│   ├── __main__.py                  # Punto de entrada CLI: `python -m pipeline`
│   ├── commands/
│   │   ├── ingest.py                # Subcomando: ingest
│   │   ├── build_tiles.py           # Subcomando: build-tiles
│   │   └── validate.py              # Subcomando: validate (dry-run sin escribir)
│   ├── loaders/
│   │   ├── base.py                  # Clase base DataLoader con validación común
│   │   ├── oede.py                  # Loader para CSVs del OEDE
│   │   ├── indec_geo.py             # Loader para shapefiles INDEC
│   │   └── eventos.py               # Loader para CSV/JSON de eventos de cierre
│   ├── compute/
│   │   ├── weights.py               # Calcula ratio_dependencia y peso_final
│   │   └── kde.py                   # KDE ponderado → GeoJSON de contornos
│   ├── tiles/
│   │   ├── generate.py              # Llama Tippecanoe, produce PMTiles
│   │   └── upload.py                # Sube PMTiles a Cloudflare R2
│   ├── db/
│   │   ├── neon.py                  # Conexión a Neon via psycopg2
│   │   ├── duckdb.py                # Conexión a DuckDB local + init schema
│   │   └── migrations/              # SQL de creación de tablas en Neon
│   │       └── 001_initial.sql
│   ├── config.py                    # Variables de entorno y constantes
│   ├── multipliers.py               # Tabla de multiplicadores sectoriales por CLAE2
│   └── requirements.txt
│
├── data/
│   ├── incoming/                    # Depositar archivos descargados aquí
│   │   ├── oede/                    # CSVs del OEDE
│   │   ├── indec_geo/               # Shapefiles / GeoJSON del INDEC
│   │   └── eventos/                 # CSVs de eventos de cierre
│   ├── processed/                   # Archivos movidos aquí después de ingestar
│   │   ├── oede/
│   │   ├── indec_geo/
│   │   └── eventos/
│   ├── analytics.db                 # DuckDB — base analítica local (NO commitear)
│   └── .gitignore                   # data/incoming/*, data/processed/*, analytics.db
│
├── .github/
│   └── workflows/
│       └── build_tiles.yml          # workflow_dispatch manual para build-tiles en Actions
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Map.svelte           # MapLibre GL JS wrapper principal
│   │   │   ├── TimeSlider.svelte    # Slider de navegación temporal
│   │   │   ├── LayerControls.svelte # Toggle de capas (KDE / burbujas / base)
│   │   │   └── EventPanel.svelte    # Panel lateral / tooltip de eventos
│   │   ├── lib/
│   │   │   ├── mapStore.ts          # Svelte store: período activo, capas visibles
│   │   │   └── tilesConfig.ts       # URLs de PMTiles en R2
│   │   └── pages/
│   │       └── index.astro
│   └── package.json
│
├── scripts/
│   └── seed_test_events.sql         # Datos de prueba para desarrollo
│
└── docs/
    ├── teoria-economica.md          # Marco teórico del proyecto
    ├── operaciones.md               # Cómo cargar datos manualmente paso a paso
    └── architecture.md
```

## Schema de Neon (pipeline/db/migrations/001_initial.sql)

```sql
-- ============================================================
-- MIGRACIÓN 001: Schema Neon
-- Tablas operacionales y geometría. NO incluye oede_empleo.
-- ============================================================

-- Eventos de cierre (alimentado desde news DB o CSV manual)
CREATE TABLE IF NOT EXISTS factory_events (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  empresa               VARCHAR(255) NOT NULL,
  localidad_raw         VARCHAR(255),      -- nombre tal como viene de la fuente
  localidad_norm        VARCHAR(255),      -- normalizado por georef-ar
  codgeo_prov           CHAR(2),           -- '06'
  codgeo_depto          CHAR(5),           -- '06270' ← clave de join con OEDE
  lat                   DECIMAL(10, 8),
  lng                   DECIMAL(11, 8),
  location              GEOGRAPHY(POINT, 4326),  -- columna PostGIS
  empleados_afectados   INTEGER,
  clae2                 CHAR(2),           -- sector AFIP de la fábrica (manufactura: 10-33)
  fecha_evento          DATE,
  tipo_evento           VARCHAR(50),       -- 'cierre', 'suspension', 'reduccion'
  fuente_url            TEXT,
  fuente_nombre         VARCHAR(100),      -- 'CEPA', 'IPA', 'periodico', etc.
  ingested_at           TIMESTAMPTZ DEFAULT NOW(),
  ingested_from         VARCHAR(255)       -- nombre del archivo fuente
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

CREATE INDEX factory_events_location_gix ON factory_events USING GIST (location);
CREATE INDEX factory_events_codgeo_depto ON factory_events (codgeo_depto);
CREATE INDEX factory_events_fecha ON factory_events (fecha_evento);


-- Geometría departamentos (cargada una vez desde INDEC shapefile)
CREATE TABLE IF NOT EXISTS geo_departamentos (
  codgeo_depto          CHAR(5) PRIMARY KEY,
  nombre_depto          VARCHAR(255),
  codgeo_prov           CHAR(2),
  nombre_prov           VARCHAR(255),
  geom                  GEOMETRY(MULTIPOLYGON, 4326)
);
CREATE INDEX geo_departamentos_geom_gix ON geo_departamentos USING GIST (geom);


-- Pesos calculados por evento × período (output de compute_weights)
CREATE TABLE IF NOT EXISTS event_weights (
  event_id              UUID REFERENCES factory_events(id) ON DELETE CASCADE,
  periodo               DATE,
  puestos_total_depto   INTEGER,
  ratio_dependencia     DECIMAL(8, 6),     -- empleados_afectados / puestos_total_depto
  multiplicador         DECIMAL(4, 2),     -- según CLAE2
  peso_final            DECIMAL(8, 6),     -- ratio × multiplicador, capped 1.0
  computed_at           TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (event_id, periodo)
);


-- Estado del pipeline: registro de cada ingesta (Neon y DuckDB)
CREATE TABLE IF NOT EXISTS pipeline_runs (
  id                    SERIAL PRIMARY KEY,
  source                VARCHAR(50),       -- 'oede', 'indec_geo', 'eventos'
  destination           VARCHAR(20),       -- 'neon' o 'duckdb'
  filename              VARCHAR(255),
  file_sha256           CHAR(64),          -- para detectar duplicados
  records_inserted      INTEGER,
  records_updated       INTEGER,
  status                VARCHAR(20),       -- 'success', 'error', 'skipped'
  error_message         TEXT,
  ran_at                TIMESTAMPTZ DEFAULT NOW()
);
```

## Schema de DuckDB (pipeline/db/duckdb.py → función init_schema)

```sql
-- ============================================================
-- Schema DuckDB — base analítica local
-- Archivo: data/analytics.db (no commitear al repo)
-- ============================================================

-- OEDE: empleo registrado por departamento × CLAE2 × período
-- Todos los sectores (sin filtrar sólo manufactura)
CREATE TABLE IF NOT EXISTS oede_empleo (
  codgeo_depto  VARCHAR(5) NOT NULL,
  clae2         VARCHAR(2),          -- código CLAE a 2 dígitos
  letra         VARCHAR(1),          -- letra de sector ('C' = manufactura, 'G' = comercio, etc.)
  periodo       DATE    NOT NULL,    -- primer día del mes: 2024-01-01
  puestos       INTEGER,
  ingested_from VARCHAR(255)         -- nombre del archivo fuente
);

CREATE UNIQUE INDEX IF NOT EXISTS oede_pk
  ON oede_empleo (codgeo_depto, clae2, periodo);

-- Vista: total de empleo por departamento y período
-- Usar esta vista como denominador en compute_weights
CREATE OR REPLACE VIEW oede_total_depto AS
SELECT
  codgeo_depto,
  periodo,
  SUM(puestos) AS puestos_total
FROM oede_empleo
GROUP BY codgeo_depto, periodo;

-- Vista: total de empleo manufacturero por departamento y período
CREATE OR REPLACE VIEW oede_manufactura_depto AS
SELECT
  codgeo_depto,
  periodo,
  SUM(puestos) AS puestos_manufactura
FROM oede_empleo
WHERE letra = 'C'
GROUP BY codgeo_depto, periodo;
```

## Multiplicadores sectoriales por CLAE2

```python
# pipeline/multipliers.py
# Multiplicadores keynesiano-insumo-producto por sector CLAE2
# Calibrados para Argentina (mercado interno): canal de consumo + encadenamiento local
# Fuente: estimaciones propias basadas en literatura de economía regional argentina

MULTIPLICADORES: dict[str, float] = {
    "10": 1.8,   # Elaboración de alimentos
    "11": 1.6,   # Elaboración de bebidas
    "12": 1.4,   # Elaboración de tabaco
    "13": 2.1,   # Fabricación de productos textiles
    "14": 2.0,   # Confección de prendas de vestir
    "15": 1.9,   # Curtido y adobo de cueros; calzado
    "16": 1.7,   # Producción de madera; artículos de madera
    "17": 1.8,   # Fabricación de papel y cartón
    "18": 1.6,   # Impresión y reproducción de grabaciones
    "19": 1.5,   # Fabricación de coque y productos de petróleo
    "20": 1.9,   # Fabricación de sustancias y productos químicos
    "21": 1.8,   # Fabricación de productos farmacéuticos
    "22": 1.8,   # Fabricación de productos de caucho y plástico
    "23": 1.7,   # Fabricación de otros productos minerales no metálicos
    "24": 2.2,   # Fabricación de metales comunes (siderurgia, aluminio)
    "25": 2.1,   # Fabricación de productos elaborados de metal
    "26": 2.0,   # Fabricación de equipos de cómputo y electrónica
    "27": 2.3,   # Fabricación de maquinaria y aparatos eléctricos
    "28": 2.2,   # Fabricación de maquinaria y equipo n.c.p.
    "29": 2.4,   # Fabricación de vehículos automotores
    "30": 2.3,   # Fabricación de otro equipo de transporte
    "31": 1.9,   # Fabricación de muebles
    "32": 1.8,   # Otras industrias manufactureras
    "33": 1.7,   # Reparación e instalación de maquinaria
}

MULTIPLICADOR_DEFAULT = 1.8


def get_multiplicador(clae2: str | None) -> float:
    if clae2 is None:
        return MULTIPLICADOR_DEFAULT
    return MULTIPLICADORES.get(str(clae2).zfill(2), MULTIPLICADOR_DEFAULT)
```

## Fórmula de peso (pipeline/compute/weights.py)

```python
def calcular_peso(
    empleados_afectados: int,
    puestos_total_depto: int,
    clae2: str | None,
) -> dict:
    """
    Calcula el peso de impacto local de un evento de cierre.

    El ratio_dependencia mide qué fracción del empleo formal del departamento
    se pierde directamente. El multiplicador captura el efecto de arrastre
    sobre empleo indirecto (consumo local + proveedores).

    Returns dict con todas las variables intermedias para trazabilidad.
    """
    from pipeline.multipliers import get_multiplicador

    puestos_base = max(puestos_total_depto, 1)  # evitar división por cero
    ratio = empleados_afectados / puestos_base
    multiplicador = get_multiplicador(clae2)
    peso = min(ratio * multiplicador, 1.0)  # cap: nunca mayor que 1.0

    return {
        "ratio_dependencia": round(ratio, 6),
        "multiplicador": multiplicador,
        "peso_final": round(peso, 6),
    }
```

## CLI: comandos del pipeline

```bash
# Validar un archivo sin escribir nada (dry-run)
python -m pipeline validate --source oede --file data/incoming/oede/puestos_2024_q1.csv

# Ingestar datos OEDE
python -m pipeline ingest --source oede --file data/incoming/oede/puestos_2024_q1.csv

# Ingestar geometría INDEC (sólo necesario una vez o cuando haya actualización)
python -m pipeline ingest --source indec-geo --file data/incoming/indec_geo/departamentos.geojson

# Ingestar eventos de cierre desde CSV
python -m pipeline ingest --source eventos --file data/incoming/eventos/cierres_2024.csv

# Calcular pesos para todos los eventos sin peso calculado
python -m pipeline compute-weights

# Regenerar superficie KDE y actualizar tiles
python -m pipeline build-tiles

# Pipeline completo (compute-weights + build-tiles)
python -m pipeline rebuild

# Ver estado del sistema
python -m pipeline status
```

## Formato esperado de cada fuente

### OEDE CSV (columnas mínimas requeridas)

```
codigo_departamento_indec,clae2,fecha,puestos,letra
06270,13,2024-01-01,1250,C
```

El loader `oede.py` debe:
- Zero-pad `codigo_departamento_indec` a 5 chars
- Parsear `fecha` como DATE (acepta YYYYMM, YYYY-MM-01, YYYY-MM)
- Filtrar sólo registros con `letra == 'C'` (manufactura) o `clae2` entre 10-33
- Detectar duplicados por checksum SHA256 del archivo completo → registrar en `pipeline_runs`

### INDEC Geometría (GeoJSON o Shapefile)

El loader `indec_geo.py` debe:
- Aceptar `.geojson`, `.shp`, o `.zip` (shapefile comprimido)
- Usar geopandas para leer
- Normalizar a WGS84 (EPSG:4326) si la proyección es otra
- Extraer `IN1` o `link` como `codgeo_depto` (5 chars)

### Eventos CSV (columnas mínimas requeridas)

```
empresa,localidad_raw,codgeo_depto,lat,lng,empleados_afectados,clae2,fecha_evento,tipo_evento,fuente_url
```

Si `codgeo_depto` está vacío pero hay `localidad_raw`, el loader
debe llamar a la API georef-ar para resolverlo antes de insertar.

## Variables de entorno necesarias

```env
# .env (nunca commitear)

# Neon — connection string completo desde el dashboard
# → proyecto → "Connection string" → copiar con ?sslmode=require
DATABASE_URL=postgresql://user:password@ep-xxx.us-east-2.aws.neon.tech/dbname?sslmode=require

# DuckDB — ruta al archivo local (relativa a la raíz del proyecto)
# No necesita credenciales, es un archivo local
DUCKDB_PATH=data/analytics.db

# Cloudflare R2
R2_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET_NAME=mapa-industrial-tiles
R2_PUBLIC_URL=https://pub-xxx.r2.dev

# APIs externas
GEOREF_API_BASE=https://apis.datos.gob.ar/georef/api
```

> **GitHub Actions** sólo necesita `DATABASE_URL` y las vars de R2.
> `DUCKDB_PATH` no se usa en CI: los pesos ya están pre-calculados en Neon.

## Tarea de inicio (Fase 1)

Implementar el módulo `pipeline/loaders/oede.py` y el comando `ingest` para OEDE.

El loader debe:

1. Recibir la ruta a un archivo CSV descargado manualmente
2. Calcular SHA256 del archivo y verificar en `pipeline_runs` si ya fue procesado
   (si existe y status='success', loggear "ya procesado" y salir sin error)
3. Validar que el CSV tenga las columnas requeridas; si faltan, lanzar error descriptivo
   con las columnas que se esperaban y las que se encontraron
4. Parsear y normalizar:
   - `codigo_departamento_indec` → `codgeo_depto` CHAR(5) con zero-padding
   - `fecha` → DATE (manejar formatos YYYYMM, YYYY-MM, YYYY-MM-DD)
   - `clae2` → CHAR(2) con zero-padding
5. Filtrar sólo filas de manufactura (letra == 'C' o clae2 entre '10' y '33')
6. Hacer upsert en `oede_empleo` (clave única: codgeo_depto + clae2 + periodo)
7. Mover el archivo original a `data/processed/oede/` con timestamp en el nombre
8. Registrar en `pipeline_runs`: filename, sha256, records_inserted, records_updated, status

Al final, imprimir resumen:
```
✓ OEDE procesado: 12.450 filas manufactureras
  Insertadas: 8.200 | Actualizadas: 4.250 | Período: 2014-01-01 → 2024-03-01
  Departamentos cubiertos: 512 | Archivo archivado: data/processed/oede/...
```

Usar `psycopg2-binary`, `pandas`, `click` (para el CLI), `rich` (para output con colores).

No implementar todavía compute_weights ni build_tiles.
Validar el loader con un archivo de prueba pequeño antes de escalar.

### Implementación de `pipeline/db/neon.py`

```python
# pipeline/db/neon.py
import os
import contextlib
import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ["DATABASE_URL"]


def get_connection():
    return psycopg2.connect(DATABASE_URL)


@contextlib.contextmanager
def transaction():
    """
    Context manager: abre conexión, expone cursor, commit al salir,
    rollback en excepción.

    Uso:
        with transaction() as cur:
            cur.execute("INSERT INTO ...")
    """
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                yield cur
    finally:
        conn.close()


def execute_values(cur, sql: str, data: list[tuple], page_size: int = 1000):
    """Upserts en batch via psycopg2.extras.execute_values."""
    psycopg2.extras.execute_values(cur, sql, data, page_size=page_size)
```

### Implementación de `pipeline/db/duckdb.py`

```python
# pipeline/db/duckdb.py
import os
import duckdb

DUCKDB_PATH = os.environ.get("DUCKDB_PATH", "data/analytics.db")


def get_connection(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Conexión al archivo DuckDB local."""
    return duckdb.connect(DUCKDB_PATH, read_only=read_only)


def init_schema():
    """
    Crea tablas y vistas en DuckDB si no existen.
    Llamar una vez al inicio del pipeline o al ingestar por primera vez.
    """
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS oede_empleo (
            codgeo_depto  VARCHAR(5) NOT NULL,
            clae2         VARCHAR(2),
            letra         VARCHAR(1),
            periodo       DATE NOT NULL,
            puestos       INTEGER,
            ingested_from VARCHAR(255)
        )
    """)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS oede_pk
            ON oede_empleo (codgeo_depto, clae2, periodo)
    """)
    # Vistas: recrear siempre (CREATE OR REPLACE)
    conn.execute("""
        CREATE OR REPLACE VIEW oede_total_depto AS
        SELECT codgeo_depto, periodo, SUM(puestos) AS puestos_total
        FROM oede_empleo
        GROUP BY codgeo_depto, periodo
    """)
    conn.execute("""
        CREATE OR REPLACE VIEW oede_manufactura_depto AS
        SELECT codgeo_depto, periodo, SUM(puestos) AS puestos_manufactura
        FROM oede_empleo
        WHERE letra = 'C'
        GROUP BY codgeo_depto, periodo
    """)
    conn.close()


def upsert_oede(records: list[dict]):
    """
    Inserta o reemplaza registros en oede_empleo.
    DuckDB no tiene ON CONFLICT como PostgreSQL;
    se usa INSERT OR REPLACE con la clave única definida por el índice.
    """
    conn = get_connection()
    conn.executemany("""
        INSERT OR REPLACE INTO oede_empleo
            (codgeo_depto, clae2, letra, periodo, puestos, ingested_from)
        VALUES (?, ?, ?, ?, ?, ?)
    """, [
        (r["codgeo_depto"], r["clae2"], r["letra"],
         r["periodo"], r["puestos"], r["ingested_from"])
        for r in records
    ])
    conn.close()
```

### `requirements.txt` de la Fase 1

```
psycopg2-binary>=2.9
duckdb>=0.10
pandas>=2.0
click>=8.1
rich>=13.0
httpx>=0.27
python-dotenv>=1.0
```

### `pipeline/config.py`

```python
import os
from dotenv import load_dotenv

load_dotenv()  # carga .env si existe; sin error si no hay archivo

DATABASE_URL = os.environ["DATABASE_URL"]
DUCKDB_PATH  = os.environ.get("DUCKDB_PATH", "data/analytics.db")
GEOREF_API   = os.environ.get("GEOREF_API_BASE", "https://apis.datos.gob.ar/georef/api")

R2_ACCOUNT_ID        = os.environ.get("R2_ACCOUNT_ID", "")
R2_ACCESS_KEY_ID     = os.environ.get("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET_NAME       = os.environ.get("R2_BUCKET_NAME", "mapa-industrial-tiles")
R2_PUBLIC_URL        = os.environ.get("R2_PUBLIC_URL", "")
```

### Cambio en el loader OEDE

El loader `oede.py` ahora escribe en **DuckDB** en lugar de Neon.
Flujo interno:

```python
from pipeline.db import duckdb as duck_db
from pipeline.db import neon

duck_db.init_schema()          # no-op si las tablas ya existen
records = parsear_csv(file)    # retorna lista de dicts
duck_db.upsert_oede(records)   # escribe en DuckDB

# El audit log sigue en Neon (accesible desde CI)
with neon.transaction() as cur:
    cur.execute("""
        INSERT INTO pipeline_runs
            (source, destination, filename, file_sha256,
             records_inserted, status)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, ('oede', 'duckdb', filename, sha256, len(records), 'success'))
```

> **Nota sobre la data ya cargada en Neon:** si tenés `oede_empleo` en Neon
> con datos de manufactura, podés mantenerla por ahora. Una vez que DuckDB
> tenga todos los sectores y `compute-weights` corra correctamente leyendo
> desde DuckDB, podés hacer `DROP TABLE oede_empleo CASCADE` en Neon para
> recuperar espacio.
```
