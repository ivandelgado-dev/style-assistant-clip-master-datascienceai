"""
Demo funcional del asistente de estilo.

Qué hace
--------
Subes una imagen de referencia y ordena TUS prendas por proximidad, usando el
mismo backbone congelado y las mismas cabezas entrenadas que se evaluaron en
`docs/resultados_modelado.md`. No hay nada simulado: los vectores son los que
salen de `src/embeddings_clip.py` y las proyecciones son los checkpoints de
`experiments/`.

Qué NO hace, y es deliberado
----------------------------
1. **No aplica los umbrales de banda calibrados sobre catálogo.** Existen
   (`experiments/calibracion_bandas/bandas_conjunta_val.yaml`) pero se midieron
   sobre imágenes de DeepFashion. Las fotos del armario son otro dominio y la
   escala de similitudes no tiene por qué coincidir: usar aquí aquellos
   umbrales sería presentar como calibrado algo que no se ha comprobado en
   estas fotos. La barra que se muestra es proximidad relativa dentro de los
   resultados, y se dice.

2. **No decide conjuntos.** La compatibilidad entre prendas no está
   implementada.

3. **No opina sobre si la prenda favorece.** No hay modelo de adecuación
   corporal, por decisión de diseño desde la entrega 1.

Por qué no necesita etiquetas
-----------------------------
Ordenar por parecido solo requiere las fotos y sus vectores. Las etiquetas de
`armario.csv` hacen falta para MEDIR si el orden es correcto, no para
producirlo. Si el CSV está relleno, la ficha de cada prenda muestra su
categoría; si no, muestra el nombre del fichero y todo lo demás funciona igual.

Uso
---
    pip install streamlit
    python src/embeddings_clip.py --carpeta data/raw/wardrobe/img --out data/embeddings_armario
    python -m streamlit run app.py
"""

from __future__ import annotations

import pathlib
import sys

import numpy as np
import pandas as pd
import streamlit as st
import torch
from PIL import Image

RAIZ = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ / "src"))

FOTOS = RAIZ / "data/raw/wardrobe/img"
EMB = RAIZ / "data/embeddings_armario"
PARES = RAIZ / "data/raw/wardrobe/pares.csv"
ETIQUETAS = RAIZ / "data/raw/wardrobe/armario.csv"
MODELO = "openai/clip-vit-base-patch32"

# Nombre visible -> checkpoint. "Parecido general" es la proyección conjunta,
# que fue la que mejor ordenó en la evaluación; las otras tres son las cabezas
# por atributo. El baseline sin proyección se añade aparte, como comparación.
DIMENSIONES = {
    "Parecido general": RAIZ / "experiments/conjunta/cabeza_conjunta.pt",
    "Corte":            RAIZ / "experiments/por_atributo/cabeza_forma.pt",
    "Textura":          RAIZ / "experiments/por_atributo/cabeza_textura.pt",
    "Tejido":           RAIZ / "experiments/por_atributo/cabeza_tejido.pt",
}

ESTILO = """
<style>
  :root{
    --base:#F7F3EC; --plate:#EFEAE0; --plate2:#E3DACB; --line:#DED3C3;
    --burdeos:#7B2D40; --ink:#1C1B1A; --muted:#5A5651; --faint:#756E66;
  }
  .stApp{background:var(--base);}
  html, body, [class*="css"]{font-family:Helvetica,Arial,sans-serif;color:var(--ink);}
  #MainMenu, footer, header{visibility:hidden;}
  .marca{font-size:13px;letter-spacing:.8px;text-transform:uppercase;
         border-bottom:1px solid var(--ink);padding-bottom:10px;margin-bottom:22px;}
  .rot{font-size:11px;letter-spacing:.4px;text-transform:uppercase;color:var(--faint);
       margin:0;}
  .rot-f{font-size:11px;letter-spacing:.4px;text-transform:uppercase;color:var(--ink);
         font-weight:700;margin:0;}
  .nom{font-size:12px;letter-spacing:.4px;text-transform:uppercase;margin:6px 0 2px 0;
       white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
  .cuerpo{font-size:12px;line-height:18px;color:var(--muted);}
  .pista{height:3px;background:var(--plate2);margin-top:6px;}
  .barra{height:3px;background:var(--burdeos);}
  /* Sin sombras, sin radios: el sistema visual de la entrega 5. */
  div[data-testid="stImage"] img{border-radius:0;}
  section[data-testid="stSidebar"]{background:var(--base);
                                   border-right:1px solid var(--line);}
</style>
"""


# ---------------------------------------------------------------------------
# Carga (cacheada: el modelo y los vectores se leen una vez por sesión)
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


@st.cache_data(show_spinner=False)
def cargar_armario():
    """Vectores del armario, una foto por prenda, con etiqueta si la hay."""
    npy, idx = EMB / "embeddings.npy", EMB / "embeddings_index.parquet"
    if not npy.exists():
        trozos_v, trozos_r = [], []
        for f in sorted(EMB.glob("idx_*.parquet")):
            n = int(f.stem.split("_")[1])
            if (EMB / f"emb_{n:05d}.npy").exists():
                trozos_v.append(np.load(EMB / f"emb_{n:05d}.npy"))
                trozos_r += pd.read_parquet(f)["image_path"].tolist()
        if not trozos_v:
            return None, None
        V, rutas = np.concatenate(trozos_v), trozos_r
    else:
        V = np.load(npy)
        rutas = pd.read_parquet(idx)["image_path"].tolist()

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


def normalizar(x: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(x, axis=-1, keepdims=True)
    return x / np.where(n == 0, 1, n)


def encajar(im: Image.Image, obj: float = 3 / 2) -> Image.Image:
    """Encaja la foto en una proporcion comun SIN cortar la prenda.

    El sistema visual de la entrega 5 usa 2:3 vertical, que es lo que hacen las
    tiendas: sus fotos son de una persona de pie. Las del armario son prendas
    estiradas y salieron HORIZONTALES. Recortar a 2:3 partia por la mitad un
    pantalon colocado a lo largo — se veia en la prueba de recorte.

    Asi que se rellena en vez de recortar: la foto entera, centrada sobre el
    beige de fondo. La rejilla mantiene una proporcion uniforme y ninguna
    prenda pierde una pernera.
    """
    w, h = im.size
    if w / h > obj:
        W, H = w, int(w / obj)
    else:
        W, H = int(h * obj), h
    lienzo = Image.new("RGB", (W, H), (239, 234, 224))   # var(--plate)
    lienzo.paste(im, ((W - w) // 2, (H - h) // 2))
    return lienzo


# ---------------------------------------------------------------------------

st.set_page_config(page_title="Asistente de Estilo", layout="wide",
                   initial_sidebar_state="expanded")
st.markdown(ESTILO, unsafe_allow_html=True)
st.markdown('<div class="marca">Asistente de Estilo</div>', unsafe_allow_html=True)

V, arm = cargar_armario()
if V is None:
    st.markdown(
        '<p class="cuerpo">No hay embeddings del armario. Lánzalo una vez:<br><br>'
        '<code>python src/embeddings_clip.py --carpeta data/raw/wardrobe/img '
        '--out data/embeddings_armario</code></p>', unsafe_allow_html=True)
    st.stop()

with st.sidebar:
    st.markdown('<p class="rot-f">Comparar por</p>', unsafe_allow_html=True)
    dim = st.radio("dim", list(DIMENSIONES), label_visibility="collapsed")
    st.markdown('<p class="rot-f" style="margin-top:18px;">Resultados</p>',
                unsafe_allow_html=True)
    k = st.slider("k", 4, 24, 8, label_visibility="collapsed")
    crudo = st.checkbox("Comparar con CLIP sin proyección")
    st.markdown(
        f'<p class="rot" style="margin-top:22px;">{len(arm)} prendas · '
        f'{"etiquetadas" if "categoria" in arm.columns else "sin etiquetar"}</p>',
        unsafe_allow_html=True)

subida = st.file_uploader("Imagen de referencia", type=["jpg", "jpeg", "png", "webp"])
if subida is None:
    st.markdown('<p class="cuerpo">Sube una foto de referencia y el sistema '
                'ordena tus prendas por proximidad.</p>', unsafe_allow_html=True)
    st.stop()

proc, modelo, extraer = cargar_clip()
ref = Image.open(subida).convert("RGB")
with torch.no_grad():
    px = proc(images=ref, return_tensors="pt")["pixel_values"]
    v_ref = extraer(modelo.get_image_features(pixel_values=px)).numpy()

def proyectar(x: np.ndarray, ruta: pathlib.Path | None) -> np.ndarray:
    if ruta is None:
        return normalizar(x)
    cab = cargar_cabeza(str(ruta), x.shape[1])
    with torch.no_grad():
        return cab(torch.from_numpy(np.ascontiguousarray(x))).numpy()

V_arm = V[arm["pos"].to_numpy()]

def ranking(ruta):
    z_arm = proyectar(V_arm, ruta)
    z_ref = proyectar(v_ref, ruta)[0]
    return z_arm @ z_ref

ruta = DIMENSIONES[dim] if DIMENSIONES[dim].exists() else None
if ruta is None:
    st.markdown(f'<p class="rot">Sin checkpoint para «{dim}»: se usa CLIP sin '
                f'proyección.</p>', unsafe_allow_html=True)
sim = ranking(ruta)
orden = np.argsort(-sim)[:k]

izq, der = st.columns([1, 4], gap="large")
with izq:
    st.markdown('<p class="rot">Referencia</p>', unsafe_allow_html=True)
    st.image(encajar(ref), use_container_width=True)
    st.markdown(f'<p class="rot" style="margin-top:8px;">{len(arm)} prendas '
                f'comparadas</p>', unsafe_allow_html=True)

with der:
    st.markdown(f'<p class="rot-f">Más próximas · {dim}</p>', unsafe_allow_html=True)
    # La barra es proximidad RELATIVA dentro de estos resultados: el mejor llena
    # la barra. No es una probabilidad ni una banda calibrada — ver el pie.
    lo, hi = float(sim[orden].min()), float(sim[orden].max())
    rango = max(hi - lo, 1e-6)
    for fila in range(0, len(orden), 4):
        for col, i in zip(st.columns(4, gap="small"), orden[fila:fila + 4]):
            r = arm.iloc[int(i)]
            with col:
                try:
                    st.image(encajar(Image.open(FOTOS / r["fichero"]).convert("RGB")),
                             use_container_width=True)
                except Exception:
                    st.markdown('<p class="rot">foto ilegible</p>', unsafe_allow_html=True)
                cat = str(r.get("categoria", "") or "").strip()
                st.markdown(f'<p class="nom">{cat or pathlib.Path(r["fichero"]).stem}</p>'
                            f'<p class="rot">{r["prenda_id"]} · {sim[i]:.3f}</p>'
                            f'<div class="pista"><div class="barra" '
                            f'style="width:{100*(sim[i]-lo)/rango:.0f}%"></div></div>',
                            unsafe_allow_html=True)

    if crudo:
        sim2 = ranking(None)
        o2 = np.argsort(-sim2)[:k]
        coincide = len(set(orden.tolist()) & set(o2.tolist()))
        st.markdown(
            f'<p class="rot-f" style="margin-top:26px;">CLIP sin proyección</p>'
            f'<p class="cuerpo">Comparten {coincide} de {k} resultados con la '
            f'proyección entrenada. Las diferencias son lo que aporta la '
            f'proyección supervisada.</p>', unsafe_allow_html=True)
        for fila in range(0, len(o2), 4):
            for col, i in zip(st.columns(4, gap="small"), o2[fila:fila + 4]):
                r = arm.iloc[int(i)]
                with col:
                    try:
                        st.image(encajar(Image.open(FOTOS / r["fichero"]).convert("RGB")),
                                 use_container_width=True)
                    except Exception:
                        pass
                    st.markdown(f'<p class="rot">{r["prenda_id"]} · {sim2[i]:.3f}</p>',
                                unsafe_allow_html=True)

st.markdown('<hr style="border:none;border-top:1px solid var(--line);margin:30px 0 18px 0;">',
            unsafe_allow_html=True)
c1, c2, c3 = st.columns(3, gap="large")
with c1:
    st.markdown('<p class="rot-f">Cómo se ha ordenado</p>'
                '<p class="cuerpo">CLIP ViT-B/32 congelado más una proyección '
                'supervisada de 128 dimensiones, entrenada sobre DeepFashion. '
                'El orden es por similitud coseno. Ningún LLM interviene.</p>',
                unsafe_allow_html=True)
with c2:
    st.markdown('<p class="rot-f">La barra no es una probabilidad</p>'
                '<p class="cuerpo">Indica proximidad relativa dentro de estos '
                'resultados. Las bandas calibradas (26 de cada 100 en la banda '
                'alta) se midieron sobre fotografía de catálogo, no sobre estas '
                'fotos, así que aquí no se aplican.</p>', unsafe_allow_html=True)
with c3:
    st.markdown('<p class="rot-f">Limitación conocida</p>'
                '<p class="cuerpo">El modelo se entrenó con fotografía de '
                'catálogo sobre cuerpo. Estas fotos son prendas planas de móvil. '
                'La magnitud de esa caída es lo que mide el análisis de '
                '<i>domain gap</i>.</p>', unsafe_allow_html=True)
