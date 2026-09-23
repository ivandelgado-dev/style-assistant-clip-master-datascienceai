"""
¿Da Gemini las mismas etiquetas si se le pregunta dos veces por la misma foto?

Por qué hace falta
------------------
`gemini-3.5-flash-lite` ignora el parámetro `temperature` (usa valores de
muestreo fijos; la biblioteca de LangChain lo avisa). Y aun con temperatura 0,
un modelo servido en remoto no garantiza respuestas idénticas. Así que el
etiquetado NO es reproducible por construcción.

Cómo se trata en este trabajo
-----------------------------
1. Las etiquetas se tratan como una ANOTACIÓN: se generan una vez, se guardan
   (data/etiquetas_cache.json, con el modelo y la versión del prompt) y todo
   lo demás —la aplicación y la evaluación— lee esa copia congelada. Con la
   copia guardada, los resultados se reproducen exactamente.
2. Lo que varía al regenerarlas se MIDE aquí: se vuelve a preguntar por las
   fotos de producto, saltándose la caché, y se compara campo a campo con lo
   guardado. Es la fiabilidad test-retest del anotador, la misma idea que la
   deriva de anotador medida a mano en docs/resultados_anotacion_dominio.md.

Coste: una petición por cada 10 fotos (3 peticiones con 24 productos).

Uso
---
    python src/consistencia_etiquetas.py
"""

from __future__ import annotations

import json
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from paginas import etiquetas, gemini  # noqa: E402

CAMPOS = ("posicion", "tipo", "manga", "largo", "color", "estampado", "tejido")


def main() -> int:
    modelo = gemini.elegir_modelo()
    fotos = sorted((RAIZ / "data/eval_color/producto").glob("*.*"))
    datos = [f.read_bytes() for f in fotos]
    guardadas = [etiquetas.en_cache(d, modelo) for d in datos]
    if any(g is None for g in guardadas):
        print("Primero lanza evaluar_busqueda.py: faltan etiquetas guardadas.")
        return 1
    print(f"Modelo: {modelo}. Repitiendo {len(fotos)} fotos sin caché…")
    nuevas = []
    for i in range(0, len(datos), 10):
        nuevas += etiquetas.pedir_lote(datos[i:i + 10], modelo)

    iguales = {c: 0 for c in CAMPOS}
    n = 0
    difs = []
    for f, a, b in zip(fotos, guardadas, nuevas):
        if not b or not a["piezas"] or not b["piezas"]:
            continue
        pa, pb = a["piezas"][0], b["piezas"][0]
        n += 1
        for c in CAMPOS:
            if pa.get(c) == pb.get(c):
                iguales[c] += 1
            else:
                difs.append(f"{f.stem}: {c} {pa.get(c)} -> {pb.get(c)}")
    res = {"modelo": modelo, "fotos": n,
           "acuerdo_por_campo": {c: f"{iguales[c]}/{n}" for c in CAMPOS},
           "fotos_identicas": sum(
               all(a["piezas"][0].get(c) == b["piezas"][0].get(c) for c in CAMPOS)
               for a, b in zip(guardadas, nuevas) if b and a["piezas"] and b["piezas"])}
    sal = RAIZ / "experiments/busqueda_modelo_producto"
    sal.mkdir(parents=True, exist_ok=True)
    (sal / "consistencia_etiquetas.json").write_text(
        json.dumps({**res, "diferencias": difs}, indent=2, ensure_ascii=False),
        encoding="utf-8")
    print(json.dumps(res, indent=2, ensure_ascii=False))
    for d in difs:
        print("  ", d)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
