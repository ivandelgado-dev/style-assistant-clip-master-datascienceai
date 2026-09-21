# Calibración de las bandas de confianza del frontal

16/09/2026. `src/calibrar_bandas.py`, split de validación, semilla 42.
Salidas en `experiments/calibracion_bandas/`.

## 1. Qué se calibra y por qué no es un porcentaje

La interfaz tiene que decirle al usuario cuánto fiarse de cada resultado. Lo
fácil sería mostrar "92% de coincidencia". Sería falso: el modelo produce
distancias coseno en un subespacio, no probabilidades, y nada las convierte en
probabilidades sin medirlo.

Lo que sí se puede afirmar es una frecuencia observada: *de los resultados que
el sistema coloca en esta banda, cuántos de cada 100 compartían el atributo
consultado con la referencia*. Eso es lo que se mide aquí.

## 2. Método

- Índice: 22.421 imágenes de validación. 12.211 consultas (imagen, atributo).
- Para cada consulta se guardan los 50 primeros resultados con su similitud y
  si comparten el atributo consultado. 610.550 pares en total.
- Los umbrales se fijan **por cuantil de la distribución de similitud, elegidos
  antes de mirar la precisión**: p99 para la banda alta, p90 para la banda
  "posible". Elegir el umbral viendo qué precisión sale sería elegir el que
  mejor queda. La curva completa precisión-umbral se guarda para que la elección
  sea auditable.
- Un umbral por grupo de atributo: cada cabeza vive en su subespacio y un 0,98
  en textura no significa lo mismo que un 0,98 en corte.
- Sobre validación, nunca sobre test. Calibrar un elemento de interfaz no
  justifica gastar la única mirada a test.

## 3. Resultado — proyección conjunta ("parecido general", la pantalla principal)

| banda | umbral | comparten el atributo |
|---|---|---|
| alta (p99) | ≥ 0,973 | **26 de cada 100** |
| posible (p90) | ≥ 0,955 | 15 de cada 100 |
| cualquier resultado del top-50 | — | 7 de cada 100 |

Factor 3,5 sobre la tasa base. Las bandas separan.

**No dependen de haber memorizado el atributo.** En la banda alta: 25,8 de cada
100 en atributos vistos durante el entrenamiento, 24,4 en atributos no vistos.
La diferencia es despreciable, y eso es lo que autoriza a enseñar la banda en
producción, donde los atributos del usuario no son los del entrenamiento.

Por grupo (proyección conjunta), banda alta: textura 32, tejido 29, forma 28,
partes 20, estilo 15.

## 4. Cabezas por atributo frente a proyección conjunta

**Los agregados publicados no son comparables entre sí.** El de la conjunta
cubre los cinco grupos, incluidos `estilo` (15) y `partes` (20), que las cabezas
por atributo ni siquiera tienen. Leído sin cuidado, `por_atributo` parece ganar
28 a 26; es un artefacto de agregar poblaciones distintas.

Restringiendo la conjunta a los tres grupos con cabeza propia, sobre las mismas
consultas y los mismos 351.450 pares:

| | banda alta | banda posible | base |
|---|---|---|---|
| proyección conjunta | 29,5 | 18,0 | 8,7 |
| cabezas por atributo | 27,9 | 18,5 | 9,0 |

Por grupo, banda alta: forma 28,4 vs 25,7 · tejido 28,8 vs 28,6 · textura 32,5
vs 27,9. La conjunta iguala o gana en los tres.

**Lectura correcta, y no es "la conjunta gana".** Son 1,6 puntos en el agregado
y aquí no se han calculado intervalos de confianza. Lo que sostiene esta medida
es lo mismo que sostenía el NDCG con bootstrap pareado en
`resultados_modelado.md`: **el desacoplamiento por atributo no aporta.** Dos
métricas distintas, construidas de forma independiente, apuntando al mismo
sitio. Eso es lo que vale, no el signo de la diferencia.

## 5. Consecuencia de producto

**El rótulo "coincidencia clara" se retira.** 26 de cada 100 es 1 de cada 4.
Llamar a eso una coincidencia clara sería exactamente la mentira que el diseño
decía evitar. La banda pasa a llamarse "mayor proximidad", y la cifra aparece en
la pantalla junto a la tasa base, para que el usuario pueda leer el 3,5× y no
solo el 26%.

## 6. Limitación de la métrica

"Compartir el atributo etiquetado" es un criterio duro. El etiquetado de
DeepFashion es incompleto: una prenda de rayas puede no llevar la etiqueta
`striped`. Un resultado visualmente correcto cuenta como fallo si le falta la
etiqueta.

Por tanto **26 de cada 100 es una cota inferior** de lo que el usuario percibiría
como acierto. No se corrige al alza —no hay forma de estimar cuánto falta sin
reanotar DeepFashion— y no se usa como excusa para inflar la cifra de la
pantalla. Se declara y la pantalla muestra el número medido.

## 7. Nota de reproducibilidad

La primera versión del script escribía las salidas sin el nombre del experimento
en el fichero. La corrida de `conjunta` machacó la de `por_atributo` en
silencio. Corregido: las salidas son `bandas_<experimento>_<split>.yaml` y
equivalentes. Ambas corridas se relanzaron con el script corregido.
Los tres ficheros de la corrida machacada están en `_obsoleto/`: no se borran
—el repositorio no pierde nada en silencio— pero no son de fiar porque no se
sabe con certeza qué experimento los escribió.
