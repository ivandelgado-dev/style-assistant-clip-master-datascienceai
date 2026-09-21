# Resultados del EDA de atributos (paso 2)

**Fecha:** 31 de agosto de 2026
**Fuente:** DeepFashion, Category and Attribute Prediction, `Anno_coarse`
**Script:** `src/eda_atributos.py`
**Salidas:** `data/processed/{attrs_meta,attrs_long}.parquet`, `heldout.yaml`, `cooc_flags.csv`

> **Cómo leer este documento.** Las secciones 1-4 describen la corrida
> **sin filtrar**, que es la que hizo aflorar el problema del género de prenda.
> Los parámetros y números definitivos están en **Ejecución final**, al final.
> Se conserva la progresión a propósito: justifica por qué existe el filtro.

---

## Datos base

- 289.222 imágenes x 1.000 atributos.
- Valores en el fichero: solo `1` (0,332 %) y `-1` (99,668 %). El README documenta
  un `0` = *unknown* que **los anotadores no usaron nunca**.
- Media de 3,32 atributos positivos por imagen (mediana 3, máximo 21).
  **12.969 imágenes no tienen ningún atributo positivo** y no pueden generar ni
  consultas ni pares contrastivos.
- Tras filtrar a los 250 más frecuentes con umbral de 500 ocurrencias quedan
  786.758 positivos, el 82 % del total.

### Sobre el `-1` y la pérdida contrastiva

Que no exista el `0` **no** convierte el `-1` en un negativo verificado. Las
etiquetas de DeepFashion derivan de descripciones de producto de tiendas online:
un `-1` significa "esa palabra no aparecía en la descripción", no "un anotador
comprobó que la prenda no lo tiene". Una prenda descrita como *"floral blouse"*
recibe `floral=1` y `-1` en todo lo demás, incluido `sheer`, aunque sea
transparente.

Es una hipótesis de mundo cerrado sobre texto scrapeado. La entrega 3 §7.2 acierta
en la conclusión, pero el argumento correcto es este, no la existencia del `0`.
**Conviene corregirlo en la memoria**: es una pregunta fácil de tribunal.

---

## Hallazgo 1 — La cabeza de color no tiene supervisión

Los cinco tipos de atributo de DeepFashion son textura, tejido, forma, partes y
estilo. **No hay tipo cromático.**

Matiz: aparecen palabras de color (`red`, `pink`) clasificadas como **estilo**,
junto a `summer`, `classic`, `love`, `shopping` y `party`. No es una señal de
color utilizable, es ruido de descripciones de producto.

**Decisión: se suprime la cabeza de color.** No es una pérdida: H1 predice que
CLIP plano ya codifica bien el color, así que era la cabeza con menos margen. El
proyecto queda más afilado —ataca exactamente donde CLIP es débil— en vez de
prometer tres cabezas y defender dos.

Afecta a: `README.md` (tres menciones), entregas 2, 3 y 4, y el campo
`emb_color` del modelo de datos.

---

## Hallazgo 2 — DeepFashion es mayoritariamente ropa de mujer

**Es el hallazgo más importante y no estaba previsto en ninguna entrega.**

| Categoría | Imágenes | % |
|---|---|---|
| Dress | 72.158 | 24,95 % |
| Tee | 36.887 | 12,75 % |
| Blouse | 24.557 | 8,49 % |
| Shorts | 19.666 | 6,80 % |
| Tank | 15.429 | 5,33 % |
| Skirt | 14.773 | 5,11 % |

Un cuarto del corpus son vestidos. Sumando Blouse, Skirt, Romper, Jumpsuit,
Leggings y Kimono, la mayoría del corpus queda fuera del alcance del proyecto.

Se ve en los propios atributos. Los ocho de **forma** (= corte) más frecuentes son:

    maxi, shirt, fit, bodycon, crop, skater, mini, muscle

`maxi`, `bodycon`, `skater` y `mini` son siluetas de vestido y falda. **La cabeza
de corte —la contribución central— se estaría entrenando sobre un vocabulario que
no existe en el armario masculino sobre el que luego se evalúa.**

### Por qué importa para la evaluación, no solo para el alcance

El conjunto de test *out-of-distribution* es un armario masculino fotografiado con
móvil. Sin filtrar, la caída de rendimiento mezclaría **dos desplazamientos
distintos**: el cambio de dominio fotográfico (estudio -> móvil), que es el que el
proyecto quiere medir, y el cambio de género de prenda, que es un artefacto de no
haber filtrado. El *domain gap* dejaría de medir lo que dice medir.

### Decisión

Filtrar por categoría **antes** de calcular las frecuencias, no después: el
ranking de los 250 atributos más frecuentes cambia al filtrar, y con él la
partición SEEN/UNSEEN.

Categorías conservadas (~26 de 50), las compatibles con ropa de hombre:

- **Upper:** Anorak, Blazer, Bomber, Button-Down, Cardigan, Flannel, Henley,
  Hoodie, Jacket, Jersey, Parka, Peacoat, Sweater, Tank, Tee, Top, Turtleneck
- **Lower:** Chinos, Cutoffs, Jeans, Joggers, Shorts, Sweatpants, Sweatshorts, Trunks
- **Full:** Coat

Estimación: ~150.000 imágenes supervivientes, holgadamente dentro del rango de
30.000-100.000 que la entrega 2 declara necesario.

La corrida sin filtrar ya está hecha, así que la comparación filtrado / sin
filtrar sale gratis como ablation.

---

## Hallazgo 3 — H2 se sostiene, pero menos de lo que parece

Solapamiento de Jaccard dentro del grupo frente a entre grupos (percentil 99):

| Grupo | dentro | fuera | ratio |
|---|---|---|---|
| textura | 0,123 | 0,023 | 5,3x |
| tejido | 0,070 | 0,029 | 2,4x |
| forma | 0,043 | 0,030 | 1,4x |
| estilo | 0,037 | 0,025 | 1,5x |
| partes | 0,035 | 0,027 | 1,3x |

"Dentro" supera a "fuera" en los cinco grupos, así que **H2 no queda refutada**.
Pero hay dos avisos que van en la memoria:

**El 5,3x de textura está inflado por sinónimos.** El vocabulario contiene
`print` / `printed`, `stripe` / `striped`, `floral` / `floral print`: el mismo
concepto escrito dos veces, que co-ocurre consigo mismo por construcción y siempre
dentro del grupo. Parte del "dentro" es redundancia léxica, no estructura.

**Corte y partes están al borde del ruido** (1,3-1,4x). Y corte es justo donde el
proyecto espera ganar.

**Esto mide co-ocurrencia de ETIQUETAS, no separabilidad perceptual.** Que dos
atributos de corte no aparezcan juntos en las descripciones no impide que
compartan subespacio visual. La prueba real sigue siendo el retrieval del paso 4.

---

## Hallazgo 4 — `estilo` no merece cabeza

Sus atributos más frecuentes: `summer`, `classic`, `red`, `pink`, `love`, `rose`,
`shopping`, `party`. Es ruido de descripciones de producto, no una dimensión
perceptual. Se conserva en los datos, no genera cabeza.

---

## Partición SEEN / UNSEEN y sinónimos

48 atributos held-out sobre 250 conservados. **6 están comprometidos** por tener
un casi-sinónimo entre los SEEN:

| Held-out | Sinónimo en SEEN | Jaccard |
|---|---|---|
| terry | french terry | 0,84 |
| crew | crew neck | 0,67 |
| leopard | leopard print | 0,59 |
| fit | flare | 0,50 |
| paisley | paisley print | 0,42 |
| floral | floral print | 0,31 |

Textura es la peor parada: 3 de sus 8 held-out están comprometidos. Un held-out
con gemelo en entrenamiento hace el test casi trivial e infla el número UNSEEN,
que es precisamente el que sostiene la contribución.

**Pendiente:** volver a sortear los held-out excluyendo los que tengan sinónimo,
en vez de solo reportarlos. Es una enmienda al protocolo y se documenta como tal.

---

## Nota sobre un fallo corregido

La primera ejecución produjo resultados falsos: se ordenaba la tabla de atributos
por frecuencia y luego se indexaban las columnas de la matriz con posiciones del
DataFrame ya reordenado. Nombres y columnas desalineados.

No lanzaba ninguna excepción. Se detectó porque los "casi-sinónimos" eran
absurdos: `fit` ↔ `floral print` con Jaccard 0,82. Tras el arreglo salen
`terry` ↔ `french terry` y `crew` ↔ `crew neck`.

El script incorpora ahora una verificación que recuenta las frecuencias desde la
tabla larga y las compara con las de la matriz. Con el fallo reintroducido a
propósito, aborta. **Los `attrs_long.parquet` generados antes de este arreglo
tenían atributos mal asignados** y no deben reutilizarse.


---

# Ejecución final

    python src/eda_atributos.py --data-root data/raw/deepfashion \
        --anno-dir Anno_coarse --out data/processed --min-freq 300

## Parámetros congelados

| Parámetro | Valor | Justificación |
|---|---|---|
| Filtro de categoría | 29 de 50 (24 claras + 5 dudosas) | Alcance del proyecto; evita confundir domain gap con gender gap |
| `top_n` | 250 | Práctica establecida en la literatura sobre DeepFashion |
| `min_freq` | **300** | Sobre 289k imágenes, 500 era el 0,17 % del corpus. Sobre las 155k filtradas, el equivalente relativo son ~270. Se mantiene constante la barra **relativa**, no la absoluta; con 500 se perdían 6 atributos de `forma`, la cabeza insignia |
| `frac_unseen` | 0,20 | |
| `jaccard_flag` | 0,30 | Umbral de casi-sinónimo, para componentes y para el reporte |
| `seed` | 42 | |

## Corpus resultante

- **155.369 imágenes** de 289.222 (53,7 %), 29 de 50 categorías.
- Descartadas por volumen: Dress (72.158), Blouse (24.557), Skirt (14.773),
  Romper (7.408), Jumpsuit (6.153).
- 3,04 atributos positivos por imagen de media. 8.527 imágenes sin ninguno.
- **250 atributos conservados**, 391.279 positivos en `attrs_long.parquet`.

## Efecto del filtro sobre el vocabulario de corte

Es la validación de la decisión. Atributos de `forma` más frecuentes:

| | Top-8 |
|---|---|
| **Sin filtrar** | maxi, shirt, fit, bodycon, crop, skater, mini, muscle |
| **Filtrado** | shirt, muscle, crop, **skinny**, **boxy**, cropped, fit, **longline** |

Desaparecen `maxi`, `bodycon`, `skater` y `mini` —siluetas de vestido y falda— y
aparecen `skinny`, `boxy`, `longline`, `slim` y `oversized`. Es literalmente el
vocabulario del campo `corte` de la entrega 3 (`slim`, `regular`, `oversize`,
`relaxed`).

Mismo efecto en `partes`: entran `drawstring`, `hooded`, `zip`.

## Partición SEEN / UNSEEN definitiva

| Grupo | SEEN | UNSEEN | Cabeza |
|---|---|---|---|
| forma (= corte) | 29 | 8 | **Sí** |
| textura | 33 | 7 | **Sí** |
| tejido | 54 | 13 | **Sí** |
| partes | 38 | 8 | No (por decidir) |
| estilo | 48 | 12 | No (ruido) |

**Cero held-out comprometidos por sinónimos**, frente a 6 de 48 en la primera
corrida.

## Componentes de casi-sinónimos

El vocabulario de DeepFashion contiene el mismo concepto varias veces, a menudo
como fragmentos de una expresión: `['french', 'terry', 'french terry']`,
`['faux', 'leather', 'faux leather', 'fur', 'faux fur']`, `['cable', 'cable knit']`,
`['sleeve', 'long sleeve']`, `['floral', 'floral print']`.

Se agrupan en componentes conexas por Jaccard >= 0,30 y **cada componente se
reparte entero** a SEEN o a UNSEEN, con el mismo criterio que el `dup_group` de
prendas del protocolo §3: las unidades correlacionadas no cruzan el split.

Un componente puede además **cruzar grupos de atributo** (`palm` en textura,
`tree` en estilo). Como el reparto es por grupo, esos componentes se partían. Se
resuelve por el lado conservador: un componente partido pasa entero a SEEN.
Encoger el UNSEEN es aceptable; contaminarlo no, porque es el número que sostiene
la contribución.

## Enmienda al protocolo

`docs/protocolo_evaluacion.md` §2 decía que los casi-sinónimos se *reportarían
aparte*. Se sustituye por: **se agrupan en componentes y se reparten enteros**.
Reportar no arreglaba nada. Cambio hecho antes de ver ningún resultado de
retrieval, que es la condición que el propio protocolo pone para modificarse.

## Pendiente

- Reflejar la supresión de la cabeza de color en `README.md` y en las entregas.
- Decidir si `partes` recibe cabeza. Tiene 38 atributos utilizables y vocabulario
  relevante (`hooded`, `zip`, `pocket`, `v-neck`), pero H2 lo deja en 1,5x.
- Corrida de control sobre `Anno_fine` (26 atributos mejor etiquetados).
