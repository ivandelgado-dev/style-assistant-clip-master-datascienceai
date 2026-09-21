"""
Etiquetado zero-shot del eje "quien lleva la prenda" sobre el indice de catalogo.

Por que hace falta
------------------
DeepFashion no trae metadato de genero ni de presentacion, y la anotacion manual
no escala a 21.883 imagenes. Sin esa etiqueta, la caida de rendimiento sobre el
armario no se puede descomponer: quedaria un unico numero que mezcla dispositivo,
fondo, presentacion y genero de la prenda (ver docs/resultados_anotacion_dominio.md).

Por que zero-shot y no una sonda entrenada
------------------------------------------
Entrenar una sonda exigiria mis propias etiquetas, y esas etiquetas ya
demostraron tener deriva de anotador (7% frente a 19% en dos pasadas sobre la
misma poblacion). Una sonda entrenada sobre etiquetas inconsistentes hereda la
inconsistencia y la reparte por todo el indice sin dejar rastro.

El zero-shot no usa mis etiquetas para NADA salvo para medirse. Es un
procedimiento fijo, escrito antes de ver el resultado, y su acierto se reporta
contra una muestra anotada a mano bajo criterio escrito. Si acierta poco, se
dice y no se usa.

Circularidad: se usa CLIP para etiquetar imagenes sobre las que despues se
evalua CLIP. Es aceptable porque la etiqueta NO es el juicio de relevancia
—eso lo da la categoria de DeepFashion, anotada por humanos— sino una variable
de estratificacion, y porque su tasa de error va medida y reportada. No seria
aceptable si definiera el acierto.

Prompt ensembling
-----------------
Un solo prompt es fragil: "a photo of a man" y "a man" dan resultados distintos
sin ninguna razon de fondo. Se promedian varios por clase y se renormaliza, que
es la practica estandar desde el paper original de CLIP.

Uso
---
    python src/etiquetar_genero.py
    python src/etiquetar_genero.py --split test --out experiments/anotacion_dominio
"""

from __future__ import annotations

import argparse
import pathlib

import numpy as np
import pandas as pd
import torch

MODELO = "openai/clip-vit-base-patch32"

EJES: dict[str, list[str]] = {
    "hombre": [
        "a photo of a man wearing clothes",
        "a male model wearing an outfit",
        "a men's fashion photo with a male model",
        "a photo of a guy wearing a shirt",
    ],
    "mujer": [
        "a photo of a woman wearing clothes",
        "a female model wearing an outfit",
        "a women's fashion photo with a female model",
        "a photo of a girl wearing a shirt",
    ],
    "sin_persona": [
        "a product photo of a garment on a plain background",
        "clothing laid flat with nobody wearing it",
        "a piece of clothing on a hanger, no person",
        "an isolated product shot of an item of clothing",
    ],
}
CLASES = ("hombre", "mujer", "sin_persona")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--emb", type=pathlib.Path, default=pathlib.Path("data/embeddings"))
    p.add_argument("--splits", type=pathlib.Path,
                   default=pathlib.Path("data/processed/splits.parquet"))
    p.add_argument("--split", default=None,
                   help="Limitar a una particion. Por defecto, todo el corpus")
    p.add_argument("--out", type=pathlib.Path,
                   default=pathlib.Path("experiments/anotacion_dominio"))
    p.add_argument("--modelo", default=MODELO)
    args = p.parse_args()

    from transformers import AutoTokenizer, CLIPModel

    # Mismo helper que usa la extraccion de imagenes. En transformers 5.x ni
    # get_image_features ni get_text_features devuelven un tensor: devuelven un
    # objeto, y el vector proyectado esta dentro. Ya nos mordio una vez con las
    # imagenes; tener UN solo sitio donde se resuelve evita que vuelva a pasar.
    import sys as _sys
    _sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    from embeddings_clip import extraer_vector

    tok = AutoTokenizer.from_pretrained(args.modelo)
    modelo = CLIPModel.from_pretrained(args.modelo).eval()

    vs = []
    with torch.no_grad():
        for c in CLASES:
            t = tok(EJES[c], padding=True, return_tensors="pt")
            e = extraer_vector(modelo.get_text_features(**t))
            e = e / e.norm(dim=-1, keepdim=True)
            v = e.mean(0)
            vs.append((v / v.norm()).numpy().astype(np.float32))
    T = np.stack(vs)
    print(f"{len(CLASES)} ejes de texto, dim {T.shape[1]}")

    V = np.load(args.emb / "embeddings.npy").astype(np.float32)
    rutas = pd.read_parquet(args.emb / "embeddings_index.parquet")["image_path"]
    V /= (np.linalg.norm(V, axis=1, keepdims=True) + 1e-8)

    d = pd.DataFrame({"image_path": rutas})
    if args.split:
        s = pd.read_parquet(args.splits)[["image_path", "split", "excluir_indice"]]
        d = d.merge(s, on="image_path", how="left")
        m = (d["split"] == args.split).to_numpy()
        V, d = V[m], d[m].reset_index(drop=True)
    print(f"{len(d):,} imagenes")

    S = V @ T.T
    for i, c in enumerate(CLASES):
        d[c] = S[:, i]
    d["etiqueta"] = [CLASES[i] for i in S.argmax(axis=1)]
    orden = np.sort(S, axis=1)
    # Margen entre la primera y la segunda clase. Un margen pequeno es una
    # imagen sobre la que el procedimiento no se moja; sirve para poder
    # descartar dudosas mas adelante sin volver a calcular nada.
    d["margen"] = orden[:, -1] - orden[:, -2]

    args.out.mkdir(parents=True, exist_ok=True)
    salida = args.out / f"genero_zeroshot{'_' + args.split if args.split else ''}.parquet"
    d.to_parquet(salida, index=False)

    print("\nreparto:")
    print((d["etiqueta"].value_counts(normalize=True) * 100).round(1).to_string())
    print(f"\nmargen: mediana {d['margen'].median():.4f}  "
          f"p10 {d['margen'].quantile(.10):.4f}")
    print(f"escrito {salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
