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

print()
if fallos:
    print(f"FALLAN {len(fallos)}: {fallos}")
    sys.exit(1)
print("Todo en orden.")
