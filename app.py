"""
Asistente de Estilo — aplicación.

Este fichero es solo el enrutador: configura la página, inyecta el sistema
visual, dibuja la barra superior y ejecuta la pantalla activa. Todo lo demás
vive en `paginas/`:

    paginas/estilo.py   el sistema visual, y de dónde sale cada regla
    paginas/nucleo.py   rutas, carga de datos, proyección y rejilla
    paginas/cupula.py   el héroe de la portada: los embeddings reales
    paginas/auth.py     registro y acceso (scrypt + SQLite)
    paginas/armario.py  las prendas de cada usuario (SQLite)
    paginas/vistas.py   las pantallas informativas, acceso y búsqueda
    paginas/pantalla_armario.py   Mi armario: ver, añadir y quitar prendas

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

import pathlib

import streamlit as st

_ICONO = pathlib.Path(__file__).parent / "paginas/marca/logo_burdeos_icono.png"
st.set_page_config(page_title="Akin", layout="wide",
                   page_icon=str(_ICONO) if _ICONO.exists() else None,
                   initial_sidebar_state="collapsed")

import streamlit.components.v1 as componentes  # noqa: E402
from paginas import pantalla_armario, vistas    # noqa: E402
from paginas.entrada import GUION               # noqa: E402
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
P_ARMARIO = st.Page(pantalla_armario.mi_armario, title="Mi armario",
                    url_path="armario")

# Las vistas necesitan las páginas para `st.switch_page`, y las páginas
# necesitan las funciones de las vistas. Se rompe el ciclo inyectándolas aquí.
vistas.PAGINAS.update({"inicio": P_INICIO, "sistema": P_SISTEMA,
                       "resultados": P_RESULT, "futuro": P_FUTURO,
                       "proyecto": P_SOBRE, "acceso": P_ACCESO,
                       "buscar": P_BUSCAR, "armario": P_ARMARIO})

pg = st.navigation([P_INICIO, P_SISTEMA, P_RESULT, P_FUTURO, P_SOBRE,
                    P_ACCESO, P_BUSCAR, P_ARMARIO], position="hidden")

# ---- barra superior -------------------------------------------------------
# Dos grupos, como en las tiendas de referencia: en el centro, las páginas que
# explican el proyecto; a la derecha, lo que es TUYO (buscar, tu armario, tu
# cuenta). Las dos de la aplicación solo aparecen con sesión iniciada: sin
# cuenta no hay armario en el que buscar.
u = usuario()
marca, nav, acc = st.columns([1.3, 4.3, 2.4], vertical_alignment="center")
with marca:
    st.markdown(f'<div class="marca">{logotipo()}</div>',
                unsafe_allow_html=True)
with nav:
    cols = st.columns(5)
    for col, pagina in zip(cols, [P_INICIO, P_SISTEMA, P_RESULT, P_FUTURO,
                                  P_SOBRE]):
        with col:
            st.page_link(pagina, label=pagina.title)
with acc:
    # Icono de persona, como en las tres tiendas de referencia. `st.page_link`
    # acepta iconos de Material Symbols con la sintaxis :material/<nombre>:.
    if u:
        c_bus, c_arm, c_cta = st.columns([1, 1.25, 1.05])
        with c_bus:
            st.page_link(P_BUSCAR, label="Buscar")
        with c_arm:
            st.page_link(P_ARMARIO, label="Mi armario")
    else:
        _, c_cta = st.columns([2.3, 1.05])
    with c_cta:
        st.page_link(P_ACCESO,
                     label=u["nombre"].split()[0] if u else "Acceder",
                     icon=":material/person:")

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

# La entrada de los elementos al aparecer en pantalla. Va al final, cuando el
# contenido de la pagina ya esta en el DOM. Ver paginas/entrada.py: si el
# iframe no alcanza al documento padre, no pasa nada y la pagina se ve entera.
componentes.html(GUION, height=0)
