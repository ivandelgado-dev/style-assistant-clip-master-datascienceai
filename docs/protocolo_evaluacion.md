# Protocolo de evaluación y split

**Fecha de congelación:** 31 de agosto de 2026
**Estado:** decidido antes de ver ningún resultado.

> Este documento se fija **antes** de entrenar. Si después se cambia el valor de
> k, la definición de relevancia o la partición de atributos porque "así sale
> mejor", eso es *p-hacking* y es una pregunta que el tribunal puede hacer.
> Se puede cambiar, pero se cambia documentando qué y por qué, y se versiona.

---

## 1. Definición de consulta y de relevancia

**Consulta** = el par `(imagen q, atributo concreto t)`, donde `q` tiene `t`
etiquetado y `t` pertenece al grupo de atributos `a` (corte, textura, ...).

**Relevante** = todo ítem del índice etiquetado con **ese mismo atributo `t`**.

Se descarta la definición alternativa "comparte al menos un atributo del grupo
`a`". Motivos:

- Es interpretable: se puede reportar el rendimiento por atributo individual y
  detectar en cuáles falla, en lugar de una media que lo esconde.
- Evita que los atributos muy frecuentes dominen el cálculo.
- Es la que corresponde al caso de uso real: *"parécete a esto en el corte"* es
  una consulta sobre una silueta concreta, no sobre la categoría "corte".

**Sesgo conocido y asumido.** El etiquetado de DeepFashion no es exhaustivo: la
ausencia de `t` no garantiza que la prenda no lo tenga. Por tanto el conjunto de
"no relevantes" contiene falsos negativos y **el Recall@k absoluto está sesgado a
la baja**.

Consecuencia que hay que escribir en la memoria sin rodeos: los valores absolutos
de este protocolo **no son comparables con los publicados en la literatura**.
Solo son comparables las **diferencias entre condiciones**, porque todas se
evalúan sobre el mismo protocolo sesgado y el sesgo las afecta por igual.

---

## 2. Partición de atributos: SEEN / UNSEEN

Esta es la decisión que evita que la métrica se muerda la cola.

Si el atributo sobre el que se evalúa es el mismo que se usó para formar las
tripletas contrastivas, la cabeza fue optimizada directamente contra ese criterio
y CLIP plano no. La comparación estaría sesgada por construcción.

Por tanto, dentro de **cada grupo** de atributos:

| Partición | % objetivo | Uso |
|---|---|---|
| **SEEN** | ~80 % | Entran en las tripletas de entrenamiento. Se evalúa también sobre ellos |
| **UNSEEN** (held-out) | ~20 % | **Nunca** aparecen en ninguna tripleta. Solo evaluación |

**Cómo se lee cada número:**

- Métrica sobre SEEN -> mide *"la cabeza aprendió lo que le enseñamos"*.
  Es el número optimista. Se reporta, pero no es la afirmación del proyecto.
- Métrica sobre UNSEEN -> mide si el subespacio de "corte" captura la noción de
  corte **en general**, o si solo memorizó los atributos concretos del
  entrenamiento. **Este es el número que sostiene la contribución.**

**Detalle de implementación.** Un atributo held-out no puede usarse como señal
positiva ni negativa. Como la pérdida es contrastiva sobre positivos, basta con
**no formar pares por él**. Las imágenes que tienen a la vez atributos SEEN y
UNSEEN **no se eliminan**: se usan por sus etiquetas SEEN. Se conserva el dato.

**Cómo elegir los UNSEEN.** Estratificando por frecuencia, no al azar puro: hacen
falta held-out frecuentes y raros. Y hay que mirar la matriz de co-ocurrencia
antes de fijarlos: si un held-out tiene un casi-sinónimo entre los SEEN
(`oversize` held-out con `loose` en entrenamiento), la cabeza lo aprende
indirectamente y el test es más fácil de lo que parece. No es *leakage* —
generalizar por correlación semántica es justo lo que se quiere medir — pero esos
casos se **reportan aparte**.

---

## 3. Split de prendas

Independiente y ortogonal al split de atributos.

- **Disjoint a nivel de prenda**: train / val / test. Ninguna prenda individual
  aparece en dos particiones.
- **El índice de recuperación en evaluación se construye solo con prendas de
  test.** Si contuviera prendas de train, el modelo tendría ventaja sobre ítems
  ya vistos.
- Las consultas también salen de test. La propia consulta se excluye de su
  ranking.

### Casi-duplicados

Es el *leakage* específico de este problema, y va **antes** del split.

1. Agrupar por similitud coseno sobre **CLIP plano** dentro de la misma
   categoría. Umbral inicial ~0,98, calibrado mirando pares a mano (media hora,
   no más).
2. Cada `dup_group` va **entero** a un solo lado del split.
3. En evaluación, **un solo representante por grupo en el índice**. Si no, el
   top-k se satura con variantes de la misma prenda y el Recall@k no lo detecta.

Que la deduplicación se haga con CLIP plano es correcto y además conveniente: es
lo único disponible antes de entrenar, y al ser idéntica para todas las
condiciones no favorece a ninguna.

---

## 4. Condiciones a comparar

Esto es el núcleo del diseño experimental. Con solo *aleatorio* y *CLIP plano* no
se puede distinguir **"desacoplar por atributo ayuda"** de **"cualquier proyección
supervisada sobre moda ayuda"**. Cualquier cabeza entrenada bate a CLIP
*zero-shot*.

| # | Condición | Qué controla |
|---|---|---|
| 1 | Aleatorio estratificado por categoría | Suelo absoluto |
| 2 | CLIP plano, 512d, coseno | Baseline principal: el enfoque "básico" |
| 3 | CLIP reducido a 128d (PCA ajustado **en train**) | Dimensionalidad — descarta que la mejora venga de reducir dimensiones |
| 4 | **Proyección conjunta 128d**, misma pérdida contrastiva sobre *todos* los atributos juntos | **Supervisión** — descarta que la mejora venga solo de adaptar CLIP al dominio |
| 5 | **Proyecciones por atributo 128d** | La contribución del proyecto |
| 6 | MLP por atributo *(opcional, si sobra tiempo)* | Si la no linealidad aporta |

> **La afirmación del proyecto solo se sostiene si 5 supera a 4.**
> Que 5 supere a 2 no demuestra nada por sí solo.

La condición 4 es el mismo código de entrenamiento con una cabeza en lugar de
tres. Cuesta horas, no días, y es lo que convierte el resultado en defendible.

---

## 5. Métricas y significancia

- **Recall@k** con k en {5, 10, 20}. Se reporta **k = 10** como principal.
- **NDCG@10**.
- **mAP**.

Todo desglosado **por atributo individual**, agregado por grupo, y separando
SEEN de UNSEEN. Nunca una métrica del modelo sin su baseline al lado.

**Comparación pareada.** Todas las condiciones se evalúan sobre **exactamente el
mismo conjunto de consultas**. La métrica se calcula por consulta y se compara la
**distribución de las diferencias**, no dos medias sueltas.

**Significancia.** Bootstrap sobre consultas (10.000 remuestreos), intervalo de
confianza del 95 % de la diferencia pareada. Es lo estándar en *information
retrieval* y es lo que permite decir "mejora" en lugar de "sale un poco más alto".

Semillas fijadas y registradas en el YAML de cada corrida.

---

## 6. Evaluación *out-of-distribution* sobre el armario real

Dos preguntas distintas, que no se mezclan:

**(a) Magnitud del domain gap.** Descriptiva: distribución de distancias entre
embeddings de catálogo y embeddings de armario, y visualización 2D. **No requiere
etiquetas.** Es un resultado propio del proyecto y sobrevive aunque la
contribución principal no gane.

**(b) Retrieval sobre armario.** Consulta = foto de armario, índice = armario.
Requiere etiquetar los atributos del armario con **el mismo vocabulario** que
DeepFashion, en lo que sea aplicable.

**Aviso que conviene tener asumido de antemano:** con ~150 prendas y unos pocos
relevantes por consulta, el Recall@k va a ser muy ruidoso y los intervalos de
confianza van a salir anchos. Es probable que la diferencia entre condiciones no
sea significativa sobre el armario. **Eso también es un resultado**, siempre que
se reporte con su intervalo y no como un número pelado. Ir al extremo alto del
rango de fotos (150) ayuda; no lo arregla.

Regla que no se salta: **el armario se etiqueta antes de ver ninguna salida del
modelo**, con la taxonomía ya congelada.

---

## 7. Lo que este documento no puede decidir todavía

Depende del EDA (paso 2 del plan):

- Cuántos atributos sobreviven al filtro de frecuencia, y por tanto cuántos
  held-out salen por grupo. El 80/20 es la proporción, no un número absoluto.
- Si la cabeza de color existe. DeepFashion clasifica sus atributos en textura /
  tejido / forma / partes / estilo — color no está entre ellos.
- El umbral definitivo de deduplicación.
