# Resultados del modelado (pasos 4b–4d)

**Fecha:** 5 de septiembre de 2026
**Split de evaluación:** validación. **Test no se ha tocado.**
**Métrica principal:** NDCG@10. **Índice:** 22.421 imágenes. **Consultas:** 12.211
(9.941 sobre atributos SEEN, 2.270 sobre UNSEEN).

---

## Nota metodológica: por qué NDCG y no Recall@k

La primera lectura se hizo con Recall@10 y no medía nada. Con una mediana de
**143 relevantes por consulta** (p90 = 601, máx = 2.369), el Recall@k queda
acotado por `k / n_relevantes`: un recuperador **perfecto** sacaría 10/2.000 =
0,005 en las consultas de atributos frecuentes. Todas las condiciones caían en
esa banda y dejaban de distinguirse.

El techo medio de Recall@10 con un ranking perfecto sobre este índice es
**0,0889**, y las condiciones observadas estaban entre 0,0050 y 0,0063.

NDCG@k normaliza contra el ideal truncado a k (IDCG sobre `min(n_rel, k)`), así
que vale 1 cuando las k primeras son relevantes, tenga la consulta 40 relevantes
o 4.000. Es la métrica que discrimina en este montaje.

Recall@k se sigue reportando como secundaria, con esta limitación declarada.

---

## Resultados

### NDCG@10 por condición

| Condición | seen | unseen | global |
|---|---|---|---|
| 1 aleatorio | 0,0118 | 0,0112 | 0,0117 |
| 2 CLIP plano (512d) | 0,1010 | 0,1141 | 0,1034 |
| 3 CLIP + PCA 128d | 0,1028 | 0,1133 | 0,1048 |
| **4 proyección conjunta 128d** | **0,1226** | **0,1273** | **0,1235** |
| 4b conjunta MLP | 0,1195 | 0,1226 | 0,1201 |
| 5 proyecciones por atributo | 0,1223 | 0,1206 | 0,1220 |
| 5b por atributo MLP | 0,1142 | 0,1095 | 0,1133 |

---

## Lo que queda demostrado

**1. La supervisión contrastiva sobre CLIP congelado funciona.**
Proyección conjunta frente a CLIP plano: **+0,0217** en seen
(IC95 [+0,0184, +0,0249]) y **+0,0132** en unseen (IC95 [+0,0069, +0,0196]).
Ambos significativos. La mejora **generaliza a atributos nunca vistos**, que es
la afirmación fuerte.

**2. La mejora no viene de reducir dimensionalidad.**
El control PCA a 128d iguala a CLIP plano en las seis celdas grupo × partición
(ninguna diferencia relevante). Descarta la explicación alternativa obvia.

**3. El desacoplamiento por atributo NO aporta sobre una proyección conjunta.**
Cabezas por atributo frente a conjunta: empate en seen (−0,0003, IC cruza el
cero) y **peor en unseen** (−0,0067, IC95 [−0,0126, −0,0008]).

**4. La no linealidad empeora.**
El MLP pierde contra el lineal en ambas condiciones y ambas particiones. La
proyección lineal es a la vez la mejor y la más interpretable, que es el
criterio de desempate declarado en la entrega 4 §6.

---

## El contraste que decidía, y por qué falla

La única celda donde el desacoplamiento ganaba a la conjunta era **forma
(= corte) sobre atributos SEEN**: +0,0077 (IC95 [+0,0021, +0,0136]).

Sobre atributos **UNSEEN** del mismo grupo: **−0,0029, IC95 [−0,0132, +0,0076],
no significativo.**

La ventaja existe solo sobre los 29 atributos de forma con los que la cabeza se
entrenó, y desaparece sobre los 8 que no vio. La interpretación es directa: la
cabeza **memorizó esos atributos concretos en lugar de aprender la noción de
corte**. Si hubiera aprendido la dimensión, generalizaría.

Es exactamente el escenario que la partición SEEN/UNSEEN se diseñó para
detectar. Sin ella, el +0,0077 se habría reportado como éxito.

---

## Conclusión

**La hipótesis central del proyecto —que las proyecciones específicas por
atributo mejoran la recuperación frente a un embedding monolítico— queda
refutada con estos datos.**

Lo que sí queda establecido es más modesto y está bien medido: una proyección
supervisada de 128 dimensiones sobre CLIP congelado mejora la recuperación por
atributo de forma significativa y generalizable, y esa mejora no se explica ni
por la reducción de dimensiones ni por la capacidad del modelo.

No es un fracaso del trabajo: es un resultado negativo con seis condiciones, dos
controles, intervalos de confianza por bootstrap pareado y partición
SEEN/UNSEEN. La entrega 4 §8 lo contempla explícitamente como salida válida.

**Consecuencia de alcance:** la aportación principal se desplaza al análisis del
*domain gap* entre catálogo y armario real (entrega 4 §8, alternativa 1). El
armario deja de ser una tarea de fondo y pasa a la ruta crítica.

---

## Ablation de presupuesto de datos: objeción cerrada

La cabeza conjunta entrenaba con **94.488** anclas y las de grupo con 28.481
(forma), 28.027 (textura) y 44.978 (tejido). La objeción evidente al resultado
negativo era que las cabezas perdían por tener entre dos y tres veces menos
material, no por el desacoplamiento.

Se reentrenó la conjunta con exactamente **28.481** anclas, el presupuesto de la
cabeza más pequeña (`--presupuesto-datos 28481`).

| Condición | anclas | NDCG@10 seen | NDCG@10 unseen |
|---|---|---|---|
| conjunta | 94.488 | 0,1226 | 0,1273 |
| **conjunta con presupuesto** | **28.481** | **0,1188** | **0,1264** |
| por atributo | 28-45k | 0,1223 | 0,1206 |

Recortar el 70 % del material de entrenamiento cuesta **−0,0038** en seen y
**−0,0009** en unseen, este último ni siquiera significativo (IC95
[−0,0045, +0,0025]).

**Dos conclusiones.** La primera: la objeción del volumen de datos queda
cerrada — las cabezas no pierden por falta de material. La segunda, no buscada
pero informativa: **la tarea satura en torno a las 28.000 anclas**. Triplicar
los datos de entrenamiento no mejora el resultado, lo que sugiere que el límite
está en lo que un mapa lineal puede extraer del embedding congelado, no en la
cantidad de supervisión disponible.

### Comparación justa: cabezas frente a conjunta con el mismo material

Con ambas condiciones entrenadas sobre las mismas 28.481 anclas
(`--referencia 4_conjunta_p28k`):

| Corte | Diferencia | IC95 | Significativo |
|---|---|---|---|
| **seen** | **+0,0035** | [+0,0007, +0,0063] | **Sí** |
| unseen | −0,0058 | [−0,0115, +0,0001] | No |
| forma \| seen | +0,0088 | [+0,0030, +0,0149] | Sí |
| textura \| seen | +0,0108 | [+0,0048, +0,0168] | Sí |
| forma \| unseen | −0,0052 | [−0,0169, +0,0060] | No |
| textura \| unseen | +0,0029 | [−0,0105, +0,0169] | No |
| tejido \| seen | −0,0037 | [−0,0074, −0,0001] | Sí, peor |
| tejido \| unseen | −0,0111 | [−0,0185, −0,0038] | Sí, peor |

**Matiz sobre la ablation.** Frente a la conjunta con los 94.488 ejemplos, las
cabezas empataban en seen. Con el material igualado **ganan en seen**. El
presupuesto de datos sí afectaba a esa comparación: decir que la objeción quedaba
"muerta" era excesivo. Lo que no cambia es el resultado en unseen.

### Enunciado final del resultado

> El desacoplamiento por atributo mejora la recuperación **sobre el vocabulario
> de atributos con el que se entrenó** (+0,0035 NDCG@10 global; +0,0088 en corte
> y +0,0108 en textura, todos significativos frente a una proyección conjunta
> con el mismo presupuesto de datos), pero esa ventaja **no se transfiere a
> atributos nuevos del mismo grupo** (−0,0058 en unseen, IC95
> [−0,0115, +0,0001]).
>
> Las cabezas construyen subespacios especializados en atributos concretos, no
> en la dimensión perceptual que los agrupa. Es una mejora de
> **especialización**, no de **representación**.

La hipótesis original —que las proyecciones por atributo capturan la noción de
corte, textura o tejido y por tanto generalizan— **no se sostiene**. La versión
acotada que sí se sostiene es considerablemente más modesta.

En términos de producto: con un vocabulario de atributos cerrado y conocido, las
cabezas aportan un 3 % relativo. Con consultas por atributos arbitrarios, no
aportan. En ninguno de los dos casos justifican la complejidad de mantener tres
cabezas frente a una sola proyección.

### Evidencia acumulada

| Control | Qué descarta | Resultado |
|---|---|---|
| Aleatorio | Que las diferencias sean ruido | Todas las condiciones lo baten ~10x |
| PCA 128d | Que la mejora venga de reducir dimensiones | PCA ≈ CLIP plano |
| Presupuesto 28k | Que las cabezas perdieran por menos datos | La conjunta apenas cae |
| MLP | Que el límite fuera la linealidad del mapa | El MLP empeora en todo |
| SEEN / UNSEEN | Que se memoricen los atributos vistos | La ventaja en corte se evapora |

El resultado negativo se apoya en cinco controles, no en una sola comparación.

## Reproducción

    python src/entrenar_proyecciones.py --condicion conjunta
    python src/entrenar_proyecciones.py --condicion por_atributo
    python src/entrenar_proyecciones.py --condicion conjunta --mlp
    python src/entrenar_proyecciones.py --condicion por_atributo --mlp
    python src/evaluar_condiciones.py            # val por defecto
    python src/tabla_resultados.py               # ndcg@10

Configuración de cada corrida en `experiments/<condicion>/config.yaml`.
Métricas por consulta en `experiments/resultados_val/`.
