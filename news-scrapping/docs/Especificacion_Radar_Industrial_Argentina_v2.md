# Especificación de Proyecto: Radar Industrial Argentina (ETL & Observatorio Laboral) — v2

## 1. Visión General del Proyecto

Construir una herramienta automatizada y de costo cero que rastree, procese y consolide noticias sobre despidos, suspensiones, conflictos gremiales y cierres de plantas industriales en Argentina.

El objetivo final es alimentar una base de datos en **Supabase** (PostgreSQL + PostGIS) vinculada a códigos oficiales INDEC y clasificadores sectoriales (CLAE2) para cruzar los eventos con el Observatorio de Empleo y Dinámica Empresarial (OEDE), calcular el impacto relativo del empleo y proyectar las capas en un mapa interactivo.

---

## 2. Decisiones de Arquitectura y Stack Tecnológico

* **Orquestador / Ejecución:** `GitHub Actions` (cron periódico cada 6 o 12 horas, tier gratuito). Incluye `workflow_dispatch` manual para evitar la suspensión automática por inactividad (GH Actions suspende crons en repos sin actividad > 60 días).
* **Core ETL:** `Python 3.11+` modularizado.
* **Descubrimiento de Noticias:** Feeds RSS dinámicos de `Google News` con queries booleanas sectoriales y regionales, complementados con scrapers directos a fuentes sindicales y especializadas.
* **Extracción de Contenido (Scraping):** `trafilatura` (limpieza semántica del cuerpo del texto, sin ruido publicitario ni menús).
* **Deduplicación Semántica:** `rapidfuzz` para fuzzy matching de nombres de empresa (ratio ≥ 85%) antes del chequeo en Supabase.
* **Extracción Estructurada & Normalización Sectorial:** `Google Gemini API` (`gemini-2.5-flash`) mediante *Structured Outputs* (JSON Schema estricto). Clasifica el sector y mapea el código **CLAE a 2 dígitos (`clae2`)** para manufactura (valores 10 a 33). Incluye few-shot examples para mejorar la precisión de clasificación sectorial.
* **Normalización Geográfica & Códigos INDEC:** [Georef-ar API](https://georef-ar-api.readthedocs.io/) (`apis.datos.gob.ar/georef/api/localidades`). Resuelve coordenadas (`lat`, `lng`), nombre normalizado (`localidad_norm`), código de provincia (`codgeo_provincia`) y código departamental INDEC (`codgeo_depto`). Incluye **cache local** de pares `(localidad, provincia)` ya resueltos para reducir llamadas redundantes.
* **Base de Datos & GIS:** `Supabase` (PostgreSQL con extensión `postgis`). Conexión mediante `psycopg2` / `SQLAlchemy`.
* **Notificaciones:** Hermes Agent (corriendo en la computadora personal) consulta periódicamente la tabla `pipeline_runs` en Supabase y genera mensajes de alerta en Signal. El pipeline no necesita alcanzar ningún endpoint externo — Hermes va a buscar los datos.

---

## 3. Esquema de Base de Datos en Supabase

### 3.1 Tabla principal `factory_events`

```sql
-- Habilitar extensión PostGIS para queries espaciales
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS factory_events (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- Empresa
    empresa VARCHAR(255) NOT NULL,
    empresa_normalizada VARCHAR(255) NOT NULL,

    -- Geografía
    localidad_raw VARCHAR(255),
    localidad_norm VARCHAR(255),               -- Nombre oficial según georef-ar
    localidades_adicionales JSONB DEFAULT '[]', -- Para plantas multi-localidad (ej: Ford Pacheco + Gral. Pacheco)
    provincia VARCHAR(255) NOT NULL,
    codgeo_provincia CHAR(2),                  -- Código INDEC de provincia (ej: '06')
    codgeo_depto CHAR(5),                      -- Clave crítica para join con OEDE (ej: '06270')
    lat DECIMAL(10, 8),
    lng DECIMAL(11, 8),
    location GEOGRAPHY(POINT, 4326),           -- Columna PostGIS espacial (generada por trigger)

    -- Evento laboral
    empleados_afectados INT,
    empleados_afectados_es_estimacion BOOLEAN DEFAULT FALSE, -- TRUE si el número es aproximado
    fecha_evento DATE,
    tipo_evento VARCHAR(50) NOT NULL,          -- 'cierre', 'despidos', 'suspensiones', 'procedimiento_preventivo_crisis'
    estado_evento VARCHAR(30) DEFAULT 'confirmado', -- 'confirmado', 'rumor', 'en_negociacion', 'revertido'
    sindicato VARCHAR(100),                    -- UOM, SMATA, UOCRA, etc.
    causa_declarada VARCHAR(100),              -- 'importaciones', 'caida_demanda', 'deuda', 'cierre_mercado', etc.

    -- Clasificación sectorial
    sector VARCHAR(100),
    clae2 CHAR(2),                             -- Código CLAE a 2 dígitos (10 a 33 para manufactura)

    -- Contenido y fuentes
    resumen TEXT,
    fuente_url TEXT UNIQUE NOT NULL,
    fuentes_adicionales TEXT[] DEFAULT '{}',

    -- Metadatos del pipeline
    modelo_llm VARCHAR(50),                    -- 'gemini-2.5-flash', para reprocessing futuro
    confidence_score DECIMAL(4, 3),            -- Float 0.0 a 1.0; confianza de la extracción LLM
    procesado_at TIMESTAMPTZ,                  -- Cuándo corrió el pipeline (distinto de created_at)
    verificado BOOLEAN DEFAULT FALSE,          -- Para curación manual posterior

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Índices
CREATE INDEX IF NOT EXISTS factory_events_location_gix   ON factory_events USING GIST (location);
CREATE INDEX IF NOT EXISTS idx_factory_empresa_norm      ON factory_events (empresa_normalizada);
CREATE INDEX IF NOT EXISTS idx_factory_codgeo_depto      ON factory_events (codgeo_depto);
CREATE INDEX IF NOT EXISTS idx_factory_fecha_evento      ON factory_events (fecha_evento);
CREATE INDEX IF NOT EXISTS idx_factory_clae2             ON factory_events (clae2);
CREATE INDEX IF NOT EXISTS idx_factory_estado_evento     ON factory_events (estado_evento);

-- Trigger PostGIS: sincroniza 'location' a partir de lat/lng
CREATE OR REPLACE FUNCTION sync_factory_location()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.lat IS NOT NULL AND NEW.lng IS NOT NULL THEN
    NEW.location = ST_SetSRID(ST_MakePoint(NEW.lng, NEW.lat), 4326)::geography;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sync_factory_location ON factory_events;
CREATE TRIGGER trg_sync_factory_location
  BEFORE INSERT OR UPDATE OF lat, lng
  ON factory_events
  FOR EACH ROW EXECUTE FUNCTION sync_factory_location();
```

### 3.2 Tabla de monitoreo `pipeline_runs`

```sql
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ejecutado_at TIMESTAMPTZ DEFAULT NOW(),
    urls_descubiertas INT DEFAULT 0,
    urls_procesadas INT DEFAULT 0,
    eventos_insertados INT DEFAULT 0,
    eventos_actualizados INT DEFAULT 0,
    eventos_descartados INT DEFAULT 0,
    errores_scraping INT DEFAULT 0,
    errores_llm INT DEFAULT 0,
    errores_georef INT DEFAULT 0,
    detalle_errores JSONB DEFAULT '[]'
);
```

### 3.3 Tabla auxiliar `oede_empleo_depto`

```sql
-- Datos del Observatorio de Empleo y Dinámica Empresarial (MTEySS)
-- Actualizar periódicamente desde el portal de datos abiertos
CREATE TABLE IF NOT EXISTS oede_empleo_depto (
    codgeo_depto CHAR(5) PRIMARY KEY,
    nombre_depto VARCHAR(255),
    codgeo_provincia CHAR(2),
    empleo_registrado_total INT,
    empleo_registrado_manufactura INT,
    periodo VARCHAR(7),                        -- 'YYYY-MM'
    actualizado_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 3.4 Cache de localidades resueltas `georef_cache`

```sql
-- Cache para evitar llamadas repetidas a Georef-ar API
CREATE TABLE IF NOT EXISTS georef_cache (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    localidad_raw VARCHAR(255) NOT NULL,
    provincia_raw VARCHAR(255) NOT NULL,
    localidad_norm VARCHAR(255),
    codgeo_provincia CHAR(2),
    codgeo_depto CHAR(5),
    lat DECIMAL(10, 8),
    lng DECIMAL(11, 8),
    resuelto_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (localidad_raw, provincia_raw)
);
```

---

## 4. Pipeline de Procesamiento Paso a Paso

### Paso 1: Ingesta de Feeds (Discovery)

**Google News RSS** con codificación `hl=es-419&gl=AR&ceid=AR:es-419`:

1. `("cierre de planta" OR "cierre de fábrica" OR "baja de persianas" OR "suspensiones") AND ("trabajadores" OR "empleados" OR "operarios") AND Argentina`
2. `("despidos" OR "paralización") AND ("metalúrgica" OR "textil" OR "calzado" OR "autopartista" OR "alimenticia" OR "química") AND Argentina`
3. `("parque industrial" OR "fábrica") AND ("suspende" OR "echa" OR "cierra") AND ("Pilar" OR "Córdoba" OR "Santa Fe" OR "Tierra del Fuego" OR "Tucumán" OR "Buenos Aires")`

> **Nota:** Validar que cada URL de Google News RSS generada efectivamente retorna ítems antes de parsear. Las queries booleanas largas pueden truncarse silenciosamente.

**Fuentes directas adicionales** (scrapers dedicados en `src/scraper.py`):

* **APL** (Agencia Periodística Laboral): feed RSS o scraping del índice de noticias.
* **Infogremiales**: portal sindical con cobertura de conflictos antes de que lleguen a medios nacionales.
* **Portales provinciales:** La Voz del Interior (Córdoba), El Litoral (Santa Fe), La Gaceta (Tucumán), Diario Río Negro. Cubren conflictos locales que los nacionales ignoran.
* **Cámaras sectoriales:** ADIMRA, CIRA — secciones de prensa institucional.

### Paso 2: Filtrado Preliminar y Scraping

- Verificar si la URL ya existe en `fuente_url` o en el array `fuentes_adicionales`. Descartar si ya fue registrada.
- Extraer texto limpio del cuerpo con `trafilatura`. Descartar páginas vacías o con texto menor a 200 caracteres.

### Paso 3: Extracción Estructurada con Gemini (JSON Schema)

**JSON Schema enriquecido:**

```json
{
  "es_relevante": true,
  "empresa": "Nombre Oficial de la Empresa",
  "localidad": "Quilmes",
  "provincia": "Buenos Aires",
  "sector": "metalurgica",
  "clae2": "25",
  "tipo_evento": "cierre",
  "estado_evento": "confirmado",
  "empleados_afectados": 120,
  "empleados_afectados_es_estimacion": false,
  "sindicato": "UOM",
  "causa_declarada": "importaciones",
  "fecha_aproximada": "YYYY-MM-DD",
  "resumen": "Resumen factual del conflicto en 2 oraciones.",
  "confidence_score": 0.91
}
```

*Si no refiere a un conflicto fabril concreto en Argentina, el modelo debe retornar `"es_relevante": false`.*

**Few-shot examples para `clae2`** (incluir en el system prompt para mejorar la precisión de clasificación):

```
Actividad: "Planta de fabricación de autopartes metálicas" → clae2: "29"
Actividad: "Frigorífico de exportación bovina" → clae2: "10"
Actividad: "Hilandería y tejeduría de algodón" → clae2: "13"
Actividad: "Laboratorio farmacéutico" → clae2: "21"
Actividad: "Industria petroquímica" → clae2: "20"
Actividad: "Fábrica de calzado de cuero" → clae2: "15"
```

**Valores válidos de `tipo_evento`:** `cierre`, `despidos`, `suspensiones`, `procedimiento_preventivo_crisis`  
**Valores válidos de `estado_evento`:** `confirmado`, `rumor`, `en_negociacion`, `revertido`  
**Valores válidos de `causa_declarada`:** `importaciones`, `caida_demanda`, `deuda`, `cierre_mercado`, `reestructuracion`, `quiebra`, `otro`  
**Valores válidos de `sindicato`:** `UOM`, `SMATA`, `UOCRA`, `UATRE`, `ATILRA`, `AOT`, `FATAGA`, `FIQUIMIA`, `otro`

### Paso 4: Georreferenciación y Resolución INDEC (Georef-ar API)

**Chequeo de cache primero:**

```python
# Antes de llamar a Georef-ar, consultar tabla georef_cache en Supabase
resultado = db.query(
    "SELECT * FROM georef_cache WHERE localidad_raw = %s AND provincia_raw = %s",
    (localidad, provincia)
)
if resultado:
    return resultado  # Cache hit, no API call
```

**Si no hay cache hit**, ejecutar GET a la API con reintentos y timeout:

```
GET https://apis.datos.gob.ar/georef/api/localidades?nombre={localidad}&provincia={provincia}&max=1
```

Extraer de la respuesta:
- `localidad_norm`: `localidades[0].nombre`
- `codgeo_provincia`: `localidades[0].provincia.id` (2 caracteres)
- `codgeo_depto`: `localidades[0].departamento.id` (5 caracteres — clave para join OEDE)
- `lat`: `localidades[0].centroide.lat`
- `lng`: `localidades[0].centroide.lon`

**Fallback en cascada:**
1. Si la localidad exacta no matchea → consultar `/departamentos` para obtener al menos `codgeo_depto` y coordenadas aproximadas.
2. Si el departamento tampoco matchea → consultar `/provincias` para obtener al menos `codgeo_provincia`.

**Persistir resultado en `georef_cache`** después de cada resolución exitosa.

**Plantas multi-localidad:** Si el LLM detecta que el evento involucra más de una planta (ej: "plantas en Córdoba y Rosario"), registrar la planta principal en `localidad_norm` y las adicionales en `localidades_adicionales` como array de objetos GeoJSON:

```json
[
  {"localidad": "Rosario", "provincia": "Santa Fe", "lat": -32.946, "lng": -60.639}
]
```

### Paso 5: Deduplicación Inteligente

1. **Normalización de nombre:** Quitar puntuación, pasar a minúsculas y remover tipos societarios (`S.A.`, `S.R.L.`, `S.A.I.C.`, `S.C.A.`, etc.) para formar `empresa_normalizada`.

2. **Fuzzy matching con `rapidfuzz`** antes de consultar Supabase:

```python
from rapidfuzz import fuzz

# Obtener candidatos del mismo codgeo_depto en ventana temporal
candidatos = db.get_candidates(codgeo_depto, fecha_evento, delta_dias=45)

for candidato in candidatos:
    ratio = fuzz.token_sort_ratio(empresa_normalizada, candidato.empresa_normalizada)
    if ratio >= 85:
        # Es el mismo evento — actualizar, no insertar
        db.update_event(candidato.id, fuente_url, empleados_afectados)
        return
```

3. **Chequeo en Supabase** solo si no hay match por fuzzy:
   - `empresa_normalizada` coincide exactamente
   - Mismo `codgeo_depto` o misma provincia
   - `fecha_evento` dentro de ±45 días

4. **Persistencia:**
   - **Existe (fuzzy o exacto):** Actualizar sumando URL a `fuentes_adicionales`, refrescar `updated_at`, actualizar `empleados_afectados` si la nueva fuente tiene dato más certero (y menor `confidence_score` de estimación).
   - **No existe:** Insertar nuevo registro en `factory_events`.

### Paso 6: Notificaciones vía Hermes (polling a Supabase)

El pipeline no necesita alcanzar ningún endpoint externo. En cambio, **Hermes Agent** — corriendo en la computadora personal con Signal — consulta periódicamente las tablas `pipeline_runs` y `factory_events` en Supabase y genera los mensajes de alerta directamente en Signal.

**Configurar en Hermes** un cron job con la frecuencia deseada (ej: cada hora) que ejecute la siguiente lógica:

```python
# Pseudocódigo del cron job de Hermes
import psycopg2
from datetime import datetime, timedelta

def check_radar_updates():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # 1. Último run del pipeline
    cur.execute("""
        SELECT ejecutado_at, eventos_insertados, eventos_actualizados,
               errores_scraping + errores_llm + errores_georef AS errores_totales
        FROM pipeline_runs
        ORDER BY ejecutado_at DESC
        LIMIT 1
    """)
    run = cur.fetchone()

    if run and run[0] > datetime.now(tz=UTC) - timedelta(hours=7):
        # Hay un run reciente — enviar resumen
        send_signal_message(
            f"🏭 Radar Industrial AR — Run completado\n"
            f"📅 {run[0].strftime('%d/%m/%Y %H:%M')}\n"
            f"✅ Eventos nuevos: {run[1]}\n"
            f"♻️  Eventos actualizados: {run[2]}\n"
            f"⚠️  Errores: {run[3]}"
        )

    # 2. Eventos críticos recientes (> ALERT_THRESHOLD trabajadores)
    cur.execute("""
        SELECT empresa, localidad_norm, provincia,
               empleados_afectados, empleados_afectados_es_estimacion,
               tipo_evento, estado_evento, fuente_url
        FROM factory_events
        WHERE created_at > NOW() - INTERVAL '7 hours'
          AND empleados_afectados >= %s
        ORDER BY empleados_afectados DESC
    """, (ALERT_THRESHOLD,))

    for evento in cur.fetchall():
        empresa, localidad, provincia, afectados, es_estimacion, tipo, estado, url = evento
        send_signal_message(
            f"🚨 ALERTA — Evento crítico\n"
            f"🏢 {empresa}\n"
            f"📍 {localidad}, {provincia}\n"
            f"👷 Afectados: {afectados}{'~' if es_estimacion else ''}\n"
            f"📋 {tipo} ({estado})\n"
            f"🔗 {url}"
        )
```

**La variable `ALERT_THRESHOLD`** (umbral de trabajadores para alerta inmediata) se configura localmente en Hermes, no en el pipeline.

---

## 5. Integración con OEDE (Observatorio de Empleo y Dinámica Empresarial)

Módulo `src/oede.py` para mantener actualizados los datos de empleo registrado por departamento (base para calcular impacto relativo):

1. **Descarga de microdatos** desde el portal de datos abiertos del MTEySS (`datos.gob.ar`).
2. **Transformación:** Agregar empleo registrado por `codgeo_depto` y por `clae2` (sección de manufactura).
3. **Carga en `oede_empleo_depto`:** Upsert por `codgeo_depto`, actualizando el campo `periodo`.
4. **Cron separado:** Este módulo corre en un workflow de GH Actions diferente, mensual o trimestral (según la frecuencia de actualización del MTEySS).

**Join de análisis de impacto relativo:**

```sql
SELECT
    fe.empresa,
    fe.localidad_norm,
    fe.provincia,
    fe.empleados_afectados,
    oe.empleo_registrado_manufactura,
    ROUND(
        fe.empleados_afectados::DECIMAL / NULLIF(oe.empleo_registrado_manufactura, 0) * 100,
        2
    ) AS impacto_pct_manufactura
FROM factory_events fe
LEFT JOIN oede_empleo_depto oe ON fe.codgeo_depto = oe.codgeo_depto
WHERE fe.clae2 BETWEEN '10' AND '33'
ORDER BY impacto_pct_manufactura DESC NULLS LAST;
```

---

## 6. Estructura del Repositorio

```plaintext
radar-industrial-ar/
├── .github/
│   └── workflows/
│       ├── etl_cron.yml          # Pipeline principal (cron cada 6-12hs + workflow_dispatch)
│       ├── oede_sync.yml         # Sincronización mensual de datos OEDE
│       └── keepalive.yml         # Commit vacío semanal para evitar suspensión del cron
├── src/
│   ├── __init__.py
│   ├── config.py                 # Configuración, queries booleanas, constantes (ALERT_THRESHOLD, etc.)
│   ├── database.py               # Operaciones Supabase/PostgreSQL, deduplicación, pipeline_runs
│   ├── scraper.py                # Google News RSS + scrapers de fuentes sindicales/provinciales
│   ├── extractor.py              # Gemini API con Structured Outputs (CLAE2 + few-shot examples)
│   ├── georef.py                 # Cliente Georef-ar API con cache, reintentos y fallback en cascada
│   ├── deduplicator.py           # Fuzzy matching con rapidfuzz + lógica de merge/update
│   ├── notifications.py          # (vacío / stub) — las notificaciones las maneja Hermes desde su lado
│   ├── oede.py                   # Descarga y carga de microdatos MTEySS
│   └── pipeline.py               # Orquestador principal del flujo ETL
├── data/
│   └── georef_cache.json         # Cache local de respaldo (en caso de Supabase no disponible)
├── requirements.txt
├── .env.example
└── main.py
```

---

## 7. Variables de Entorno (`.env`)

```bash
# APIs externas
GEMINI_API_KEY="tu_api_key_de_google_ai_studio"
USER_AGENT="RadarIndustrialAR/1.0"

# Base de datos
DATABASE_URL="postgresql://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres"
```

> Las variables de notificación (`ALERT_THRESHOLD`, número de Signal, etc.) se configuran localmente en Hermes, no en el pipeline ni en los secrets de GitHub.

---

## 8. Configuración del Cron Job de Hermes (notificaciones)

El pipeline no tiene lógica de notificación propia. Todo corre del lado de Hermes. Configurar en Hermes Agent un cron job que se ejecute cada hora con acceso a `DATABASE_URL` de Supabase.

**Tarea del cron job:**

1. Consultar `pipeline_runs` buscando runs ejecutados en las últimas 7 horas.
2. Si existe un run reciente, armar y enviar el resumen de actividad en Signal.
3. Consultar `factory_events` buscando eventos insertados en las últimas 7 horas con `empleados_afectados >= ALERT_THRESHOLD`.
4. Para cada evento crítico encontrado, enviar una alerta individual en Signal.

**Formatos de mensajes:**

Resumen de run:
```
🏭 Radar Industrial AR — Run completado
📅 {fecha_hora}
✅ Eventos nuevos: {n}
♻️  Eventos actualizados: {n}
⚠️  Errores: {n}
```

Alerta de evento crítico:
```
🚨 ALERTA — Evento crítico
🏢 {empresa}
📍 {localidad_norm}, {provincia}
👷 Afectados: {empleados_afectados}[~]
📋 {tipo_evento} ({estado_evento})
🔗 {fuente_url}
```

> El `[~]` se agrega si `empleados_afectados_es_estimacion = TRUE`.

---

## 9. Workflow de GitHub Actions (`etl_cron.yml`)

```yaml
name: ETL Radar Industrial AR

on:
  schedule:
    - cron: '0 */6 * * *'    # Cada 6 horas
  workflow_dispatch:           # Ejecución manual para evitar suspensión por inactividad

jobs:
  etl:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Configurar Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Instalar dependencias
        run: pip install -r requirements.txt

      - name: Ejecutar pipeline ETL
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          USER_AGENT: "RadarIndustrialAR/1.0"
        run: python main.py
```

---

## 10. Instrucciones de Implementación

Al ejecutar este proyecto:

1. **`src/scraper.py`:** Implementar Google News RSS con validación de URL antes de parsear. Agregar scrapers directos para APL, Infogremiales y los portales provinciales listados.

2. **`src/extractor.py`:** Configurar el JSON Schema completo con todos los campos nuevos. Incluir los few-shot examples de `clae2` en el system prompt. Usar `gemini-2.5-flash` con `response_mime_type: "application/json"`. Persistir el nombre del modelo en `modelo_llm`.

3. **`src/georef.py`:** Implementar el chequeo de cache (`georef_cache`) antes de cada llamada HTTP. Configurar reintentos con `tenacity` (3 intentos, backoff exponencial, timeout 5s). Implementar fallback en cascada: `/localidades` → `/departamentos` → `/provincias`.

4. **`src/deduplicator.py`:** Usar `rapidfuzz.fuzz.token_sort_ratio` para fuzzy matching de `empresa_normalizada` con umbral 85. Aplicar fuzzy antes de la consulta exacta a Supabase.

5. **`src/database.py`:** Insertar en `factory_events` sin pasar el campo `location` (el trigger de PostgreSQL lo genera automáticamente desde `lat` y `lng`). Registrar métricas de cada run en `pipeline_runs`. Implementar upsert en `georef_cache`.

6. **`src/notifications.py`:** No requiere implementación en el pipeline. Las notificaciones las maneja Hermes desde su lado consultando `pipeline_runs` y `factory_events` directamente en Supabase. El archivo puede dejarse como stub vacío o eliminarse del repo.

7. **`src/oede.py`:** Descargar microdatos del MTEySS desde `datos.gob.ar`. Agregar por `codgeo_depto` y `clae2`. Hacer upsert en `oede_empleo_depto`. Configurar en workflow separado `oede_sync.yml` con cron mensual.

8. **`.github/workflows/keepalive.yml`:** Workflow semanal con `workflow_dispatch` que hace un commit vacío o un `git commit --allow-empty` para mantener el repo activo y evitar que GH Actions suspenda el cron principal.

9. **Secrets de repositorio a configurar:** `GEMINI_API_KEY`, `DATABASE_URL`. Son los únicos dos que necesita el pipeline. El resto (`ALERT_THRESHOLD`, credenciales de Signal) se configuran localmente en Hermes.
