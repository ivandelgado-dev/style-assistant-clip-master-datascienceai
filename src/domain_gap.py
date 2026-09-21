"""
Paso 7 — Medicion del domain gap: catalogo (DeepFashion) frente a armario real.

Por que este script es ahora el resultado principal
---------------------------------------------------
El resultado de modelado (docs/resultados_modelado.md) cerro la hipotesis
original: la proyeccion supervisada gana a CLIP plano, pero el desacoplamiento
por atributo solo mejora sobre el vocabulario con el que se entreno y esa
ventaja NO se transfiere a atributos nuevos. Es una mejora de especializacion,
no de representacion.

Lo que queda por medir, y que ningun trabajo de los que se citan mide con datos
propios, es si algo de eso sobrevive fuera del catalogo. Todo el entrenamiento y
toda la evaluacion se han hecho sobre fotografia de estudio. El producto recibe
fotos de movil. Este script mide ese salto.

Tres medidas, en este orden, porque cada una solo se puede leer a la luz de la
anterior:

  1. SUELO DE RUIDO. Cuanto se mueve el embedding de la MISMA prenda al
     recolocarla y volver a fotografiarla. Sin este numero, cualquier caida
     atribuida al dominio es indistinguible de la varianza de captura.

  2. SEPARABILIDAD DE DOMINIO. Si una sonda lineal distingue "foto de armario"
     de "foto de catalogo", el dominio esta escrito en el embedding y compite
     con la semantica de prenda por las mismas direcciones.

  3. DEGRADACION EN LA TAREA. Recuperacion de categoria con consulta de armario
     contra el indice de catalogo, frente a la misma medida con consulta de
     catalogo. La diferencia es el gap en unidades de lo que el producto hace.

Y las tres por partida doble: sobre CLIP plano y sobre cada proyeccion
entrenada. La pregunta interesante es si la proyeccion, entrenada UNICAMENTE
sobre catalogo, amplifica el gap. Si lo amplifica, es una limitacion real del
metodo y hay que decirlo; el protocolo prefiere un negativo bien medido a un
positivo mal medido.

Trampa evitada, y conviene tenerla a mano para el tribunal
-----------------------------------------------------------
La sonda de dominio tiene 512 caracteristicas y ~130 ejemplos por clase: p >> n.
Una regresion logistica separa dos conjuntos ALEATORIOS de puntos en 512
dimensiones casi perfectamente si se mide sobre los mismos datos con los que se
ajusto. Por eso:

  - el AUC se mide siempre en validacion cruzada, nunca en entrenamiento;
  - se repite sobre 20 submuestreos del catalogo, para no leer un accidente;
  - y se ejecuta un CONTROL con las etiquetas permutadas. Si el control no da
    ~0,50 el procedimiento esta roto y el numero principal no vale nada.

Uso
---
    python src/domain_gap.py \
        --emb-armario data/embeddings_armario \
        --armario-csv data/raw/wardrobe/armario.csv \
        --emb-corpus data/embeddings \
        --splits data/processed/splits.parquet \
        --experimentos experiments/conjunta experiments/por_atributo \
        --out experiments/domain_gap
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

import numpy as np
import pandas as pd
import yaml
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_score

# ---------------------------------------------------------------------------
# Mapeos de categoria, CONGELADOS antes de ver ningun resultado
# ---------------------------------------------------------------------------
# Los dos vocabularios no coinciden: DeepFashion etiqueta prendas de tienda con
# 50 categorias; la plantilla del armario usa la taxonomia de la entrega 3. Para
# comparar hace falta un vocabulario comun, y elegirlo DESPUES de ver los
# numeros seria elegir el que mejor queda.
#
# Granularidad: se agrupa hasta donde la distincion es observable en una foto.
# "Chinos" frente a "Joggers" frente a "Jeans" es una distincion de tejido y
# acabado que ni una persona resuelve con fiabilidad en una foto cenital de la
# prenda estirada; exigirsela al modelo mediria etiquetado, no representacion.
# Se colapsan en `pantalon_largo`. Lo mismo con las chaquetas.
#
# Fuera del vocabulario comun (mapeados a None):
#   Tank, Top, Poncho, Robe, Onesie  -> ambiguos o sin equivalente masculino
#                                       claro (ya marcados dudosos en el EDA)
#   Trunks                           -> bano; no esta en la taxonomia
#   polo, chaleco                    -> sin categoria equivalente en DeepFashion
#   calzado y accesorios             -> DeepFashion CAP no contiene calzado

GRUPO_DEEPFASHION: dict[str, str] = {
    "Tee": "camiseta", "Henley": "camiseta",
    "Button-Down": "camisa", "Flannel": "camisa",
    "Hoodie": "sudadera",
    "Sweater": "jersey", "Jersey": "jersey", "Turtleneck": "jersey",
    "Cardigan": "cardigan",
    "Blazer": "chaqueta", "Jacket": "chaqueta",
    "Bomber": "chaqueta", "Anorak": "chaqueta",
    "Coat": "abrigo", "Parka": "abrigo", "Peacoat": "abrigo",
    "Jeans": "pantalon_largo", "Chinos": "pantalon_largo",
    "Joggers": "pantalon_largo", "Sweatpants": "pantalon_largo",
    "Shorts": "pantalon_corto", "Cutoffs": "pantalon_corto",
    "Sweatshorts": "pantalon_corto",
}

GRUPO_ARMARIO: dict[str, str] = {
    "camiseta": "camiseta",
    "camisa": "camisa",
    "sudadera": "sudadera",
    "jersey": "jersey",
    "cardigan": "cardigan",
    "chaqueta": "chaqueta", "cazadora": "chaqueta", "blazer": "chaqueta",
    "abrigo": "abrigo",
    "pantalon": "pantalon_largo", "vaquero": "pantalon_largo",
    "chino": "pantalon_largo", "jogger": "pantalon_largo",
    "bermuda": "pantalon_corto",
}

# Granularidad gruesa: el slot de la entrega 3. Es la medida titular porque no
# admite discusion de etiquetado — una camisa no es un pantalon.
SLOT_DE_GRUPO: dict[str, str] = {
    "camiseta": "top", "camisa": "top", "sudadera": "top",
    "jersey": "top", "cardigan": "top",
    "chaqueta": "outer", "abrigo": "outer",
    "pantalon_largo": "bottom", "pantalon_corto": "bottom",
}


# ---------------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------------

def normalizar(x: np.ndarray) -> np.ndarray:
    """L2 por filas. Las cabezas ya normalizan; CLIP plano no."""
    n = np.linalg.norm(x, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return x / n


def cargar_embeddings(dirs: pathlib.Path) -> tuple[np.ndarray, list[str]]:
    """Consolida los shards de un directorio de embeddings.

    Acepta tanto el resultado de `--verificar` (embeddings.npy +
    embeddings_index.parquet) como los shards sueltos. Si estan las dos cosas se
    usa el consolidado, que es lo que se distribuye.
    """
    npy = dirs / "embeddings.npy"
    idx = dirs / "embeddings_index.parquet"
    if npy.exists() and idx.exists():
        vec = np.load(npy)
        rutas = pd.read_parquet(idx)["image_path"].tolist()
    else:
        vs, rs = [], []
        for f_idx in sorted(dirs.glob("idx_*.parquet")):
            n = int(f_idx.stem.split("_")[1])
            f_npy = dirs / f"emb_{n:05d}.npy"
            if not f_npy.exists():
                continue
            vs.append(np.load(f_npy))
            rs += pd.read_parquet(f_idx)["image_path"].tolist()
        if not vs:
            raise SystemExit(f"No hay embeddings en {dirs}")
        vec, rutas = np.concatenate(vs), rs
    if len(vec) != len(rutas):
        raise SystemExit(
            f"ALINEAMIENTO ROTO en {dirs}: {len(vec)} vectores y {len(rutas)} rutas"
        )
    return vec.astype(np.float32), rutas


def cargar_representaciones(dim_in: int, experimentos: list[pathlib.Path],
                            dev: str) -> dict[str, object]:
    """{nombre: None para CLIP plano, o una cabeza cargada}.

    torch solo se importa si hay experimentos que cargar: la medida sobre CLIP
    plano no lo necesita y asi el script corre en un entorno sin torch.
    """
    reps: dict[str, object] = {"clip_plano": None}
    if not experimentos:
        return reps

    import torch
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    from entrenar_proyecciones import Proyeccion

    for exp in experimentos:
        for pt in sorted(exp.glob("cabeza_*.pt")):
            ck = torch.load(pt, map_location=dev, weights_only=False)
            m = Proyeccion(dim_in, ck["dim"], mlp=ck["mlp"]).to(dev).eval()
            m.load_state_dict(ck["state_dict"])
            reps[f"{exp.name}/{pt.stem.replace('cabeza_', '')}"] = m
    return reps


def aplicar(rep, x: np.ndarray, dev: str, lote: int = 4096) -> np.ndarray:
    """Proyecta (o no) y devuelve vectores de norma unitaria."""
    if rep is None:
        return normalizar(x)
    import torch
    salida = []
    with torch.no_grad():
        for i in range(0, len(x), lote):
            t = torch.from_numpy(x[i:i + lote]).to(dev)
            salida.append(rep(t).cpu().numpy())
    return np.concatenate(salida).astype(np.float32)


# ---------------------------------------------------------------------------
# 1. Suelo de ruido
# ---------------------------------------------------------------------------

def suelo_de_ruido(vec: np.ndarray, prenda_id: np.ndarray, toma: np.ndarray,
                   semilla: int) -> dict[str, float] | None:
    """Coseno entre las dos tomas de la misma prenda, contra el nulo.

    Las tomas las da `pares.csv` (src/emparejar_tomas.py), no el nombre del
    fichero: las fotos salieron del movil con su propio nombre y renombrar 236
    ficheros a mano habria sido una fuente de errores silenciosos.

    El nulo son pares de prendas DISTINTAS del propio armario, y se toma UNA
    sola foto por prenda para construirlo. Si se sortease sobre las 236 fotos,
    de vez en cuando saldrian las dos tomas de la misma prenda y el nulo se
    contaminaria con justo lo que intenta servir de contraste.

    Comparar contra el nulo del catalogo tampoco valdria: mezclaria dominio con
    identidad de prenda y no mediria lo que queremos.
    """
    df = pd.DataFrame({"prenda_id": prenda_id, "toma": toma,
                       "i": np.arange(len(vec))})
    pares = [g["i"].to_numpy()[:2] for _, g in df.groupby("prenda_id")
             if len(g) >= 2]
    if not pares:
        return None

    mismos = np.array([float(vec[a] @ vec[b]) for a, b in pares])

    primeras = df.sort_values(["prenda_id", "toma"]).groupby("prenda_id").first()
    idx = primeras["i"].to_numpy()
    rng = np.random.default_rng(semilla)
    distintos = []
    for _ in range(5000):
        i, j = rng.choice(idx, 2, replace=False)
        distintos.append(float(vec[i] @ vec[j]))
    distintos = np.array(distintos)

    return {
        "n_pares": len(mismos),
        "cos_misma_prenda_mediana": float(np.median(mismos)),
        "cos_misma_prenda_p05": float(np.percentile(mismos, 5)),
        "cos_misma_prenda_min": float(mismos.min()),
        "cos_prendas_distintas_mediana": float(np.median(distintos)),
        "cos_prendas_distintas_p95": float(np.percentile(distintos, 95)),
        # Margen: cuanto separa la identidad de la prenda por encima del ruido
        # de recolocarla. Si es negativo o proximo a cero, dos fotos de la misma
        # camisa no estan mas cerca entre si que dos camisas cualesquiera, y
        # ninguna medida posterior significa nada.
        "margen": float(np.median(mismos) - np.percentile(distintos, 95)),
    }


# ---------------------------------------------------------------------------
# 2. Separabilidad de dominio
# ---------------------------------------------------------------------------

def emparejar_por_categoria(cat_armario: np.ndarray, cat_corpus: np.ndarray,
                            rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """Indices del armario y del catalogo con la MISMA composicion por categoria.

    Sin esto la sonda de dominio miente, y miente hacia arriba. El armario no
    tiene la mezcla de categorias de DeepFashion —donde una de cada cuatro
    imagenes es una camiseta— asi que una sonda entrenada sobre muestras sin
    emparejar separa los dos conjuntos leyendo QUE prendas hay, no COMO estan
    fotografiadas, y devuelve un AUC alto aunque el dominio sea identico.

    Se verifico simulando un armario sin ningun desplazamiento de dominio: sin
    emparejar daba AUC 0,80; emparejando, 0,50. El numero sin emparejar se
    guarda igualmente, marcado como confundido, porque explicar por que se
    descarta es parte del resultado.

    Las prendas sin categoria mapeable quedan fuera de esta medida.
    """
    ia, ic = [], []
    for g in pd.unique(cat_armario[pd.notna(cat_armario)]):
        cand = np.flatnonzero(cat_corpus == g)
        if len(cand) == 0:
            continue
        propias = np.flatnonzero(cat_armario == g)
        ia.extend(propias.tolist())
        ic.extend(rng.choice(cand, size=len(propias),
                             replace=len(cand) < len(propias)).tolist())
    return np.array(ia, dtype=int), np.array(ic, dtype=int)


def separabilidad(v_armario: np.ndarray, v_corpus: np.ndarray,
                  semilla: int, repeticiones: int = 20,
                  cat_armario: np.ndarray | None = None,
                  cat_corpus: np.ndarray | None = None) -> dict[str, float]:
    """AUC de una sonda lineal armario-vs-catalogo, en validacion cruzada.

    Se submuestrea el catalogo al tamano del armario en cada repeticion: con
    130 frente a 21.000 el AUC estaria dominado por el desequilibrio y no por
    la geometria.

    Si se pasan las categorias, el submuestreo ademas EMPAREJA la composicion
    (ver `emparejar_por_categoria`). Ese es el numero que vale.

    El control con etiquetas permutadas no es decorativo. Con p >> n es la
    unica forma de demostrar que el AUC alto significa algo.
    """
    rng = np.random.default_rng(semilla)
    n = len(v_armario)
    emparejado = cat_armario is not None and cat_corpus is not None
    aucs, aucs_control = [], []
    n_usado = n

    for r in range(repeticiones):
        if emparejado:
            ia, ic = emparejar_por_categoria(cat_armario, cat_corpus, rng)
            if len(ia) < 20:
                return {"error": "menos de 20 prendas con categoria mapeable"}
            n_usado = len(ia)
            X = np.concatenate([v_armario[ia], v_corpus[ic]])
            y = np.concatenate([np.ones(n_usado), np.zeros(n_usado)])
        else:
            sel = rng.choice(len(v_corpus), size=n, replace=False)
            X = np.concatenate([v_armario, v_corpus[sel]])
            y = np.concatenate([np.ones(n), np.zeros(n)])
        _sep_ajuste(X, y, semilla + r, aucs, aucs_control, rng)

    c_arm = normalizar(v_armario.mean(axis=0, keepdims=True))[0]
    c_cor = normalizar(v_corpus.mean(axis=0, keepdims=True))[0]

    return {
        "auc_media": float(np.mean(aucs)),
        "auc_sd": float(np.std(aucs)),
        "auc_control_media": float(np.mean(aucs_control)),
        "auc_control_sd": float(np.std(aucs_control)),
        "cos_centroides": float(c_arm @ c_cor),
        "emparejado_por_categoria": bool(emparejado),
        "n_por_clase": int(n_usado),
        "repeticiones": int(repeticiones),
    }


def nulos_de_catalogo(v_corpus: np.ndarray, cat_corpus: np.ndarray,
                      sub_corpus: np.ndarray, cuentas: dict[str, int],
                      semilla: int, repeticiones: int = 20) -> dict[str, float]:
    """Dos nulos construidos SOLO con catalogo. No hay dominio que detectar.

    `nulo_muestral`: las dos mitades se sortean al azar (y disjuntas) dentro de
    cada grupo. Es el suelo empirico del procedimiento.

    Ese suelo NO es 0,50 y no hay que corregirlo: medido sobre el corpus real
    con ~80-130 ejemplos por clase en 512 dimensiones, sale por DEBAJO de 0,50
    (~0,38 en las pruebas). Es el sesgo conocido de la validacion cruzada con
    p >> n: el clasificador se ajusta perfectamente a cada pliegue de
    entrenamiento y sus predicciones sobre el pliegue retenido quedan
    anticorreladas cuando no hay senal. Por eso el suelo se MIDE en vez de
    suponerse; dar por bueno el 0,50 teorico haria parecer senal a cualquier
    cosa por encima de 0,45.

    `nulo_composicion`: las dos mitades se sortean de SUBCATEGORIAS DISJUNTAS
    dentro de cada grupo (por ejemplo Jeans frente a Chinos dentro de
    pantalon_largo). Mide cuanto puede subir el AUC por diferencias de
    composicion fina, sin que cambie nada del dominio.

    Esto responde a la objecion evidente: el emparejamiento se hace al nivel de
    grupo, que es lo mas fino que permiten las etiquetas del armario, asi que
    dentro de un grupo las mezclas pueden seguir siendo distintas. Un AUC de
    dominio por debajo de `nulo_composicion` no demuestra nada.
    """
    rng = np.random.default_rng(semilla)
    res = {}

    for modo in ("muestral", "composicion"):
        aucs, control = [], []
        for r in range(repeticiones):
            ia, ib = [], []
            for g, n_g in cuentas.items():
                cand = np.flatnonzero(cat_corpus == g)
                if len(cand) < 4:
                    continue
                pa = pb = cand
                if modo == "muestral":
                    # Las dos mitades deben ser DISJUNTAS. Sortear las dos del
                    # mismo saco deja imagenes repetidas con etiqueta opuesta y
                    # hunde el AUC por debajo de 0,5: no es un nulo, es ruido
                    # contradictorio.
                    barajado = rng.permutation(cand)
                    corte = len(barajado) // 2
                    pa, pb = barajado[:corte], barajado[corte:]
                else:
                    subs = pd.Series(sub_corpus[cand]).value_counts().index.tolist()
                    if len(subs) < 2:
                        pa = pb = cand
                    else:
                        s_a = set(subs[0::2])
                        pa = cand[np.isin(sub_corpus[cand], list(s_a))]
                        pb = cand[~np.isin(sub_corpus[cand], list(s_a))]
                        if len(pa) == 0 or len(pb) == 0:
                            barajado = rng.permutation(cand)
                            corte = len(barajado) // 2
                            pa, pb = barajado[:corte], barajado[corte:]
                ia.extend(rng.choice(pa, n_g, replace=len(pa) < n_g).tolist())
                ib.extend(rng.choice(pb, n_g, replace=len(pb) < n_g).tolist())
            if len(ia) < 20:
                break
            X = np.concatenate([v_corpus[ia], v_corpus[ib]])
            y = np.concatenate([np.ones(len(ia)), np.zeros(len(ib))])
            _sep_ajuste(X, y, semilla + r, aucs, control, rng)
        res[f"auc_nulo_{modo}"] = float(np.mean(aucs)) if aucs else float("nan")
    return res


def _sep_ajuste(X, y, estado, aucs, aucs_control, rng) -> None:
    """Un ajuste con CV mas su control permutado. Extraido para no repetirlo."""
    for destino, etiquetas in ((aucs, y), (aucs_control, rng.permutation(y))):
        cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=estado)
        clf = LogisticRegression(max_iter=5000)
        destino.append(
            cross_val_score(clf, X, etiquetas, cv=cv, scoring="roc_auc").mean()
        )


# ---------------------------------------------------------------------------
# 3. Degradacion en la tarea
# ---------------------------------------------------------------------------

def precision_en_k(v_consulta: np.ndarray, etq_consulta: np.ndarray,
                   v_indice: np.ndarray, etq_indice: np.ndarray,
                   k: int, excluir: np.ndarray | None = None) -> pd.DataFrame:
    """P@k por consulta. `excluir[i]` es la mascara de items vetados para i.

    Se veta la carpeta de origen cuando la consulta viene del propio catalogo:
    DeepFashion agrupa por producto y sin ese veto se recuperarian fotos casi
    identicas del mismo articulo. Eso no mide recuperacion, mide indexado.
    """
    filas = []
    for i in range(len(v_consulta)):
        sim = v_indice @ v_consulta[i]
        if excluir is not None:
            sim = np.where(excluir[i], -np.inf, sim)
        top = np.argpartition(-sim, k)[:k]
        aciertos = int((etq_indice[top] == etq_consulta[i]).sum())
        filas.append({"etiqueta": etq_consulta[i], "p_at_k": aciertos / k})
    return pd.DataFrame(filas)


def macro_ic(df: pd.DataFrame, semilla: int, reps: int = 1000
             ) -> tuple[float, float, float]:
    """Macro con intervalo del 95% por bootstrap, remuestreando CONSULTAS.

    Sin intervalo, comparar 112 consultas de armario con 2.000 de catalogo
    invita a leer como diferencia lo que puede ser ruido. Se remuestrea dentro
    de cada etiqueta para respetar la estructura del macro: el grupo `abrigo`
    tiene UNA prenda en el armario y su media no significa nada por si sola.
    """
    rng = np.random.default_rng(semilla)
    grupos = [g["p_at_k"].to_numpy() for _, g in df.groupby("etiqueta")]
    muestras = np.empty(reps)
    for r in range(reps):
        muestras[r] = np.mean([
            g[rng.integers(0, len(g), len(g))].mean() for g in grupos
        ])
    return macro(df), float(np.percentile(muestras, 2.5)), float(np.percentile(muestras, 97.5))


def macro(df: pd.DataFrame) -> float:
    """Media por etiqueta y luego media de medias.

    Sin macro, el numero lo decidiria la categoria mas frecuente: en el indice
    de test hay 5.173 camisetas y 39 camisas de franela, y el armario no tiene
    esas proporciones. Comparar micro entre dos conjuntos con priors distintos
    compara priors, no modelos.
    """
    return float(df.groupby("etiqueta")["p_at_k"].mean().mean())


# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--emb-armario", type=pathlib.Path, required=True)
    p.add_argument("--armario-csv", type=pathlib.Path, required=True)
    p.add_argument("--pares", type=pathlib.Path,
                   default=pathlib.Path("data/raw/wardrobe/pares.csv"),
                   help="Salida de src/emparejar_tomas.py: que fotos son la misma prenda")
    p.add_argument("--toma", default="a",
                   help="Toma usada para sonda y recuperacion. La otra sirve "
                        "como replica independiente de la medida")
    p.add_argument("--emb-corpus", type=pathlib.Path,
                   default=pathlib.Path("data/embeddings"))
    p.add_argument("--splits", type=pathlib.Path,
                   default=pathlib.Path("data/processed/splits.parquet"))
    p.add_argument("--experimentos", type=pathlib.Path, nargs="*", default=[])
    p.add_argument("--out", type=pathlib.Path,
                   default=pathlib.Path("experiments/domain_gap"))
    p.add_argument("--split", default="test",
                   help="Particion del catalogo que hace de indice")
    p.add_argument("--split-consultas", default=None,
                   help="Particion de la que salen las CONSULTAS de catalogo. "
                        "Debe ser distinta del indice: asi ninguna consulta "
                        "tiene su carpeta dentro del indice, igual que las "
                        "fotos del armario. Por defecto, la otra")
    p.add_argument("--k", type=int, default=10)
    p.add_argument("--n-consultas-catalogo", type=int, default=2000,
                   help="Submuestreo de consultas in-domain, por coste")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--device", default=None)
    args = p.parse_args()

    dev = args.device
    if dev is None:
        try:
            import torch
            dev = "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            dev = "cpu"

    args.out.mkdir(parents=True, exist_ok=True)

    # ---------------- armario ----------------
    v_arm_bruto, ficheros = cargar_embeddings(args.emb_armario)

    # Dos cruces, y en este orden: foto -> prenda (pares.csv), prenda ->
    # etiquetas (armario.csv). La unidad de etiquetado es la prenda, la unidad
    # del embedding es la foto, y mezclarlas es como se cuelan los
    # desalineamientos que nadie ve hasta que los numeros salen raros.
    pares = pd.read_csv(args.pares, encoding="utf-8-sig",
                        dtype={"prenda_id": str, "toma": str, "fichero": str})
    pares["fichero"] = pares["fichero"].str.replace("\\", "/", regex=False)
    if pares["fichero"].duplicated().any():
        raise SystemExit(f"{args.pares} tiene ficheros repetidos.")

    etiquetas = pd.read_csv(args.armario_csv, encoding="utf-8-sig", dtype=str)
    if etiquetas["item_id"].duplicated().any():
        raise SystemExit(f"{args.armario_csv} tiene item_id repetidos.")

    orden = pd.DataFrame({"fichero": ficheros, "pos": range(len(ficheros))})
    arm = orden.merge(pares[["fichero", "prenda_id", "toma"]],
                      on="fichero", how="left")
    huerfanas = int(arm["prenda_id"].isna().sum())
    if huerfanas:
        raise SystemExit(
            f"{huerfanas} fotos con embedding no aparecen en {args.pares}. "
            f"Vuelve a lanzar src/emparejar_tomas.py sobre la carpeta actual."
        )
    arm = arm.merge(etiquetas.rename(columns={"item_id": "prenda_id"})
                             .drop(columns=["fichero"], errors="ignore"),
                    on="prenda_id", how="left")
    assert len(arm) == len(ficheros), "el cruce ha cambiado el numero de filas"

    if "excluir" in arm.columns:
        arm.loc[arm["excluir"].fillna("").str.strip() != "", "categoria"] = np.nan

    sin_etiqueta = int(arm["categoria"].isna().sum())
    if sin_etiqueta:
        print(f"AVISO: {sin_etiqueta} fotos sin categoria (sin etiquetar o "
              f"excluidas). Quedan fuera de la recuperacion, pero cuentan para "
              f"dominio y ruido.")

    # ---------------- catalogo ----------------
    v_cor_bruto, rutas_cor = cargar_embeddings(args.emb_corpus)
    splits = pd.read_parquet(args.splits)
    pos_cor = pd.DataFrame({"image_path": rutas_cor, "pos": range(len(rutas_cor))})
    cor = pos_cor.merge(splits, on="image_path", how="left")
    huerfanas = int(cor["split"].isna().sum())
    if huerfanas:
        # Un embedding sin fila en splits no se puede colocar en ninguna
        # particion. Silenciarlo dejaria imagenes fuera del indice sin que
        # nadie se entere; es exactamente como se construyen los splits mal.
        raise SystemExit(
            f"{huerfanas} embeddings del catalogo no aparecen en {args.splits}. "
            f"Los dos ficheros no vienen de la misma corrida."
        )
    en_indice = (cor["split"] == args.split) & (~cor["excluir_indice"].astype(bool))
    todo_cor = cor.copy()
    cor = cor[en_indice].reset_index(drop=True)

    # Las consultas de catalogo salen de OTRA particion. Sin esto, una consulta
    # de catalogo tenia que vetarse su propia carpeta de producto —la mediana
    # son 34 imagenes en el indice, todas de su misma categoria por
    # construccion— mientras que una foto del armario no se vetaba nada. Esa
    # asimetria basta para invertir el signo de la caida, y lo hizo: en la
    # primera tirada el armario "recuperaba mejor" que el catalogo.
    #
    # Como los splits son disjuntos por carpeta (0 carpetas compartidas, se
    # comprueba abajo), una consulta de otra particion no tiene ninguna imagen
    # suya en el indice. Misma situacion que el armario, y el veto sobra.
    otro = args.split_consultas or ("test" if args.split == "val" else "val")
    if otro == args.split:
        raise SystemExit("--split-consultas debe ser distinto de --split")
    cor_q = todo_cor[(todo_cor["split"] == otro)
                     & (~todo_cor["excluir_indice"].astype(bool))].reset_index(drop=True)
    comunes_carp = set(cor_q["carpeta"]) & set(cor["carpeta"])
    if comunes_carp:
        raise SystemExit(
            f"{len(comunes_carp)} carpetas aparecen a la vez en el indice "
            f"({args.split}) y en las consultas ({otro}). La comparacion no "
            f"seria simetrica con el armario."
        )
    print(f"armario: {len(arm):,} fotos  |  indice {args.split}: {len(cor):,} "
          f"imagenes  |  consultas de catalogo desde {otro}: {len(cor_q):,}")

    # ---------------- vocabulario comun ----------------
    cor["grupo_cat"] = cor["categoria"].map(GRUPO_DEEPFASHION)
    arm["grupo_cat"] = (arm["categoria"].fillna("").str.strip().str.lower()
                        .map(GRUPO_ARMARIO))
    cor["slot_cat"] = cor["grupo_cat"].map(SLOT_DE_GRUPO)
    cor_q["grupo_cat"] = cor_q["categoria"].map(GRUPO_DEEPFASHION)
    cor_q["slot_cat"] = cor_q["grupo_cat"].map(SLOT_DE_GRUPO)
    arm["slot_cat"] = arm["grupo_cat"].map(SLOT_DE_GRUPO)

    excluidas = arm.loc[arm["grupo_cat"].isna() & arm["categoria"].notna(),
                        "categoria"].value_counts()
    if len(excluidas):
        print("Categorias del armario sin equivalente en DeepFashion "
              "(fuera de la parte de recuperacion):")
        print("  " + ", ".join(f"{k} ({v})" for k, v in excluidas.items()))

    reps = cargar_representaciones(v_arm_bruto.shape[1], args.experimentos, dev)
    print(f"representaciones: {', '.join(reps)}")

    rng = np.random.default_rng(args.seed)
    fil_ruido, fil_dom, fil_rec = [], [], []

    for nombre, rep in reps.items():
        print(f"\n--- {nombre} ---")
        v_arm = aplicar(rep, v_arm_bruto, dev)
        v_cor = aplicar(rep, v_cor_bruto[cor["pos"].to_numpy()], dev)
        v_cor_q = aplicar(rep, v_cor_bruto[cor_q["pos"].to_numpy()], dev)

        # 1 -----------------------------------------------------------------
        r = suelo_de_ruido(v_arm, arm["prenda_id"].to_numpy(),
                           arm["toma"].to_numpy(), args.seed)
        if r is None:
            print("  suelo de ruido: NO HAY prendas con dos tomas. "
                  "El resto de numeros queda sin escala de referencia.")
        else:
            print(f"  suelo de ruido: misma prenda {r['cos_misma_prenda_mediana']:.3f} "
                  f"| distintas p95 {r['cos_prendas_distintas_p95']:.3f} "
                  f"| margen {r['margen']:+.3f}")
            fil_ruido.append({"representacion": nombre, **r})

        # 2 -----------------------------------------------------------------
        # A partir de aqui, UNA foto por prenda. Con las dos, la validacion
        # cruzada reparte la toma A al entrenamiento y la toma B a la prueba:
        # son la misma prenda, asi que el clasificador la reconoce y el AUC
        # sube por fuga, no por dominio. Lo mismo en recuperacion, donde 236
        # consultas de las que 118 son casi duplicadas fingirian una muestra
        # mayor de la que hay y estrecharian los intervalos indebidamente.
        una = (arm["toma"].to_numpy() == args.toma)
        if una.sum() == 0:
            raise SystemExit(f"Ninguna foto con toma '{args.toma}'")
        v_arm1 = v_arm[una]
        arm1 = arm[una].reset_index(drop=True)

        cat_a = arm1["grupo_cat"].to_numpy()
        cat_c = cor["grupo_cat"].to_numpy()
        d = separabilidad(v_arm1, v_cor, args.seed,
                          cat_armario=cat_a, cat_corpus=cat_c)
        # El mismo numero SIN emparejar composicion. No se usa como resultado:
        # se reporta para poder ensenar cuanto infla el confusor de categoria.
        d_conf = separabilidad(v_arm1, v_cor, args.seed)
        if "error" in d:
            print(f"  dominio: {d['error']}. Se reporta solo el numero "
                  f"confundido, que no es interpretable por si solo.")
            d = {**d_conf, "emparejado_por_categoria": False}
        else:
            d["auc_sin_emparejar"] = d_conf["auc_media"]
            cuentas = arm1["grupo_cat"].value_counts().to_dict()
            cuentas = {g: n for g, n in cuentas.items() if g in set(cat_c)}
            d.update(nulos_de_catalogo(v_cor, cat_c,
                                       cor["categoria"].to_numpy(),
                                       cuentas, args.seed))
            print(f"  dominio: AUC {d['auc_media']:.3f} ± {d['auc_sd']:.3f} "
                  f"| nulos catalogo {d['auc_nulo_muestral']:.3f} (muestral) "
                  f"{d['auc_nulo_composicion']:.3f} (composicion) "
                  f"| control {d['auc_control_media']:.3f} "
                  f"| sin emparejar {d_conf['auc_media']:.3f}")
            if d["auc_media"] <= d["auc_nulo_composicion"]:
                print("  LEER CON CUIDADO: el AUC de dominio no supera al nulo "
                      "de composicion. No hay evidencia de que el dominio sea "
                      "linealmente legible mas alla de que las prendas difieran.")
        if abs(d["auc_control_media"] - 0.5) > 0.08:
            print("  AVISO: el control permutado no da ~0,50. El AUC principal "
                  "no es interpretable; revisa la validacion cruzada.")
        fil_dom.append({"representacion": nombre, **d})

        # 3 -----------------------------------------------------------------
        for col, nivel in (("slot_cat", "slot"), ("grupo_cat", "grupo")):
            comunes = set(arm1[col].dropna()) & set(cor[col].dropna())
            if not comunes:
                continue

            m_arm = arm1[col].isin(comunes).to_numpy()
            m_cor = cor[col].isin(comunes).to_numpy()
            idx_v = v_cor[m_cor]
            idx_e = cor.loc[m_cor, col].to_numpy()

            cruzado = precision_en_k(v_arm1[m_arm], arm1.loc[m_arm, col].to_numpy(),
                                     idx_v, idx_e, args.k)

            m_q = cor_q[col].isin(comunes).to_numpy()
            n_q = min(args.n_consultas_catalogo, int(m_q.sum()))
            # Generador propio por nivel, no el compartido: asi TODAS las
            # representaciones consultan exactamente las mismas imagenes de
            # catalogo. Con el generador compartido, cada representacion
            # sorteaba una muestra distinta y el lado de catalogo dejaba de
            # ser comparable prenda a prenda, que es la comparacion con mas
            # potencia que hay aqui.
            rng_q = np.random.default_rng(
                args.seed + int.from_bytes(nivel.encode(), "little") % 10_000)
            sel = rng_q.choice(int(m_q.sum()), size=n_q, replace=False)
            # Sin veto: ninguna de estas consultas tiene su carpeta en el
            # indice, igual que las del armario. La simetria es el punto.
            interno = precision_en_k(v_cor_q[m_q][sel],
                                     cor_q.loc[m_q, col].to_numpy()[sel],
                                     idx_v, idx_e, args.k)

            # Referencia aleatoria: el prior de cada etiqueta en el indice,
            # promediado en macro igual que las otras dos. Sin esto, un P@k de
            # 0,45 no se sabe si es bueno.
            prior = pd.Series(idx_e).value_counts(normalize=True)
            azar = float(prior.reindex(sorted(comunes)).mean())

            pc, pc_lo, pc_hi = macro_ic(interno, args.seed)
            pa, pa_lo, pa_hi = macro_ic(cruzado, args.seed)
            fila = {
                "representacion": nombre, "nivel": nivel, "k": args.k,
                "p_at_k_catalogo": pc, "cat_ic_lo": pc_lo, "cat_ic_hi": pc_hi,
                "p_at_k_armario": pa, "arm_ic_lo": pa_lo, "arm_ic_hi": pa_hi,
                "azar_macro": azar,
                "n_consultas_armario": int(m_arm.sum()),
                "n_consultas_catalogo": n_q,
                "n_indice": int(m_cor.sum()),
                "etiquetas": len(comunes),
            }
            fila["caida"] = fila["p_at_k_catalogo"] - fila["p_at_k_armario"]
            fila["caida_relativa"] = (
                fila["caida"] / fila["p_at_k_catalogo"]
                if fila["p_at_k_catalogo"] > 0 else np.nan
            )
            fil_rec.append(fila)
            print(f"  {nivel}: catalogo {pc:.3f} [{pc_lo:.3f},{pc_hi:.3f}] -> "
                  f"armario {pa:.3f} [{pa_lo:.3f},{pa_hi:.3f}]  "
                  f"caida {fila['caida']:+.3f}"
                  f"{'  (los IC se solapan)' if pa_hi > pc_lo and pc_hi > pa_lo else ''}"
                  f"  azar {azar:.3f}")

            # Se guardan LOS DOS lados. Con solo el del armario no se puede
            # recalcular la caida excluyendo grupos degenerados (`abrigo` tiene
            # UNA prenda) sin volver a lanzar todo.
            pd.concat([
                cruzado.assign(origen="armario"),
                interno.assign(origen="catalogo"),
            ]).assign(representacion=nombre, nivel=nivel) \
                .to_csv(args.out / f"consultas_{nombre.replace('/', '_')}_{nivel}_{args.toma}.csv",
                        index=False, encoding="utf-8")

    for filas, nombre in ((fil_ruido, "suelo_ruido"),
                          (fil_dom, "separabilidad_dominio"),
                          (fil_rec, "recuperacion")):
        if filas:
            pd.DataFrame(filas).to_csv(args.out / f"{nombre}_{args.toma}.csv",
                                       index=False, encoding="utf-8")

    (args.out / "config.yaml").write_text(yaml.safe_dump({
        "emb_armario": str(args.emb_armario),
        "armario_csv": str(args.armario_csv),
        "pares": str(args.pares),
        "toma": args.toma,
        "emb_corpus": str(args.emb_corpus),
        "split_indice": args.split,
        "experimentos": [str(e) for e in args.experimentos],
        "k": args.k,
        "seed": args.seed,
        "n_armario": int(len(arm)),
        "n_indice": int(len(cor)),
        "grupo_deepfashion": GRUPO_DEEPFASHION,
        "grupo_armario": GRUPO_ARMARIO,
    }, sort_keys=False, allow_unicode=True), encoding="utf-8")

    print(f"\nEscrito en {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
