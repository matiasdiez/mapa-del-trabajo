# Marco teórico: economía del cierre industrial y representación cartográfica

## Por qué un mapa de cierres necesita teoría económica

Un mapa que cuenta cierres de fábricas por punto geográfico parece sencillo, pero esconde una trampa: **no todos los cierres son iguales**. Una fábrica que cierra en el Gran Buenos Aires y despide 150 trabajadores es un evento en una economía que emplea formalmente a cientos de miles. La misma fábrica en un pueblo de 800 trabajadores formales totales es una catástrofe económica local.

Si el mapa no corrige esa diferencia, miente. Amplifica los lugares que ya tienen muchas fábricas y borra los lugares donde una sola fábrica es toda la economía formal.

Construir los pesos correctos —los números que hacen que el segundo caso brille más en el mapa que el primero— requiere tomar posición sobre tres preguntas teóricas:

1. ¿Cómo se transmite el impacto de un cierre industrial al resto de la economía local?
2. ¿Cómo medimos la dependencia de una comunidad respecto de un establecimiento?
3. ¿Cómo representamos ese impacto en el espacio sin que la geografía Argentina distorsione la imagen?

Las respuestas vienen de tres tradiciones distintas dentro de la economía.

---

## I. Teoría de la Base Económica y sus límites en Argentina

### El modelo original

La Teoría de la Base Económica fue desarrollada sistemáticamente por Homer Hoyt en los años 30 y formalizada por Charles Tiebout en la década del 50. La idea central es una distinción entre dos tipos de empleo en cualquier economía local:

- **Empleo básico** (*basic employment*): produce bienes y servicios que se venden *fuera* de la región. Trae dinero de afuera. En una ciudad industrial clásica, son las fábricas que exportan o venden a otras ciudades.
- **Empleo no básico** (*non-basic employment*): produce para el consumo local. El almacén, la peluquería, el médico, el colectivo. Su existencia depende del ingreso que genera el empleo básico.

El **multiplicador de la base** es la razón entre el empleo total y el empleo básico. Si una ciudad tiene 1.000 trabajadores básicos y 2.000 no básicos, el multiplicador es 3: por cada empleo básico que se pierde, el total local cae en 3.

### El problema: Argentina no exporta su manufactura

Este modelo asume que la industria es el sector "básico" porque exporta. En Argentina, esa premisa falla estructuralmente.

<cite index="3-1">Argentina ha sido históricamente importadora neta de productos industriales, con déficit comercial en manufacturas, especialmente aquellas que no son de origen agroindustrial.</cite> La manufactura argentina —textil, metalmecánica, plásticos, muebles, calzado— produce principalmente para el mercado interno. No trae divisas de afuera: *es* el mercado local.

Esto tiene una consecuencia directa para la teoría: **el multiplicador no opera por el canal exportador sino por dos canales distintos**.

---

## II. El multiplicador keynesiano de consumo

### Cómo opera el primer canal

Cuando una fábrica cierra, sus trabajadores pierden el ingreso. Pero esos trabajadores eran también consumidores locales: compraban en el almacén del barrio, iban a la farmacia, pagaban el transporte, compraban ropa en el comercio del centro. Cuando ese ingreso desaparece, la demanda local se contrae.

Este mecanismo es el **multiplicador keynesiano**, formulado por John Maynard Keynes en *The General Theory* (1936). Funciona a través de la **propensión marginal a consumir localmente** (PMgCL): qué fracción de cada peso de ingreso se gasta dentro de la misma economía local.

Si un trabajador gana $100.000 y gasta $60.000 localmente (PMgCL = 0,6), al perder su trabajo el almacén pierde $60.000 de ventas. El dueño del almacén también reduce su consumo local. El efecto se multiplica.

El multiplicador keynesiano local es:

```
k = 1 / (1 - PMgCL)
```

Con PMgCL = 0,6, el multiplicador es 2,5: cada peso de ingreso perdido en la fábrica termina reduciendo el ingreso total local en 2,5 pesos.

### Por qué el multiplicador varía por sector

La PMgCL no es igual para todos los sectores. Algunos factores determinan su tamaño:

- **Nivel salarial**: salarios más altos tienen mayor propensión a gastar por fuera del municipio (vacaciones, educación privada, bienes importados). Sectores como siderurgia o automotriz tienen salarios más altos → parte del consumo se filtra afuera.
- **Tamaño de la localidad**: en pueblos chicos la PMgCL es alta porque casi todo se gasta localmente por falta de alternativas. En ciudades grandes, el consumo se dispersa más.
- **Integración del sector con comercio local**: trabajadores textiles o de alimentos gastan más en el comercio local de proximidad que trabajadores de industria química o petroquímica.

En el código, esto se traduce en la tabla `MULTIPLICADORES` por CLAE2: el sector automotriz tiene 2,4 porque tiene altos salarios *y* alta integración local (proveedores, servicios técnicos), mientras que tabaco tiene 1,4 porque sus pocos trabajadores tienen patrones de consumo más dispersos.

---

## III. Encadenamientos productivos: el canal de proveedores

### El segundo canal

El segundo mecanismo opera antes de que el trabajador gaste su salario: actúa sobre los **proveedores** de la fábrica.

Este canal proviene del análisis de **insumo-producto** (input-output), desarrollado por Wassily Leontief en los años 40. La idea es que cada sector productivo compra insumos de otros sectores, y esas compras crean dependencia entre ellos.

Cuando una metalúrgica cierra, no sólo despide a sus obreros: deja de comprarle acero al proveedor local, deja de contratar el servicio de limpieza, deja de llamar al taller mecánico que mantenía sus máquinas, deja de consumir energía, deja de pagar el transporte de sus productos. Cada uno de esos proveedores pierde una fuente de ingreso.

Se llaman **encadenamientos hacia atrás** (*backward linkages*): el impacto va hacia los sectores que le vendían insumos a la fábrica que cerró.

### Por qué sectores como metalmecánica tienen multiplicadores más altos

Sectores con alto valor agregado y alta complejidad tecnológica —metalurgia, maquinaria, automotriz— tienen más encadenamientos locales: más tipos distintos de proveedores, más servicios especializados. Cuando cierran, el efecto de arrastre es mayor.

Sectores como alimentos o bebidas tienen alta integración *hacia adelante* (llegan a muchos consumidores) pero menor complejidad de encadenamientos hacia atrás: sus insumos principales (granos, agua) no se compran en el mercado local de servicios.

Esta lógica justifica que en el código la metalurgia (CLAE2 = 24) tenga multiplicador 2,2 y alimentos (CLAE2 = 10) tenga 1,8: el primero destruye más empleo indirecto por cada empleo directo perdido.

---

## IV. Dependencia económica local: el pueblo fábrica

### El concepto

La literatura anglosajona llama *company town* (pueblo empresa) a las localidades donde una única firma o un único sector explica la mayor parte del empleo formal. En Argentina el concepto tiene nombre propio: **pueblo fábrica**.

Los casos históricos son abundantes: Comodoro Rivadavia con YPF, las hilanderías textiles que fundaron pueblos en el interior de Buenos Aires, los ingenios azucareros en Tucumán, los frigoríficos en localidades patagónicas. En todos estos casos, el cierre de la empresa no sólo destruye empleos directos: destruye la razón de existir del pueblo como economía viable.

### El ratio de dependencia

La variable más directa para medir esta situación es el **ratio de dependencia local**:

```
ratio_dependencia = empleados_afectados / total_empleo_formal_departamento
```

Un ratio de 0,20 significa que el 20% del empleo formal del área se pierde con ese cierre. Combinado con el multiplicador, el impacto total estimado sobre el empleo local (directo + indirecto) es:

```
impacto_total ≈ empleados_afectados × multiplicador_sectorial
impacto_relativo = impacto_total / total_empleo_formal_departamento
```

Este `impacto_relativo` es lo que en el código se llama `peso_final`. Es la variable que hace que el mapa muestre correctamente que 40 empleos perdidos en un pueblo de 200 trabajadores formales son más graves que 400 empleos perdidos en una ciudad de 100.000 trabajadores formales.

### El Cociente de Localización (LQ)

Herramienta complementaria que mide la especialización relativa de un sector en un área:

```
LQ = (empleo_sector_i_local / empleo_total_local) 
     ÷ 
     (empleo_sector_i_nacional / empleo_total_nacional)
```

Un LQ > 1 significa que el área está especializada en ese sector por encima de la media nacional. Un LQ de 5 en manufactura textil en una localidad significa que su economía depende estructuralmente de ese sector —y que su pérdida es más difícil de sustituir.

**Limitación importante**: el LQ es inestable en poblaciones pequeñas. Agregar o quitar un solo establecimiento puede cambiar el LQ dramáticamente en municipios con menos de 4.000 a 5.000 trabajadores formales. Por eso en este proyecto el LQ se usa como señal indicativa pero no como variable de ponderación principal —el ratio de dependencia es más robusto para localidades pequeñas.

---

## V. El mapa como representación del impacto relativo

### Por qué no usar un mapa de calor simple

Un mapa de calor que cuenta puntos por celda geográfica tiene el problema de Argentina: el 40% de la producción industrial está en el AMBA. Cualquier visualización de ese tipo va a generar una gran mancha caliente en Buenos Aires y silencio en el resto del país.

El problema es que ese mapa estaría representando **concentración absoluta**, no **impacto relativo**. Ambas cosas son informativas, pero son distintas. Este proyecto quiere mostrar la segunda.

### KDE ponderado: qué mide y qué supone

El **KDE ponderado** (*Weighted Kernel Density Estimation*) es la herramienta cartográfica para representar una distribución espacial continua donde cada punto tiene importancia diferente.

La idea es: cada evento de cierre es un punto en el mapa. Alrededor de ese punto se dibuja una "campana" gaussiana —el kernel. La altura de esa campana en cada celda del mapa depende de cuántos eventos hay cerca *y* de cuánto pesa cada uno (su `peso_final`).

Formalmente, para una celda ubicada en el punto **x** del espacio:

```
KDE(x) = Σᵢ (peso_i / h²) × K((x - xᵢ) / h)
```

Donde `K` es la función kernel (gaussiana), `h` es el **bandwidth** (ancho de banda), y `xᵢ` es la posición del evento `i`.

**Qué supone el bandwidth:** el bandwidth es el radio de influencia espacial que le asignamos a cada cierre. Si h = 50 km, estamos asumiendo que el impacto de un cierre se propaga hasta 50 km de radio en su intensidad plena. Esto es un supuesto teórico que puede discutirse: ¿se mueve la gente a trabajar a 50 km? ¿Los proveedores locales están dentro de 50 km? En un contexto rural argentino ese radio puede ser razonable; en el conurbano puede ser demasiado amplio.

El **bandwidth adaptativo** es una extensión que usa radios distintos según la densidad local: en áreas con muchos eventos (como el AMBA), usa un radio pequeño para mantener resolución; en áreas despobladas, usa un radio mayor para no perder eventos aislados en el silencio. Para Argentina esto es especialmente relevante.

### Qué significa la "temperatura" del mapa

La escala de colores del mapa **no representa cantidad de fábricas que cerraron** sino **intensidad de impacto relativo por unidad de economía local**. Una zona "roja" en el mapa es un lugar donde los cierres documentados representan una fracción significativa del empleo formal local, amplificada por el multiplicador sectorial de esas industrias.

Una zona que aparece "fría" puede tener muchos cierres en términos absolutos pero poca dependencia local de esas industrias; o puede simplemente no tener datos documentados en la base de noticias todavía.

---

## VI. Las variables en el código y su anclaje teórico

Esta tabla resume la correspondencia entre conceptos teóricos y variables concretas:

| Variable | Tipo | Fundamento teórico |
|----------|------|-------------------|
| `empleados_afectados` | int | Impacto directo; numerador del shock de empleo |
| `puestos_total_depto` | int | Circuito económico local; denominador de la dependencia |
| `ratio_dependencia` | float 0-1 | Teoría de dependencia monoindustrial; mide el shock relativo |
| `multiplicador_sectorial` | float | Multiplicador keynesiano + encadenamiento input-output por sector |
| `peso_final` | float 0-1 | Índice compuesto de impacto local; variable de ponderación del KDE |
| `location` GEOGRAPHY | PostGIS | Punto en el espacio para cálculo del kernel |
| KDE bandwidth | parámetro | Supuesto de alcance espacial del impacto (radio de propagación) |
| `codgeo_depto` | CHAR(5) | Clave de join entre eventos y denominador de empleo (OEDE) |

### Cómo modificar las variables según el enfoque teórico

El diseño del código permite cambiar el marco teórico sin reescribir toda la arquitectura:

**Si se quiere usar el LQ como peso en lugar del ratio de dependencia:**

Reemplazar `ratio_dependencia` por `lq_sector_local` en `compute_weights.py`.
Requiere calcular previamente el LQ por departamento × CLAE2 × período desde los datos OEDE.
Limitación: inestable en municipios pequeños.

**Si se quiere usar PBI municipal como denominador en lugar de empleo formal:**

El OEDE provee masa salarial por departamento, que es un proxy razonable del PBI local de la economía formal. Cambiar `puestos_total_depto` por `masa_salarial_depto` en el denominador da un indicador de impacto sobre el ingreso formal, no sobre el empleo.

**Si se quieren usar multiplicadores calibrados para Argentina:**

Los valores actuales son estimaciones propias. Una mejora metodológica sería usar las tablas de insumo-producto del INDEC (publicadas esporádicamente) para calcular multiplicadores de empleo por sector para la economía argentina específicamente.

**Si se quiere agregar recuperación temporal:**

Un evento de cierre no tiene el mismo impacto en el año 1 que en el año 3. Se podría agregar una función de decaimiento temporal al `peso_final`:
```
peso_temporal(t) = peso_final × exp(-λ × años_desde_cierre)
```
Donde λ es la tasa de recuperación esperada del mercado laboral local. Esto es especialmente relevante para el análisis histórico con el slider temporal.

---

## VII. Limitaciones metodológicas y decisiones abiertas

### Sobre los datos

- Los datos del OEDE están disponibles a nivel **departamento** (~500 unidades), no a nivel localidad. En departamentos grandes con varias localidades, el denominador puede estar sobreestimado para el evento específico.
- Los eventos documentados en la base de noticias son una **muestra sesgada**: se documentan más los cierres grandes y mediáticos. Los cierres de microempresas y pymes pequeñas están subrepresentados.
- El **empleo informal** no está en el OEDE. En muchas localidades del interior el empleo informal representa una fracción importante del empleo total. El denominador formal subestima la economía local real.

### Sobre los multiplicadores

Los valores de la tabla `MULTIPLICADORES` son estimaciones construidas a partir de literatura de economía regional, no de tablas insumo-producto específicas para Argentina. Son consistentes internamente (los sectores más complejos tienen multiplicadores más altos) pero deberían considerarse como órdenes de magnitud, no como valores precisos.

### Sobre el KDE

El bandwidth de 50 km es un punto de partida. La decisión óptima del bandwidth debería calibrarse a la geografía argentina: radios menores en el conurbano, mayores en la Patagonia o el NOA. El bandwidth adaptativo (implementado en librerías como `KernelDensity` de scikit-learn con `algorithm='ball_tree'`) es la extensión metodológica más importante pendiente.

---

## VIII. Fuentes de datos utilizadas

- **OEDE** (Observatorio de Empleo y Dinámica Empresarial, Ministerio de Capital Humano): empleo asalariado registrado privado por departamento, CLAE2 y período. Serie mensual desde 2014.
- **SRT** (Superintendencia de Riesgos del Trabajo): registro de empleadores activos y bajas. Base de los conteos de cierres del CEPA y el IPA.
- **INDEC CODGEO**: cartografía censal a nivel departamento, fracción y radio censal. Censo 2022. Disponible en formato SHP y GeoJSON en geoservicios.indec.gov.ar
- **georef-ar API** (datos.gob.ar): API pública para normalización de nombres geográficos y resolución de códigos INDEC por nombre de localidad.
- **Base de noticias propia**: eventos de cierre documentados periodísticamente, geocodificados vía georef-ar.
