"""
Cuentas (`paginas/auth.py`): registro, reglas de nombre y contraseña, límite
de intentos y foto de perfil.

Sin Streamlit ni red: una base temporal.

    python tests/test_auth.py
"""

import io
import pathlib
import sys
import tempfile

from PIL import Image

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from paginas import auth  # noqa: E402

fallos = []


def check(nombre, cond, detalle=""):
    print(f"  {'OK  ' if cond else 'FALLA'}  {nombre} {detalle}")
    if not cond:
        fallos.append(nombre)


tmp = pathlib.Path(tempfile.mkdtemp())
BD = tmp / "usuarios.db"

print("\n=== 1. Nombre y apellidos ===")
V = auth.validar_registro
check("nombre con tildes y compuesto", V("a@b.es", "María José", "clave123", "clave123") is None)
check("apellidos con guion y apóstrofo",
      V("a@b.es", "Iván", "clave123", "clave123", "O'Neill García-Pérez") is None)
check("sin nombre: no", V("a@b.es", "  ", "clave123", "clave123") is not None)
check("nombre con números: no", V("a@b.es", "Iván2", "clave123", "clave123") is not None)
check("nombre con HTML: no", V("a@b.es", "<b>x</b>", "clave123", "clave123") is not None)
check("nombre demasiado largo: no", V("a@b.es", "A" * 41, "clave123", "clave123") is not None)
check("apellidos opcionales", V("a@b.es", "Iván", "clave123", "clave123", "") is None)

print("\n=== 2. Contraseña ===")
check("solo letras: no", auth.validar_clave("abcdefgh") is not None)
check("solo números: no", auth.validar_clave("12345678") is not None)
check("corta: no", auth.validar_clave("abc123") is not None)
check("letras y números: sí", auth.validar_clave("abcd1234") is None)
check("igual que el correo: no", auth.validar_clave("ivan1234", "ivan1234@x.es") is not None)
check("más de 128: no", auth.validar_clave("a1" * 65) is not None)

print("\n=== 3. Registro y acceso ===")
ok, _ = auth.registrar(BD, "Ivan@X.es", "  Iván  ", "clave123", apellidos=" Delgado ")
check("se registra", ok)
d = auth.datos(BD, 1)
check("correo en minúsculas, nombre y apellidos sin espacios de sobra",
      d["correo"] == "ivan@x.es" and d["nombre"] == "Iván" and d["apellidos"] == "Delgado")
check("correo repetido: no", not auth.registrar(BD, "ivan@x.es", "Otro", "clave123")[0])
check("entra", auth.acceder(BD, "ivan@x.es", "clave123") is not None)
check("datos() nunca devuelve sal ni hash", "sal" not in d and "clave" not in d)

print("\n=== 4. Límite de intentos ===")
for _ in range(auth.MAX_FALLOS):
    auth.acceder(BD, "ivan@x.es", "mala1234")
check("tras 5 fallos, bloqueado", auth.espera_bloqueo("ivan@x.es") > 0)
check("bloqueado: ni con la buena", auth.acceder(BD, "ivan@x.es", "clave123") is None)
for _ in range(auth.MAX_FALLOS):
    auth.acceder(BD, "nadie@x.es", "mala1234")
check("un correo que no existe se bloquea igual (no delata cuáles existen)",
      auth.espera_bloqueo("nadie@x.es") > 0)
auth._FALLOS.clear()
check("un acierto limpia el contador", auth.acceder(BD, "ivan@x.es", "clave123") is not None
      and auth.espera_bloqueo("ivan@x.es") == 0)

print("\n=== 5. Cambiar contraseña con las reglas nuevas ===")
check("sin números: no", not auth.cambiar_clave(BD, 1, "clave123", "abcdefgh", "abcdefgh")[0])
check("con la actual mal: no", not auth.cambiar_clave(BD, 1, "mala", "nueva123", "nueva123")[0])
check("bien: sí", auth.cambiar_clave(BD, 1, "clave123", "nueva123", "nueva123")[0])

print("\n=== 6. Perfil y foto ===")
check("perfil: nombre vacío no", not auth.actualizar_perfil(BD, 1, " ", "")[0])
check("perfil: se guarda", auth.actualizar_perfil(BD, 1, "Iván", "Delgado Chaparro")[0]
      and auth.datos(BD, 1)["apellidos"] == "Delgado Chaparro")
b = io.BytesIO()
im = Image.new("RGB", (900, 600), "red")
exif = im.getexif()
exif[0x010F] = "MovilDePrueba"          # fabricante: no debe sobrevivir
im.save(b, "JPEG", exif=exif)
ok, _ = auth.guardar_foto(BD, tmp, 1, b.getvalue())
rel = auth.datos(BD, 1)["foto"]
guardada = Image.open(tmp / rel) if rel else None
check("foto: se guarda cuadrada a 400 px", ok and guardada is not None and guardada.size == (400, 400))
check("foto: sin metadatos", guardada is not None and not guardada.getexif())
ok2, _ = auth.guardar_foto(BD, tmp, 1, b.getvalue()[:-10] + b"0000000000")
rel2 = auth.datos(BD, 1)["foto"]
check("foto nueva: solo queda una en la carpeta",
      len(list((tmp / "usuarios/1").glob("perfil_*.jpg"))) == 1)
check("no es una imagen: no", not auth.guardar_foto(BD, tmp, 1, b"no soy una foto")[0])
check("demasiado grande: no", not auth.guardar_foto(BD, tmp, 1, b"0" * (auth.MAX_FOTO + 1))[0])
auth.quitar_foto(BD, tmp, 1)
check("quitar: sin foto y sin fichero", auth.datos(BD, 1)["foto"] is None
      and not list((tmp / "usuarios/1").glob("perfil_*.jpg")))

print("\n=== 7. Eliminar cuenta ===")
import json  # noqa: E402
import numpy as np  # noqa: E402
from paginas import armario, etiquetas  # noqa: E402
etiquetas.CACHE = tmp / "cache.json"
BD2, D2 = tmp / "u2.db", tmp / "d2"
auth.registrar(BD2, "a@x.es", "Ana", "clave123")
auth.registrar(BD2, "b@x.es", "Beto", "clave123")
vec = lambda _b: np.ones(armario.DIM, np.float32)  # noqa: E731


def jpg(color):
    b = io.BytesIO()
    Image.new("RGB", (300, 300), color).save(b, "JPEG")
    return b.getvalue()


pa = armario.anadir(BD2, D2, 1, "camiseta", "arriba", jpg("red"), vec)
pb = armario.anadir(BD2, D2, 1, "vaquero", "abajo", jpg("blue"), vec)
qb = armario.anadir(BD2, D2, 2, "camiseta", "arriba", jpg("green"), vec)
qc = armario.anadir(BD2, D2, 2, "vaquero", "abajo", jpg("white"), vec)
armario.valorar_outfit(BD2, 1, {"arriba": pa, "abajo": pb}, 1, estilo="casual")
armario.valorar_outfit(BD2, 2, {"arriba": qb, "abajo": qc}, -1, estilo="casual")
auth.guardar_foto(BD2, D2, 1, jpg("black"))
fotos_a = [D2 / f["foto"] for f in armario.listar(BD2, 1)[1]]
etiquetas.CACHE.write_text(json.dumps({
    f"{__import__('hashlib').sha1(fotos_a[0].read_bytes()).hexdigest()}|e1|m": {"x": 1},
    "otra|e1|m": {"x": 2}}), encoding="utf-8")
check("con la contraseña mal: no se borra nada",
      not auth.eliminar_cuenta(BD2, D2, 1, "mala1234")[0] and auth.datos(BD2, 1) is not None
      and armario.contar(BD2, 1) == 2)
ok, _ = auth.eliminar_cuenta(BD2, D2, 1, "clave123")
check("con la buena: se elimina", ok and auth.datos(BD2, 1) is None)
check("su armario, fuera", armario.contar(BD2, 1) == 0)
check("su carpeta (fotos y perfil), fuera", not (D2 / "usuarios/1").exists())
import sqlite3  # noqa: E402
cx = sqlite3.connect(BD2)
n_out = cx.execute("SELECT COUNT(*) FROM outfits WHERE usuario_id = 1").fetchone()[0]
n_fb = cx.execute("SELECT COUNT(*) FROM feedback WHERE usuario_id = 1").fetchone()[0]
n_otro = cx.execute("SELECT COUNT(*) FROM feedback WHERE usuario_id = 2").fetchone()[0]
cx.close()
check("sus outfits y valoraciones, fuera", n_out == 0 and n_fb == 0)
check("lo que la IA dijo de sus fotos, fuera de la caché",
      list(json.loads(etiquetas.CACHE.read_text(encoding="utf-8"))) == ["otra|e1|m"])
check("la otra cuenta, intacta", auth.datos(BD2, 2) is not None and armario.contar(BD2, 2) == 2
      and n_otro == 1 and (D2 / "usuarios/2").exists())

print()
if fallos:
    print(f"FALLAN {len(fallos)}: {fallos}")
    sys.exit(1)
print("Todo en orden.")
