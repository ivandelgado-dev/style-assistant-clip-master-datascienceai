"""
Paso 8 — Calibracion de las bandas de confianza del frontal.

El problema de producto
-----------------------
La pantalla tiene que decirle algo al usuario sobre cuanto se fia el sistema de
cada resultado. Lo facil es inventarse un "92% de coincidencia". Es mentira: el
modelo produce distancias en un subespacio, no probabilidades calibradas, y no
hay nada que convierta una en otra sin medirlo.

Lo que si se puede decir con honestidad es esto: "de los resultados que el
sistema coloca en esta banda, X de cada 100 compartian el atributo consultado
con la referencia, medido sobre las consultas de validacion". Eso es una
frecuencia observada, no una probabilidad inventada, y este script la calcula.

Como se definen las bandas
--------------------------
Por cuantiles de la distribucion de similitud, no por un umbral elegido a mano.
Elegir el umbral mirando la precision que sale seria elegir el que mejor queda.
Los cuantiles se fijan antes (p99 y p90) y la precision es lo que se reporta.

Y por grupo de atributo, con su propio umbral. Cada cabeza vive en su subespacio
y sus similitudes no son comparables entre si: un 0,78 en textura no significa lo
mismo que un 0,78 en corte. Un umbral unico mezclaria tres escalas distintas.

Se calcula sobre VALIDACION. Test se mira una vez, al final, y calibrar un
elemento de interfaz no es motivo para gastarlo.

Uso
---
    python src/calibrar_bandas.py --experimento experiments/por_atributo
    python src/calibrar_bandas.py --experimento experiments/conjunta --split val
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import numpy as np
import pandas as pd
import torch
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from evaluacion import construir_consultas                      # noqa: E402
from evaluar_condiciones import cargar_cabeza                   # noqa: E402

CUANTILES = {"clara": 0.99, "posible": 0.90}
TOPK = 50          # cuantos resultados por consulta entran en la calibracion


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--experimento", type=pathlib.Path,
                   default=pathlib.Path("experiments/por_atributo"))
    p.add_argument("--emb", type=pathlib.Path, default=pathlib.Path("data/embeddings"))
    p.add_argument("--procesados", type=pathlib.Path,
                   default=pathlib.Path("data/processed"))
    p.add_argument("--split", default="val", choices=["val", "test"])
    p.add_argument("--max-por-atributo", type=int, default=50)
    p.add_argument("--out", type=pathlib.Path,
                   default=pathlib.Path("experiments/calibracion_bandas"))
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--device", default=None)
    args = p.parse_args()

    # El nombre del experimento va en los ficheros de salida. Sin esto, correr
    # dos experimentos contra el mismo --out machaca el primero en silencio, que
    # es justo lo que paso la primera vez.
    etq = f"{args.experimento.name}_{args.split}"

    dev = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    if args.split == "test":
        print("AVISO: estas calibrando sobre TEST. Solo si ya es la corrida final.")

    V = np.load(args.emb / "embeddings.npy").astype(np.float32)
    idx = pd.read_parquet(args.emb / "embeddings_index.parquet")
    splits = pd.read_parquet(args.procesados / "splits.parquet")
    idx = idx.merge(splits[["image_path", "split", "excluir_indice"]],
                    on="image_path", how="left")
    en = ((idx.split == args.split) & (~idx.excluir_indice)).to_numpy()
    ids = idx.loc[en, "image_path"].to_numpy()
    Vi = V[en]
    print(f"indice {args.split}: {len(ids):,} imagenes")

    long = pd.read_parquet(args.procesados / "attrs_long.parquet")
    long = long[long.image_path.isin(set(ids))]
    cons = construir_consultas(long, ids, max_por_atributo=args.max_por_atributo,
                               semilla=args.seed, col_id="image_path")
    print(f"consultas: {len(cons.q_idx):,}")

    filas = []
    for grupo in sorted(set(cons.grupo)):
        pt = args.experimento / f"cabeza_{grupo}.pt"
        if not pt.exists():
            pt = args.experimento / "cabeza_conjunta.pt"
        if not pt.exists():
            print(f"  sin cabeza para '{grupo}' en {args.experimento}, se salta")
            continue
        cab = cargar_cabeza(pt, V.shape[1], dev)
        with torch.no_grad():
            Z = cab(torch.from_numpy(Vi).to(dev))
            Z = torch.nn.functional.normalize(Z, dim=-1)

        sel = np.flatnonzero(cons.grupo == grupo)
        print(f"  {grupo}: {len(sel):,} consultas  ({pt.name})")

        for a in range(0, len(sel), 256):
            lote = sel[a:a + 256]
            q = Z[torch.from_numpy(cons.q_idx[lote]).to(dev)]
            S = q @ Z.T
            S[torch.arange(len(lote)), torch.from_numpy(cons.q_idx[lote]).to(dev)] = -2
            val, pos = torch.topk(S, TOPK, dim=1)
            val = val.cpu().numpy(); pos = pos.cpu().numpy()
            for j, i in enumerate(lote):
                rel = set(cons.relevantes[i].tolist())
                for r in range(TOPK):
                    filas.append((grupo, str(cons.particion[i]), r + 1,
                                  float(val[j, r]), int(pos[j, r] in rel)))

    d = pd.DataFrame(filas, columns=["grupo", "particion", "rango",
                                     "similitud", "acierto"])
    args.out.mkdir(parents=True, exist_ok=True)
    d.to_parquet(args.out / f"pares_{etq}.parquet", index=False)

    # --- curva completa, para que la eleccion de cuantil sea auditable -------
    curva = []
    for grupo, g in d.groupby("grupo"):
        for c in (0.999, 0.99, 0.975, 0.95, 0.90, 0.75, 0.50, 0.0):
            t = g["similitud"].quantile(c) if c > 0 else -2.0
            m = g["similitud"] >= t
            curva.append({"grupo": grupo, "cuantil": c, "umbral": round(float(t), 4),
                          "precision": round(float(g.loc[m, "acierto"].mean()), 4),
                          "n_resultados": int(m.sum())})
    curva = pd.DataFrame(curva)
    curva.to_csv(args.out / f"curva_{etq}.csv", index=False, encoding="utf-8")
    print("\ncurva precision-umbral por grupo:")
    print(curva.to_string(index=False))

    # --- bandas, con los cuantiles fijados de antemano ----------------------
    bandas = {}
    print("\nBANDAS (cuantiles fijados antes de mirar la precision):")
    for grupo, g in d.groupby("grupo"):
        t1 = float(g["similitud"].quantile(CUANTILES["clara"]))
        t2 = float(g["similitud"].quantile(CUANTILES["posible"]))
        m1 = g["similitud"] >= t1
        m2 = (g["similitud"] >= t2) & (~m1)
        azar = float(g["acierto"].mean())
        bandas[grupo] = {
            "umbral_clara": round(t1, 4), "umbral_posible": round(t2, 4),
            "precision_clara": round(float(g.loc[m1, "acierto"].mean()), 4),
            "precision_posible": round(float(g.loc[m2, "acierto"].mean()), 4),
            "precision_todos": round(azar, 4),
            "n_clara": int(m1.sum()), "n_posible": int(m2.sum()),
        }
        b = bandas[grupo]
        print(f"  {grupo:<9} clara >={t1:.3f}: {100*b['precision_clara']:.0f}/100   "
              f"posible >={t2:.3f}: {100*b['precision_posible']:.0f}/100   "
              f"(cualquier resultado del top-{TOPK}: {100*azar:.0f}/100)")

    t1g = float(d["similitud"].quantile(CUANTILES["clara"]))
    t2g = float(d["similitud"].quantile(CUANTILES["posible"]))
    g1 = d["similitud"] >= t1g
    g2 = (d["similitud"] >= t2g) & (~g1)
    bandas["_agregado"] = {
        "umbral_clara": round(t1g, 4), "umbral_posible": round(t2g, 4),
        "precision_clara": round(float(d.loc[g1, "acierto"].mean()), 4),
        "precision_posible": round(float(d.loc[g2, "acierto"].mean()), 4),
        "precision_todos": round(float(d["acierto"].mean()), 4),
        "n_clara": int(g1.sum()), "n_posible": int(g2.sum()),
    }
    b = bandas["_agregado"]
    print(f"  {'AGREGADO':<9} clara >={t1g:.3f}: {100*b['precision_clara']:.0f}/100   "
          f"posible >={t2g:.3f}: {100*b['precision_posible']:.0f}/100   "
          f"(cualquier resultado del top-{TOPK}: {100*b['precision_todos']:.0f}/100)")
    print("  El agregado es el numero de la pantalla de 'parecido general', donde "
          "el usuario no elige dimension.")

    with open(args.out / f"bandas_{etq}.yaml", "w", encoding="utf-8") as fh:
        yaml.safe_dump({"split": args.split, "cuantiles": CUANTILES, "topk": TOPK,
                        "experimento": str(args.experimento),
                        "seed": args.seed, "bandas": bandas},
                       fh, sort_keys=False, allow_unicode=True)
    print(f"\nescrito en {args.out}")
    print("El numero para el mockup es 'precision_clara' del grupo que muestre "
          "la pantalla; si la pantalla no distingue grupo, usa el peor de los tres.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
