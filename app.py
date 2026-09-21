"""
Asistente de Estilo — aplicación.

Este fichero es solo el enrutador: configura la página, inyecta el sistema
visual, dibuja la barra superior y ejecuta la pantalla activa. Todo lo demás
vive en `paginas/`:

    paginas/estilo.py   el sistema visual, y de dónde sale cada regla
    paginas/nucleo.py   rutas, carga de datos, proyección y rejilla
    paginas/cupula.py   el héroe de la portada: los embeddings reales
    paginas/auth.py     registro y acceso (scrypt + SQLite)
    paginas/vistas.py   las siete pantallas

Por qué la navegación se dibuja a mano
--------------------------------------
`st.navigation(position="hidden")` apaga la navegación propia de Streamlit, y
la barra se compone con `st.page_link`. Es más trabajo que dejar la del
sidebar, pero permite marcar la pestaña activa con PESO tipográfico en vez de
con color, que es la regla que salió de medir Zara, Pull&Bear y Bershka.

Arranque
--------
    python -m streamlit run app.py

Desde CMD, no desde Git Bash: el emulador de terminal de MINGW le da EOF a
Streamlit en la entrada estándar nada más arrancar, y Streamlit lo interpreta
como una petición de parada y se apaga solo.
"""

from __future__ import annotations

import html as _html
import pathlib

import streamlit as st

_ICONO = pathlib.Path(__file__).parent / "paginas/marca/logo_burdeos_icono.png"
st.set_page_config(page_title="Akin", layout="wide",
                   page_icon=str(_ICONO) if _ICONO.exists() else None,
                   initial_sidebar_state="collapsed")

from paginas import vistas                      # noqa: E402
from paginas.estilo import CSS                  # noqa: E402
from paginas.nucleo import usuario              # noqa: E402

st.markdown(CSS, unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def logotipo() -> str:
    """El logotipo de la barra, incrustado en base64.

    Va incrustado y no por `st.image` para poder controlar su alto exacto
    junto al resto de la barra. Si el fichero no estuviera, cae al nombre en
    texto y la aplicacion sigue funcionando.
    """
    import base64
    f = pathlib.Path(__file__).parent / "paginas/marca/logo_burdeos_texto.png"
    if not f.exists():
        return '<span style="font-size:15px;letter-spacing:2px;">AKIN</span>'
    b64 = base64.b64encode(f.read_bytes()).decode()
    return f'<img src="data:image/png;base64,{b64}" alt="Akin">' 

P_INICIO = st.Page(vistas.inicio, title="Inicio", url_path="inicio", default=True)
P_SISTEMA = st.Page(vistas.sistema, title="El sistema", url_path="sistema")
P_RESULT = st.Page(vistas.resultados, title="Resultados", url_path="resultados")
P_FUTURO = st.Page(vistas.futuro, title="Futuro", url_path="futuro")
P_SOBRE = st.Page(vistas.sobre, title="El proyecto", url_path="proyecto")
P_ACCESO = st.Page(vistas.acceso, title="Acceso", url_path="acceso")
P_BUSCAR = st.Page(vistas.buscar, title="Buscar", url_path="buscar")

# Las vistas necesitan las páginas para `st.switch_page`, y las páginas
# necesitan las funciones de las vistas. Se rompe el ciclo inyectándolas aquí.
vistas.PAGINAS.update({"inicio": P_INICIO, "sistema": P_SISTEMA,
                       "resultados": P_RESULT, "futuro": P_FUTURO,
                       "proyecto": P_SOBRE, "acceso": P_ACCESO,
                       "buscar": P_BUSCAR})

pg = st.navigation([P_INICIO, P_SISTEMA, P_RESULT, P_FUTURO, P_SOBRE,
                    P_ACCESO, P_BUSCAR], position="hidden")

# ---- barra superior -------------------------------------------------------
marca, nav, acc = st.columns([1.4, 5.0, 1.4], vertical_alignment="center")
with marca:
    st.markdown(f'<div class="marca">{logotipo()}</div>',
                unsafe_allow_html=True)
with nav:
    # Seis columnas IGUALES. Antes la ultima era 1.6 y empujaba los enlaces
    # hacia la izquierda, dejando un hueco muerto antes del boton.
    cols = st.columns(6)
    for col, pagina in zip(cols, [P_INICIO, P_SISTEMA, P_RESULT, P_FUTURO,
                                  P_SOBRE, P_BUSCAR]):
        with col:
            st.page_link(pagina, label=pagina.title)
with acc:
    u = usuario()
    if u:
        st.markdown(f'<div class="rot" style="text-align:right;">'
                    f'{_html.escape(u["nombre"])}</div>',
                    unsafe_allow_html=True)
    else:
        if st.button("Iniciar sesión", type="primary",
                     use_container_width=True):
            st.switch_page(P_ACCESO)

st.markdown('<div class="regla-fuerte"></div>', unsafe_allow_html=True)

# ---- estado activo de la navegación ---------------------------------------
# No se puede resolver solo con CSS. Streamlit 1.64 no pone `aria-current` en
# st.page_link, y el `href` vacío no marca la página ACTIVA sino la página por
# DEFECTO: en /sistema, el enlace de Inicio sigue teniendo href="". Comprobado
# sobre el DOM.
#
# Quien sí lo sabe con certeza es Python: `st.navigation` devuelve la página
# actual, y `Page.url_path` devuelve exactamente el mismo valor que acaba en el
# atributo href ("" para la página por defecto). Así que la regla se emite
# apuntando a ese href concreto en cada recarga.
st.markdown(
    f'<style>'
    f'div[data-testid="stPageLink"] a[href="{pg.url_path}"]{{'
    f'  border-bottom-color:var(--ink) !important;}}'
    f'div[data-testid="stPageLink"] a[href="{pg.url_path}"] p{{'
    f'  color:var(--ink) !important;font-weight:700 !important;}}'
    f'</style>', unsafe_allow_html=True)

pg.run()
