"""
El mapa categoría -> posición de la aplicación coincide con el del análisis.

Por qué existe este test
------------------------
La búsqueda por posiciones (`paginas/busqueda.py`) y el análisis de salto de
dominio (`src/domain_gap.py`) deciden, cada uno por su lado, si una prenda va
arriba, abajo o encima. Si esos dos mapas se separan, la aplicación estaría
enseñando posiciones que no son las que se midieron, y nadie lo notaría.

Se leen los diccionarios directamente del código fuente con `ast`, sin
importar los módulos: así el test no arrastra scikit-learn, torch ni
Streamlit, y corre en cualquier sitio.

Se ejecuta como los demás tests del proyecto:

    python tests/test_posiciones.py
"""

import ast
import csv
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[1]
fallos = []


def check(nombre, cond, detalle=""):
    print(f"  {'OK  ' if cond else 'FALLA'}  {nombre} {detalle}")
    if not cond:
        fallos.append(nombre)


def leer_asignaciones(ruta: pathlib.Path) -> dict:
    """Todas las asignaciones de nivel superior que sean literales."""
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    salida = {}
    for nodo in arbol.body:
        destino, valor = None, None
        if isinstance(nodo, ast.Assign) and len(nodo.targets) == 1:
            destino, valor = nodo.targets[0], nodo.value
        elif isinstance(nodo, ast.AnnAssign):
            destino, valor = nodo.target, nodo.value
        if isinstance(destino, ast.Name) and valor is not None:
            try:
                salida[destino.id] = ast.literal_eval(valor)
            except ValueError:
                pass
    return salida


analisis = leer_asignaciones(RAIZ / "src" / "domain_gap.py")
app = leer_asignaciones(RAIZ / "paginas" / "busqueda.py")

GRUPO, SLOT = analisis["GRUPO_ARMARIO"], analisis["SLOT_DE_GRUPO"]
POSICION, AÑADIDAS = app["POSICION"], set(app["AÑADIDAS"])
TRADUCE = app["_SLOT_A_POSICION"]

print("\n=== 1. La aplicación reproduce el mapa del análisis ===")
for cat, grupo in sorted(GRUPO.items()):
    esperado = TRADUCE[SLOT[grupo]]
    check(f"{cat:10s} -> {esperado}", POSICION.get(cat) == esperado,
          f"(app dice {POSICION.get(cat)!r})")

print("\n=== 2. Las únicas diferencias son las declaradas ===")
extra = set(POSICION) - set(GRUPO)
check("categorías añadidas == AÑADIDAS", extra == AÑADIDAS,
      f"(extra={sorted(extra)}, declaradas={sorted(AÑADIDAS)})")
check("el análisis no tiene categorías que la app ignore",
      set(GRUPO) <= set(POSICION), f"(faltan={sorted(set(GRUPO) - set(POSICION))})")

print("\n=== 3. Todas las prendas del armario tienen posición ===")
csv_armario = RAIZ / "data" / "raw" / "wardrobe" / "armario.csv"
if csv_armario.exists():
    with open(csv_armario, encoding="utf-8-sig") as f:
        cats = {r["categoria"].strip().lower() for r in csv.DictReader(f)
                if r.get("categoria", "").strip()}
    sin = sorted(c for c in cats if c not in POSICION)
    check(f"{len(cats)} categorías del armario mapeadas", not sin,
          f"(sin posición: {sin})")
else:
    print("  (sin armario.csv: se omite)")

print("\n=== 4. Las bandas de recorte son coherentes ===")
fuente = (RAIZ / "paginas" / "busqueda.py").read_text(encoding="utf-8")
arbol = ast.parse(fuente)
fn = next(n for n in arbol.body
          if isinstance(n, ast.FunctionDef) and n.name == "cajas_look")
ns = {}
exec(compile(ast.Module(body=[fn], type_ignores=[]), "cajas_look", "exec"), ns)
for cintura in (0.35, 0.52, 0.65):
    c = ns["cajas_look"](cintura)
    arr, aba = c["arriba"], c["abajo"]
    dentro = all(0 <= v <= 1 for caja in (arr, aba) for v in caja)
    check(f"cintura {cintura}: dentro de la imagen", dentro)
    check(f"cintura {cintura}: arriba empieza por encima de abajo",
          arr[1] < aba[1])
    check(f"cintura {cintura}: las bandas se solapan en la cintura",
          arr[3] > aba[1], f"(arriba acaba {arr[3]:.2f}, abajo empieza {aba[1]:.2f})")

print()
if fallos:
    print(f"FALLAN {len(fallos)}: {fallos}")
    sys.exit(1)
print("Todo en orden.")
