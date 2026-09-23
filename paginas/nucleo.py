"""
Núcleo compartido de la demo: rutas, carga de datos, proyección y rejilla.

Todo lo que toca modelo o datos vive aquí, y las pantallas de `paginas/` solo
componen. Así la capa visual se puede reescribir sin rozar nada evaluable.
"""

from __future__ import annotations

import base64
import html as _html
import io
import pathlib
import sys

import numpy as np
import pandas as pd
import streamlit as st
import torch
from PIL import Image

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

DATOS = RAIZ / "data"
FOTOS = DATOS / "raw/wardrobe/img"
EMB = RAIZ / "data/embeddings_armario"
PARES = RAIZ / "data/raw/wardrobe/pares.csv"
ETIQUETAS = RAIZ / "data/raw/wardrobe/armario.csv"
BD_USUARIOS = RAIZ / "data/usuarios.db"
MODELO = "openai/clip-vit-base-patch32"

DIMENSIONES = {
    "Parecido general": RAIZ / "experiments/conjunta/cabeza_conjunta.pt",
    "Corte":            RAIZ / "experiments/por_atributo/cabeza_forma.pt",
    "Textura":          RAIZ / "experiments/por_atributo/cabeza_textura.pt",
    "Tejido":           RAIZ / "experiments/por_atributo/cabeza_tejido.pt",
}

# Cifras de la portada. Ninguna se escribe a mano aquí sin estar medida y
# trazable al documento que la respalda.
CIFRAS = [
    # OJO: el mismo redondeo que en la página de Resultados. Antes la portada
    # decía +0,022 y Resultados +0,0217. Es el mismo número, y verlo escrito
    # de dos formas se lee como descuido, no como estilo.
    ("+0,0217", "NDCG@10 de la proyección supervisada sobre CLIP plano, en "
                "atributos vistos. Significativo por bootstrap.",
     "resultados_modelado.md"),
    ("26 / 100", "Aciertos en la banda de mayor proximidad, frente a 7 de cada "
                 "100 sin ordenar. En atributos no vistos, 24.",
     "resultados_calibracion.md"),
    ("1,000", "AUC separando fotografía de catálogo de fotografía de móvil. "
              "El nulo por composición está en 0,57–0,64.",
     "resultados_domain_gap.md"),
    # No es un resultado, es el tamaño del conjunto. Va en la banda porque
    # da la escala con la que leer los otros tres.
    ("118", "Prendas propias fotografiadas, dos tomas cada una, como test "
            "fuera de distribución. No se usaron para entrenar.",
     "protocolo_armario.md"),
]


# ---------------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner="Cargando CLIP…")
def cargar_clip():
    from transformers import AutoImageProcessor, CLIPModel
    from embeddings_clip import extraer_vector
    proc = AutoImageProcessor.from_pretrained(MODELO)
    modelo = CLIPModel.from_pretrained(MODELO).eval()
    for q in modelo.parameters():
        q.requires_grad_(False)
    return proc, modelo, extraer_vector


@st.cache_resource(show_spinner=False)
def cargar_cabeza(ruta_str: str, dim_in: int):
    from entrenar_proyecciones import Proyeccion
    ck = torch.load(ruta_str, map_location="cpu", weights_only=False)
    m = Proyeccion(dim_in, ck["dim"], mlp=ck["mlp"]).eval()
    m.load_state_dict(ck["state_dict"])
    return m


def leer_indice(ruta):
    """Lee un índice de embeddings, prefiriendo el CSV gemelo si existe.

    Motivo: en el portátil de desarrollo, Windows App Control bloquea la DLL
    `pyarrow._parquet`. `import pyarrow` pasa, pero leer parquet revienta. El
    índice es una sola columna de rutas, así que un CSV al lado sirve igual y
    elimina esa dependencia binaria de la capa de presentación. El parquet
    sigue siendo el formato canónico que escribe `src/embeddings_clip.py`.

        python -c "import pandas as pd; pd.read_parquet('X.parquet').to_csv('X.csv', index=False)"
    """
    csv = ruta.with_suffix(".csv")
    if csv.exists():
        return pd.read_csv(csv, encoding="utf-8")
    return pd.read_parquet(ruta)


@st.cache_data(show_spinner=False)
def cargar_armario():
    """Vectores del armario, una sola toma por prenda, con etiqueta si la hay."""
    npy, idx = EMB / "embeddings.npy", EMB / "embeddings_index.parquet"
    if not npy.exists():
        trozos_v, trozos_r = [], []
        for f in sorted(EMB.glob("idx_*.parquet")):
            n = int(f.stem.split("_")[1])
            if (EMB / f"emb_{n:05d}.npy").exists():
                trozos_v.append(np.load(EMB / f"emb_{n:05d}.npy"))
                trozos_r += leer_indice(f)["image_path"].tolist()
        if not trozos_v:
            return None, None
        V, rutas = np.concatenate(trozos_v), trozos_r
    else:
        V = np.load(npy)
        rutas = leer_indice(idx)["image_path"].tolist()

    d = pd.DataFrame({"fichero": rutas, "pos": range(len(rutas))})

    # Una sola toma por prenda. Sin esto saldrían dos resultados casi idénticos
    # de la misma camisa ocupando los dos primeros puestos.
    if PARES.exists():
        p = pd.read_csv(PARES, encoding="utf-8-sig", dtype=str)
        p["fichero"] = p["fichero"].str.replace("\\", "/", regex=False)
        d["fichero"] = d["fichero"].str.replace("\\", "/", regex=False)
        d = d.merge(p[["fichero", "prenda_id", "toma"]], on="fichero", how="left")
        d = d[d["toma"].fillna("a") == "a"].reset_index(drop=True)
    else:
        d["prenda_id"] = d["fichero"]

    if ETIQUETAS.exists():
        e = pd.read_csv(ETIQUETAS, encoding="utf-8-sig", dtype=str,
                        keep_default_na=False)
        e = e.rename(columns={"item_id": "prenda_id"}).drop(
            columns=["fichero"], errors="ignore")
        d = d.merge(e, on="prenda_id", how="left")

    return V.astype(np.float32), d


@st.cache_data(show_spinner=False)
def cargar_segundas_tomas() -> dict:
    """prenda_id -> fichero de la toma B, para el cambio al pasar el cursor.

    Va aparte de `cargar_armario` a propósito: aquella descarta la toma B
    porque para rankear sobra, y esa función no se toca.
    """
    if not PARES.exists():
        return {}
    p = pd.read_csv(PARES, encoding="utf-8-sig", dtype=str)
    p["fichero"] = p["fichero"].str.replace("\\", "/", regex=False)
    b = p[p["toma"].fillna("a") != "a"].drop_duplicates("prenda_id")
    return dict(zip(b["prenda_id"], b["fichero"]))


EMB_CATALOGO = RAIZ / "data/embeddings"


@st.cache_data(show_spinner=False)
def muestra_catalogo(n: int = 6000, semilla: int = 7):
    """Muestra fija del corpus de catálogo, solo para AJUSTAR la base PCA.

    No se dibuja: define el sistema de coordenadas del espacio general, para
    que el armario se sitúe dentro de él en vez de definir su propio eje. Se
    lee con `mmap_mode` para no traer 304 MB a memoria.
    """
    npy = EMB_CATALOGO / "embeddings.npy"
    if not npy.exists():
        return None
    M = np.load(npy, mmap_mode="r")
    idx = np.sort(np.random.default_rng(semilla).choice(
        M.shape[0], size=min(n, M.shape[0]), replace=False))
    return np.asarray(M[idx], dtype=np.float32)


@st.cache_data(show_spinner=False)
def nube_para_cupula(V: np.ndarray | None, n_malla: int = 1400):
    """Retículo del héroe y qué posiciones se rellenan.

    El retículo es uniforme por construcción (Fibonacci) y siempre el mismo.
    Lo que cambia al iniciar sesión es cuántas posiciones se rellenan y
    cuáles: cada prenda DEL USUARIO que ha entrado toma la posición más
    próxima a su vector real proyectado, así que el patrón de relleno es
    dato, no adorno. Sin sesión, o con el armario vacío, no se rellena nada.

    La caché va por el contenido de `V`: al añadir o quitar una prenda cambia
    la matriz y la cúpula se recalcula sola.
    """
    from paginas.cupula import (asignar, orientar, proyectar_a_esfera,
                                reticulo)
    malla = reticulo(n_malla)
    if V is None or len(V) == 0:
        return malla.tolist(), [], 0.0
    P, explicada = proyectar_a_esfera(V, referencia=muestra_catalogo())
    # Sin esto, el armario cae en la mitad de la esfera que la cúpula no
    # muestra y no se rellena ni una posición. Ver `orientar`.
    return malla.tolist(), asignar(malla, orientar(P)), explicada


# ---------------------------------------------------------------------------
# Cálculo
# ---------------------------------------------------------------------------

def normalizar(x: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(x, axis=-1, keepdims=True)
    return x / np.where(n == 0, 1, n)


def proyectar(x: np.ndarray, ruta) -> np.ndarray:
    if ruta is None:
        return normalizar(x)
    cab = cargar_cabeza(str(ruta), x.shape[1])
    with torch.no_grad():
        return cab(torch.from_numpy(np.ascontiguousarray(x))).numpy()


def encajar(im: Image.Image, obj: float = 3 / 2) -> Image.Image:
    """Encaja la foto en una proporción común SIN cortar la prenda.

    Las fotos de tienda son verticales porque retratan a una persona de pie;
    las del armario son prendas estiradas y salieron horizontales. Recortar
    partía por la mitad un pantalón colocado a lo largo — se vio en la prueba
    de recorte. Así que se rellena en vez de recortar.
    """
    w, h = im.size
    W, H = (w, int(w / obj)) if w / h > obj else (int(h * obj), h)
    lienzo = Image.new("RGB", (W, H), (239, 234, 224))
    lienzo.paste(im, ((W - w) // 2, (H - h) // 2))
    return lienzo


@st.cache_data(show_spinner=False, max_entries=1024)
def dato_uri(rel: str, ancho: int = 560, rellenar: bool = True) -> str:
    """Foto incrustada en base64. `rel` es relativa a `data/`.

    Relativa a `data/` y no a la carpeta del armario del autor porque ahora
    hay dos sitios: las fotos importadas siguen en `raw/wardrobe/img/` y las
    subidas van a `usuarios/<id>/`. La fila de la base guarda cuál.

    `draft` le pide al decodificador JPEG que lea la foto ya reducida (1/2,
    1/4 o 1/8). Una foto de móvil de 12 Mpx pasa de ~100 ms a ~15 ms, que es
    lo que hace que un armario de cien prendas se pinte sin esperar.
    """
    try:
        im = Image.open(DATOS / rel)
        im.draft("RGB", (ancho * 2, ancho * 2))
        im = im.convert("RGB")
    except Exception:
        return ""
    if rellenar:
        im = encajar(im)
        if im.width > ancho:
            im = im.resize((ancho, int(im.height * ancho / im.width)),
                           Image.LANCZOS)
    else:
        # Sin relleno: cabe en un cuadrado de `ancho` de lado y el marco
        # la centra con object-fit:contain. Un pantalón vertical ya no se
        # queda diminuto dentro de un marco apaisado.
        im.thumbnail((ancho, ancho), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=82, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def ficha(r, puesto: int, s: float, ancho_barra: float, segundas: dict,
          ver_sim: bool = True) -> str:
    # ver_sim=False oculta la cifra exacta. En este armario todo cae en un
    # margen minúsculo (se midió), y tres decimales en la vista principal
    # aparentan una precisión que no hay. Queda en el modo evaluación.
    a = dato_uri(r["fichero"])
    rel_b = segundas.get(str(r.get("prenda_id", "")), "")
    b = dato_uri(rel_b) if rel_b else a
    cat = str(r.get("categoria", "") or "").strip()
    desc = str(r.get("descripcion_libre", "") or "").strip()
    nombre = cat or pathlib.Path(r["fichero"]).stem
    pid = str(r.get("prenda_id", "") or "")
    if not a:
        return ('<div class="ficha"><div class="marco"></div>'
                '<p class="sub">foto ilegible</p></div>')
    # Sin líneas en blanco ni sangría: ver `busqueda.compactar`.
    return "".join(linea.strip() for linea in f"""
    <div class="ficha">
      <div class="marco">
        <span class="puesto">{puesto:02d}</span>
        <img class="a" src="{a}" alt=""><img class="b" src="{b}" alt="">
      </div>
      <div class="pie">
        <p class="nom">{_html.escape(nombre)}</p>
        <p class="sub">{_html.escape(pid)}{f' · {s:.3f}' if ver_sim else ''}</p>
        <div class="medidor"><div class="barra" style="width:{ancho_barra:.0f}%"></div></div>
        <p class="desc">{_html.escape(desc)}</p>
      </div>
    </div>""".splitlines())


def rejilla(indices, arm, sim, segundas, densa: bool = False) -> str:
    lo, hi = float(sim[indices].min()), float(sim[indices].max())
    rango = max(hi - lo, 1e-6)
    fichas = "".join(
        ficha(arm.iloc[int(i)], n + 1, float(sim[i]),
              100 * (sim[i] - lo) / rango, segundas)
        for n, i in enumerate(indices))
    return f'<div class="{"rejilla densa" if densa else "rejilla"}">{fichas}</div>'


# ---------------------------------------------------------------------------
# Sesión
# ---------------------------------------------------------------------------

def usuario():
    return st.session_state.get("usuario")


def detalle_texto(f: dict) -> str:
    """Talla · color · corte · tejido · notas, lo que haya."""
    return " · ".join(str(f[k]).strip() for k in
                      ("talla", "color", "corte", "tejido", "notas")
                      if f.get(k) and str(f[k]).strip())


def armario_usuario(usuario_id: int):
    """(vectores, tabla) del armario de un usuario, en el mismo orden.

    La tabla lleva las columnas que esperan `ficha` y `busqueda.html_pieza`
    (`fichero`, `prenda_id`, `categoria`, `descripcion_libre`), así que la
    búsqueda no distingue una prenda importada de una subida.

    Sin caché a propósito: son unos cientos de filas de SQLite, milisegundos,
    y así una prenda recién añadida aparece sin tener que invalidar nada.
    """
    from paginas import armario
    armario.rellenar_colores(BD_USUARIOS, DATOS, usuario_id)
    rellenar_etiquetas_desde_cache(usuario_id)
    V, filas = armario.listar(BD_USUARIOS, usuario_id)
    d = pd.DataFrame(filas, columns=[
        "id", "categoria", "posicion", "foto", "foto_b", "talla", "color",
        "corte", "tejido", "notas", "origen", "ref", "creado", "color_l",
        "color_a", "color_b", "etiquetas"])
    d["fichero"] = d["foto"]
    d["fichero_b"] = d["foto_b"].fillna("")
    d["prenda_id"] = [r if r else f"#{i}" for r, i in zip(d["ref"], d["id"])]
    d["descripcion_libre"] = [detalle_texto(f) for f in filas]
    return V, d


_INTENTADAS: set = set()


def rellenar_etiquetas_desde_cache(usuario_id: int) -> int:
    """Pone etiquetas a las prendas que ya se etiquetaron antes (misma foto).
    Sin llamar a la API: solo mira la caché. Devuelve cuántas ha puesto."""
    from paginas import armario, etiquetas
    # Leer cada foto para sacar su huella es caro (MB por foto). Solo se
    # intenta si la caché ha cambiado desde la última vez para este usuario.
    try:
        marca = (usuario_id, etiquetas.CACHE.stat().st_mtime)
    except OSError:
        return 0
    if marca in _INTENTADAS:
        return 0
    _INTENTADAS.add(marca)
    n = 0
    for pid, foto in armario.sin_etiquetas(BD_USUARIOS, usuario_id):
        try:
            e = etiquetas.desde_cache((DATOS / foto).read_bytes())
        except OSError:
            continue
        if e and e.get("piezas"):
            armario.guardar_etiquetas(BD_USUARIOS, usuario_id, pid, e["piezas"][0])
            n += 1
    return n


def segundas_de(d: pd.DataFrame) -> dict:
    """prenda_id -> foto de la segunda toma, para el cambio al pasar el cursor."""
    return {p: b for p, b in zip(d["prenda_id"], d["fichero_b"]) if b}


def asegurar_importacion(u: dict) -> int:
    """Lleva el armario del autor a su cuenta la primera vez. Idempotente.

    Solo lo hace la cuenta marcada con `armario = 'propio'` (la primera que se
    registró, ver `auth.registrar`). Usa los vectores ya calculados por
    `src/embeddings_clip.py`: los mismos con los que se midió el trabajo.
    """
    if not u or u.get("armario") != "propio":
        return 0
    from paginas import armario
    from paginas.busqueda import posicion_de
    V, arm = cargar_armario()
    if V is None:
        return 0
    segundas = cargar_segundas_tomas()
    filas = []
    for _, r in arm.iterrows():
        b = segundas.get(str(r.get("prenda_id", "")), "")
        filas.append({
            "ref": str(r.get("prenda_id", "") or "") or None,
            "foto": "raw/wardrobe/img/" + r["fichero"],
            "foto_b": ("raw/wardrobe/img/" + b) if b else None,
            "categoria": r.get("categoria", ""),
            "color": r.get("color_base", ""),
            "corte": r.get("corte", ""),
            "tejido": r.get("tejido", ""),
            # La descripción libre del protocolo («camisa manga corta»,
            # «sudadera sin capucha») es justo lo que distingue dos prendas
            # de la misma categoría. Va a notas.
            "notas": r.get("descripcion_libre", ""),
        })
    return armario.importar(BD_USUARIOS, u["id"], V[arm["pos"].to_numpy()],
                            filas, posicion_de)


def exige_sesion(destino) -> bool:
    """Muestra el aviso y devuelve False si no hay nadie dentro."""
    if usuario():
        return True
    st.markdown('<div style="padding:70px 0 0 0;max-width:560px;">'
                '<p class="titular">Necesitas una cuenta</p>'
                '<p class="cuerpo" style="margin-top:12px;">La búsqueda trabaja '
                'sobre el armario de un usuario concreto, así que hay que '
                'entrar primero.</p></div>', unsafe_allow_html=True)
    c, _ = st.columns([1, 4])
    with c:
        st.markdown('<div style="height:22px;"></div>', unsafe_allow_html=True)
        if st.button("Ir a acceder", type="primary", use_container_width=True):
            st.switch_page(destino)
    return False
