"""Pruebas del motor de evaluación. Se ejecutan sin ningún dato real."""

import numpy as np
import pandas as pd

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from evaluacion import (
    average_precision,
    bootstrap_pareado,
    construir_consultas,
    evaluar,
    ndcg_at_k,
    recall_at_k,
    tabla_comparativa,
)

fallos = []


def check(nombre, cond, detalle=""):
    print(f"  {'OK  ' if cond else 'FALLA'}  {nombre} {detalle}")
    if not cond:
        fallos.append(nombre)


print("\n=== 1. Métricas contra valores calculados a mano ===")

# Ranking: relevante en posiciones 1 y 3 (1-indexado). 4 relevantes en total.
rel = np.array([1, 0, 1, 0, 0, 0, 0, 0, 0, 0])
check("recall@5 = 2/4", np.isclose(recall_at_k(rel, 4, 5), 0.5))
check("recall@1 = 1/4", np.isclose(recall_at_k(rel, 4, 1), 0.25))

# DCG@3 = 1/log2(2) + 0 + 1/log2(4) = 1 + 0.5 = 1.5
# IDCG@3 = 1/log2(2)+1/log2(3)+1/log2(4) = 1 + 0.6309 + 0.5 = 2.1309
esperado = 1.5 / (1 + 1 / np.log2(3) + 0.5)
check("ndcg@3 a mano", np.isclose(ndcg_at_k(rel, 4, 3), esperado), f"({ndcg_at_k(rel,4,3):.4f})")

# Ranking perfecto -> ndcg = 1
perfecto = np.array([1, 1, 1, 0, 0, 0])
check("ndcg@3 de ranking perfecto = 1", np.isclose(ndcg_at_k(perfecto, 3, 3), 1.0))

# Menos relevantes que k: el IDCG solo puede usar n_rel posiciones
uno = np.array([1, 0, 0, 0, 0])
check("ndcg@5 con 1 relevante en pos 1 = 1", np.isclose(ndcg_at_k(uno, 1, 5), 1.0))

# AP: precisiones 1/1 y 2/3, dividido por 4 relevantes
check("mAP a mano", np.isclose(average_precision(rel, 4), (1.0 + 2 / 3) / 4))
check("AP de ranking perfecto = 1", np.isclose(average_precision(perfecto, 3), 1.0))
check("n_relevantes=0 -> NaN", np.isnan(recall_at_k(rel, 0, 5)))


print("\n=== 2. Ranker informativo vs aleatorio ===")

rng = np.random.default_rng(0)
N_ITEMS, N_ATTR, DIM = 400, 8, 32

# Embeddings construidos para que compartir atributo implique cercanía.
prototipos = rng.normal(size=(N_ATTR, DIM))
pertenencia = np.zeros((N_ITEMS, N_ATTR), dtype=int)
for i in range(N_ITEMS):
    for a in rng.choice(N_ATTR, size=rng.integers(1, 3), replace=False):
        pertenencia[i, a] = 1
emb_bueno = pertenencia @ prototipos + 0.35 * rng.normal(size=(N_ITEMS, DIM))
emb_malo = rng.normal(size=(N_ITEMS, DIM))  # sin relación con los atributos

filas = [
    {"item_id": f"it_{i:04d}", "attr_name": f"a{a}", "attr_group": "g", "particion": "seen"}
    for i in range(N_ITEMS)
    for a in range(N_ATTR)
    if pertenencia[i, a]
]
attrs_long = pd.DataFrame(filas)
ids = np.array([f"it_{i:04d}" for i in range(N_ITEMS)])

cons = construir_consultas(attrs_long, ids, max_por_atributo=40, semilla=1)
print(f"  consultas construidas: {len(cons)}")
check("se construyeron consultas", len(cons) > 100)

r_bueno = evaluar(emb_bueno, cons, condicion="informativo")
r_malo = evaluar(emb_malo, cons, condicion="ruido")
r_azar = evaluar(emb_malo, cons, condicion="aleatorio", semilla_aleatoria=7)

m = lambda d: d["recall@10"].mean()
print(f"  recall@10 informativo={m(r_bueno):.4f}  ruido={m(r_malo):.4f}  azar={m(r_azar):.4f}")
check("informativo > ruido", m(r_bueno) > m(r_malo) * 2)

# El azar debe rondar k/n_items: 10/400 = 0.025
check("azar cerca de k/N", abs(m(r_azar) - 10 / N_ITEMS) < 0.02, f"({m(r_azar):.4f} vs 0.025)")
check("una fila por consulta", len(r_bueno) == len(cons))
check("ndcg en [0,1]", r_bueno["ndcg@10"].between(0, 1).all())
check("la consulta no se recupera a si misma",
      (r_bueno["n_relevantes"] < N_ITEMS).all())


print("\n=== 3. Bootstrap pareado ===")

b = bootstrap_pareado(r_malo, r_bueno, "recall@10", n_boot=2000, semilla=3)
print(f"  informativo - ruido: dif={b['diferencia']:+.4f} "
      f"IC95=[{b['ic_bajo']:+.4f}, {b['ic_alto']:+.4f}] sig={b['significativo']}")
check("detecta diferencia real", b["significativo"] and b["diferencia"] > 0)

# Misma condición contra sí misma: diferencia 0, no significativa.
b0 = bootstrap_pareado(r_bueno, r_bueno.copy(), "recall@10", n_boot=2000, semilla=3)
check("A vs A no es significativo", not b0["significativo"] and abs(b0["diferencia"]) < 1e-12)

# Dos condiciones con distinto conjunto de consultas deben reventar, no colar.
try:
    bootstrap_pareado(r_bueno, r_bueno.iloc[:-5], "recall@10", n_boot=10)
    check("rechaza consultas no emparejadas", False)
except ValueError:
    check("rechaza consultas no emparejadas", True)


print("\n=== 4. Tabla comparativa ===")
tabla = tabla_comparativa(
    {"conjunta": r_malo, "por_atributo": r_bueno, "aleatorio": r_azar},
    referencia="conjunta",
    metrica="recall@10",
    n_boot=1000,
)
print(tabla[["condicion", "particion", "diferencia", "ic_bajo", "ic_alto",
             "significativo"]].to_string(index=False))
check("compara todas contra la referencia", len(tabla) == 2)


print("\n=== 5. col_id equivocado da error claro ===")
try:
    construir_consultas(attrs_long.rename(columns={"item_id": "image_path"}), ids)
    check("KeyError informativo", False)
except KeyError as e:
    check("KeyError informativo", "image_path" in str(e))


print(f"\n{'TODO OK' if not fallos else 'FALLOS: ' + ', '.join(fallos)}")
raise SystemExit(1 if fallos else 0)
