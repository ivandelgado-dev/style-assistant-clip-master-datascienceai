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

print("\n=== 5. Orden «prioridades» ===")
import numpy as np  # noqa: E402
import importlib.util  # noqa: E402
if importlib.util.find_spec("torch") is None:   # busqueda lo importa; aquí no se usa
    import types
    sys.modules["torch"] = types.ModuleType("torch")
from paginas import busqueda, color  # noqa: E402
P = lambda **k: dict({"tipo": "pantalon", "manga": "no_aplica", "largo": "largo"}, **k)  # noqa: E731
check("vaquero frente a pantalón es blando",
      e.niveles_prioridad(P(), P(tipo="vaquero")) == (0, 1))
check("bermuda frente a pantalón largo es duro",
      e.niveles_prioridad(P(), P(tipo="bermuda", largo="corto"))[0] >= 1)
check("sudadera frente a camiseta es duro",
      e.niveles_prioridad({"tipo": "camiseta", "manga": "corta"},
                          {"tipo": "sudadera", "manga": "corta"}) == (1, 0))
check("sin etiquetas, (0, 0)", e.niveles_prioridad(None, P()) == (0, 0))
# Foto: pantalón largo gris oscuro. Armario, ya ordenado por parecido:
# 0 camuflaje (pantalón, lejos de color), 1 vaquero negro, 2 bermuda gris oscuro.
gris_osc, negro, verde = [30, 0, 0], [18, 0, 0], [45, -15, 20]
labs = np.array([verde, negro, gris_osc], dtype=float)
etqs = [P(), P(tipo="vaquero"), P(tipo="bermuda", largo="corto")]
orden = busqueda.ordenar_por_prioridades(np.array([0, 1, 2]), etqs, P(),
                                         labs, np.array(gris_osc, float), (4.52, 9.05))
check("el color pesa más que vaquero/pantalón", int(orden[0]) == 1, f"{orden}")
check("la bermuda, aunque sea del color, al final", int(orden[-1]) == 2, f"{orden}")
labs[1] = np.nan
orden = busqueda.ordenar_por_prioridades(np.array([0, 1, 2]), etqs, P(),
                                         labs, np.array(gris_osc, float), (4.52, 9.05))
check("sin color leído no revienta y va detrás", int(orden[0]) == 0, f"{orden}")
_ = color
check("franja IA: misma familia = 1", e.franja_color({"color": "negro"}, {"color": "gris oscuro"}) == 1)
check("franja IA: sin color = 2", e.franja_color({"color": "negro"}, None) == 2)
et = [P(color="verde"), P(tipo="vaquero", color="negro"),
      P(tipo="bermuda", largo="corto", color="gris oscuro"), P(color=None)]
orden = busqueda.ordenar_por_prioridades(np.arange(4), et, P(color="gris oscuro"),
                                         None, None, None, color_ia=True)
check("prioridades_ia: vaquero negro primero, bermuda al final",
      int(orden[0]) == 1 and int(orden[-1]) == 2, f"{orden}")

print("\n=== 6. Capas ===")
sud = {"posicion": "encima", "tipo": "sudadera", "abierta": True}
abr = {"posicion": "encima", "tipo": "abrigo", "abierta": False}
pan = {"posicion": "abajo", "tipo": "pantalon"}
c = e.completar_capas({"hay_persona": True, "piezas": [sud, pan]})
check("abierta sin nada debajo: se añade lo de debajo",
      e.pieza(c, "arriba") is not None and e.pieza(c, "arriba").get("inferida"))
cam = {"posicion": "arriba", "tipo": "camiseta"}
c2 = e.completar_capas({"hay_persona": True, "piezas": [cam, sud, pan]})
check("si ya está, no se duplica", len(c2["piezas"]) == 3)
c3 = e.completar_capas({"hay_persona": True, "piezas": [{**sud, "abierta": False}, pan]})
check("cerrada: no se inventa nada", e.pieza(c3, "arriba") is None)
check("prenda suelta: no se toca",
      e.completar_capas({"hay_persona": False, "piezas": [sud]})["piezas"] == [sud])
check("capas de dentro a fuera",
      [q["tipo"] for q in e.capas_encima({"piezas": [cam, sud, abr, pan]})] == ["sudadera", "abrigo"])
# Armario: 0 camiseta (arriba), 1 sudadera guardada arriba, 2 sin etiqueta (arriba),
# 3 cazadora (encima)
pos = np.array(["arriba", "arriba", "arriba", "encima"])
et = [{"tipo": "camiseta"}, {"tipo": "sudadera"}, None, {"tipo": "cazadora"}]
m = busqueda.candidatos(pos, et, "arriba", e.pieza(c, "arriba"), bajo_capa=True)
check("debajo de una capa: la sudadera guardada «arriba» no compite",
      list(m) == [True, False, True, False], f"{list(m)}")
m = busqueda.candidatos(pos, et, "arriba", {"tipo": "sudadera"}, bajo_capa=True)
check("si lo de debajo es una sudadera (bajo un abrigo), sí compite",
      list(m) == [True, True, True, False], f"{list(m)}")
m = busqueda.candidatos(pos, et, "encima", sud)
check("la sudadera guardada «arriba» compite encima", bool(m[1]) and bool(m[3]))
check("la inferida se describe como tal",
      busqueda.describir(e.pieza(c, "arriba")).startswith("algo debajo"))

print()
if fallos:
    print(f"FALLAN {len(fallos)}: {fallos}")
    sys.exit(1)
print("Todo en orden.")
