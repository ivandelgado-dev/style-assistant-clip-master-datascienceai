# Akin · Asistente de Estilo Personal con IA

Trabajo de Fin de Máster del **Máster en Data Science y Desarrollo de IA**, Evolve Academy.

**Autor:** Iván Delgado

---

## Qué es

Subes la foto de un look que te gusta y Akin busca en **tu propio armario** lo más parecido, pieza a pieza. O eliges un estilo y te monta conjuntos con lo que ya tienes, diciéndote si una prenda tuya encaja y por qué.

El alcance del producto es ropa de hombre.

## Enfoque

Es un sistema de **recuperación**, no de generación. Cada prenda se convierte en un vector con **CLIP ViT-B/32 congelado**, y encima va una **proyección lineal de 512 a 128 dimensiones** entrenada con pérdida contrastiva sobre las etiquetas de atributos de DeepFashion.

La hipótesis de partida era que **una cabeza por atributo** (corte, textura, tejido) funcionaría mejor que una sola proyección conjunta.

## Qué salió

Detalle en `docs/resultados_*.md`. Métricas y configuración de cada corrida en `experiments/`.

- **La proyección supervisada mejora a CLIP**, también en atributos que no vio al entrenar: +0,0217 NDCG@10 en atributos vistos y +0,0132 en no vistos, los dos significativos por bootstrap pareado.
- **Las cabezas por atributo no ganan a la conjunta.** Solo mejoran en el vocabulario con el que se entrenaron (+0,0035) y fuera de él no se distinguen del ruido (−0,0058, no significativo). Es un resultado negativo, medido con cinco controles.
- **Salto de dominio** (catálogo frente a fotos de móvil de mi armario, 118 prendas): las dos fuentes se separan con AUC 1,000, pero en la tarea no se detecta una caída significativa con esta muestra.
- **En la app**, desde la foto de un modelo de tienda, la prenda exacta sale primera 22 de 30 veces entre 172 (CLIP solo: 19). Son fotos nuevas, con la regla escrita antes.

## La aplicación

Streamlit, con cuentas de usuario y un armario por cuenta (SQLite).

- **Mi armario:** subir prendas de una en una o varias de golpe. Gemini propone tipo, color y tejido, y lo que pone el usuario manda.
- **Buscar desde una foto:** la foto se corta por zonas y por capas, y cada zona se busca solo entre tus prendas de esa posición.
- **Por estilo:** 10 estilos, con reglas de estilista escritas en el código (formalidad, capas, color y paletas del diccionario de Sanzo Wada). Cada look dice por qué.

La IA generativa **describe y traduce, nunca decide**: qué prenda sale y en qué orden lo deciden los vectores y las reglas.

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Gemini necesita `GEMINI_API_KEY` en un fichero `.env`, que no se sube al repositorio. Sin clave, la app funciona y pregunta en vez de proponer.

## Estado

| Entrega | Contenido | Estado |
|---|---|---|
| 1 | Ideación y detección de oportunidades | Completada |
| 2 | Selección de idea y análisis de datos | Completada |
| 3 | Modelo de datos y capa gold | Completada |
| 4 | Diseño del análisis y estrategia de modelado | Completada |
| 5 | Diseño del frontal y experiencia de usuario | Completada |

## Estructura

```
app.py, paginas/        la aplicación
src/                    datos, entrenamiento y evaluación
experiments/            una carpeta por corrida: config.yaml y métricas
docs/                   protocolos y resultados
docs/entregas/          las cinco entregas
docs/assets/            mockups de la entrega 5
tests/                  pruebas automáticas
data/                   fuera de git
```

## Datos

| Fuente | Uso | Licencia |
|---|---|---|
| [DeepFashion](https://mmlab.ie.cuhk.edu.hk/projects/DeepFashion.html) | Supervisión de atributos | Solo investigación académica |
| Armario propio · 118 prendas | Test fuera de distribución, nunca entrenamiento | Fotos del autor |
| Parejas modelo / producto · 54 | Evaluación de la búsqueda | Fotos de tienda, solo en local |
| [Diccionario de Wada](https://github.com/mattdesl/dictionary-of-colour-combinations) | Paletas de «Por estilo» | MIT |
| [Polyvore Outfits](https://huggingface.co/datasets/mvasil/polyvore-outfits) | Compatibilidad | Prevista, no usada |
| [Fashion Product Images](https://www.kaggle.com/datasets/paramaggarwal/fashion-product-images-small) | Catálogo | Previsto, no usado. Licencia no declarada |

DeepFashion resultó ser mayoritariamente ropa de mujer (81-93 %, anotado a mano), aunque filtré por categorías compatibles con ropa de hombre. El producto es de hombre; el corpus de entrenamiento, no. Está en `docs/resultados_anotacion_dominio.md`.

## Reproducibilidad

Semillas y versiones fijadas. Cada experimento guarda su `config.yaml` y sus métricas en `experiments/`. Las imágenes no se redistribuyen: `data/` está fuera de git desde el primer commit.
