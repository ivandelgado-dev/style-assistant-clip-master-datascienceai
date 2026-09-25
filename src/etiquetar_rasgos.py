"""
Rasgos de estilo (paginas/etiquetas.py, versión r1) para las prendas que ya
están en el armario, y la medida de cuánto fiarse de ellos.

    python src/etiquetar_rasgos.py                 # todas las cuentas
    python src/etiquetar_rasgos.py --retest 30     # y consistencia en 30 fotos

Qué hace:
1. Pide a Gemini los rasgos de las prendas que no los tienen (10 fotos por
   petición; lo ya pedido está en data/etiquetas_cache.json y no se repite)
   y los guarda en la base (etiquetas → "rasgos").
2. Mide, sin tocar nada de la app:
   - cuántas prendas cambian de formalidad al añadir los rasgos (y cuáles,
     en cambios.csv, para revisarlas a mano);
   - acuerdo entre la formalidad de la REGLA (outfits.formalidad) y la que
     dice la IA (formalidad_ia): exacto y a ±1. La regla decide; la de la IA
     solo sirve para medirla;
   - con --retest N: se vuelve a preguntar por N fotos sin caché y se cuenta
     cuántas veces coincide cada rasgo (test-retest).
3. Deja en experiments/rasgos_r1/ config.yaml, metricas.json y cambios.csv.

Necesita GEMINI_API_KEY en .env (no se imprime nunca). No necesita torch.
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import random
import sqlite3
import sys
import types
from collections import Counter
from datetime import datetime

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.modules.setdefault("torch", types.ModuleType("torch"))   # no hace falta aquí

from paginas import armario, etiquetas, gemini, outfits  # noqa: E402

DATOS = RAIZ / "data"
BD = DATOS / "usuarios.db"
SEMILLA = 7


def _prendas(uid: int):
    """(id, foto, etiquetas, categoria, notas) de un usuario."""
    cx = sqlite3.connect(BD)
    try:
        filas = cx.execute("SELECT id, foto, etiquetas, categoria, notas FROM prendas "
                           "WHERE usuario_id = ? AND etiquetas IS NOT NULL ORDER BY id",
                           (uid,)).fetchall()
    finally:
        cx.close()
    out = []
    for pid, foto, e, cat, notas in filas:
        try:
            out.append((pid, foto, json.loads(e), cat, notas))
        except (TypeError, ValueError):
            pass
    return out


def _f(e: dict, cat, notas, con_rasgos: bool) -> tuple[int, str]:
    K = armario.clave_categoria
    tipo = K(cat) if K(cat or "") in etiquetas.TIPOS else e.get("tipo")
    if e.get("largo") == "corto" and tipo in ("pantalon", "chino", "vaquero"):
        tipo = "bermuda"
    f, por, _ = outfits.formalidad(
        tipo, e.get("estampado") or "liso", e.get("manga"), e.get("largo"),
        K(str(e.get("descripcion") or "")),
        rasgos=e.get("rasgos") if con_rasgos else None,
        notas=K(notas) if isinstance(notas, str) else "")
    return f, por


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--usuario", type=int, default=None, help="solo esta cuenta")
    ap.add_argument("--retest", type=int, default=0, help="fotos para test-retest")
    ap.add_argument("--salida", default="experiments/rasgos_r1")
    a = ap.parse_args()
    if not gemini.disponible():
        sys.exit("Falta GEMINI_API_KEY (en el entorno o en .env).")
    modelo = gemini.elegir_modelo()

    cx = sqlite3.connect(BD)
    uids = [a.usuario] if a.usuario else [u for (u,) in cx.execute(
        "SELECT DISTINCT usuario_id FROM prendas ORDER BY 1")]
    cx.close()

    # 1. Pedir y guardar.
    for uid in uids:
        pend = armario.sin_rasgos(BD, uid)
        print(f"cuenta {uid}: {len(pend)} prendas sin rasgos")
        datos = {pid: (DATOS / foto).read_bytes() for pid, foto in pend
                 if (DATOS / foto).exists()}
        etiquetas.rasgos_lote(list(datos.values()), modelo)
        for pid, b in datos.items():
            r = etiquetas.rasgos_en_cache(b)
            if r:
                armario.guardar_rasgos(BD, uid, pid, r)

    # 2. Medir.
    filas, cambios, exacto, uno, n_ia = [], [], 0, 0, 0
    conf = Counter()
    for uid in uids:
        for pid, foto, e, cat, notas in _prendas(uid):
            if not e.get("rasgos"):
                continue
            f0, _ = _f(e, cat, notas, False)
            f1, por = _f(e, cat, notas, True)
            fia = e["rasgos"].get("formalidad_ia")
            filas.append((uid, pid, f0, f1, fia))
            if fia:
                n_ia += 1
                exacto += f1 == fia
                uno += abs(f1 - fia) <= 1
                conf[(f1, fia)] += 1
            if f0 != f1:
                cambios.append({"cuenta": uid, "id": pid, "tipo": e.get("tipo"),
                                "sin_rasgos": f0, "con_rasgos": f1, "por": por,
                                "formalidad_ia": fia,
                                "rasgos": ",".join(k for k in etiquetas.RASGOS
                                                   if e["rasgos"].get(k)),
                                "descripcion": e.get("descripcion"), "notas": notas or ""})
    met = {"prendas_con_rasgos": len(filas),
           "cambian_con_rasgos": len(cambios),
           "regla_vs_ia": {"n": n_ia, "exacto": exacto, "a_1": uno,
                           "matriz_regla_ia": {f"{r}-{i}": v for (r, i), v in sorted(conf.items())}}}

    # 3. Test-retest.
    if a.retest:
        todas = [(DATOS / foto).read_bytes() for uid in uids
                 for _, foto, e, *_ in _prendas(uid) if e.get("rasgos") and (DATOS / foto).exists()]
        random.Random(SEMILLA).shuffle(todas)
        muestra = todas[:a.retest]
        iguales, total = Counter(), 0
        for i in range(0, len(muestra), 10):
            lote = muestra[i:i + 10]
            try:
                nuevos = etiquetas.pedir_rasgos_lote(lote, modelo)
            except gemini.ErrorGemini as ex:
                print("  retest:", gemini.resumen_error(ex))
                break
            for b, r2 in zip(lote, nuevos):
                r1 = etiquetas.rasgos_en_cache(b)
                if not (r1 and r2):
                    continue
                total += 1
                for k in [*etiquetas.RASGOS, "formalidad_ia"]:
                    iguales[k] += r1.get(k) == r2.get(k)
        met["retest"] = {"n": total, **{k: iguales[k] for k in [*etiquetas.RASGOS, "formalidad_ia"]}}

    sal = RAIZ / a.salida
    sal.mkdir(parents=True, exist_ok=True)
    (sal / "config.yaml").write_text(
        f"fecha: {datetime.now().isoformat(timespec='seconds')}\n"
        f"modelo: {modelo}\nversion_rasgos: {etiquetas.VERSION_RASGOS}\n"
        f"cuentas: {uids}\nretest: {a.retest}\nsemilla: {SEMILLA}\n", encoding="utf-8")
    (sal / "metricas.json").write_text(json.dumps(met, ensure_ascii=False, indent=1),
                                       encoding="utf-8")
    with open(sal / "cambios.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, delimiter=";", fieldnames=[
            "cuenta", "id", "tipo", "sin_rasgos", "con_rasgos", "por", "formalidad_ia",
            "rasgos", "descripcion", "notas"])
        w.writeheader()
        w.writerows(cambios)
    print(json.dumps(met, ensure_ascii=False, indent=1))
    print(f"\nGuardado en {sal.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
