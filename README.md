# Asistente de Estilo Personal con IA

Proyecto Final del **Máster en Data Science y Desarrollo de IA** — Evolve Academy.

**Autor:** Iván Delgado

---

## Qué es

Un sistema de búsqueda visual de ropa por atributos. Dada una imagen de referencia, recupera las prendas más parecidas de un armario digitalizado, pudiendo consultar por un atributo concreto —corte, color o textura— de forma independiente.

Sobre ese núcleo se construye, como ampliación, un recomendador de outfits que combina las prendas del armario y sugiere piezas de catálogo para completar un look.

El alcance está acotado a **ropa de hombre**.

## Enfoque

El sistema es de **recuperación y ranking multimodal**, no de generación. Las prendas se representan en un espacio de embeddings visual-textual sobre un backbone CLIP congelado.

La contribución técnica central son las **proyecciones específicas por atributo**: cabezas ligeras entrenadas sobre el embedding congelado que permiten consultar por corte, color o textura por separado. Esto es lo que hace posible responder a *"parécete al corte, ignora el color"* cuando el usuario no posee la prenda exacta de la referencia. Un embedding CLIP plano no lo permite: mezcla todos los atributos en un único vector.

## Alcance

El proyecto distingue deliberadamente entre un núcleo evaluable y las ampliaciones opcionales, para proteger un core acotado y demostrable.

**Core — lo que se evalúa con rigor:**
- Que la búsqueda por atributos mejora de forma medible frente al enfoque básico (CLIP plano).
- Que el sistema funciona sobre un armario real, no solo sobre fotos de catálogo (evaluación del *domain gap*).

**Ampliaciones (nice-to-have) — solo si el core está cerrado:**
- Recomendador completo de outfits y compatibilidad entre prendas.
- Catálogo comercial y enlace a producto.
- LLM para interpretar peticiones y explicar recomendaciones.
- Aplicación web desplegada.

## Estado

| Entrega | Contenido | Estado |
|---|---|---|
| 1 | Ideación y detección de oportunidades | Completada |
| 2 | Selección de idea y análisis de datos | Completada |
| 3 | Modelo de datos y capa gold | Completada |
| 4 | Diseño del análisis y estrategia de modelado | Completada |

## Estructura

```
docs/
└── entregas/
    ├── 01_ideas_producto.md
    ├── 02_datos_necesarios.md
    ├── 03_modelo_datos.md
    └── 04_analisis_modelado.md
```

## Fuentes de datos

El núcleo del proyecto trabaja exclusivamente con fuentes académicas. El catálogo comercial queda fuera del core.

| Fuente | Uso | Licencia |
|---|---|---|
| [DeepFashion](https://mmlab.ie.cuhk.edu.hk/projects/DeepFashion.html) | Atributos de prenda (señal de entrenamiento) | Solo investigación académica |
| [Polyvore Outfits](https://huggingface.co/datasets/mvasil/polyvore-outfits) | Compatibilidad entre prendas (ampliación) | CC BY 4.0 |
| [Fashion Product Images](https://www.kaggle.com/datasets/paramaggarwal/fashion-product-images-small) | Catálogo de recuperación | No declarada |
| Armario propio | Evaluación *out-of-distribution* | Recolección primaria |

Detalle completo, riesgos y alternativas en [`02_datos_necesarios.md`](docs/entregas/02_datos_necesarios.md).

## Evaluación

- **Métricas automáticas:** Recall@k, NDCG@k y mAP de recuperación por atributo, siempre frente al baseline CLIP plano.
- **Valoración humana:** panel ciego de evaluadores que comparan baseline y modelo sin saber cuál es cuál, para medir coherencia percibida más allá de las métricas.
- **Baseline:** similitud coseno sobre el embedding CLIP completo.

Detalle en [`04_analisis_modelado.md`](docs/entregas/04_analisis_modelado.md).

## Stack

Python · PyTorch · CLIP (HuggingFace) · scikit-learn · pandas · PostgreSQL + pgvector · FastAPI · Streamlit · Docker.

## Nota sobre licencias

Este es un artefacto **académico**. DeepFashion restringe su uso a investigación, y la licencia de Fashion Product Images no está declarada. Ninguna imagen de catálogo comercial se almacena ni redistribuye en este repositorio.
