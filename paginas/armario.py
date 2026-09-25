"""
El armario de cada usuario: prendas, fotos y vectores.

Esto es lo que convierte la demo en una aplicación de verdad para varios
usuarios. Antes solo existía un armario, el del autor, leído de ficheros. Ahora
cada cuenta tiene el suyo en la base de datos, y la búsqueda lee siempre el del
usuario que ha entrado. El del autor es uno más: se importa una vez a su cuenta
y a partir de ahí pasa por el mismo código que cualquier otro.

Modelo de datos
---------------
Sigue la tabla `garments` de la entrega 3, con los nombres en castellano como
el resto de la base (`usuarios`):

    prendas              una fila por prenda, con su vector CLIP
    categorias_propias   categorías que crea el usuario («Otra…»)
    importaciones        qué armarios preexistentes se han importado ya

Por qué SQLite y no PostgreSQL + pgvector
----------------------------------------
La entrega 3 propone pgvector, y sigue siendo el camino si esto creciera. Aquí
no aporta nada medible: la búsqueda es EXACTA sobre las prendas de un solo
usuario, que son del orden de cien. Multiplicar una matriz 100×512 por un
vector cuesta microsegundos; un índice aproximado solo tiene sentido con
cientos de miles de filas, y además cambia resultados exactos por aproximados.
SQLite va en la biblioteca estándar y no obliga a levantar un servidor para la
defensa. El esquema es portable: la columna `embedding` pasaría a `vector(512)`.

Qué se guarda de cada foto, y qué no
------------------------------------
La foto se abre, se endereza según la orientación que guarda el móvil, se
reduce a 1600 px de lado como mucho y se vuelve a codificar en JPEG. Al
recodificar se pierden los metadatos EXIF, incluida la ubicación GPS que muchos
móviles escriben en cada foto: no hay ninguna razón para guardarla.

El vector se calcula sobre ESA foto ya normalizada, no sobre la original. Así,
si algún día hay que recalcular los vectores, se parte exactamente de la misma
imagen que se usó.

No hay entrenamiento
--------------------
Añadir una prenda es una pasada por CLIP congelado: nada se reentrena. Las
cabezas de proyección se aplican en el momento de buscar, sobre este vector.
Por eso la pantalla no tiene un botón de «entrenar»: sería mentira.

Por qué este módulo no importa Streamlit ni torch
-------------------------------------------------
Es la capa de datos, y quien la llama le pasa la función que vectoriza. Así se
puede probar con una base temporal y un vector falso, sin cargar el modelo.
"""

from __future__ import annotations

import io
import json
import sqlite3
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image, ImageOps

DIM = 512
MODELO = "openai/clip-vit-base-patch32"
POSICIONES = ("arriba", "abajo", "encima")
LADO_MAX = 1600       # px; de sobra para CLIP (224) y para verla en pantalla
LADO_MIN = 224        # por debajo, CLIP estaría ampliando la foto
ORIGEN_TFM = "armario_tfm"

DETALLES = ("talla", "color", "corte", "tejido", "notas")


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clave_categoria(nombre: str) -> str:
    """Nombre normalizado: minúsculas y sin tildes.

    «Pantalón», «pantalon» y « PANTALÓN » son la misma categoría. Sin esto, un
    usuario que escribe «Pantalón» en «Otra…» crearía un duplicado de la
    predefinida `pantalon`.
    """
    s = unicodedata.normalize("NFKD", str(nombre or "").strip().lower())
    return " ".join("".join(c for c in s if not unicodedata.combining(c)).split())


def _conexion(bd: Path) -> sqlite3.Connection:
    bd.parent.mkdir(parents=True, exist_ok=True)
    cx = sqlite3.connect(bd)
    cx.execute("PRAGMA foreign_keys = ON")
    cx.executescript(f"""
        CREATE TABLE IF NOT EXISTS prendas (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id  INTEGER NOT NULL REFERENCES usuarios(id),
            categoria   TEXT    NOT NULL,
            posicion    TEXT    NOT NULL
                        CHECK (posicion IN ('arriba', 'abajo', 'encima')),
            foto        TEXT    NOT NULL,   -- relativa a data/
            foto_b      TEXT,               -- segunda toma, si la hay
            talla TEXT, color TEXT, corte TEXT, tejido TEXT, notas TEXT,
            embedding   BLOB    NOT NULL,   -- float32 x {DIM}, sin proyectar
            modelo      TEXT    NOT NULL,   -- quién produjo el vector
            origen      TEXT    NOT NULL DEFAULT 'subida',
            ref         TEXT,               -- id externo (w_0000) si se importó
            creado      TEXT    NOT NULL
        );
        CREATE INDEX IF NOT EXISTS prendas_usuario ON prendas(usuario_id);

        CREATE TABLE IF NOT EXISTS categorias_propias (
            usuario_id  INTEGER NOT NULL REFERENCES usuarios(id),
            nombre      TEXT    NOT NULL,
            posicion    TEXT    NOT NULL
                        CHECK (posicion IN ('arriba', 'abajo', 'encima')),
            PRIMARY KEY (usuario_id, nombre)
        );

        CREATE TABLE IF NOT EXISTS importaciones (
            usuario_id  INTEGER NOT NULL REFERENCES usuarios(id),
            origen      TEXT    NOT NULL,
            n           INTEGER NOT NULL,
            fecha       TEXT    NOT NULL,
            PRIMARY KEY (usuario_id, origen)
        );

        -- Outfits valorados y su valoración (Entrega 3, §4.4-4.6). Se guarda
        -- un outfit cuando el usuario lo valora: es lo que hace falta para
        -- medir algún día si las reglas aciertan. `clave` identifica el mismo
        -- conjunto con el mismo estilo, para que valorar dos veces actualice.
        CREATE TABLE IF NOT EXISTS outfits (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id  INTEGER NOT NULL REFERENCES usuarios(id),
            clave       TEXT    NOT NULL,
            estilo      TEXT,
            color       TEXT,
            puntos      REAL,
            wada        INTEGER,
            restricciones TEXT,             -- JSON: lo que se pidió
            creado      TEXT    NOT NULL,
            UNIQUE (usuario_id, clave)
        );
        CREATE TABLE IF NOT EXISTS outfit_items (
            outfit_id   INTEGER NOT NULL REFERENCES outfits(id) ON DELETE CASCADE,
            prenda_id   INTEGER NOT NULL REFERENCES prendas(id) ON DELETE CASCADE,
            posicion    TEXT    NOT NULL,
            PRIMARY KEY (outfit_id, posicion)
        );
        CREATE TABLE IF NOT EXISTS feedback (
            outfit_id   INTEGER NOT NULL REFERENCES outfits(id) ON DELETE CASCADE,
            usuario_id  INTEGER NOT NULL REFERENCES usuarios(id),
            rating      INTEGER NOT NULL CHECK (rating IN (-1, 1)),
            creado      TEXT    NOT NULL,
            PRIMARY KEY (outfit_id, usuario_id)
        );
    """)
    # Columnas añadidas después (23/09): el color leído en los píxeles. Una
    # base creada antes no las tiene; ALTER TABLE las añade sin tocar nada.
    cols = {f[1] for f in cx.execute("PRAGMA table_info(prendas)")}
    for c, tipo in (("color_l", "REAL"), ("color_a", "REAL"),
                    ("color_b", "REAL"), ("color_version", "TEXT"),
                    # Etiquetas de Gemini (JSON de una pieza), ver
                    # paginas/etiquetas.py. NULL = sin etiquetar.
                    ("etiquetas", "TEXT")):
        if c not in cols:
            cx.execute(f"ALTER TABLE prendas ADD COLUMN {c} {tipo}")
    cx.commit()
    return cx


# ---------------------------------------------------------------------------
# Foto
# ---------------------------------------------------------------------------

def preparar_foto(datos: bytes) -> bytes:
    """Foto subida -> JPEG enderezado, reducido y sin metadatos.

    Lanza ValueError con un mensaje para el usuario si la foto no vale.
    """
    try:
        im = Image.open(io.BytesIO(datos))
        im.load()
    except Exception:
        raise ValueError("No se puede leer esa imagen. Prueba con un JPG o PNG.")
    # El móvil suele guardar la foto de lado y apuntar en el EXIF cómo girarla.
    # Sin esto, una camiseta vertical se guarda tumbada.
    im = ImageOps.exif_transpose(im).convert("RGB")
    if min(im.size) < LADO_MIN:
        raise ValueError(f"La foto es demasiado pequeña ({im.width}×{im.height} "
                         f"px). Hace falta al menos {LADO_MIN} px de lado.")
    if max(im.size) > LADO_MAX:
        im.thumbnail((LADO_MAX, LADO_MAX), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=90, optimize=True)   # sin exif=
    return buf.getvalue()


def _vector_valido(v) -> np.ndarray:
    v = np.asarray(v, dtype=np.float32).reshape(-1)
    if v.shape != (DIM,) or not np.all(np.isfinite(v)):
        raise ValueError("El modelo devolvió un vector inválido para esta foto.")
    return v


# ---------------------------------------------------------------------------
# Escritura
# ---------------------------------------------------------------------------

def anadir(bd: Path, datos_dir: Path, usuario_id: int, categoria: str,
           posicion: str, foto: bytes, vectorizar: Callable[[bytes], object],
           detalles: dict | None = None, etiquetas: dict | None = None) -> int:
    """Guarda una prenda nueva y devuelve su id.

    Orden deliberado: primero el vector, luego el fichero, luego la fila. Si
    CLIP falla no queda ninguna foto huérfana en disco; si falla la base, se
    borra la foto que se acababa de escribir.
    """
    cat = clave_categoria(categoria)
    if not cat:
        raise ValueError("Elige qué tipo de prenda es.")
    if len(cat) > 40:
        raise ValueError("Ese nombre de categoría es demasiado largo.")
    if posicion not in POSICIONES:
        raise ValueError("Elige dónde va la prenda: arriba, abajo o encima.")

    jpeg = preparar_foto(foto)
    v = _vector_valido(vectorizar(jpeg))
    from paginas import color
    lab = color.color_de_bytes(jpeg)

    rel = Path("usuarios") / str(int(usuario_id)) / f"{uuid.uuid4().hex}.jpg"
    destino = datos_dir / rel
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(jpeg)

    d = {k: (str((detalles or {}).get(k) or "").strip()[:80] or None)
         for k in DETALLES}
    cx = _conexion(bd)
    try:
        cur = cx.execute(
            "INSERT INTO prendas (usuario_id, categoria, posicion, foto,"
            " talla, color, corte, tejido, notas, embedding, modelo, origen,"
            " creado, color_l, color_a, color_b, color_version, etiquetas)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (int(usuario_id), cat, posicion, rel.as_posix(), d["talla"],
             d["color"], d["corte"], d["tejido"], d["notas"], v.tobytes(),
             MODELO, "subida", _ahora(), *map(float, lab), color.VERSION,
             json.dumps(etiquetas, ensure_ascii=False) if etiquetas else None))
        cx.commit()
        return int(cur.lastrowid)
    except Exception:
        destino.unlink(missing_ok=True)
        raise
    finally:
        cx.close()


def borrar(bd: Path, datos_dir: Path, usuario_id: int, prenda_id: int) -> bool:
    """Quita una prenda del armario. Solo si es de ese usuario.

    La condición `usuario_id = ?` no es redundante: es lo que impide que una
    sesión borre prendas de otra cuenta con solo cambiar un id.

    La foto se borra únicamente si la subió el usuario. Las importadas son el
    conjunto de test del trabajo y viven fuera de su carpeta: quitarlas del
    armario no toca el fichero original.
    """
    cx = _conexion(bd)
    try:
        fila = cx.execute("SELECT foto, origen FROM prendas WHERE id = ?"
                          " AND usuario_id = ?",
                          (int(prenda_id), int(usuario_id))).fetchone()
        if fila is None:
            return False
        cx.execute("DELETE FROM prendas WHERE id = ? AND usuario_id = ?",
                   (int(prenda_id), int(usuario_id)))
        cx.commit()
    finally:
        cx.close()
    foto, origen = fila
    if origen == "subida":
        carpeta = (datos_dir / "usuarios" / str(int(usuario_id))).resolve()
        f = (datos_dir / foto).resolve()
        if carpeta in f.parents:          # nunca fuera de su carpeta
            f.unlink(missing_ok=True)
    return True


def guardar_categoria(bd: Path, usuario_id: int, nombre: str,
                      posicion: str) -> str:
    """Registra una categoría creada con «Otra…». Devuelve su clave."""
    cat = clave_categoria(nombre)
    if not cat or posicion not in POSICIONES:
        raise ValueError("La categoría necesita nombre y posición.")
    cx = _conexion(bd)
    try:
        cx.execute("INSERT OR IGNORE INTO categorias_propias"
                   " (usuario_id, nombre, posicion) VALUES (?,?,?)",
                   (int(usuario_id), cat, posicion))
        cx.commit()
    finally:
        cx.close()
    return cat


# ---------------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------------

def listar(bd: Path, usuario_id: int) -> tuple[np.ndarray, list[dict]]:
    """(vectores n×512, filas) de un usuario, en el mismo orden.

    Solo devuelve vectores del modelo actual. Si algún día se cambia de
    backbone, un vector antiguo no es comparable con uno nuevo aunque tenga
    las mismas 512 dimensiones: mezclarlos daría similitudes sin sentido.
    """
    cx = _conexion(bd)
    try:
        filas = cx.execute(
            "SELECT id, categoria, posicion, foto, foto_b, talla, color, corte,"
            " tejido, notas, origen, ref, creado, color_l, color_a, color_b,"
            " etiquetas, embedding FROM prendas"
            " WHERE usuario_id = ? AND modelo = ?"
            " ORDER BY posicion, categoria, id",
            (int(usuario_id), MODELO)).fetchall()
    finally:
        cx.close()
    cols = ("id", "categoria", "posicion", "foto", "foto_b", "talla", "color",
            "corte", "tejido", "notas", "origen", "ref", "creado", "color_l",
            "color_a", "color_b", "etiquetas")
    salida = [dict(zip(cols, f[:-1])) for f in filas]
    for f in salida:
        try:
            f["etiquetas"] = json.loads(f["etiquetas"]) if f["etiquetas"] else None
        except (TypeError, ValueError):
            f["etiquetas"] = None
    if not filas:
        return np.zeros((0, DIM), dtype=np.float32), []
    V = np.stack([np.frombuffer(f[-1], dtype=np.float32) for f in filas])
    return V, salida


def rellenar_colores(bd: Path, datos_dir: Path, usuario_id: int) -> int:
    """Lee el color de las prendas que aún no lo tienen (o lo tienen de una
    versión anterior del algoritmo). Devuelve cuántas ha calculado.

    Las importadas y las subidas antes de existir el color entran por aquí la
    primera vez. Después es una consulta vacía.
    """
    from paginas import color
    cx = _conexion(bd)
    try:
        faltan = cx.execute(
            "SELECT id, foto FROM prendas WHERE usuario_id = ? AND"
            " (color_version IS NULL OR color_version != ?)",
            (int(usuario_id), color.VERSION)).fetchall()
        for pid, foto in faltan:
            try:
                lab = color.color_prenda(Image.open(datos_dir / foto))[0]
            except Exception:
                continue          # foto ilegible: se queda sin color
            cx.execute("UPDATE prendas SET color_l = ?, color_a = ?,"
                       " color_b = ?, color_version = ? WHERE id = ?",
                       (*map(float, lab), color.VERSION, pid))
        cx.commit()
        return len(faltan)
    finally:
        cx.close()


def sin_etiquetas(bd: Path, usuario_id: int) -> list[tuple[int, str]]:
    """(id, foto) de las prendas que aún no tienen etiquetas."""
    cx = _conexion(bd)
    try:
        return cx.execute("SELECT id, foto FROM prendas WHERE usuario_id = ?"
                          " AND etiquetas IS NULL ORDER BY id",
                          (int(usuario_id),)).fetchall()
    finally:
        cx.close()


def guardar_etiquetas(bd: Path, usuario_id: int, prenda_id: int,
                      etiquetas: dict) -> None:
    cx = _conexion(bd)
    try:
        cx.execute("UPDATE prendas SET etiquetas = ? WHERE id = ? AND"
                   " usuario_id = ?", (json.dumps(etiquetas, ensure_ascii=False),
                                       int(prenda_id), int(usuario_id)))
        cx.commit()
    finally:
        cx.close()


def sin_rasgos(bd: Path, usuario_id: int) -> list[tuple[int, str]]:
    """(id, foto) de las prendas con etiquetas pero sin rasgos de estilo
    (etiquetas.VERSION_RASGOS): las de antes de existir los rasgos."""
    cx = _conexion(bd)
    try:
        filas = cx.execute("SELECT id, foto, etiquetas FROM prendas WHERE usuario_id = ?"
                           " AND etiquetas IS NOT NULL ORDER BY id",
                           (int(usuario_id),)).fetchall()
    finally:
        cx.close()
    salida = []
    for pid, foto, e in filas:
        try:
            if not (json.loads(e) or {}).get("rasgos"):
                salida.append((pid, foto))
        except (TypeError, ValueError):
            continue
    return salida


def guardar_rasgos(bd: Path, usuario_id: int, prenda_id: int, rasgos: dict) -> None:
    """Añade los rasgos a las etiquetas de la prenda, sin tocar el resto."""
    cx = _conexion(bd)
    try:
        f = cx.execute("SELECT etiquetas FROM prendas WHERE id = ? AND usuario_id = ?",
                       (int(prenda_id), int(usuario_id))).fetchone()
        if not f or not f[0]:
            return
        e = json.loads(f[0])
        e["rasgos"] = rasgos
        cx.execute("UPDATE prendas SET etiquetas = ? WHERE id = ? AND usuario_id = ?",
                   (json.dumps(e, ensure_ascii=False), int(prenda_id), int(usuario_id)))
        cx.commit()
    finally:
        cx.close()


def contar(bd: Path, usuario_id: int) -> int:
    cx = _conexion(bd)
    try:
        return cx.execute("SELECT COUNT(*) FROM prendas WHERE usuario_id = ?",
                          (int(usuario_id),)).fetchone()[0]
    finally:
        cx.close()


def categorias_propias(bd: Path, usuario_id: int) -> dict[str, str]:
    cx = _conexion(bd)
    try:
        return dict(cx.execute("SELECT nombre, posicion FROM categorias_propias"
                               " WHERE usuario_id = ? ORDER BY nombre",
                               (int(usuario_id),)).fetchall())
    finally:
        cx.close()


# ---------------------------------------------------------------------------
# Importación del armario del autor
# ---------------------------------------------------------------------------

def importar(bd: Path, usuario_id: int, V: np.ndarray, filas: list[dict],
             posicion_de: Callable[[str], str | None],
             origen: str = ORIGEN_TFM) -> int:
    """Importa un armario ya vectorizado a una cuenta. UNA sola vez.

    `filas[i]` describe la prenda de `V[i]`, con las claves `ref`, `foto`
    (relativa a data/), `foto_b`, `categoria` y, opcionales, los detalles.

    Se usan los vectores YA calculados, los mismos con los que se midió todo
    el trabajo: recalcularlos aquí podría cambiar resultados en decimales
    (GPU frente a CPU) y la aplicación dejaría de ser exactamente lo medido.

    La marca va en `importaciones`, no en «¿tiene ya prendas importadas?»: si
    el usuario quita todas, no deben volver a aparecer al entrar.
    """
    if len(V) != len(filas):
        raise ValueError("Vectores y filas no casan.")
    cx = _conexion(bd)
    try:
        if cx.execute("SELECT 1 FROM importaciones WHERE usuario_id = ? AND"
                      " origen = ?", (int(usuario_id), origen)).fetchone():
            return 0
        ahora, n = _ahora(), 0
        for v, f in zip(V, filas):
            cat = clave_categoria(f.get("categoria"))
            pos = posicion_de(cat)
            if pos not in POSICIONES:
                continue          # sin posición no puede entrar en la búsqueda
            vec = _vector_valido(v)
            cx.execute(
                "INSERT INTO prendas (usuario_id, categoria, posicion, foto,"
                " foto_b, talla, color, corte, tejido, notas, embedding,"
                " modelo, origen, ref, creado)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (int(usuario_id), cat, pos, f["foto"], f.get("foto_b") or None,
                 *(str(f.get(k) or "").strip() or None for k in DETALLES),
                 vec.tobytes(), MODELO, origen, f.get("ref"), ahora))
            n += 1
        cx.execute("INSERT INTO importaciones (usuario_id, origen, n, fecha)"
                   " VALUES (?,?,?,?)", (int(usuario_id), origen, n, ahora))
        cx.commit()               # todo o nada: una sola transacción
        return n
    except Exception:
        cx.rollback()
        raise
    finally:
        cx.close()


def actualizar_categoria(bd: Path, usuario_id: int, prenda_id: int,
                         categoria: str, posicion: str) -> bool:
    """Cambia qué es una prenda propia (y por tanto dónde va). La foto y el
    vector no cambian: lo que se ve es lo mismo, solo cambia la etiqueta."""
    cat = clave_categoria(categoria)
    if not cat or posicion not in ("arriba", "abajo", "encima"):
        raise ValueError("categoría o posición no válidas")
    with _conexion(bd) as cx:
        n = cx.execute("UPDATE prendas SET categoria = ?, posicion = ?"
                       " WHERE id = ? AND usuario_id = ?",
                       (cat, posicion, prenda_id, usuario_id)).rowcount
    return n == 1


def actualizar_detalles(bd: Path, usuario_id: int, prenda_id: int,
                        detalles: dict) -> bool:
    """Cambia talla, color, corte, tejido y notas de una prenda propia. Mismo
    recorte que al añadirla: texto sin espacios de más, vacío = NULL."""
    d = {k: (str(detalles.get(k) or "").strip()[:80] or None)
         for k in ("talla", "color", "corte", "tejido", "notas")}
    with _conexion(bd) as cx:
        n = cx.execute(
            "UPDATE prendas SET talla = ?, color = ?, corte = ?, tejido = ?, notas = ?"
            " WHERE id = ? AND usuario_id = ?",
            (d["talla"], d["color"], d["corte"], d["tejido"], d["notas"],
             prenda_id, usuario_id)).rowcount
    return n == 1


# ---------------------------------------------------------------------------
# Valoraciones de outfits
# ---------------------------------------------------------------------------

def valorar_outfit(bd: Path, usuario_id: int, prendas: dict[str, int], rating: int,
                   estilo: str | None = None, color: str | None = None,
                   puntos: float | None = None, wada: int | None = None,
                   restricciones: dict | None = None) -> int:
    """Guarda (o actualiza) la valoración de un outfit: +1 me lo pondría, -1 no.

    `prendas` es {posicion: id de prenda}. Solo se aceptan prendas del propio
    usuario. Devuelve el id del outfit.
    """
    if rating not in (-1, 1):
        raise ValueError("rating es 1 o -1")
    clave = (estilo or "") + "|" + ",".join(f"{p}:{prendas[p]}" for p in sorted(prendas))
    with _conexion(bd) as cx:
        mias = {r[0] for r in cx.execute(
            f"SELECT id FROM prendas WHERE usuario_id = ? AND id IN "
            f"({','.join('?' * len(prendas))})", (usuario_id, *prendas.values()))}
        if mias != set(prendas.values()):
            raise ValueError("prendas de otro usuario")
        cx.execute(
            "INSERT INTO outfits (usuario_id, clave, estilo, color, puntos, wada,"
            " restricciones, creado) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(usuario_id, clave) DO NOTHING",
            (usuario_id, clave, estilo, color, puntos, wada,
             json.dumps(restricciones or {}, ensure_ascii=False), _ahora()))
        oid = cx.execute("SELECT id FROM outfits WHERE usuario_id = ? AND clave = ?",
                         (usuario_id, clave)).fetchone()[0]
        cx.executemany("INSERT OR IGNORE INTO outfit_items VALUES (?, ?, ?)",
                       [(oid, pid, pos) for pos, pid in prendas.items()])
        cx.execute("INSERT INTO feedback VALUES (?, ?, ?, ?) ON CONFLICT(outfit_id,"
                   " usuario_id) DO UPDATE SET rating = excluded.rating,"
                   " creado = excluded.creado", (oid, usuario_id, rating, _ahora()))
    return oid


def valoraciones(bd: Path, usuario_id: int) -> dict[str, int]:
    """{clave del outfit: rating} de un usuario."""
    with _conexion(bd) as cx:
        return {k: r for k, r in cx.execute(
            "SELECT o.clave, f.rating FROM outfits o JOIN feedback f ON f.outfit_id = o.id"
            " WHERE f.usuario_id = ?", (usuario_id,))}
