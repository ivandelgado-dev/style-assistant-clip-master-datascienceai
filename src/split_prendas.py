"""
Paso 4a — Split disjoint del corpus (protocolo §3).

Reparte el corpus en train / val / test de forma que ninguna prenda —ni nada
suficientemente parecido a ella— aparezca en dos particiones.

Por que el grupo es la CARPETA de producto y no la imagen
---------------------------------------------------------
Las rutas de DeepFashion son `img/<grupo_de_estilo>/img_XXXXXXXX.jpg`. Medido
sobre los embeddings del corpus masculino:

    coseno medio DENTRO de carpeta : 0,740
    coseno medio ENTRE  carpetas   : 0,684
    pares internos con coseno > 0,95 : 0,1 %

O sea que una carpeta NO son fotos repetidas de la misma prenda: son prendas
distintas del mismo estilo (`Floral_Print_Blazer` reune ~179 blazers floreados
diferentes). El duplicado literal es raro.

Aun asi el split va por carpeta, por una razon distinta y mas importante: las
carpetas concentran las etiquetas. En `Floral_Print_Blazer`, `floral` aparece
en 155 de sus imagenes y `floral print` en 133. Con un split por imagen, una
consulta de test por `floral` recuperaria compañeras de carpeta que el modelo
ya vio en entrenamiento, con el mismo estilo y la misma etiqueta. No es fuga de
duplicados, es fuga de grupo de estilo — y basta para inflar el Recall@k.

Repartir por carpeta es la opcion conservadora y es la que responde a la
pregunta del proyecto: generalizar a prendas NUNCA vistas.

Ademas se hace una pasada de casi-duplicados ENTRE carpetas (misma prenda
listada dos veces bajo nombres distintos). Las carpetas unidas por un par por
encima del umbral se fusionan en un solo grupo y van juntas.

Uso
---
    python src/split_prendas.py --out data/processed
    python src/split_prendas.py --out data/processed --por-imagen   # ablation
"""

from __future__ import annotations

import argparse
import pathlib

import numpy as np
import pandas as pd
import yaml


def union_find(n: int, pares) -> np.ndarray:
    padre = list(range(n))

    def raiz(x: int) -> int:
        while padre[x] != x:
            padre[x] = padre[padre[x]]
            x = padre[x]
        return x

    for i, j in pares:
        ri, rj = raiz(int(i)), raiz(int(j))
        if ri != rj:
            padre[ri] = rj
    return np.array([raiz(i) for i in range(n)])


def pares_casi_duplicados(
    V: np.ndarray, categorias: np.ndarray, umbral: float, chunk: int = 512
) -> list[tuple[int, int]]:
    """Pares de imagenes con coseno >= umbral, DENTRO de la misma categoria.

    Solo tiene sentido comparar dentro de categoria: una camiseta y un pantalon
    nunca son el mismo articulo, y restringirlo convierte un problema de 155k x
    155k en varios mucho menores.

    Se calcula por bloques y se guardan solo los indices que superan el umbral,
    nunca la matriz completa: 155.369^2 en float32 son 96 GB.
    """
    pares: list[tuple[int, int]] = []
    for cat in pd.unique(categorias):
        idx = np.flatnonzero(categorias == cat)
        if len(idx) < 2:
            continue
        Vc = V[idx]
        for ini in range(0, len(idx), chunk):
            fin = min(ini + chunk, len(idx))
            S = Vc[ini:fin] @ Vc.T
            # Solo la mitad superior, para no contar cada par dos veces.
            for r in range(fin - ini):
                fila = S[r]
                glob = ini + r
                cand = np.flatnonzero(fila >= umbral)
                cand = cand[cand > glob]
                for c in cand:
                    pares.append((idx[glob], idx[c]))
    return pares


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--corpus", type=pathlib.Path,
                   default=pathlib.Path("data/processed/corpus.parquet"))
    p.add_argument("--embeddings", type=pathlib.Path,
                   default=pathlib.Path("data/embeddings"))
    p.add_argument("--out", type=pathlib.Path,
                   default=pathlib.Path("data/processed"))
    p.add_argument("--umbral-dup", type=float, default=0.98,
                   help="Coseno a partir del cual dos imagenes se consideran "
                        "el mismo articulo listado dos veces")
    p.add_argument("--min-pares-fusion", type=int, default=10,
                   help="Numero minimo de pares duplicados entre dos carpetas "
                        "para fusionarlas. Con 1 el enlace simple encadena y "
                        "colapsa el corpus entero")
    p.add_argument("--frac-val", type=float, default=0.15)
    p.add_argument("--frac-test", type=float, default=0.15)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--por-imagen", action="store_true",
                   help="ABLATION: reparte por imagen en vez de por carpeta. "
                        "Produce fuga de grupo de estilo; sirve para medir "
                        "cuanto infla el resultado, no para el experimento")
    args = p.parse_args()

    rng = np.random.default_rng(args.seed)
    corpus = pd.read_parquet(args.corpus)
    idx_emb = pd.read_parquet(args.embeddings / "embeddings_index.parquet")
    V = np.load(args.embeddings / "embeddings.npy")

    # El orden de embeddings.npy manda: se reordena el corpus para que la
    # fila i de V corresponda a la fila i de la tabla. Asumir que ya coinciden
    # es la clase de error que no lanza excepcion.
    corpus = idx_emb.merge(corpus, on="image_path", how="left")
    if corpus["categoria"].isna().any():
        raise SystemExit("Hay imagenes con embedding que no estan en el corpus.")
    if len(corpus) != len(V):
        raise SystemExit(f"{len(corpus)} filas frente a {len(V)} vectores.")

    corpus["carpeta"] = corpus.image_path.str.split("/").str[1]
    Vn = (V / np.linalg.norm(V, axis=1, keepdims=True)).astype(np.float32)
    print(f"corpus: {len(corpus):,} imagenes, {corpus.carpeta.nunique():,} carpetas, "
          f"{corpus.categoria.nunique()} categorias")

    if args.por_imagen:
        print("\n*** ABLATION por imagen: hay fuga de grupo de estilo por diseño ***")
        corpus["grupo"] = np.arange(len(corpus))
    else:
        print(f"\nbuscando casi-duplicados entre carpetas (coseno >= {args.umbral_dup}) ...")
        pares = pares_casi_duplicados(Vn, corpus.categoria.to_numpy(), args.umbral_dup)
        # Solo interesan los pares que CRUZAN carpetas: los de dentro ya van
        # juntos por construccion.
        carp = corpus.carpeta.to_numpy()
        cruzados = [(i, j) for i, j in pares if carp[i] != carp[j]]
        print(f"  pares por encima del umbral: {len(pares):,} "
              f"({len(cruzados):,} cruzan carpetas)")

        carpetas = sorted(corpus.carpeta.unique())
        pos_carp = {c: i for i, c in enumerate(carpetas)}

        # Cuantos pares duplicados hay entre CADA par de carpetas.
        #
        # Fusionar dos carpetas por UN solo par sobre el umbral es un error:
        # union-find es enlace simple, asi que A-B y B-C arrastran A, B y C
        # enteras, con sus cientos de imagenes que no son duplicadas de nada.
        # Con 4.168 pares cruzados eso colapso 3.272 carpetas en 889 grupos.
        #
        # Un unico par proximo entre dos grupos de estilo es ruido esperable
        # en un espacio donde el coseno medio ya es 0,68. Que compartan DECENAS
        # de pares casi identicos si es evidencia de ser la misma linea de
        # producto listada dos veces.
        from collections import Counter
        cuenta = Counter()
        for i, j in cruzados:
            a, b = pos_carp[carp[i]], pos_carp[carp[j]]
            cuenta[(min(a, b), max(a, b))] += 1

        vals = np.array(sorted(cuenta.values()))
        print(f"  pares de carpetas conectadas: {len(cuenta):,}")
        print(f"  duplicados por pareja: mediana {np.median(vals):.0f}, "
              f"p90 {np.percentile(vals, 90):.0f}, max {vals.max()}")
        print(f"  parejas con >= {args.min_pares_fusion} duplicados: "
              f"{int((vals >= args.min_pares_fusion).sum()):,}")

        aristas = {k for k, v in cuenta.items() if v >= args.min_pares_fusion}
        comp = union_find(len(carpetas), aristas)
        mapa = {c: int(comp[pos_carp[c]]) for c in carpetas}
        corpus["grupo"] = corpus.carpeta.map(mapa)
        fusionadas = len(carpetas) - len(set(comp))
        print(f"  carpetas fusionadas: {fusionadas} "
              f"-> {len(set(comp)):,} grupos")

        tam = corpus.groupby("grupo").size()
        print(f"  imagenes por grupo: mediana {tam.median():.0f}, "
              f"max {tam.max():,} ({100 * tam.max() / len(corpus):.1f} % del corpus)")
        if tam.max() > 0.10 * len(corpus):
            print("  AVISO: un grupo se lleva mas del 10 % del corpus. El "
                  "encadenamiento sigue siendo excesivo; sube --min-pares-fusion.")

    # --- reparto de GRUPOS, estratificado por categoria --------------------
    # La estratificacion evita que una categoria entera caiga en un solo lado
    # y deje sin test a media taxonomia.
    g = (corpus.groupby("grupo")
         .agg(categoria=("categoria", "first"), n=("image_path", "size"))
         .reset_index())
    print(f"\ngrupos a repartir: {len(g):,}")

    # El reparto se hace por NUMERO DE IMAGENES, no por numero de grupos.
    #
    # Los grupos son muy desiguales (de 1 a varios miles de imagenes). Repartir
    # el 15 % de los grupos no reparte el 15 % de las imagenes: en la primera
    # version salio val con 29.937 imagenes y test con 7.856, cuando ambos
    # tenian 135 grupos. Un test cuatro veces mas pequeño que val no es lo que
    # se declaro, y encima estrecha el indice de recuperacion justo donde se
    # miden los resultados.
    #
    # Se asigna de forma voraz: los grupos van, de mayor a menor, a la
    # particion que este mas lejos de su cuota. Empezar por los grandes es lo
    # que evita que el ultimo grupo enorme descuadre el reparto entero.
    split_grupo: dict[int, str] = {}
    objetivo = {"train": 1 - args.frac_val - args.frac_test,
                "val": args.frac_val, "test": args.frac_test}

    for cat, bloque in g.groupby("categoria"):
        bloque = bloque.sample(frac=1.0, random_state=args.seed)   # desempate aleatorio
        bloque = bloque.sort_values("n", ascending=False, kind="stable")
        total = bloque.n.sum()
        acum = {k: 0 for k in objetivo}
        # Con muy pocos grupos no se pueden cubrir las tres particiones; se
        # deja constancia en el aviso final en lugar de inventar un reparto.
        for gid, n_img in zip(bloque.grupo, bloque.n):
            deficit = {k: objetivo[k] * total - acum[k] for k in objetivo}
            destino = max(deficit, key=deficit.get)
            split_grupo[int(gid)] = destino
            acum[destino] += n_img

    corpus["split"] = corpus.grupo.map(split_grupo)

    # --- comprobaciones ----------------------------------------------------
    cruce = corpus.groupby("grupo").split.nunique()
    if (cruce > 1).any():
        raise SystemExit(f"ERROR: {int((cruce > 1).sum())} grupos a caballo "
                         f"entre particiones.")

    print("\nreparto de IMAGENES:")
    print(corpus.split.value_counts().to_string())
    print("\nreparto de GRUPOS:")
    print(g.assign(split=g.grupo.map(split_grupo)).split.value_counts().to_string())

    faltan = [c for c, b in corpus.groupby("categoria")
              if b.split.nunique() < 3]
    if faltan:
        print(f"\nAVISO: categorias sin las 3 particiones: {faltan}")
        print("  (son las de muy pocos grupos; se reportan aparte en errores)")

    # --- casi-duplicados que quedan a caballo entre particiones ------------
    # Fusionar las carpetas enteras era desproporcionado (un par aislado no
    # convierte dos grupos de estilo en el mismo producto), pero la imagen
    # concreta si es un problema: si su gemela esta en train, recuperarla en
    # test no demuestra generalizacion. Se marca para excluirla del INDICE de
    # evaluacion, no del entrenamiento.
    #
    # Es la version quirurgica de lo que el protocolo §3 pide, sin el efecto
    # colateral del enlace simple.
    corpus["excluir_indice"] = False
    if not args.por_imagen and cruzados:
        sp = corpus.split.to_numpy()
        fuera: set[int] = set()
        n_train_eval = n_val_test = 0

        for i, j in cruzados:
            a, b = sp[i], sp[j]
            if a == b:
                continue
            if "train" in (a, b):
                # Caso grave: la gemela esta en entrenamiento. Recuperarla en
                # evaluacion no demuestra generalizacion, demuestra memoria.
                k = i if a != "train" else j
                fuera.add(int(k))
                n_train_eval += 1
            else:
                # val <-> test. Mas leve: no hay fuga desde entrenamiento, pero
                # el test dejaria de ser independiente del conjunto con el que
                # se selecciona modelo. Se saca solo el lado de TEST, que es el
                # que tiene que quedar limpio; val puede convivir con ello.
                k = i if a == "test" else j
                fuera.add(int(k))
                n_val_test += 1

        corpus.loc[list(fuera), "excluir_indice"] = True
        n_ev = int((corpus.split != "train").sum())
        print(f"\ncasi-duplicados a caballo entre particiones:")
        print(f"  train <-> val/test : {n_train_eval:,} pares  (fuga desde "
              f"entrenamiento; se excluye el lado de evaluacion)")
        print(f"  val <-> test       : {n_val_test:,} pares  (independencia del "
              f"test; se excluye solo el lado de test)")
        print(f"  total marcadas 'excluir_indice': {len(fuera):,} "
              f"({100 * len(fuera) / max(n_ev, 1):.2f} % de val+test)")
        print("  se quitan del indice de evaluacion; siguen disponibles para entrenar")

    cols = ["image_path", "categoria", "carpeta", "grupo", "split", "excluir_indice"]
    corpus[cols].to_parquet(args.out / "splits.parquet", index=False)

    cfg = {
        "modo": "por_imagen" if args.por_imagen else "por_carpeta",
        "umbral_dup": args.umbral_dup,
        "frac_val": args.frac_val,
        "frac_test": args.frac_test,
        "seed": args.seed,
        "n_imagenes": int(len(corpus)),
        "n_grupos": int(corpus.grupo.nunique()),
        "min_pares_fusion": args.min_pares_fusion,
        "reparto_imagenes": corpus.split.value_counts().to_dict(),
        "n_excluidas_indice": int(corpus.excluir_indice.sum()),
    }
    with open(args.out / "config_split.yaml", "w", encoding="utf-8") as fh:
        yaml.safe_dump(cfg, fh, allow_unicode=True, sort_keys=False)
    print(f"\nsplits.parquet escrito. Ningun grupo cruza particiones.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
