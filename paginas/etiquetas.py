"""
Etiquetas de prenda puestas por un modelo de visión y lenguaje (Gemini).

Qué papel tiene, y cuál no
--------------------------
El modelo grande DESCRIBE: qué prendas hay en la foto, en qué posición, con
qué manga, color, estampado y tejido. No decide qué prenda del armario sale
primero. Eso lo sigue calculando este código: primero por cuántas etiquetas
coinciden, y dentro de cada nivel por el parecido visual de CLIP.

Así lo pedía el plan desde la entrega 2: «el LLM etiqueta atributos; no decide
el outfit, que debe ser reproducible y evaluable». Con las etiquetas guardadas,
la misma foto contra el mismo armario da siempre el mismo orden.

Por qué hace falta
------------------
Lo que CLIP no resuelve en esta aplicación, medido o visto:
- salto de dominio: una foto de calle y una de producto le parecen de mundos
  distintos (AUC 1,000 separándolas);
- no separa capas: una camisa abierta sobre una camiseta es un único vector;
- la manga o el largo pesan poco frente al color y el fondo.
Un modelo de visión y lenguaje grande describe esas tres cosas con palabras.

Orden de prioridad (fijado antes de medir)
------------------------------------------
Cada prenda del armario recibe una penalización frente a la pieza buscada:

    tipo distinto            8   (misma familia: 4)
    manga o largo distintos  4
    color distinto           2   (misma familia de color: 1)
    estampado distinto       1
    tejido distinto          1

Se ordena por penalización y, a igualdad, por parecido CLIP. Tipo y forma van
antes que el color porque cambian qué prenda es (un pantalón corto no es un
pantalón largo del mismo color); el color va antes que estampado y tejido
porque es lo primero que se mira, que es lo que pedía el usuario.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import time

from paginas import gemini

VERSION = "e1"           # cambia si cambia el prompt o el esquema
CACHE = pathlib.Path(__file__).resolve().parents[1] / "data" / "etiquetas_cache.json"

TIPOS = ["camiseta", "polo", "camisa", "sudadera", "jersey", "cardigan",
         "chaleco", "chaqueta", "cazadora", "blazer", "abrigo",
         "pantalon", "vaquero", "chino", "jogger", "bermuda", "otra"]
MANGAS = ["corta", "larga", "sin_manga", "no_aplica"]
LARGOS = ["corto", "largo", "no_aplica"]
COLORES = ["negro", "gris oscuro", "gris", "gris claro", "blanco", "crudo",
           "beige", "camel", "marron", "caqui", "verde", "verde oscuro",
           "azul marino", "azul", "azul claro", "rojo", "burdeos", "rosa",
           "naranja", "amarillo", "morado", "multicolor"]
ESTAMPADOS = ["liso", "rayas", "cuadros", "estampado", "logo", "camuflaje"]
TEJIDOS = ["vaquero", "punto", "algodon", "cuero", "pana", "sintetico",
           "lana", "otro"]
POSICIONES = ["arriba", "encima", "abajo"]

# Familias: una discrepancia dentro de la familia cuenta la mitad.
FAMILIA_TIPO = {
    **dict.fromkeys(["camiseta", "polo"], "punto_ligero"),
    **dict.fromkeys(["sudadera", "jersey", "cardigan"], "abrigo_ligero"),
    **dict.fromkeys(["chaqueta", "cazadora", "blazer", "abrigo", "chaleco"], "exterior"),
    **dict.fromkeys(["pantalon", "chino", "jogger", "vaquero"], "pantalon_largo"),
}
FAMILIA_COLOR = {
    **dict.fromkeys(["negro", "gris oscuro"], "oscuro"),
    **dict.fromkeys(["gris", "gris claro"], "gris"),
    **dict.fromkeys(["blanco", "crudo", "beige"], "claro"),
    **dict.fromkeys(["camel", "marron", "caqui"], "tierra"),
    **dict.fromkeys(["verde", "verde oscuro"], "verde"),
    **dict.fromkeys(["azul marino", "azul", "azul claro"], "azul"),
    **dict.fromkeys(["rojo", "burdeos", "rosa"], "rojo"),
    **dict.fromkeys(["naranja", "amarillo"], "calido"),
}

_PIEZA = {
    "type": "OBJECT",
    "properties": {
        "posicion": {"type": "STRING", "enum": POSICIONES},
        "tipo": {"type": "STRING", "enum": TIPOS},
        "manga": {"type": "STRING", "enum": MANGAS},
        "largo": {"type": "STRING", "enum": LARGOS},
        "color": {"type": "STRING", "enum": COLORES},
        "estampado": {"type": "STRING", "enum": ESTAMPADOS},
        "tejido": {"type": "STRING", "enum": TEJIDOS},
        "abierta": {"type": "BOOLEAN"},
        "descripcion": {"type": "STRING"},
    },
    "required": ["posicion", "tipo", "manga", "largo", "color", "estampado",
                 "tejido", "abierta", "descripcion"],
}
ESQUEMA = {
    "type": "OBJECT",
    "properties": {"hay_persona": {"type": "BOOLEAN"},
                   "piezas": {"type": "ARRAY", "items": _PIEZA}},
    "required": ["hay_persona", "piezas"],
}

INSTRUCCIONES = f"""Eres un etiquetador de ropa de hombre. Mira la imagen y
devuelve SOLO JSON con este formato:
{{"hay_persona": bool, "piezas": [{{"posicion", "tipo", "manga", "largo",
"color", "estampado", "tejido", "abierta", "descripcion"}}]}}

Reglas:
- hay_persona: true si alguien lleva la ropa puesta; false si es una prenda
  suelta (extendida, colgada o foto de producto).
- Con persona, una pieza por prenda visible de ropa, sin calzado ni
  complementos. posicion: "arriba" para la prenda del torso más interior
  (camiseta, polo, camisa cerrada, sudadera sin abrir); "encima" para la capa
  exterior abierta o que va sobre otra (chaqueta, cazadora, camisa abierta
  sobre camiseta, sudadera de cremallera abierta, chaleco); "abajo" para
  pantalones y bermudas.
- Sin persona, exactamente una pieza: la prenda de la foto. Una chaqueta,
  cazadora, abrigo, blazer, chaleco o sudadera con cremallera completa va en
  "encima"; el resto de prendas de torso en "arriba"; pantalones en "abajo".
- tipo, uno de: {", ".join(TIPOS)}. Vaqueros largos: "vaquero"; pantalón
  corto de cualquier tejido: "bermuda".
- manga (prendas de torso): {", ".join(MANGAS)}; en pantalones "no_aplica".
- largo (pantalones): corto o largo; en prendas de torso "no_aplica".
- color: el color dominante de la prenda, uno de: {", ".join(COLORES)}.
  Un vaquero azul es "azul"; uno negro o gris lavado, "negro" o "gris".
- estampado: {", ".join(ESTAMPADOS)}.
- tejido: {", ".join(TEJIDOS)}.
- abierta: true solo si es una prenda abierta por delante (cremallera o
  botones sin cerrar).
- descripcion: como mucho 10 palabras, en castellano.
No inventes prendas que no se vean."""

# Fotos de un look (la referencia de Buscar). Las mismas reglas y, además,
# las capas. Versión aparte: la caché de las prendas del armario y la de la
# evaluación (e1) no se tocan. Motivo, visto en uso: con una sudadera abierta
# encima, la IA a veces describía solo la sudadera y el pantalón, y la
# camiseta de debajo no se buscaba; y con camiseta + sudadera + abrigo solo
# había sitio para una capa exterior.
VERSION_LOOK = "l1"
INSTRUCCIONES_LOOK = INSTRUCCIONES + """

Capas del torso (solo con persona):
- Lista TODAS las prendas del torso que se vean, de DENTRO a FUERA, en ese
  orden dentro de la lista.
- La más interior va en "arriba". Cada capa que vaya por fuera de ella, en
  "encima": puede haber dos (por ejemplo, sudadera abierta y abrigo).
- Si una prenda está abierta, debajo hay otra: lístala en "arriba" aunque
  solo se vea una franja o el cuello.
- Si en el torso solo hay una prenda cerrada, sigue la regla de posicion de
  arriba (una sudadera cerrada va en "arriba")."""

# Capa típica de cada tipo de torso: 1 base, 2 intermedia, 3 exterior. Sirve
# para no proponer una sudadera como «lo de debajo» de otra prenda.
CAPA = {**dict.fromkeys(["camiseta", "polo", "camisa"], 1),
        **dict.fromkeys(["sudadera", "jersey", "cardigan"], 2),
        **dict.fromkeys(["chaleco", "chaqueta", "cazadora", "blazer", "abrigo"], 3)}


# ---------------------------------------------------------------------------
# Análisis con caché
# ---------------------------------------------------------------------------

def _leer_cache() -> dict:
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _guardar_cache(c: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE.with_suffix(".tmp")
    tmp.write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(CACHE)


def normalizar(r: dict) -> dict:
    """Valida la respuesta. Lo que no esté en las listas se descarta, no se
    adivina: una etiqueta inventada es peor que ninguna."""
    piezas = []
    for p in (r.get("piezas") or []):
        q = {
            "posicion": p.get("posicion") if p.get("posicion") in POSICIONES else None,
            "tipo": p.get("tipo") if p.get("tipo") in TIPOS else None,
            "manga": p.get("manga") if p.get("manga") in MANGAS else None,
            "largo": p.get("largo") if p.get("largo") in LARGOS else None,
            "color": p.get("color") if p.get("color") in COLORES else None,
            "estampado": p.get("estampado") if p.get("estampado") in ESTAMPADOS else None,
            "tejido": p.get("tejido") if p.get("tejido") in TEJIDOS else None,
            "abierta": bool(p.get("abierta")),
            "descripcion": str(p.get("descripcion") or "")[:120],
        }
        if q["posicion"] and q["tipo"]:
            piezas.append(q)
    return {"hay_persona": bool(r.get("hay_persona")), "piezas": piezas}


def analizar(imagen: bytes, modelo: str | None = None, pausa: float = 0.0,
             instrucciones: str = INSTRUCCIONES, version: str = VERSION) -> dict:
    """Etiquetas de una foto. La misma foto no se manda dos veces.

    Clave de la caché: huella de la imagen + versión del prompt + modelo. Si
    cambia cualquiera de las tres, se vuelve a preguntar.
    """
    modelo = modelo or gemini.elegir_modelo()
    k = _clave(imagen, modelo, version)
    c = _leer_cache()
    if k in c:
        return c[k]
    if pausa:
        time.sleep(pausa)     # para no pasar del límite de peticiones gratuito
    r = normalizar(gemini.generar_json(modelo, instrucciones, imagen, ESQUEMA))
    r["modelo"], r["version"] = modelo, version
    c = _leer_cache()
    c[k] = r
    _guardar_cache(c)
    return r


_LOTE = {
    "type": "OBJECT",
    "properties": {"resultados": {"type": "ARRAY", "items": {
        "type": "OBJECT",
        "properties": {"imagen": {"type": "INTEGER"}, **ESQUEMA["properties"]},
        "required": ["imagen", "hay_persona", "piezas"]}}},
    "required": ["resultados"],
}


def _clave(imagen: bytes, modelo: str, version: str = VERSION) -> str:
    return f"{hashlib.sha1(imagen).hexdigest()}|{version}|{modelo}"



def efectivas(e: dict | None, categoria: str | None, posicion: str | None = None,
              tejido: str | None = None, color: str | None = None) -> dict | None:
    """Las etiquetas con las que se trabaja: las de la IA, corregidas por lo
    que ha dicho el usuario. Lo declarado manda (visto en uso: la IA llamaba
    «pantalon» a joggers que el autor tenía como jogger, y «camiseta» a una
    sudadera). Solo se aplica si el valor está en las listas cerradas; texto
    libre que no encaja no pisa nada. Sin etiquetas de la IA, la categoría
    sola ya da el tipo."""
    from paginas.armario import clave_categoria
    cat = clave_categoria(categoria) if isinstance(categoria, str) else ""
    tej = clave_categoria(tejido) if isinstance(tejido, str) else ""
    col = clave_categoria(color) if isinstance(color, str) else ""
    if not e and cat not in TIPOS:
        return e
    out = dict(e) if e else {"posicion": posicion, "tipo": None, "manga": None,
                             "largo": None, "color": None, "estampado": None,
                             "tejido": None, "abierta": False, "descripcion": ""}
    if cat in TIPOS:
        out["tipo"] = cat
        if cat == "bermuda":
            out["largo"] = "corto"
        if cat == "vaquero" and not tej:
            out["tejido"] = "vaquero"
    if tej in TEJIDOS:
        out["tejido"] = tej
    if col in COLORES:
        out["color"] = col
    return out

def analizar_look(imagen: bytes, modelo: str | None = None) -> dict:
    """La referencia de Buscar, con capas (INSTRUCCIONES_LOOK) y completada
    con completar_capas."""
    return completar_capas(analizar(imagen, modelo, instrucciones=INSTRUCCIONES_LOOK,
                                    version=VERSION_LOOK))


def completar_capas(etq: dict | None) -> dict | None:
    """Si hay una capa abierta encima y ninguna pieza «arriba», añade la de
    debajo, sin describir (inferida=True): una prenda abierta lleva algo
    debajo aunque la IA no lo haya listado. No toca la caché."""
    if not etq or not etq.get("hay_persona"):
        return etq
    piezas = etq.get("piezas", [])
    if (any(q["posicion"] == "encima" and q.get("abierta") for q in piezas)
            and not any(q["posicion"] == "arriba" for q in piezas)):
        base = {"posicion": "arriba", "tipo": None, "manga": None, "largo": None,
                "color": None, "estampado": None, "tejido": None, "abierta": False,
                "descripcion": "", "inferida": True}
        etq = dict(etq, piezas=[base] + piezas)
    return etq


def capas_encima(etq: dict | None) -> list[dict]:
    """Las piezas «encima», de dentro a fuera (el orden en que las lista la IA)."""
    return [q for q in (etq or {}).get("piezas", []) if q["posicion"] == "encima"]


def en_cache(imagen: bytes, modelo: str) -> dict | None:
    return _leer_cache().get(_clave(imagen, modelo))


def pedir_lote(lote: list[bytes], modelo: str) -> list[dict | None]:
    """UNA petición con varias fotos, SIN caché. Una etiqueta (o None) por
    foto, en el mismo orden. Lo usa analizar_lote y la prueba de
    consistencia, que necesita volver a preguntar lo ya preguntado."""
    instr = (INSTRUCCIONES + f"\n\nHay {len(lote)} imágenes, numeradas. "
             "Devuelve {\"resultados\": [...]} con un elemento por imagen, "
             "en orden, cada uno con su número en \"imagen\" y el formato "
             "de arriba. Cada imagen es independiente de las demás.")
    r = gemini.generar_json(modelo, instr, lote, _LOTE, lado=768)
    salida: list[dict | None] = [None] * len(lote)
    for res in r.get("resultados", []):
        k = res.get("imagen")
        if isinstance(k, int) and 1 <= k <= len(lote):
            etq = normalizar(res)
            etq["modelo"], etq["version"] = modelo, VERSION
            salida[k - 1] = etq
    return salida


def analizar_lote(imagenes: list[bytes], modelo: str, tam: int = 10,
                  aviso=print) -> int:
    """Etiqueta muchas fotos con pocas peticiones: `tam` fotos por petición.

    La cuota gratuita cuenta PETICIONES. Una a una, 166 fotos son 166
    peticiones; de diez en diez, 17. Las que ya están en caché no se mandan.
    Cada resultado se guarda con la huella de SU foto, así que después se
    reutiliza igual que si se hubiera pedido sola.

    Se envían a 768 px: para decir tipo, manga y color sobra, y cada imagen
    cuesta menos tokens. Devuelve cuántas fotos quedaron etiquetadas nuevas.
    """
    pendientes = [im for im in dict.fromkeys(imagenes) if en_cache(im, modelo) is None]
    hechas = 0
    for i in range(0, len(pendientes), tam):
        lote = pendientes[i:i + tam]
        try:
            res = pedir_lote(lote, modelo)
        except gemini.CuotaAgotada:
            aviso(f"  cuota diaria de {modelo} agotada: quedan {len(pendientes) - i} "
                  "fotos sin etiquetar (se reanuda donde se quedó)")
            break
        except gemini.ErrorGemini as e:
            aviso(f"  lote {i // tam + 1}: {gemini.resumen_error(e)}; se sigue")
            continue
        c = _leer_cache()
        for img, etq in zip(lote, res):
            if etq is not None:
                c[_clave(img, modelo)] = etq
                hechas += 1
        _guardar_cache(c)
        aviso(f"  lote {i // tam + 1}/{-(-len(pendientes) // tam)}: "
              f"{hechas} etiquetadas")
    return hechas


def desde_cache(imagen: bytes) -> dict | None:
    """Etiquetas ya calculadas para esta imagen, sin llamar a la API.

    Sirve para rellenar las prendas del armario con lo que ya se etiquetó en
    la evaluación (misma foto, mismos bytes) sin gastar ni una petición.
    """
    pref = f"{hashlib.sha1(imagen).hexdigest()}|{VERSION}|"
    hits = [v for k, v in _leer_cache().items() if k.startswith(pref)]
    return hits[-1] if hits else None


def pieza(etq: dict | None, posicion: str) -> dict | None:
    """La pieza de una posición. Si no hay ninguna en esa posición, None."""
    if not etq:
        return None
    for p in etq.get("piezas", []):
        if p["posicion"] == posicion:
            return p
    return None


# ---------------------------------------------------------------------------
# Penalización
# ---------------------------------------------------------------------------

def penalizacion(ref: dict | None, cand: dict | None) -> float:
    """Cuánto se aleja `cand` de `ref` en etiquetas. 0 = todo coincide.

    Sin etiquetas en uno de los dos lados, 0: no se castiga lo que no se sabe,
    y el orden cae entero en el parecido CLIP.
    """
    if not ref or not cand:
        return 0.0
    pen = 0.0
    if ref.get("tipo") and cand.get("tipo") and ref["tipo"] != cand["tipo"]:
        misma = (FAMILIA_TIPO.get(ref["tipo"]) is not None
                 and FAMILIA_TIPO.get(ref["tipo"]) == FAMILIA_TIPO.get(cand["tipo"]))
        pen += 4 if misma else 8
    for campo in ("manga", "largo"):
        a, b = ref.get(campo), cand.get(campo)
        if a and b and a != "no_aplica" and b != "no_aplica" and a != b:
            pen += 4
            break
    a, b = ref.get("color"), cand.get("color")
    if a and b and a != b:
        misma = FAMILIA_COLOR.get(a) is not None and FAMILIA_COLOR.get(a) == FAMILIA_COLOR.get(b)
        pen += 1 if misma else 2
    for campo in ("estampado", "tejido"):
        a, b = ref.get(campo), cand.get(campo)
        if a and b and a != b:
            pen += 1
    return pen


def compatibles(ref: dict | None, cand: dict | None) -> bool:
    """Mismo tipo o misma familia de tipo (camiseta/polo, sudadera/jersey…)."""
    if not ref or not cand or not ref.get("tipo") or not cand.get("tipo"):
        return False
    if ref["tipo"] == cand["tipo"]:
        return True
    f = FAMILIA_TIPO.get(ref["tipo"])
    return f is not None and f == FAMILIA_TIPO.get(cand["tipo"])


def penalizacion_estructura(ref: dict | None, cand: dict | None) -> int:
    """Qué prenda es, no cómo se ve: tipo, manga y largo. 0 = coincide todo.

    tipo distinto 2 (misma familia 1); manga o largo distintos 2.
    Solo los campos que se midieron estables y fiables: tipo 105/118 contra
    las anotaciones del autor, manga 25/27; al repetir, manga y largo 24/24 y
    tipo 22/24. El color, que es lo que hundía el orden por etiquetas
    completo con otra luz, NO entra. Es la misma idea que la posición («una
    bermuda no compite con una camisa»), un nivel más fino: un pantalón corto
    no compite con uno largo, ni una sudadera con una camiseta.
    Sin etiqueta en uno de los lados, 0: no se castiga lo que no se sabe.
    """
    if not ref or not cand:
        return 0
    pen = 0
    if ref.get("tipo") and cand.get("tipo") and ref["tipo"] != cand["tipo"]:
        pen += 1 if compatibles(ref, cand) else 2
    for campo in ("manga", "largo"):
        a, b = ref.get(campo), cand.get(campo)
        if a and b and a != "no_aplica" and b != "no_aplica" and a != b:
            pen += 2
            break
    return pen



def niveles_prioridad(ref: dict | None, cand: dict | None) -> tuple[int, int]:
    """(dura, blanda) para el orden «prioridades» (busqueda.ORDEN_PRIORIDADES).

    dura: lo que cambia QUÉ prenda es y no se arregla con otro color: familia
    de tipo distinta (camiseta frente a sudadera) +1, manga o largo distintos
    +1. Va antes que el color: un pantalón largo negro no sustituye a una
    bermuda negra.
    blanda: mismo grupo pero otro tipo (vaquero frente a pantalón, camiseta
    frente a polo). Es casi siempre una diferencia de tela o de corte, y en el
    orden que pidió el autor (color, luego tela, luego corte) va DESPUÉS del
    color: con un pantalón gris oscuro en la foto, un vaquero negro va antes
    que un pantalón de camuflaje.
    Sin etiqueta en uno de los lados, (0, 0).
    """
    if not ref or not cand:
        return 0, 0
    dura = blanda = 0
    if ref.get("tipo") and cand.get("tipo") and ref["tipo"] != cand["tipo"]:
        if compatibles(ref, cand):
            blanda = 1
        else:
            dura += 1
    for campo in ("manga", "largo"):
        a, b = ref.get(campo), cand.get(campo)
        if a and b and a != "no_aplica" and b != "no_aplica" and a != b:
            dura += 1
            break
    return dura, blanda


def franja_color(ref: dict | None, cand: dict | None) -> int:
    """Franja de color según las etiquetas de la IA: 0 mismo color, 1 misma
    familia (FAMILIA_COLOR), 2 otro o desconocido. Es la alternativa a la
    franja por píxeles (color.delta_cmc) para «prioridades_ia»."""
    a = (ref or {}).get("color")
    b = (cand or {}).get("color")
    if not a or not b:
        return 2
    if a == b:
        return 0
    f = FAMILIA_COLOR.get(a)
    return 1 if f is not None and f == FAMILIA_COLOR.get(b) else 2

# ---------------------------------------------------------------------------
# Ajustes en lenguaje natural («más oscuro», «de manga larga»)
# ---------------------------------------------------------------------------
# El modelo traduce la petición a CAMBIOS sobre la descripción de lo buscado.
# No elige prendas: después se vuelve a ordenar con la misma penalización.
# Es el papel que el plan le daba: «traducir intención a restricciones».

_CAMBIOS = {
    "type": "OBJECT",
    "properties": {
        "posicion": {"type": "STRING", "enum": POSICIONES + ["todas"]},
        "tipo": {"type": "STRING", "enum": TIPOS + ["sin_cambio"]},
        "manga": {"type": "STRING", "enum": MANGAS + ["sin_cambio"]},
        "largo": {"type": "STRING", "enum": LARGOS + ["sin_cambio"]},
        "color": {"type": "STRING", "enum": COLORES + ["sin_cambio"]},
        "estampado": {"type": "STRING", "enum": ESTAMPADOS + ["sin_cambio"]},
        "tejido": {"type": "STRING", "enum": TEJIDOS + ["sin_cambio"]},
        "entendido": {"type": "BOOLEAN"},
    },
    "required": ["posicion", "tipo", "manga", "largo", "color", "estampado",
                 "tejido", "entendido"],
}


def interpretar_ajuste(texto: str, piezas: list[dict], modelo: str | None = None) -> dict:
    """Petición del usuario -> {"posicion": ..., campo: valor nuevo, ...}.

    Devuelve solo los campos que cambian. Si la petición no se refiere a la
    ropa, `entendido` es False y no se cambia nada.
    """
    modelo = modelo or gemini.elegir_modelo()
    actual = "; ".join(f'{p["posicion"]}: {p["tipo"]} {p["color"]} manga '
                       f'{p["manga"]} largo {p["largo"]} {p["estampado"]} '
                       f'{p["tejido"]}' for p in piezas) or "sin descripción"
    instr = (
        "Eres el traductor de peticiones de una app que busca ropa en el "
        "armario del usuario. Lo que se busca ahora:\n" + actual + "\n\n"
        f"Petición del usuario: «{texto[:300]}»\n\n"
        "Devuelve SOLO JSON con los cambios que pide sobre lo buscado. "
        "posicion: la prenda a la que se refiere, o \"todas\". Cada campo "
        "que no cambie: \"sin_cambio\". «Más oscuro» sobre un color claro es "
        "el tono oscuro de esa familia (azul claro -> azul marino; gris -> gris "
        "oscuro); sobre uno oscuro, negro. Un pantalón corto, unos shorts o "
        "unas bermudas son tipo \"bermuda\" con largo \"corto\"; si pide "
        "pantalón largo sin decir de qué, cambia solo el largo. "
        "entendido: false si la petición no "
        f"trata de la ropa. Valores válidos: tipo {TIPOS}; manga {MANGAS}; "
        f"largo {LARGOS}; color {COLORES}; estampado {ESTAMPADOS}; tejido "
        f"{TEJIDOS}.")
    r = gemini.generar_json(modelo, instr, None, _CAMBIOS)
    listas = {"tipo": TIPOS, "manga": MANGAS, "largo": LARGOS, "color": COLORES,
              "estampado": ESTAMPADOS, "tejido": TEJIDOS}
    out = {"posicion": r.get("posicion") if r.get("posicion") in POSICIONES + ["todas"]
           else "todas", "entendido": bool(r.get("entendido"))}
    for campo, lista in listas.items():
        v = r.get(campo)
        if v in lista:
            out[campo] = v
    # Coherencia tipo/largo. El modelo tiende a leer «pantalón corto» como
    # tipo «pantalon» + largo «corto», y eso castigaba justo a las bermudas
    # (tipo distinto) por delante de los pantalones largos. Visto en uso.
    if out.get("largo") == "corto" and out.get("tipo") in (None, "pantalon", "vaquero", "chino", "jogger"):
        out["tipo"] = "bermuda"
    if out.get("tipo") == "bermuda":
        out["largo"] = "corto"
    if out.get("largo") == "largo" and out.get("tipo") == "bermuda":
        out.pop("tipo")
    return out


def aplicar_ajuste(pz: dict | None, posicion: str, ajuste: dict) -> dict | None:
    """La pieza buscada con los cambios del ajuste, si le afectan."""
    if not ajuste.get("entendido") or ajuste["posicion"] not in ("todas", posicion):
        return pz
    base = dict(pz) if pz else {"posicion": posicion, "tipo": None, "manga": None,
                                "largo": None, "color": None, "estampado": None,
                                "tejido": None}
    for campo in ("tipo", "manga", "largo", "color", "estampado", "tejido"):
        if campo in ajuste:
            base[campo] = ajuste[campo]
    return base


# ---------------------------------------------------------------------------
# Rasgos de estilo (versión r1): lo que el tipo cerrado no dice
# ---------------------------------------------------------------------------
# Visto en uso: una camisa de béisbol es «camisa» por tipo y las reglas la
# trataban como una de vestir. La descripción libre lo decía a veces; estos
# rasgos se lo preguntan a la IA SIEMPRE, con respuesta cerrada (sí/no), sobre
# la foto. Es una petición aparte: la versión e1 (tipo, color…) está
# congelada porque es la de la evaluación, y no se toca.
# La IA solo DESCRIBE la prenda; qué estilo le va lo deciden las reglas
# (paginas/outfits.py). "formalidad_ia" se guarda para MEDIR la regla contra
# ella, no se usa para decidir.
VERSION_RASGOS = "r1"
RASGOS = {
    "deportiva": "ropa de deporte o de chándal: felpa de chándal, tejido técnico, franjas laterales",
    "cargo": "bolsillos cargo (de parche, en los laterales de la pierna)",
    "rota": "rotos o desgaste fuerte a propósito",
    "capucha": "tiene capucha",
    "grafico_grande": "gráfico, dibujo, letras o logo GRANDE y visible",
    "logo_discreto": "solo un logo o texto pequeño o bordado",
    "fantasia": "camisa o polo de fantasía: de béisbol, de bolos, hawaiana o de estampado tropical",
    "rustica": "de trabajo o de campo: franela, lona, sobrecamisa, pana gruesa",
    "de_vestir": "de sastre o de vestir: pantalón de pinzas o con raya, camisa de vestir, tejido fino",
    "volumen": "corte muy ancho: baggy, wide leg, oversize",
    "cuello_alto": "cuello vuelto, alto o perkins",
    "manga_corta": "manga corta",
    "sobrecamisa": "camisa gruesa pensada para llevar por fuera, como una chaqueta",
}
_ITEM_RASGOS = {
    "type": "OBJECT",
    "properties": {"imagen": {"type": "INTEGER"},
                   **{k: {"type": "BOOLEAN"} for k in RASGOS},
                   "formalidad": {"type": "INTEGER"}},
    "required": ["imagen", *RASGOS, "formalidad"],
}
_LOTE_RASGOS = {"type": "OBJECT",
                "properties": {"resultados": {"type": "ARRAY", "items": _ITEM_RASGOS}},
                "required": ["resultados"]}
INSTRUCCIONES_RASGOS = (
    "Eres un etiquetador de ropa de hombre. En cada imagen hay UNA prenda. "
    "Para cada rasgo responde true solo si se ve claramente en la foto:\n"
    + "\n".join(f"- {k}: {v}" for k, v in RASGOS.items())
    + "\n- formalidad: de 1 a 5 (1 deporte, 2 informal, 3 casual, 4 arreglado, "
      "5 formal), según las guías de vestimenta habituales.\n"
      "Devuelve {\"resultados\": [...]} con un elemento por imagen, en orden, "
      "cada uno con su número en \"imagen\". Cada imagen es independiente.")


def normalizar_rasgos(r: dict) -> dict:
    """Solo booleanos de la lista y una formalidad 1-5; lo demás se descarta."""
    f = r.get("formalidad")
    return {**{k: bool(r.get(k)) for k in RASGOS},
            "formalidad_ia": f if isinstance(f, int) and 1 <= f <= 5 else None,
            "version": VERSION_RASGOS}


def pedir_rasgos_lote(lote: list[bytes], modelo: str) -> list[dict | None]:
    """UNA petición con varias fotos, SIN caché (la prueba de consistencia
    necesita volver a preguntar lo ya preguntado)."""
    r = gemini.generar_json(modelo, INSTRUCCIONES_RASGOS, lote, _LOTE_RASGOS, lado=768)
    salida: list[dict | None] = [None] * len(lote)
    for res in r.get("resultados", []):
        k = res.get("imagen")
        if isinstance(k, int) and 1 <= k <= len(lote):
            salida[k - 1] = {**normalizar_rasgos(res), "modelo": modelo}
    return salida


def rasgos_en_cache(imagen: bytes) -> dict | None:
    """Rasgos ya pedidos para esta foto (cualquier modelo), sin llamar a la API."""
    pref = f"{hashlib.sha1(imagen).hexdigest()}|{VERSION_RASGOS}|"
    hits = [v for k, v in _leer_cache().items() if k.startswith(pref)]
    return hits[-1] if hits else None


def rasgos_lote(imagenes: list[bytes], modelo: str | None = None, tam: int = 10,
                aviso=print) -> int:
    """Pide los rasgos de las fotos que no los tienen, `tam` por petición, y los
    guarda en la caché con la huella de cada foto. Devuelve cuántas nuevas."""
    modelo = modelo or gemini.elegir_modelo()
    pend = [im for im in dict.fromkeys(imagenes) if rasgos_en_cache(im) is None]
    hechas = 0
    for i in range(0, len(pend), tam):
        lote = pend[i:i + tam]
        try:
            res = pedir_rasgos_lote(lote, modelo)
        except gemini.CuotaAgotada:
            aviso(f"  cuota diaria de {modelo} agotada: faltan {len(pend) - i}")
            break
        except gemini.ErrorGemini as e:
            aviso(f"  lote {i // tam + 1}: {gemini.resumen_error(e)}; se sigue")
            continue
        c = _leer_cache()
        for img, r in zip(lote, res):
            if r is not None:
                c[_clave(img, modelo, VERSION_RASGOS)] = r
                hechas += 1
        _guardar_cache(c)
        aviso(f"  lote {i // tam + 1}/{-(-len(pend) // tam)}: {hechas} con rasgos")
    return hechas


def analizar_rasgos(imagen: bytes, modelo: str | None = None) -> dict | None:
    """Rasgos de UNA foto (al subir una prenda), con caché."""
    hit = rasgos_en_cache(imagen)
    if hit:
        return hit
    rasgos_lote([imagen], modelo, aviso=lambda *_: None)
    return rasgos_en_cache(imagen)


def olvidar(imagenes: list[bytes]) -> int:
    """Quita de la caché todo lo que se pidió sobre estas fotos (etiquetas,
    rasgos, lo que sea): al eliminar una cuenta, lo que la IA dijo de sus
    fotos tampoco se queda. Devuelve cuántas entradas se han quitado."""
    huellas = {hashlib.sha1(im).hexdigest() for im in imagenes}
    if not huellas:
        return 0
    c = _leer_cache()
    fuera = [k for k in c if k.split("|", 1)[0] in huellas]
    for k in fuera:
        del c[k]
    if fuera:
        _guardar_cache(c)
    return len(fuera)
