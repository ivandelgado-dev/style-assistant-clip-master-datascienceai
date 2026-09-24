# Búsqueda foto con modelo → prenda: color y etiquetas de Gemini (23/09)

Script: `src/evaluar_busqueda.py`. Métricas y resultados por consulta en
`experiments/busqueda_modelo_producto/`. El protocolo y la regla de decisión
están escritos en el propio script, y se fijaron antes de ver ningún
resultado. Los umbrales de color se calibraron en el armario del autor, antes
de esta prueba (`experiments/color_primero/calibracion.json`).

## Datos

24 parejas de Bershka (8 de arriba, 8 de abajo, 8 de encima). Cada pareja es
la foto de un modelo con la prenda puesta y la foto de producto de la misma
prenda. La consulta es la foto del modelo, recortada como la recorta la
aplicación en modo «Una persona».

Hay dos galerías:

- **Limpia:** los 8 productos de la misma posición. Acertar por azar: 12,5 %.
- **Real:** los mismos 8 productos más las prendas del autor como
  distractores: 47 abajo, 78 arriba y 17 encima. Acertar por azar: 3,1 %.

Gemini: `gemini-3.5-flash-lite`, con 10 fotos por petición. Las etiquetas se
guardan en `data/etiquetas_cache.json` y todo se calcula sobre esa copia
congelada.

## Resultados

| método | limpia @1 | limpia @3 | real @1 | real @3 | real, peor rango |
|---|---|---|---|---|---|
| CLIP plano | 17/24 | 21/24 | 16/24 | 18/24 | 7 |
| actual (proyección conjunta) | 17/24 | 22/24 | 17/24 | 22/24 | 29 |
| color primero (píxeles) | 19/24 | 24/24 | 17/24 | 23/24 | 4 |
| etiquetas (Gemini) | 21/24 | 23/24 | 19/24 | 21/24 | 10 |

Comparación con «actual», prueba de signos:

- **Galería limpia:**
  - etiquetas: mejora en 6 consultas, empeora en 1 (p = 0,125)
  - color: mejora en 7, empeora en 4 (p = 0,55)
- **Galería real:**
  - etiquetas: mejora en 6, empeora en 3 (p = 0,51)
  - color: mejora en 6, empeora en 5 (p = 1,0)

## Decisión (regla escrita antes)

Un método entra si mejora el acierto@1 sin empeorar el acierto@3.

- **En la galería limpia entrarían los dos,** y ganaría etiquetas.
- **En la galería real no entra ninguno.** Etiquetas mejora el @1 (19 frente
  a 17), pero empeora el @3 (21 frente a 22). Color iguala el @1.
- **Ninguna mejora es significativa** con 24 parejas.

**Queda el orden actual.** La galería real es la situación de la cuenta del
autor, y la regla hay que cumplirla en ella. Elegir la galería que da mejor
resultado sería escoger el escenario a posteriori.

## Lo que sí se sostiene

1. **CLIP + proyección conjunta encuentra la prenda exacta entre fotos de
   dominio distinto** (modelo → producto): 17/24 la primera y 22/24 entre las
   tres primeras, frente a un 3 % por azar con la galería real. La proyección
   supera a CLIP plano en el top-3 con distractores: 22 frente a 18.
2. **El color por píxeles es el método más estable.** Nunca deja la prenda
   correcta por debajo del 4º puesto, y «actual» llega al 29º (arriba_02:
   camiseta crudo en luz de calle). No gana en el top-1.
3. **Gemini es fiable para lo estructural.** En las 118 prendas del autor,
   contra sus anotaciones a mano:
   - tipo: 105/118 (89 %)
   - manga: 25/27 (93 %)
   - prenda suelta sin persona: 118/118
   - persona detectada en las 24 fotos de modelo: 24/24

   Esto contrasta con el zero-shot de CLIP para persona / sin persona, que se
   quedó en el 66 %.
4. **Como criterio de orden, Gemini falla por el color bajo luz distinta.**
   Una camiseta azul marino fotografiada con modelo sale «negro»; un bermuda
   caqui, «verde». La penalización es estricta, así que un color mal leído
   hunde la prenda correcta detrás de prendas del armario del mismo color
   leído (abajo_07 cae del 1º al 10º). La corrección de color con la luz la
   comparten el método de píxeles y Gemini, y es el mismo salto de dominio del
   resto del trabajo.

## Consistencia de las etiquetas (test-retest)

`src/consistencia_etiquetas.py` vuelve a pedir las 24 fotos de producto sin
caché y compara campo a campo con lo guardado. El modelo ignora `temperature`,
así que no es determinista.

| campo | acuerdo |
|---|---|
| posición, manga, largo | 24/24 |
| tipo | 22/24 (sudadera de cremallera ↔ chaqueta) |
| color | 22/24 (verde ↔ verde oscuro: misma familia) |
| tejido | 22/24 |
| estampado | 18/24 (estampado ↔ logo) |

Salen idénticas 14 de las 24 fotos. El estampado es el campo menos estable,
y aun así entraba en la penalización. Se trata como anotación: se congela, y
su variabilidad queda medida y declarada.

## Qué queda en la aplicación

- **Orden por defecto:** el actual. `ORDEN_COLOR` y `ORDEN_ETIQUETAS` siguen
  en `False`.
- **Gemini, para lo que se ha medido fiable:**
  - proponer si hay persona y qué piezas lleva, en las preguntas de Buscar
  - proponer la categoría al subir una prenda
  - la caja «¿Algo distinto?»: ahí el usuario pide un cambio de forma
    explícita («manga larga»), y la manga se acierta en el 93 %

## Hipótesis para trabajo futuro (NO probadas aquí)

Combinar los dos métodos: el color por píxeles como criterio suave, y de
Gemini solo los campos estables (tipo, manga, largo). Ajustar esa combinación
mirando estas 24 parejas sería sobreajustarla a la prueba. Haría falta un
conjunto de parejas nuevo.

## Análisis a posteriori: «estructura» (24/09)

**Decidido DESPUÉS de ver los resultados anteriores:** no es confirmatorio.

**Motivo.** Al usar la aplicación aparecieron fallos que la prueba de 24
parejas no cubre:

- con una sudadera abierta sobre una camiseta, «arriba» y «encima» miraban el
  mismo recorte y ninguna columna acertaba;
- las sudaderas de cremallera del autor están guardadas como «arriba», así
  que la columna «encima» no las encontraba;
- a una foto con bermudas se le proponían pantalones largos.

**El método, que reproduce la aplicación con `ORDEN_ESTRUCTURA`:**

- solo tipo, manga y largo, que son los campos que midieron fiables y
  estables; el color no entra;
- compiten también las prendas del mismo tipo guardadas en otra posición;
- si la IA ve algo abierto encima, lo de arriba se busca en la franja
  central del torso;
- una misma prenda no sale como principal en dos columnas.

| galería | actual @1 / @3 | estructura @1 / @3 | mejora / empeora / igual |
|---|---|---|---|
| limpia | 17 / 22 | 17 / 22 | 0 / 0 / 24 |
| real | 17 / 22 | 17 / 22 | 1 / 0 / 23 |

La que mejora es arriba_02: del puesto 29 al 11. En «encima», la galería pasa
de 17 a 46 prendas, porque entran las sudaderas del autor, y sigue 8/8 a la
primera.

**Decisión: se enciende**, porque no empeora nada en la prueba. Lo que no hay
es una medida de lo que sí mejora: capas, y corto frente a largo. Para eso
solo hay ejemplos de uso, y así hay que contarlo. Un conjunto de fotos con
capas es trabajo futuro.

## Segunda ronda a posteriori: «prioridades» (24/09)

**Por qué.** Probando la aplicación, la prenda exacta de la foto salía segunda
por detrás de otra de distinto color. La primera ronda ya lo mostraba: con
«actual», arriba_02 cae al puesto 29, y es la 1 con CLIP plano y con el color
primero. La proyección conjunta se entrenó con atributos de DeepFashion, que
casi no incluyen el color, así que ordena por forma.

**El método.** Es el orden que pidió el autor (color, luego tela, luego
corte), con la estructura delante. Las claves, de más a menos importante:

1. estructura dura: familia de tipo, manga y largo;
2. franja de color por píxeles;
3. estructura blanda: vaquero frente a pantalón, camiseta frente a polo;
4. parecido en la proyección.

**La regla, escrita antes de medir.** Entra si en la galería real no empeora
ni el @1 ni el @3 de «estructura».

| galería | estructura @1 / @3 | prioridades @1 / @3 | mejora / empeora / igual |
|---|---|---|---|
| limpia | 17 / 22 | **20 / 24** | 7 / 3 / 14 |
| real | 17 / 22 | 16 / 23 | 6 / 6 / 12 |

**Decisión: no entra.** En la galería real pierde un acierto a la primera.

**Lectura.** Las seis consultas que empeoran en la galería real (abajo_03,
05 y 07; encima_04, 05 y 08) tienen franja_objetivo = 2: el color leído en la
foto del modelo cae lejos del de la foto de producto. Cuando la lectura acierta,
el color primero gana con claridad (arriba_02 pasa del puesto 11 al 1,
abajo_01 del 4 al 1). Cuando falla, entierra la prenda correcta. En la
galería real el daño es mayor porque hay 118 prendas más a las que adelantar.

El cuello de botella es leer el color de una persona fotografiada, no el
orden. La lectura por píxeles cae en la franja 2 en 9 de las 24 consultas.

No se ajusta nada más sobre estas 24 parejas: una tercera variante elegida
mirándolas sería sobreajuste a la prueba.

## Tercera ronda, confirmatoria: «prioridades_ia» (24/09)

**Protocolo.** Escrito antes de recoger las fotos (docstring de
`src/evaluar_busqueda.py`).

**Datos.** 30 parejas nuevas (10 por posición) en `data/eval_color2`. Se
comprobó con hash perceptivo que ninguna repite un producto de la primera
prueba.

**Galería.** 172 prendas: los 30 productos nuevos, los 24 de la primera prueba
como distractores y las 118 del autor. Acertar por azar a la primera: 2,2 %.
Resultados en `experiments/busqueda_ronda3/`.

| método | @1 | @3 | MRR |
|---|---|---|---|
| CLIP plano | 19 | 23 | 0,721 |
| actual | 22 | 27 | 0,827 |
| color primero | 21 | 27 | 0,806 |
| etiquetas | 23 | 28 | 0,849 |
| estructura (en la app) | 23 | 26 | 0,833 |
| prioridades (réplica) | 25 | 29 | 0,908 |
| **prioridades_ia (la candidata)** | **20** | **26** | 0,786 |

**Decisión, por la regla escrita: «prioridades_ia» no entra.** Pierde tres
aciertos a la primera frente a «estructura» (mejora en 6 consultas, empeora
en 7). El color que da la IA no ordena mejor que el de los píxeles.

**Réplica de «prioridades» (píxeles).** El protocolo la dejaba fuera de
decisión: se mide solo como réplica. En estas parejas nuevas quedaría por
encima de «estructura» (25/29 frente a 23/26; mejora 7, empeora 4,
p = 0,55). En la segunda ronda había quedado por debajo en el @1 (16/23
frente a 17/22).

Sumando las dos galerías reales, 54 consultas:

| | @1 | @3 |
|---|---|---|
| prioridades | 41 | 52 |
| estructura | 40 | 48 |

Mejora en 13 consultas y empeora en 10. Lectura: prioridades empata en el @1
y mejora algo en el @3, sin diferencia significativa. La lectura de color por
píxeles cae en la franja 2 en 5 de las 30 consultas nuevas, frente a 9 de 24
en la primera prueba. El resultado depende de lo bien que se lea el color en
cada tanda de fotos.

**La proyección conjunta, en datos nuevos.** Frente a CLIP plano: 22/27
frente a 19/23. Replica la ventaja en el top-3 que se vio en la primera
prueba.

**Decisión final (24/09): se sigue la regla.** La aplicación se queda con
«estructura»; `ORDEN_PRIORIDADES` y `ORDEN_PRIORIDADES_IA` quedan en False.
Encender «prioridades» por su réplica sería elegir con los datos de la
prueba. Queda como trabajo futuro, con un conjunto mayor que decida sin
ambigüedad.
