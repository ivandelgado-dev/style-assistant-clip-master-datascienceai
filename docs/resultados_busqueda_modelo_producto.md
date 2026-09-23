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
