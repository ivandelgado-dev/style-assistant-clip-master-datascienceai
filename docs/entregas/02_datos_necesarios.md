# Entrega 2 — Selección de idea y análisis de datos necesarios

**Autor:** Iván Delgado
**Máster en Data Science y Desarrollo de IA — Evolve Academy**
**Fecha:** Julio 2026

---

## 1. Idea seleccionada

**Asistente de Estilo Personal con IA** (Idea 1 de la Entrega 1), con el alcance acotado a **ropa de hombre**.

### Párrafo 1 — Problema que resuelve

La mayoría de las personas tiene en su armario prendas suficientes para construir buenos conjuntos, pero carece del criterio o del tiempo para combinarlas. El problema no es la falta de ropa: es la falta de una función que, dado un armario concreto y una intención estética, devuelva combinaciones válidas. Las aplicaciones de moda existentes no resuelven esto porque operan sobre catálogos comerciales y no sobre el inventario real del usuario; su objetivo de negocio es vender prendas nuevas, no rentabilizar las existentes. El resultado es un patrón conocido: se compran prendas que replican lo que ya se tiene, se usa una fracción pequeña del armario, y se consume de forma impulsiva. El usuario afectado es cualquier persona con un armario de tamaño medio (50–200 prendas) que consume referencias estéticas en redes sociales y no sabe traducirlas a lo que posee. El valor de resolverlo es doble: reducción del consumo impulsivo y mejor aprovechamiento del inventario existente.

Existe además un problema secundario, subordinado al anterior: cuando la referencia estética no es alcanzable con el armario actual, el usuario necesita saber **qué prenda concreta le falta**, no una recomendación genérica de catálogo.

### Párrafo 2 — Solución planteada

El enfoque es de **recuperación y ranking multimodal**, no de generación. El sistema representa cada prenda —del armario del usuario y de un catálogo comercial— como un vector en un espacio de embeddings visual-textual compartido, obtenido mediante un modelo preentrenado tipo CLIP. Esto permite que una imagen de inspiración (una foto de un modelo, un influencer o un look de referencia) y una prenda del armario sean comparables directamente por distancia vectorial.

Sobre esa base se añade la contribución técnica central del proyecto: **proyecciones específicas por atributo**. Un embedding CLIP es un vector monolítico donde color, corte, textura y categoría están entrelazados y no pueden consultarse por separado. El proyecto entrena cabezas ligeras sobre el embedding congelado, una por atributo, de forma que sea posible formular consultas del tipo *"parécete al corte, ignora el color"*. Esto no es un refinamiento cosmético: es el requisito funcional que hace que el sistema sea útil cuando el usuario no posee la prenda exacta de la referencia pero sí una con la silueta correcta en otro color.

Sobre el espacio de embeddings se construye un pipeline de **retrieve-then-rerank**: recuperación barata de candidatos por categoría mediante búsqueda vectorial, seguida de un reranking que aplica reglas de compatibilidad (armonía cromática, coherencia de categorías, adecuación a la ocasión) y restricciones declaradas por el usuario. Un LLM se emplea en dos funciones periféricas y bien delimitadas: traducir peticiones en lenguaje natural a restricciones estructuradas, y etiquetar automáticamente atributos de las prendas al subirlas (patrón de extracción estructurada). **El LLM no decide el outfit**; esa decisión debe ser reproducible y evaluable.

### Párrafo 3 — MVP del proyecto final

Una aplicación web funcional que permita:

1. **Digitalizar un armario.** El usuario sube fotos de sus prendas. Un VLM propone automáticamente categoría, color y atributos (corte, tejido, manga); el usuario los corrige o completa. Talla, tejido y corte son campos declarables pero **opcionales**: el sistema funciona sin ellos y mejora con ellos.
2. **Generar el outfit del día** a partir del armario, filtrable por estilo (streetwear, casual, smart casual, formal) y por paleta cromática.
3. **Matching visual desde una imagen de referencia.** El usuario sube la foto de un look; el sistema devuelve varias propuestas construidas con prendas propias, ordenadas por similitud, explicitando en qué atributo se aproxima cada prenda (corte, color, textura) y en cuál no.
4. **Cierre de huecos con catálogo.** Cuando una posición del outfit no puede cubrirse con el armario, el sistema recupera del catálogo las prendas más próximas a la referencia.
5. **Explicación de la recomendación** generada por LLM sobre los factores que contribuyeron al ranking.

La aplicación se sirve mediante una API (FastAPI) y una interfaz de usuario, contenerizada y desplegada. Junto al producto, se entrega la **evaluación cuantitativa** de los componentes de modelado, que es donde reside el rigor del proyecto: retrieval por atributo frente a baseline de CLIP plano, con métricas de Recall@k y NDCG, y ablations sobre cada componente.

---

## 2. Datos necesarios

El proyecto necesita **cuatro conjuntos de datos con funciones distintas**. Es importante distinguirlos porque tienen requisitos de volumen, granularidad y calidad muy diferentes.

### 2.1 Corpus de prendas con atributos (entrenamiento)

Es el conjunto sobre el que se entrenan las proyecciones por atributo. Requiere que cada prenda tenga **etiquetas de atributo**, que son la señal de supervisión.

| Aspecto | Requisito |
|---|---|
| **Granularidad** | Una fila por prenda individual |
| **Campos imprescindibles** | Imagen de la prenda; categoría (camisa, pantalón, zapato...); atributos etiquetados (color, corte/silueta, textura/tejido, patrón) |
| **Campos deseables** | Descripción textual libre; segmentación de la prenda respecto al fondo; género del artículo |
| **Volumen razonable** | 30.000–100.000 prendas. Por debajo de ~20.000 las cabezas de atributo no tienen suficiente señal por clase; por encima de ~100.000 el coste de cómputo no compensa con embeddings congelados |
| **Profundidad histórica** | **No aplica.** No es una serie temporal. Un corte estático es suficiente |

**Observación sobre historicidad.** Este es un punto donde el proyecto se aparta del patrón habitual: no hay dimensión temporal en el problema. La compatibilidad entre una camisa y un pantalón no es una serie de eventos. Lo único que envejece es la *tendencia estética* del corpus, y eso es un sesgo a documentar (ver §5), no una carencia de histórico a subsanar.

### 2.2 Outfits curados por humanos (supervisión de compatibilidad)

Necesario para el módulo de compatibilidad: qué prendas casan entre sí. Este conocimiento **no puede derivarse de la similitud**: dos pantalones vaqueros casi idénticos están muy próximos en el espacio de embeddings y jamás se llevan juntos. La compatibilidad es una relación *complementaria*, no de semejanza, y requiere supervisión explícita.

| Aspecto | Requisito |
|---|---|
| **Granularidad** | Un outfit = conjunto de 2–8 prendas, con referencia a cada prenda individual |
| **Campos imprescindibles** | Composición del outfit; identificador y categoría de cada prenda; imagen de cada prenda |
| **Campos deseables** | Descripción textual; señal de calidad (likes, vistas) |
| **Volumen razonable** | 20.000–70.000 outfits |
| **Profundidad histórica** | No aplica |

### 2.3 Catálogo comercial (recuperación de prendas faltantes)

| Aspecto | Requisito |
|---|---|
| **Granularidad** | Una fila por producto (SKU) |
| **Campos imprescindibles** | Imagen; categoría; color; género |
| **Campos deseables** | Precio; talla disponible; **altura del modelo y talla que viste** (permite referencia de escala explícita); tejido; enlace al producto |
| **Volumen razonable** | 5.000–45.000 productos, filtrados a hombre |
| **Profundidad histórica** | No aplica. El catálogo es un corte actual por definición |

### 2.4 Armario real (evaluación *out-of-distribution*)

Este conjunto no sirve para entrenar. Sirve para **medir honestamente**.

Todos los datasets públicos disponibles son fotografías de catálogo: fondo blanco, iluminación de estudio, prenda planchada, encuadre canónico. Un armario real son fotos de móvil, prendas arrugadas, luz de habitación, fondos ruidosos. Un modelo evaluado únicamente sobre catálogo puede degradarse severamente sobre fotos reales, y ese **domain gap** es uno de los resultados más informativos que el proyecto puede reportar.

| Aspecto | Requisito |
|---|---|
| **Granularidad** | Una foto por prenda |
| **Campos imprescindibles** | Imagen; categoría |
| **Campos deseables** | Talla; tejido; corte (declarados por el usuario) |
| **Volumen razonable** | 80–150 prendas. Es un conjunto de test, no de entrenamiento |
| **Profundidad histórica** | No aplica |

### 2.5 Resumen: imprescindible frente a deseable

**Imprescindibles.** Imágenes de prendas con categoría y atributos etiquetados; outfits curados por humanos; un catálogo con imágenes y categoría; un armario real fotografiado para test.

**Deseables pero no obligatorios.** Descripciones textuales libres; máscaras de segmentación; altura del modelo y talla de referencia del catálogo; señales de popularidad de los outfits; metadatos de tejido y corte declarados por el usuario.

**Explícitamente descartados.** Datos que relacionen medidas corporales con adecuación de prendas. No existe ningún dataset público de este tipo, y su construcción sería un proyecto completo por sí misma. Ver §4 y §5.

---

## 3. Fuentes de datos previstas

### 3.1 Polyvore Outfits — compatibilidad

- **Enlace:** https://huggingface.co/datasets/mvasil/polyvore-outfits
- **Referencia original:** Vasileva & Plummer, *Learning Type-Aware Embeddings for Fashion Compatibility*, ECCV 2018
- **Contenido:** <cite index="12-1">68.306 outfits creados por usuarios reales, compuestos por 261.058 prendas heterogéneas, con metadatos de descripción, categoría y agrupación de outfits</cite>.
- **Formato:** Hugging Face Datasets (Parquet + imágenes)
- **Licencia:** <cite index="15-1">CC BY 4.0. Permite uso comercial y no comercial, redistribución y obras derivadas, con atribución al paper original</cite>. Es la licencia más permisiva de todas las fuentes contempladas.
- **Estabilidad:** Alta. Alojado en Hugging Face, mantenido por la autora original, ampliamente citado.
- **Ventaja decisiva:** proporciona dos particiones oficiales. <cite index="12-1">La partición *disjoint* a nivel de prenda, sin solapamiento de artículos individuales entre train y test, es la recomendada y evalúa la capacidad de generalizar a prendas nunca vistas</cite>. Se usará esta partición, pese a producir métricas más bajas, porque la partición no disjunta permite que un modelo memorice prendas concretas e infle artificialmente el resultado.
- **Números de referencia publicados:** en FITB sobre la partición disjunta, los métodos publicados van de ~55% (Type-Aware) a ~62% (aproximaciones basadas en LLM). Esto proporciona un marco de comparación externo para los resultados propios.
- **Riesgos:** Polyvore como plataforma cerró en 2018, por lo que los outfits reflejan tendencias de esa época. Es un sesgo de distribución que debe documentarse, no un defecto de calidad. Parte de las prendas son accesorios y complementos no relevantes para el alcance masculino del proyecto; requerirá filtrado por categoría.

### 3.2 DeepFashion — atributos de prenda

- **Enlace:** https://mmlab.ie.cuhk.edu.hk/projects/DeepFashion.html
- **Benchmark relevante:** *Category and Attribute Prediction*
- **Contenido:** <cite index="7-1">209.222 imágenes de entrenamiento, 40.000 de validación y 40.000 de test, con 1.000 clases de atributo. La práctica establecida por los autores es usar solo los 250 atributos más frecuentes</cite>. <cite index="5-1">Cada imagen está etiquetada con 50 categorías y anotada con 1.000 atributos, bounding box y landmarks</cite>.
- **Formato:** JPEG + ficheros de anotación en texto plano
- **Licencia:** <cite index="5-1">Disponible para investigación académica; cualquier uso comercial está prohibido</cite>.
- **Acceso:** <cite index="5-1">De los cuatro benchmarks derivados, solo *Attribute Prediction* está disponible sin solicitud de contraseña; los demás requieren firmar un acuerdo</cite>. Esto es favorable: es precisamente el benchmark que el proyecto necesita.
- **Estabilidad:** Alta. Mantenido por MMLab (CUHK), con actualizaciones documentadas hasta 2022.
- **Riesgos:** el desequilibrio entre clases de atributo es severo (algunos atributos aparecen en una fracción mínima de imágenes). Requerirá muestreo estratificado o ponderación de pérdida. La restricción a uso académico impide cualquier explotación comercial del artefacto entrenado, lo que debe reflejarse en la memoria.

### 3.3 Fashion Product Images — catálogo

- **Enlace:** https://www.kaggle.com/datasets/paramaggarwal/fashion-product-images-small
- **Contenido:** <cite index="24-1">44.000 productos con etiquetas de categoría e imágenes. Cada producto tiene un identificador y un mapeo en `styles.csv` con metadatos: género, categoría maestra, subcategoría, nombre descriptivo de color, temporada, año y uso previsto</cite>.
- **Formato:** CSV + JPEG. Existe una versión de alta resolución (2400×1600) para los casos en que la calidad de imagen sea limitante.
- **Licencia:** **No declarada explícitamente.** Este es un riesgo real y se documenta como tal: hay hilos abiertos en la propia página del dataset preguntando por la licencia y por su disponibilidad comercial, sin respuesta clara del autor. Para un proyecto académico sin redistribución de las imágenes el uso es defendible, pero **no puede asumirse que sea reutilizable comercialmente**.
- **Estabilidad:** Media. Publicado en 2019, sin actualizaciones desde entonces. Hay reportes de usuarios sobre ficheros ZIP corruptos en algunas descargas.
- **Riesgos:** los productos proceden de un catálogo indio, con distribución de estilo y tipología que no coincide exactamente con el mercado europeo. Para el MVP es suficiente; para producción, no.

### 3.4 Catálogo comercial real (Zara / Pull&Bear / Bershka) — índice secundario acotado

Las fichas de producto de estos catálogos contienen un dato que ningún dataset público ofrece: la **altura del modelo y la talla que viste**. Esto permite establecer una referencia de escala explícita frente a la altura declarada por el usuario, que es el único anclaje objetivo disponible para las restricciones de proporción (§4.2).

Adicionalmente, la funcionalidad de cierre de huecos del MVP —cuando una posición del outfit no puede cubrirse con el armario, el sistema recupera del catálogo y **enlaza al producto real**— requiere que al menos una parte del índice apunte a productos efectivamente comprables.

**Restricciones y decisión de diseño.** Estos catálogos no exponen API pública, sus términos de uso restringen la extracción automatizada, y sus imágenes de producto están protegidas por derechos de autor. La consecuencia operativa es que **las imágenes no pueden almacenarse ni redistribuirse** en un repositorio público.

Esto no impide construir el índice, porque el sistema no necesita las imágenes en reposo. Necesita **embeddings**. Un vector de 512 dimensiones no contiene la imagen ni permite reconstruirla: es una representación derivada. El pipeline adoptado es el siguiente:

1. **Recopilación manual acotada.** 150–300 productos de la sección de hombre, anotados individualmente. Volumen compatible con una sesión de trabajo, sin automatización de la extracción.
2. **Campos registrados.** URL del producto, URL de la imagen, categoría, color, tejido declarado, corte, altura del modelo, talla que viste.
3. **Cómputo de embeddings** sobre las imágenes accedidas públicamente, sin almacenamiento local persistente.
4. **Contenido del repositorio:** un CSV de metadatos, las URLs, y el fichero de embeddings. **Ninguna imagen de producto.**
5. **Comportamiento en la aplicación:** el matching opera sobre embeddings; la imagen se carga en el navegador del usuario directamente desde el servidor de origen, y el producto se enlaza a su ficha original.

Este patrón es equivalente al de cualquier agregador o comparador: se enlaza al producto, no se aloja. La documentación registrará fecha y alcance de la recopilación.

**Función dentro del proyecto.** Este índice es **secundario**. El entrenamiento y la evaluación cuantitativa se realizan íntegramente sobre §3.2 y §3.3. El índice comercial sirve para (a) calibrar las reglas de proporción con medidas reales, y (b) demostrar que el motor de recuperación opera sobre un catálogo comprable.

**Escalabilidad y trabajo futuro.** La cobertura del índice escala linealmente con su tamaño y **no requiere cambios en la arquitectura**: el motor de recuperación es agnóstico respecto al origen del catálogo, y opera igual sobre 300 productos que sobre el feed completo de un retailer. Esta separación es deliberada. La contribución técnica del proyecto es el motor de emparejamiento visual desacoplado por atributos, no la obtención del catálogo. La integración con el feed de producto de un retailer comercial —vía acuerdo o acceso a su catálogo estructurado— se declara como **trabajo futuro**, y constituye precisamente el argumento de valor del sistema frente a una integración basada en extracción de su web pública.

**Riesgo y alternativa.** Si esta recopilación no fuera viable, el proyecto funciona íntegramente sobre §3.3, perdiendo únicamente el anclaje de medidas reales y la demostración de enlace a producto comprable. Ninguna métrica de evaluación depende de este índice.

### 3.5 Armario propio — recolección primaria

Fotografía de 80–150 prendas propias con teléfono móvil, fondo neutro, luz natural, una prenda por imagen. Etiquetado manual de categoría; talla, tejido y corte declarados cuando se conozcan.

- **Formato:** JPEG + CSV de metadatos
- **Coste:** una sesión de trabajo
- **Riesgo:** volumen bajo. **No es un problema**, porque su función es servir de conjunto de test *out-of-distribution*, no de entrenamiento. Un test de 100 prendas es suficiente para detectar una degradación de rendimiento significativa.

---

## 4. Consideraciones de privacidad y protección de datos

### 4.1 Datos personales identificables

El proyecto **sí maneja datos personales**, y de dos tipos distintos con implicaciones diferentes:

**Fotografías del armario.** Aunque el objeto fotografiado sea una prenda, las imágenes pueden capturar incidentalmente el interior de una vivienda, y las prendas de una persona son en conjunto un identificador razonablemente distintivo. En el MVP el armario es el del autor, con consentimiento evidente. En un despliegue real, estas imágenes serían datos personales bajo el RGPD y requerirían base legal, política de retención y derecho de supresión.

**Altura, peso y complexión.** Aquí conviene ser preciso. La altura y el peso, por sí solos, no son categoría especial de datos bajo el artículo 9 del RGPD. Pero son datos que permiten inferir información sobre el estado físico de una persona, y su tratamiento merece cautela. La decisión de diseño adoptada es:

- Son **campos opcionales**, nunca obligatorios.
- Se usan **exclusivamente** para las reglas heurísticas de proporción, no como entrada de ningún modelo aprendido.
- El sistema es plenamente funcional sin ellos.
- No se almacenan en el repositorio ni se publican en ninguna forma.

Se descarta explícitamente pedir estos datos como requisito de uso. Un sistema que exige datos corporales que no necesita para funcionar tiene un defecto de diseño antes que un problema legal.

### 4.2 Riesgo ético: modelos que juzgan cuerpos

Esta es la consideración más importante de la sección, y se aborda de frente.

La idea original contemplaba que el sistema aprendiese qué prendas *favorecen* a cada tipo de cuerpo. El razonamiento subyacente es correcto: una talla M no cae igual sobre dos complexiones distintas, y la caída del tejido depende de la silueta. El problema no es que la premisa sea falsa. Es doble:

**No hay datos.** Entrenar tal modelo requeriría triplas de (prenda, medidas corporales, valoración de cómo sienta). No existe ningún corpus público de este tipo. Los datasets de *virtual try-on* (VITON, DressCode) aprenden a superponer una prenda sobre una foto, es decir, a mostrar **cómo se ve** — no a juzgar **si favorece**. Son problemas distintos.

**El riesgo ético es sustantivo.** Un modelo entrenado sobre valoraciones humanas de qué favorece a qué cuerpo aprendería, inevitablemente, los sesgos estéticos y corporales de quienes etiquetaron. El artefacto resultante sería un sistema automatizado que emite juicios sobre cuerpos. Eso no es un efecto secundario a mitigar: es lo que el modelo haría por construcción.

**Decisión adoptada.** El proyecto **no entrena ningún modelo de adecuación corporal**. La consideración de proporciones se implementa como un conjunto de **reglas heurísticas explícitas y auditables**, documentadas con su fuente, que el usuario puede desactivar. Se declaran como capa heurística y no como contribución de modelado. La alternativa —mostrar visualmente cómo queda la prenda mediante *virtual try-on* preentrenado, sin emitir juicio— se contempla como posible extensión de producto, no como componente evaluado.

### 4.3 Restricciones de uso de las fuentes

| Fuente | Licencia | Implicación |
|---|---|---|
| Polyvore Outfits | CC BY 4.0 | Uso libre con atribución. Sin restricción comercial |
| DeepFashion | Solo investigación académica | El modelo entrenado no puede explotarse comercialmente |
| Fashion Product Images | No declarada | Riesgo. Uso académico defendible; comercial, no asumible |
| Catálogo Inditex | Imágenes con copyright; ToS restringen extracción automatizada | Recopilación manual acotada. Se almacenan embeddings, metadatos y URLs. Ninguna imagen se aloja ni redistribuye |

**Consecuencia agregada:** el proyecto es un artefacto académico. Ninguna de las licencias implicadas permite un despliegue comercial del modelo entrenado tal cual. Esto se declara sin ambigüedad en la memoria y no se presenta como producto listo para comercializar.

### 4.4 Datos evitados deliberadamente

- Cualquier corpus que asocie apariencia corporal con juicio estético.
- Fotografías de personas reales en el armario del usuario (las imágenes son de prendas, no de la persona vistiéndolas).
- Redistribución de imágenes con derechos de autor en el repositorio público.

---

## 5. Viabilidad inicial del proyecto

### ¿Es viable obtener los datos?

**Sí, y con holgura para las piezas críticas.** Polyvore Outfits está en Hugging Face bajo CC BY 4.0, descargable sin fricción. DeepFashion — Attribute Prediction es accesible sin solicitud de contraseña, a diferencia de los otros tres benchmarks del mismo proyecto. Fashion Product Images está en Kaggle. El armario real depende únicamente del autor.

La única fuente con fricción de obtención es el catálogo comercial, que requiere recopilación manual y no admite redistribución de imágenes. Está clasificada como índice secundario precisamente por eso, y ninguna métrica del proyecto depende de ella.

### ¿Tienen calidad, granularidad e histórico suficientes?

**Calidad y granularidad: sí.** Ambos datasets principales son benchmarks establecidos con anotación manual y decenas de publicaciones evaluadas sobre ellos, lo que permite comparar los resultados propios contra números externos en lugar de contra una referencia inventada.

**Histórico: no aplica, y es importante decirlo.** El problema no tiene dimensión temporal. No hay una serie que modelar. La única componente temporal relevante es que Polyvore refleja tendencias de antes de 2018, lo cual constituye un **sesgo de distribución documentado**, no una carencia de profundidad histórica. Se reporta como limitación en la memoria.

### ¿Es desarrollable de forma realista durante el curso?

Sí, **con el alcance acotado que se ha definido**. Las decisiones que lo hacen viable:

- **Solo ropa de hombre.** No es únicamente una decisión de tiempo. El espacio de combinaciones masculino es más pequeño y está más convencionalizado, lo que hace las reglas de compatibilidad más aprendibles y más evaluables. Menos ruido sobre el mismo problema.
- **Backbone congelado.** No se entrena ningún modelo de visión desde cero. Se entrenan proyecciones ligeras sobre embeddings preextraídos. El coste es de horas de GPU, no de semanas.
- **Compatibilidad por reglas en el MVP**, con el modelo entrenado sobre Polyvore como extensión si el calendario lo permite.
- **Sin generación de imágenes.** Ningún GAN ni VAE produciendo ropa. Se descarta explícitamente y se justifica en la memoria: la evaluación de imágenes generadas no es defendible con el tiempo disponible, y el problema real es de recuperación, no de generación.

### ¿Qué parte se percibe como más arriesgada?

Por orden decreciente de riesgo:

1. **Que las proyecciones por atributo no superen al baseline de CLIP plano.** Es el riesgo central, porque es la contribución del proyecto. CLIP ya codifica color y categoría razonablemente bien; el margen de mejora está en corte y textura, que es donde el desacoplamiento debería aportar. Si no aporta, el proyecto reporta un **resultado negativo bien medido**, con ablations que expliquen por qué. Esto es un resultado, no un fracaso, y así se presentará.

2. **El domain gap entre catálogo y armario real.** Es posible que el rendimiento se degrade severamente sobre fotos de móvil. Se mitiga con aumentación (fondos, iluminación, oclusión) y, si es necesario, con segmentación de la prenda respecto al fondo. Su medición es en sí misma un resultado del proyecto.

3. **Desequilibrio de atributos en DeepFashion.** Los atributos raros pueden no tener señal suficiente. Se mitiga restringiendo el entrenamiento a los atributos más frecuentes, siguiendo la práctica establecida en la literatura.

4. **Sesgo temporal de Polyvore.** Afecta a la percepción de actualidad de las recomendaciones, no a la validez de las métricas. Se documenta.

### ¿Qué alternativa hay si la fuente principal falla?

El diseño está deliberadamente desacoplado de cualquier fuente única.

- **Si DeepFashion resultara inaccesible:** Fashion Product Images incluye atributos de color, temporada y uso, más pobres pero utilizables. Alternativamente, un VLM puede etiquetar atributos sobre cualquier corpus de imágenes, generando supervisión sintética — con la salvedad, documentada, de que se estaría destilando el sesgo del VLM.
- **Si Polyvore resultara inaccesible:** el módulo de compatibilidad opera sobre reglas explícitas (armonía cromática, coherencia de categoría, formalidad). Es lo previsto para el MVP de todos modos; el modelo entrenado es la extensión, no la base.
- **Si Fashion Product Images resultara inaccesible o su licencia se aclarara desfavorablemente:** el subconjunto *In-shop Clothes Retrieval* de DeepFashion cumple la función de catálogo, con menor volumen.
- **Si la recopilación del catálogo comercial no fuera viable:** no afecta a ninguna métrica. El índice comercial es secundario por diseño, y su ausencia solo elimina el anclaje de medidas reales para las reglas de proporción y la demostración de enlace a producto comprable.

La pieza sin sustituto es el **armario real**, y depende únicamente de que el autor fotografíe su propia ropa.

---

## Referencias

- Vasileva, M. I., Plummer, B. A., Dusad, K., Rajpal, S., Kumar, R., Forsyth, D. (2018). *Learning Type-Aware Embeddings for Fashion Compatibility*. ECCV. — Polyvore Outfits, CC BY 4.0.
- Liu, Z., Luo, P., Qiu, S., Wang, X., Tang, X. (2016). *DeepFashion: Powering Robust Clothes Recognition and Retrieval with Rich Annotations*. CVPR.
- Han, X., Wu, Z., Jiang, Y.-G., Davis, L. S. (2017). *Learning Fashion Compatibility with Bidirectional LSTMs*. ACM MM.
- Radford, A. et al. (2021). *Learning Transferable Visual Models From Natural Language Supervision* (CLIP). ICML.
