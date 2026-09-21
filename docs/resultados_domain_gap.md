# Domain gap: catálogo frente a armario real

Estado: **cerrado**. Incluye la corrida única final sobre test.
18/09/2026. `src/domain_gap.py`, semilla 42.
Salidas en `experiments/domain_gap/` y `experiments/domain_gap_r85/`.

## 1. Qué se mide

Todo el entrenamiento y toda la evaluación se hicieron con fotografía de
catálogo (DeepFashion). El producto recibe fotos de móvil. Aquí se mide ese
salto con 118 prendas propias, 236 fotos (dos tomas por prenda), etiquetadas a
mano antes de ver ninguna salida del modelo.

Entran en la medición 112 prendas; quedan fuera 10 polos y 2 chalecos, sin
categoría equivalente en DeepFashion. Los análisis principales se restringen
además a los 7 grupos con ≥5 prendas: `abrigo` tiene UNA y su media no
significa nada.

## 2. Un fallo de diseño que invirtió el signo, y cómo se corrigió

La primera corrida dio una caída **negativa**: el armario recuperaba mejor que
el catálogo. Era el instrumento.

Las consultas de catálogo salían del propio índice y tenían que vetarse su
carpeta de producto para no recuperar sus propias fotos casi idénticas. La
mediana de una carpeta en el índice son **34 imágenes, todas de su misma
categoría por construcción**. Una consulta de catálogo competía con 34
candidatos correctos menos; una del armario, con ninguno menos.

**Corrección:** las consultas de catálogo salen ahora de otra partición. Como
los splits son disjuntos por carpeta (comprobado: 0 carpetas compartidas de
3.272), ninguna consulta tiene imágenes suyas en el índice — la misma situación
que el armario. El veto sobra y se elimina.

Se deja escrito porque el número equivocado era plausible y llegó a defenderse
durante media hora.

## 3. Suelo de ruido

Coseno entre las dos tomas de la misma prenda, contra pares de prendas
distintas del propio armario:

| | misma prenda (mediana) | distintas (p95) | margen |
|---|---|---|---|
| CLIP plano | 0,991 | 0,926 | +0,065 |
| proyección conjunta | 0,994 | 0,925 | +0,069 |
| cabeza forma | 0,995 | 0,951 | +0,044 |
| cabeza tejido | 0,994 | 0,932 | +0,062 |
| cabeza textura | 0,994 | 0,936 | +0,058 |

Dos lecturas:

1. **La identidad de la prenda es recuperable**: recolocarla y volver a
   fotografiarla mueve el vector menos de lo que separa a dos prendas
   distintas. Sin esto, nada de lo que sigue tendría escala.
2. **El armario está muy concentrado.** Dos prendas *distintas* dan 0,93 de
   coseno en el percentil 95. El fondo, la luz y el encuadre comunes pesan
   tanto que casi tapan las diferencias entre prendas. El margen útil es de
   apenas 0,05-0,07.

## 4. El dominio es trivialmente legible

Sonda lineal armario-vs-catálogo, emparejada por composición de categorías,
en validación cruzada:

| | AUC | nulo muestral | nulo de composición | control permutado |
|---|---|---|---|---|
| todas las representaciones | 0,999-1,000 | 0,45-0,49 | 0,57-0,64 | 0,51 |

AUC 1,000 frente a un nulo de composición de 0,64. Una sonda lineal separa las
dos fuentes sin equivocarse una sola vez, y no es un artefacto de que las
prendas difieran: el nulo construido con catálogo contra catálogo y
composición fina deliberadamente distinta se queda en 0,64.

El dominio ocupa direcciones propias del embedding.

## 5. Resultado principal (test)

Recuperación de categoría contra el índice de catálogo, en condiciones
simétricas (§2). Bootstrap pareado sobre consultas, macro por los 7 grupos con
≥5 prendas: 111 prendas del armario y 1.958 consultas de catálogo.

### 5.1 No se detecta caída entre dominios

Sobre test, **todas** las diferencias catálogo→armario tienen intervalos
solapados, tanto a nivel de grupo como de slot. Con 112 prendas y esta métrica,
**no hay evidencia de una caída de rendimiento medible al pasar de fotografía
de catálogo a fotografía de móvil.**

Es un resultado negativo, y hay que leerlo como lo que es: ausencia de
evidencia con este tamaño de muestra, no evidencia de ausencia. Los intervalos
del lado del armario son anchos (±0,04-0,09) porque son 111 consultas
repartidas en 7 grupos.

En validación sí salían tres caídas con intervalos separados. No sobrevivieron
a test. Por eso test se mira una vez y al final.

### 5.2 Lo que sí es robusto: ganancia sobre CLIP plano

Diferencia pareada frente a CLIP plano. `*` = el intervalo del 95% no contiene
el cero.

| | en catálogo | en el armario |
|---|---|---|
| proyección conjunta | +0,024 [+0,014, +0,035] * | +0,032 [−0,011, +0,076] |
| **cabeza forma** | +0,025 [+0,014, +0,035] * | **+0,090 [+0,054, +0,125] *** |
| **cabeza tejido** | +0,014 [+0,002, +0,026] * | **+0,065 [+0,019, +0,115] *** |
| cabeza textura | −0,049 [−0,061, −0,036] * | −0,043 [−0,090, +0,004] |

**Las cabezas de forma y tejido mantienen su ventaja fuera de dominio**, y su
estimación puntual es mayor en el armario que en catálogo. La proyección
conjunta no alcanza significación fuera de dominio.

Donde más ayuda la forma: `pantalon_largo` (0,338 → 0,610) y `camisa`
(0,181 → 0,406). Categorías definidas por la silueta, que una prenda estirada
conserva intacta aunque la cámara sea un móvil.

Advertencia: catálogo y armario son poblaciones de consulta distintas, con
dificultad distinta. Que la ganancia sea mayor en el armario **no** demuestra
que las cabezas funcionen mejor con fotos de móvil; demuestra que la ventaja
está presente y es significativa en los dos sitios.

### 5.3 Réplica sobre tres corridas

Columna del armario, ganancia sobre CLIP plano:

| | validación toma A | validación toma B | test |
|---|---|---|---|
| conjunta | +0,017 | +0,024 | +0,032 |
| forma | +0,072 * | +0,083 * | +0,090 * |
| tejido | +0,029 | +0,065 * | +0,065 * |
| textura | −0,100 * | −0,060 * | −0,043 |

Las tomas A y B son **fotografías distintas de las mismas prendas**: una réplica
con datos independientes, no una repetición del mismo cálculo.

`forma` es significativa en las tres. `tejido` en dos de tres y con el mismo
valor en las dos últimas. `conjunta` en ninguna. `textura` mantiene el signo
en las tres.

### 5.4 La cabeza de textura empeora en LOS DOS dominios

−0,049 en catálogo y −0,043 en el armario. No es un fallo de transferencia.

Explicación: **cada cabeza ayuda a recuperar categoría en proporción a cuánto
correlaciona su atributo con la categoría.** La forma prácticamente *es* la
categoría; el tejido correlaciona a medias; la textura es casi ortogonal —una
camisa de rayas y un pantalón de rayas comparten textura y no categoría. La
cabeza de textura hace bien aquello para lo que se entrenó, y por eso destruye
información de categoría.

**Limitación que esto obliga a declarar:** se está evaluando a tres cabezas en
una tarea para la que no fueron entrenadas. El armario solo tiene etiquetas de
categoría, así que es lo único medible fuera de dominio. La comparación
catálogo→armario *dentro de una misma representación* es válida; comparar
cabezas entre sí con esta métrica no lo es.

Vía para arreglarlo, no ejecutada: la columna `descripcion_libre` del armario
contiene notas de corte, manga, cuello y tejido escritas antes de ver
resultados. Mapearlas al vocabulario de atributos permitiría evaluar cada
cabeza en su propio atributo.

### 5.5 La medida es más ruidosa de lo que dicen sus intervalos

La ganancia de la conjunta sobre catálogo pasa de +0,063 (índice val) a +0,024
(índice test). Los intervalos de cada corrida no se solapan entre sí.

Los intervalos reportados capturan el muestreo de consultas, **no** la
variación entre particiones. Conclusiones que dependan de un valor exacto no se
sostienen; las que dependen del signo y de la significación, repetidas en tres
corridas, sí.

## 6. Ablation de recorte: hipótesis descartada

**Predicción escrita antes de ejecutarla:** si la cabeza de textura está
enganchada a la colcha de rayas del fondo, recortar el encuadre debería
recuperar parte de su pérdida.

**Resultado:** el recorte al 85% no tiene efecto medible en ninguna
representación. Todas alrededor de −0,020 con el intervalo cruzando el cero.

Predicción descartada. La explicación de §5.4 la sustituye y no necesita al
fondo para nada.

**Lo que esta ablation sí establece:** la diferencia entre dominios no la
explica el encuadre ni el margen exterior. **Lo que NO establece:** que el
fondo sea irrelevante. La colcha no está solo alrededor de la prenda, está
debajo y entre medias —entre las perneras, en el hueco de las mangas—, y
recortar no la quita.

## 7. Lo que queda confundido

La diferencia medida entre los dos dominios mezcla cuatro cosas, y solo una se
ha acotado:

| factor | estado |
|---|---|
| encuadre y margen | **descartado** como causa (§6) |
| dispositivo y luz | no separado |
| presentación: 89% del índice es prenda sobre cuerpo; el armario es plano | no separado |
| género de la prenda: el índice es 81-93% ropa de mujer | no separado, ver `resultados_anotacion_dominio.md` |

## 8. Corridas

| directorio | índice | consultas de catálogo | toma | uso |
|---|---|---|---|---|
| `domain_gap/` | val | test | A | exploratoria. **Su columna de catálogo no es válida**: sorteó una muestra distinta por representación, anterior al parche del generador fijo. |
| `domain_gap_r85/` | val | test | A | ablation de recorte |
| `domain_gap_tomab/` | val | test | B | réplica con fotos independientes |
| `domain_gap_test/` | **test** | val | A | **corrida final** |
