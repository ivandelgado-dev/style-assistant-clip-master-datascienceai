"""
Outfits por estilo y color con las prendas del armario.

Qué hace
--------
Dado un estilo (streetwear, smart casual…) y, si se quiere, un color, arma
conjuntos arriba + abajo (+ encima) con las prendas del usuario y los ordena
por una puntuación de reglas. Es la función 2 del MVP de la Entrega 2: «el
outfit del día, filtrable por estilo y por paleta».

Por qué reglas y no un modelo
-----------------------------
- La compatibilidad aprendida (Polyvore) quedó fuera por tiempo, y un LLM no
  decide el outfit: esa decisión tiene que ser reproducible y evaluable.
- Las reglas son las de un estilista, escritas aquí y leíbles: qué tipos
  encajan en cada estilo, cuántos colores, qué estampados. Misma entrada,
  mismo resultado, y cada outfit lleva sus razones.
- Lo que NO son: una medida de qué queda bien. No hay datos para medirlo en
  el tiempo del trabajo; se recoge la valoración del usuario (tabla
  `feedback`) para poder medirlo después.

De dónde sale cada dato de la prenda
------------------------------------
- tipo, estampado, tejido, manga: etiquetas de la IA (etiquetas.py), y si no
  hay, la categoría que puso el usuario.
- color: el nombre que da la IA para las reglas de familias; el color medido
  en píxeles (Lab, color.py) para el Diccionario de Wada.
- corte: SOLO lo que declara el usuario (ajustado / recto / holgado). La IA
  no mide el ajuste de una prenda extendida, así que Oversize solo existe si
  el usuario lo ha declarado.

El Diccionario de Wada
----------------------
Sanzo Wada, «A Dictionary of Color Combinations» (Japón, 1933; reedición de
Seigensha). 348 combinaciones de 2, 3 y 4 colores entre 159 colores. Datos:
github.com/mattdesl/dictionary-of-colour-combinations (MIT; licencia en
paginas/datos/WADA_LICENSE.md), con los colores en CIELAB. Una prenda «es»
de un color de la paleta si está a menos del umbral de color cercano
calibrado en el armario ANTES de esto (ΔE CMC 9,05, experiments/
color_primero/calibracion.json): no se ha ajustado mirando outfits.
"""

from __future__ import annotations

import json
import pathlib
import re
from collections import defaultdict

import numpy as np

from paginas import color as _color
from paginas.armario import clave_categoria as _clave
from paginas import etiquetas as _etq

# ---------------------------------------------------------------------------
# Estilos
# ---------------------------------------------------------------------------
# tipos: 2 = prenda propia del estilo, 1 = encaja. Lo que no está, no entra.
# encima: "no" | "opcional" | "recomendado".
ESTAMPADOS_FUERTES = {"estampado", "logo", "camuflaje", "cuadros"}

ESTILOS = {
    "casual": {
        "nombre": "Casual",
        "idea": "Lo de todos los días: básicos que combinan sin pensar.",
        "arriba": {"camiseta": 2, "polo": 2, "camisa": 1, "sudadera": 1, "jersey": 1},
        "abajo": {"vaquero": 2, "chino": 2, "pantalon": 1, "bermuda": 1},
        "encima": {"cazadora": 2, "chaqueta": 2, "cardigan": 1, "sudadera": 1, "abrigo": 1},
        "capa": "opcional",
    },
    "streetwear": {
        "nombre": "Streetwear",
        "idea": "Sudaderas, gráficos y pantalón con volumen.",
        "arriba": {"sudadera": 2, "camiseta": 2, "camisa": 1},
        "abajo": {"vaquero": 2, "jogger": 2, "bermuda": 2, "pantalon": 1},
        "encima": {"cazadora": 2, "sudadera": 2, "chaqueta": 1, "chaleco": 1},
        "capa": "opcional",
    },
    "athleisure": {
        "nombre": "Athleisure",
        "idea": "Ropa deportiva para la calle: punto y tejido técnico.",
        "arriba": {"camiseta": 2, "sudadera": 2},
        "abajo": {"jogger": 2, "bermuda": 1},
        "encima": {"sudadera": 2, "chaqueta": 2, "cazadora": 1},
        "capa": "opcional",
    },
    "minimalista": {
        "nombre": "Minimalista",
        "idea": "Liso, neutros y como mucho un color.",
        "arriba": {"camiseta": 2, "camisa": 2, "jersey": 2, "polo": 1, "sudadera": 1},
        "abajo": {"pantalon": 2, "chino": 2, "vaquero": 1},
        "encima": {"abrigo": 2, "chaqueta": 2, "blazer": 1, "cardigan": 1, "cazadora": 1},
        "capa": "opcional",
    },
    "smart_casual": {
        "nombre": "Smart Casual",
        "idea": "Arreglado sin traje: camisa o polo, chino, y americana si hace falta.",
        "arriba": {"camisa": 2, "polo": 2, "jersey": 1, "camiseta": 1},
        "abajo": {"chino": 2, "pantalon": 2, "vaquero": 1},
        "encima": {"blazer": 2, "chaqueta": 1, "cardigan": 1, "abrigo": 1},
        "capa": "opcional",
    },
    "business_casual": {
        "nombre": "Business Casual",
        "idea": "Oficina sin corbata: camisa, pantalón de vestir o chino, americana.",
        "arriba": {"camisa": 2, "polo": 1, "jersey": 1},
        "abajo": {"pantalon": 2, "chino": 2},
        "encima": {"blazer": 2, "cardigan": 1, "abrigo": 1},
        "capa": "recomendado",
    },
    "preppy": {
        "nombre": "Preppy",
        "idea": "Universitario clásico: polo, camisa, punto, chino; rayas y cuadros.",
        "arriba": {"polo": 2, "camisa": 2, "jersey": 1, "cardigan": 1},
        "abajo": {"chino": 2, "bermuda": 1, "pantalon": 1, "vaquero": 1},
        "encima": {"blazer": 2, "cardigan": 2, "jersey": 1},
        "capa": "opcional",
    },
    "rocker": {
        "nombre": "Rocker",
        "idea": "Negro, vaquero oscuro y cazadora; si es de cuero, mejor.",
        "arriba": {"camiseta": 2, "camisa": 1},
        "abajo": {"vaquero": 2, "pantalon": 1},
        "encima": {"cazadora": 2, "chaqueta": 1},
        "capa": "recomendado",
    },
    "grunge": {
        "nombre": "Grunge",
        "idea": "Capas desgastadas: camiseta, camisa de cuadros abierta, vaquero; colores apagados.",
        "arriba": {"camiseta": 2, "jersey": 1, "sudadera": 1},
        "abajo": {"vaquero": 2, "pantalon": 1},
        "encima": {"camisa": 2, "cardigan": 2, "cazadora": 1},
        "capa": "recomendado",
    },
    "oversize": {
        "nombre": "Oversize",
        "idea": "Volumen: prendas holgadas. Solo con el corte declarado en Mi armario.",
        "arriba": {"camiseta": 2, "sudadera": 2, "camisa": 1},
        "abajo": {"vaquero": 2, "pantalon": 2, "jogger": 1, "bermuda": 1},
        "encima": {"cazadora": 1, "chaqueta": 1, "sudadera": 1},
        "capa": "opcional",
    },
}
ORDEN_ESTILOS = list(ESTILOS)

# Colores que se pueden pedir y qué nombres de color entran en cada uno.
COLORES_PEDIDO = {
    "negro": {"negro"},
    "gris": {"gris oscuro", "gris", "gris claro"},
    "blanco": {"blanco", "crudo"},
    "beige y marrón": {"beige", "camel", "marron", "marrón", "caqui"},
    "azul": {"azul marino", "azul", "azul claro", "vaquero"},
    "verde": {"verde", "verde oscuro", "caqui"},
    "rojo": {"rojo", "burdeos"},
    "rosa": {"rosa", "rosa palo"},
    "amarillo y naranja": {"amarillo", "naranja"},
}
# Neutros de un armario de hombre: combinan con todo. El vaquero azul cuenta
# como neutro, como en cualquier manual de estilo masculino.
NEUTROS = {"negro", "gris oscuro", "gris", "gris claro", "blanco", "crudo",
           "beige", "camel", "azul marino"}

# Proporción (opcional, la activa el usuario con su altura en Mi cuenta).
# Convención de estilismo, no un resultado: por debajo de ~1,70 m, poco
# contraste de claridad entre arriba y abajo alarga la figura, porque no corta
# el cuerpo en dos. Solo SUMA a los looks que lo cumplen: no quita ninguno, se
# enseña en la ficha y se apaga. No hay regla por peso (ver vistas._mi_cuenta).
ALTURA_ALARGAR = 170       # cm
CONTRASTE_BAJO = 20.0      # diferencia de L* (CIELAB, 0-100) entre arriba y abajo

# Pesos de la puntuación: explícitos para que se puedan leer y discutir.
PESO = {"afinidad": 1.0, "regla": 1.0, "armonia": 1.0, "wada": 2.0}


# ---------------------------------------------------------------------------
# Prendas
# ---------------------------------------------------------------------------

def prendas_de(arm) -> list[dict]:
    """Filas de armario_usuario() -> lo que necesitan las reglas."""
    out = []
    for i, r in enumerate(arm.itertuples(index=False)):
        e = r.etiquetas if isinstance(r.etiquetas, dict) else {}
        lab = np.array([r.color_l, r.color_a, r.color_b], dtype=float)
        nom = e.get("color") or (_color.nombre_color(lab) if np.all(np.isfinite(lab)) else None)
        nom = {"marrón": "marron"}.get(nom, nom)
        # Lo que declara el usuario manda sobre la IA, si es un color conocido.
        dec = _clave(r.color) if isinstance(r.color, str) else ""
        if dec in _etq.COLORES:
            nom = dec
        def txt(x):      # sin tildes ni mayúsculas: «Algodón» == algodon
            return _clave(x) if isinstance(x, str) else ""
        tejido = txt(r.tejido) or e.get("tejido")
        tipo = e.get("tipo") or txt(r.categoria)
        # Un pantalón corto es una bermuda para las reglas, aunque la categoría
        # diga «pantalon» (visto en uso: un «pantalón pirata» salía en Smart
        # Casual con nivel 2, mientras las bermudas no entraban).
        if r.posicion == "abajo" and e.get("largo") == "corto" and tipo in ("pantalon", "chino", "vaquero"):
            tipo = "bermuda"
        desc = _clave(str(e.get("descripcion") or ""))
        texto = desc + " " + txt(r.notas)
        ras = e.get("rasgos") if isinstance(e.get("rasgos"), dict) else {}
        estampado = e.get("estampado") or "liso"
        fz, fz_por, fz_marcas = formalidad(tipo, estampado, e.get("manga"),
                                           e.get("largo"), desc, rasgos=ras,
                                           notas=txt(r.notas))
        out.append({
            "i": i, "id": int(r.id), "posicion": r.posicion,
            "tipo": tipo,
            "color": nom, "lab": lab if np.all(np.isfinite(lab)) else None,
            "estampado": estampado,
            "tejido": tejido, "manga": e.get("manga"),
            "corte": txt(r.corte) or None,
            "informal": _informal(e.get("tipo") or txt(r.categoria), e, txt(r.notas)),
            "vestir": any(w in _clave(str(e.get("descripcion") or "")) + " " + txt(r.notas)
                          for w in ("de vestir", "traje")),
            "largo": e.get("largo"),
            "formalidad": fz, "formal_por": fz_por, "marcas": fz_marcas,
            "logo_discreto": bool(ras.get("logo_discreto")) or _hay(texto, "bordad", "pequen"),
            "manga_corta": (e.get("manga") == "corta" or bool(ras.get("manga_corta"))
                            or _hay(texto, "manga corta")),
            "cuello_alto": bool(ras.get("cuello_alto")) or _hay(
                texto, "cuello vuelto", "cuello alto", "cuello cisne"),
            "sobrecamisa": bool(ras.get("sobrecamisa")) or _hay(texto, "sobrecamisa", "overshirt"),
        })
    return out


# ---------------------------------------------------------------------------
# Formalidad (1-5): lo que el tipo solo no dice
# ---------------------------------------------------------------------------
# El tipo cerrado no distingue una camisa de vestir de una de béisbol ni un
# chino de un cargo. La formalidad sale del tipo y de la descripción de la IA
# (que ha visto la foto) más las notas del usuario, con reglas escritas aquí.
# Visto en uso: una camisa de béisbol salía «muy Preppy» y en Business Casual.
# Escala, la de las guías de vestimenta: 1 deporte, 2 informal, 3 casual,
# 4 arreglado, 5 formal.
FORMAL_NOMBRE = {1: "deporte", 2: "informal", 3: "casual", 4: "arreglado", 5: "formal"}
FORMAL_BASE = {"jogger": 1, "bermuda": 2, "sudadera": 2, "chaleco": 2, "camiseta": 2,
               "vaquero": 3, "pantalon": 3, "polo": 3, "jersey": 3, "cardigan": 3,
               "cazadora": 3, "chaqueta": 3, "chino": 4, "camisa": 4, "abrigo": 4,
               "blazer": 5}
# (palabra en el texto, cómo se dice): la primera que aparece manda.
_SUBE = [("de vestir", "de vestir"), ("formal", "formal"), ("milrayas", "milrayas"),
         ("oxford", "oxford"), ("elegante", "elegante"), ("clasic", "clásica"),
         ("traje", "de traje"), ("punto fino", "de punto fino"),
         ("cuello vuelto", "de cuello vuelto"), ("cuello alto", "de cuello alto"),
         ("cuello en pico", "de cuello de pico")]
_BAJA = [("informal", "informal")]
_TOPE = [  # (tope, palabra, cómo se dice, marca)
    (1, "chandal", "de chándal", "deporte"), (2, "deportiv", "deportiva", "deporte"),
    (1, "track", "de chándal", "deporte"), (1, "felpa", "de felpa", "deporte"),
    (1, "jogger", "jogger", "deporte"),
    (2, "cargo", "cargo", "cargo"), (2, "beisbol", "de béisbol", "fantasia"),
    (2, "baseball", "de béisbol", "fantasia"), (2, "bolos", "de bolos", "fantasia"),
    (2, "bowling", "de bolos", "fantasia"), (2, "hawaian", "hawaiana", "fantasia"),
    (2, "tie dye", "tie-dye", "fantasia"), (2, "tie-dye", "tie-dye", "fantasia"),
    (2, "roto", "rota", "roto"), (2, "capucha", "con capucha", "sudadera"),
    (2, "hoodie", "con capucha", "sudadera"), (2, "sudader", "de sudadera", "sudadera"),
    (3, "franela", "de franela", "rustica"), (3, "sobrecamisa", "sobrecamisa", "rustica"),
    (3, "lona", "de lona", "rustica"), (3, "baggy", "baggy", "volumen"),
    (3, "wide leg", "wide leg", "volumen"), (3, "slouchy", "slouchy", "volumen"),
    (3, "jorts", "jorts", "volumen"),
]
_GRAFICO = ("grafico", "calavera", "dibujo", "letras", "texto")


def _hay(texto: str, *palabras: str) -> bool:
    """Alguna palabra EMPIEZA una palabra del texto («formal» no casa con «informal»)."""
    return any(re.search(r"(?<![a-z])" + re.escape(w), texto) for w in palabras)


# Rasgos de la IA (etiquetas.RASGOS) que ponen tope, como las palabras.
# «deportiva» de la IA pone tope 2, no 1: en la revisión a mano marcaba
# también una bomber y una camiseta con un parche (experiments/rasgos_r1).
# El 1 (chándal de verdad) lo dan las palabras («chándal», «jogger»…).
_RASGO_TOPE = {"deportiva": (2, "deportiva", "deporte"), "cargo": (2, "cargo", "cargo"),
               "rota": (2, "rota", "roto"), "capucha": (2, "con capucha", "sudadera"),
               "fantasia": (2, "de fantasía", "fantasia"),
               "rustica": (3, "de trabajo", "rustica"), "volumen": (3, "ancha", "volumen")}


# Palabras con las que el usuario DICE cómo de arreglada es una prenda. Las
# que solo describen («cuello alto», «clásica», «lisa») no cuentan: visto en
# uso, «jersey de cuello alto con cremallera» tapaba que la IA veía una
# sudadera deportiva.
_DECLARACION = ("de vestir", "formal", "elegante", "traje", "informal", "casual",
                "chandal", "deportiv", "cargo", "jogger")


def _declara(notas: str) -> bool:
    """¿Dicen algo las notas del usuario sobre lo arreglada que es la prenda?"""
    return bool(notas) and _hay(notas, *_DECLARACION)


def formalidad(tipo: str, estampado: str, manga: str | None, largo: str | None,
               texto: str, rasgos: dict | None = None,
               notas: str = "") -> tuple[int, str, set]:
    """(nivel 1-5, lo que lo explica, marcas).

    Fuentes: el tipo; lo que la IA ve en la foto (`rasgos`, sí/no cerrados,
    y `texto`, su descripción); y las `notas` del usuario. Lo declarado manda:
    si las notas hablan de formalidad, cuentan ellas y no lo que vio la IA.
    """
    notas = notas or ""
    if _declara(notas):
        texto, rasgos = notas, None
    else:
        texto = f"{texto or ''} {notas}"
    R = rasgos or {}
    f = FORMAL_BASE.get(tipo, 3)
    por, marcas = "", set()
    corto = tipo == "bermuda" or largo == "corto"
    discreto = R.get("logo_discreto") or _hay(texto, "bordad", "pequen")
    grafico = (estampado in ("estampado", "camuflaje") or R.get("grafico_grande")
               or (estampado == "logo" and not discreto)
               or (_hay(texto, *_GRAFICO) and not discreto))
    if corto:
        # Una bermuda solo sube si es de sastre; «clásica» no la hace de vestir.
        if _hay(texto, "chino", "de vestir") or R.get("de_vestir"):
            f, por = f + 1, "tipo chino"
    else:
        sube = next((d for w, d in _SUBE if _hay(texto, w)), None) or (
            "de vestir" if R.get("de_vestir") else None)
        if sube:
            f, por = f + 1, sube
        elif tipo == "camiseta" and estampado in ("liso", "rayas") and not grafico:
            f, por = f + 1, "lisa" if estampado == "liso" else "de rayas"
        elif tipo == "polo" and _hay(texto, "punto", "manga larga"):
            f, por = f + 1, "de punto"
    baja = next((d for w, d in _BAJA if _hay(texto, w)), None)
    if baja:
        f, por = f - 1, baja
    elif tipo == "camisa" and (manga == "corta" or R.get("manga_corta")
                               or _hay(texto, "manga corta")):
        f, por = f - 1, "de manga corta"
    elif tipo == "camisa" and estampado == "cuadros":
        f, por = f - 1, "de cuadros"
    # Topes: primero los de las palabras (su nombre es más preciso: «de
    # béisbol» mejor que «de fantasía»), después los de los rasgos.
    topes = [(t, d, m) for t, w, d, m in _TOPE if _hay(texto, w)]
    topes += [v for k, v in _RASGO_TOPE.items() if R.get(k)]
    if tipo == "jogger":
        topes.append((1, "jogger", "deporte"))
    if grafico:
        topes.append((2, "con estampado", "grafico"))
    if corto:
        topes.append((3, "corta", "corto"))
    for t, d, m in sorted(topes, key=lambda x: x[0]):
        marcas.add(m)
        if f > t:
            f, por = t, d
    return max(1, min(5, f)), por, marcas


# Qué formalidad admite cada estilo, prenda a prenda (mín, máx).
VENTANA = {"casual": (1, 5), "streetwear": (1, 3), "athleisure": (1, 3),
           "minimalista": (2, 5), "smart_casual": (3, 5), "business_casual": (4, 5),
           "preppy": (3, 5), "rocker": (2, 4), "grunge": (2, 3), "oversize": (1, 4)}
# Excepciones por posición: una bermuda tipo chino (3) no es Athleisure.
VENTANA_POS = {("athleisure", "abajo"): (1, 2)}
# Dentro de un mismo look, de lo más informal a lo más formal, como mucho 2
# escalones: una camisa de vestir con una bermuda de chándal no es un estilo.
SALTO_MAX = 2


def _texto_ventana(v: tuple[int, int]) -> str:
    lo, hi = v
    if hi == 5:
        return f"de {FORMAL_NOMBRE[lo]} para arriba ({lo}/5 o más)"
    if lo == 1:
        return f"hasta {FORMAL_NOMBRE[hi]} ({hi}/5 como mucho)"
    return f"entre {FORMAL_NOMBRE[lo]} y {FORMAL_NOMBRE[hi]}"


def _fuera_de_ventana(estilo: str, p: dict) -> str | None:
    f = p.get("formalidad")
    if f is None:
        return None
    v = VENTANA_POS.get((estilo, p.get("posicion")), VENTANA[estilo])
    if v[0] <= f <= v[1]:
        return None
    que = f"{_leg(p['tipo']).capitalize()} {p.get('formal_por') or ''}".strip()
    return (f"{que}: formalidad {f}/5 ({FORMAL_NOMBRE[f]}). "
            f"{ESTILOS[estilo]['nombre']} pide {_texto_ventana(v)}.")


def capas_ok(a: dict, c: dict, b: dict) -> bool:
    """¿Se puede llevar `c` encima de `a`, con `b` abajo? Reglas de sastrería
    y de temporada, no de estilo: valen para todos."""
    corto_abajo = b["tipo"] == "bermuda" or b.get("largo") == "corto"
    camisa_corta = a["tipo"] in ("camisa", "polo") and a.get("manga_corta")
    if c["tipo"] in ("blazer", "abrigo"):
        # Ni americana ni abrigo con bermuda; ni sobre una camisa de manga corta.
        if corto_abajo or (a["tipo"] == "camisa" and a.get("manga_corta")):
            return False
    if a.get("sobrecamisa"):
        return False           # una sobrecamisa ya es la capa de fuera
    if c["tipo"] == "sudadera" and a["tipo"] not in ("camiseta", "camisa"):
        return False           # una sudadera encima de un polo o un jersey, no
    if c["tipo"] in ("jersey", "cardigan") and a["tipo"] in ("camisa", "polo"):
        # Bajo el punto, cuello a la vista y manga larga; y un cuello vuelto
        # no va sobre un cuello de camisa.
        if camisa_corta or c.get("cuello_alto"):
            return False
    return True


# Palabras que delatan una prenda informal aunque su tipo diga otra cosa: la
# lista cerrada de tipos no tiene «cargo», «chándal» ni «camisa de béisbol».
# Se miran en la descripción de la IA y en las notas del usuario, y cada una
# lleva cómo se dice en el veredicto. Visto en uso: una camisa de béisbol
# salía «muy Preppy» y válida para Business Casual con americana.
_INFORMAL = {"cargo": "cargo", "chandal": "de chándal", "deportiv": "deportiva",
             "jogger": "jogger", "sudader": "de sudadera", "beisbol": "de béisbol",
             "baseball": "de béisbol", "bolos": "de bolos", "bowling": "de bolos",
             "hawaian": "hawaiana"}


def _informal(tipo: str, e: dict, notas: str) -> str | None:
    """Qué la delata como informal («de béisbol», «cargo»…), o None."""
    if tipo == "jogger":
        return "jogger"
    texto = _clave(str(e.get("descripcion") or "")) + " " + (notas or "")
    return next((v for w, v in _INFORMAL.items() if w in texto), None)


def es_neutro(p: dict) -> bool:
    return p["color"] in NEUTROS or p["tejido"] == "vaquero" or p["color"] == "vaquero"


def familia(p: dict) -> str | None:
    if es_neutro(p):
        return None
    return _etq.FAMILIA_COLOR.get(p["color"], p["color"])


# ---------------------------------------------------------------------------
# Diccionario de Wada
# ---------------------------------------------------------------------------

_WADA = None


def wada() -> tuple[list[dict], dict[int, list[int]], np.ndarray]:
    """(colores, paleta -> índices de color, Lab de cada color)."""
    global _WADA
    if _WADA is None:
        f = pathlib.Path(__file__).resolve().parent / "datos" / "wada_colores.json"
        cols = json.loads(f.read_text(encoding="utf-8"))
        pal = defaultdict(list)
        for k, c in enumerate(cols):
            for n in c["combinaciones"]:
                pal[n].append(k)
        _WADA = (cols, dict(pal), np.array([c["lab"] for c in cols], dtype=float))
    return _WADA


def umbral_wada() -> float:
    """El umbral de «color cercano» calibrado en el armario (ΔE CMC)."""
    f = (pathlib.Path(__file__).resolve().parents[1]
         / "experiments/color_primero/calibracion.json")
    try:
        return float(json.loads(f.read_text(encoding="utf-8"))["umbral_color_cercano"])
    except Exception:
        return 9.05


def paletas_por_prenda(prendas: list[dict], umbral: float) -> list[dict[int, int]]:
    """Para cada prenda, {paleta: color de la paleta al que se parece}."""
    cols, pal, L = wada()
    out = []
    for p in prendas:
        d = {}
        if p["lab"] is not None:
            de = _color.delta_cmc(p["lab"], L)
            for n, ks in pal.items():
                k = min(ks, key=lambda j: de[j])
                if de[k] <= umbral:
                    d[n] = k
        out.append(d)
    return out


def paleta_comun(pps: list[dict[int, int]]) -> int | None:
    """La paleta de Wada que siguen todas las prendas, cubriendo al menos dos
    de sus colores; la de número más bajo si hay varias (determinista)."""
    comunes = set(pps[0])
    for d in pps[1:]:
        comunes &= set(d)
    for n in sorted(comunes):
        if len({d[n] for d in pps}) >= 2:
            return n
    return None


# ---------------------------------------------------------------------------
# Reglas
# ---------------------------------------------------------------------------

def reglas_estilo(estilo: str, ps: list[dict]) -> tuple[float, list[str]] | None:
    """Reglas propias de cada estilo sobre el conjunto. None = no vale."""
    pts, por = 0.0, []
    if any(_fuera_de_ventana(estilo, p) for p in ps):
        return None
    fs = [p["formalidad"] for p in ps if p.get("formalidad")]
    if fs and max(fs) - min(fs) > SALTO_MAX:
        return None
    if estilo == "minimalista" and any(p.get("marcas", set()) & {"cargo", "roto"} for p in ps):
        return None
    fuertes = [p for p in ps if p["estampado"] in ESTAMPADOS_FUERTES]
    if estilo == "casual":
        if len(fuertes) > 1:
            pts -= len(fuertes) - 1
            por.append("más de una prenda estampada resta")
    elif estilo == "streetwear":
        if any(p["estampado"] in ("logo", "estampado", "camuflaje") for p in ps):
            pts += 1
            por.append("una prenda gráfica")
    elif estilo == "athleisure":
        if any(p["tejido"] == "vaquero" or p["tipo"] == "vaquero" for p in ps):
            return None
        tec = sum(p["tejido"] in ("sintetico", "punto") for p in ps)
        if tec:
            pts += tec
            por.append("tejido técnico o de punto")
    elif estilo == "minimalista":
        if any(p["estampado"] != "liso" for p in ps):
            return None
        colores = {familia(p) for p in ps} - {None}
        if len(colores) > 1:
            return None
        if not colores:
            pts += 1          # la razón («todo en neutros») ya la da armonia()
    elif estilo in ("smart_casual", "business_casual"):
        if any(p["estampado"] in ("camuflaje", "estampado")
               or (p["estampado"] == "logo" and not p.get("logo_discreto")) for p in ps):
            return None
        # Ni chándal ni cargo: se ven en la descripción aunque el tipo diga
        # «pantalón» (visto en uso: joggers propuestos para Business Casual).
        if any(p.get("informal") for p in ps):
            return None
        if estilo == "business_casual" and any(p.get("largo") == "corto" for p in ps):
            return None
        if any(p.get("vestir") for p in ps):
            pts += 1
            por.append("pantalón de vestir")
        vaq = [p for p in ps if p["tipo"] == "vaquero"]
        if vaq and not all(p["color"] in ("negro", "gris oscuro", "azul marino") for p in vaq):
            return None
        if vaq:
            por.append("vaquero oscuro")
    elif estilo == "preppy":
        if any(p["estampado"] == "camuflaje" or p.get("informal")
               or "volumen" in p.get("marcas", set()) for p in ps):
            return None
        if any(p["estampado"] in ("rayas", "cuadros") for p in ps):
            pts += 1
            por.append("rayas o cuadros")
        if any(p["estampado"] == "logo" for p in ps):
            pts -= 1
    elif estilo == "grunge" and any(p["tipo"] == "camisa" and p["estampado"] in
                                    ("estampado", "logo", "camuflaje") for p in ps):
        return None
    elif estilo == "rocker":
        negros = sum(p["color"] == "negro" for p in ps)
        if not negros:
            return None
        pts += min(negros, 2)
        por.append("negro")
        if any(p["tejido"] == "cuero" for p in ps):
            pts += 2
            por.append("cuero")
    elif estilo == "grunge":
        if any(p["estampado"] == "cuadros" for p in ps):
            pts += 1
            por.append("cuadros")
        croma = [np.hypot(p["lab"][1], p["lab"][2]) for p in ps if p["lab"] is not None]
        if croma and max(croma) < 25:
            pts += 1
            por.append("colores apagados")
    elif estilo == "oversize":
        holg = sum(p["corte"] == "holgado" for p in ps)
        if not holg:
            return None
        pts += holg
        por.append("corte holgado declarado")
    return pts, por


def armonia(ps: list[dict]) -> tuple[float, str]:
    """Regla de estilista sobre el número de colores (familias) no neutros."""
    fam = {familia(p) for p in ps} - {None}
    if not fam:
        return 1.0, "todo en neutros"
    if len(fam) == 1:
        nombre = next(p["color"] for p in ps if familia(p))
        if any(es_neutro(p) for p in ps):
            return 2.0, f"base neutra y un color ({nombre})"
        return 1.5, "un solo color, en tonos"
    if len(fam) == 2:
        return 0.0, "dos colores"
    return -2.0, "demasiados colores"


def _pide(p: dict, color_pedido: str | None) -> bool:
    return color_pedido is None or p["color"] in COLORES_PEDIDO[color_pedido]


# ---------------------------------------------------------------------------
# Generación
# ---------------------------------------------------------------------------

def generar(prendas: list[dict], estilo: str, color_pedido: str | None = None,
            con_encima: bool | None = None, solo_wada: bool = False,
            n: int = 8, max_repeticion: int = 2, altura: int | None = None,
            ancla: int | None = None, forzar: bool = False, semilla: int = 0) -> dict:
    """Outfits ordenados. Devuelve {"outfits": [...], "faltan": [...], "aviso": str|None}.

    Cada outfit: {"prendas": {posicion: índice en `prendas`}, "puntos",
    "razones": [...], "wada": nº de paleta o None}.

    `ancla`: índice de una prenda que TIENE que estar en todos los outfits
    (el usuario parte de ella). Si no encaja en el estilo, no sale nada salvo
    con `forzar`: entonces se monta igual y las reglas del estilo se aplican
    solo al resto. `semilla`: 0 = los mejores, en orden; otra = otra tanda de
    propuestas, muestreadas en proporción a su puntuación (Gumbel top-k). La
    misma semilla da la misma tanda: sigue siendo reproducible.
    """
    E = ESTILOS[estilo]
    if con_encima is None:
        con_encima = E["capa"] == "recomendado"
    umbral = umbral_wada()
    pps = paletas_por_prenda(prendas, umbral)
    pa = prendas[ancla] if ancla is not None else None
    if pa is not None and pa["posicion"] == "encima":
        con_encima = True

    def afin(p, pos):
        return E[pos].get(p["tipo"], 0)

    def vale(p, pos):
        return afin(p, pos) or (forzar and p is pa)

    A = [p for p in prendas if p["posicion"] == "arriba" and vale(p, "arriba")]
    B = [p for p in prendas if p["posicion"] == "abajo" and vale(p, "abajo")]
    # Encima: lo guardado encima y lo que, por tipo, se lleva encima en este
    # estilo aunque esté guardado arriba (la sudadera de cremallera).
    C = [p for p in prendas if vale(p, "encima")
         and (p["posicion"] == "encima" or _etq.CAPA.get(p["tipo"], 0) >= 2
              or p["tipo"] == "camisa")]
    if pa is not None:
        # La prenda de partida ocupa su posición y no compite en otra.
        if pa["posicion"] == "abajo":
            B = [pa] if pa in B else []
        elif pa["posicion"] == "encima":
            C = [pa] if pa in C else []
        else:
            A = [pa] if pa in A else []
        A = [p for p in A if p is pa or pa["posicion"] != "arriba"]
        C = [p for p in C if p is not pa or pa["posicion"] == "encima"]

    faltan = []
    if not A:
        faltan.append(("arriba", sorted(E["arriba"], key=lambda t: -E["arriba"][t])))
    if not B:
        faltan.append(("abajo", sorted(E["abajo"], key=lambda t: -E["abajo"][t])))
    if con_encima and not C:
        faltan.append(("encima", sorted(E["encima"], key=lambda t: -E["encima"][t])))
    if estilo == "oversize" and not any(p["corte"] == "holgado" for p in prendas):
        return {"outfits": [], "faltan": [], "aviso":
                "Oversize necesita saber qué prendas te quedan holgadas. Márcalo en "
                "Mi armario, en «Más detalles» → Corte → Holgado."}
    if not A or not B:
        return {"outfits": [], "faltan": faltan, "aviso": None}

    def puntuar(ps, afinidad):
        # Forzada, la prenda de partida no cuenta para las reglas del estilo
        # (ya se sabe que no las cumple): se juzga el resto.
        r = reglas_estilo(estilo, [p for p in ps if not (forzar and p is pa)] or ps)
        if r is None:
            return None
        pr, por = r
        a, txt = armonia(ps)
        w = paleta_comun([pps[p["i"]] for p in ps])
        if solo_wada and w is None:
            return None
        puntos = (PESO["afinidad"] * afinidad + PESO["regla"] * pr
                  + PESO["armonia"] * a + (PESO["wada"] if w else 0))
        razones = [txt] + por
        if altura and altura < ALTURA_ALARGAR:
            arr, aba = ps[0], ps[1]
            if (arr["lab"] is not None and aba["lab"] is not None
                    and abs(arr["lab"][0] - aba["lab"][0]) < CONTRASTE_BAJO):
                puntos += 1
                razones.append("poco contraste arriba-abajo: alarga la figura")
        return puntos, razones, w

    base = []
    for a in A:
        for b in B:
            s = puntuar([a, b], afin(a, "arriba") + afin(b, "abajo"))
            if s:
                base.append((s[0], a["id"], b["id"], a, b))
    base.sort(key=lambda t: (-t[0], t[1], t[2]))

    cand = []
    for _, _, _, a, b in base[:400]:
        opciones = [(None, puntuar([a, b], afin(a, "arriba") + afin(b, "abajo")))]
        if con_encima:
            opciones = []
            for c in C:
                if c["id"] in (a["id"], b["id"]):
                    continue
                # La capa de fuera tiene que ir por fuera: una camisa encima
                # solo sobre una camiseta; el resto, de una capa más exterior.
                if c["tipo"] == "camisa":
                    if a["tipo"] != "camiseta":
                        continue
                elif _etq.CAPA.get(c["tipo"], 3) <= _etq.CAPA.get(a["tipo"], 1):
                    continue
                if not capas_ok(a, c, b):
                    continue
                s = puntuar([a, b, c], afin(a, "arriba") + afin(b, "abajo") + afin(c, "encima"))
                if s:
                    opciones.append((c, s))
        for c, s in opciones:
            if not s:
                continue
            ps = [a, b] + ([c] if c else [])
            if color_pedido and not any(_pide(p, color_pedido) for p in ps):
                continue
            cand.append({"prendas": {"arriba": a["i"], "abajo": b["i"],
                                     **({"encima": c["i"]} if c else {})},
                         "puntos": round(float(s[0]), 2), "razones": s[1], "wada": s[2],
                         "_ids": tuple(p["id"] for p in ps)})
    if pa is not None:
        cand = [o for o in cand if pa["i"] in o["prendas"].values()]
    cand.sort(key=lambda o: (-o["puntos"], o["_ids"]))
    if semilla:
        ruido = np.random.default_rng(semilla).gumbel(size=len(cand))
        orden = np.argsort([-(o["puntos"] + r) for o, r in zip(cand, ruido)], kind="stable")
        cand = [cand[k] for k in orden]

    # Variedad: no se repite el mismo arriba + abajo, una paleta de Wada sale
    # como mucho dos veces y, en dos pasadas, primero cada prenda una sola vez
    # (la de partida no cuenta) para que ocho looks no sean los mismos
    # vaqueros con otra camiseta; si no llega a `n`, se rellena permitiendo
    # hasta `max_repeticion` usos.
    usos, pares, elegidos = defaultdict(int), set(), []
    paletas = defaultdict(int)
    vistos = set()
    for tope in dict.fromkeys((1, max_repeticion)):
        for o in cand:
            ids = o["_ids"]
            if (id(o) in vistos or ids[:2] in pares
                    or any(usos[i] >= tope for i in ids if pa is None or i != pa["id"])
                    or (o["wada"] and paletas[o["wada"]] >= 2)):
                continue
            if o["wada"]:
                paletas[o["wada"]] += 1
            elegidos.append(o)
            vistos.add(id(o))
            pares.add(ids[:2])
            for i in ids:
                usos[i] += 1
            if len(elegidos) == n:
                break
        if len(elegidos) == n:
            break
    # El orden que ve el usuario sigue siendo el de la puntuación (o el del
    # sorteo, con semilla), no el de la pasada en que entró cada look.
    pos = {id(o): k for k, o in enumerate(cand)}
    elegidos.sort(key=lambda o: pos[id(o)])
    for o in elegidos:
        o.pop("_ids")
    aviso = None
    if not elegidos and not faltan:
        aviso = ("Con tus prendas no sale ningún conjunto que cumpla todo."
                 + (" Prueba sin color." if color_pedido else "")
                 + (" Prueba sin limitarte al diccionario." if solo_wada else ""))
    return {"outfits": elegidos, "faltan": faltan, "aviso": aviso}


# ---------------------------------------------------------------------------
# ¿Encaja una prenda en un estilo?
# ---------------------------------------------------------------------------

LEGIBLE = {"pantalon": "pantalón", "cardigan": "cárdigan", "algodon": "algodón",
           "sintetico": "sintético", "marron": "marrón", "jogger": "jogger"}
POS_TEXTO = {"arriba": "arriba", "abajo": "abajo", "encima": "encima"}


def _leg(t):
    return LEGIBLE.get(t, t or "prenda")


def _frase_informal(p: dict) -> str:
    """«Camisa de béisbol», «Bermuda cargo», «Jogger»: la prenda y lo que la delata."""
    t = _leg(p["tipo"]).capitalize()
    if p["informal"] is True or p["informal"] == "jogger" or (
            p["informal"] == "de sudadera" and p["tipo"] == "sudadera"):
        return t
    return f"{t} {p['informal']}"


def _choca(estilo: str, p: dict) -> str | None:
    """La regla del estilo que una prenda sola ya incumple, o None."""
    nom = ESTILOS[estilo]["nombre"]
    if estilo == "athleisure" and (p["tejido"] == "vaquero" or p["tipo"] == "vaquero"):
        return "Athleisure es ropa deportiva: el vaquero no entra."
    if estilo == "minimalista" and p["estampado"] != "liso":
        return "Minimalista pide prendas lisas, sin estampado."
    if estilo in ("smart_casual", "business_casual"):
        if p.get("informal"):
            return f"{_frase_informal(p)}: demasiado informal para {nom}."
        if p["estampado"] in ("camuflaje", "estampado") or (
                p["estampado"] == "logo" and not p.get("logo_discreto")):
            return f"Un estampado grande o un logo no es de {nom}."
        if p["tipo"] == "vaquero" and p["color"] not in ("negro", "gris oscuro", "azul marino"):
            return f"En {nom}, el vaquero solo oscuro."
        if estilo == "business_casual" and p.get("largo") == "corto":
            return "Business Casual no lleva nada corto."
    if estilo == "preppy" and p["estampado"] == "camuflaje":
        return "El camuflaje no es Preppy."
    if estilo == "preppy" and "volumen" in p.get("marcas", set()):
        return f"{_leg(p['tipo']).capitalize()} de corte ancho: Preppy es de corte recto."
    if estilo == "preppy" and p.get("informal"):
        return f"{_frase_informal(p)}: Preppy es clásico, no deportivo."
    if estilo == "minimalista" and p.get("marcas", set()) & {"cargo", "roto"}:
        return f"{_leg(p['tipo']).capitalize()} {p.get('formal_por') or ''}".strip() \
            + ": Minimalista pide líneas limpias, sin bolsillos cargo ni rotos."
    fuera = _fuera_de_ventana(estilo, p)
    if fuera:
        return fuera
    if estilo == "oversize" and p["corte"] != "holgado":
        return "Oversize pide prendas holgadas, y esta no está marcada como holgada."
    return None


def _nivel(p: dict, estilo: str) -> int:
    E = ESTILOS[estilo]
    niveles = [E[p["posicion"]].get(p["tipo"], 0)]
    if p["posicion"] == "arriba" and (_etq.CAPA.get(p["tipo"], 0) >= 2 or p["tipo"] == "camisa"):
        niveles.append(E["encima"].get(p["tipo"], 0))
    return 0 if _choca(estilo, p) else max(niveles)


def encaje(p: dict, estilo: str) -> dict:
    """Veredicto de una prenda para un estilo, con sus razones.

    nivel 2 = muy del estilo, 1 = encaja, 0 = no encaja. `alternativas`: los
    estilos en los que sí encaja, de más a menos propio. Son las mismas
    reglas que montan los conjuntos: no hay un criterio aparte.
    """
    E = ESTILOS[estilo]
    nivel = _nivel(p, estilo)
    razones = []
    motivo = _choca(estilo, p)
    if motivo:
        razones.append(motivo)
    elif nivel == 0:
        pide = sorted(E[p["posicion"]], key=lambda t: -E[p["posicion"]][t])[:3]
        razones.append(f"{E['nombre']} no lleva {_leg(p['tipo'])} {POS_TEXTO[p['posicion']]}: "
                       f"pide {', '.join(_leg(t) for t in pide)}.")
    elif nivel == 2:
        razones.append(f"Es una prenda muy de {E['nombre']}.")
    else:
        razones.append(f"Encaja en {E['nombre']}, aunque no es lo más propio del estilo.")
    alternativas = sorted((k for k in ORDEN_ESTILOS if k != estilo and _nivel(p, k)),
                          key=lambda k: -_nivel(p, k))
    return {"nivel": nivel, "razones": razones, "alternativas": alternativas}


# ---------------------------------------------------------------------------
# Petición en lenguaje natural -> restricciones (la IA no elige el outfit)
# ---------------------------------------------------------------------------

_PETICION = {
    "type": "OBJECT",
    "properties": {
        "estilo": {"type": "STRING", "enum": ORDEN_ESTILOS + ["sin_cambio"]},
        "color": {"type": "STRING", "enum": list(COLORES_PEDIDO) + ["ninguno", "sin_cambio"]},
        "encima": {"type": "STRING", "enum": ["si", "no", "sin_cambio"]},
        "entendido": {"type": "BOOLEAN"},
    },
    "required": ["estilo", "color", "encima", "entendido"],
}


def interpretar_peticion(texto: str, modelo: str | None = None) -> dict:
    """«Algo para una cena, en azul» -> {"estilo": "smart_casual", "color": "azul"}.
    Solo los campos que cambian. La IA traduce; las reglas eligen."""
    from paginas import gemini
    modelo = modelo or gemini.elegir_modelo()
    estilos = "; ".join(f'{k}: {v["nombre"]} ({v["idea"]})' for k, v in ESTILOS.items())
    instr = (
        "Eres el traductor de peticiones de una app de estilismo para hombre "
        "que monta outfits con el armario del usuario. Traduce la petición a "
        "restricciones. Estilos: " + estilos + ". Una ocasión se traduce al "
        "estilo que le corresponde (oficina -> business_casual; cena o cita -> "
        "smart_casual; gimnasio o paseo -> athleisure). color: el color que "
        "pide que aparezca, o \"ninguno\" si pide quitar el color. encima: si "
        "pide llevar algo encima (frío, chaqueta, capas) o no. Lo que no pida: "
        f"\"sin_cambio\". entendido: false si no trata de ropa.\n\nPetición: «{texto[:300]}»")
    r = gemini.generar_json(modelo, instr, None, _PETICION)
    out = {"entendido": bool(r.get("entendido"))}
    if r.get("estilo") in ESTILOS:
        out["estilo"] = r["estilo"]
    if r.get("color") in COLORES_PEDIDO:
        out["color"] = r["color"]
    elif r.get("color") == "ninguno":
        out["color"] = None
    if r.get("encima") in ("si", "no"):
        out["encima"] = r["encima"] == "si"
    return out
