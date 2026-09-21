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
2. **No hay recuperación de contraseña**, ni verificación de correo, ni
   limitación de intentos. Los tres son trabajo de producto, no de evaluación.
3. **Un usuario nuevo no tiene armario.** La digitalización de prendas no está
   implementada en el MVP: solo existe el armario del autor, usado como
   conjunto de test fuera de distribución. Un usuario recién registrado entra,
   y la pantalla de búsqueda se lo dice y le ofrece explorar con ese armario
   en modo demostración.

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
    cx.commit()
    return cx


def _derivar(clave: str, sal: bytes) -> bytes:
    return hashlib.scrypt(clave.encode("utf-8"), salt=sal,
                          n=_N, r=_R, p=_P, dklen=_DK)


def validar_registro(correo: str, nombre: str, clave: str,
                     repetida: str) -> str | None:
    """Devuelve el mensaje de error, o None si los datos son válidos."""
    if not nombre.strip():
        return "Escribe un nombre."
    if not _CORREO.match(correo.strip()):
        return "Ese correo no tiene un formato válido."
    if len(clave) < MIN_CLAVE:
        return f"La contraseña debe tener al menos {MIN_CLAVE} caracteres."
    if clave != repetida:
        return "Las dos contraseñas no coinciden."
    return None


def registrar(bd: Path, correo: str, nombre: str, clave: str,
              armario: str | None = None) -> tuple[bool, str]:
    """Da de alta una cuenta.

    `armario` asocia un armario digitalizado. En el MVP solo existe uno — el
    del autor — así que la primera cuenta que se crea se lo queda y las
    siguientes entran sin armario propio. No hay ninguna credencial escrita en
    el código: la cuenta inicial se crea registrándose como cualquier otra.
    """
    cx = _conexion(bd)
    try:
        sal = os.urandom(_SAL)
        cx.execute(
            "INSERT INTO usuarios (correo, nombre, sal, clave, armario, creado)"
            " VALUES (?,?,?,?,?,?)",
            (correo.strip().lower(), nombre.strip(), sal, _derivar(clave, sal),
             armario, datetime.now(timezone.utc).isoformat(timespec="seconds")))
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
    """
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
        return None
    idu, cor, nom, sal, esperado, armario = fila
    if not hmac.compare_digest(_derivar(clave, sal), esperado):
        return None
    return {"id": idu, "correo": cor, "nombre": nom, "armario": armario}


def cuantos(bd: Path) -> int:
    cx = _conexion(bd)
    try:
        return cx.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
    finally:
        cx.close()
