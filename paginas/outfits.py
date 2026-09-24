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
        "encima": {"cazadora": 2, "chaqueta": 2, "cardigan": 1, "sudadera": 1},
        "capa": "opcional",
    },
    "streetwear": {
        "nombre": "Streetwear",
        "idea": "Sudaderas, gráficos y pantalón con volumen.",
        "arriba": {"sudadera": 2, "camiseta": 2},
        "abajo": {"vaquero": 2, "jogger": 2, "bermuda": 2, "pantalon": 1},
        "encima": {"cazadora": 2, "sudadera": 2, "chaqueta": 1},
        "capa": "opcional",
    },
    "athleisure": {
        "nombre": "Athleisure",
        "idea": "Ropa deportiva para la calle: punto y tejido técnico.",
        "arriba": {"camiseta": 2, "sudadera": 2},
        "abajo": {"jogger": 2, "bermuda": 1},
        "encima": {"sudadera": 2, "cazadora": 1},
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
        out.append({
            "i": i, "id": int(r.id), "posicion": r.posicion,
            "tipo": e.get("tipo") or txt(r.categoria),
            "color": nom, "lab": lab if np.all(np.isfinite(lab)) else None,
            "estampado": e.get("estampado") or "liso",
            "tejido": tejido, "manga": e.get("manga"),
            "corte": txt(r.corte) or None,
            "informal": _informal(e.get("tipo") or txt(r.categoria), e, txt(r.notas)),
            "vestir": any(w in _clave(str(e.get("descripcion") or "")) + " " + txt(r.notas)
                          for w in ("de vestir", "traje")),
            "largo": e.get("largo"),
        })
    return out


# Palabras que delatan una prenda de chándal o utilitaria aunque su tipo sea
# «pantalon» (la lista cerrada de tipos no tiene «cargo» ni «chándal»). Se
# miran en la descripción de la IA y en las notas del usuario.
_INFORMAL = ("cargo", "chandal", "deportiv", "jogger", "sudader")


def _informal(tipo: str, e: dict, notas: str) -> bool:
    if tipo == "jogger":
        return True
    texto = _clave(str(e.get("descripcion") or "")) + " " + (notas or "")
    return any(w in texto for w in _INFORMAL)


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
        if any(p["estampado"] in ("logo", "camuflaje", "estampado") for p in ps):
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
        if any(p["estampado"] == "camuflaje" for p in ps):
            return None
        if any(p["estampado"] in ("rayas", "cuadros") for p in ps):
            pts += 1
            por.append("rayas o cuadros")
        if any(p["estampado"] == "logo" for p in ps):
            pts -= 1
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
            n: int = 8, max_repeticion: int = 2, altura: int | None = None) -> dict:
    """Outfits ordenados. Devuelve {"outfits": [...], "faltan": [...], "aviso": str|None}.

    Cada outfit: {"prendas": {posicion: índice en `prendas`}, "puntos",
    "razones": [...], "wada": nº de paleta o None}.
    """
    E = ESTILOS[estilo]
    if con_encima is None:
        con_encima = E["capa"] == "recomendado"
    umbral = umbral_wada()
    pps = paletas_por_prenda(prendas, umbral)

    def afin(p, pos):
        return E[pos].get(p["tipo"], 0)

    A = [p for p in prendas if p["posicion"] == "arriba" and afin(p, "arriba")]
    B = [p for p in prendas if p["posicion"] == "abajo" and afin(p, "abajo")]
    # Encima: lo guardado encima y lo que, por tipo, se lleva encima en este
    # estilo aunque esté guardado arriba (la sudadera de cremallera).
    C = [p for p in prendas if afin(p, "encima")
         and (p["posicion"] == "encima" or _etq.CAPA.get(p["tipo"], 0) >= 2
              or p["tipo"] == "camisa")]

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
        r = reglas_estilo(estilo, ps)
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
    cand.sort(key=lambda o: (-o["puntos"], o["_ids"]))

    # Variedad: una prenda sale como mucho `max_repeticion` veces, y no se
    # repite el mismo arriba + abajo.
    usos, pares, elegidos = defaultdict(int), set(), []
    for o in cand:
        ids = o["_ids"]
        if ids[:2] in pares or any(usos[i] >= max_repeticion for i in ids):
            continue
        elegidos.append(o)
        pares.add(ids[:2])
        for i in ids:
            usos[i] += 1
        if len(elegidos) == n:
            break
    for o in elegidos:
        o.pop("_ids")
    aviso = None
    if not elegidos and not faltan:
        aviso = ("Con tus prendas no sale ningún conjunto que cumpla todo."
                 + (" Prueba sin color." if color_pedido else "")
                 + (" Prueba sin limitarte al diccionario." if solo_wada else ""))
    return {"outfits": elegidos, "faltan": faltan, "aviso": aviso}


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
