---
name: frontend-stack
description: >
  Consultar siempre que la tarea involucre el frontend del proyecto:
  componentes de Astro, componentes de Svelte 5, interactividad con Alpine.js,
  estilos con TailwindCSS, componentes base de Flowbite, rutas, layouts,
  o integración del frontend con la API de Strapi. Contiene las convenciones
  y patrones específicos del proyecto Izquierda Nacional, incluyendo el flujo
  de trabajo con Flowbite, errores conocidos y decisiones de arquitectura
  de componentes. Para el diseño visual y el tema, ver el skill diseno-estilos.
---

# Skill: Frontend Stack — Mapa

## Stack y versiones

| Tecnología | Versión | Propósito |
|---|---|---|
| Astro | v6 | Framework principal, SSG + routing |
| Svelte | 5 | Componentes reactivos complejos |
| Alpine.js | 3.15.12 | Interactividad simple |
| TailwindCSS | 4.3 | Estilos utility-first |
| Flowbite | 4 | Biblioteca de componentes base (scaffold) |

**Hosting**: Cloudflare Pages  
**Output mode**: SSG por defecto, hybrid cuando sea necesario

---

## Árbol de decisión: ¿qué tecnología usar?

```
¿El elemento necesita reactividad o estado?
├── NO → ¿Es markup simple repetido?
│         ├── SÍ → Componente .astro
│         └── NO → HTML inline en el .astro padre
└── SÍ → ¿Es interactividad simple (toggle, dropdown)?
          ├── SÍ → Alpine.js (x-data, x-show, etc.)
          └── NO → ¿Necesita acceso al DOM o dibujar SVG?
                    ├── SÍ → Svelte 5 con client:load
                    └── NO → Svelte 5 con client:visible (lazy)
```

### Cuándo usar cada uno en detalle

**Astro `.astro`**
- Layouts, páginas, wrappers
- Componentes estáticos (cards, headers, footers)
- Fetch de datos en build time (`Astro.glob`, `fetch` en frontmatter)
- Elementos repetidos simples (ej: lista de publicaciones)

**Svelte 5**
- Timeline interactivo
- Buscador con resultados dinámicos
- Cualquier componente con `$state`, `$derived`, `$effect`
- Componentes que dibujan SVG en base a datos (requieren DOM → `client:load`)
- Reciben datos de Astro como props, los procesan reactivamente

**Alpine.js**
- Menú mobile (open/close)
- Accordions, tabs simples
- Formularios de filtro sin lógica compleja
- Casos donde las runas de Svelte 5 generaron problemas

---

## Patrones de Svelte 5 en este proyecto

### Recibir datos del servidor como props

El patrón correcto es fetchear en Astro y pasar como props al componente Svelte:

```astro
---
// src/pages/timeline.astro
import Timeline from '../components/Timeline.svelte';
const { data: periodos } = await fetch(`${STRAPI_URL}/api/periodos...`).then(r => r.json());
---
<Timeline periodos={periodos} client:load />
```

```svelte
<!-- src/components/Timeline.svelte -->
<script>
  let { periodos } = $props();  // Svelte 5: $props() en lugar de export let
  
  let periodoActivo = $state(null);
  let alturaLinea = $derived(calcularAltura(periodos));
</script>
```

### Runas de Svelte 5 — referencia rápida

| Svelte 4 | Svelte 5 | Uso |
|---|---|---|
| `export let prop` | `let { prop } = $props()` | Recibir props |
| `let variable = x` (reactivo) | `let variable = $state(x)` | Estado reactivo |
| `$: derivado = ...` | `let derivado = $derived(...)` | Valor derivado |
| `$: { efecto }` | `$effect(() => { ... })` | Efecto secundario |
| `<svelte:component>` | Renderizado directo | Componentes dinámicos |

> ⚠️ **Problema conocido con runas**: algunas funcionalidades tienen
> implementaciones en Alpine.js debido a problemas con las runas de Svelte 5.
> Al agregar funcionalidad nueva, verificar si hay precedente en Alpine.js
> antes de optar por Svelte.

---

## Patrones de Astro en este proyecto

### Estructura de directorios

```
src/
├── components/
│   └──  ui/             ← Componentes Astro genéricos (Button, Card, etc.)
├── layouts/
│   └── BaseLayout.astro
├── pages/
│   ├── index.astro
│   ├── articulos/
│   │   ├── index.astro
│   │   └── [slug].astro
│   └── api/            ← Endpoints SSR (webhooks, etc.)
├── lib/
│   ├── strapi.ts       ← Cliente Strapi
│   └── utils.ts
└── styles/
    └── global.css
```

### Fetch de datos en tiempo de build

```astro
---
// src/pages/articulos/[slug].astro
export async function getStaticPaths() {
  const { data } = await fetchStrapi('publicaciones', 
    new URLSearchParams({ 'fields[0]': 'slug', 'pagination[pageSize]': '100' })
  );
  
  return data.map((pub: any) => ({
    params: { slug: pub.slug },
    props: { publicacion: pub }
  }));
}

const { publicacion } = Astro.props;
---
```

### SSG vs Hybrid: criterio del proyecto

**SSG** (output: 'static'):
- Páginas del archivo histórico
- Listados de publicaciones
- Timeline de períodos históricos
- Todo el contenido que no cambia entre visitas

**Hybrid / SSR** (output: 'hybrid' con `export const prerender = false`):
- Resultados de búsqueda semántica (RAG)
- Endpoint receptor de webhooks
- Funcionalidades de usuario (si se agregan)

---

## Flowbite: rol y flujo de trabajo

Flowbite se usa como **biblioteca de scaffold**, no como sistema de diseño final. 
El flujo es:

```
Flowbite (HTML + clases Tailwind base)
  → copiar el componente
  → adaptar estructura HTML si es necesario  
  → reemplazar clases de color/tipografía por las del proyecto
  → ajustar spacing y bordes al estilo del sitio
```

Flowbite provee la estructura funcional (markup semántico, accesibilidad básica,
estados hover/focus/active). El estilo visual final siempre viene del tema del
proyecto (ver skill `diseno-estilos`).

### Instalación

En Tailwind v4 no hay `tailwind.config.mjs`. Flowbite se integra
directamente en el CSS principal con directivas:

```css
/* src/styles/global.css */
@import "tailwindcss";

/* Plugin de Flowbite (variantes, utilidades extra) */
@plugin "flowbite/plugin";

/* Decirle a Tailwind que escanee los componentes de Flowbite
   para incluir sus clases en el build                        */
@source "../node_modules/flowbite";
```

El JS de Flowbite, para componentes interactivos (dropdowns, modals):

```astro
<!-- src/layouts/BaseLayout.astro — antes del </body> -->
<script src="https://cdn.jsdelivr.net/npm/flowbite@latest/dist/flowbite.min.js"></script>
```

> ⚠️ Si el componente Flowbite usa JS propio (dropdown, modal, tooltip),
> verificar que no entre en conflicto con Alpine.js. En general, si ya usamos
> Alpine.js para manejar el estado, NO importar el JS de Flowbite para ese
> componente — usar solo el HTML/CSS de Flowbite y manejar la lógica con Alpine.

### Componentes Flowbite más usados en el proyecto

> Completar con los componentes que efectivamente se usan.

| Componente | URL de referencia | Observaciones de adaptación |
|---|---|---|
| Navbar | https://flowbite.com/docs/components/navbar/ | [completar] |
| Cards | https://flowbite.com/docs/components/card/ | [completar] |
| Breadcrumb | https://flowbite.com/docs/components/breadcrumb/ | [completar] |
| Pagination | https://flowbite.com/docs/components/pagination/ | [completar] |
| [agregar] | | |

### Qué NO hacer con Flowbite

- No dejar las clases de color por defecto de Flowbite (`blue-600`, `gray-700`, etc.) en producción — siempre reemplazar por los tokens del proyecto
- No usar los colores de Flowbite como referencia para el diseño — el diseño manda sobre Flowbite, no al revés
- No importar el CSS completo de Flowbite si Tailwind ya genera las clases necesarias

---

## TailwindCSS: problema conocido con valores dinámicos del CMS

### ⚠️ NO usar clases dinámicas desde el CMS

```astro
<!-- ❌ INCORRECTO: Tailwind no incluye estas clases en el build -->
<div class={`bg-${color}-500 text-${color}-900`}>

<!-- ✅ CORRECTO: usar style inline para valores que vienen de Strapi -->
<div style={`background-color: ${color}; color: ${colorTexto};`}>
```

Aplica a cualquier valor de color, tamaño o variante que venga de Strapi
(colores de períodos históricos, categorías de artículos, etc.).

> Para colores y estilos estáticos del proyecto → ver skill `diseno-estilos`.

---

## Variables de entorno del frontend

```bash
# .env (en la raíz del proyecto Astro)
STRAPI_URL=https://[tu-strapi].railway.app
STRAPI_TOKEN=[token de solo lectura]
RAG_SERVICE_URL=https://[tu-app].fly.dev
WEBHOOK_SECRET=[secreto para validar webhooks entrantes]
CF_DEPLOY_HOOK=[URL del deploy hook de Cloudflare Pages]
```

---

## Referencias

- Astro v6 docs: https://docs.astro.build/
- Svelte 5 runes: https://svelte.dev/docs/svelte/$state
- Alpine.js docs: https://alpinejs.dev/
- Flowbite docs: https://flowbite.com/docs/getting-started/introduction/
- TailwindCSS safelist: https://tailwindcss.com/docs/content-configuration#safelisting-classes
- **Diseño y estilos del proyecto** → ver skill `diseno-estilos`
