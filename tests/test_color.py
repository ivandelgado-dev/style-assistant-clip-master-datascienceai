"""
Color dominante por píxeles (`paginas/color.py`), con imágenes sintéticas.

    python tests/test_color.py
"""

import pathlib
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from paginas import color  # noqa: E402

fallos = []


def check(nombre, cond, detalle=""):
    print(f"  {'OK  ' if cond else 'FALLA'}  {nombre} {detalle}")
    if not cond:
        fallos.append(nombre)


def lienzo(fondo, w=400, h=500):
    return Image.new("RGB", (w, h), fondo)


print("\n=== 1. Conversión y distancia ===")
lab = color.rgb_a_lab(np.array([180, 20, 30]))
check("ida y vuelta Lab -> RGB", color.lab_a_rgb(lab) == (180, 20, 30), f"{color.lab_a_rgb(lab)}")
d = color.delta_cmc(color.rgb_a_lab([20, 20, 24]),
                    color.rgb_a_lab([[20, 20, 24], [30, 30, 34], [40, 50, 90]]))
check("ΔE a sí mismo = 0", abs(d[0]) < 1e-9)
check("negro vs gris oscuro < negro vs azul", d[1] < d[2], f"{d.round(1)}")

print("\n=== 2. Prenda suelta ===")
im = lienzo((230, 230, 230)); im.paste((180, 20, 30), (100, 100, 300, 420))
check("roja sobre gris -> rojo", color.nombre_color(color.color_prenda(im)[0]) == "rojo")
# Pantalón que toca los bordes laterales: el caso que rompía la versión c1.
im = lienzo((225, 215, 195), w=600, h=300); im.paste((25, 25, 30), (0, 80, 600, 220))
check("negra tocando el borde -> negro",
      color.nombre_color(color.color_prenda(im)[0]) == "negro",
      color.nombre_color(color.color_prenda(im)[0]))
arr = np.zeros((500, 400, 3), np.uint8); arr[:] = (200, 190, 170)
arr[::20] = (90, 60, 50); arr[1::20] = (90, 60, 50)
im = Image.fromarray(arr); im.paste((30, 45, 110), (100, 100, 300, 420))
check("azul sobre colcha de rayas -> azul marino/azul",
      color.nombre_color(color.color_prenda(im)[0]) in ("azul marino", "azul"),
      color.nombre_color(color.color_prenda(im)[0]))

print("\n=== 3. Persona ===")
banda = lienzo((120, 130, 110), w=300, h=300)          # calle
banda.paste((20, 20, 22), (70, 0, 230, 300))           # piernas en negro
check("banda de abajo -> negro",
      color.nombre_color(color.color_persona(banda, "abajo")[0]) == "negro")

print("\n=== 4. Determinista ===")
a = color.color_prenda(im)[0]; b = color.color_prenda(im)[0]
check("mismo píxel, mismo color", np.array_equal(a, b))

print()
if fallos:
    print(f"FALLAN {len(fallos)}: {fallos}")
    sys.exit(1)
print("Todo en orden.")
