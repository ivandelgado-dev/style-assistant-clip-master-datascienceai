"""
Color dominante de una prenda, medido en los píxeles.

Por qué existe
--------------
No hay cabeza de color: se suprimió porque DeepFashion no trae ningún tipo de
atributo cromático (docs/resultados_eda_atributos.md, hallazgo 1), y la
hipótesis era que CLIP plano ya codifica bien el color. En condiciones de
catálogo puede que sí. Con una foto de calle contra fotos de producto falló a
la vista: ante un vaquero negro lavado, el primero fue uno azul.

Así que el color se mide aparte, sin modelo: visión clásica, auditable, y
cada paso se puede explicar en el tribunal.

Cómo
----
1. **Qué píxeles son prenda.**
   - Prenda suelta (foto de producto o del armario): el fondo se estima en el
     BORDE de la foto, que en una foto de prenda extendida es siempre fondo.
     Se agrupa en tres tonos (así se cubre también un fondo de dos tonos,
     como una colcha de rayas) y se descarta todo píxel parecido a ellos.
   - Persona: el borde no sirve, porque la prenda toca el borde de la banda
     recortada. Se mira una región fija donde, de pie y de frente, está la
     prenda: el torso para «arriba», los laterales del torso para «encima»
     (una camisa abierta se ve a los lados de la camiseta), y caderas y
     muslos para «abajo».
2. **Qué color domina.** k-medias ponderado (k=3) en espacio CIELAB, con más
   peso en el centro. El color es el del grupo con más peso.
3. **Cuánto se parecen dos colores.** ΔE CMC(2:1), la fórmula de la norma
   textil ISO 105-J03. El 2:1 tolera el doble en claridad que en tono: una
   misma prenda cambia mucho más de claridad (luz, sombra) que de tono, y es
   justo el cambio entre una foto de calle y una de estudio.

Lo que NO hace
--------------
No segmenta la prenda con un modelo. Con fondos estampados o con una pose
rara, el color puede salir mal. Por eso se enseña en pantalla el color que se
ha leído: si se equivoca, se ve por qué el orden es el que es.

Sin dependencias nuevas: numpy y PIL.
"""

from __future__ import annotations

import io

import numpy as np
from PIL import Image

VERSION = "c2"          # cambia si cambia el algoritmo: obliga a recalcular
LADO = 128              # px del lado mayor al medir: sobra para un color
BORDE = 0.06            # fracción de cada lado que se toma como fondo
UMBRAL_FONDO = 12.0     # ΔE76 por debajo del cual un píxel es fondo


# ---------------------------------------------------------------------------
# sRGB -> CIELAB (D65)
# ---------------------------------------------------------------------------

_M = np.array([[0.4124564, 0.3575761, 0.1804375],
               [0.2126729, 0.7151522, 0.0721750],
               [0.0193339, 0.1191920, 0.9503041]])
_BLANCO = np.array([0.95047, 1.0, 1.08883])


def rgb_a_lab(rgb: np.ndarray) -> np.ndarray:
    c = np.asarray(rgb, dtype=np.float64) / 255.0
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    t = (lin @ _M.T) / _BLANCO
    f = np.where(t > 0.008856, np.cbrt(t), 7.787 * t + 16 / 116)
    L = 116 * f[..., 1] - 16
    a = 500 * (f[..., 0] - f[..., 1])
    b = 200 * (f[..., 1] - f[..., 2])
    return np.stack([L, a, b], axis=-1)


def lab_a_rgb(lab) -> tuple[int, int, int]:
    """Solo para pintar la muestra en pantalla."""
    L, a, b = lab
    fy = (L + 16) / 116
    f = np.array([fy + a / 500, fy, fy - b / 200])
    t = np.where(f ** 3 > 0.008856, f ** 3, (f - 16 / 116) / 7.787) * _BLANCO
    lin = np.linalg.solve(_M, t)
    c = np.where(lin <= 0.0031308, 12.92 * lin, 1.055 * np.clip(lin, 0, None) ** (1 / 2.4) - 0.055)
    return tuple(int(round(v)) for v in np.clip(c, 0, 1) * 255)


# ---------------------------------------------------------------------------
# Distancia CMC(l:c)
# ---------------------------------------------------------------------------

def delta_cmc(ref, otros, l: float = 2.0, c: float = 1.0) -> np.ndarray:
    """ΔE CMC(l:c) de cada color de `otros` respecto a `ref`.

    CMC no es simétrica: las tolerancias se calculan sobre el color de
    referencia. Aquí la referencia es siempre la foto que se busca.
    """
    L1, a1, b1 = np.asarray(ref, dtype=np.float64)
    O = np.atleast_2d(np.asarray(otros, dtype=np.float64))
    L2, a2, b2 = O[:, 0], O[:, 1], O[:, 2]
    C1, C2 = np.hypot(a1, b1), np.hypot(a2, b2)
    dL, dC = L1 - L2, C1 - C2
    dH2 = np.clip((a1 - a2) ** 2 + (b1 - b2) ** 2 - dC ** 2, 0, None)
    H1 = np.degrees(np.arctan2(b1, a1)) % 360
    SL = 0.511 if L1 < 16 else 0.040975 * L1 / (1 + 0.01765 * L1)
    SC = 0.0638 * C1 / (1 + 0.0131 * C1) + 0.638
    F = np.sqrt(C1 ** 4 / (C1 ** 4 + 1900))
    T = (0.56 + abs(0.2 * np.cos(np.radians(H1 + 168))) if 164 <= H1 <= 345
         else 0.36 + abs(0.4 * np.cos(np.radians(H1 + 35))))
    SH = SC * (F * T + 1 - F)
    return np.sqrt((dL / (l * SL)) ** 2 + (dC / (c * SC)) ** 2 + dH2 / SH ** 2)


# ---------------------------------------------------------------------------
# k-medias ponderado, determinista
# ---------------------------------------------------------------------------

def _kmedias(X: np.ndarray, w: np.ndarray, k: int, iters: int = 12):
    """Centros y peso de cada grupo. Semilla fija: mismo píxel, mismo color."""
    k = min(k, len(X))
    rng = np.random.default_rng(0)
    p = w / w.sum()
    C = X[rng.choice(len(X), size=k, replace=False, p=p)]
    for _ in range(iters):
        asig = np.argmin(((X[:, None, :] - C[None]) ** 2).sum(-1), axis=1)
        for j in range(k):
            m = asig == j
            if w[m].sum() > 0:
                C[j] = (X[m] * w[m, None]).sum(0) / w[m].sum()
    asig = np.argmin(((X[:, None, :] - C[None]) ** 2).sum(-1), axis=1)
    pesos = np.array([w[asig == j].sum() for j in range(k)])
    return C, pesos / pesos.sum()


# ---------------------------------------------------------------------------
# Color dominante
# ---------------------------------------------------------------------------

# Regiones (x0, y0, x1, y1) dentro de la BANDA ya recortada de una persona.
REGIONES_PERSONA = {
    "arriba": [(0.30, 0.20, 0.70, 0.75)],                   # torso
    "encima": [(0.12, 0.15, 0.32, 0.80), (0.68, 0.15, 0.88, 0.80)],  # lados
    "abajo":  [(0.22, 0.05, 0.78, 0.55)],                   # caderas y muslos
}


def _pequena(im: Image.Image) -> np.ndarray:
    if im.format == "JPEG":
        # Decodifica ya reducida (1/2 … 1/8): una foto de móvil de 12 Mpx
        # pasa de ~100 ms a ~10 ms, y para un color sobran 128 px.
        im.draft("RGB", (LADO * 2, LADO * 2))
    im = im.convert("RGB")
    im.thumbnail((LADO, LADO), Image.BILINEAR)
    return rgb_a_lab(np.asarray(im))


def color_prenda(im: Image.Image) -> tuple[np.ndarray, float]:
    """(Lab, fracción de prenda) de una foto de prenda suelta."""
    lab = _pequena(im)
    h, w, _ = lab.shape
    by, bx = max(1, int(h * BORDE)), max(1, int(w * BORDE))
    borde = np.ones((h, w), bool)
    borde[by:h - by, bx:w - bx] = False
    centro_zona = np.zeros((h, w), bool)
    centro_zona[int(h * .3):int(h * .7), int(w * .3):int(w * .7)] = True

    # Tonos del borde. No todos son fondo: un pantalón extendido a lo ancho
    # o unas mangas abiertas TOCAN el borde, y en la primera versión su color
    # se tomaba por fondo y se borraba la prenda (w_0050, un vaquero negro,
    # salía «crudo»: el color de la colcha). Un tono del borde es fondo solo
    # si abunda en el borde MÁS que en el centro de la foto.
    tonos, _ = _kmedias(lab[borde], np.ones(borde.sum()), 3)
    cerca = np.argmin(np.linalg.norm(lab[..., None, :] - tonos[None, None],
                                     axis=-1), axis=-1)
    d_tono = np.min(np.linalg.norm(lab[..., None, :] - tonos[None, None],
                                   axis=-1), axis=-1)
    fondo = np.zeros((h, w), bool)
    for j in range(len(tonos)):
        del_tono = (cerca == j) & (d_tono < UMBRAL_FONDO)
        en_borde = del_tono[borde].mean()
        en_centro = del_tono[centro_zona].mean()
        if en_borde >= 0.15 and en_centro < en_borde:
            fondo |= del_tono
    prenda = ~fondo
    if prenda.mean() < 0.05:
        # Prenda del mismo color que el fondo: se renuncia a separarlas y se
        # mira el centro.
        prenda = centro_zona
    yy, xx = np.mgrid[0:h, 0:w]
    centro = np.exp(-(((xx / w - .5) ** 2 + (yy / h - .5) ** 2) / (2 * .28 ** 2)))
    X, peso = lab[prenda], centro[prenda]
    C, pesos = _kmedias(X, peso, 3)
    return C[np.argmax(pesos)], float(prenda.mean())


def color_persona(banda: Image.Image, posicion: str) -> tuple[np.ndarray, float]:
    """(Lab, 1.0) de la prenda de `posicion` en una banda de persona."""
    lab = _pequena(banda)
    h, w, _ = lab.shape
    trozos = [lab[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)].reshape(-1, 3)
              for x0, y0, x1, y1 in REGIONES_PERSONA[posicion]]
    X = np.concatenate(trozos)
    C, pesos = _kmedias(X, np.ones(len(X)), 3)
    return C[np.argmax(pesos)], 1.0


def color_de_bytes(datos: bytes) -> np.ndarray:
    return color_prenda(Image.open(io.BytesIO(datos)))[0]


# ---------------------------------------------------------------------------
# Nombre, solo para enseñarlo
# ---------------------------------------------------------------------------

_PALETA = {
    "negro": (15, 0, 0), "gris oscuro": (35, 0, 0), "gris": (55, 0, 0),
    "gris claro": (75, 0, 0), "blanco": (94, 0, 1), "crudo": (90, 1, 9),
    "beige": (78, 4, 18), "camel": (60, 12, 32), "marrón": (38, 14, 24),
    "caqui": (50, -6, 25), "verde": (50, -35, 25), "verde oscuro": (30, -18, 12),
    "azul marino": (22, 5, -25), "azul": (45, 5, -40), "azul claro": (72, -6, -20),
    "vaquero": (48, -2, -18), "rojo": (48, 60, 40), "burdeos": (28, 32, 10),
    "rosa": (75, 25, 3), "rosa palo": (80, 12, 6), "naranja": (65, 40, 60), "amarillo": (88, -5, 70),
    "morado": (35, 35, -35),
}


def nombre_color(lab) -> str:
    nombres = list(_PALETA)
    d = delta_cmc(lab, np.array([_PALETA[n] for n in nombres]))
    return nombres[int(np.argmin(d))]
