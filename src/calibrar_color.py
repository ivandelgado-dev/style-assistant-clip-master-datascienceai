"""
Calibración de las franjas de color, sobre el armario del autor.

Se ejecuta ANTES de mirar la evaluación con fotos de Bershka, y sus umbrales
quedan escritos en experiments/color_primero/calibracion.json. La evaluación
los lee de ahí y no los toca. Si se ajustaran mirando la propia prueba, la
cifra final no valdría nada: sería el mejor resultado de varios intentos.

Qué mide
--------
Cada prenda del armario tiene dos tomas (A y B), de la misma prenda con la
misma luz. La distancia ΔE CMC(2:1) entre el color leído en A y el leído en B
dice cuánto «ruido» mete el propio procedimiento cuando el color es el
mismo. La distancia a las demás prendas dice cuánto separa colores distintos.

Umbrales (regla fijada antes de ver los datos)
----------------------------------------------
- «Mismo color»: ΔE hasta el percentil 90 de la misma prenda. Nueve de cada
  diez prendas idénticas caen en la primera franja.
- «Color cercano»: hasta el doble. Deja margen para lo que esta calibración
  NO ve: el cambio de luz entre una foto de calle y una de estudio, que
  mueve sobre todo la claridad.
- Más allá, «otro color».

Uso
---
    python src/calibrar_color.py
"""

from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pandas as pd
from PIL import Image

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from paginas import color  # noqa: E402

FOTOS = RAIZ / "data/raw/wardrobe/img"
SALIDA = RAIZ / "experiments/color_primero"


def main() -> int:
    p = pd.read_csv(RAIZ / "data/raw/wardrobe/pares.csv", encoding="utf-8-sig",
                    dtype=str)
    p["fichero"] = p["fichero"].str.replace("\\", "/", regex=False)
    a = p[p["toma"] == "a"].set_index("prenda_id")["fichero"]
    b = p[p["toma"] == "b"].set_index("prenda_id")["fichero"]
    ids = sorted(set(a.index) & set(b.index))

    lab_a, lab_b = [], []
    for i in ids:
        lab_a.append(color.color_prenda(Image.open(FOTOS / a[i]))[0])
        lab_b.append(color.color_prenda(Image.open(FOTOS / b[i]))[0])
    A, B = np.array(lab_a), np.array(lab_b)

    misma = np.array([color.delta_cmc(A[k], B[k:k + 1])[0] for k in range(len(ids))])
    distinta = np.concatenate([
        np.delete(color.delta_cmc(A[k], B), k) for k in range(len(ids))])

    t1 = float(np.percentile(misma, 90))
    res = {
        "version_color": color.VERSION,
        "n_prendas": len(ids),
        "misma_prenda": {q: round(float(np.percentile(misma, q)), 2)
                         for q in (50, 75, 90, 95)},
        "prendas_distintas": {q: round(float(np.percentile(distinta, q)), 2)
                              for q in (5, 10, 25, 50)},
        "umbral_mismo_color": round(t1, 2),
        "umbral_color_cercano": round(2 * t1, 2),
        "regla": "mismo = p90 de la misma prenda (toma A vs B); cercano = 2x",
    }
    # Qué fracción de pares DISTINTOS caería en cada franja: si «mismo color»
    # se tragara medio armario, la franja no ordenaría nada.
    res["distintas_en_franja_mismo"] = round(float((distinta <= t1).mean()), 3)
    res["distintas_en_franja_cercano"] = round(float((distinta <= 2 * t1).mean()), 3)

    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / "calibracion.json").write_text(
        json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    pd.DataFrame({"prenda_id": ids,
                  "L_a": A[:, 0], "a_a": A[:, 1], "b_a": A[:, 2],
                  "L_b": B[:, 0], "a_b": B[:, 1], "b_b": B[:, 2],
                  "nombre_a": [color.nombre_color(x) for x in A],
                  "de_misma": misma}).to_csv(SALIDA / "colores_armario.csv",
                                             index=False)
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
