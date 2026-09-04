# Roadmap: Mapa Industrial Argentina

## Cómo usar este documento

Cada fase es un prompt independiente para Claude Code.
Al terminar una fase:
1. Correr los tests de aceptación listados
2. Hacer commit
3. Abrir un nuevo contexto en Claude Code
4. Pegar el contenido del archivo `fase-N-prompt.md` correspondiente
5. El prompt de cada fase incluye contexto de lo construido hasta ese punto

No mezclar fases en el mismo contexto de Claude Code.

## Mapa de dependencias

```
Fase 1 (OEDE loader)
    │
    ▼
Fase 2 (loaders completos + CLI) ──── Fase 9 (integración news DB)
    │
    ▼
Fase 3 (cálculo de pesos)
    │
    ▼
Fase 4 (KDE + tiles)
    │
    ├──► Fase 5 (frontend base + mapa)
    │         │
    │         ▼
    │    Fase 6 (slider temporal)
    │         │
    │         ▼
    │    Fase 7 (capa de eventos + tooltips)
    │
    └──► Fase 8 (deployment)
```

---

## Fase 1 — Ingesta OEDE

**Archivo de prompt:** `fase-1-prompt.md` (ya creado)

**Qué construye:**
- `pipeline/loaders/oede.py`
- `pipeline/db/neon.py` con conexión a Neon (psycopg2)
- `pipeline/db/duckdb.py` con conexión a DuckDB local
- `pipeline/db/migrations/001_initial.sql`
- `pipeline/commands/ingest.py` (sólo source=oede)
- `pipeline/__main__.py` con comando `ingest`

**Aceptación:**
```bash
python -m pipeline ingest --source oede --file data/incoming/oede/test.csv
# → imprime resumen con registros insertados
# → archivo movido a data/processed/oede/
# → registro en pipeline_runs con status='success'
# → segunda ejecución con mismo archivo: status='skipped' (hash duplicado)
```

**Estado de la base al terminar:**
- Tablas: `factory_events`, `oede_empleo`, `oede_total_depto` (vista),
  `geo_departamentos`, `event_weights`, `pipeline_runs`
- `oede_empleo` con datos reales de manufactura por departamento

---

## Fase 2 — Loaders completos + CLI

**Archivo de prompt:** `fase-2-prompt.md`

**Qué construye:**
- `pipeline/loaders/indec_geo.py` — shapefile/GeoJSON de departamentos INDEC
- `pipeline/loaders/eventos.py` — CSV de eventos de cierre con geocodificación
- `pipeline/loaders/georef.py` — cliente para API georef-ar
- Completa `pipeline/commands/ingest.py` con sources: `indec-geo`, `eventos`
- `pipeline/commands/validate.py` — dry-run de cualquier fuente
- `pipeline/commands/status.py` — muestra estado del sistema

**Aceptación:**
```bash
# Geometría INDEC
python -m pipeline ingest --source indec-geo --file data/incoming/indec_geo/departamentos.geojson
# → 525 departamentos en geo_departamentos con geometría válida

# Eventos con geocodificación automática
python -m pipeline ingest --source eventos --file data/incoming/eventos/cierres_test.csv
# → factory_events con location, codgeo_depto, localidad_norm completos

# Validar sin escribir
python -m pipeline validate --source oede --file data/incoming/oede/nuevo.csv
# → reporte de columnas, tipos, períodos, registros esperados

# Estado
python -m pipeline status
# → tablas con conteos: N eventos, M departamentos con OEDE, últimas ingestas
```

---

## Fase 3 — Cálculo de pesos

**Archivo de prompt:** `fase-3-prompt.md`

**Qué construye:**
- `pipeline/multipliers.py` — tabla de multiplicadores CLAE2
- `pipeline/compute/weights.py` — lógica de cálculo
- `pipeline/commands/compute_weights.py`
- Tests unitarios para la fórmula de peso

**Lógica central:**
Para cada evento en `factory_events`:
1. Encontrar el período OEDE más cercano anterior a `fecha_evento`
2. Buscar `puestos_total` del departamento en ese período (`oede_total_depto`)
3. Calcular `ratio_dependencia = empleados_afectados / puestos_total`
4. Aplicar multiplicador por `clae2`
5. `peso_final = min(ratio × multiplicador, 1.0)`
6. Insertar/actualizar `event_weights`

**Aceptación:**
```bash
python -m pipeline compute-weights
# → N pesos calculados, M eventos sin datos OEDE (advertencia, no error)
# → evento test con 40 empleados en depto de 200 formales → ratio=0.20
# → con multiplicador 2.1 (textil) → peso_final=0.42
```

---

## Fase 4 — KDE + Tiles

**Archivo de prompt:** `fase-4-prompt.md`

**Qué construye:**
- `pipeline/compute/kde.py` — KDE ponderado → GeoJSON
- `pipeline/tiles/generate.py` — wrapper de Tippecanoe
- `pipeline/tiles/upload.py` — upload a Cloudflare R2
- `pipeline/commands/build_tiles.py`
- Actualiza `pipeline/__main__.py` con `build-tiles` y `rebuild`

**Tilesets generados:**
- `kde-{periodo}.pmtiles` — superficie KDE por período (o un único archivo con atributo período)
- `eventos.pmtiles` — puntos de eventos con todos sus atributos
- `departamentos.pmtiles` — polígonos base de departamentos/provincias

**Aceptación:**
```bash
python -m pipeline build-tiles
# → archivos .pmtiles en /tmp/tiles/
# → upload a R2 exitoso
# → URL pública accesible: https://pub-xxx.r2.dev/eventos.pmtiles

python -m pipeline rebuild
# → compute-weights + build-tiles en secuencia
```

---

## Fase 5 — Frontend: mapa base

**Archivo de prompt:** `fase-5-prompt.md`

**Qué construye:**
- Setup Astro + Svelte
- `frontend/src/components/Map.svelte` — MapLibre GL JS con pmtiles
- Capas iniciales: departamentos (borde fino, sin relleno) + superficie KDE
- Leyenda de colores para el KDE
- Responsive: desktop y mobile

**Aceptación:**
- El mapa carga sin errores en `localhost`
- Se ven los polígonos de departamentos
- Se ve la superficie KDE con escala de colores
- El mapa cubre el país completo con zoom inicial adecuado

---

## Fase 6 — Slider temporal

**Archivo de prompt:** `fase-6-prompt.md`

**Qué construye:**
- `frontend/src/components/TimeSlider.svelte`
- `frontend/src/lib/mapStore.ts` — Svelte store con período activo
- Lógica: el slider actualiza el filtro de MapLibre sobre la capa KDE
- Formato de períodos: trimestral (Q1 2014 → Q4 2024)

**Aceptación:**
- Mover el slider actualiza la capa KDE sin recargar el tileset
- El período actual se muestra como texto sobre el mapa
- Animación auto-play opcional (reproducir la historia)

---

## Fase 7 — Capa de eventos + panel

**Archivo de prompt:** `fase-7-prompt.md`

**Qué construye:**
- Capa de círculos proporcionales sobre el mapa (radio ∝ `empleados_afectados`)
- `frontend/src/components/EventPanel.svelte` — sidebar o tooltip
- Click en punto → muestra: empresa, localidad, empleados, fecha, fuente
- Toggle para mostrar/ocultar la capa de eventos
- `frontend/src/components/LayerControls.svelte`

**Aceptación:**
- Click en burbuja muestra datos del evento
- Radio de la burbuja es visualmente distinguible entre 40 y 400 empleados
- La capa es togglable sin recargar

---

## Fase 8 — Deployment

**Archivo de prompt:** `fase-8-prompt.md`

**Qué construye:**
- Build de Astro para producción
- Configuración de hosting (Cloudflare Pages o similar)
- `docs/operaciones.md` — manual para cargar datos nuevos
- `.github/workflows/build_tiles.yml` — workflow_dispatch para build-tiles en CI

**Aceptación:**
- URL pública funcional
- Manual operativo que un no-programador puede seguir para cargar un CSV nuevo

---

## Fase 9 — Integración con news DB (opcional / paralela a Fase 2+)

**Archivo de prompt:** `fase-9-prompt.md`

**Qué construye:**
- Schema en Strapi v5 para content type `FactoryClosure` con campos de geolocalización
- Lifecycle hook en Strapi: al guardar un registro, llama georef-ar y completa `codgeo_depto`, `lat`, `lng`
- Script de exportación: `scripts/export_events_from_newsdb.py`
  → lee tabla de Strapi desde la base de datos del news DB, exporta CSV en el formato esperado por el loader de Fase 2
- Documentación de cuándo usar export manual vs. cuándo usar el loader directamente

**Aceptación:**
- Crear un registro en Strapi con sólo `empresa` + `localidad` en texto libre
- El hook completa automáticamente `codgeo_depto`, `lat`, `lng`
- Correr `export_events_from_newsdb.py` genera un CSV listo para el loader de Fase 2

---

## Variables de entorno (todas las fases)

```env
# Base de datos — Neon
# Connection string completo desde el dashboard de Neon
# → proyecto → "Connection string" → copiar con ?sslmode=require
DATABASE_URL=postgresql://user:password@ep-xxx.us-east-2.aws.neon.tech/dbname?sslmode=require

# Cloudflare R2
R2_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET_NAME=mapa-industrial-tiles
R2_PUBLIC_URL=https://pub-xxx.r2.dev

# APIs externas
GEOREF_API_BASE=https://apis.datos.gob.ar/georef/api
```

## Arquitectura de bases de datos

El proyecto usa dos bases de datos con roles distintos:

| Base | Tecnología | Qué almacena | Acceso |
|------|-----------|--------------|--------|
| Neon | PostgreSQL + PostGIS | `factory_events`, `geo_departamentos`, `event_weights`, `pipeline_runs` | Local + CI |
| DuckDB | Archivo local `data/analytics.db` | `oede_empleo` y futuros datasets CSV/XLS | Solo local |

**Neon** usa `psycopg2-binary` con `DATABASE_URL`.
Requiere `?sslmode=require` en el connection string de Neon.
Implementado en `pipeline/db/neon.py`.

**DuckDB** es un archivo local, no requiere credenciales.
Se crea automáticamente la primera vez que se corre `ingest --source oede`.
Implementado en `pipeline/db/duckdb.py`.

**GitHub Actions** solo necesita `DATABASE_URL` (Neon) + vars de R2.
DuckDB no se usa en CI: los pesos calculados viven en Neon (`event_weights`).

## Nota sobre la data ya cargada en Neon

Si tenés `oede_empleo` en Neon con datos de manufactura, convive sin problema
con la nueva arquitectura. Una vez que DuckDB tenga todos los sectores y
`compute-weights` corra correctamente, podés liberar espacio en Neon con:
```sql
DROP TABLE oede_empleo CASCADE;  -- también elimina la vista oede_total_depto
```
