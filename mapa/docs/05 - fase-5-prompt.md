# Fase 5 — Frontend: mapa base + slider temporal

## Contexto de lo construido en fases anteriores

El pipeline Python genera tres PMTiles en Cloudflare R2:
- `kde.pmtiles` — superficie KDE de intensidad de impacto, con atributo `periodo` (ej: "2022-Q1")
- `eventos.pmtiles` — puntos de eventos de cierre con sus atributos
- `departamentos.pmtiles` — polígonos de departamentos argentinos

Las URLs de R2 son públicas y estables.

## Objetivo de esta fase

Construir el frontend completo: mapa base, superficie KDE, slider temporal,
capa de eventos y panel de detalle. Todo en Astro + Svelte + MapLibre GL JS.

---

## Setup inicial

```bash
npm create astro@latest mapa-industrial-frontend -- --template minimal --typescript strict
cd mapa-industrial-frontend
npx astro add svelte
npm install maplibre-gl pmtiles
```

Archivo de configuración de tiles (`src/lib/tilesConfig.ts`):

```typescript
export const TILES = {
  base: "https://demotiles.maplibre.org/style.json",  // estilo base gratuito
  kde: "https://pub-xxx.r2.dev/kde.pmtiles",
  eventos: "https://pub-xxx.r2.dev/eventos.pmtiles",
  departamentos: "https://pub-xxx.r2.dev/departamentos.pmtiles",
} as const;

// Períodos disponibles en formato "YYYY-QN"
// En producción, generarlos dinámicamente desde los tiles
export const PERIODOS = [
  "2014-Q1", "2014-Q2", "2014-Q3", "2014-Q4",
  // ... hasta el período más reciente disponible
];
```

---

## Componente Map (`src/components/Map.svelte`)

### Inicialización

```javascript
import maplibregl from 'maplibre-gl';
import { Protocol } from 'pmtiles';

// Registrar protocolo PMTiles antes de crear el mapa
const protocol = new Protocol();
maplibregl.addProtocol("pmtiles", protocol.tile.bind(protocol));

const map = new maplibregl.Map({
  container: mapContainer,
  style: TILES.base,
  center: [-63.5, -37.5],   // centro de Argentina
  zoom: 4,
  minZoom: 3,
  maxZoom: 14,
  maxBounds: [[-80, -60], [-50, -20]],  // limitar a Argentina + entorno
});
```

### Capas a agregar (en orden de z-index, de abajo hacia arriba)

**Capa 1 — Departamentos (base):**
```javascript
map.addSource("departamentos", {
  type: "vector",
  url: `pmtiles://${TILES.departamentos}`,
});
map.addLayer({
  id: "departamentos-fill",
  type: "fill",
  source: "departamentos",
  "source-layer": "departamentos",
  paint: {
    "fill-color": "#f5f5f0",
    "fill-opacity": 0.3,
  },
});
map.addLayer({
  id: "departamentos-border",
  type: "line",
  source: "departamentos",
  "source-layer": "departamentos",
  paint: {
    "line-color": "#aaa",
    "line-width": 0.5,
    "line-opacity": 0.6,
  },
});
```

**Capa 2 — Superficie KDE:**
```javascript
map.addSource("kde", {
  type: "vector",
  url: `pmtiles://${TILES.kde}`,
});
map.addLayer({
  id: "kde-fill",
  type: "fill",
  source: "kde",
  "source-layer": "kde",
  filter: ["==", ["get", "periodo"], periodoActivo],  // ← actualizable via setFilter
  paint: {
    "fill-color": [
      "interpolate", ["linear"], ["get", "intensity"],
      0.0,  "rgba(255,255,204,0)",    // transparente
      0.15, "rgba(255,237,160,0.5)",
      0.35, "rgba(254,178,76,0.65)",
      0.55, "rgba(253,141,60,0.75)",
      0.75, "rgba(240,59,32,0.85)",
      1.0,  "rgba(189,0,38,0.95)",
    ],
    "fill-opacity": 1,  // la opacidad ya está en el color
  },
});
```

**Capa 3 — Eventos (burbujas):**
```javascript
map.addSource("eventos", {
  type: "vector",
  url: `pmtiles://${TILES.eventos}`,
});
map.addLayer({
  id: "eventos-circles",
  type: "circle",
  source: "eventos",
  "source-layer": "eventos",
  filter: ["==", ["get", "periodo"], periodoActivo],
  paint: {
    "circle-radius": [
      "interpolate", ["linear"], ["get", "empleados_afectados"],
      0,    4,
      50,   7,
      200,  12,
      1000, 20,
    ],
    "circle-color": "#1a1a2e",
    "circle-opacity": 0.7,
    "circle-stroke-color": "#fff",
    "circle-stroke-width": 1,
  },
});
```

---

## Componente TimeSlider (`src/components/TimeSlider.svelte`)

```svelte
<script lang="ts">
  import { periodoActivo } from '$lib/mapStore';
  import { PERIODOS } from '$lib/tilesConfig';

  let playing = false;
  let intervalId: number;

  function setPeriodo(p: string) {
    $periodoActivo = p;
  }

  function togglePlay() {
    if (playing) {
      clearInterval(intervalId);
      playing = false;
    } else {
      playing = true;
      let idx = PERIODOS.indexOf($periodoActivo);
      intervalId = setInterval(() => {
        idx = (idx + 1) % PERIODOS.length;
        $periodoActivo = PERIODOS[idx];
        if (idx === PERIODOS.length - 1) {
          clearInterval(intervalId);
          playing = false;
        }
      }, 600);  // 600ms por paso = animación legible
    }
  }
</script>

<div class="slider-container">
  <button on:click={togglePlay}>{playing ? '⏸' : '▶'}</button>
  <input
    type="range"
    min="0"
    max={PERIODOS.length - 1}
    value={PERIODOS.indexOf($periodoActivo)}
    on:input={(e) => setPeriodo(PERIODOS[+e.target.value])}
  />
  <span class="periodo-label">{$periodoActivo}</span>
</div>
```

En `Map.svelte`, suscribirse al store y actualizar los filtros de MapLibre:

```javascript
import { periodoActivo } from '$lib/mapStore';

periodoActivo.subscribe((periodo) => {
  if (!map) return;
  map.setFilter("kde-fill", ["==", ["get", "periodo"], periodo]);
  map.setFilter("eventos-circles", ["==", ["get", "periodo"], periodo]);
});
```

---

## Store (`src/lib/mapStore.ts`)

```typescript
import { writable } from 'svelte/store';
import { PERIODOS } from './tilesConfig';

// Período inicial: el más reciente
export const periodoActivo = writable(PERIODOS[PERIODOS.length - 1]);

// Estado de capas visibles
export const layerVisibility = writable({
  kde: true,
  eventos: true,
  departamentos: true,
});
```

---

## Panel de eventos (`src/components/EventPanel.svelte`)

Al hacer click en un evento en el mapa:

```javascript
map.on("click", "eventos-circles", (e) => {
  const props = e.features[0].properties;
  // Emitir evento Svelte con los datos
  dispatch("eventClick", props);
});
```

El panel muestra:
- Nombre de empresa
- Localidad (normalizada)
- Empleados afectados
- Período
- Tipo de evento (cierre / suspensión / reducción)
- Peso de impacto (como barra visual, no como número crudo)
- Ratio de dependencia (como porcentaje: "20% del empleo formal del departamento")
- Link a fuente (si está disponible)

---

## Controles de capas (`src/components/LayerControls.svelte`)

Toggle para cada capa con indicador visual del estado.
Cuando una capa se desactiva, usar `map.setLayoutProperty(id, "visibility", "none")`.

---

## Página principal (`src/pages/index.astro`)

```astro
---
// Sin SSR para este componente — el mapa es client-side only
---
<html lang="es">
<head>
  <title>Industria Argentina — Monitor de Cierres</title>
  <link rel="stylesheet" href="https://unpkg.com/maplibre-gl/dist/maplibre-gl.css" />
</head>
<body>
  <Map client:only="svelte" />
</body>
</html>
```

Usar `client:only="svelte"` para MapLibre porque necesita `window` y no puede
ejecutarse en SSR.

---

## Diseño y tipografía

- Mapa ocupa 100% del viewport
- Controles flotantes sobre el mapa con fondo semitransparente (backdrop-filter: blur)
- Slider en la parte inferior, ancho completo
- Panel de evento en la esquina inferior derecha (slide-in al hacer click)
- Tipografía: Inter o IBM Plex Sans (disponibles en Google Fonts, sin necesidad de build step)
- Paleta de colores del mapa: la escala roja-amarilla del KDE contrasta con el mapa base claro

---

## Tests de aceptación

```bash
npm run dev
# → localhost:4321 abre sin errores en consola

# Verificar:
# 1. El mapa carga centrado en Argentina con polígonos de departamentos visibles
# 2. La superficie KDE es visible con gradiente de colores
# 3. Las burbujas de eventos son visibles en el mapa
# 4. El slider cambia el período y la capa KDE se actualiza visualmente
# 5. El botón ▶ anima el slider automáticamente
# 6. Click en una burbuja abre el EventPanel con los datos del evento
# 7. Los toggles de capas ocultan/muestran cada capa correctamente
# 8. En mobile (emular en DevTools): el mapa es usable, el slider es táctil

npm run build
# → build sin errores
# → dist/ generada
```
