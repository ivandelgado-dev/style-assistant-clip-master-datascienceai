"""
Paso 4c — Evaluacion comparada de las seis condiciones del protocolo.

Produce la tabla que decide el proyecto. Todas las condiciones pasan por el
MISMO motor (`src/evaluacion.py`) y sobre EXACTAMENTE las mismas consultas: la
comparacion es pareada y la diferencia entre condiciones no puede venir del
evaluador.

Condiciones (protocolo §4)
--------------------------
  1 aleatorio        ranking al azar. Suelo absoluto.
  2 clip_plano       coseno sobre el embedding CLIP de 512d. El baseline real.
  3 clip_pca128      CLIP reducido a 128d con PCA ajustado EN TRAIN. Controla
                     que la mejora no venga de reducir dimensiones.
  4 conjunta         una proyeccion 128d entrenada sobre todos los atributos.
                     Controla que la mejora no venga solo de supervisar.
  5 por_atributo     una cabeza por grupo. La contribucion del proyecto.
  6 *_mlp            variantes no lineales, si existen.

La referencia de la tabla es la CONJUNTA, no CLIP plano: batir a CLIP plano solo
demuestra que la supervision ayuda. Lo que sostiene la tesis es 5 > 4.

Uso
---
    python src/evaluar_condiciones.py
    python src/evaluar_condiciones.py --split val     # durante el desarrollo
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import numpy as np
import pandas as pd
import torch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from entrenar_proyecciones import GRUPOS_CABEZA, Proyeccion   # noqa: E402
from evaluacion import (construir_consultas, evaluar,          # noqa: E402
                        tabla_comparativa)


def cargar_cabeza(path: pathlib.Path, dim_in: int, dev: str) -> Proyeccion:
    ck = torch.load(path, map_location=dev, weights_only=False)
    m = Proyeccion(dim_in, ck["dim"], mlp=ck["mlp"]).to(dev).eval()
    m.load_state_dict(ck["state_dict"])
    return m


@torch.no_grad()
def proyectar(modelo: Proyeccion, V: np.ndarray, dev: str) -> np.ndarray:
    X = torch.from_numpy(V).float().to(dev)
    X = torch.nn.functional.normalize(X, dim=-1)   # misma entrada que en train
    return modelo(X).cpu().numpy()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--procesados", type=pathlib.Path,
                   default=pathlib.Path("data/processed"))
    p.add_argument("--embeddings", type=pathlib.Path,
                   default=pathlib.Path("data/embeddings"))
    p.add_argument("--experimentos", type=pathlib.Path,
                   default=pathlib.Path("experiments"))
    # Por defecto VAL, no test. El protocolo dice que test se mira una vez, al
    # final; tenerlo de default invita a iterar contra el y a que la ultima
    # cifra este contaminada por las decisiones tomadas mirandola.
    p.add_argument("--split", default="val", choices=["val", "test"])
    p.add_argument("--max-por-atributo", type=int, default=50)
    p.add_argument("--metrica", default="recall@10")
    p.add_argument("--n-boot", type=int, default=10_000)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--device", default=None)
    args = p.parse_args()

    dev = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device: {dev}   |   split de evaluacion: {args.split}")
    if args.split == "test":
        print("Recuerda: test se mira UNA vez, al final. Para iterar usa --split val.")

    idx = pd.read_parquet(args.embeddings / "embeddings_index.parquet")
    V = np.load(args.embeddings / "embeddings.npy")
    splits = pd.read_parquet(args.procesados / "splits.parquet")
    long = pd.read_parquet(args.procesados / "attrs_long.parquet")

    idx = idx.merge(splits[["image_path", "split", "excluir_indice"]],
                    on="image_path", how="left")

    # --- indice de evaluacion ---------------------------------------------
    # Solo del split elegido, y sin las imagenes con gemela casi identica en
    # otra particion (protocolo §3).
    en_indice = ((idx.split == args.split) & (~idx.excluir_indice)).to_numpy()
    ids_indice = idx.loc[en_indice, "image_path"].to_numpy()
    V_ev = V[en_indice]
    print(f"indice: {len(ids_indice):,} imagenes "
          f"({int((idx.split == args.split).sum() - len(ids_indice)):,} excluidas "
          f"por casi-duplicado)")

    long_ev = long[long.image_path.isin(set(ids_indice))]
    consultas = construir_consultas(
        long_ev, ids_indice, max_por_atributo=args.max_por_atributo,
        semilla=args.seed, col_id="image_path")
    print(f"consultas: {len(consultas):,}")
    for part in ("seen", "unseen"):
        m = consultas.particion == part
        print(f"  {part:7s}: {m.sum():>6,}  "
              f"({len(set(consultas.atributo[m]))} atributos distintos)")

    # --- matriz de embeddings por condicion y grupo ------------------------
    # Cada condicion aporta, para cada grupo de atributos, la matriz sobre la
    # que se ordena. Las condiciones compartidas usan la misma para todos los
    # grupos; las por_atributo usan la cabeza de su grupo.
    condiciones: dict[str, dict[str, np.ndarray]] = {}
    todos = lambda M: {g: M for g in GRUPOS_CABEZA}   # noqa: E731

    condiciones["1_aleatorio"] = todos(V_ev)          # se sortea en evaluar()
    condiciones["2_clip_plano"] = todos(V_ev)

    # PCA ajustado SOLO en train: ajustarlo sobre test seria mirar los datos
    # de evaluacion para construir el baseline.
    from sklearn.decomposition import PCA
    tren = (idx.split == "train").to_numpy()
    pca = PCA(n_components=128, random_state=args.seed)
    pca.fit(V[tren] / np.linalg.norm(V[tren], axis=1, keepdims=True))
    V_pca = pca.transform(V_ev / np.linalg.norm(V_ev, axis=1, keepdims=True))
    condiciones["3_clip_pca128"] = todos(V_pca.astype(np.float32))
    print(f"PCA: varianza explicada acumulada "
          f"{pca.explained_variance_ratio_.sum() * 100:.1f} %")

    # Las condiciones entrenadas se DESCUBREN mirando el disco, no una lista
    # fija de sufijos. Con la lista fija, cualquier corrida con --sufijo (por
    # ejemplo la ablation de presupuesto de datos) se entrenaba y luego el
    # evaluador la ignoraba en silencio: la tabla salia identica y parecia que
    # el experimento no habia cambiado nada.
    for d in sorted(args.experimentos.iterdir()):
        if not d.is_dir() or d.name.startswith("resultados"):
            continue
        f = d / "cabeza_conjunta.pt"
        if f.exists():
            m = cargar_cabeza(f, V.shape[1], dev)
            condiciones[f"4_{d.name}"] = todos(proyectar(m, V_ev, dev))
            continue
        porg = {}
        for g in GRUPOS_CABEZA:
            fg = d / f"cabeza_{g}.pt"
            if fg.exists():
                porg[g] = proyectar(cargar_cabeza(fg, V.shape[1], dev), V_ev, dev)
        if porg:
            condiciones[f"5_{d.name}"] = porg
        elif not f.exists():
            print(f"  (aviso: {d.name} no contiene ninguna cabeza; se omite)")

    print(f"\ncondiciones a evaluar: {', '.join(sorted(condiciones))}")

    # --- evaluacion --------------------------------------------------------
    # Se evalua grupo a grupo porque las cabezas por atributo viven en
    # subespacios distintos, y se recomponen las filas al final. Las consultas
    # son las mismas para todas las condiciones, que es lo que hace pareada la
    # comparacion.
    resultados: dict[str, pd.DataFrame] = {}
    for nombre, por_grupo in sorted(condiciones.items()):
        trozos = []
        for g in GRUPOS_CABEZA:
            if g not in por_grupo:
                continue
            sel = np.flatnonzero(consultas.grupo == g)
            if not len(sel):
                continue
            sub = type(consultas)(
                q_idx=consultas.q_idx[sel], atributo=consultas.atributo[sel],
                grupo=consultas.grupo[sel], particion=consultas.particion[sel],
                relevantes=[consultas.relevantes[i] for i in sel])
            df = evaluar(por_grupo[g], sub, condicion=nombre,
                         semilla_aleatoria=(args.seed if "aleatorio" in nombre
                                            else None))
            # consulta_id global, para que el emparejamiento entre condiciones
            # sea el mismo aunque cada grupo se evalue por separado.
            df["consulta_id"] = sel
            trozos.append(df)
        resultados[nombre] = pd.concat(trozos, ignore_index=True)
        r = resultados[nombre]
        print(f"  {nombre:22s} {args.metrica} = {r[args.metrica].mean():.4f}  "
              f"(seen {r.loc[r.particion=='seen', args.metrica].mean():.4f} / "
              f"unseen {r.loc[r.particion=='unseen', args.metrica].mean():.4f})")

    dest = args.experimentos / f"resultados_{args.split}"
    dest.mkdir(parents=True, exist_ok=True)
    pd.concat(resultados.values(), ignore_index=True).to_parquet(
        dest / "metricas_por_consulta.parquet", index=False)

    # --- tablas comparativas ----------------------------------------------
    ref = "4_conjunta" if "4_conjunta" in resultados else "2_clip_plano"
    for referencia in dict.fromkeys([ref, "2_clip_plano"]):
        if referencia not in resultados:
            continue
        print(f"\n{'=' * 78}\nDIFERENCIA PAREADA frente a {referencia} "
              f"({args.metrica}, IC95 bootstrap)\n{'=' * 78}")
        for corte in ("particion", "attr_group"):
            t = tabla_comparativa(resultados, referencia, metrica=args.metrica,
                                  por=corte, n_boot=args.n_boot, semilla=args.seed)
            cols = ["condicion", corte, "media_a", "media_b", "diferencia",
                    "ic_bajo", "ic_alto", "significativo"]
            print(f"\n-- por {corte} --")
            print(t[cols].to_string(index=False,
                                    float_format=lambda v: f"{v:+.4f}"))
            t.to_csv(dest / f"comparativa_{referencia}_{corte}.csv", index=False)

    print(f"\nresultados en {dest}")
    print("\nLECTURA: la tesis del proyecto se sostiene si 5_por_atributo supera a\n"
          "4_conjunta con el intervalo de confianza sin cruzar el cero, y sobre\n"
          "todo en las consultas UNSEEN. Batir a 2_clip_plano no basta.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
