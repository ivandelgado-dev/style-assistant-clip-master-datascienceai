# Entrega 4 — Diseño del análisis y estrategia de modelado

**Autor:** Iván Delgado
**Máster en Data Science y Desarrollo de IA — Evolve Academy**
**Fecha:** Julio 2026

---

## Nota preliminar: reajuste de alcance respecto a las entregas 2 y 3

El enunciado permite modificar decisiones previas si el diseño del análisis lo obliga, manteniendo la trazabilidad. Esta entrega ejerce esa opción, siguiendo la corrección recibida sobre la entrega anterior.

Las entregas 2 y 3 describían un MVP con múltiples componentes: digitalización del armario, etiquetado automático por VLM, generación de conjuntos, búsqueda por atributos, catálogo comercial, explicaciones por LLM y aplicación desplegada. La observación del profesor fue precisa: **son demasiadas piezas para un MVP, y conviene proteger un core acotado**.

En consecuencia, se redefine el alcance con la siguiente disciplina:

**Core del proyecto — lo que se demuestra con rigor y se evalúa:**
1. Que la búsqueda por atributos (embeddings desacoplados) **mejora de forma medible** frente al enfoque básico (CLIP plano).
2. Que el sistema **funciona sobre un armario real**, no solo sobre fotos de catálogo.

**Nice-to-have — se construye solo si el core está cerrado y sobra tiempo:**
- Recomendador completo de outfits (composición y compatibilidad).
- Catálogo comercial y enlace a producto.
- LLM para intención y explicaciones.
- Aplicación desplegada.

Todo el resto del documento se organiza sobre esta separación. El modelado, las métricas y la validación se refieren al **core**. Los componentes nice-to-have se mencionan cuando corresponde, pero no son objeto de la evaluación formal.

Se incorpora además una segunda corrección del profesor: **las métricas de recuperación no bastan** para demostrar que un conjunto es útil o coherente, por lo que se añade una **valoración humana** como parte de la evaluación (§7). Y una tercera: **el catálogo comercial se excluye del core**; el núcleo trabaja exclusivamente con fuentes académicas, evitando las restricciones legales de los catálogos de tienda.

---

## 1. Problema que se busca resolver

### Qué ocurre actualmente y por qué es un problema

Cuando alguien ve una prenda o un look que le gusta —en una foto, en una tienda, en redes— y quiere encontrar algo parecido en su propio armario, no dispone de ninguna herramienta que lo haga. El buscador mental humano falla especialmente en un caso: **cuando el parecido es parcial**. La persona tiene una prenda con el corte adecuado pero en otro color, o la textura correcta en otra forma, y no la asocia con la referencia porque "no es igual".

Los sistemas de búsqueda visual existentes tienen el mismo límite, pero por un motivo técnico: representan cada imagen con un único vector (embedding) que **mezcla todos los atributos** —color, corte, textura, categoría— en una sola magnitud. Con esa representación, "parecido" significa "parecido en todo a la vez". No se puede pedir "parécete en el corte, ignora el color".

### Quién usa el resultado y para qué decisión

El usuario final es una persona que quiere vestir con lo que ya tiene. La decisión que apoya el sistema es concreta: **dado un estímulo visual, qué prendas de mi armario se aproximan a él, y en qué dimensión** (corte, color, textura).

En el marco del proyecto, el usuario inmediato del *resultado del modelado* es el propio sistema de recomendación (nice-to-have), que consume la búsqueda por atributos como componente. Pero la búsqueda por atributos tiene valor por sí sola y es lo que se evalúa.

### Qué resultado concreto lo hace útil

El proyecto se considera exitoso si demuestra que:

> Una búsqueda de prendas por atributo específico (corte, color o textura) recupera resultados más relevantes para ese atributo que una búsqueda con el embedding CLIP completo, y ese comportamiento se mantiene sobre fotografías de un armario real, no solo sobre imágenes de catálogo.

Ese es el enunciado que las secciones siguientes operacionalizan en modelos, datos y métricas.

---

## 2. Análisis de datos planteado y utilidad esperada

Este es un proyecto de **recuperación (retrieval)**, no de predicción temporal ni de clasificación clásica. Siguiendo la indicación del enunciado, el análisis se centra en lo que un problema de recuperación requiere: entender los elementos (prendas), sus atributos, y cómo se estructura el espacio de representación.

### Preguntas que se quieren responder con los datos

**Sobre los atributos (antes del modelado):**
- ¿Cómo se distribuyen los atributos en DeepFashion? ¿Cuántos son utilizables tras filtrar los poco frecuentes?
- ¿Los atributos se agrupan limpiamente en corte / color / textura, o hay solapamiento y ambigüedad? *(Esta es la pregunta de la que depende toda la contribución — ver §8.)*
- ¿Qué grado de desequilibrio hay por atributo, y qué implica para el entrenamiento?

**Sobre el espacio de embeddings (antes y durante el modelado):**
- ¿Qué estructura tiene el espacio CLIP plano? ¿Los vecinos más próximos de una prenda comparten categoría, color, ambos, ninguno?
- Cuando se buscan las prendas más parecidas a una dada, ¿en qué atributo se parecen realmente? Esto revela qué atributo *domina* el embedding plano, que es precisamente lo que el desacoplamiento busca corregir.

**Sobre el armario real (evaluación):**
- ¿Cuánto se separan, en el espacio de embeddings, las fotos de armario real de las de catálogo? Es la medición directa del *domain gap*.

### Análisis concretos

| Análisis | Tipo | Qué revela |
|---|---|---|
| Distribución de frecuencia de atributos | Descriptivo | Cuántos atributos son entrenables; magnitud del desequilibrio |
| Matriz de co-ocurrencia de atributos | Relacional | Si los grupos (corte/color/textura) son separables o se solapan |
| Vecinos más próximos en CLIP plano | Exploratorio | Qué atributo domina la similitud "por defecto" |
| Proyección 2D del espacio (UMAP/t-SNE) | Visual | Si el espacio se organiza por categoría, color o de forma difusa |
| Distancia catálogo vs. armario real | Comparativo | Magnitud del domain gap |
| Casi-duplicados en catálogo | Calidad | Prendas que saturarían los resultados de búsqueda |

### Hipótesis que se quieren comprobar

- **H1:** En el embedding CLIP plano, la similitud está dominada por categoría y color, y es débil en corte y textura. *(Si es cierta, justifica el proyecto: el margen de mejora está en los atributos que CLIP no separa bien.)*
- **H2:** Los atributos de DeepFashion pueden agruparse en un número reducido de dimensiones perceptualmente coherentes.
- **H3:** Las fotos de armario real están sistemáticamente desplazadas respecto a las de catálogo en el espacio de embeddings.

### Qué entra en el MVP

Del análisis, se incorporan al MVP: la visualización del espacio de embeddings (para la memoria y la defensa), el indicador de domain gap, y las tablas de distribución de atributos. No como dashboard decorativo, sino como evidencia de las decisiones de modelado.

### Cómo ayuda este análisis

El análisis de co-ocurrencia de atributos (H2) **decide cómo se agrupan las cabezas del modelo**, que es la decisión de diseño más crítica. El análisis de vecinos en CLIP plano (H1) establece el baseline cualitativo y dice dónde hay margen. El domain gap (H3) define la dificultad de la evaluación sobre armario real. Ninguno es un gráfico de relleno: cada uno alimenta una decisión posterior.

---

## 3. Tipo de modelos que se van a plantear

### Tipo de tarea

**Recuperación multimodal por atributo** (attribute-specific image retrieval). No es clasificación ni regresión: dado un vector de consulta y un atributo, se ordenan las prendas por relevancia respecto a ese atributo.

El "modelo" que se entrena son las **proyecciones por atributo**: transformaciones que llevan el embedding CLIP a subespacios donde la distancia refleja un solo atributo.

### Baseline y candidatos

| Alternativa | Tipo | Por qué se plantea | Limitación principal |
|---|---|---|---|
| **Baseline 0: aleatorio** | Ranking aleatorio estratificado por categoría | Referencia mínima absoluta. Cualquier método debe superarlo con holgura | Trivial. Solo sirve de suelo |
| **Baseline 1: CLIP plano** | Similitud coseno sobre el embedding CLIP completo, sin modificar | Es el enfoque "básico" que el proyecto quiere superar. **Es el baseline real y difícil de batir** | Mezcla todos los atributos; no permite consultar por uno solo |
| **Candidato 1: proyecciones lineales** | Una matriz de proyección por atributo, entrenada con contrastive loss | Interpretable, rápida de entrenar, reproducible. Primera solución desacoplada | Puede no capturar relaciones no lineales entre embedding y atributo |
| **Candidato 2: cabezas MLP** | Pequeña red (2-3 capas) por atributo, sobre CLIP congelado | Comprueba si la no linealidad mejora el desacoplamiento respecto a la proyección lineal | Más riesgo de sobreajuste; menos interpretable; más coste |

### Justificación de la selección

Se plantean **dos candidatos y no más**, siguiendo el enunciado (no se valora la cantidad de algoritmos). La progresión es deliberada: del más simple e interpretable (proyección lineal) al más flexible (MLP), para responder empíricamente a la pregunta "¿la complejidad adicional aporta mejora real?". Si la proyección lineal ya iguala al MLP, se elige la lineal por interpretabilidad y coste — decisión coherente con el criterio del enunciado de que un modelo menos complejo puede ser preferible.

**El backbone CLIP permanece congelado en todos los casos.** No se hace fine-tuning: el coste en tiempo y datos no está justificado, y congelar el backbone hace que la comparación entre candidatos sea limpia (solo cambian las cabezas).

### Sobre la compatibilidad de outfits (nice-to-have)

El modelo de compatibilidad —qué prendas combinan entre sí, entrenado sobre Polyvore— **queda fuera del core**. Si se aborda, su baseline serían reglas de armonía cromática y coherencia de categoría, y su métrica el FITB accuracy. Se documenta aquí para trazabilidad, pero no forma parte de la evaluación formal de esta entrega.

---

## 4. Datos de entrada del análisis y los modelos

### Entradas del core

| Entrada | Descripción | Granularidad / tipo | Uso en el modelo |
|---|---|---|---|
| `garment_attributes` | Prendas de DeepFashion con atributos etiquetados | Una fila por (prenda, atributo); booleano | **Señal de supervisión** para entrenar las cabezas |
| `garments.embedding` | Embedding CLIP de cada prenda | Vector de 512 dim | **Entrada** de las cabezas y del baseline |
| `garments.emb_corte/color/textura` | Proyecciones entrenadas | Vector de 128 dim | **Salida** del modelo; sobre lo que se evalúa |
| `garments` (source=wardrobe) | Armario real fotografiado | Una fila por prenda; imagen + categoría | **Conjunto de test out-of-distribution** |

### Granularidad y claves

- Unidad de análisis del entrenamiento: **la prenda individual** (`garment_id` / `train_item_id`).
- No hay fecha de referencia: **el problema no es temporal.** Ninguna variable depende del momento de generación. Esto se hace explícito porque el enunciado pregunta por disponibilidad temporal de las variables, y aquí la respuesta es que no aplica: un embedding de una prenda es estable en el tiempo.

### Variables de entrada principales y transformaciones

- **Imagen → embedding CLIP (512d):** transformación con el backbone congelado. Se precomputa una vez.
- **Etiquetas de atributo:** se filtran a los ~250 más frecuentes, se agrupan en corte/color/textura/patrón según el análisis de §2, y se usan como señal contrastiva (positivos), no como target binario (ver §6 y la justificación de calidad de la entrega 3).

### Variables que NO se utilizan, y por qué

| Variable | Motivo de exclusión |
|---|---|
| `talla`, `tejido` | Opcionales, con muchos nulos. No son entrada del core; podrían alimentar el recomendador (nice-to-have) |
| `altura_cm`, `peso_kg` | Solo para reglas de proporción (nice-to-have). Fuera del core. Además, riesgo ético documentado |
| Atributos con frecuencia < umbral | Señal insuficiente; introducirían ruido |
| Imágenes de catálogo comercial | Excluidas del core por decisión de alcance y restricciones legales |
| Metadatos temporales (`created_at`) | No hay señal temporal que modelar |

### Qué información está disponible en el momento de uso

En el momento de generar un resultado (una búsqueda), el sistema dispone de: la imagen de consulta y el índice de embeddings ya calculado. No usa ninguna información que no estaría disponible en producción. **No hay riesgo de fuga temporal**, porque no hay dimensión temporal (ver §8).

---

## 5. Datos de salida y forma de consumo

### Qué produce el sistema

Dada una imagen de consulta y un atributo objetivo, la salida es un **ranking de prendas** del índice, ordenadas por proximidad en el subespacio de ese atributo.

| Campo de salida | Descripción | Tipo | Uso posterior |
|---|---|---|---|
| `garment_id` | Identificador de la prenda recuperada | integer | Trazabilidad; unión con metadatos |
| `atributo_consulta` | Sobre qué atributo se busca (corte/color/textura) | categoría | Determina qué subespacio se usa |
| `rank` | Posición en el ranking | integer | Orden de presentación |
| `distancia` | Distancia en el subespacio del atributo | float | Confianza / corte de resultados |
| `explicacion` | En qué atributo se aproxima cada prenda | texto | Interpretación por el usuario (nice-to-have, vía LLM) |

### Granularidad y formato

- Granularidad de la salida: **una fila por prenda recuperada**, para una consulta dada.
- Formato: resultado de una consulta SQL sobre PostgreSQL/pgvector (`ORDER BY emb_atributo <-> query LIMIT k`). En el MVP se expone vía la interfaz; el resultado bruto es una tabla.

### Cómo lo usa el usuario y qué decisión toma

El usuario ve las prendas de su armario ordenadas por parecido a la referencia en la dimensión que le interesa, y decide cuál usar. La explicación ("esta se parece en el corte, aunque el color difiere") le permite entender por qué aparece cada una — que es justamente el valor de desacoplar los atributos.

### Información adicional necesaria

Es importante mostrar **en qué atributo** se produce el parecido, no solo la lista. Un ranking sin esa información sería indistinguible de una búsqueda plana a ojos del usuario. La distancia por atributo es lo que hace el resultado interpretable.

---

## 6. Estrategia para diseñar y seleccionar el modelo

### Preparación del dataset de modelado

1. Precomputar embeddings CLIP de todo el corpus (una vez).
2. Filtrar atributos a los ~250 más frecuentes; agruparlos en corte/color/textura/patrón según el análisis de co-ocurrencia (§2).
3. Construir pares/tripletas contrastivas: prendas que comparten un atributo son positivos en el subespacio de ese atributo.
4. Aplicar el split disjoint (ver §7) **antes** de construir las tripletas, para que ninguna prenda de test aparezca en el entrenamiento.

### Definición de la salida a generar

No hay variable objetivo en el sentido clásico (no es clasificación). El objetivo del entrenamiento es que **la distancia en el subespacio de un atributo se corresponda con la similitud real en ese atributo**. La señal es contrastiva: acercar lo que comparte atributo, alejar lo que no.

### Preprocesamiento

- **Nulos:** una prenda sin cierto atributo etiquetado no genera negativo para ese atributo (etiquetado no exhaustivo; ver entrega 3 §7.2). No se imputan atributos.
- **Normalización:** los embeddings se normalizan a norma unitaria (estándar en similitud coseno).
- **Escalado / codificación:** no aplica en el sentido tabular; la entrada ya es un vector denso.
- **Aumentación (para el domain gap):** sobre las imágenes de evaluación de armario, se estudian transformaciones (fondo, iluminación, oclusión) para acercar la distribución de catálogo a la real.

### Criterios de comparación

Siguiendo el enunciado, no se selecciona por métrica única:

| Criterio | Peso en la decisión |
|---|---|
| Mejora en retrieval por atributo frente a CLIP plano | Principal |
| Estabilidad entre atributos (que no mejore corte a costa de empeorar color) | Alto |
| Interpretabilidad | Medio (favorece la proyección lineal) |
| Coste computacional | Bajo-medio |
| Comportamiento sobre armario real | Alto |

### Regla de decisión final

Un candidato se selecciona si cumple **todas** estas condiciones:

1. Supera a CLIP plano en la métrica de retrieval por atributo, de forma consistente en al menos corte y textura (los atributos donde se espera margen — H1).
2. No degrada significativamente ningún atributo respecto al baseline.
3. Mantiene la mejora sobre el conjunto de armario real, aunque sea atenuada.

Entre candidatos que cumplan las tres, se elige el **más simple e interpretable** (previsiblemente la proyección lineal), no el de métrica marginalmente superior.

---

## 7. Estrategia de validación y evaluación

Esta sección incorpora las dos correcciones del profesor: split riguroso sin contaminación, y **valoración humana** además de las métricas automáticas.

### Separación de datos

**Split disjoint a nivel de prenda.** Ninguna prenda individual aparece a la vez en entrenamiento y test. Este es el punto crítico: un split aleatorio ingenuo permitiría que variantes casi idénticas de una prenda cayeran en ambos lados, inflando el resultado. Polyvore proporciona una partición disjoint oficial; para DeepFashion se construye garantizando separación por prenda.

**No es un split temporal** porque no hay dimensión temporal. La separación relevante aquí es *por entidad* (prenda), no por tiempo.

**Conjunto de test out-of-distribution separado:** el armario real. Nunca se usa en entrenamiento ni en selección de modelo. Sirve para medir si el sistema generaliza de catálogo a fotos reales.

### Cómo se evita la contaminación

- Split disjoint por prenda (arriba).
- Deduplicación por similitud antes del split: los casi-duplicados se agrupan y no se reparten entre train y test.
- El armario real se mantiene completamente aislado.
- No hay información futura que pueda filtrarse, al no haber eje temporal.

### Métricas

**Automáticas (retrieval por atributo):**

| Métrica | Qué mide | Por qué es adecuada |
|---|---|---|
| **Recall@k** | Cuántas prendas relevantes para el atributo aparecen en el top-k | Refleja la utilidad directa: ¿encuentro lo que busco entre los primeros? |
| **NDCG@k** | Calidad del orden del ranking | Penaliza colocar lo relevante en posiciones bajas |
| **mAP** | Precisión media a lo largo del ranking | Resumen global de la calidad de recuperación |

Todas se reportan **por atributo** (corte, color, textura) y **frente al baseline CLIP plano**. La comparación es el resultado, no el número absoluto.

**Valoración humana (coherencia y utilidad):**

Las métricas de retrieval no dicen si un resultado es *útil* a ojos de una persona. Se añade un protocolo de valoración humana, definido con precisión para que sea reproducible y no "preguntar a unos amigos":

- **Panel:** 3-5 evaluadores que no han participado en el desarrollo (para evitar el sesgo de juez y parte).
- **Muestra:** 20-30 consultas, cada una con los resultados del baseline y del modelo, **presentados de forma ciega** (el evaluador no sabe cuál es cuál).
- **Pregunta:** para cada resultado, "¿esta prenda se parece a la referencia en [atributo]?" en escala 1-5, y "¿el conjunto de resultados es coherente?".
- **Métrica derivada:** proporción de veces que el modelo se prefiere al baseline; acuerdo entre evaluadores (p. ej. alfa de Krippendorff o simple porcentaje de coincidencia).

**Plan B si no se reúne panel:** valoración individual del autor, declarada explícitamente como limitación por sesgo de evaluador único. Es una evaluación más débil, pero honesta si se reconoce. Se prioriza reunir el panel.

### Comparación con el baseline

Toda métrica automática se reporta como **par (baseline, modelo)** y su diferencia. La valoración humana se reporta como **preferencia relativa** en comparación ciega. En ningún caso se presenta un número del modelo sin su baseline al lado.

### Análisis de errores y por segmentos

- **Por atributo:** ¿mejora en corte pero no en color? Esperado y informativo.
- **Por categoría de prenda:** ¿funciona en camisas pero falla en calzado?
- **Catálogo vs. armario real:** cuantificar la caída de rendimiento (el domain gap en números).
- **Casos extremos:** prendas con atributos raros, fotos de armario especialmente malas.

### Resultado mínimo aceptable y plan si no se alcanza

| Elemento | Decisión prevista | Justificación |
|---|---|---|
| Separación de datos | Split disjoint por prenda + armario real aislado | Evita contaminación por casi-duplicados; reproduce el uso real |
| Métrica principal | Recall@k y NDCG@k por atributo, vs. baseline | Reflejan utilidad de la recuperación |
| Métrica complementaria | Preferencia humana en comparación ciega | Las métricas automáticas no capturan coherencia percibida |
| Baseline | CLIP plano (similitud coseno) | Es el enfoque "básico" que se quiere superar |
| Criterio de aceptación | Mejora consistente sobre CLIP plano en corte y textura, mantenida en armario real | Es la afirmación central del proyecto |

**Si ningún candidato supera al baseline:** es un **resultado válido**, no un fracaso. Significaría que CLIP ya codifica los atributos suficientemente bien y que el desacoplamiento explícito no aporta. Se reportaría con las ablations que expliquen por qué, y el proyecto pivotaría su aportación hacia el análisis del domain gap (que seguiría siendo un resultado propio) y hacia la construcción del sistema como integración. Esta salida está contemplada desde el diseño y no invalida el trabajo.

---

## 8. Riesgos y alternativas

### ¿La "variable objetivo" representa el fenómeno?

No hay variable objetivo clásica. La señal son las etiquetas de atributo de DeepFashion, y su representatividad tiene una limitación conocida: el etiquetado es **no exhaustivo** (la ausencia de una etiqueta no garantiza la ausencia del atributo). Por eso la pérdida es contrastiva sobre positivos y no binaria — la calidad del dato determina la función de pérdida, no al revés.

### ¿Riesgo de data leakage?

El riesgo real no es temporal (no hay tiempo), sino de **casi-duplicados repartidos entre train y test**. Se mitiga con deduplicación previa al split y split disjoint por prenda. Es el leakage específico de este tipo de problema, y está identificado.

### ¿Volumen, histórico y calidad suficientes?

- **Volumen:** suficiente. DeepFashion aporta cientos de miles de imágenes etiquetadas.
- **Histórico:** no aplica; el problema no es temporal.
- **Calidad:** el desequilibrio de atributos y el etiquetado ruidoso son los puntos débiles, ya mitigados (filtrado a los más frecuentes, pérdida contrastiva).

### ¿Desbalanceo, sesgos, segmentos con pocos datos?

- **Desbalanceo de atributos:** severo. Mitigado por filtrado y muestreo.
- **Sesgo de cobertura:** catálogo de origen indio; afecta a la percepción, no a la validez de la comparación baseline-modelo (ambos se evalúan sobre los mismos datos).
- **Segmentos con pocos datos:** atributos raros y ciertas categorías. Se reportan por separado en el análisis de errores en lugar de diluirse en la media.

### ¿Qué parte genera más incertidumbre?

**La agrupación de atributos en cabezas** (corte/color/textura). Toda la contribución depende de que esos grupos sean perceptualmente separables, y ahora mismo es una hipótesis (H2). Si los atributos no se agrupan limpiamente, las cabezas aprenden subespacios sin sentido claro y el desacoplamiento no funciona. No se sabrá hasta el primer resultado comparado con el baseline. **Es el riesgo número uno.**

### ¿Qué alternativa si el modelo no supera el baseline o no se valida?

Por orden:

1. **Si el desacoplamiento no mejora:** pivotar la aportación al análisis del domain gap catálogo↔armario, que es un resultado propio y medible, y presentar el sistema como integración de componentes existentes bien evaluada.
2. **Si DeepFashion no da señal utilizable:** etiquetar atributos con un VLM sobre el catálogo (supervisión sintética), asumiendo y documentando que se hereda el sesgo del etiquetador.
3. **Si no se reúne panel humano:** valoración individual declarada como limitación.
4. **Si el tiempo se agota:** el core (búsqueda por atributos + armario real) es defendible por sí solo, sin ninguno de los componentes nice-to-have.

El diseño está construido para que el proyecto tenga un resultado defendible incluso en el peor caso de cada riesgo. Esa es la consecuencia práctica de acotar el core con disciplina.
