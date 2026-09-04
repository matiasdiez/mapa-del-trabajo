# Operaciones — Fase 1: Ingesta OEDE

Guía paso a paso para configurar el entorno, inicializar las bases de datos
y ejecutar la ingesta de datos del OEDE.

---

## Índice

1. [Requisitos previos](#1-requisitos-previos)
2. [Configuración del entorno Python](#2-configuración-del-entorno-python)
3. [Variables de entorno](#3-variables-de-entorno)
4. [Arquitectura de datos](#4-arquitectura-de-datos)
5. [Aplicar el schema en Neon](#5-aplicar-el-schema-en-neon)
6. [Flujo de ingesta OEDE](#6-flujo-de-ingesta-oede)
7. [Verificar la ingesta](#7-verificar-la-ingesta)
8. [Resolución de problemas](#8-resolución-de-problemas)

---

## 1. Requisitos previos

| Herramienta | Versión mínima | Verificar |
|-------------|---------------|-----------|
| Python      | 3.11          | `python --version` |
| pip         | 23+           | `pip --version` |
| Cuenta Neon | —             | [neon.tech](https://neon.tech) |

El pipeline **no** requiere Docker, PostgreSQL local ni Tippecanoe en esta fase.

---

## 2. Configuración del entorno Python

```bash
# Desde el directorio mapa/
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
# .venv\Scripts\activate         # Windows

pip install -r pipeline/requirements.txt
```

Dependencias instaladas:

| Paquete | Uso |
|---------|-----|
| `psycopg2-binary` | Driver PostgreSQL para conectar a Neon |
| `duckdb` | Base analítica local (oede_empleo) |
| `pandas` | Lectura y transformación de CSVs |
| `click` | Interfaz de línea de comandos |
| `rich` | Output formateado con colores |
| `python-dotenv` | Carga de variables desde `.env` |
| `httpx` | Requests HTTP (Georef AR, Fase 2) |
| `geopandas` | Lectura de shapefiles (Fase 2) |
| `scipy` | KDE ponderado (Fase 3) |
| `boto3` | Upload a Cloudflare R2 (Fase 3) |

Verificar que el CLI funciona:

```bash
python -m pipeline --help
```

---

## 3. Variables de entorno

### 3.1 Crear el archivo `.env`

```bash
cp .env.example .env
```

Editar `.env` con los valores reales:

```env
# Neon — connection string completo desde el dashboard
DATABASE_URL=postgresql://user:password@ep-xxx.us-east-2.aws.neon.tech/dbname?sslmode=require

# DuckDB — ruta al archivo local (relativa a mapa/)
# No necesita credenciales. El archivo se crea automáticamente.
DUCKDB_PATH=data/analytics.db
```

> **⚠ Importante:** Obtener el `DATABASE_URL` desde el **Neon dashboard** →
> proyecto → pestaña **"Connection string"**. Asegurarse de incluir `?sslmode=require`
> al final. Esta cadena incluye usuario y contraseña y **nunca debe commitearse**.

### 3.2 Variables opcionales para Fase 1

Las variables de R2 y Georef no son necesarias para la ingesta OEDE.
Pueden dejarse vacías o comentadas en esta fase.

---

## 4. Arquitectura de datos

El pipeline usa una arquitectura **híbrida** con dos bases de datos:

| Base de datos | Tecnología | Qué almacena |
|---------------|-----------|--------------|
| **Operacional** | Neon (PostgreSQL serverless) | `factory_events`, `geo_departamentos`, `event_weights`, `pipeline_runs` |
| **Analítica** | DuckDB (archivo local `data/analytics.db`) | `oede_empleo` (todos los sectores) |

### ¿Por qué DuckDB para OEDE?

Neon tiene un límite de **512 MB** en el tier gratuito. El OEDE completo
(~3.5M filas, todos los sectores, desde 2014) supera ese límite con índices.

DuckDB no tiene límite de almacenamiento, corre localmente como un archivo,
y es muy eficiente para queries analíticas sobre millones de filas.

### Regla simple

- **¿Dato operacional o geometría?** → Neon
- **¿CSV o XLS grande (OEDE)?** → DuckDB
- **¿Tiles para el frontend?** → Cloudflare R2

### GitHub Actions

CI solo necesita `DATABASE_URL` (Neon) y credenciales R2.
`DUCKDB_PATH` no se usa en CI: los pesos ya están pre-calculados
y guardados en Neon (`event_weights`).

---

## 5. Aplicar el schema en Neon

El archivo `pipeline/db/migrations/001_initial.sql` crea las tablas
operacionales. **No incluye `oede_empleo`** — esa tabla vive en DuckDB.

### Tablas que crea en Neon

| Tabla | Descripción |
|-------|-------------|
| `factory_events` | Eventos de cierre documentados |
| `geo_departamentos` | Geometría de departamentos (INDEC) |
| `event_weights` | Pesos calculados por evento (Fase 2+) |
| `pipeline_runs` | Audit log de cada ingesta (Neon y DuckDB) |

### Pasos

**Opción A — SQL Editor de Neon (más simple):**

1. Ir a [console.neon.tech](https://console.neon.tech) → seleccionar el proyecto
2. En el menú lateral, ir a **SQL Editor**
3. Abrir `pipeline/db/migrations/001_initial.sql` y pegar el contenido completo
4. Ejecutar con **Run**

**Opción B — psql desde la terminal:**

```bash
psql "$DATABASE_URL" -f pipeline/db/migrations/001_initial.sql
```

### Verificar que las tablas existen

En el SQL Editor de Neon o vía psql:

```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;
```

Deben aparecer: `event_weights`, `factory_events`, `geo_departamentos`, `pipeline_runs`.

### DuckDB — schema automático

El schema de DuckDB (`oede_empleo` + vistas) se crea automáticamente
la primera vez que se ejecuta `ingest`. No hay ningún paso manual.

---

## 6. Flujo de ingesta OEDE

### 6.1 Descargar el archivo CSV

El archivo debe descargarse **manualmente** desde una de estas fuentes:

- **Fuente recomendada:** [datos.produccion.gob.ar](https://datos.produccion.gob.ar) → buscar **"Puestos de trabajo por departamento/partido y sector"** → descargar `puestos_depto_priv_por_clae2.csv`
- **Fuente alternativa:** [argentina.gob.ar/trabajo/estadisticas/oede-estadisticas-provinciales](https://argentina.gob.ar/trabajo/estadisticas/oede-estadisticas-provinciales)

El archivo de `datos.produccion.gob.ar` tiene columnas:
```
fecha,codigo_departamento_indec,id_provincia_indec,clae2,puestos
```

### 6.2 Verificar el formato del CSV

Columnas requeridas (el loader acepta que `letra` no esté presente):

```
codigo_departamento_indec, clae2, fecha, puestos
```

El loader acepta estos formatos de fecha:

| Formato | Ejemplo | Se normaliza a |
|---------|---------|----------------|
| `YYYYMM` | `202401` | `2024-01-01` |
| `YYYY-MM` | `2024-01` | `2024-01-01` |
| `YYYY-MM-DD` | `2024-01-15` | `2024-01-01` |

> **Nota sobre clae2=999:** El OEDE incluye filas de totales agregados con
> `clae2=999`. El loader las descarta automáticamente — no son códigos CLAE2
> reales (el rango válido es 01-97).

### 6.3 Depositar el archivo

```bash
cp ~/Descargas/puestos_depto_priv_por_clae2.csv data/incoming/oede/
```

### 6.4 Validar antes de ingestar (dry-run)

Siempre validar primero. Este paso **no escribe nada** en ninguna base de datos:

```bash
python -m pipeline validate --source oede --file data/incoming/oede/puestos_depto_priv_por_clae2.csv
```

Salida esperada:

```
OEDE Loader (dry-run)
  Archivo: data/incoming/oede/puestos_depto_priv_por_clae2.csv
  Calculando SHA256... 55394dbd93ac…
  Leyendo CSV... 3,592,707 filas brutas
  Normalizando campos...
  ⚠ 41,533 filas con código clae2 inválido (se omitirán): ['999']
  Columna 'letra' no encontrada
  Filas a insertar: 3,551,174 (84 sectores CLAE2 distintos)
╭──────────────────────────── 🔍 OEDE procesado ─────────────────────────────╮
│   Modo              DRY-RUN (sin escritura)                                 │
│   Filas a insertar  3,551,174                                               │
│   Período           2014-01-01 → 2023-11-01                                │
│   Departamentos     506                                                     │
╰────────────────────────────────────────────────────────────────────────────╯
✓ Validación exitosa. Archivo listo para ingestar.
```

### 6.5 Ingestar

```bash
python -m pipeline ingest --source oede --file data/incoming/oede/puestos_depto_priv_por_clae2.csv
```

El loader ejecuta estos pasos:

1. **SHA256** — verifica si el archivo ya fue procesado (evita duplicados)
2. **Validación** — columnas requeridas presentes
3. **Normalización** — codgeo_depto a 5 chars, fecha a DATE, clae2 a 2 chars
4. **Filtro clae2** — descarta filas con códigos inválidos (ej: `999`)
5. **COPY a DuckDB** — carga masiva vía buffer en memoria (~5-15 minutos para 3.5M filas)
6. **Registro** — anota el run en `pipeline_runs` (Neon) con SHA256 y estadísticas
7. **Archivo** — mueve el CSV a `data/processed/oede/` con timestamp
8. **Resumen** — imprime resultado

> **Tiempo esperado:** el COPY a DuckDB es mucho más rápido que inserts fila
> por fila. Para 3.5M filas se espera entre 5 y 15 minutos dependiendo del
> hardware local. El progreso se imprime cada 100.000 filas.

### 6.6 Re-ejecutar el mismo archivo

Si se intenta ingestar un archivo ya procesado, el loader lo detecta por SHA256:

```
⚠ Ya procesado: puestos_depto_priv_por_clae2.csv (2024-09-02). Saliendo sin error.
```

Para forzar una re-ingesta (por ejemplo si cambió el archivo):

```sql
-- Correr en Neon SQL Editor
DELETE FROM pipeline_runs
WHERE source = 'oede'
  AND filename = 'puestos_depto_priv_por_clae2.csv';
```

Luego volver a ejecutar `ingest`.

---

## 7. Verificar la ingesta

### 7.1 Audit log en Neon

```sql
SELECT
  source,
  destination,
  filename,
  LEFT(file_sha256, 12) AS sha256_prefix,
  records_inserted,
  status,
  ran_at
FROM pipeline_runs
ORDER BY ran_at DESC
LIMIT 10;
```

### 7.2 Verificar datos en DuckDB

Abrir una sesión de Python o usar el CLI de DuckDB:

```bash
python -c "
import duckdb
conn = duckdb.connect('data/analytics.db')

print('=== Total registros ===')
print(conn.execute('SELECT COUNT(*) FROM oede_empleo').fetchone())

print('=== Por período (últimos 6) ===')
print(conn.execute('''
    SELECT periodo, COUNT(*) AS filas, SUM(puestos) AS puestos_total
    FROM oede_empleo
    GROUP BY periodo
    ORDER BY periodo DESC
    LIMIT 6
''').df())

conn.close()
"
```

### 7.3 Verificar el archivo archivado

```bash
ls -lh data/processed/oede/
```

El archivo original fue movido con timestamp. El directorio `data/incoming/oede/`
debe quedar vacío (solo el `.gitkeep`).

---

## 8. Resolución de problemas

### Error: `DATABASE_URL` no definida

```
ValueError: La variable de entorno DATABASE_URL no está definida.
```

Verificar que `.env` existe y tiene el connection string correcto:

```bash
cat .env | grep DATABASE_URL
```

---

### Error: columnas requeridas faltantes

```
✗ Error de validación: Columnas requeridas faltantes en archivo.csv:
  Esperadas  : ['clae2', 'codigo_departamento_indec', ...]
  Encontradas: ['dept_code', 'sector', ...]
```

El CSV tiene nombres de columnas distintos. Renombrar con `sed` o en Excel:

```bash
sed -i '1s/dept_code/codigo_departamento_indec/' data/incoming/oede/archivo.csv
```

---

### Error: `value too long for type character(2)` (clae2)

```
psycopg2.errors.StringDataRightTruncation: value too long for type character(2)
CONTEXT: COPY _oede_staging, line 85, column clae2: "999"
```

El CSV tiene filas de totales agregados con `clae2=999`. El loader ya filtra
estos códigos automáticamente. Si ves este error, verificar que estás usando
la versión actualizada del loader.

---

### Error: conexión a Neon

```
psycopg2.OperationalError: connection to server ... failed
```

1. Verificar que `DATABASE_URL` en `.env` es correcto y completo
2. Incluye `?sslmode=require` al final
3. El proyecto de Neon está activo (no suspendido por inactividad)

Probar conexión directamente:

```bash
psql "$DATABASE_URL" -c "SELECT version();"
```

---

### Error: storage lleno en Neon

```
psycopg2.errors.DiskFull: could not extend file because project size limit (512 MB) has been exceeded
```

El plan gratuito de Neon tiene 512 MB de límite. **Los datos OEDE van en DuckDB**,
no en Neon, precisamente por este motivo. Si ves este error durante la ingesta
OEDE, verificar que el loader está apuntando a DuckDB y no a Neon.

---

### El validate funciona pero el ingest falla

El comando `validate` corre en dry-run sin conectarse a ninguna base de datos.
Si `ingest` falla, el problema es de conectividad (Neon) o de permisos en el
archivo `data/analytics.db` (DuckDB).

---

## Referencia rápida de comandos

```bash
# Activar entorno virtual
source .venv/bin/activate

# Ver ayuda del CLI
python -m pipeline --help
python -m pipeline ingest --help
python -m pipeline validate --help

# Validar un archivo (sin escritura, sin credenciales)
python -m pipeline validate --source oede --file data/incoming/oede/<archivo>.csv

# Ingestar un archivo → escribe en DuckDB, audit log en Neon
python -m pipeline ingest --source oede --file data/incoming/oede/<archivo>.csv

# Ver últimas ingestas (Neon)
psql "$DATABASE_URL" -c "SELECT source, destination, filename, status, ran_at FROM pipeline_runs ORDER BY ran_at DESC LIMIT 10;"

# Consultar datos en DuckDB directamente
python -c "import duckdb; conn = duckdb.connect('data/analytics.db'); print(conn.execute('SELECT COUNT(*) FROM oede_empleo').fetchone())"
```
