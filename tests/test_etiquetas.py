"""
Etiquetas de Gemini (`paginas/etiquetas.py`): validación, penalización y
ajustes. Sin red: no se llama a la API.

    python tests/test_etiquetas.py
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from paginas import etiquetas as e  # noqa: E402

fallos = []


def check(nombre, cond, detalle=""):
    print(f"  {'OK  ' if cond else 'FALLA'}  {nombre} {detalle}")
    if not cond:
        fallos.append(nombre)


ref = {"tipo": "vaquero", "manga": "no_aplica", "largo": "largo", "color": "negro",
       "estampado": "liso", "tejido": "vaquero"}

print("\n=== 1. Normalizar: lo que no está en la lista se descarta ===")
n = e.normalizar({"hay_persona": 1, "piezas": [
    {"posicion": "abajo", "tipo": "vaquero", "color": "fucsia"},
    {"posicion": "x", "tipo": "camiseta"}, {"posicion": "arriba", "tipo": "toga"}]})
check("una pieza válida", len(n["piezas"]) == 1)
check("color inventado -> None", n["piezas"][0]["color"] is None)

print("\n=== 2. Penalización: el orden de prioridad ===")
pen = lambda **k: e.penalizacion(ref, dict(ref, **k))  # noqa: E731
check("idéntica = 0", pen() == 0)
check("otro tipo > otra forma > otro color > otro estampado",
      pen(tipo="camiseta") > pen(largo="corto") > pen(color="azul") > pen(estampado="rayas"),
      f"{pen(tipo='camiseta')} {pen(largo='corto')} {pen(color='azul')} {pen(estampado='rayas')}")
check("misma familia de color cuenta menos", pen(color="gris oscuro") < pen(color="azul"))
check("misma familia de tipo cuenta menos", pen(tipo="pantalon") < pen(tipo="camiseta"))
check("sin etiquetas no castiga", e.penalizacion(ref, None) == 0 and e.penalizacion(None, ref) == 0)
check("campo desconocido no castiga", pen(color=None) == 0)

print("\n=== 3. Ajustes ===")
aj = {"posicion": "abajo", "entendido": True, "largo": "corto", "color": "azul"}
nuevo = e.aplicar_ajuste(ref, "abajo", aj)
check("cambia lo pedido", nuevo["largo"] == "corto" and nuevo["color"] == "azul")
check("no toca el original", ref["largo"] == "largo")
check("no afecta a otra posición", e.aplicar_ajuste(ref, "arriba", aj) is ref)
check("no entendido = sin cambios",
      e.aplicar_ajuste(ref, "abajo", dict(aj, entendido=False)) is ref)
check("sin pieza previa crea una", e.aplicar_ajuste(None, "abajo", aj)["largo"] == "corto")

print("\n=== 4. Pieza por posición ===")
etq = {"piezas": [{"posicion": "arriba", "tipo": "camiseta"}, {"posicion": "abajo", "tipo": "vaquero"}]}
check("encuentra la de abajo", e.pieza(etq, "abajo")["tipo"] == "vaquero")
check("None si no hay", e.pieza(etq, "encima") is None)

print()
if fallos:
    print(f"FALLAN {len(fallos)}: {fallos}")
    sys.exit(1)
print("Todo en orden.")
