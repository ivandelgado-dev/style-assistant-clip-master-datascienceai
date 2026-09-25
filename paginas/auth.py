"""
Autenticación local para la demo.

Qué es y qué no es
------------------
Esto NO es una capa de autenticación de producción. Es lo mínimo honesto para
que la demo tenga registro y acceso sin mentir sobre lo que hace:

- Las contraseñas **nunca** se guardan. Se guarda `scrypt(clave, sal)` con una
  sal aleatoria de 16 bytes por usuario. `scrypt` está en `hashlib`, en la
  biblioteca estándar: no añade dependencias y es una KDF con coste de memoria,
  que es lo correcto para contraseñas. Un hash rápido (MD5, SHA-256 a secas) no
  lo sería: se rompe por fuerza bruta a millones de intentos por segundo.
- La comparación es en tiempo constante (`hmac.compare_digest`), para no filtrar
  información por el tiempo de respuesta.
- El almacén es SQLite, que también es biblioteca estándar. Vive en
  `data/usuarios.db`, que el `.gitignore` excluye: las credenciales no viajan
  al repositorio.

Limitaciones, declaradas a propósito
------------------------------------
1. **La sesión no persiste al recargar.** Vive en `st.session_state`, que
   Streamlit reinicia con cada recarga del navegador. Mantenerla exigiría una
   cookie firmada, y Streamlit no expone cookies sin un componente externo.
2. **No hay recuperación de contraseña ni verificación de correo.** Las dos
   exigen enviar correos: un servidor SMTP con credenciales, entregabilidad,
   tokens con caducidad. Es trabajo de producto, no de evaluación, y un fallo
   en directo rompería la demo. Queda como trabajo futuro. Por lo mismo, el
   correo no se puede cambiar: sin verificar el nuevo, una sesión abierta
   bastaría para llevarse la cuenta.
   Sí hay (25/09) **límite de intentos**: 5 fallos seguidos con un correo
   bloquean ese correo 5 minutos. Se cuenta en memoria y por correo, exista o
   no la cuenta: si solo se bloquearan las que existen, el bloqueo diría qué
   correos están registrados. Se pierde al reiniciar el servidor, y basta
   para frenar la fuerza bruta contra una cuenta.
3. **Un usuario nuevo empieza con el armario vacío** y sube sus prendas desde
   Mi armario (`paginas/armario.py`). La primera cuenta registrada queda
   marcada con `armario = 'propio'`: al entrar se le importan las 118 prendas
   del autor, con los vectores ya calculados con los que se midió el trabajo.

Por qué existe esto si la entrega 3 lo descartaba
-------------------------------------------------
La entrega 3 argumenta que login y sesiones no aportan nada a la evaluación del
sistema de recomendación, y ese argumento sigue siendo cierto: ninguna métrica
de este trabajo cambia por tener autenticación. Se implementa como capa de
producto, explícitamente fuera del núcleo evaluado. La memoria debe recoger el
cambio y este razonamiento.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# Parámetros de scrypt. n=2**14 es un compromiso razonable para una demo que
# corre en un portátil: ~100 ms por derivación. Subirlo endurece el ataque por
# fuerza bruta y encarece el login legítimo en la misma proporción.
_N, _R, _P, _DK = 2 ** 14, 8, 1, 32
_SAL = 16

_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_CLAVE = 8
MAX_CLAVE = 128            # scrypt acepta más, pero no tiene sentido y cuesta
# Nombre y apellidos: letras (con tildes y ñ), espacios, guion y apóstrofo.
# Sin dígitos ni símbolos: evita basura y HTML, y cubre nombres reales como
# «María José», «O'Neill» o «García-Pérez».
_NOMBRE = re.compile(r"^[^\W\d_]+(?:[ '\-][^\W\d_]+)*$")
MAX_NOMBRE, MAX_APELLIDOS = 40, 60

# Límite de intentos: ver la cabecera, punto 2.
MAX_FALLOS, BLOQUEO_S = 5, 300
_FALLOS: dict[str, tuple[int, float]] = {}


def _texto_nombre(valor: str, campo: str, maximo: int, obligatorio: bool) -> str | None:
    v = " ".join(valor.split())
    if not v:
        return f"Escribe tu {campo}." if obligatorio else None
    if len(v) > maximo:
        return f"El {campo} no puede pasar de {maximo} caracteres."
    if not _NOMBRE.match(v):
        return f"El {campo} solo puede llevar letras, espacios, guion o apóstrofo."
    return None


def validar_clave(clave: str, correo: str = "") -> str | None:
    """Mínimo 8, máximo 128, con letras y números, y distinta del correo."""
    if len(clave) < MIN_CLAVE:
        return f"La contraseña debe tener al menos {MIN_CLAVE} caracteres."
    if len(clave) > MAX_CLAVE:
        return f"La contraseña no puede pasar de {MAX_CLAVE} caracteres."
    if not (re.search(r"[^\W\d_]", clave) and re.search(r"\d", clave)):
        return "La contraseña tiene que llevar letras y números."
    if correo and clave.strip().lower() in (correo.strip().lower(),
                                            correo.strip().lower().split("@")[0]):
        return "La contraseña no puede ser tu correo."
    return None


def espera_bloqueo(correo: str) -> int:
    """Segundos que faltan para poder volver a intentarlo (0 = libre)."""
    import time
    n, hasta = _FALLOS.get(correo.strip().lower(), (0, 0.0))
    return max(0, int(hasta - time.time())) if n >= MAX_FALLOS else 0


def _apuntar(correo: str, ok: bool) -> None:
    import time
    c = correo.strip().lower()
    if ok:
        _FALLOS.pop(c, None)
        return
    n, _ = _FALLOS.get(c, (0, 0.0))
    n += 1
    _FALLOS[c] = (n, time.time() + BLOQUEO_S if n >= MAX_FALLOS else 0.0)


def _conexion(bd: Path) -> sqlite3.Connection:
    bd.parent.mkdir(parents=True, exist_ok=True)
    cx = sqlite3.connect(bd)
    cx.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            correo  TEXT    NOT NULL UNIQUE,
            nombre  TEXT    NOT NULL,
            sal     BLOB    NOT NULL,
            clave   BLOB    NOT NULL,
            armario TEXT,                      -- NULL = sin armario propio
            creado  TEXT    NOT NULL
        )""")
    # Altura, opcional (24/09). Solo la usa una regla de proporción de «Por
    # estilo» que el usuario ve y puede apagar (paginas/outfits.py). El peso
    # no se pide: no hay regla que lo use sin juzgar un cuerpo.
    cols = {f[1] for f in cx.execute("PRAGMA table_info(usuarios)")}
    if "altura_cm" not in cols:
        cx.execute("ALTER TABLE usuarios ADD COLUMN altura_cm INTEGER")
    # Perfil (25/09): apellidos opcionales y foto de perfil (ruta relativa a
    # data/, como las prendas). Sin nombre de usuario: se entra con el
    # correo, y un segundo identificador único no aporta nada.
    for c in ("apellidos", "foto"):
        if c not in cols:
            cx.execute(f"ALTER TABLE usuarios ADD COLUMN {c} TEXT")
    cx.commit()
    return cx


def _derivar(clave: str, sal: bytes) -> bytes:
    return hashlib.scrypt(clave.encode("utf-8"), salt=sal,
                          n=_N, r=_R, p=_P, dklen=_DK)


def validar_registro(correo: str, nombre: str, clave: str,
                     repetida: str, apellidos: str = "") -> str | None:
    """Devuelve el mensaje de error, o None si los datos son válidos."""
    err = (_texto_nombre(nombre, "nombre", MAX_NOMBRE, True)
           or _texto_nombre(apellidos, "apellido", MAX_APELLIDOS, False))
    if err:
        return err
    if len(correo.strip()) > 254 or not _CORREO.match(correo.strip()):
        return "Ese correo no tiene un formato válido."
    err = validar_clave(clave, correo)
    if err:
        return err
    if clave != repetida:
        return "Las dos contraseñas no coinciden."
    return None


def registrar(bd: Path, correo: str, nombre: str, clave: str,
              armario: str | None = None, apellidos: str = "") -> tuple[bool, str]:
    """Da de alta una cuenta.

    `armario = 'propio'` marca la cuenta a la que se importa el armario del
    autor (ver `nucleo.asegurar_importacion`). Solo la primera cuenta que se
    crea la lleva; las demás empiezan vacías. No hay ninguna credencial escrita
    en el código: la cuenta inicial se crea registrándose como cualquier otra.
    """
    cx = _conexion(bd)
    try:
        sal = os.urandom(_SAL)
        cx.execute(
            "INSERT INTO usuarios (correo, nombre, sal, clave, armario, creado, apellidos)"
            " VALUES (?,?,?,?,?,?,?)",
            (correo.strip().lower(), " ".join(nombre.split()), sal, _derivar(clave, sal),
             armario, datetime.now(timezone.utc).isoformat(timespec="seconds"),
             " ".join(apellidos.split()) or None))
        cx.commit()
        return True, "Cuenta creada."
    except sqlite3.IntegrityError:
        return False, "Ya existe una cuenta con ese correo."
    finally:
        cx.close()


def acceder(bd: Path, correo: str, clave: str) -> dict | None:
    """Devuelve los datos del usuario, o None si las credenciales no valen.

    Un correo inexistente y una contraseña incorrecta devuelven lo mismo, y a
    propósito: distinguirlos permite averiguar qué correos están registrados.
    Con el correo bloqueado (espera_bloqueo > 0) no se comprueba nada.
    """
    if espera_bloqueo(correo):
        return None
    cx = _conexion(bd)
    try:
        fila = cx.execute(
            "SELECT id, correo, nombre, sal, clave, armario FROM usuarios"
            " WHERE correo = ?", (correo.strip().lower(),)).fetchone()
    finally:
        cx.close()
    if fila is None:
        # Se deriva igualmente sobre una sal falsa para que el tiempo de
        # respuesta no revele si el correo existe.
        _derivar(clave, b"\x00" * _SAL)
        _apuntar(correo, False)
        return None
    idu, cor, nom, sal, esperado, armario = fila
    if not hmac.compare_digest(_derivar(clave, sal), esperado):
        _apuntar(correo, False)
        return None
    _apuntar(correo, True)
    return {"id": idu, "correo": cor, "nombre": nom, "armario": armario}


def cuantos(bd: Path) -> int:
    cx = _conexion(bd)
    try:
        return cx.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
    finally:
        cx.close()


# ---------------------------------------------------------------------------
# Cuenta
# ---------------------------------------------------------------------------

def datos(bd: Path, idu: int) -> dict | None:
    """Datos visibles de una cuenta. Nunca devuelve la sal ni el hash."""
    cx = _conexion(bd)
    try:
        fila = cx.execute(
            "SELECT id, correo, nombre, armario, creado, altura_cm, apellidos, foto"
            " FROM usuarios WHERE id = ?", (idu,)).fetchone()
    finally:
        cx.close()
    if fila is None:
        return None
    return dict(zip(("id", "correo", "nombre", "armario", "creado", "altura_cm",
                     "apellidos", "foto"), fila))


def guardar_altura(bd: Path, idu: int, altura_cm: int | None) -> tuple[bool, str]:
    """Altura en cm, o None para borrarla."""
    if altura_cm is not None and not 120 <= int(altura_cm) <= 230:
        return False, "Pon la altura en centímetros, entre 120 y 230."
    cx = _conexion(bd)
    try:
        cx.execute("UPDATE usuarios SET altura_cm = ? WHERE id = ?",
                   (None if altura_cm is None else int(altura_cm), idu))
        cx.commit()
    finally:
        cx.close()
    return True, "Altura guardada." if altura_cm else "Altura borrada."


def actualizar_nombre(bd: Path, idu: int, nombre: str) -> tuple[bool, str]:
    nombre = nombre.strip()
    if not nombre:
        return False, "El nombre no puede quedar vacío."
    if len(nombre) > 80:
        return False, "Ese nombre es demasiado largo."
    cx = _conexion(bd)
    try:
        cx.execute("UPDATE usuarios SET nombre = ? WHERE id = ?", (nombre, idu))
        cx.commit()
    finally:
        cx.close()
    return True, "Nombre actualizado."


def cambiar_clave(bd: Path, idu: int, actual: str, nueva: str,
                  repetida: str) -> tuple[bool, str]:
    """Cambia la contraseña exigiendo la actual.

    Pedir la actual no es burocracia: sin ello, cualquiera que encontrara una
    sesión abierta podría cambiar la contraseña y quedarse con la cuenta.

    La contraseña nueva lleva una sal NUEVA. Reutilizar la anterior no rompe
    nada hoy, pero es una mala costumbre: la sal está para que cada derivación
    sea única, incluida la de la misma cuenta a lo largo del tiempo.
    """
    err = validar_clave(nueva)
    if err:
        return False, err
    if nueva != repetida:
        return False, "Las dos contraseñas nuevas no coinciden."
    cx = _conexion(bd)
    try:
        fila = cx.execute("SELECT sal, clave FROM usuarios WHERE id = ?",
                          (idu,)).fetchone()
        if fila is None:
            return False, "No se encuentra la cuenta."
        sal, esperado = fila
        if not hmac.compare_digest(_derivar(actual, sal), esperado):
            return False, "La contraseña actual no es correcta."
        if hmac.compare_digest(_derivar(nueva, sal), esperado):
            return False, "La nueva contraseña es igual que la actual."
        sal_nueva = os.urandom(_SAL)
        cx.execute("UPDATE usuarios SET sal = ?, clave = ? WHERE id = ?",
                   (sal_nueva, _derivar(nueva, sal_nueva), idu))
        cx.commit()
    finally:
        cx.close()
    return True, "Contraseña cambiada."


def actualizar_perfil(bd: Path, idu: int, nombre: str, apellidos: str) -> tuple[bool, str]:
    """Nombre (obligatorio) y apellidos (opcionales), con las mismas reglas
    que al registrarse."""
    err = (_texto_nombre(nombre, "nombre", MAX_NOMBRE, True)
           or _texto_nombre(apellidos, "apellido", MAX_APELLIDOS, False))
    if err:
        return False, err
    cx = _conexion(bd)
    try:
        cx.execute("UPDATE usuarios SET nombre = ?, apellidos = ? WHERE id = ?",
                   (" ".join(nombre.split()), " ".join(apellidos.split()) or None, idu))
        cx.commit()
    finally:
        cx.close()
    return True, "Datos guardados."


MAX_FOTO = 8 * 1024 * 1024


def guardar_foto(bd: Path, datos: Path, idu: int, contenido: bytes) -> tuple[bool, str]:
    """Foto de perfil: se abre con PIL (si no es una imagen, no se guarda), se
    endereza por EXIF, se recorta al cuadrado del centro, se reduce a 400 px y
    se recodifica en JPEG SIN metadatos (ni GPS ni modelo de móvil). Queda en
    data/usuarios/<id>/perfil_<huella>.jpg, que no sube al repositorio. La
    huella en el nombre hace que una foto nueva nunca salga de la caché de la
    anterior (nucleo.dato_uri cachea por ruta)."""
    from io import BytesIO
    from PIL import Image, ImageOps, UnidentifiedImageError
    if len(contenido) > MAX_FOTO:
        return False, "La foto pesa demasiado: como mucho 8 MB."
    try:
        im = Image.open(BytesIO(contenido))
        im = ImageOps.exif_transpose(im).convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError):
        return False, "Eso no parece una imagen."
    if min(im.size) < 64:
        return False, "La foto es demasiado pequeña."
    im = ImageOps.fit(im, (400, 400), method=Image.LANCZOS, centering=(0.5, 0.4))
    buf = BytesIO()
    im.save(buf, "JPEG", quality=88)
    carpeta = Path(datos) / f"usuarios/{int(idu)}"
    carpeta.mkdir(parents=True, exist_ok=True)
    for vieja in carpeta.glob("perfil_*.jpg"):
        vieja.unlink(missing_ok=True)
    rel = f"usuarios/{int(idu)}/perfil_{hashlib.sha1(buf.getvalue()).hexdigest()[:8]}.jpg"
    (Path(datos) / rel).write_bytes(buf.getvalue())
    cx = _conexion(bd)
    try:
        cx.execute("UPDATE usuarios SET foto = ? WHERE id = ?", (rel, idu))
        cx.commit()
    finally:
        cx.close()
    return True, "Foto de perfil guardada."


def quitar_foto(bd: Path, datos: Path, idu: int) -> tuple[bool, str]:
    cx = _conexion(bd)
    try:
        cx.execute("UPDATE usuarios SET foto = NULL WHERE id = ?", (idu,))
        cx.commit()
    finally:
        cx.close()
    for vieja in (Path(datos) / f"usuarios/{int(idu)}").glob("perfil_*.jpg"):
        vieja.unlink(missing_ok=True)
    return True, "Foto quitada."
