"""
Comprobacion previa de la escritura en parquet.

Por que existe
--------------
En este equipo (Windows con una directiva de Control de aplicaciones) la PRIMERA
carga de una DLL desconocida se bloquea mientras el sistema consulta reputacion,
y a la segunda ya pasa. Cuando eso le toca a pyarrow durante el arranque de
pandas, pandas se traga el ImportError, marca sus banderas de version como si
pyarrow no estuviera, y mas tarde —cuando pyarrow SI importa— ejecuta su codigo
de compatibilidad para pyarrow < 14 contra un pyarrow 25. El sintoma es:

    pyarrow.lib.ArrowKeyError: No type extension with name
    arrow.py_extension_type found

Lo caro no es el fallo, es CUANDO falla: al volcar el primer fragmento, despues
del computo. Con 236 imagenes son segundos; con 155.369 fueron cuatro minutos de
GPU tirados. Esta comprobacion lo mueve al principio: si la ruta de parquet no
funciona, se sabe en el segundo uno.

No arregla el entorno ni parchea pandas. Solo falla pronto y explica por que.
"""

from __future__ import annotations

import tempfile
import pathlib


def comprobar_parquet() -> None:
    """Escribe y lee un parquet de dos filas. Lanza SystemExit si no puede."""
    import pandas as pd

    try:
        import pyarrow  # noqa: F401
    except Exception as e:
        raise SystemExit(
            f"No se puede importar pyarrow: {e}\n"
            f"Si es un bloqueo de Control de aplicaciones de Windows, relanza el "
            f"comando una vez: la segunda carga suele pasar."
        )

    from pandas.compat.pyarrow import pa_version_under14p1
    if pa_version_under14p1 and getattr(pyarrow, "__version__", "0") >= "14":
        raise SystemExit(
            f"pandas cree que pyarrow es anterior a 14.0.1, pero el instalado es "
            f"{pyarrow.__version__}. Eso pasa cuando el import de pyarrow fallo "
            f"durante el arranque de pandas (tipicamente, DLL bloqueada la primera "
            f"vez). RELANZA EL COMANDO: casi siempre va a la segunda."
        )

    with tempfile.TemporaryDirectory() as tmp:
        f = pathlib.Path(tmp) / "prueba.parquet"
        try:
            pd.DataFrame({"a": [1, 2]}).to_parquet(f)
            assert len(pd.read_parquet(f)) == 2
        except Exception as e:
            raise SystemExit(
                f"La escritura en parquet no funciona en este entorno: "
                f"{type(e).__name__}: {e}\n"
                f"Relanza el comando una vez antes de investigar nada."
            )
