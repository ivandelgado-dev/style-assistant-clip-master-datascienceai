# Entrega 3 — Diseño del modelo de datos y capa gold

**Autor:** Iván Delgado
**Máster en Data Science y Desarrollo de IA — Evolve Academy**
**Fecha:** Julio 2026

---

## 1. Resumen de la idea y datos del proyecto

**Problema.** Las personas tienen en su armario prendas suficientes para construir buenos conjuntos, pero carecen de criterio o tiempo para combinarlas. Las aplicaciones de moda operan sobre catálogos comerciales, no sobre el inventario real del usuario, porque su objetivo de negocio es vender prendas nuevas.

**Solución.** Un sistema de recomendación de outfits basado en recuperación y ranking multimodal. Dado un armario digitalizado y una imagen de inspiración, el sistema construye conjuntos con las prendas que el usuario ya posee. Cuando una posición del outfit no puede cubrirse con el armario, recupera del catálogo la prenda más próxima y enlaza al producto real. Alcance acotado a ropa de hombre.

La contribución técnica son las **proyecciones específicas por atributo** sobre un backbone CLIP congelado: cabezas ligeras que permiten consultar por corte, color o textura de forma independiente, en lugar de sobre un embedding monolítico.

**Fuentes y aportación de cada una:**

| Fuente | Qué aporta |
|---|---|
| DeepFashion (Category & Attribute Prediction) | Imágenes de prenda con etiquetas de atributo. **Señal de supervisión** para entrenar las cabezas de atributo |
| Polyvore Outfits | Outfits curados por humanos. **Señal de supervisión** para compatibilidad entre prendas |
| Fashion Product Images | Catálogo de 44k productos con categoría, color y género. **Índice de recuperación** |
| Catálogo comercial (Zara/Bershka) | 150–300 productos con altura de modelo y talla. **Anclaje de escala** y enlace a producto comprable |
| Armario propio | 80–150 prendas fotografiadas con móvil. **Conjunto de test out-of-distribution** |

Las tres primeras y la última contienen imágenes; ninguna contiene series temporales. Detalle completo en [`02_datos_necesarios.md`](02_datos_necesarios.md).

---

## 2. Tecnología o formato de almacenamiento elegido

La decisión se toma por tipo de dato, no por preferencia. El proyecto maneja **tres tipos de dato con requisitos incompatibles entre sí**, y forzarlos a un único formato produciría un diseño peor.

### 2.1 PostgreSQL con la extensión pgvector — almacén principal

**Qué guarda:** metadatos estructurados de prendas, armarios de usuario, outfits generados, feedback, y **los embeddings** de cada prenda.

**Por qué.** El sistema necesita dos operaciones sobre la misma entidad:

1. Filtrado relacional: *"prendas de la categoría camisa, del usuario 3, de color azul"*
2. Búsqueda vectorial: *"las 10 prendas cuyo embedding esté más próximo a este vector"*

Y, críticamente, **las necesita combinadas**: *"las 10 camisas del usuario 3 más próximas a este embedding"*. Una consulta de vecinos más cercanos con un filtro relacional previo.

Con Postgres + pgvector esto es una sola consulta SQL con `ORDER BY embedding <-> :query_vector` y un `WHERE` normal. Con una base vectorial separada (FAISS, Chroma) habría que mantener dos sistemas sincronizados y resolver el filtrado en la aplicación, con el riesgo de recuperar k vecinos y descubrir que ninguno cumple el filtro.

**Por qué PostgreSQL y no MySQL.** MySQL no dispone de extensión de búsqueda vectorial equiparable. El SQL utilizado (CTEs, funciones de ventana, JOINs, constraints) es el mismo en ambos.

**Por qué no SQLite.** pgvector no está disponible. Para un despliegue en Docker, Postgres es igual de sencillo de levantar.

### 2.2 Ficheros Parquet — capas intermedias del pipeline offline

**Qué guarda:** las tablas de anotación de DeepFashion y Polyvore tras la limpieza, y las matrices de embeddings antes de su carga en base de datos.

**Por qué.** DeepFashion distribuye sus anotaciones como ficheros de texto plano de ~290.000 filas con formato posicional. Polyvore es JSON anidado. Ninguno se consume directamente. La capa intermedia es tabular, se lee muchas veces durante el entrenamiento y no se modifica: es el caso de uso exacto de un formato columnar.

Parquet frente a CSV: tipado nativo (evita reinferir tipos en cada lectura), compresión, y lectura selectiva de columnas. Una tabla de 290k filas con 250 columnas de atributo binario ocupa un orden de magnitud menos y se lee sensiblemente más rápido.

### 2.3 Sistema de ficheros — imágenes

**Qué guarda:** las imágenes de DeepFashion, Fashion Product Images y el armario propio.

**Por qué.** Almacenar imágenes como BLOB en la base de datos es un antipatrón conocido: infla el tamaño de la base, complica los backups y no aporta nada, porque nunca se consultan por contenido — se leen por ruta durante la extracción de embeddings.

La base de datos guarda la **ruta o URL**, no el binario.

**Excepción crítica.** Las imágenes del catálogo comercial (Zara/Bershka) **no se almacenan en ninguna forma**. Se guarda su URL y su embedding. La aplicación las carga en el navegador del usuario desde el servidor de origen. Justificación de derechos de autor en `02_datos_necesarios.md`, §3.4.

### 2.4 YAML — configuración de experimentos

Un fichero por corrida de entrenamiento, con hiperparámetros, semilla y rutas. Las métricas resultantes se guardan junto al YAML. No es una capa de datos del proyecto, pero es parte del contrato de reproducibilidad.

### 2.5 Resumen de la decisión

| Formato | Qué contiene | Por qué |
|---|---|---|
| PostgreSQL + pgvector | Metadatos, embeddings, outfits, feedback | Filtrado relacional y búsqueda vectorial en una sola consulta |
| Parquet | Anotaciones limpias, matrices de embeddings | Tabular, inmutable, lectura repetida, tipado nativo |
| Sistema de ficheros | Imágenes de datasets públicos y armario | Los BLOB en base de datos son un antipatrón |
| YAML | Configuración de experimentos | Reproducibilidad |
| — | Imágenes de catálogo comercial | **No se almacenan.** Solo URL y embedding |

No se usa Excel (no hay intervención manual sobre tablas grandes) ni JSON como almacenamiento (solo como formato de origen de Polyvore, que se convierte a Parquet en la primera transformación).

---

## 3. Estructura de capas de datos

Se adopta la estructura raw / processed / gold propuesta en el enunciado, **con una desviación que debe justificarse**: la capa gold no es un conjunto de ficheros, sino un **esquema en base de datos**.

### 3.1 Motivo de la desviación

La capa gold se define como "los datos finales preparados para ser consumidos en análisis, modelos, dashboards o entregables finales". En este proyecto, el consumidor final no es un notebook ni un dashboard: es una **aplicación que sirve consultas en tiempo real**. La operación central —*buscar los k vecinos más próximos a un vector, filtrados por categoría y usuario*— no puede resolverse eficientemente sobre un fichero Parquet.

Adicionalmente, dos de las tablas gold (`outfits`, `feedback`) **se escriben en tiempo de ejecución**, no en el pipeline de preparación. Un fichero no soporta escritura concurrente con integridad transaccional.

Por tanto: raw y processed son ficheros; **gold es Postgres**.

### 3.2 Estructura

```
data/
├── raw/                          ← tal como se descarga, nunca se modifica
│   ├── deepfashion/
│   │   ├── img/
│   │   └── anno/                 ← list_attr_img.txt, list_category_img.txt
│   ├── polyvore/                 ← HuggingFace datasets, formato original
│   ├── fashion_products/
│   │   ├── images/
│   │   └── styles.csv
│   └── wardrobe/                 ← fotos propias + metadatos_wardrobe.csv
│
├── processed/                    ← limpio, tipado, sin decisiones de modelado
│   ├── deepfashion_attrs.parquet
│   ├── polyvore_outfits.parquet
│   ├── polyvore_items.parquet
│   ├── catalog_items.parquet
│   ├── wardrobe_items.parquet
│   └── commercial_catalog.parquet
│
└── embeddings/                   ← salida del backbone congelado
    ├── clip_deepfashion.parquet
    ├── clip_catalog.parquet
    └── clip_wardrobe.parquet

[capa gold → PostgreSQL, ver §4]
```

`data/` está en `.gitignore` en su totalidad. Las imágenes de DeepFashion superan los 20 GB y las licencias de dos de las fuentes prohíben la redistribución.

### 3.3 Qué ocurre en cada transición

**raw → processed.** Limpieza sin decisiones de modelado: tipado, normalización de nombres de columna, resolución de rutas de imagen, filtrado por género (masculino), eliminación de registros con imagen ausente o corrupta. Es idempotente y reproducible desde raw.

**processed → embeddings.** Se ejecuta el backbone CLIP congelado sobre cada imagen. Es la operación más costosa del pipeline (~1–2 h de GPU para el corpus completo) y se ejecuta **una sola vez**. Que sea una capa separada y no un paso dentro de la carga es deliberado: si cambia el esquema de la base de datos, no se recomputan los embeddings.

**embeddings + processed → gold.** Carga en PostgreSQL. Aquí sí hay decisiones de modelado: qué atributos se conservan, cómo se mapean las categorías entre fuentes, qué constituye una prenda válida.

---

## 4. Definición de la capa gold

La capa gold son **seis tablas en PostgreSQL**. Constituyen el contrato de datos: todo lo que consumen el modelo, la API y la aplicación sale de aquí.

### 4.1 `users`

**Descripción funcional.** Perfil del usuario. Todos los campos salvo el identificador son opcionales, por diseño (§4.7).

**Granularidad.** Una fila por usuario.
**Volumen esperado.** 1–5 registros (MVP).
**Clave primaria.** `user_id`.

| Campo | Tipo | Obligatorio | Observaciones |
|---|---|---|---|
| `user_id` | `SERIAL` | Sí | PK |
| `nombre` | `VARCHAR(50)` | Sí | Etiqueta para el selector de la demo |
| `altura_cm` | `SMALLINT` | No | Solo para reglas de proporción |
| `peso_kg` | `SMALLINT` | No | Solo para reglas de proporción |
| `estilo_preferido` | `VARCHAR(20)` | No | Enum: streetwear, casual, smart_casual, formal |
| `created_at` | `TIMESTAMP` | Sí | Default `NOW()` |

**Consumido por.** Aplicación (motor de reglas de proporción).

---

### 4.2 `garments`

**Descripción funcional.** Tabla central del sistema. Contiene **tanto las prendas del armario del usuario como las del catálogo**, unificadas. La distinción es `user_id IS NULL` para catálogo.

Esta unificación no es un atajo: el motor de recuperación es idéntico en ambos casos, y la operación *"busca en mi armario, y si no lo encuentras, busca en el catálogo"* se resuelve cambiando un `WHERE` en lugar de duplicando lógica.

**Granularidad.** Una fila por prenda individual.
**Volumen esperado.** ~44.000 (catálogo Kaggle) + ~300 (catálogo comercial) + ~150 (armario propio) ≈ **44.500 registros**.
**Clave primaria.** `garment_id`.

| Campo | Tipo | Obligatorio | Observaciones |
|---|---|---|---|
| `garment_id` | `SERIAL` | Sí | PK |
| `user_id` | `INTEGER` | No | FK → `users`. **NULL ⇒ prenda de catálogo** |
| `source` | `VARCHAR(20)` | Sí | Enum: `wardrobe`, `kaggle_catalog`, `commercial_catalog` |
| `categoria` | `VARCHAR(30)` | Sí | Taxonomía unificada (§6). Enum cerrado |
| `slot` | `VARCHAR(15)` | Sí | Derivado de categoría. Enum: `top`, `bottom`, `outer`, `shoes`, `accessory` |
| `color_base` | `VARCHAR(20)` | Sí | Taxonomía unificada de ~15 colores |
| `talla` | `VARCHAR(10)` | No | Declarada por el usuario |
| `tejido` | `VARCHAR(30)` | No | Declarado o inferido por VLM |
| `corte` | `VARCHAR(30)` | No | Declarado o inferido por VLM |
| `atributos` | `JSONB` | No | Atributos adicionales sin esquema fijo |
| `image_path` | `TEXT` | No | Ruta local. NULL para catálogo comercial |
| `image_url` | `TEXT` | No | URL de origen. Obligatorio si `image_path` es NULL |
| `product_url` | `TEXT` | No | Enlace de compra. Solo `commercial_catalog` |
| `modelo_altura_cm` | `SMALLINT` | No | Altura del modelo. Solo `commercial_catalog` |
| `modelo_talla` | `VARCHAR(10)` | No | Talla que viste el modelo |
| `embedding` | `VECTOR(512)` | Sí | Embedding CLIP. Índice HNSW |
| `emb_corte` | `VECTOR(128)` | No | Proyección de atributo. NULL hasta entrenar |
| `emb_color` | `VECTOR(128)` | No | Proyección de atributo |
| `emb_textura` | `VECTOR(128)` | No | Proyección de atributo |

**Restricciones.**
- `CHECK (image_path IS NOT NULL OR image_url IS NOT NULL)` — toda prenda debe ser localizable
- `CHECK (source <> 'commercial_catalog' OR image_path IS NULL)` — **garantiza a nivel de base de datos que ninguna imagen comercial se almacena localmente**

Esta segunda restricción convierte una decisión legal en una invariante del sistema. No depende de que nadie se olvide.

**Variables especialmente relevantes.** `embedding` es la entrada del retrieval. `emb_corte`, `emb_color`, `emb_textura` son la **salida del modelo entrenado** y el objeto de la evaluación: comparar retrieval sobre `embedding` (baseline) frente a retrieval sobre las proyecciones.

**Consumido por.** Modelo (entrenamiento y evaluación), API, aplicación.

---

### 4.3 `garment_attributes`

**Descripción funcional.** Etiquetas de atributo de DeepFashion, en formato largo. Es la **señal de supervisión** para entrenar las cabezas de atributo.

Se mantiene separada de `garments` porque la relación es N:M y porque las prendas de DeepFashion no entran en el índice de recuperación: sirven solo para entrenar. Meterlas en `garments` contaminaría el catálogo con 290.000 prendas no comprables.

**Granularidad.** Una fila por (prenda de entrenamiento, atributo).
**Volumen esperado.** ~290.000 prendas × ~5 atributos activos ≈ **1,5 M registros**.
**Clave primaria.** `(train_item_id, attr_name)`.

| Campo | Tipo | Obligatorio | Observaciones |
|---|---|---|---|
| `train_item_id` | `INTEGER` | Sí | ID de DeepFashion |
| `attr_name` | `VARCHAR(50)` | Sí | Nombre del atributo |
| `attr_group` | `VARCHAR(15)` | Sí | Enum: `corte`, `color`, `textura`, `patron`, `categoria` |
| `value` | `BOOLEAN` | Sí | Presencia del atributo |
| `image_path` | `TEXT` | Sí | Ruta a la imagen |

**Variable objetivo.** `value`, agrupada por `attr_group`. Cada cabeza del modelo se entrena sobre un grupo.

**Consumido por.** Entrenamiento de las proyecciones de atributo.

---

### 4.4 `outfits`

**Descripción funcional.** Outfits generados por el sistema y presentados al usuario. Se escribe en tiempo de ejecución.

**Granularidad.** Una fila por outfit generado.
**Volumen esperado.** Crece con el uso. Cientos de registros durante el desarrollo.
**Clave primaria.** `outfit_id`.

| Campo | Tipo | Obligatorio | Observaciones |
|---|---|---|---|
| `outfit_id` | `SERIAL` | Sí | PK |
| `user_id` | `INTEGER` | Sí | FK → `users` |
| `source_image_url` | `TEXT` | No | Imagen de inspiración, si la hubo |
| `query_text` | `TEXT` | No | Petición en lenguaje natural |
| `constraints` | `JSONB` | No | Restricciones extraídas por el LLM |
| `score` | `REAL` | Sí | Puntuación de compatibilidad |
| `created_at` | `TIMESTAMP` | Sí | Default `NOW()` |

**Consumido por.** Aplicación, análisis de uso, trabajo futuro sobre personalización.

---

### 4.5 `outfit_items`

**Descripción funcional.** Tabla puente. Resuelve la relación N:M entre outfits y prendas.

**Granularidad.** Una fila por (outfit, prenda).
**Volumen esperado.** ~4× el número de outfits.
**Clave primaria.** `(outfit_id, garment_id)`.

| Campo | Tipo | Obligatorio | Observaciones |
|---|---|---|---|
| `outfit_id` | `INTEGER` | Sí | FK → `outfits`, `ON DELETE CASCADE` |
| `garment_id` | `INTEGER` | Sí | FK → `garments` |
| `slot` | `VARCHAR(15)` | Sí | Posición que ocupa en el outfit |
| `similarity` | `REAL` | No | Similitud con la referencia, si la hubo |

**Restricción.** `UNIQUE (outfit_id, slot)` — un outfit no puede tener dos prendas en la misma posición.

---

### 4.6 `feedback`

**Descripción funcional.** Valoración del usuario sobre un outfit.

No se modela en el MVP. Se recoge desde el primer día porque cuesta una tabla, y porque es el único camino honesto hacia la personalización: un modelo de preferencia requiere preferencias observadas, y esas no se pueden generar retroactivamente.

**Granularidad.** Una fila por (usuario, outfit) valorado.
**Volumen esperado.** Decenas o cientos.
**Clave primaria.** `(outfit_id, user_id)`.

| Campo | Tipo | Obligatorio | Observaciones |
|---|---|---|---|
| `outfit_id` | `INTEGER` | Sí | FK → `outfits` |
| `user_id` | `INTEGER` | Sí | FK → `users` |
| `rating` | `SMALLINT` | Sí | `CHECK (rating IN (-1, 1))` |
| `motivo` | `VARCHAR(30)` | No | Enum: `color`, `corte`, `ocasion`, `otro` |
| `created_at` | `TIMESTAMP` | Sí | Default `NOW()` |

**Consumido por.** Métrica de producto. Trabajo futuro.

---

### 4.7 Ausencia deliberada: tabla de medidas corporales

No existe ninguna tabla que asocie medidas corporales con adecuación de prendas, ni ningún campo de "qué le sienta bien a este usuario".

`altura_cm` y `peso_kg` viven en `users` como campos opcionales, se consumen **exclusivamente** por el motor de reglas heurísticas, y no son entrada de ningún modelo aprendido. Justificación completa en `02_datos_necesarios.md`, §4.2: no existen datos públicos para entrenar tal modelo, y un modelo entrenado sobre juicios estéticos de cuerpos aprendería sesgos corporales por construcción.

Esta ausencia es una decisión de diseño, no una omisión.

---

### 4.8 Tabla resumen

| Dataset gold | Granularidad | Campos clave | Volumen | Uso posterior |
|---|---|---|---|---|
| `users` | Una fila por usuario | `user_id`, `altura_cm` | ~5 | Aplicación, reglas |
| `garments` | Una fila por prenda | `garment_id`, `user_id`, `embedding`, `emb_*` | ~44.500 | Modelo, API, aplicación |
| `garment_attributes` | Una fila por (prenda, atributo) | `train_item_id`, `attr_group`, `value` | ~1,5 M | Entrenamiento |
| `outfits` | Una fila por outfit generado | `outfit_id`, `user_id`, `score` | Cientos | Aplicación, análisis |
| `outfit_items` | Una fila por (outfit, prenda) | `outfit_id`, `garment_id`, `slot` | ~4× outfits | Aplicación |
| `feedback` | Una fila por valoración | `outfit_id`, `user_id`, `rating` | Decenas | Métrica de producto |

---

## 5. Relaciones entre datos

### 5.1 Diagrama

```
users.user_id          1 --- N   garments.user_id      (NULL ⇒ catálogo)
users.user_id          1 --- N   outfits.user_id
users.user_id          1 --- N   feedback.user_id

outfits.outfit_id      1 --- N   outfit_items.outfit_id
garments.garment_id    1 --- N   outfit_items.garment_id
                       └── outfit_items resuelve N:M entre outfits y garments

outfits.outfit_id      1 --- 1   feedback.outfit_id    (por usuario)

garment_attributes     ─ sin FK a garments (ver §5.3)
```

### 5.2 Cardinalidades

| Relación | Tipo | Nota |
|---|---|---|
| `users` → `garments` | 1:N | **Opcional.** `user_id` NULL identifica catálogo |
| `users` → `outfits` | 1:N | Obligatoria |
| `outfits` ↔ `garments` | **N:M** | Resuelta por `outfit_items` |
| `outfits` → `feedback` | 1:1 por usuario | PK compuesta lo garantiza |

La relación N:M es la única no trivial: un outfit contiene varias prendas, y una prenda aparece en varios outfits. La tabla puente lleva atributos propios (`slot`, `similarity`), lo que confirma que no es un artificio.

### 5.3 Por qué `garment_attributes` no tiene clave foránea a `garments`

Es deliberado y conviene explicarlo, porque a primera vista parece un error de diseño.

`garment_attributes` contiene prendas de **DeepFashion**, que existen únicamente para entrenar las cabezas de atributo. No entran en el índice de recuperación, no son comprables y no pertenecen a ningún armario. Son 290.000 registros de entrenamiento.

`garments` contiene prendas **recuperables**: del armario o del catálogo.

Son poblaciones disjuntas. Forzar una FK obligaría a insertar 290.000 prendas de entrenamiento en la tabla de recuperación, contaminando todas las consultas del sistema con un `WHERE source <> 'training'`.

La alternativa es reconocer que **son dos universos distintos**: uno de entrenamiento, uno de servicio. El puente entre ellos no es una clave foránea: son los **pesos del modelo** entrenado sobre el primero y aplicado al segundo.

### 5.4 Joins previstos

**Consulta principal del sistema.** Recuperar las k prendas del usuario más próximas a un embedding de referencia, en una categoría dada:

```sql
SELECT garment_id, categoria, color_base,
       emb_corte <-> :query_vector AS distancia
FROM garments
WHERE user_id = :user_id
  AND slot = :slot
ORDER BY distancia
LIMIT :k;
```

Filtro relacional y ordenación vectorial en una sola consulta. Este es el argumento entero a favor de pgvector.

**Fallback a catálogo.** La misma consulta con `WHERE user_id IS NULL`. Sin lógica adicional.

**Composición de outfit.** `outfits ⋈ outfit_items ⋈ garments`, agrupando por `outfit_id`.

**Análisis de uso.** `feedback ⋈ outfits ⋈ outfit_items ⋈ garments` para responder qué categorías o colores reciben peor valoración. Requiere `COUNT(DISTINCT ...)` para evitar fan-out: un outfit con cuatro prendas produce cuatro filas tras el join, y contar valoraciones sobre ese resultado las cuadruplicaría.

### 5.5 Problemas previstos al combinar fuentes

**Taxonomías incompatibles.** Es el problema principal. DeepFashion tiene 50 categorías, Polyvore 11 tipos gruesos y 142 finos, Fashion Product Images su propia jerarquía de tres niveles. No existe correspondencia uno a uno: DeepFashion distingue `Tee` de `Top`, Fashion Product Images los agrupa en `Tshirts`.

**Mitigación.** Una taxonomía unificada de ~20 categorías masculinas, con una tabla de mapeo explícita y versionada por fuente. Se documenta qué se pierde en cada mapeo. Toda categoría no mapeable se descarta, no se asigna a la más parecida.

**Colores expresados de forma distinta.** Fashion Product Images usa nombres comerciales (`Navy Blue`, `Teal`). DeepFashion usa atributos binarios. El armario propio lo declara el usuario.

**Mitigación.** Taxonomía de ~15 colores base. Los nombres comerciales se mapean por diccionario; los no reconocidos se marcan como `NULL` y se resuelven por VLM, no por adivinación léxica.

**Distribución visual heterogénea.** Fashion Product Images son fotos de estudio con fondo blanco. El armario propio son fotos de móvil. Los embeddings de ambos conviven en la misma tabla y se comparan por distancia coseno.

Este es el **domain gap**, y no es un problema a resolver antes del modelado: es un fenómeno a **medir**. Es el motivo de que el armario propio exista como conjunto de test.

---

## 6. Diccionario de datos inicial

Se documentan los campos relevantes para el modelo, la aplicación y la evaluación.

| Campo | Descripción | Tipo | Fuente | Obligatorio | Observaciones |
|---|---|---|---|---|---|
| `garment_id` | Identificador de prenda | `SERIAL` | Generado | Sí | PK |
| `user_id` | Propietario de la prenda | `INTEGER` | Generado | No | **NULL ⇒ catálogo.** Semántica esencial |
| `source` | Origen del registro | `VARCHAR(20)` | Generado | Sí | `wardrobe` / `kaggle_catalog` / `commercial_catalog` |
| `categoria` | Categoría de prenda | `VARCHAR(30)` | Mapeada | Sí | Taxonomía unificada, ~20 valores. Enum cerrado |
| `slot` | Posición en el outfit | `VARCHAR(15)` | Derivada | Sí | `top`/`bottom`/`outer`/`shoes`/`accessory`. Función de `categoria` |
| `color_base` | Color dominante | `VARCHAR(20)` | Mapeada | Sí | ~15 valores. Nombres comerciales normalizados |
| `talla` | Talla de la prenda | `VARCHAR(10)` | Usuario / catálogo | No | Sin normalizar entre marcas. Ver §7 |
| `tejido` | Composición | `VARCHAR(30)` | Usuario / VLM | No | Opcional. El sistema funciona sin él |
| `corte` | Silueta | `VARCHAR(30)` | Usuario / VLM | No | `slim`, `regular`, `oversize`, `relaxed` |
| `image_path` | Ruta local a la imagen | `TEXT` | Generada | No | NULL para catálogo comercial, por diseño |
| `image_url` | URL de la imagen de origen | `TEXT` | Fuente | No | Obligatorio si `image_path` es NULL |
| `product_url` | Enlace de compra | `TEXT` | Fuente | No | Solo catálogo comercial |
| `modelo_altura_cm` | Altura del modelo de la ficha | `SMALLINT` | Catálogo comercial | No | Anclaje de escala. Rango esperado 175–195 |
| `embedding` | Embedding CLIP de la imagen | `VECTOR(512)` | Modelo | Sí | Índice HNSW. Baseline de retrieval |
| `emb_corte` | Proyección de atributo: corte | `VECTOR(128)` | Modelo | No | NULL hasta entrenar. **Objeto de evaluación** |
| `emb_color` | Proyección de atributo: color | `VECTOR(128)` | Modelo | No | Ídem |
| `emb_textura` | Proyección de atributo: textura | `VECTOR(128)` | Modelo | No | Ídem |
| `attr_group` | Grupo del atributo | `VARCHAR(15)` | Mapeada | Sí | Determina qué cabeza lo consume |
| `value` | Presencia del atributo | `BOOLEAN` | DeepFashion | Sí | **Variable objetivo del entrenamiento** |
| `rating` | Valoración del outfit | `SMALLINT` | Usuario | Sí | −1 o 1. `CHECK` en base de datos |
| `score` | Puntuación de compatibilidad | `REAL` | Modelo | Sí | Rango [0, 1] |

**Campos con semántica no obvia**, que conviene explicitar:

- `user_id = NULL` **no significa dato ausente.** Significa "prenda de catálogo". Es una convención deliberada que evita una tabla separada.
- `slot` es **función determinista de `categoria`**. Se materializa como columna porque el filtrado por slot es la operación más frecuente y no conviene resolverlo con un `CASE` en cada consulta.
- `image_path = NULL` en catálogo comercial **no es un dato faltante**: es una restricción de diseño garantizada por un `CHECK`.

---

## 7. Problemas de calidad esperados

Aterrizados al caso concreto, no genéricos.

### 7.1 Desequilibrio severo de atributos en DeepFashion

De los 1.000 atributos etiquetados, una fracción pequeña aparece con frecuencia razonable; el resto son casi inexistentes. Entrenar una cabeza sobre un atributo que aparece en 200 de 290.000 imágenes produce un clasificador que predice siempre la clase mayoritaria y acierta el 99,9%.

Es el problema de calidad más grave del proyecto, porque afecta directamente a la señal de supervisión de la contribución técnica.

### 7.2 Etiquetado ruidoso y no exhaustivo

Los atributos de DeepFashion son etiquetas positivas: si una prenda tiene marcado `floral`, lo es. Pero **la ausencia de `striped` no garantiza que no lo sea** — puede que nadie lo etiquetara. El `value = FALSE` no es un negativo fiable.

Esto invalida el uso ingenuo de una pérdida binaria sobre todos los atributos.

### 7.3 Inconsistencia de categorías entre fuentes

Tres taxonomías incompatibles (§5.5). El riesgo concreto: un mapeo agresivo que fuerce correspondencias inexistentes introduce ruido sistemático, no aleatorio, y el modelo lo aprende.

### 7.4 Colores con nombres comerciales

`Navy Blue`, `Teal`, `Burgundy`, `Charcoal`. No hay lista cerrada, y un mapeo por coincidencia de subcadena confunde `Light Blue` con `Blue`.

### 7.5 Prendas casi duplicadas en el catálogo

Fashion Product Images contiene el mismo producto en varias variantes de color como registros independientes. Sus embeddings son casi idénticos. En retrieval, esto **satura los k primeros resultados con la misma prenda**, degradando la utilidad percibida sin degradar el Recall@k — la métrica no lo detecta.

### 7.6 Sesgo temporal de Polyvore

Polyvore cerró en 2018. Los outfits reflejan tendencias de esa época. Afecta a la percepción de actualidad, no a la validez de las métricas de compatibilidad.

### 7.7 Sesgo de cobertura del catálogo

Fashion Product Images procede de un catálogo indio. La distribución de estilo y tipología no coincide con el mercado europeo. Un usuario español encontrará prendas que no reconoce como opciones plausibles.

### 7.8 Domain gap entre catálogo y armario

Estudio con fondo blanco frente a fotos de móvil. **No es un defecto a corregir: es el fenómeno que el conjunto de test out-of-distribution existe para medir.**

### 7.9 Tallas no normalizadas entre marcas

Una M de Zara no es una M de Bershka. El campo `talla` es informativo, no comparable.

### 7.10 Imágenes corruptas o ausentes

Hay reportes de ZIP corruptos en Fashion Product Images. DeepFashion contiene rutas que apuntan a ficheros inexistentes.

### 7.11 Nulos genuinos frente a nulos semánticos

`tejido = NULL` significa "no se declaró".
`user_id = NULL` significa "prenda de catálogo".
`image_path = NULL` significa "prohibido almacenar".

Tratarlos uniformemente sería un error. Están documentados en §6.

### 7.12 Lo que no es un problema aquí

**Fechas mal formateadas, unidades de medida distintas, falta de histórico.** El proyecto no tiene serie temporal. No hay fechas de negocio que normalizar ni histórico que acumular. Los únicos campos temporales (`created_at`) son generados por la base de datos.

Se hace explícito porque el enunciado los sugiere y **no aplican** — inventar problemas de calidad inexistentes para rellenar la sección sería peor que omitirlos.

---

## 8. Decisiones de limpieza y transformación previstas

Hipótesis iniciales, revisables con datos.

### 8.1 Filtrado de atributos (responde a §7.1)

Se conservan únicamente los **~250 atributos más frecuentes**, siguiendo la práctica establecida en la literatura sobre DeepFashion. Sobre ese subconjunto, se aplica un umbral de frecuencia mínima por atributo (a determinar empíricamente, orden de 500 ocurrencias).

Los atributos se agrupan manualmente en `corte`, `color`, `textura`, `patron`. Esta agrupación **define qué cabeza consume qué señal** y es una decisión de modelado, no de limpieza. Se documenta el mapeo completo.

### 8.2 Tratamiento del etiquetado no exhaustivo (responde a §7.2)

No se usa pérdida binaria sobre negativos no verificados. Se entrena con **pérdida contrastiva sobre positivos**: dos prendas que comparten el atributo `oversize` deben acercarse en el subespacio de corte, sin afirmar nada sobre las que no lo tienen etiquetado.

Es la decisión de modelado que la calidad del dato impone. Merece la pena señalarlo: **el ruido de las etiquetas determina la función de pérdida**, no al revés.

### 8.3 Taxonomía unificada (responde a §7.3)

Se construye una tabla de mapeo explícita y versionada:

```
source_category → unified_category → slot
```

Reglas:
- Toda categoría de origen se mapea explícitamente o **se descarta**. No hay asignación por defecto.
- Las categorías femeninas se descartan (alcance del proyecto).
- El mapeo vive en `data/mappings/categories.csv`, bajo control de versiones. Es código, no un diccionario improvisado en un notebook.

### 8.4 Normalización de color (responde a §7.4)

Diccionario explícito de nombres comerciales → ~15 colores base. Los no reconocidos se marcan `NULL` y se resuelven por VLM sobre la imagen, **no por heurística léxica**. Preferible un nulo honesto a un `Light Blue` clasificado como `Blue`.

### 8.5 Deduplicación de casi-duplicados (responde a §7.5)

Detección por umbral de similitud coseno entre embeddings dentro de la misma categoría (umbral inicial ~0,98, calibrado sobre una muestra anotada a mano).

Los duplicados **no se eliminan**: se marcan con un `dup_group_id`. En retrieval se devuelve un único representante por grupo. Eliminarlos perdería variantes de color que sí son productos distintos y comprables.

### 8.6 Validez de un registro

Se descarta una prenda si:
- La imagen no existe, no se abre, o mide menos de 100×100 px
- La categoría no está en la taxonomía unificada
- Es prenda femenina
- Falla el `CHECK` de localizabilidad (ni `image_path` ni `image_url`)

Se conserva, con nulos, si faltan `talla`, `tejido` o `corte`. **Son opcionales por diseño.**

### 8.7 Variables derivadas

| Variable | Cómo se construye | Para qué |
|---|---|---|
| `slot` | Función de `categoria` | Filtrado en retrieval |
| `embedding` | CLIP sobre la imagen | Baseline y entrada de las cabezas |
| `emb_corte`, `emb_color`, `emb_textura` | Cabezas entrenadas sobre `embedding` | **Contribución del proyecto** |
| `dup_group_id` | Clustering por similitud | Deduplicación en retrieval |
| `ratio_altura` | `user.altura_cm / modelo_altura_cm` | Reglas de proporción |

### 8.8 Datos descartados y por qué

| Descartado | Motivo |
|---|---|
| Prendas femeninas | Alcance del proyecto |
| Atributos con frecuencia < umbral | Señal insuficiente (§7.1) |
| Categorías no mapeables | Evitar ruido sistemático (§8.3) |
| Accesorios de Polyvore no textiles | Fuera del espacio de outfit masculino |
| Imágenes de catálogo comercial | Derechos de autor. Solo embedding y URL |
| Cualquier corpus de juicio estético sobre cuerpos | Riesgo ético. Ver `02_datos_necesarios.md` §4.2 |

---

## 9. Riesgos del modelo de datos

### 9.1 Qué está más claro

El **esquema relacional**. Seis tablas, cardinalidades conocidas, una única relación N:M resuelta con tabla puente. Es un modelo dimensional convencional y no hay ambigüedad sobre qué representa cada fila.

La **elección tecnológica**. La consulta central del sistema —vecinos más próximos con filtro relacional— determina la decisión por sí sola. No hay margen razonable de duda.

La **capa raw**. Las fuentes están identificadas, son descargables y su licencia está documentada.

### 9.2 Qué genera más incertidumbre

**La agrupación de atributos en cabezas** (§8.1). Es la decisión de la que depende toda la contribución técnica, y ahora mismo es una hipótesis. Que los ~250 atributos de DeepFashion se dividan limpiamente en corte / color / textura es una suposición, y la literatura no ofrece una partición canónica.

Si la agrupación es mala, las cabezas aprenden subespacios que no corresponden a atributos perceptualmente separables, y el desacoplamiento no funciona. **No se sabrá hasta tener el primer resultado de retrieval por atributo frente al baseline.**

Es el riesgo número uno del proyecto entero, y es un riesgo del modelo de datos: nace de cómo se agrupa la señal de supervisión.

### 9.3 Qué fuente puede dar más problemas

**DeepFashion**, por tres motivos acumulados:

1. Es la fuente de la señal de supervisión de la contribución
2. Su etiquetado es ruidoso y no exhaustivo (§7.2)
3. Su desequilibrio es severo (§7.1)

Fashion Product Images tiene una licencia no declarada, pero es sustituible. Polyvore alimenta un módulo que en el peor caso se reemplaza por reglas. DeepFashion no tiene sustituto directo para lo que hace.

### 9.4 Qué ocurriría si la capa gold no se puede construir

Depende de qué falle.

**Si falla `garment_attributes`** (DeepFashion inaccesible o su etiquetado inservible), no hay señal para entrenar las cabezas. El proyecto pierde su contribución. Alternativa: etiquetar atributos con un VLM sobre el catálogo, generando supervisión sintética. Es viable y está contemplado en `02_datos_necesarios.md` §5 — con la salvedad documentada de que se estaría destilando el sesgo del VLM, y de que el modelo resultante no puede superar a su etiquetador.

**Si falla `garments`** (ningún catálogo disponible), no hay sistema. Es el escenario improbable: hay al menos tres fuentes alternativas.

**Si fallan `outfits`, `outfit_items` o `feedback`**, no pasa nada relevante: son tablas que el sistema escribe, no que consume para modelar.

### 9.5 Alternativa de simplificación

Si el modelo relacional resultara excesivo para el tiempo disponible, la degradación es gradual y por este orden:

1. **Prescindir de `feedback`.** Coste: perder la métrica de producto. Cero impacto en el modelado.
2. **Prescindir de `outfits` y `outfit_items`.** Los outfits se generan en memoria y no se persisten. Coste: no hay análisis de uso.
3. **Prescindir de `users`.** Un solo armario, sin `user_id`. Coste: el sistema deja de ser multi-usuario, lo cual sería una regresión de diseño difícil de revertir. **Se descarta salvo emergencia.**
4. **Sustituir pgvector por FAISS + Parquet.** Coste: dos sistemas que sincronizar y filtrado resuelto en la aplicación. Es un paso atrás, no adelante.

El núcleo irreducible es `garments` con sus embeddings y `garment_attributes` con sus etiquetas. Todo lo demás es infraestructura alrededor.

**Lo que no se simplifica bajo ninguna circunstancia:** el `CHECK` que impide almacenar imágenes de catálogo comercial, y la partición disjunta de Polyvore. El primero es una obligación legal; el segundo, la diferencia entre una métrica honesta y una inflada.
