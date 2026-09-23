"""
Capa de datos del armario por usuario (`paginas/armario.py`).

Corre sin torch ni Streamlit: el vector se sustituye por uno falso y todo va a
una base temporal, así que no toca `data/usuarios.db`.

    python tests/test_armario.py
"""

import hashlib
import io
import pathlib
import sys
import tempfile

import numpy as np
from PIL import Image

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from paginas import armario, auth  # noqa: E402

fallos = []


def check(nombre, cond, detalle=""):
    print(f"  {'OK  ' if cond else 'FALLA'}  {nombre} {detalle}")
    if not cond:
        fallos.append(nombre)


def vector_falso(jpeg: bytes) -> np.ndarray:
    semilla = int(hashlib.sha256(jpeg).hexdigest()[:8], 16)
    return np.random.default_rng(semilla).normal(size=armario.DIM)


def foto(w=600, h=400, color=(200, 30, 60), exif=None) -> bytes:
    buf = io.BytesIO()
    im = Image.new("RGB", (w, h), color)
    im.save(buf, format="JPEG", **({"exif": exif} if exif else {}))
    return buf.getvalue()


tmp = pathlib.Path(tempfile.mkdtemp())
BD, DATOS = tmp / "usuarios.db", tmp / "data"
auth.registrar(BD, "a@a.es", "Ana", "clave-larga-1")
auth.registrar(BD, "b@b.es", "Bea", "clave-larga-2")
A, B = 1, 2

print("\n=== 1. Añadir y listar ===")
pid = armario.anadir(BD, DATOS, A, "Camiseta", "arriba", foto(), vector_falso,
                     {"talla": "M", "color": " azul "})
V, filas = armario.listar(BD, A)
check("una prenda, un vector", V.shape == (1, 512) and len(filas) == 1)
check("categoría normalizada", filas[0]["categoria"] == "camiseta")
check("detalles recortados", filas[0]["color"] == "azul" and filas[0]["talla"] == "M")
check("detalle vacío -> NULL", filas[0]["corte"] is None)
check("foto dentro de la carpeta del usuario",
      filas[0]["foto"].startswith(f"usuarios/{A}/") and (DATOS / filas[0]["foto"]).exists())
check("vector guardado == vector calculado",
      np.allclose(V[0], vector_falso((DATOS / filas[0]["foto"]).read_bytes())))

print("\n=== 2. La foto se normaliza ===")
# EXIF con orientación 6 (girar 90º) y una etiqueta GPS.
ex = Image.Exif()
ex[0x0112] = 6
ex[0x8825] = {1: "N", 2: (40.0, 25.0, 0.0)}
jpeg = armario.preparar_foto(foto(800, 500, exif=ex.tobytes()))
im = Image.open(io.BytesIO(jpeg))
check("enderezada según EXIF", im.size == (500, 800), f"{im.size}")
check("sin EXIF (ni GPS)", len(im.getexif()) == 0)
im = Image.open(io.BytesIO(armario.preparar_foto(foto(4000, 3000))))
check("reducida a 1600 px", max(im.size) == 1600, f"{im.size}")

print("\n=== 3. Fotos que no valen ===")
for nombre, datos in [("demasiado pequeña", foto(150, 150)),
                      ("no es una imagen", b"esto no es un jpg")]:
    try:
        armario.preparar_foto(datos)
        check(nombre, False, "(no lanzó)")
    except ValueError:
        check(nombre + " -> ValueError", True)


def revienta(_):
    raise RuntimeError("CLIP caído")


antes = len(list((DATOS / "usuarios" / str(A)).glob("*.jpg")))
try:
    armario.anadir(BD, DATOS, A, "camisa", "arriba", foto(), revienta)
except RuntimeError:
    pass
check("si CLIP falla no queda foto huérfana",
      len(list((DATOS / "usuarios" / str(A)).glob("*.jpg"))) == antes)
for cat, pos in [("", "arriba"), ("camisa", "pies")]:
    try:
        armario.anadir(BD, DATOS, A, cat, pos, foto(), vector_falso)
        check(f"rechaza ({cat!r}, {pos!r})", False)
    except ValueError:
        check(f"rechaza ({cat!r}, {pos!r})", True)

print("\n=== 4. Cada usuario ve solo lo suyo ===")
armario.anadir(BD, DATOS, B, "pantalón", "abajo", foto(color=(10, 10, 90)), vector_falso)
check("A tiene 1, B tiene 1", armario.contar(BD, A) == 1 and armario.contar(BD, B) == 1)
check("B no ve la prenda de A", all(f["id"] != pid for f in armario.listar(BD, B)[1]))
check("B no puede borrar la de A", armario.borrar(BD, DATOS, B, pid) is False
      and armario.contar(BD, A) == 1)
ruta = DATOS / filas[0]["foto"]
check("A sí puede borrar la suya", armario.borrar(BD, DATOS, A, pid) is True)
check("y su foto desaparece", not ruta.exists())

print("\n=== 5. Categorías propias ===")
check("«Pantalón» == pantalon", armario.clave_categoria("  PANTALÓN ") == "pantalon")
armario.guardar_categoria(BD, A, "Sobrecamisa", "encima")
armario.guardar_categoria(BD, A, "sobrecamisa", "encima")
check("sin duplicados", armario.categorias_propias(BD, A) == {"sobrecamisa": "encima"})
check("son de cada usuario", armario.categorias_propias(BD, B) == {})

print("\n=== 6. Importación del armario del autor ===")
original = DATOS / "raw/wardrobe/img/x.jpg"
original.parent.mkdir(parents=True)
original.write_bytes(foto())
Vi = np.random.default_rng(0).normal(size=(3, 512)).astype(np.float32)
filas_i = [{"ref": f"w_000{i}", "foto": "raw/wardrobe/img/x.jpg",
            "categoria": c} for i, c in enumerate(["polo", "vaquero", "zapato"])]
pos = {"polo": "arriba", "vaquero": "abajo"}.get
n = armario.importar(BD, A, Vi, filas_i, pos)
check("importa las que tienen posición", n == 2, f"(n={n})")
check("segunda vez no duplica", armario.importar(BD, A, Vi, filas_i, pos) == 0)
Va, fa = armario.listar(BD, A)
check("vectores importados intactos",
      np.array_equal(Va[[f["ref"] == "w_0000" for f in fa]][0], Vi[0]))
for f in fa:
    armario.borrar(BD, DATOS, A, f["id"])
check("quitar una importada NO borra la foto original", original.exists())
check("vaciado no reimporta", armario.importar(BD, A, Vi, filas_i, pos) == 0
      and armario.contar(BD, A) == 0)

print()
if fallos:
    print(f"FALLAN {len(fallos)}: {fallos}")
    sys.exit(1)
print("Todo en orden.")
