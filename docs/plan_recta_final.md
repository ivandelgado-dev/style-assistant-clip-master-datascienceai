# Plan de la recta final

## FECHAS CONFIRMADAS (18/09/2026)

**Exposición: miércoles 30 de septiembre.** Plaza confirmada por el coordinador.

El plazo de entrega del 4 de octubre **no es margen para terminar**: es para
corregir detalles que surjan en la propia exposición. Textualmente: *"damos un
margen de tiempo entre la presentación y la entrega para poder corregir pequeños
detalles que surjan en la exposición […] tampoco es necesario, tenlo lo más
listo posible"*.

**La fecha operativa es el 30.** Doce días desde hoy.

Consecuencia sobre las prioridades: hay exposición, luego la demo funcionando
deja de ser un extra y pasa a ser lo que se enseña en pantalla.

Pendiente de respuesta (preguntado al responsable de TFM): si hay memoria
aparte de las entregas 1-5 y con qué extensión, duración y formato de la
defensa, y si existe rúbrica.


**Fecha de escritura:** 31 de agosto de 2026
**Fecha límite:** final de septiembre de 2026
**Estado de partida:** entregas 1-4 cerradas, cero código escrito.

Este documento existe porque las sesiones son irregulares. Si vuelves después de
varios días, empieza aquí.

---

## Decisión de alcance tomada el 31/08

**Se corta la infraestructura hasta tener un número.**

PostgreSQL + pgvector, FastAPI, Streamlit y Docker quedan fuera de la ruta
crítica. Para el core, buscar los k vecinos entre ~44.000 vectores es un producto
de matrices de numpy que cabe en RAM.

La entrega 3 argumenta que la capa gold debe ser Postgres, y ese argumento es
correcto **como diseño**: filtrado relacional y búsqueda vectorial resueltos en
una sola consulta. Lo que cambia no es el diseño, es el orden de construcción.

- La capa gold se implementa como **parquet + numpy** para poder evaluar.
- El esquema de Postgres se defiende como **diseño documentado** — que es
  exactamente lo que la entrega 3 ya hace, con su justificación completa.
- Se levanta de verdad **solo si el core cierra y sobra tiempo**.

Construir la base de datos antes de tener la primera métrica no aporta ninguna
métrica y consume el recurso más escaso que hay.

---

## Orden de ejecución

1. **Protocolo de evaluación y split.** HECHO — ver `docs/protocolo_evaluacion.md`.
   Va primero porque retrofitarlo después significa reentrenar todo.

2. **DeepFashion + EDA de atributos.** Código listo en `src/eda_atributos.py`.
   Falta descargar `anno/list_attr_cloth.txt` y `anno/list_attr_img.txt` a
   `data/raw/deepfashion/anno/`. **No hacen falta las imágenes todavía.**
   Aquí se resuelve la cuestión de la cabeza de color con datos delante.

3. **Precomputar embeddings CLIP.** Una sola vez, salida a parquet.
   Aquí sí hacen falta los ~20 GB de imágenes.

4. **Entrenar las condiciones 4 y 5 del protocolo a la vez:** proyección conjunta
   (baseline de supervisión) y proyecciones por atributo (la contribución).
   Es el mismo código con una cabeza en vez de tres.
   **Aquí sale el primer número real.**

5. **Checkpoint duro — mediados de septiembre.** PASADO, el 07/09.

   El número salió y decidió por nosotros. La proyección supervisada bate a CLIP
   plano (+0,0217 vistos, +0,0132 no vistos, NDCG@10, las dos significativas),
   pero el desacoplamiento por atributo solo mejora sobre el vocabulario con el
   que se entrenó: +0,0035 en atributos vistos y −0,0058 en no vistos, este
   último no significativo. Es una mejora de especialización, no de
   representación. Detalle en `docs/resultados_modelado.md`.

   Consecuencia: se ejecuta el plan B previsto en la entrega 4 §8. La aportación
   principal pasa a ser el análisis del *domain gap*, y con ello las fotos del
   armario dejan de ser un extra y pasan a ser la ruta crítica.

5-bis. **Domain gap.** Preparado el 07/09, a la espera de fotos.
   - Protocolo de captura fijado y cerrado: `docs/protocolo_armario.md`.
   - `src/embeddings_clip.py --carpeta` acepta un directorio suelto de imágenes.
   - `src/domain_gap.py` mide las tres cosas, sobre CLIP plano y sobre cada
     proyección: suelo de ruido (tomas repetidas), separabilidad de dominio
     (sonda lineal con validación cruzada, emparejada por composición de
     categorías, con dos nulos de catálogo y control permutado) y degradación en
     la tarea (recuperación de categoría, consulta de armario contra índice de
     catálogo frente a consulta de catálogo).
   - Validado con un armario simulado: sin desplazamiento de dominio no detecta
     nada (caída +0,001); con desplazamiento la detecta (caída +0,142).

   Comandos, una vez estén las fotos etiquetadas:

       python src/embeddings_clip.py --carpeta data/raw/wardrobe/img --out data/embeddings_armario
       python src/embeddings_clip.py --verificar --sin-corpus --out data/embeddings_armario
       python src/domain_gap.py \
           --emb-armario data/embeddings_armario \
           --armario-csv data/raw/wardrobe/armario.csv \
           --experimentos experiments/conjunta experiments/por_atributo \
           --out experiments/domain_gap

5-ter. **Checkpoint anterior, conservado como referencia:**
   - Si no hay número: se pivota al análisis del *domain gap* como aportación
     principal, con tiempo suficiente para hacerlo bien.
   - Si las cabezas no baten a la proyección conjunta: se sabe aquí, y se reporta
     como resultado negativo con ablations. Está contemplado desde la entrega 4.

5-quater. **Composición del corpus (16/09).** Hallazgo no previsto: el corpus
   de atributos es 81-93% ropa de mujer. El filtro del EDA seleccionaba por
   nombre de categoría, y esos nombres son unisex. Ver
   `docs/resultados_anotacion_dominio.md`.
   - No cambia el resultado de modelado: las tres condiciones vieron los mismos
     datos.
   - Sí obliga a corregir la afirmación de alcance en la memoria.
   - Añade un cuarto confusor al domain gap. Se declara, no se descompone: la
     sonda de género se descartó por coste/beneficio a dos semanas de entregar.

6. **Evaluación sobre armario real + bootstrap.**

7. **Memoria.**

---

## En paralelo, desde el primer día

**Fotografiar y etiquetar el armario.** Es la única pieza sin sustituto, no
necesita GPU ni que el código funcione, y es trabajo que se puede hacer un día
de vuelta del turno sin energía para programar.

Regla que no se salta: **etiquetar los atributos antes de ver ninguna salida del
modelo.** Si se etiqueta después, el etiquetador ya sabe qué resultado quiere.

**Buscar el panel humano.** 3-5 personas ajenas al desarrollo. Es lo único que
depende del calendario de otros, así que se empieza a cuadrar ya aunque la
evaluación ocurra al final.

---

## Fuera de alcance, como trabajo futuro

No es un recorte de emergencia: es ejecutar la separación core / nice-to-have que
la propia entrega 4 ya estableció.

- Polyvore y el módulo de compatibilidad entre prendas.
- Catálogo comercial y enlace a producto.
- LLM para interpretar peticiones y explicar recomendaciones.
- Aplicación web desplegada.
- PostgreSQL + pgvector implementado (el diseño sí se defiende).

---

## Puntos abiertos

- Si la cabeza de color sobrevive. Depende del EDA del paso 2: DeepFashion
  clasifica sus atributos en textura / tejido / forma / partes / estilo, y color
  no está entre ellos. La supervisión de color tendría que venir de `baseColour`
  de Fashion Product Images, que es otro corpus con otra distribución visual.
- Cuántos atributos sobreviven al filtro de frecuencia, y por tanto cuántos
  quedan como held-out. Sale del paso 2.
