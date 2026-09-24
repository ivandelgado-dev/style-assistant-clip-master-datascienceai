"""
Búsqueda por posiciones: «recrea este look con lo que tienes».

El problema que resuelve
------------------------
La versión anterior convertía la foto de referencia en UN vector y ordenaba
todo el armario contra él. Una foto de calle es una persona entera, así que ese
vector mezcla la sudadera con el pantalón, y el resultado salía revuelto:
camisas, bermudas y cazadoras en la misma lista.

Lo que pide el producto es otra cosa: la prenda más parecida DE CADA POSICIÓN.
La mejor de arriba, la mejor de abajo, y alternativas para cada una.

Cómo se hace
------------
1. **Se separa la referencia.** Si es una persona («un look»), se recortan dos
   bandas horizontales: la de arriba y la de abajo, con el corte en una línea
   de cintura que el usuario puede mover. Si es una prenda suelta, se usa
   entera.
2. **Cada recorte se compara solo con su posición.** La banda de arriba contra
   camisetas, camisas, sudaderas…; la de abajo contra pantalones y bermudas.
3. **Se ordena por similitud coseno** en la dimensión elegida, exactamente
   como antes. No hay ningún modelo nuevo: son dos recortes y dos pasadas más
   por el mismo CLIP congelado.

Lo que esto NO es
-----------------
No compone conjuntos. No dice que esas prendas combinen bien: dice que cada
una es la más parecida a la pieza correspondiente de la referencia. La
compatibilidad entre prendas sigue sin implementar, y la pantalla no la
aparenta.

Lo que no está medido
---------------------
Que separar la foto mejore los resultados es una mejora ESPERABLE, no medida.
La separación es una heurística: supone una foto de cuerpo entero, de pie y
centrada, que es el caso típico de una foto de calle. Con poses raras o planos
cortos, las bandas pueden caer mal; por eso el usuario ve los recortes y puede
mover la línea de cintura.

Mapa de posiciones
------------------
Es el MISMO que usa el análisis de salto de dominio (`src/domain_gap.py`,
GRUPO_ARMARIO + SLOT_DE_GRUPO), para que la aplicación y la medición hablen de
lo mismo. Se añaden dos categorías que aquel análisis no mapeaba y que el
armario sí tiene: `polo` (arriba) y `chaleco` (encima). El test
`tests/test_posiciones.py` comprueba que ambos mapas coinciden en todo lo
demás.
"""

from __future__ import annotations

import base64
import html as _html
import io

import numpy as np
import streamlit as st
from PIL import Image

from paginas.nucleo import cargar_clip, dato_uri, proyectar

# ---------------------------------------------------------------------------
# Posiciones
# ---------------------------------------------------------------------------

ETIQUETA = {"arriba": "Arriba", "abajo": "Abajo", "encima": "Encima"}

# Traducción de SLOT_DE_GRUPO (top/bottom/outer) a los nombres de la interfaz.
_SLOT_A_POSICION = {"top": "arriba", "bottom": "abajo", "outer": "encima"}

# Categoría -> posición. Idéntico al análisis salvo `polo` y `chaleco`.
POSICION = {
    "camiseta": "arriba", "camisa": "arriba", "sudadera": "arriba",
    "jersey": "arriba", "cardigan": "arriba",
    "chaqueta": "encima", "cazadora": "encima", "blazer": "encima",
    "abrigo": "encima",
    "pantalon": "abajo", "vaquero": "abajo", "chino": "abajo",
    "jogger": "abajo", "bermuda": "abajo",
    # Añadidas: el armario las tiene y el análisis no las mapeaba.
    "polo": "arriba",
    "chaleco": "encima",
}
AÑADIDAS = {"polo", "chaleco"}

# Orden en que se enseñan las posiciones: lo de arriba, lo que va encima de
# ello, y lo de abajo. Es el orden en que se lee un conjunto.
ORDEN = ("arriba", "encima", "abajo")

# Singular y plural de las categorías predefinidas, con tildes. La clave (sin
# tildes) es lo que se guarda en la base; esto es solo lo que se lee.
NOMBRES = {
    "camiseta": ("Camiseta", "Camisetas"), "polo": ("Polo", "Polos"),
    "camisa": ("Camisa", "Camisas"), "sudadera": ("Sudadera", "Sudaderas"),
    "jersey": ("Jersey", "Jerséis"), "cardigan": ("Cárdigan", "Cárdigans"),
    "chaleco": ("Chaleco", "Chalecos"), "chaqueta": ("Chaqueta", "Chaquetas"),
    "cazadora": ("Cazadora", "Cazadoras"), "blazer": ("Blazer", "Blazers"),
    "abrigo": ("Abrigo", "Abrigos"), "pantalon": ("Pantalón", "Pantalones"),
    "vaquero": ("Vaquero", "Vaqueros"), "chino": ("Chino", "Chinos"),
    "jogger": ("Jogger", "Joggers"), "bermuda": ("Bermuda", "Bermudas"),
}


def nombre(cat: str, plural: bool = False) -> str:
    cat = str(cat or "").strip()
    if cat in NOMBRES:
        return NOMBRES[cat][1 if plural else 0]
    return cat.capitalize() or "Prenda"


def posicion_de(categoria: str) -> str | None:
    return POSICION.get(str(categoria or "").strip().lower())


# ---------------------------------------------------------------------------
# Separación de la referencia
# ---------------------------------------------------------------------------

def cajas_look(cintura: float) -> dict[str, tuple[float, float, float, float]]:
    """Bandas (x0, y0, x1, y1) en fracciones de la imagen.

    La banda de arriba empieza en el 12 % para dejar fuera la cabeza —una cara
    no ayuda a encontrar una camisa— y termina un poco por DEBAJO de la
    cintura. La de abajo empieza un poco por ENCIMA. Ese solape del 4 % es a
    propósito: una prenda metida por dentro o un pantalón de tiro alto
    cruzan la línea, y es mejor que las dos bandas los vean que ninguna.
    Los márgenes laterales quitan fondo, que en una foto de calle es casi
    siempre calle.
    """
    return {
        "arriba": (0.10, 0.12, 0.90, min(cintura + 0.04, 0.95)),
        "abajo":  (0.14, max(cintura - 0.04, 0.05), 0.86, 0.93),
    }


def caja_interior(cintura: float) -> tuple[float, float, float, float]:
    """Franja central del torso: lo que asoma entre una prenda abierta.

    Con una chaqueta o sudadera abierta encima, la banda de arriba entera es
    sobre todo la capa exterior, y CLIP ve un solo vector con las dos capas
    mezcladas. Para buscar lo de DEBAJO se mira solo el centro.
    """
    return (0.40, 0.18, 0.60, max(cintura - 0.02, 0.3))


def candidatos(pos_arm: np.ndarray, etqs: list, posicion: str, pz,
               bajo_capa: bool = False) -> np.ndarray:
    """Qué prendas compiten por una posición.

    Las de esa posición y, si la IA ha descrito la pieza, también las del
    mismo tipo aunque estén guardadas en otra posición. Motivo, visto en uso:
    una sudadera de cremallera se guarda «arriba», pero puesta abierta sobre
    una camiseta va «encima», y la columna de encima no la encontraba.

    Con `bajo_capa` (lo de «arriba» cuando hay algo encima), fuera las
    prendas de una capa más exterior que la buscada: debajo de una sudadera
    abierta no se propone otra sudadera. Si no se sabe qué es lo de debajo
    (pieza inferida), solo capa base: camiseta, polo, camisa. Las prendas sin
    etiqueta se quedan: no se descarta lo que no se sabe.
    """
    from paginas import etiquetas
    m = pos_arm == posicion
    if pz and pz.get("tipo"):
        m = m | np.array([etiquetas.compatibles(pz, e) for e in etqs], dtype=bool)
    if bajo_capa and posicion == "arriba":
        limite = etiquetas.CAPA.get((pz or {}).get("tipo"), 1)
        m = m & np.array([etiquetas.CAPA.get((e or {}).get("tipo"), 0) <= limite
                          for e in etqs], dtype=bool)
    return m


def recortar(im: Image.Image, caja) -> Image.Image:
    if caja is None:
        return im
    w, h = im.size
    x0, y0, x1, y1 = caja
    return im.crop((int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)))


@st.cache_data(show_spinner=False, max_entries=96)
def vector(datos: bytes, caja: tuple | None) -> np.ndarray:
    """Vector CLIP de la imagen (o de un recorte), en caché por contenido.

    La caché va por los BYTES de la imagen y la caja, no por el nombre del
    fichero: cambiar de dimensión o marcar una casilla repinta la pantalla,
    y sin esto cada repintado volvería a pasar las tres imágenes por CLIP.
    """
    import torch
    proc, modelo, extraer = cargar_clip()
    im = recortar(Image.open(io.BytesIO(datos)).convert("RGB"), caja)
    with torch.no_grad():
        px = proc(images=im, return_tensors="pt")["pixel_values"]
        return extraer(modelo.get_image_features(pixel_values=px)).numpy()


def uri_pil(im: Image.Image, ancho: int = 360) -> str:
    im = im.copy()
    if im.width > ancho:
        im = im.resize((ancho, int(im.height * ancho / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=84, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


# ---------------------------------------------------------------------------
# Ordenación por posición
# ---------------------------------------------------------------------------

def ordenar(V_arm: np.ndarray, pos_arm: np.ndarray, v_ref: np.ndarray,
            posicion: str, ruta, mascara=None) -> tuple[np.ndarray, np.ndarray]:
    """Índices (sobre el armario) de una posición, de más a menos parecido.

    Devuelve (indices, similitudes), ambos ya ordenados. Solo compara contra
    las prendas de esa posición: una bermuda nunca compite con una camisa.
    `mascara`, si se da, sustituye a «las de esa posición» (ver candidatos).
    """
    idx = np.flatnonzero(pos_arm == posicion if mascara is None else mascara)
    if idx.size == 0:
        return idx, np.array([])
    sim = proyectar(V_arm[idx], ruta) @ proyectar(v_ref, ruta)[0]
    orden = np.argsort(-sim)
    return idx[orden], sim[orden]


def detectar_posicion(V_arm: np.ndarray, pos_arm: np.ndarray,
                      v_ref: np.ndarray, ruta) -> str:
    """Posición más probable de una prenda suelta: la de su vecina más cercana.

    Se compara la foto con las prendas de cada posición y gana la posición de
    la más parecida. Es comparable entre posiciones porque es el mismo vector
    y la misma proyección.

    Medido en el armario del autor, con la segunda toma de cada prenda contra
    las primeras tomas de las DEMÁS (CLIP sin proyectar): 109/118 = 92,4 %,
    frente a 59,3 % de responder siempre «arriba». Los fallos se concentran
    en «encima» (5 de 9 salen como «arriba»). Es una cifra optimista: mismas
    condiciones de foto que el armario. Por eso es solo el valor por defecto
    y el usuario lo puede cambiar.
    """
    mejor = {}
    for p in ORDEN:
        _, sims = ordenar(V_arm, pos_arm, v_ref, p, ruta)
        if sims.size:
            mejor[p] = float(sims[0])
    return max(mejor, key=mejor.get) if mejor else "arriba"


# ---------------------------------------------------------------------------
# Color primero
# ---------------------------------------------------------------------------

# APAGADO hasta que lo decida la medición (src/evaluar_busqueda.py). La regla
# está escrita allí: entra solo si mejora el acierto@1 sin empeorar el @3 en
# las parejas modelo → producto. Si no, se queda apagado y se reporta.
ORDEN_COLOR = False


@st.cache_data(show_spinner=False)
def umbrales_color() -> tuple[float, float] | None:
    """(mismo color, color cercano), calibrados en el armario del autor."""
    import json
    import pathlib
    from paginas import color
    f = (pathlib.Path(__file__).resolve().parents[1]
         / "experiments/color_primero/calibracion.json")
    try:
        cal = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return None
    if cal.get("version_color") != color.VERSION:
        return None       # calibrado con otro algoritmo: no vale
    return float(cal["umbral_mismo_color"]), float(cal["umbral_color_cercano"])


def ordenar_por_color(idx: np.ndarray, labs: np.ndarray, lab_ref,
                      umbrales) -> np.ndarray:
    """Reordena `idx` (ya ordenado por parecido) por franjas de color.

    Franja 0: mismo color; 1: cercano; 2: otro. Dentro de cada franja se
    conserva el orden por parecido. Si no hay ninguna del mismo color, la
    franja 0 queda vacía y el orden pasa solo a la siguiente. Una prenda sin
    color leído va a la última franja.
    """
    from paginas import color
    t1, t2 = umbrales
    de = np.full(len(idx), np.inf)
    ok = np.all(np.isfinite(labs[idx]), axis=1)
    if ok.any():
        de[ok] = color.delta_cmc(lab_ref, labs[idx][ok])
    franja = np.where(de <= t1, 0, np.where(de <= t2, 1, 2))
    return idx[np.argsort(franja, kind="stable")]


# ---------------------------------------------------------------------------
# Etiquetas de Gemini
# ---------------------------------------------------------------------------

# Ordenar por etiquetas: APAGADO hasta que lo decida src/evaluar_busqueda.py
# (misma regla que el color). Rellenar las preguntas con lo que ve la IA y
# atender a los ajustes en lenguaje natural sí va encendido si hay clave: en
# los dos casos la IA propone y el usuario ve y corrige.
ORDEN_ETIQUETAS = False
# Tipo, manga y largo (ver etiquetas.penalizacion_estructura). Decidido tras
# la evaluación, así que se midió aparte y se declara como análisis a
# posteriori (docs/resultados_busqueda_modelo_producto.md, §estructura):
# en las 24 parejas no empeora ninguna consulta en ninguna de las dos
# galerías (igual en 24/24 y 23/24; mejora 1: del puesto 29 al 11). Su
# utilidad está en lo que esa prueba no cubre —capas, corto frente a largo—
# y ahí solo hay ejemplos, no una medida.
ORDEN_ESTRUCTURA = True
# «Prioridades»: el orden que pidió el autor (color, luego tela, luego corte)
# con la estructura delante. Claves, de más a menos importante:
#   1. estructura dura (familia de tipo, manga, largo; etiquetas.niveles_prioridad)
#   2. franja de color por píxeles (la de ORDEN_COLOR, umbrales calibrados)
#   3. estructura blanda (vaquero frente a pantalón, camiseta frente a polo)
#   4. parecido en la proyección conjunta
# Por qué hace falta: la proyección se entrenó con los atributos de
# DeepFashion (textura, tela, forma, partes, estilo), que casi no incluyen el
# color. Ordena por forma y deja el color fuera; en la prueba modelo →
# producto la camiseta crudo cae al puesto 29 con ella y es la 1 con CLIP
# plano o con el color primero. Segunda ronda a posteriori, con la regla
# escrita ANTES de medirla (src/evaluar_busqueda.py, METODOS): entra si en la
# galería real no empeora el @1 ni el @3 de «estructura». Hasta entonces, False.
ORDEN_PRIORIDADES = False
# Resultado (docs/resultados_busqueda_modelo_producto.md): NO entra. Galería
# real 16/23 frente a 17/22; limpia 20/24 frente a 17/22. Pierde donde el
# color leído por píxeles en la foto del modelo cae lejos del del producto.
#
# Tercera ronda, con parejas NUEVAS (data/eval_color2) y la regla escrita
# antes de recogerlas (src/evaluar_busqueda.py, «prioridades_ia»): la misma
# idea con el color que dice la IA en vez del leído por píxeles.
ORDEN_PRIORIDADES_IA = False
# Resultado (30 parejas nuevas, galería de 172): NO entra, 20/26 frente a
# 23/26. «prioridades» (píxeles), medida ahí solo como réplica, sale 25/29;
# sumando las dos rondas, 41/52 frente a 40/48. Se sigue la regla: las dos
# quedan apagadas.
# Relacionado y con la misma condición: con la IA, cada pieza compite con las
# prendas de su tipo aunque estén en otra posición, lo de debajo de una
# prenda abierta se busca en la franja central, y una prenda no se repite
# como principal en dos columnas.


@st.cache_data(show_spinner=False, max_entries=64)
def analizar_referencia(datos: bytes) -> dict | None:
    """Lo que ve Gemini en la foto de referencia, o None si no está o falla.
    La aplicación nunca depende de esto: sin red o sin clave, se pregunta."""
    from paginas import etiquetas, gemini
    if not gemini.disponible():
        return None
    try:
        return etiquetas.analizar_look(datos)
    except gemini.ErrorGemini:
        return None


@st.cache_data(show_spinner=False, max_entries=64)
def interpretar(texto: str, piezas_json: str) -> dict | None:
    import json
    from paginas import etiquetas, gemini
    try:
        return etiquetas.interpretar_ajuste(texto, json.loads(piezas_json))
    except gemini.ErrorGemini:
        return None


def ordenar_por_etiquetas(idx: np.ndarray, etqs, pz: dict) -> np.ndarray:
    """Reordena `idx` (ya por parecido) por penalización de etiquetas. A
    igualdad de penalización se conserva el parecido."""
    from paginas import etiquetas
    pen = np.array([etiquetas.penalizacion(pz, etqs[i]) for i in idx])
    return idx[np.argsort(pen, kind="stable")]


def ordenar_por_estructura(idx: np.ndarray, etqs, pz: dict) -> np.ndarray:
    """Primero las de la misma manga y el mismo largo; dentro, por parecido."""
    from paginas import etiquetas
    pen = np.array([etiquetas.penalizacion_estructura(pz, etqs[i]) for i in idx])
    return idx[np.argsort(pen, kind="stable")]


def ordenar_por_prioridades(idx: np.ndarray, etqs, pz: dict | None,
                            labs: np.ndarray, lab_ref, umbrales,
                            color_ia: bool = False) -> np.ndarray:
    """Reordena `idx` (ya por parecido) por estructura dura, franja de color y
    estructura blanda; a igualdad de las tres, se conserva el parecido. Una
    prenda sin color leído va a la última franja; sin etiquetas, niveles 0.
    Con `color_ia`, la franja sale del color que dice la IA
    (etiquetas.franja_color) y no de los píxeles."""
    from paginas import color, etiquetas
    if color_ia:
        franja = np.array([etiquetas.franja_color(pz, etqs[i]) for i in idx], dtype=int)
    else:
        t1, t2 = umbrales
        de = np.full(len(idx), np.inf)
        ok = np.all(np.isfinite(labs[idx]), axis=1)
        if ok.any():
            de[ok] = color.delta_cmc(lab_ref, labs[idx][ok])
        franja = np.where(de <= t1, 0, np.where(de <= t2, 1, 2))
    niv = np.array([etiquetas.niveles_prioridad(pz, etqs[i]) for i in idx],
                   dtype=int).reshape(-1, 2)
    return idx[np.lexsort((np.arange(len(idx)), niv[:, 1], franja, niv[:, 0]))]


def describir(pz: dict) -> str:
    if pz.get("inferida"):
        return "algo debajo (no se ve bien)"
    partes = [nombre(pz.get("tipo")).lower() if pz.get("tipo") not in (None, "otra") else ""]
    if pz.get("manga") in ("corta", "larga"):
        partes.append(f"manga {pz['manga']}")
    if pz.get("largo") in ("corto", "largo") and pz.get("tipo") not in ("bermuda",):
        partes.append(pz["largo"])
    if pz.get("color"):
        partes.append(pz["color"])
    if pz.get("estampado") not in (None, "liso"):
        partes.append(pz["estampado"])
    return " ".join(p for p in partes if p)


ALTERNATIVAS = 2     # las que se ven sin pulsar nada
MAS = 10             # las que salen al pulsar «Ver más»


def reparto(n: int) -> tuple[int, int]:
    """(alternativas visibles, cuántas más tras «Ver más») con n prendas.

    La principal es una; debajo, hasta dos; el resto, hasta diez más, solo si
    se piden. Con pocas prendas no se rellena con lo que no hay.
    """
    alt = max(0, min(ALTERNATIVAS, n - 1))
    return alt, max(0, min(MAS, n - 1 - alt))


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

def compactar(html: str) -> str:
    """Quita la sangría y las líneas vacías de un bloque HTML.

    No es estética: `st.markdown` pasa el HTML por un intérprete de Markdown,
    y en Markdown una línea en blanco CIERRA el bloque HTML. Lo que viene
    detrás, si está sangrado cuatro espacios o más, se convierte en un bloque
    de código. Eso pasó: con la nota vacía quedaba una línea en blanco dentro
    de la tarjeta, media respuesta se pintaba como texto y la fila medía
    400 000 px de ancho, con la foto fuera de la pantalla.
    """
    return "".join(linea.strip() for linea in html.splitlines())


def _mini(r, puesto: int) -> str:
    uri = dato_uri(r["fichero"], ancho=260, rellenar=False)
    return (f'<div class="mini"><div class="cuadro">'
            f'<span class="puesto">{puesto:02d}</span>'
            f'<img class="a" src="{uri}" alt=""></div>'
            f'<p class="nom">{_html.escape(nombre(r.get("categoria")))}</p>'
            f'</div>')


def html_columna(posicion: str, filas: list, uri_recorte: str | None,
                 color_leido=None, aviso: str | None = None,
                 titulo: str | None = None) -> str:
    """Una posición: la prenda principal, dos parecidas y «Ver más».

    `filas` son las prendas de esa posición ya ordenadas de más a menos
    parecida. «Ver más» es un <details> de HTML: se abre en el navegador sin
    volver a ejecutar la página.
    """
    cab = f'<p class="rot-f pos">{_html.escape(titulo or ETIQUETA[posicion])}'
    if color_leido:
        # El color que se ha leído en la foto, a la vista: si se equivoca,
        # se ve por qué el orden es el que es.
        nom, (r, g, b) = color_leido
        cab += (f'<span class="leido"><i style="background:rgb({r},{g},{b})">'
                f'</i>{_html.escape(nom)}</span>')
    cab += '</p>'
    if aviso:
        return (f'<div class="col-pos">{cab}<div class="cuadro grande hueco">'
                f'<p>{aviso}</p></div></div>')
    if not filas:
        return (f'<div class="col-pos">{cab}<div class="cuadro grande hueco">'
                f'<p>No tienes prendas de esta posición.<br>Añádelas en Mi '
                f'armario.</p></div></div>')
    r0 = filas[0]
    a = dato_uri(r0["fichero"], ancho=620, rellenar=False)
    rel_b = str(r0.get("fichero_b") or "")
    b = dato_uri(rel_b, ancho=620, rellenar=False) if rel_b else a
    inserto = (f'<div class="inserto"><img src="{uri_recorte}" alt=""></div>'
               if uri_recorte else "")
    det = str(r0.get("descripcion_libre") or "").strip()
    alt, mas = reparto(len(filas))
    partes = [
        f'<div class="col-pos">{cab}',
        f'<div class="cuadro grande"><span class="puesto">01</span>'
        f'<img class="a" src="{a}" alt=""><img class="b" src="{b}" alt="">'
        f'{inserto}</div>',
        f'<p class="nom">{_html.escape(nombre(r0.get("categoria")))}</p>',
        f'<p class="det">{_html.escape(det) or "&nbsp;"}</p>',
    ]
    if alt:
        partes.append('<p class="rot sub-alt">También se parecen</p><div class="dos">'
                      + "".join(_mini(r, k + 2) for k, r in enumerate(filas[1:1 + alt]))
                      + '</div>')
    if mas:
        resto = filas[1 + alt:1 + alt + mas]
        partes.append(f'<details class="mas"><summary>Ver más ({len(resto)})</summary>'
                      f'<div class="tira">'
                      + "".join(_mini(r, k + 2 + alt) for k, r in enumerate(resto))
                      + '</div></details>')
    partes.append('</div>')
    return "".join(partes)


def html_resultado(columnas: list[str]) -> str:
    return compactar(f'<div class="resultado" style="--n:{len(columnas)};">'
                     f'{"".join(columnas)}</div>')
