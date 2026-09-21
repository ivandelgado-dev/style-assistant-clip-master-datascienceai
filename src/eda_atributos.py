"""
Paso 2 del plan — EDA de atributos de DeepFashion.

Responde a las tres preguntas que bloquean el entrenamiento:

  1. ¿Cuántos atributos son entrenables tras filtrar los poco frecuentes?
  2. ¿Cómo se reparten por tipo, y hay señal de color? (decide si la cabeza
     de color existe)
  3. ¿Qué atributos se reservan como UNSEEN (held-out) según el protocolo?

NO necesita las imágenes. Solo los ficheros de anotación:
    <data_root>/anno/list_attr_cloth.txt
    <data_root>/anno/list_attr_img.txt

Uso:
    python eda_atributos.py --data-root data/raw/deepfashion --out data/processed

Salidas:
    attrs_meta.parquet  — un registro por atributo: nombre, tipo, frecuencia,
                          si se conserva, y partición SEEN/UNSEEN
    attrs_long.parquet  — formato largo (imagen, atributo) solo de positivos
                          de atributos conservados. Alimenta garment_attributes
    heldout.yaml        — la lista de held-out, congelada. Se versiona en git
    cooc_flags.csv      — pares held-out / seen con solapamiento alto, que hay
                          que reportar aparte en la memoria
"""

from __future__ import annotations

import argparse
import pathlib

import numpy as np
import pandas as pd
import yaml

# Tipos de atributo según la documentación de DeepFashion (list_attr_cloth.txt,
# segunda columna). Verificado contra la descripción oficial del formato.
# Nótese que NO hay tipo "color": esa es exactamente la razón por la que la
# cabeza de color no tiene supervisión en este corpus.
TIPOS = {
    1: "textura",
    2: "tejido",
    3: "forma",     # -> mapea a "corte" en la nomenclatura del proyecto
    4: "partes",
    5: "estilo",
}

# Grupos que se entrenan como cabezas. Los tipos no listados se analizan pero
# no generan cabeza. Revisado tras la primera corrida: 'estilo' queda fuera
# (summer, classic, love, shopping, party: ruido de descripciones de producto).
GRUPOS_CABEZA = {"forma": "corte", "textura": "textura", "tejido": "tejido"}

# ---------------------------------------------------------------------------
# Filtro de categorías: el alcance del proyecto es ropa de hombre
# ---------------------------------------------------------------------------
# DeepFashion está dominado por ropa de mujer: 'Dress' solo es el 25 % del
# corpus. Sin filtrar, la cabeza de corte se entrena sobre siluetas (maxi,
# bodycon, skater, mini) que no existen en el armario masculino de evaluación,
# y la caída de rendimiento sobre ese armario mezclaría dos desplazamientos
# distintos: el fotográfico (estudio -> móvil), que es el que se quiere medir, y
# el de género de prenda, que sería un artefacto de no haber filtrado.
#
# El filtro se aplica ANTES de calcular frecuencias, porque el ranking de los
# 250 atributos más frecuentes cambia al filtrar.
#
# La clasificación es un juicio explícito y auditable, no un dato del dataset:
# DeepFashion no trae campo de género.

CATEGORIAS_HOMBRE = {
    # upper
    "Anorak", "Blazer", "Bomber", "Button-Down", "Cardigan", "Flannel",
    "Henley", "Hoodie", "Jacket", "Jersey", "Parka", "Peacoat", "Sweater",
    "Tee", "Turtleneck",
    # lower
    "Chinos", "Cutoffs", "Jeans", "Joggers", "Shorts", "Sweatpants",
    "Sweatshorts", "Trunks",
    # full
    "Coat",
}

# Ambiguas: existen en ropa de hombre pero en DeepFashion tienden a uso
# femenino. Se incluyen por defecto y se pueden excluir con --sin-dudosas,
# para poder medir si cambian algo en vez de discutirlo.
CATEGORIAS_DUDOSAS = {"Tank", "Top", "Robe", "Onesie", "Poncho"}


def leer_categorias(anno: pathlib.Path) -> tuple[list[str], np.ndarray]:
    """Lee list_category_cloth.txt y list_category_img.txt.

    Devuelve (nombres de categoría, id de categoría por imagen). Los ids del
    fichero son 1-based; se devuelven tal cual y se restan al indexar.
    """
    lineas = (anno / "list_category_cloth.txt").read_text(
        encoding="utf-8", errors="replace"
    ).splitlines()
    n_cats = int(lineas[0].strip())
    nombres = [l.rsplit(maxsplit=1)[0].strip() for l in lineas[2:] if l.strip()]
    if len(nombres) != n_cats:
        raise ValueError(
            f"list_category_cloth.txt declara {n_cats} categorias, "
            f"se parsearon {len(nombres)}."
        )

    etiquetas = []
    with open(anno / "list_category_img.txt", encoding="utf-8",
              errors="replace") as f:
        n_imgs = int(next(f).strip())
        next(f)
        for linea in f:
            if linea.strip():
                etiquetas.append(int(linea.rsplit(maxsplit=1)[1]))
    if len(etiquetas) != n_imgs:
        raise ValueError(
            f"list_category_img.txt declara {n_imgs} imagenes, "
            f"se leyeron {len(etiquetas)}."
        )
    return nombres, np.asarray(etiquetas, dtype=np.int32)


# ---------------------------------------------------------------------------
# Lectura de anotaciones
# ---------------------------------------------------------------------------

def leer_atributos_cloth(path: pathlib.Path) -> pd.DataFrame:
    """Parsea list_attr_cloth.txt -> DataFrame(attr_name, attr_type).

    Formato: fila 1 = nº de atributos, fila 2 = nombres de columna, resto =
    "<nombre del atributo> <tipo>".

    El nombre del atributo CONTIENE ESPACIOS ("a line dress"), así que se
    parte por la derecha y solo una vez. Partir por la izquierda o por
    todos los espacios rompe silenciosamente ~la mitad de los nombres, y el
    error no da excepción: da atributos truncados. Es el fallo clásico con
    este fichero.
    """
    lineas = path.read_text(encoding="utf-8", errors="replace").splitlines()
    n_declarado = int(lineas[0].strip())

    filas = []
    for linea in lineas[2:]:
        linea = linea.rstrip()
        if not linea.strip():
            continue
        nombre, tipo = linea.rsplit(maxsplit=1)
        filas.append((nombre.strip(), int(tipo)))

    df = pd.DataFrame(filas, columns=["attr_name", "attr_type"])

    if len(df) != n_declarado:
        raise ValueError(
            f"list_attr_cloth.txt declara {n_declarado} atributos pero se "
            f"parsearon {len(df)}. No sigas: el orden de las columnas de "
            f"list_attr_img.txt es posicional y depende de este fichero."
        )

    df["attr_group"] = df["attr_type"].map(TIPOS)
    return df


def leer_atributos_img(
    path: pathlib.Path, n_attrs: int, verbose: bool = True
) -> tuple[np.ndarray, np.ndarray, dict[str, int]]:
    """Parsea list_attr_img.txt -> (nombres, matriz int8, recuento de valores).

    Formato: fila 1 = nº de imágenes, fila 2 = nombres de columna, resto =
    "<ruta imagen> <v1> <v2> ... <vN>".

    El README documenta tres valores: 1 = positivo, -1 = negativo, 0 = unknown.
    En la practica el fichero solo trae 1 y -1: el recuento devuelto lo verifica
    en cada ejecucion en vez de darlo por supuesto.

    Decisión de codificación: se considera POSITIVO solo el valor 1. El -1 no se
    usa como negativo fiable. Motivo, y conviene tenerlo claro para defenderlo:
    los atributos de DeepFashion se derivaron de descripciones de producto de
    tiendas online. Un -1 significa "esa palabra no aparecia en la descripcion",
    no "un anotador verifico que la prenda no lo tiene". Una blusa descrita como
    "floral blouse" recibe floral=1 y -1 en todo lo demas, incluido "sheer",
    aunque sea transparente. Es una hipotesis de mundo cerrado sobre texto
    scrapeado, y por eso la ausencia no es un negativo.

    Esto es lo que obliga a la pérdida contrastiva sobre positivos (entrega 3
    §8.2): la calidad del dato determina la función de pérdida, no al revés.

    Se lee EN STREAMING. El fichero real son ~888 MB: cargarlo entero con
    read_text() mas splitlines() pasa de 2 GB de RAM solo en las cadenas, antes
    de tocar la matriz. Iterando por linea, el pico es la matriz int8
    (289.222 x 1.000 = ~290 MB) mas una linea.
    """
    with open(path, encoding="utf-8", errors="replace") as f:
        n_imgs = int(next(f).strip())
        next(f)  # fila de nombres de columna

        nombres = np.empty(n_imgs, dtype=object)
        matriz = np.zeros((n_imgs, n_attrs), dtype=np.int8)
        recuento: dict[str, int] = {}
        i = 0

        for linea in f:
            if not linea.strip():
                continue
            if i >= n_imgs:
                raise ValueError(
                    f"list_attr_img.txt declara {n_imgs} imagenes pero hay mas "
                    f"filas de datos. Fichero corrupto o cabecera incorrecta."
                )
            partes = linea.split()
            # La ruta de imagen no lleva espacios en este benchmark, pero se
            # ancla por la cola de todos modos: los N ultimos tokens son valores.
            corte = len(partes) - n_attrs
            if corte < 1:
                raise ValueError(
                    f"linea {i + 3}: se esperaban {n_attrs} valores y hay "
                    f"{len(partes) - 1}. ¿list_attr_cloth.txt de otra version?"
                )
            valores = partes[corte:]
            nombres[i] = " ".join(partes[:corte])

            for v in valores:
                recuento[v] = recuento.get(v, 0) + 1
            matriz[i] = np.fromiter(
                (1 if v == "1" else 0 for v in valores), dtype=np.int8, count=n_attrs
            )
            i += 1
            if verbose and i % 25_000 == 0:
                print(f"    {i:>7,} / {n_imgs:,}", flush=True)

    if i != n_imgs:
        raise ValueError(
            f"list_attr_img.txt declara {n_imgs} imagenes, se leyeron {i}."
        )

    return nombres, matriz, recuento


# ---------------------------------------------------------------------------
# Análisis
# ---------------------------------------------------------------------------

def resumen_por_tipo(meta: pd.DataFrame) -> pd.DataFrame:
    """Cuántos atributos y cuánta masa de etiquetas aporta cada tipo.

    Esta tabla es la que responde a la pregunta del color: si no hay tipo
    cromático, la cabeza de color no tiene de dónde aprender en este corpus.
    """
    return (
        meta.groupby("attr_group")
        .agg(
            n_atributos=("attr_name", "count"),
            n_conservados=("keep", "sum"),
            positivos_totales=("freq", "sum"),
            freq_mediana=("freq", "median"),
            freq_max=("freq", "max"),
        )
        .sort_values("n_conservados", ascending=False)
    )


def jaccard_pares(matriz: np.ndarray, idx: np.ndarray) -> np.ndarray:
    """Matriz de Jaccard entre atributos conservados.

    Se usa Jaccard y no co-ocurrencia bruta porque la co-ocurrencia premia a
    los atributos frecuentes: dos atributos muy comunes co-ocurren mucho sin
    ser sinónimos. Jaccard normaliza por la unión.

    Sirve para dos cosas:
      - ver si los tipos son separables o se solapan (hipótesis H2)
      - detectar casi-sinónimos al elegir los held-out
    """
    sub = matriz[:, idx].astype(np.float32)
    inter = sub.T @ sub
    conteos = sub.sum(axis=0)
    union = conteos[:, None] + conteos[None, :] - inter
    with np.errstate(divide="ignore", invalid="ignore"):
        jac = np.where(union > 0, inter / union, 0.0)
    np.fill_diagonal(jac, 0.0)
    return jac


def componentes_sinonimos(jac: np.ndarray, umbral: float) -> np.ndarray:
    """Agrupa atributos unidos por Jaccard alto en componentes conexas.

    Mismo principio que el `dup_group` de prendas del protocolo §3: las unidades
    correlacionadas van ENTERAS a un lado del split. Si `terry` queda de held-out
    y `french terry` en entrenamiento, la cabeza aprende el held-out de rebote y
    el numero UNSEEN —el que sostiene la contribucion— sale inflado.

    En la primera version esos pares solo se reportaban. Reportar no arregla
    nada: se agrupan y se reparten juntos.

    Union-find sin dependencias externas; el grafo tiene unos cientos de nodos.
    """
    n = jac.shape[0]
    padre = list(range(n))

    def raiz(x: int) -> int:
        while padre[x] != x:
            padre[x] = padre[padre[x]]
            x = padre[x]
        return x

    for i, j in zip(*np.where(np.triu(jac, k=1) >= umbral)):
        ri, rj = raiz(int(i)), raiz(int(j))
        if ri != rj:
            padre[ri] = rj

    return np.array([raiz(i) for i in range(n)])


def particion_seen_unseen(
    meta_keep: pd.DataFrame, frac_unseen: float, semilla: int
) -> pd.DataFrame:
    """Reparte cada grupo en SEEN / UNSEEN estratificando por frecuencia.

    La unidad de reparto es el COMPONENTE de sinonimos (columna `comp`), no el
    atributo suelto: asi ningun par de casi-sinonimos queda a caballo entre
    entrenamiento y evaluacion.

    No se muestrea al azar puro: hacen falta held-out frecuentes Y raros. Si
    todos los held-out caen en la cola rara, el test mide generalización a
    atributos sin senal en lugar de generalización de la nocion del grupo.

    Se estratifica en cuartiles de frecuencia dentro de cada grupo y se
    reserva la misma fracción de cada cuartil.
    """
    rng = np.random.default_rng(semilla)
    particion = pd.Series("seen", index=meta_keep.index, dtype=object)

    for grupo, bloque in meta_keep.groupby("attr_group"):
        # Con menos de 8 unidades, reservar el 20 % deja una o ninguna: el
        # numero no seria interpretable. Se deja el grupo entero como SEEN.
        #
        # Se avisa a gritos: un grupo sin held-out no tiene metrica UNSEEN, y
        # el UNSEEN es el que sostiene la contribucion. Descubrir eso al final
        # es quedarse sin el resultado que importa para ese grupo.
        #
        # Se colapsa a componentes: cada componente es una unidad indivisible.
        # Su frecuencia representativa es la maxima de sus miembros, para que
        # un componente con un atributo muy frecuente no caiga en el cuartil
        # bajo por arrastrar variantes raras.
        comps = bloque.groupby("comp")["freq"].max().sort_values(ascending=False)
        if len(comps) < 8:
            print(
                f"  AVISO: el grupo '{grupo}' tiene {len(comps)} componentes de "
                f"sinonimos (<8) sobre {len(bloque)} atributos. Se deja entero "
                f"como SEEN: NO habra metrica UNSEEN para este grupo."
            )
            continue

        cuartil = pd.qcut(comps, q=4, labels=False, duplicates="drop")
        for _, comps_cuartil in comps.groupby(cuartil).groups.items():
            comps_cuartil = np.array(list(comps_cuartil))
            n = max(1, int(round(len(comps_cuartil) * frac_unseen)))
            comps_elegidos = set(
                rng.choice(comps_cuartil, size=n, replace=False).tolist()
            )
            # Del componente elegido caen a UNSEEN TODOS sus atributos.
            indices = bloque.index[bloque["comp"].isin(comps_elegidos)]
            elegidos = np.array(list(indices))
            particion.loc[elegidos] = "unseen"

    # Un componente de sinonimos puede CRUZAR grupos ('palm' en textura,
    # 'tree' en estilo). El reparto de arriba es por grupo, asi que un
    # componente asi se parte y vuelve a aparecer el problema que los
    # componentes existian para evitar.
    #
    # Se resuelve en el lado conservador: cualquier componente que haya
    # quedado partido pasa ENTERO a SEEN. Encoger el conjunto UNSEEN es
    # aceptable; contaminarlo no lo es, porque UNSEEN es el numero que
    # sostiene la contribucion.
    partido = (
        pd.DataFrame({"comp": meta_keep["comp"].to_numpy(), "p": particion.to_numpy()})
        .groupby("comp")["p"]
        .nunique()
    )
    comps_partidos = set(partido[partido > 1].index)
    if comps_partidos:
        afectados = meta_keep["comp"].isin(comps_partidos).to_numpy()
        n = int((afectados & (particion.to_numpy() == "unseen")).sum())
        particion[afectados] = "seen"
        print(f"  {len(comps_partidos)} componente(s) quedaron partidos entre "
              f"grupos; pasan enteros a SEEN ({n} atributos salen de UNSEEN).")

    return particion


def flags_casi_sinonimos(
    jac: np.ndarray, nombres: list[str], particion: list[str], umbral: float
) -> pd.DataFrame:
    """Held-out que tienen un casi-sinónimo entre los SEEN.

    No es leakage: generalizar por correlación semántica es justo lo que se
    quiere medir. Pero un held-out con un gemelo en entrenamiento es un test
    más fácil de lo que aparenta, y hay que reportarlo aparte para que el
    número no se lea como más fuerte de lo que es.
    """
    filas = []
    part = np.array(particion)
    idx_unseen = np.where(part == "unseen")[0]
    idx_seen = np.where(part == "seen")[0]

    for i in idx_unseen:
        for j in idx_seen:
            if jac[i, j] >= umbral:
                filas.append(
                    {
                        "heldout": nombres[i],
                        "seen_similar": nombres[j],
                        "jaccard": round(float(jac[i, j]), 4),
                    }
                )
    cols = ["heldout", "seen_similar", "jaccard"]
    if not filas:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(filas).sort_values("jaccard", ascending=False)


# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data-root", type=pathlib.Path, required=True,
                   help="Directorio de DeepFashion (contiene Anno_coarse/, Anno_fine/, Eval/)")
    p.add_argument("--anno-dir", default="Anno_coarse",
                   help="Subcarpeta de anotaciones. 'Anno_coarse' son los 1.000 "
                        "atributos toscos (el experimento principal); 'Anno_fine' "
                        "son 26 mejor etiquetados (control de robustez)")
    p.add_argument("--out", type=pathlib.Path, default=pathlib.Path("data/processed"))
    p.add_argument("--top-n", type=int, default=250,
                   help="Nº de atributos más frecuentes a conservar (práctica de la literatura)")
    p.add_argument("--min-freq", type=int, default=500,
                   help="Frecuencia mínima absoluta. Se aplica ADEMÁS del top-n")
    p.add_argument("--frac-unseen", type=float, default=0.20)
    p.add_argument("--jaccard-flag", type=float, default=0.30,
                   help="Umbral para considerar dos atributos casi-sinonimos")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--sin-filtro-hombre", dest="filtrar_hombre",
                   action="store_false",
                   help="Desactiva el filtro de categorias masculinas. Solo para "
                        "la ablation: sin filtro, un cuarto del corpus son vestidos")
    p.add_argument("--sin-dudosas", dest="incluir_dudosas", action="store_false",
                   help="Excluye tambien las categorias ambiguas "
                        f"({', '.join(sorted(CATEGORIAS_DUDOSAS))})")
    args = p.parse_args()

    anno = args.data_root / args.anno_dir
    if not anno.is_dir():
        candidatos = sorted(d.name for d in args.data_root.glob("Anno*") if d.is_dir())
        raise SystemExit(
            f"No existe {anno}. Subcarpetas de anotacion encontradas: {candidatos}"
        )
    args.out.mkdir(parents=True, exist_ok=True)

    print("Leyendo list_attr_cloth.txt ...")
    meta = leer_atributos_cloth(anno / "list_attr_cloth.txt")
    print(f"  {len(meta)} atributos, tipos presentes: {sorted(meta.attr_type.unique())}")

    print("Leyendo list_attr_img.txt (tarda, ~888 MB en streaming) ...")
    nombres_img, matriz, recuento = leer_atributos_img(
        anno / "list_attr_img.txt", len(meta)
    )
    print(f"  {matriz.shape[0]:,} imagenes x {matriz.shape[1]:,} atributos")

    # --- filtro de categorías masculinas -----------------------------------
    # Va ANTES de calcular frecuencias: el ranking de los 250 mas frecuentes
    # cambia al filtrar, y con el cambia la particion SEEN/UNSEEN.
    if args.filtrar_hombre:
        cat_nombres, cat_por_img = leer_categorias(anno)
        if len(cat_por_img) != matriz.shape[0]:
            raise SystemExit(
                f"Descuadre: {len(cat_por_img):,} etiquetas de categoria frente "
                f"a {matriz.shape[0]:,} filas de atributos. Los ficheros deben "
                f"venir de la misma version del dataset."
            )
        aceptadas = set(CATEGORIAS_HOMBRE)
        if args.incluir_dudosas:
            aceptadas |= CATEGORIAS_DUDOSAS
        ids_ok = {i + 1 for i, n in enumerate(cat_nombres) if n in aceptadas}

        desconocidas = aceptadas - set(cat_nombres)
        if desconocidas:
            raise SystemExit(
                f"Categorias listadas que no existen en el dataset: "
                f"{sorted(desconocidas)}. Revisa la lista del codigo."
            )

        mask = np.isin(cat_por_img, list(ids_ok))
        print(f"\nFiltro de ropa de hombre: {mask.sum():,} de {len(mask):,} "
              f"imagenes ({100 * mask.mean():.1f} %), "
              f"{len(ids_ok)} de {len(cat_nombres)} categorias"
              + ("" if args.incluir_dudosas else "  [sin dudosas]"))
        descartadas = pd.Series(cat_por_img[~mask]).value_counts().head(5)
        print("  descartadas por volumen: " + ", ".join(
            f"{cat_nombres[c - 1]} ({n:,})" for c, n in descartadas.items()))

        matriz = matriz[mask]
        nombres_img = nombres_img[mask]
        cat_corpus = cat_por_img[mask]
        cat_nombre_corpus = [cat_nombres[c - 1] for c in cat_corpus]
    else:
        print("\nSIN filtro de categoria: el corpus incluye ropa de mujer "
              "(Dress es el 25 %). Solo para la ablation de comparacion.")
        # La categoria se intenta leer igualmente, porque el analisis de
        # errores por categoria la necesita. Pero aqui NO es esencial: sin
        # filtro, el corpus esta definido sin ella. Si los ficheros no estan,
        # se avisa y se sigue, en vez de tumbar toda la corrida por un campo
        # accesorio. (Con filtro si es esencial y el fallo es duro.)
        try:
            cat_nombres, cat_por_img = leer_categorias(anno)
            cat_nombre_corpus = [cat_nombres[c - 1] for c in cat_por_img]
        except (FileNotFoundError, ValueError) as e:
            print(f"  (sin categorias: {e}. corpus.parquet ira sin ese campo)")
            cat_nombre_corpus = [""] * matriz.shape[0]

    total_celdas = sum(recuento.values())
    print("  valores encontrados: " + ", ".join(
        f"{v}={n:,} ({100 * n / total_celdas:.3f}%)"
        for v, n in sorted(recuento.items())
    ))
    if "0" not in recuento:
        print(
            "  El README documenta '0' = unknown, pero el fichero no lo usa: solo\n"
            "  1 y -1. Eso NO significa que los -1 sean negativos verificados —\n"
            "  las etiquetas salen de descripciones de producto, y -1 es 'la\n"
            "  palabra no aparecia'. Por eso solo se usan positivos."
        )
    pos_por_img = matriz.sum(axis=1)
    print(f"  atributos positivos por imagen: media {pos_por_img.mean():.2f}, "
          f"mediana {np.median(pos_por_img):.0f}, max {pos_por_img.max()}, "
          f"sin ninguno: {(pos_por_img == 0).sum():,}")

    # --- frecuencias y filtrado -------------------------------------------
    # `col` guarda la posicion de cada atributo EN LA MATRIZ, que es el orden
    # del fichero. Se fija ANTES de ordenar por frecuencia: en cuanto se hace
    # sort_values + reset_index, la posicion de la fila deja de coincidir con
    # la columna de la matriz, y usar el indice del DataFrame para indexar la
    # matriz asigna nombres de atributo equivocados a los datos. No lanza
    # ninguna excepcion: solo produce resultados falsos.
    meta["col"] = np.arange(len(meta))
    meta["freq"] = matriz.sum(axis=0)
    meta = meta.sort_values("freq", ascending=False).reset_index(drop=True)

    top = meta.index < args.top_n
    meta["keep"] = top & (meta["freq"] >= args.min_freq)
    print(f"\nConservados: {int(meta.keep.sum())} atributos "
          f"(top-{args.top_n} y freq >= {args.min_freq})")

    # --- pregunta del color ------------------------------------------------
    print("\n=== Reparto por tipo de atributo ===")
    print(resumen_por_tipo(meta).to_string())
    print(
        "\nDeepFashion no define un tipo cromatico. Si esta tabla lo confirma,\n"
        "la cabeza de color no tiene supervision aqui y hay dos salidas:\n"
        "  (a) suprimirla y justificarlo (H1 predice que CLIP ya va bien en color)\n"
        "  (b) supervisarla con baseColour de Fashion Product Images, asumiendo\n"
        "      que es otro corpus con otra distribucion visual.\n"
    )

    # --- co-ocurrencia (H2) ------------------------------------------------
    keep_idx = meta.index[meta.keep].to_numpy()      # filas de meta
    meta_keep = meta.loc[keep_idx]
    cols_matriz = meta_keep["col"].to_numpy()        # columnas de la matriz
    jac = jaccard_pares(matriz, cols_matriz)
    nombres_keep = meta_keep.attr_name.tolist()

    # Componentes de casi-sinonimos: se reparten enteros en el split.
    comp = componentes_sinonimos(jac, args.jaccard_flag)
    meta.loc[keep_idx, "comp"] = comp
    meta_keep = meta.loc[keep_idx]
    n_agrupados = len(comp) - len(set(comp))
    if n_agrupados:
        print(f"=== Componentes de sinonimos (Jaccard >= {args.jaccard_flag}) ===")
        por_comp = pd.Series(nombres_keep).groupby(comp).apply(list)
        for miembros in por_comp[por_comp.map(len) > 1]:
            print(f"  {miembros}")
        print(f"  {n_agrupados} atributos absorbidos en componentes. Cada "
              f"componente va entero a SEEN o entero a UNSEEN.\n")

    grupos = meta_keep.attr_group.to_numpy()
    print("=== Solapamiento de Jaccard dentro / entre grupos (H2) ===")
    print("  La MEDIA es poco informativa aqui: con ~3 atributos positivos por")
    print("  imagen, casi todos los pares no co-ocurren nunca y la media mide")
    print("  sobre todo la dispersion. Se dan tambien percentiles altos, que es")
    print("  donde estaria la estructura si la hubiera.\n")
    print(f"  {'grupo':10s} {'':>8s} {'media':>8s} {'p90':>8s} {'p99':>8s} {'max':>8s}")
    for g in pd.unique(grupos):
        dentro = jac[np.ix_(grupos == g, grupos == g)]
        fuera = jac[np.ix_(grupos == g, grupos != g)]
        # El triangulo superior evita contar cada par dos veces y la diagonal.
        d = dentro[np.triu_indices_from(dentro, k=1)]
        f = fuera.ravel()
        for etiqueta, v in (("dentro", d), ("fuera", f)):
            print(f"  {g:10s} {etiqueta:>8s} {v.mean():8.5f} "
                  f"{np.percentile(v, 90):8.5f} {np.percentile(v, 99):8.5f} "
                  f"{v.max():8.5f}")
    print(
        "\n  Si 'dentro' no supera a 'fuera' de forma consistente —sobre todo en\n"
        "  p99— los grupos no son separables por co-ocurrencia y la agrupacion\n"
        "  en cabezas se apoya solo en la taxonomia de los autores, no en los\n"
        "  datos. Es el riesgo nº1 de las entregas 3 y 4.\n"
        "  OJO: esto mide co-ocurrencia de ETIQUETAS, no separabilidad\n"
        "  perceptual. Que dos atributos de corte no aparezcan juntos no impide\n"
        "  que compartan subespacio visual. La prueba real es el retrieval.\n"
    )

    # --- particion SEEN / UNSEEN ------------------------------------------
    meta.loc[keep_idx, "particion"] = particion_seen_unseen(
        meta_keep, args.frac_unseen, args.seed
    )
    particion_keep = meta.loc[keep_idx, "particion"].tolist()

    print("=== Particion de atributos ===")
    print(meta.loc[keep_idx].groupby(["attr_group", "particion"]).size().to_string())

    flags = flags_casi_sinonimos(jac, nombres_keep, particion_keep, args.jaccard_flag)
    if len(flags):
        print(f"\n{len(flags)} pares held-out/seen con Jaccard >= {args.jaccard_flag}.")
        print("Se reportan aparte: el test sobre esos held-out es mas facil.")
        print(flags.head(10).to_string(index=False))
    flags.to_csv(args.out / "cooc_flags.csv", index=False)

    # --- salidas -----------------------------------------------------------
    meta.to_parquet(args.out / "attrs_meta.parquet", index=False)

    # corpus.parquet define QUE imagenes forman el corpus, y es la unica
    # fuente de verdad para los pasos siguientes. El extractor de embeddings
    # lee este fichero en vez de recalcular el filtro de categorias: si cada
    # script decidiera el corpus por su cuenta, bastaria con lanzar uno con
    # --sin-dudosas y otro sin ella para que el indice y las etiquetas
    # dejasen de corresponderse, sin que nada fallara.
    #
    # Incluye TODAS las imagenes del corpus, tambien las que no tienen ningun
    # atributo positivo: no pueden ser consulta, pero si deben estar en el
    # indice de recuperacion como candidatos legitimos.
    corpus = pd.DataFrame({
        "image_path": nombres_img,
        "categoria": cat_nombre_corpus,
        "n_atributos": matriz[:, cols_matriz].sum(axis=1),
    })
    corpus.to_parquet(args.out / "corpus.parquet", index=False)
    print(f"corpus.parquet: {len(corpus):,} imagenes "
          f"({(corpus.n_atributos == 0).sum():,} sin ningun atributo conservado; "
          f"entran en el indice pero no pueden ser consulta)")

    filas, cols = np.nonzero(matriz[:, cols_matriz])
    largo = pd.DataFrame(
        {
            "image_path": nombres_img[filas],
            "attr_name": np.array(nombres_keep)[cols],
            "attr_group": grupos[cols],
            "particion": np.array(particion_keep)[cols],
        }
    )

    # Verificacion de alineamiento. Recuenta las frecuencias desde la tabla
    # larga y las compara con las que se calcularon sobre la matriz. Si los
    # nombres y las columnas se desalinean, los totales coinciden pero el
    # reparto por atributo no: es el unico sitio donde ese fallo se ve.
    recalculo = largo.groupby("attr_name").size()
    esperado = meta_keep.set_index("attr_name")["freq"]
    comunes = esperado.index.intersection(recalculo.index)
    desviados = (recalculo[comunes] != esperado[comunes]).sum()
    if desviados or len(comunes) != len(esperado):
        raise SystemExit(
            f"ALINEAMIENTO ROTO: {desviados} atributos con frecuencia distinta "
            f"entre la matriz y la tabla larga ({len(comunes)}/{len(esperado)} "
            f"nombres en comun). Los nombres no corresponden a las columnas."
        )
    print(f"\nalineamiento verificado: {len(comunes)} atributos cuadran")

    largo.to_parquet(args.out / "attrs_long.parquet", index=False)
    print(f"attrs_long.parquet: {len(largo):,} positivos")

    heldout = (
        meta.loc[meta.particion == "unseen"]
        .groupby("attr_group")["attr_name"]
        .apply(list)
        .to_dict()
    )
    with open(args.out / "heldout.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(
            {
                "semilla": args.seed,
                "frac_unseen": args.frac_unseen,
                "top_n": args.top_n,
                "min_freq": args.min_freq,
                "heldout": heldout,
            },
            f,
            allow_unicode=True,
            sort_keys=False,
        )
    print("heldout.yaml escrito. VERSIONALO EN GIT: congela el protocolo.")


if __name__ == "__main__":
    main()
