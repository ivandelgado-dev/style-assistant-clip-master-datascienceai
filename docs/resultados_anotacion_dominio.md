# Anotación manual del dominio de DeepFashion

Estado: parcial. 16/09/2026.
Datos y semillas en `experiments/anotacion_dominio/`.

## 1. Para qué

El armario real son 118 prendas de hombre fotografiadas planas sobre una
superficie. El índice contra el que se recuperan son imágenes de DeepFashion.
Antes de atribuir cualquier caída de rendimiento a "fotos de móvil" hay que
saber en qué se diferencian de verdad los dos conjuntos. DeepFashion no trae
metadato de presentación ni de género, así que se anota a mano.

## 2. Presentación (n = 100, muestra aleatoria del índice de test, semilla 42)

| | n | IC95 (Wilson) |
|---|---|---|
| prenda sobre una persona | 89 | [81, 94] |
| prenda plana, tipo producto | 7 | [3, 14] |
| colgada o maniquí | 4 | [2, 10] |

El 89% del índice son prendas puestas sobre un cuerpo. Las fotos del armario
son planas. La diferencia de presentación es, por tanto, casi total, y entra
dentro de cualquier medida de *domain gap* que no la controle.

## 3. Género aparente: resultado principal y problema de medición

El filtro del EDA seleccionó por NOMBRE de categoría (Tee, Sweater, Cardigan,
Jacket, Shorts, Jeans, Joggers…). Esos nombres existen en las dos secciones de
cualquier tienda, así que no filtran género. Los nombres de carpeta tampoco
sirven: de 3.272 carpetas, solo 6 contienen "men" o "women".

Anotando a ojo:

| pasada | hombre | % | IC95 |
|---|---|---|---|
| 1 (n=100, semilla 42) | 7 | 7,0 | [3,4 – 13,7] |
| 2 (n=210, semilla 2026) | 40 | 19,0 | [14,3 – 24,9] |

**Las dos pasadas no concuerdan, y la discrepancia es del anotador, no de la
muestra.** Estandarizando —aplicando las tasas por categoría de la pasada 2 a
la mezcla de categorías de la pasada 1, que cubre el 98% de esa mezcla— sale
17,2% frente al 7,0% observado. La composición no lo explica. La diferencia
más visible está en `Tee`: 8,3% en la primera pasada, 29,8% en la segunda.

Causa probable: **el género de una prenda no es observable en muchos casos.**
Una camiseta gris lisa sobre fondo blanco no tiene género. En la primera pasada
esos casos cayeron por defecto en "mujer" (el contexto dominante del catálogo);
en la segunda, en "hombre". El criterio no estaba escrito, y derivó.

### Lo que sí queda establecido

Las dos pasadas coinciden en lo que importa: **el corpus es abrumadoramente
ropa de mujer**, entre el 81% y el 93% según la pasada. Ninguna lectura
razonable de estos datos sostiene la afirmación "alcance: ropa de hombre" como
descripción del corpus de entrenamiento.

### Lo que no queda establecido

La proporción exacta de ropa de hombre. Está entre el 7% y el 19% y mis propias
etiquetas no son lo bastante consistentes para afinarlo más.

## 4. Corrección de criterio

Se sustituye la variable anotada. En vez del género de la PRENDA —no observable
en un porcentaje alto de casos— se anota el **género aparente de la persona que
la lleva**, con una categoría explícita `sin_persona` para el 11% restante.

Es un criterio reproducible: en el 89% de las imágenes hay una persona y su
presentación es mucho menos ambigua que la de la prenda. Y es además la
variable correcta para la descomposición que interesa: lo que separa las fotos
planas de hombre del índice es, en buena medida, que el índice muestra cuerpos
de mujer.

### Criterio, escrito antes de reanotar

- `hombre`: hay al menos una persona visible y su presentación es masculina.
- `mujer`: hay al menos una persona visible y su presentación es femenina.
- `sin_persona`: no hay nadie, o solo se ve una parte que no permite decidir
  (manos, piernas sueltas, un maniquí, un torso recortado).
- Si aparecen varias personas con presentación distinta, decide la que lleva la
  prenda de la categoría etiquetada. Si eso no se puede resolver, `sin_persona`.
- **No se juzga la prenda.** Una camiseta de corte masculino puesta sobre una
  mujer se anota `mujer`. La prenda no tiene género; la foto sí tiene, o no
  tiene, una persona.

Queda escrito aquí antes de mirar ninguna imagen de la reanotación, para que no
se pueda ajustar el criterio a lo que convenga.

### Cómo se etiqueta el índice entero

A mano no: son 21.883 imágenes. Se etiqueta con `src/etiquetar_genero.py`,
CLIP zero-shot sobre los tres ejes con *prompt ensembling* de cuatro frases por
clase.

No se entrena ninguna sonda sobre mis etiquetas, y es deliberado: mis etiquetas
ya demostraron deriva, y una sonda entrenada sobre ellas la repartiría por todo
el índice sin dejar rastro. El zero-shot es un procedimiento fijo que no usa mis
etiquetas para nada salvo para medirse contra ellas.

Sobre la circularidad de usar CLIP para etiquetar imágenes donde luego se evalúa
CLIP: es admisible porque la etiqueta **no es el juicio de relevancia** —ese lo
da la categoría de DeepFashion, anotada por humanos— sino una variable de
estratificación, y porque su tasa de acierto se mide contra anotación manual y
se reporta. No sería admisible si definiera el acierto.

Las etiquetas viejas se conservan en `anotacion.csv` y `anotacion2.csv` como
registro de la deriva; no se borran.

## 5. Consecuencias ya firmes

1. **El resultado de modelado no cambia.** La comparación entre CLIP plano,
   proyección conjunta y cabezas por atributo es internamente válida: las tres
   condiciones vieron exactamente los mismos datos. Lo que cambia es la frase
   que describe el resultado: es recuperación por atributo sobre DeepFashion, no
   sobre ropa de hombre.

2. **La afirmación de alcance hay que corregirla en la memoria.** El producto se
   plantea para ropa de hombre; el corpus de aprendizaje de atributos es
   mayoritariamente femenino. A favor: los atributos aprendidos —corte, textura,
   tejido— son en su mayoría neutros. *Rayas*, *denim*, *holgado* o *punto*
   significan lo mismo en las dos secciones. Es argumentable, pero hay que
   argumentarlo, no darlo por supuesto.

3. **El domain gap tiene cuatro componentes, no uno.** Dispositivo y luz, fondo,
   presentación (cuerpo frente a plano) y género de la prenda. Reportar la caída
   entera como "efecto de la fotografía de móvil" sería falso.

## 6. Limitación de esta anotación

Un solo anotador, sin revisión cruzada, sin segunda opinión. La deriva
documentada en §3 es prueba directa de que eso importa. Las conclusiones que
aquí se sostienen son las que aguantan ambas pasadas; las que dependen del
valor exacto, no se sostienen.

## 7. El etiquetado zero-shot falla (16/09)

`src/etiquetar_genero.py` etiquetó las 155.369 imágenes con CLIP zero-shot y
*prompt ensembling*. El resultado es inservible, medido contra las 100 imágenes
anotadas a mano:

| eje | acierto | baseline trivial |
|---|---|---|
| persona / sin persona, argmax crudo | 29% | 89% ("todo persona") |
| persona / sin persona, calibrado por clase | 66% | 89% |
| hombre / mujer, solo donde hay persona | 42% | 92% ("todo mujer") |

Pierde contra la clase mayoritaria en los dos ejes.

**Diagnóstico.** La similitud media con el corpus es 0,2584 para los prompts de
`sin_persona`, 0,2391 para `mujer` y 0,2189 para `hombre`. La diferencia de base
entre clases (~0,04) es mayor que la variación entre imágenes dentro de una
clase (~0,025), así que el argmax reportaba qué conjunto de frases tiene más
afinidad de base con fotografía de moda, no qué contiene la imagen. Calibrar
—z-score por clase sobre todo el corpus— elimina ese sesgo y sube de 29% a 66%,
todavía por debajo del baseline trivial.

Es un fallo conocido del zero-shot con cosenos sin calibrar. Se escribió el
script igualmente.

**Qué NO se concluye.** Que la información no esté en los embeddings. Lo que
falla es el alineamiento imagen-texto, no la representación visual. Una sonda
lineal supervisada sobre los embeddings de imagen es la alternativa natural
—*linear probe* por encima de *zero-shot* es el resultado habitual en la
literatura de CLIP— y requiere etiquetas manuales consistentes.

**Estado.** El procedimiento zero-shot queda descartado y documentado. El
parquet `genero_zeroshot.parquet` se conserva porque las tres columnas de
similitud son características utilizables por una sonda posterior, no porque su
columna `etiqueta` valga para algo. No vale.

## 8. Decisión: el eje de género se cierra aquí (16/09)

Se descarta seguir con una sonda supervisada de género. Motivo: coste frente a
beneficio a dos semanas de la entrega, con la memoria sin empezar.

**Lo que entra en la memoria, y está establecido:**

- El corpus de aprendizaje de atributos es entre el 81% y el 93% ropa de mujer,
  medido sobre 310 imágenes anotadas a mano en dos pasadas independientes.
- El 89% del índice son prendas sobre un cuerpo; las del armario son planas.
- La afirmación "alcance: ropa de hombre" describe el producto, no el corpus, y
  se corrige en consecuencia.
- El filtro por nombre de categoría no filtra género, y no hay metadato que lo
  permita: de 3.272 carpetas, 6 contienen "men" o "women".
- No existe alternativa pública: ningún otro benchmark ofrece el vocabulario
  fino de atributos de DeepFashion. Es una limitación del campo.
- Dos resultados negativos documentados: la deriva del anotador (§3) y el fallo
  del zero-shot (§7).

**Lo que queda sin medir, y se declara:**

La caída de rendimiento del catálogo al armario tiene cuatro componentes
—dispositivo y luz, fondo, presentación, género de la prenda— y se reporta sin
descomponer. La ablation de recorte (`--recorte` en `embeddings_clip.py`) acota
la contribución conjunta de fondo y encuadre; género y presentación quedan
enumerados como confusores, no cuantificados por separado.

**Si alguien lo retoma:** la vía es una sonda lineal sobre los embeddings de
imagen —no zero-shot— entrenada con anotación manual bajo el criterio de §4, y
validada sobre etiquetas retenidas. Las tres columnas de similitud de
`genero_zeroshot.parquet` sirven como características adicionales.
