"""
Paso 4d — Tablas comparativas a partir de las metricas ya calculadas.

`evaluar_condiciones.py` guarda una fila por (condicion, consulta) con todas las
metricas. Este script solo lee ese parquet y produce las comparativas, asi que
cambiar de metrica o de corte cuesta segundos en lugar de reevaluar.

Existe ademas por una razon de fondo: Recall@k NO sirve como metrica principal
en este montaje. Un atributo frecuente tiene miles de relevantes en el indice,
y con n_relevantes >> k el recall queda acotado por k/n_relevantes — un
recuperador PERFECTO sacaria 10/2000 = 0,005. Todas las condiciones caben en esa
banda y dejan de distinguirse.

NDCG@k normaliza contra el ideal truncado a k (IDCG sobre min(n_rel, k)), asi
que vale 1 si las k primeras son relevantes, independientemente de cuantos
relevantes haya. Es la metrica que discrimina aqui.

Uso
---
    python src/tabla_resultados.py
    python src/tabla_resultados.py --metrica mAP --split val
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from evaluacion import tabla_comparativa   # noqa: E402


def diagnostico_relevantes(df: pd.DataFrame) -> None:
    """Cuantos relevantes tiene cada consulta y que techo impone al recall."""
    una = df[df.condicion == df.condicion.iloc[0]]
    n = una.n_relevantes
    print("=== relevantes por consulta (lo que acota el Recall@k) ===")
    print(f"  mediana {n.median():.0f}   p90 {np.percentile(n, 90):.0f}   "
          f"max {n.max():,}   consultas {len(n):,}")
    for k in (5, 10, 20):
        techo = np.minimum(k, n) / n
        print(f"  techo medio de Recall@{k:<2} con un ranking perfecto: "
              f"{techo.mean():.4f}")
    print("  -> si el resultado observado ronda ese techo, la metrica esta\n"
          "     saturada y no mide calidad de ordenacion.\n")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--experimentos", type=pathlib.Path,
                   default=pathlib.Path("experiments"))
    p.add_argument("--split", default="val", choices=["val", "test"])
    p.add_argument("--metrica", default="ndcg@10")
    p.add_argument("--referencia", default=None,
                   help="Por defecto 4_conjunta si existe, si no 2_clip_plano")
    p.add_argument("--n-boot", type=int, default=10_000)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    f = args.experimentos / f"resultados_{args.split}" / "metricas_por_consulta.parquet"
    if not f.exists():
        print(f"No existe {f}. Ejecuta antes evaluar_condiciones.py", file=sys.stderr)
        return 1
    df = pd.read_parquet(f)

    metricas = [c for c in df.columns
                if c.startswith(("recall@", "ndcg@")) or c == "mAP"]
    if args.metrica not in metricas:
        print(f"Metrica '{args.metrica}' no esta. Disponibles: {metricas}",
              file=sys.stderr)
        return 1

    diagnostico_relevantes(df)

    print("=== resumen de todas las metricas (media por condicion) ===")
    resumen = (df.groupby("condicion")[metricas].mean()
               .sort_index())
    print(resumen.to_string(float_format=lambda v: f"{v:.4f}"))

    print(f"\n=== {args.metrica} por particion ===")
    piv = (df.pivot_table(index="condicion", columns="particion",
                          values=args.metrica, aggfunc="mean"))
    print(piv.to_string(float_format=lambda v: f"{v:.4f}"))

    resultados = {c: g.reset_index(drop=True) for c, g in df.groupby("condicion")}
    ref = args.referencia or ("4_conjunta" if "4_conjunta" in resultados
                              else "2_clip_plano")

    for referencia in dict.fromkeys([ref, "2_clip_plano"]):
        if referencia not in resultados:
            continue
        print(f"\n{'=' * 78}\nDIFERENCIA PAREADA frente a {referencia}"
              f"  ({args.metrica}, IC95 bootstrap)\n{'=' * 78}")
        # El cruce grupo x particion es el contraste que decide: ganar en un
        # grupo mirando seen y unseen juntos puede venir solo de los atributos
        # con los que se entreno. La afirmacion fuerte es ganar en un grupo
        # SOBRE ATRIBUTOS NUNCA VISTOS.
        for df_ in (df,):
            df_["grupo_particion"] = df_.attr_group + " | " + df_.particion
        resultados = {c: g.reset_index(drop=True)
                      for c, g in df.groupby("condicion")}

        for corte in ("particion", "attr_group", "grupo_particion"):
            t = tabla_comparativa(resultados, referencia, metrica=args.metrica,
                                  por=corte, n_boot=args.n_boot, semilla=args.seed)
            print(f"\n-- por {corte} --")
            print(t[["condicion", corte, "media_a", "media_b", "diferencia",
                     "ic_bajo", "ic_alto", "significativo"]]
                  .to_string(index=False, float_format=lambda v: f"{v:+.4f}"))
            dest = args.experimentos / f"resultados_{args.split}"
            t.to_csv(dest / f"comp_{args.metrica.replace('@','')}"
                            f"_{referencia}_{corte}.csv", index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
