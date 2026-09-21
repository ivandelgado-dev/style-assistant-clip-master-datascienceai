"""
Motor de evaluación de retrieval por atributo.

Implementa el protocolo de `docs/protocolo_evaluacion.md`. Lo usan las seis
condiciones (aleatorio, CLIP plano, CLIP-PCA, proyección conjunta, proyecciones
por atributo, MLP) sin cambiar una línea: cada una aporta su matriz de
embeddings y el resto es idéntico.

Que el código de evaluación sea común a todas las condiciones no es comodidad,
es un requisito: si cada condición se evaluara con su propio camino, cualquier
diferencia entre ellas podría venir del evaluador y no del modelo.

No depende de DeepFashion ni de CLIP. Entra una matriz de embeddings y una
tabla de relevancia; sale una métrica por consulta.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Métricas, todas por consulta (nunca promediadas aquí dentro)
# ---------------------------------------------------------------------------
# Se devuelven por consulta y no agregadas porque el protocolo exige comparación
# PAREADA: se compara la distribución de diferencias entre condiciones sobre las
# mismas consultas, no dos medias sueltas. Agregar aquí destruiría esa
# posibilidad de forma irreversible.


def recall_at_k(rel_ordenada: np.ndarray, n_relevantes: int, k: int) -> float:
    """Fracción de relevantes recuperados en el top-k.

    OJO con la interpretación: si n_relevantes > k, el recall NO puede llegar a
    1 por construcción. No se normaliza por min(n_rel, k) —eso seria Recall@k
    "capado", que infla el numero— pero hay que decirlo en la memoria, porque
    con atributos frecuentes habra cientos de relevantes y k=10.
    """
    if n_relevantes == 0:
        return np.nan
    return float(rel_ordenada[:k].sum() / n_relevantes)


def ndcg_at_k(rel_ordenada: np.ndarray, n_relevantes: int, k: int) -> float:
    """NDCG@k con relevancia binaria.

    El ideal es tener min(n_relevantes, k) unos al principio: si hay menos
    relevantes que k, el IDCG no puede usar k posiciones o el NDCG saldria
    artificialmente bajo para las consultas con pocos relevantes.
    """
    if n_relevantes == 0:
        return np.nan
    descuento = 1.0 / np.log2(np.arange(2, k + 2))
    dcg = float((rel_ordenada[:k] * descuento).sum())
    idcg = float(descuento[: min(n_relevantes, k)].sum())
    return dcg / idcg if idcg > 0 else np.nan


def average_precision(rel_ordenada: np.ndarray, n_relevantes: int) -> float:
    """AP sobre el ranking completo (no truncado a k)."""
    if n_relevantes == 0:
        return np.nan
    posiciones = np.flatnonzero(rel_ordenada)
    if posiciones.size == 0:
        return 0.0
    precisiones = (np.arange(posiciones.size) + 1) / (posiciones + 1)
    return float(precisiones.sum() / n_relevantes)


# ---------------------------------------------------------------------------
# Construcción de consultas
# ---------------------------------------------------------------------------

@dataclass
class Consultas:
    """Consultas del protocolo: el par (imagen, atributo concreto).

    q_idx[i]     -> fila de la imagen de consulta en la matriz de embeddings
    atributo[i]  -> el atributo t sobre el que se pregunta
    grupo[i]     -> corte / textura / ... (determina que subespacio se usa)
    particion[i] -> seen / unseen (determina como se lee el numero)
    relevantes[i]-> indices del indice que tienen ese atributo t
    """

    q_idx: np.ndarray
    atributo: np.ndarray
    grupo: np.ndarray
    particion: np.ndarray
    relevantes: list[np.ndarray]

    def __len__(self) -> int:
        return len(self.q_idx)


def construir_consultas(
    attrs_long: pd.DataFrame,
    ids_indice: np.ndarray,
    max_por_atributo: int | None = 50,
    min_relevantes: int = 2,
    semilla: int = 42,
    col_id: str = "item_id",
) -> Consultas:
    """Construye las consultas a partir de la tabla larga (imagen, atributo).

    `ids_indice` son los identificadores de las prendas QUE FORMAN EL INDICE, en
    el mismo orden que las filas de la matriz de embeddings. Deben ser solo de
    test y con un unico representante por dup_group: eso se resuelve antes de
    llamar aqui, filtrando la tabla.

    `max_por_atributo` limita cuantas consultas genera cada atributo. Sin este
    tope, un atributo con 8.000 positivos aporta 8.000 consultas y uno con 200
    aporta 200: la media global quedaria dominada por dos o tres atributos muy
    frecuentes y dejaria de medir "el grupo corte" para medir "el atributo mas
    comun del grupo corte". Se submuestrea con semilla fija.
    """
    rng = np.random.default_rng(semilla)

    # `col_id` existe porque attrs_long.parquet del EDA identifica la prenda por
    # `image_path`, mientras que el armario usara su propio id. Si se asumiera un
    # nombre fijo, el fallo seria un KeyError a mitad de una corrida larga.
    if col_id not in attrs_long.columns:
        raise KeyError(
            f"attrs_long no tiene la columna '{col_id}'. Columnas disponibles: "
            f"{list(attrs_long.columns)}. Pasa col_id='image_path' si vienes "
            f"directamente de eda_atributos.py."
        )

    pos = pd.Series(np.arange(len(ids_indice)), index=ids_indice)
    tabla = attrs_long[attrs_long[col_id].isin(pos.index)]

    q_idx, atributo, grupo, particion, relevantes = [], [], [], [], []

    for (attr, gr, part), bloque in tabla.groupby(
        ["attr_name", "attr_group", "particion"], observed=True
    ):
        miembros = pos.loc[bloque[col_id]].to_numpy()
        # min_relevantes cuenta SIN la consulta: si un atributo solo lo tiene
        # una prenda, al excluirse a si misma no queda ningun relevante y la
        # metrica seria NaN. Se descarta el atributo entero.
        if miembros.size < min_relevantes + 1:
            continue

        elegidas = miembros
        if max_por_atributo is not None and miembros.size > max_por_atributo:
            elegidas = rng.choice(miembros, size=max_por_atributo, replace=False)

        for q in elegidas:
            q_idx.append(q)
            atributo.append(attr)
            grupo.append(gr)
            particion.append(part)
            relevantes.append(miembros[miembros != q])

    return Consultas(
        q_idx=np.asarray(q_idx),
        atributo=np.asarray(atributo),
        grupo=np.asarray(grupo),
        particion=np.asarray(particion),
        relevantes=relevantes,
    )


# ---------------------------------------------------------------------------
# Evaluación de una condición
# ---------------------------------------------------------------------------

def evaluar(
    embeddings: np.ndarray,
    consultas: Consultas,
    ks: tuple[int, ...] = (5, 10, 20),
    condicion: str = "sin_nombre",
    chunk: int = 512,
    semilla_aleatoria: int | None = None,
) -> pd.DataFrame:
    """Evalúa una condición y devuelve UNA FILA POR CONSULTA.

    `embeddings` tiene una fila por elemento del indice, en el mismo orden que
    los `ids_indice` con los que se construyeron las consultas.

    Se normaliza a norma unitaria: con eso el producto escalar ES la similitud
    coseno, que es la metrica del protocolo, y se evita calcular normas en cada
    chunk.

    `semilla_aleatoria` activa la condicion 1 (ranking aleatorio): se ignoran
    los embeddings y se baraja. Se implementa aqui, y no como un script aparte,
    para que pase exactamente por el mismo codigo de metricas.
    """
    X = embeddings.astype(np.float32, copy=True)
    normas = np.linalg.norm(X, axis=1, keepdims=True)
    X /= np.maximum(normas, 1e-12)

    n_items = X.shape[0]
    rng = np.random.default_rng(semilla_aleatoria)
    filas = []

    for ini in range(0, len(consultas), chunk):
        fin = min(ini + chunk, len(consultas))
        qs = consultas.q_idx[ini:fin]

        if semilla_aleatoria is None:
            sims = X[qs] @ X.T
        else:
            sims = rng.random((fin - ini, n_items), dtype=np.float32)

        # La propia consulta nunca puede aparecer en su ranking.
        sims[np.arange(fin - ini), qs] = -np.inf
        orden = np.argsort(-sims, axis=1)

        for j, i_global in enumerate(range(ini, fin)):
            rel_set = consultas.relevantes[i_global]
            marcas = np.zeros(n_items, dtype=np.int8)
            marcas[rel_set] = 1
            rel_ord = marcas[orden[j]]
            n_rel = int(rel_set.size)

            fila = {
                "condicion": condicion,
                "consulta_id": i_global,
                "attr_name": consultas.atributo[i_global],
                "attr_group": consultas.grupo[i_global],
                "particion": consultas.particion[i_global],
                "n_relevantes": n_rel,
                "mAP": average_precision(rel_ord, n_rel),
            }
            for k in ks:
                fila[f"recall@{k}"] = recall_at_k(rel_ord, n_rel, k)
                fila[f"ndcg@{k}"] = ndcg_at_k(rel_ord, n_rel, k)
            filas.append(fila)

    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------
# Comparación pareada
# ---------------------------------------------------------------------------

def bootstrap_pareado(
    a: pd.DataFrame,
    b: pd.DataFrame,
    metrica: str,
    n_boot: int = 10_000,
    semilla: int = 42,
    alpha: float = 0.05,
) -> dict:
    """Diferencia pareada b - a con intervalo de confianza por bootstrap.

    Se remuestrean CONSULTAS, no observaciones sueltas: la unidad de variacion
    del experimento es la consulta, y las dos condiciones comparten las mismas.
    Remuestrear las condiciones por separado romperia el emparejamiento y daria
    intervalos mas anchos de lo que corresponde.

    Devuelve el IC de la diferencia. Si ese intervalo contiene el 0, no se puede
    afirmar que haya mejora, por bonita que sea la media.
    """
    m = a[["consulta_id", metrica]].merge(
        b[["consulta_id", metrica]], on="consulta_id", suffixes=("_a", "_b")
    )
    if len(m) != len(a) or len(m) != len(b):
        raise ValueError(
            "Las dos condiciones no cubren el mismo conjunto de consultas. "
            "La comparacion pareada exige consultas identicas."
        )

    d = (m[f"{metrica}_b"] - m[f"{metrica}_a"]).to_numpy(dtype=float)
    d = d[~np.isnan(d)]
    if d.size == 0:
        raise ValueError(f"No hay valores no-NaN para la metrica '{metrica}'.")

    rng = np.random.default_rng(semilla)
    idx = rng.integers(0, d.size, size=(n_boot, d.size))
    medias = d[idx].mean(axis=1)
    lo, hi = np.percentile(medias, [100 * alpha / 2, 100 * (1 - alpha / 2)])

    return {
        "metrica": metrica,
        "media_a": float(np.nanmean(m[f"{metrica}_a"])),
        "media_b": float(np.nanmean(m[f"{metrica}_b"])),
        "diferencia": float(d.mean()),
        "ic_bajo": float(lo),
        "ic_alto": float(hi),
        "significativo": bool(lo > 0 or hi < 0),
        "n_consultas": int(d.size),
    }


def tabla_comparativa(
    resultados: dict[str, pd.DataFrame],
    referencia: str,
    metrica: str = "recall@10",
    por: str = "particion",
    **kw,
) -> pd.DataFrame:
    """Compara cada condición contra la de referencia, desglosando por `por`.

    Uso previsto: referencia="proyeccion_conjunta". Es la comparacion que decide
    el proyecto — que las cabezas batan a CLIP plano no demuestra desacoplamiento,
    solo demuestra que la supervision ayuda.
    """
    ref = resultados[referencia]
    filas = []
    for nombre, df in resultados.items():
        if nombre == referencia:
            continue
        for valor in sorted(set(ref[por]) & set(df[por])):
            r = bootstrap_pareado(
                ref[ref[por] == valor], df[df[por] == valor], metrica, **kw
            )
            filas.append({"condicion": nombre, por: valor, **r})
    return pd.DataFrame(filas)
