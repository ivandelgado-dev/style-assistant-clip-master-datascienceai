"""
¿Qué modelos de Gemini puedo usar con MI clave, con imágenes y con cuota?

Los nombres cambian cada pocos meses y los retirados dan 404; la cuota
gratuita es distinta por modelo (la familia «lite» suele tener mucha más).
AI Studio no deja ver los límites con esta cuenta, así que se prueba: una
petición por modelo, CON una imagen diminuta, pidiendo JSON. Es exactamente
lo que hace la aplicación, así que si aquí sale OK, allí funciona.

Cuesta una petición de la cuota de cada modelo probado.

Uso
---
    python src/probar_modelos_gemini.py

Después, en el .env, una línea con el elegido:
    GEMINI_MODELO=gemini-3.5-flash-lite
"""

from __future__ import annotations

import io
import pathlib
import sys

from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from paginas import gemini  # noqa: E402

# Los que funcionaron en el proyecto de IA generativa, más los que liste la API.
CONOCIDOS = ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.1-flash-lite",
             "gemini-3-flash-preview", "gemini-flash-lite-latest",
             "gemini-flash-latest"]


def main() -> int:
    if not gemini.disponible():
        print("No hay GEMINI_API_KEY en el .env")
        return 1
    try:
        r = gemini._peticion("/models?pageSize=1000")
        listados = [m["name"].split("/")[-1] for m in r.get("models", [])
                    if "generateContent" in m.get("supportedGenerationMethods", [])
                    and "flash" in m["name"]
                    and not any(x in m["name"] for x in ("image", "tts", "live", "audio"))]
    except gemini.ErrorGemini as e:
        print(f"No se pudo listar modelos: {gemini.resumen_error(e)}")
        listados = []
    candidatos = list(dict.fromkeys(CONOCIDOS + sorted(listados)))

    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (30, 30, 120)).save(buf, format="JPEG")
    img = buf.getvalue()

    print(f"{len(candidatos)} modelos. Una petición con imagen a cada uno:\n")
    ok = []
    for m in candidatos:
        try:
            res = gemini.generar_json(m, 'Di de qué color es la imagen. Devuelve '
                                         'SOLO {"color": "..."}', img, reintentos=1)
            print(f"  OK             {m:32s} -> {res}")
            ok.append(m)
        except gemini.CuotaAgotada:
            print(f"  SIN CUOTA HOY  {m}")
        except gemini.ErrorGemini as e:
            t = str(e)
            motivo = ("sin cuota" if "HTTP 429" in t else
                      "no disponible" if "HTTP 404" in t else
                      "no admite imágenes / petición rechazada" if "HTTP 400" in t else
                      "saturado, prueba luego" if "HTTP 503" in t else
                      gemini.resumen_error(e))
            print(f"  FALLA          {m:32s} ({motivo})")
    print()
    if ok:
        lite = [m for m in ok if "lite" in m]
        print("Funcionan:", ", ".join(ok))
        print("Sugerencia (la familia «lite» suele tener más cuota diaria):")
        print(f"    GEMINI_MODELO={(lite or ok)[0]}")
    else:
        print("Ninguno responde ahora. Vuelve a probar tras las 9:00 (hora de España).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
