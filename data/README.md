# data/

Este directorio está **excluido de git** (`.gitignore`). Las imágenes de
DeepFashion superan los 20 GB y dos de las fuentes prohíben la redistribución.

## Qué va dónde

```
data/
├── raw/deepfashion/anno/     <- list_attr_cloth.txt, list_attr_img.txt
│                                (LO ÚNICO que necesita el paso 2)
├── raw/deepfashion/img/      <- imágenes. Solo a partir del paso 3
├── processed/                <- salida del EDA: attrs_meta, attrs_long, heldout.yaml
├── embeddings/               <- salida de CLIP congelado
└── mappings/                 <- categories.csv (taxonomía unificada, entrega 3 §8.3)
```

## Descarga de DeepFashion

Benchmark *Category and Attribute Prediction*, desde la página de CUHK MMLab.
Se distribuye por Google Drive, sin contraseña ni acuerdo firmado para este
benchmark concreto.

https://mmlab.ie.cuhk.edu.hk/projects/DeepFashion/AttributePrediction.html

**Para el paso 2 basta con la carpeta `Anno`.** No descargues `img` todavía.

## Excepción de derechos

Las imágenes del catálogo comercial (Zara/Bershka) **no se almacenan aquí ni en
ninguna parte**. Solo URL y embedding. Ver `docs/entregas/02_datos_necesarios.md`
§3.4.
