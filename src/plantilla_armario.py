"""
Plantilla de etiquetado del armario real (conjunto de test out-of-distribution).

Por qué existe en dos pasadas
-----------------------------
El protocolo pide etiquetar el armario con el mismo vocabulario de atributos que
DeepFashion. Ese vocabulario todavía no se conoce: sale del EDA (paso 2), que
está pendiente de la descarga. Esperar significaría no poder fotografiar nada.

Se parte en dos:

  PASADA A (ahora, sin dependencias)
    Foto + categoría + slot + color base + notas libres sobre corte, textura y
    tejido. Estos campos los fija la taxonomía del propio proyecto, no
    DeepFashion, así que se pueden congelar hoy.

  PASADA B (después del EDA)
    Mapear esas notas libres al vocabulario real de atributos. Es rápido porque
    las fotos y las notas ya existen: es traducir, no volver a mirar.

Aviso metodológico, y no es menor: las notas de la pasada A se escriben antes de
ver ninguna salida del modelo, que es lo que el protocolo exige. Para la pasada B
eso ya no se puede garantizar — para entonces habrá números. La mitigación es
hacer la B **solo desde la nota y la foto**, sin abrir ningún ranking, y
declararlo como limitación en la memoria. Es honesto y es defendible; fingir que
no existe el problema, no.

Uso
---
    python plantilla_armario.py init --fotos data/raw/wardrobe/img --out data/raw/wardrobe/armario.csv
    python plantilla_armario.py validar --csv data/raw/wardrobe/armario.csv

El CSV se escribe en utf-8-sig para que Excel en Windows no destroce los acentos.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import pandas as pd

EXTENSIONES = {".jpg", ".jpeg", ".png", ".webp", ".heic"}

# ---------------------------------------------------------------------------
# Taxonomías congeladas
# ---------------------------------------------------------------------------
# `slot` es función determinista de `categoria` (entrega 3 §6): se materializa
# como columna porque filtrar por slot es la operación más frecuente, pero no es
# un dato que se declare a mano — lo rellena este script y el validador lo
# comprueba. Si se dejara al criterio de quien etiqueta, habría camisas en
# `outer` un martes a la una de la mañana.

CATEGORIAS: dict[str, str] = {
    # top
    "camiseta": "top", "polo": "top", "camisa": "top",
    "sudadera": "top", "jersey": "top", "cardigan": "top",
    # outer
    "chaqueta": "outer", "cazadora": "outer", "abrigo": "outer",
    "blazer": "outer", "chaleco": "outer",
    # bottom
    "pantalon": "bottom", "vaquero": "bottom", "chino": "bottom",
    "bermuda": "bottom", "jogger": "bottom",
    # shoes
    "zapatilla": "shoes", "zapato": "shoes", "bota": "shoes", "sandalia": "shoes",
    # accessory — se registran, pero quedan FUERA de la evaluación del core
    # (entrega 3 §8.8: los accesorios no textiles se descartan)
    "gorra": "accessory", "cinturon": "accessory",
    "bufanda": "accessory", "mochila": "accessory",
}

COLORES = [
    "negro", "blanco", "gris", "beige", "marron", "camel",
    "azul_marino", "azul", "celeste", "verde", "verde_oliva",
    "rojo", "burdeos", "amarillo", "naranja", "rosa", "morado",
    "multicolor",
]

# Valores de corte de la entrega 3 §6. Opcional: el sistema funciona sin él.
CORTES = ["slim", "regular", "oversize", "relaxed"]

# Fondos permitidos. No es un capricho de metadato: el protocolo de foto pide
# fondo que contraste con la prenda, asi que el fondo VARIA entre fotos. Si no
# se registra, mas tarde no hay forma de comprobar si parte de la diferencia
# medida frente al catalogo la explica el fondo y no la prenda. Cuesta una
# columna; no tenerla cuesta el argumento.
FONDOS = ["claro", "oscuro", "colcha_rayas"]

# `colcha_rayas` no estaba en el protocolo: es lo que habia. Se anade al
# vocabulario en vez de forzar la realidad dentro de "claro" porque la
# diferencia importa —una colcha de rayas mete textura periodica en el
# encuadre— y porque una etiqueta que miente es peor que una etiqueta fea.

COLUMNAS = [
    "item_id", "fichero", "categoria", "descripcion_libre", "slot", "color_base",
    "corte", "tejido", "fondo", "notas_textura", "notas_corte", "excluir",
]


# ---------------------------------------------------------------------------

def filas_desde_pares(pares_csv: pathlib.Path,
                      fondo: str) -> tuple[pd.DataFrame, int, int]:
    """Una fila por PRENDA, tomando la primera toma como representante.

    Con dos fotos por prenda, etiquetar por foto significa escribir "camisa,
    beige" dos veces por prenda y abre la puerta a que las dos filas de la
    misma prenda acaben con etiquetas distintas. La unidad de etiquetado es la
    prenda; las tomas son del emparejamiento (`pares.csv`), no de quien
    etiqueta.
    """
    pares = pd.read_csv(pares_csv, dtype=str, keep_default_na=False,
                        encoding="utf-8-sig")
    for col in ("prenda_id", "toma", "fichero"):
        if col not in pares.columns:
            raise SystemExit(f"{pares_csv} no tiene la columna '{col}'. "
                             f"Genera el fichero con src/emparejar_tomas.py.")
    primeras = (pares.sort_values(["prenda_id", "toma"])
                     .groupby("prenda_id", as_index=False).first())
    n_tomas = pares.groupby("prenda_id").size().rename("n")
    return pd.DataFrame([
        {
            "item_id": r["prenda_id"],
            "fichero": r["fichero"],
            "categoria": "", "descripcion_libre": "", "slot": "", "color_base": "",
            "corte": "", "tejido": "", "fondo": fondo,
            "notas_textura": "", "notas_corte": "",
            "excluir": "",
        }
        for _, r in primeras.iterrows()
    ], columns=COLUMNAS), int(n_tomas.eq(2).sum()), len(primeras)


def cmd_init(args: argparse.Namespace) -> int:
    if getattr(args, "pares", None):
        nuevo, con_dos, total = filas_desde_pares(
            pathlib.Path(args.pares), args.fondo)
        salida = pathlib.Path(args.out)
        if salida.exists():
            print(f"ERROR: {salida} ya existe. En modo --pares no se amplia: "
                  f"borralo a mano si de verdad quieres empezar de cero.",
                  file=sys.stderr)
            return 1
        salida.parent.mkdir(parents=True, exist_ok=True)
        nuevo.to_csv(salida, index=False, encoding="utf-8-sig")
        print(f"{salida} creado con {len(nuevo)} filas "
              f"({con_dos} prendas con dos tomas de {total}).")
        print(f"\nCategorías válidas ({len(CATEGORIAS)}): "
              f"{', '.join(sorted(CATEGORIAS))}")
        print(f"\nColores válidos ({len(COLORES)}): {', '.join(COLORES)}")
        print(f"\nCortes válidos: {', '.join(CORTES)}  (opcional)")
        print(f"\n'fondo' viene relleno con '{args.fondo}' porque fue el mismo "
              f"en todas las fotos. Cambialo solo donde no lo fuera.")
        return 0

    if not args.fotos:
        print("ERROR: hace falta --pares (una fila por prenda) o --fotos "
              "(una fila por foto).", file=sys.stderr)
        return 1

    fotos = pathlib.Path(args.fotos)
    if not fotos.is_dir():
        print(f"ERROR: no existe el directorio de fotos: {fotos}", file=sys.stderr)
        return 1

    imagenes = sorted(
        p for p in fotos.rglob("*") if p.suffix.lower() in EXTENSIONES
    )
    if not imagenes:
        print(f"ERROR: ninguna imagen en {fotos} (extensiones: {sorted(EXTENSIONES)})",
              file=sys.stderr)
        return 1

    salida = pathlib.Path(args.out)
    filas = [
        {
            "item_id": f"w_{i:04d}",
            "fichero": str(p.relative_to(fotos)).replace("\\", "/"),
            "categoria": "", "descripcion_libre": "", "slot": "", "color_base": "",
            "corte": "", "tejido": "", "fondo": "",
            "notas_textura": "", "notas_corte": "",
            "excluir": "",
        }
        for i, p in enumerate(imagenes)
    ]
    nuevo = pd.DataFrame(filas, columns=COLUMNAS)

    if salida.exists():
        # Nunca se pisa trabajo ya hecho: se conservan las filas rellenadas y
        # solo se añaden las fotos nuevas. Perder dos horas de etiquetado por
        # relanzar un comando seria un final absurdo.
        previo = pd.read_csv(salida, dtype=str, keep_default_na=False,
                             encoding="utf-8-sig")
        ya = set(previo["fichero"])
        añadidas = nuevo[~nuevo["fichero"].isin(ya)]
        if añadidas.empty:
            print(f"{salida} ya cubre las {len(imagenes)} fotos. Nada que añadir.")
            return 0
        # Los item_id nuevos continúan la numeración existente.
        base = len(previo)
        añadidas = añadidas.copy()
        añadidas["item_id"] = [f"w_{base + i:04d}" for i in range(len(añadidas))]
        combinado = pd.concat([previo, añadidas], ignore_index=True)
        combinado.to_csv(salida, index=False, encoding="utf-8-sig")
        print(f"{len(añadidas)} fotos nuevas añadidas. Total: {len(combinado)}.")
        return 0

    salida.parent.mkdir(parents=True, exist_ok=True)
    nuevo.to_csv(salida, index=False, encoding="utf-8-sig")
    print(f"{salida} creado con {len(nuevo)} filas.")
    print(f"\nCategorías válidas ({len(CATEGORIAS)}): {', '.join(sorted(CATEGORIAS))}")
    print(f"\nColores válidos ({len(COLORES)}): {', '.join(COLORES)}")
    print(f"\nCortes válidos: {', '.join(CORTES)}  (opcional, se puede dejar vacío)")
    print(f"\nFondos válidos: {', '.join(FONDOS)}  (opcional, pero rellénalo)")
    print("\n`slot` lo rellena el validador a partir de `categoria`. No lo toques.")
    return 0


def cmd_validar(args: argparse.Namespace) -> int:
    csv = pathlib.Path(args.csv)
    if not csv.exists():
        print(f"ERROR: no existe {csv}", file=sys.stderr)
        return 1

    df = pd.read_csv(csv, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    problemas: list[str] = []

    faltan = [c for c in COLUMNAS if c not in df.columns]
    if faltan:
        print(f"ERROR: faltan columnas: {faltan}", file=sys.stderr)
        return 1

    activo = df[df["excluir"].str.strip() == ""]
    excluidas = len(df) - len(activo)

    # --- obligatorio de verdad: solo la categoria ---
    # `categoria` es lo unico que bloquea la medicion del domain gap: es la
    # etiqueta contra la que se comprueba si un resultado recuperado es
    # correcto. `color_base` hace falta para el producto (filtros, reglas de
    # combinacion) pero no interviene en ninguna metrica, asi que no puede
    # impedir que el pipeline corra. Se avisa, no se bloquea.
    vacias = activo[activo["categoria"].str.strip() == ""]
    if len(vacias):
        problemas.append(
            f"{len(vacias)} filas sin 'categoria': "
            f"{', '.join(vacias['item_id'].head(8))}"
            + (" ..." if len(vacias) > 8 else "")
        )

    sin_color = activo[activo["color_base"].str.strip() == ""]
    avisos = []
    if len(sin_color):
        avisos.append(
            f"{len(sin_color)} filas sin 'color_base'. No bloquea: el color no "
            f"entra en ninguna metrica. Hace falta para los filtros del producto."
        )

    # --- vocabulario cerrado ---
    def fuera(col: str, validos) -> None:
        vals = activo[col].str.strip().str.lower()
        malas = activo[(vals != "") & (~vals.isin(validos))]
        if len(malas):
            ejemplos = malas[["item_id", col]].head(8).to_dict("records")
            problemas.append(f"valores de '{col}' fuera de vocabulario: {ejemplos}")

    fuera("categoria", set(CATEGORIAS))
    fuera("color_base", set(COLORES))
    fuera("corte", set(CORTES))
    fuera("fondo", set(FONDOS))

    # --- duplicados ---
    for col in ("item_id", "fichero"):
        dup = df[df.duplicated(col, keep=False) & (df[col].str.strip() != "")]
        if len(dup):
            problemas.append(f"'{col}' duplicado en {len(dup)} filas")

    if avisos:
        print("AVISOS (no bloquean):\n")
        for a in avisos:
            print(f"  - {a}")
        print()

    if problemas:
        print("PROBLEMAS:\n")
        for p in problemas:
            print(f"  - {p}")
        print("\nCorrígelos y vuelve a validar. No se ha escrito nada.")
        return 1

    # --- normalización al escribir ---
    # La validación es insensible a mayúsculas (nadie etiqueta 150 prendas de
    # madrugada con capitalización perfecta), pero lo que se GUARDA tiene que
    # estar normalizado: si el CSV conserva "VAQUERO" y el resto del pipeline
    # busca "vaquero", el join falla en silencio y la prenda desaparece de la
    # evaluación sin que nadie lance un error.
    for col in ("categoria", "color_base", "corte", "tejido"):
        df.loc[activo.index, col] = activo[col].str.strip().str.lower()

    # --- slot derivado, no declarado ---
    df.loc[activo.index, "slot"] = df.loc[activo.index, "categoria"].map(CATEGORIAS)
    df.to_csv(csv, index=False, encoding="utf-8-sig")

    print(f"OK. {len(activo)} prendas activas ({excluidas} excluidas). "
          f"'slot' rellenado desde 'categoria'.\n")
    print("Por slot:")
    print(df.loc[activo.index, "slot"].value_counts().to_string())
    print("\nPor color:")
    print(activo["color_base"].str.lower().value_counts().to_string())

    del_core = df.loc[activo.index, "slot"].ne("accessory").sum()
    print(f"\nPrendas que entran en la evaluación del core (sin accesorios): {del_core}")
    if del_core < 80:
        print("  AVISO: por debajo de las 80 del rango previsto en la entrega 2. "
              "Con menos prendas los intervalos de confianza se abren todavía más.")
    elif del_core < 150:
        print(f"  Vas por {del_core}. El objetivo son 150: con ~100 la diferencia "
              "entre condiciones probablemente no salga significativa.")

    sin_nota = activo[
        (activo["notas_textura"].str.strip() == "")
        & (activo["notas_corte"].str.strip() == "")
        # `descripcion_libre` cuenta como nota: es texto escrito por la persona
        # mirando la prenda y ANTES de ver ninguna salida del modelo, que es la
        # condicion que el protocolo exige. Que vaya en una columna u otra es
        # irrelevante; lo que importa es cuando se escribio.
        & (activo.get("descripcion_libre", pd.Series("", index=activo.index))
                 .astype(str).str.strip() == "")
    ]
    if len(sin_nota):
        print(f"\n{len(sin_nota)} prendas sin ninguna nota de textura ni corte. "
              "Las notas son la materia prima de la pasada B: sin ellas habrá que "
              "volver a mirar la foto cuando ya existan resultados, que es "
              "justo lo que el protocolo intenta evitar.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("init", help="crea o amplía el CSV a partir de las fotos")
    i.add_argument("--fotos", help="directorio de fotos (una fila por foto)")
    i.add_argument("--pares", help="pares.csv de emparejar_tomas.py "
                                   "(una fila por prenda). Excluyente con --fotos")
    i.add_argument("--fondo", default="colcha_rayas",
                   help="valor con el que prerrellenar la columna 'fondo'")
    i.add_argument("--out", default="data/raw/wardrobe/armario.csv")
    i.set_defaults(func=cmd_init)

    v = sub.add_parser("validar", help="valida el CSV y deriva 'slot'")
    v.add_argument("--csv", default="data/raw/wardrobe/armario.csv")
    v.set_defaults(func=cmd_validar)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
