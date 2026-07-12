# Asistente de Estilo Personal con IA

Proyecto Final del **Máster en Data Science y Desarrollo de IA** — Evolve Academy.

**Autor:** Iván Delgado

---

## Qué es

Un sistema de recomendación de outfits que, dado el armario digitalizado de una persona y una imagen de inspiración, construye conjuntos con las prendas que ya posee. Cuando una posición del outfit no puede cubrirse con el armario, recupera del catálogo la prenda más próxima y enlaza al producto.

El alcance está acotado a **ropa de hombre**.

## Enfoque

El sistema es de **recuperación y ranking multimodal**, no de generación. Las prendas se representan en un espacio de embeddings visual-textual compartido sobre un backbone congelado tipo CLIP.

La contribución técnica central son las **proyecciones específicas por atributo**: cabezas ligeras entrenadas sobre el embedding congelado que permiten consultar por corte, color o textura de forma independiente. Esto es lo que hace posible responder a *"parécete al corte, ignora el color"* cuando el usuario no posee la prenda exacta de la referencia.

## Estado

| Entrega | Contenido | Estado |
|---|---|---|
| 1 | Ideación y detección de oportunidades | Completada |
| 2 | Selección de idea y análisis de datos | Completada |
| 3 | Modelo de datos y capa gold | Completada |

## Estructura

```
docs/
└── entregas/
    ├── 01_ideas_producto.md
    ├── 02_datos_necesarios.md
    └── 03_modelo_datos.md
```

## Fuentes de datos

| Fuente | Uso | Licencia |
|---|---|---|
| [Polyvore Outfits](https://huggingface.co/datasets/mvasil/polyvore-outfits) | Compatibilidad entre prendas | CC BY 4.0 |
| [DeepFashion](https://mmlab.ie.cuhk.edu.hk/projects/DeepFashion.html) | Atributos de prenda | Solo investigación académica |
| [Fashion Product Images](https://www.kaggle.com/datasets/paramaggarwal/fashion-product-images-small) | Catálogo | No declarada |
| Armario propio | Evaluación *out-of-distribution* | Recolección primaria |

Detalle completo, riesgos y alternativas en [`02_datos_necesarios.md`](docs/entregas/02_datos_necesarios.md).

## Nota sobre licencias

Este es un artefacto **académico**. DeepFashion restringe su uso a investigación, y la licencia de Fashion Product Images no está declarada. Ninguna imagen de catálogo comercial se almacena ni redistribuye en este repositorio.
