"""
Cliente mínimo de la API de Gemini, con la biblioteca estándar.

Por qué sin SDK
---------------
El SDK de Google trae dependencias binarias, y en el portátil de desarrollo
Windows App Control ya bloqueó DLL de pyarrow y de pandas. Una petición HTTP
con `urllib` no añade nada que se pueda bloquear. Lo que se usa es poco:
listar modelos y `generateContent` con una imagen y salida JSON.

La clave
--------
Se lee de la variable de entorno GEMINI_API_KEY o, si no está, del fichero
`.env` de la raíz del repositorio (excluido en .gitignore). Nunca se escribe
en ningún sitio, nunca se imprime, y va en la cabecera `x-goog-api-key`, no en
la URL: una URL acaba en logs y trazas de error.

Privacidad
----------
Lo que se manda son fotos. En el nivel gratuito de la API, Google puede usar
el contenido para mejorar sus productos. La aplicación lo dice en pantalla.
"""

from __future__ import annotations

import base64
import io
import json
import os
import pathlib
import re
import time
import urllib.error
import urllib.request

from PIL import Image

RAIZ = pathlib.Path(__file__).resolve().parents[1]
API = "https://generativelanguage.googleapis.com/v1beta"
LADO_ENVIO = 1024        # px; de sobra para describir una prenda


class ErrorGemini(RuntimeError):
    pass


class CuotaAgotada(ErrorGemini):
    """Se acabó la cuota DIARIA del modelo. No tiene sentido reintentar: cada
    intento cuenta y no va a funcionar hasta medianoche (hora del Pacífico)."""


# Cortacircuitos: tras una cuota diaria agotada, no se vuelve a llamar en
# este proceso. Antes, cada foto reintentaba cuatro veces contra una cuota
# ya gastada: minutos de espera para nada.
_AGOTADO: set = set()


def _de_env(nombre: str) -> str | None:
    v = os.environ.get(nombre)
    if v:
        return v.strip()
    env = RAIZ / ".env"
    if env.exists():
        for linea in env.read_text(encoding="utf-8").splitlines():
            if linea.strip().startswith(nombre + "="):
                return linea.split("=", 1)[1].strip().strip('"').strip("'") or None
    return None


def clave() -> str | None:
    return _de_env("GEMINI_API_KEY")


def disponible() -> bool:
    return clave() is not None


def _peticion(ruta: str, cuerpo: dict | None = None, timeout: float = 90) -> dict:
    k = clave()
    if not k:
        raise ErrorGemini("No hay GEMINI_API_KEY (ni en el entorno ni en .env).")
    datos = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
    req = urllib.request.Request(
        API + ruta, data=datos, method="POST" if datos else "GET",
        headers={"x-goog-api-key": k, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detalle = e.read().decode("utf-8", "replace")[:3000]
        raise ErrorGemini(f"HTTP {e.code}: {detalle}") from None
    except urllib.error.URLError as e:
        raise ErrorGemini(f"Sin conexión con la API: {e.reason}") from None


# ---------------------------------------------------------------------------
# Modelo
# ---------------------------------------------------------------------------

_EXCLUIR = ("image", "tts", "live", "audio", "embedding", "exp", "8b", "lite",
            "thinking", "robotics", "computer", "gemma", "nano")


def _version(nombre: str) -> tuple:
    m = re.search(r"gemini-(\d+)(?:\.(\d+))?", nombre)
    return (int(m.group(1)), int(m.group(2) or 0)) if m else (0, 0)


def elegir_modelo() -> str:
    """El «flash» estable más reciente que admita generateContent.

    Se elige al vuelo porque los nombres cambian cada pocos meses y uno
    escrito a mano caduca. Se puede fijar con GEMINI_MODELO. El nombre
    elegido se guarda con cada etiqueta: así se sabe qué modelo la produjo.
    """
    fijo = _de_env("GEMINI_MODELO")
    if fijo:
        return fijo
    r = _peticion("/models?pageSize=1000")
    cands = []
    for m in r.get("models", []):
        n = m.get("name", "").split("/")[-1]
        if ("generateContent" in m.get("supportedGenerationMethods", [])
                and "flash" in n and not any(x in n for x in _EXCLUIR)):
            cands.append(n)
    if not cands:
        raise ErrorGemini("No hay ningún modelo «flash» con generateContent.")
    estables = [n for n in cands if "preview" not in n]
    lista = estables or cands
    # Versión más alta; a igualdad, el alias sin sufijo de fecha (más corto).
    return sorted(lista, key=lambda n: (_version(n), -len(n)))[-1]


# ---------------------------------------------------------------------------
# Generación
# ---------------------------------------------------------------------------

def jpeg_para_envio(datos: bytes, lado: int = LADO_ENVIO) -> bytes:
    from PIL import ImageOps
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(datos))).convert("RGB")
    im.thumbnail((lado, lado), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


def _espera_sugerida(txt: str) -> float | None:
    """La API dice cuánto esperar ante un límite por minuto: "retryDelay": "33s"."""
    m = re.search(r'"retryDelay":\s*"(\d+(?:\.\d+)?)s"', txt)
    return float(m.group(1)) if m else None


def _es_diaria(txt: str) -> bool:
    return "PerDay" in txt or "per day" in txt.lower()


def resumen_error(e: Exception) -> str:
    """Una línea legible en vez del JSON entero."""
    t = str(e)
    if isinstance(e, CuotaAgotada):
        return "cuota diaria agotada"
    if "HTTP 429" in t:
        return "límite de peticiones por minuto"
    if "HTTP 503" in t:
        return "el modelo está saturado (503)"
    return t.splitlines()[0][:160]


def generar_json(modelo: str, instrucciones: str,
                 imagenes: bytes | list[bytes] | None,
                 esquema: dict | None = None, reintentos: int = 4,
                 lado: int = LADO_ENVIO) -> dict:
    """Una o varias imágenes + instrucciones -> un objeto JSON.

    Varias imágenes en UNA petición: la cuota gratuita cuenta peticiones, no
    imágenes. Cada imagen va precedida de «Imagen N».

    Temperatura 0: se quiere la misma respuesta ante la misma foto.
    Errores:
      - cuota diaria agotada -> CuotaAgotada, y no se vuelve a llamar a ese
        modelo en este proceso;
      - límite por minuto -> se espera lo que diga la API y se reintenta;
      - 503 (saturado) -> espera creciente y reintento;
      - 400 por el esquema -> se repite pidiendo solo JSON.
    """
    if modelo in _AGOTADO:
        raise CuotaAgotada(modelo)
    if isinstance(imagenes, (bytes, bytearray)):
        imagenes = [imagenes]
    partes = []
    for n, img in enumerate(imagenes or [], 1):
        if len(imagenes) > 1:
            partes.append({"text": f"Imagen {n}:"})
        b64 = base64.b64encode(jpeg_para_envio(img, lado)).decode("ascii")
        partes.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})
    partes.append({"text": instrucciones})
    cuerpo = {
        "contents": [{"role": "user", "parts": partes}],
        "generationConfig": {"temperature": 0,
                             "response_mime_type": "application/json"},
    }
    if esquema:
        cuerpo["generationConfig"]["response_schema"] = esquema
    espera = 5.0
    for intento in range(reintentos):
        try:
            r = _peticion(f"/models/{modelo}:generateContent", cuerpo, timeout=180)
            texto = "".join(p.get("text", "")
                            for p in r["candidates"][0]["content"]["parts"])
            return json.loads(texto)
        except ErrorGemini as e:
            txt = str(e)
            if "HTTP 400" in txt and "response_schema" in cuerpo["generationConfig"]:
                del cuerpo["generationConfig"]["response_schema"]
                continue
            if "HTTP 429" in txt and _es_diaria(txt):
                _AGOTADO.add(modelo)
                raise CuotaAgotada(modelo) from None
            if intento + 1 < reintentos and ("HTTP 429" in txt or "HTTP 5" in txt):
                time.sleep(_espera_sugerida(txt) or espera)
                espera *= 2
                continue
            raise
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            if intento + 1 < reintentos:
                continue
            raise ErrorGemini(f"Respuesta sin JSON válido: {e}") from None
    raise ErrorGemini("Sin respuesta tras los reintentos.")
