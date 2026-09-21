"""
Paso 6-bis — Reconstruir que dos fotos son la misma prenda.

El problema
-----------
El protocolo pedia nombrar las tomas repetidas con prefijo `dup_`. En la
practica las fotos salieron del movil con el nombre que pone el movil
(`20260910_124705.jpg`) y se copiaron sin orden. Renombrar 236 ficheros a mano
es una hora de trabajo y una fuente de errores silenciosos.

No hace falta: el nombre del fichero ES la marca de tiempo del disparo, con
precision de segundo. El orden nunca se perdio.

Como se empareja
----------------
Al fotografiar, la secuencia real fue: colocar prenda, disparar, recolocar,
disparar, retirar, coger la siguiente. Eso deja una firma temporal inequivoca:
un hueco de segundos DENTRO de cada par y un hueco de decenas de segundos ENTRE
prendas. La distribucion de huecos medida sobre estas fotos es bimodal con un
valle limpio:

    <=5s: 100 huecos      21-40s:  18
    6-10s: 14             41-90s:  58
    11-20s: 3             >90s:    41

El umbral se fija en 20 s, no por gusto: entre 15 y 20 s el resultado no se
mueve (118-119 grupos); a 30 s empieza a fusionar prendas distintas (aparecen
grupos de 4, 5 y 6 fotos). Un parametro cuyo valor da igual dentro de un rango
amplio es un parametro seguro.

Como se verifica
----------------
El reloj podria mentir. Asi que ademas se comprueba con las imagenes: se calcula
una huella barata (miniatura 32x32 en gris, centrada y normalizada) y se compara
la similitud DENTRO de cada par con la similitud ENTRE prendas contiguas. Si el
emparejamiento fuese ruido, las dos distribuciones se solaparian.

    dentro del par:      mediana 0,947
    prendas contiguas:   mediana 0,372

No se solapan. El emparejamiento es correcto.

Ojo con la huella, que no es un modelo: en prendas de rayas puede hundirse
(un jersey de rayas dio 0,18 porque las rayas se desplazaron media franja al
recolocarlo). Por eso una similitud baja se marca para revisar a ojo, no se usa
para deshacer un par que el reloj sostiene.

Salida
------
`pares.csv`, con una fila por foto:

    prenda_id, toma, fichero, sello, sim_par, luminancia

`prenda_id` es lo que usa el resto del pipeline; `toma` vale "a" o "b". No se
renombra ni se mueve ningun fichero original.

Uso
---
    python src/emparejar_tomas.py --fotos "data/raw/wardrobe/img" \
        --out data/raw/wardrobe/pares.csv
"""

from __future__ import annotations

import argparse
import collections
import pathlib
import re
import sys
from datetime import datetime

import numpy as np
import pandas as pd
from PIL import Image

SELLO = re.compile(r"(\d{8})[_-]?(\d{6})")
EXTENSIONES = {".jpg", ".jpeg", ".png", ".webp"}


def huella(ruta: pathlib.Path, lado: int = 32) -> np.ndarray:
    """Miniatura en gris, centrada y de norma unitaria.

    `draft` deja que el decodificador JPEG salte directamente a una escala
    reducida: con 236 fotos de movil la diferencia es de minutos a segundos.
    Centrar (restar la media) hace la huella insensible al brillo global, que
    aqui varia entre fotos; normalizar la hace comparable con un coseno.
    """
    with Image.open(ruta) as im:
        im.draft("L", (lado * 2, lado * 2))
        v = np.asarray(im.convert("L").resize((lado, lado)), dtype=np.float32)
    lum = float(v.mean())
    v = v.ravel() - v.mean()
    return v / (np.linalg.norm(v) + 1e-8), lum


def agrupar(sellos: list[datetime], umbral: float) -> list[list[int]]:
    grupos, act = [], [0]
    for i in range(1, len(sellos)):
        if (sellos[i] - sellos[i - 1]).total_seconds() <= umbral:
            act.append(i)
        else:
            grupos.append(act)
            act = [i]
    grupos.append(act)
    return grupos


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--fotos", type=pathlib.Path, required=True)
    p.add_argument("--out", type=pathlib.Path,
                   default=pathlib.Path("data/raw/wardrobe/pares.csv"))
    p.add_argument("--umbral", type=float, default=20.0,
                   help="Segundos entre tomas de la misma prenda")
    args = p.parse_args()

    ficheros = sorted(q for q in args.fotos.rglob("*")
                      if q.suffix.lower() in EXTENSIONES)
    if not ficheros:
        print(f"ERROR: no hay imagenes en {args.fotos}", file=sys.stderr)
        return 1

    reg, sin_sello, vacios = [], [], []
    for q in ficheros:
        # Un fichero de 0 bytes es una copia que se corto. No es una foto y no
        # debe parar el proceso, pero tampoco desaparecer en silencio.
        if q.stat().st_size == 0:
            vacios.append(q.name)
            continue
        m = SELLO.search(q.name)
        if not m:
            sin_sello.append(q.name)
            continue
        try:
            t = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
        except ValueError:
            sin_sello.append(q.name)
            continue
        reg.append((t, q))

    if vacios:
        print(f"AVISO: {len(vacios)} ficheros vacios, ignorados: {vacios[:5]}")

    if sin_sello:
        # Sin marca de tiempo no hay forma de situar la foto en la secuencia, y
        # colocarla "donde caiga" emparejaria prendas al azar. Se para.
        print(f"ERROR: {len(sin_sello)} ficheros sin marca de tiempo en el "
              f"nombre: {sin_sello[:5]}", file=sys.stderr)
        return 1

    reg.sort(key=lambda x: x[0])
    sellos = [t for t, _ in reg]
    print(f"{len(reg)} fotos | {sellos[0]} -> {sellos[-1]}")

    # --- estabilidad del umbral, para que la eleccion sea auditable ----------
    print("\nestabilidad del umbral:")
    for u in (8, 12, 15, 20, 25, 30, 45):
        g = agrupar(sellos, u)
        tam = collections.Counter(len(x) for x in g)
        print(f"  {u:>2}s -> {len(g):>3} grupos  "
              + " ".join(f"[{k}]x{v}" for k, v in sorted(tam.items())))

    grupos = agrupar(sellos, args.umbral)
    print(f"\numbral elegido: {args.umbral:g}s -> {len(grupos)} prendas")

    # --- huellas y verificacion ---------------------------------------------
    print("calculando huellas ...")
    H, LUM = {}, {}
    for t, q in reg:
        H[q], LUM[q] = huella(q)

    dentro, entre = [], []
    for g in grupos:
        if len(g) >= 2:
            dentro.append(float(H[reg[g[0]][1]] @ H[reg[g[1]][1]]))
    for i in range(len(grupos) - 1):
        entre.append(float(H[reg[grupos[i][-1]][1]] @ H[reg[grupos[i + 1][0]][1]]))
    dentro, entre = np.array(dentro), np.array(entre)

    print(f"\nverificacion por imagen (huella 32x32, no es el modelo):")
    print(f"  dentro del par:    mediana {np.median(dentro):.3f}  "
          f"p05 {np.percentile(dentro, 5):.3f}  min {dentro.min():.3f}")
    print(f"  prendas contiguas: mediana {np.median(entre):.3f}  "
          f"p95 {np.percentile(entre, 95):.3f}  max {entre.max():.3f}")
    if np.median(dentro) <= np.percentile(entre, 95):
        print("  ALTO: las dos distribuciones se solapan. El emparejamiento por "
              "reloj NO esta respaldado por las imagenes. No sigas.")
        return 1
    print("  separadas: el emparejamiento por reloj se sostiene.")

    # --- salida --------------------------------------------------------------
    filas = []
    for k, g in enumerate(grupos):
        sim = (float(H[reg[g[0]][1]] @ H[reg[g[1]][1]]) if len(g) >= 2
               else float("nan"))
        for j, i in enumerate(g):
            t, q = reg[i]
            filas.append({
                "prenda_id": f"w_{k:04d}",
                "toma": "abcdef"[j] if j < 6 else str(j),
                "fichero": q.relative_to(args.fotos).as_posix(),
                "sello": t.isoformat(sep=" "),
                "n_tomas": len(g),
                "sim_par": round(sim, 4),
                "luminancia": round(LUM[q], 1),
            })
    df = pd.DataFrame(filas)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False, encoding="utf-8-sig")

    raros = df[df["n_tomas"] != 2]["prenda_id"].unique()
    flojos = df[(df["toma"] == "a") & (df["sim_par"] < 0.75)]
    oscuras = df[df["luminancia"] < df["luminancia"].quantile(0.05)]

    print(f"\nescrito {args.out}  ({len(df)} filas, "
          f"{df['prenda_id'].nunique()} prendas)")
    if len(raros):
        print(f"  prendas sin dos tomas ({len(raros)}): {list(raros)[:10]}")
    if len(flojos):
        print(f"  pares con huella floja, revisar a ojo ({len(flojos)}): "
              f"{flojos['prenda_id'].tolist()[:10]}")
    print(f"  luminancia media {df['luminancia'].mean():.0f} "
          f"(p05 {df['luminancia'].quantile(0.05):.0f}, "
          f"p95 {df['luminancia'].quantile(0.95):.0f}) "
          f"- {len(oscuras)} fotos en el 5% mas oscuro")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
