"""
Pantalla de bienvenida al entrar en la aplicación.

Qué hace, y por qué no es decoración
------------------------------------
La primera vez que se usa la aplicación hay trabajo real que hacer: leer el
armario, cargar las cuatro cabezas de proyección y, sobre todo, leer CLIP del
disco, que son varios segundos. Antes eso se veía como un spinner de Streamlit
diciendo «Cargando CLIP…» en mitad de la pantalla de búsqueda.

Esta pantalla tapa exactamente ese tiempo. Y como el modelo queda cargado
mientras se ve, al llegar a la búsqueda ya no hay ninguna espera.

Dos reglas que no se rompen
---------------------------
1. **Dura lo que dura la carga, no un temporizador inventado.** Las pantallas
   de carga que hacen esperar por nada son de lo más odiado en diseño de
   interfaces. La barra avanza por pasos REALES de carga, y el texto de debajo
   dice cuál se está haciendo.

   La única espera añadida es un suelo de 1,2 s en total, para el caso en que
   todo esté ya en memoria: sin él, la pantalla aparecería y desaparecería en
   una décima y se vería como un parpadeo. Es un mínimo, no un temporizador.

2. **Una vez por sesión.** Se marca en `st.session_state` al terminar y no
   vuelve a salir hasta que se cierre la sesión.

Cómo se hace en Streamlit
-------------------------
Con `st.empty()`: se reserva un hueco, se pinta en él la pantalla, se hace la
carga (que es bloqueante, y Streamlit ya ha enviado la pantalla al navegador),
y al terminar se vacía el hueco. Entre paso y paso se repinta con la barra
más avanzada.

La pantalla es `position:fixed` a pantalla completa, así que tapa también la
barra superior, que Streamlit ha dibujado antes.

Por qué en dos capas
--------------------
Cada `hueco.markdown(...)` crea un elemento NUEVO en el DOM, y con él todas
sus animaciones vuelven a empezar. Si fondo, texto y barra estuvieran en el
mismo hueco, cada avance de la barra reiniciaría la entrada del nombre — o la
cortaría a la mitad, si el primer paso de carga es rápido.

Así que van separadas: el fondo con el saludo y el nombre se pinta UNA vez y
su animación de entrada se completa entera; la barra y el texto de la fase
viven en una segunda capa transparente encima, que es la única que se repinta.
Las dos se centran con el mismo flex y un desplazamiento vertical opuesto, así
que quedan alineadas en cualquier tamaño de pantalla.
"""

from __future__ import annotations

import base64
import html as _html
import pathlib
import time

import streamlit as st

from paginas.nucleo import (DIMENSIONES, armario_usuario,
                            asegurar_importacion, cargar_cabeza, cargar_clip,
                            dato_uri)

_MARCA = pathlib.Path(__file__).parent / "marca" / "monograma_claro.png"
SUELO_S = 1.2          # mínimo total, para que no parpadee
CLAVE = "bienvenida_vista"


@st.cache_data(show_spinner=False)
def _monograma_b64() -> str:
    if not _MARCA.exists():
        return ""
    return base64.b64encode(_MARCA.read_bytes()).decode()


_CSS = """
<style>
  .akin-bienv{position:fixed;inset:0;z-index:100000;background:#1C1B1A;
              display:flex;align-items:center;justify-content:center;
              overflow:hidden;}
  .akin-bienv .agua{position:absolute;left:50%;top:50%;height:74vh;
                    width:auto;transform:translate(-50%,-50%);opacity:.07;
                    pointer-events:none;user-select:none;}
  .akin-bienv .centro{position:relative;text-align:center;color:#F7F3EC;
                      padding:0 24px;transform:translateY(-34px);}
  /* Segunda capa: transparente, encima, solo con la barra y la fase. */
  .akin-barra{position:fixed;inset:0;z-index:100001;pointer-events:none;
              display:flex;align-items:center;justify-content:center;}
  .akin-barra .bloque{transform:translateY(62px);text-align:center;}
  .akin-bienv .saludo{font-size:11px;letter-spacing:2.6px;
                      text-transform:uppercase;color:rgba(247,243,236,.55);
                      margin:0;}
  .akin-bienv .nombre{font-size:66px;line-height:1.05;font-weight:400;
                      letter-spacing:-.022em;margin:16px 0 0 0;}
  .akin-barra .carga{width:240px;height:1px;margin:0 auto;
                     background:rgba(247,243,236,.16);position:relative;
                     overflow:hidden;}
  .akin-barra .carga i{position:absolute;left:0;top:0;bottom:0;
                       background:#F7F3EC;width:var(--hasta);
                       animation:akin-barra .55s cubic-bezier(.22,1,.36,1) both;}
  .akin-barra .fase{font-size:10px;letter-spacing:1.8px;text-transform:uppercase;
                    color:rgba(247,243,236,.42);margin:16px 0 0 0;
                    min-height:14px;}

  /* Entrada solo en el primer pintado; los repintados no la repiten. */
  .akin-bienv.entra .agua{animation:akin-agua 1.4s cubic-bezier(.22,1,.36,1) both;}
  .akin-bienv.entra .saludo{animation:akin-sube .9s cubic-bezier(.215,.61,.355,1) .15s both;}
  .akin-bienv.entra .nombre{animation:akin-sube 1.05s cubic-bezier(.215,.61,.355,1) .28s both;}
  .akin-barra.entra .bloque{animation:akin-aparece .8s ease .55s both;}
  /* Salida: fundido de las dos capas a la vez. */
  .akin-bienv.sale, .akin-barra.sale{animation:akin-fuera .45s ease forwards;}

  @keyframes akin-barra{from{width:var(--desde);}to{width:var(--hasta);}}
  @keyframes akin-sube{from{opacity:0;transform:translateY(22px);}
                       to{opacity:1;transform:none;}}
  @keyframes akin-aparece{from{opacity:0;}to{opacity:1;}}
  @keyframes akin-agua{from{opacity:0;transform:translate(-50%,-47%) scale(.97);}
                       to{opacity:.07;transform:translate(-50%,-50%);}}
  @keyframes akin-fuera{to{opacity:0;visibility:hidden;}}

  @media (prefers-reduced-motion: reduce){
    .akin-bienv *, .akin-bienv, .akin-barra *, .akin-barra{animation:none !important;}
  }
  @media (max-width:820px){
    .akin-bienv .nombre{font-size:42px;}
    .akin-bienv .agua{height:56vh;}
  }
</style>
"""


def _fondo(nombre: str, entra: bool = False, sale: bool = False) -> str:
    """Capa 1: fondo, marca de agua, saludo y nombre. Se pinta una vez."""
    b64 = _monograma_b64()
    agua = (f'<img class="agua" src="data:image/png;base64,{b64}" alt="">'
            if b64 else "")
    clases = "akin-bienv" + (" entra" if entra else "") + (" sale" if sale else "")
    return (f'{_CSS}<div class="{clases}">{agua}<div class="centro">'
            f'<p class="saludo">Bienvenido a Akin</p>'
            f'<p class="nombre">{_html.escape(nombre)}.</p>'
            f'</div></div>')


def _barra(desde: float, hasta: float, fase: str,
           entra: bool = False, sale: bool = False) -> str:
    """Capa 2: la barra de carga y el paso en curso. Se repinta."""
    clases = "akin-barra" + (" entra" if entra else "") + (" sale" if sale else "")
    return (f'<div class="{clases}"><div class="bloque">'
            f'<div class="carga" style="--desde:{desde*100:.0f}%;'
            f'--hasta:{hasta*100:.0f}%;"><i></i></div>'
            f'<p class="fase">{_html.escape(fase)}</p>'
            f'</div></div>')


def mostrar_si_toca(usuario: dict) -> None:
    """Enseña la bienvenida una vez por sesión, mientras se carga todo."""
    if st.session_state.get(CLAVE):
        return

    nombre = (usuario.get("nombre") or "").split()[0] or "de nuevo"
    capa_fondo = st.empty()
    capa_barra = st.empty()
    t0 = time.monotonic()

    # Pasos REALES de carga. La barra avanza al terminar cada uno, no por
    # tiempo. CLIP va el último porque es el pesado: la barra se queda en dos
    # tercios mientras lo lee, que es exactamente lo que está pasando.
    def armario():
        # La primera vez de la cuenta del autor, esto importa sus 118 prendas.
        # Después, lee las prendas del usuario y deja sus miniaturas en caché,
        # que es lo que tarda al abrir Mi armario por primera vez.
        from paginas.pantalla_armario import MINIATURA
        asegurar_importacion(usuario)
        _, arm = armario_usuario(usuario["id"])
        for rel in arm["fichero"]:
            dato_uri(rel, ancho=MINIATURA)

    def cabezas():
        # 512: la dimensión de CLIP ViT-B/32, la entrada de las cabezas.
        for ruta in DIMENSIONES.values():
            if ruta.exists():
                cargar_cabeza(str(ruta), 512)

    pasos = [
        ("Leyendo tu armario", armario),
        ("Preparando las proyecciones", cabezas),
        ("Cargando el modelo de visión", cargar_clip),
    ]

    capa_fondo.markdown(_fondo(nombre, entra=True), unsafe_allow_html=True)
    capa_barra.markdown(_barra(0.0, 0.0, pasos[0][0], entra=True),
                        unsafe_allow_html=True)

    avance = 0.0
    for i, (fase, paso) in enumerate(pasos):
        if i > 0:
            capa_barra.markdown(_barra(avance, avance, fase),
                                unsafe_allow_html=True)
        try:
            paso()
        except Exception:
            # La bienvenida no puede ser lo que rompa la aplicación: si un
            # paso falla, la pantalla de búsqueda lo mostrará con su propio
            # mensaje al intentarlo de nuevo.
            pass
        nuevo = (i + 1) / len(pasos)
        capa_barra.markdown(_barra(avance, nuevo, fase),
                            unsafe_allow_html=True)
        avance = nuevo

    resto = SUELO_S - (time.monotonic() - t0)
    if resto > 0:
        time.sleep(resto)

    capa_fondo.markdown(_fondo(nombre, sale=True), unsafe_allow_html=True)
    capa_barra.markdown(_barra(1.0, 1.0, "Listo", sale=True),
                        unsafe_allow_html=True)
    time.sleep(0.45)
    capa_barra.empty()
    capa_fondo.empty()
    st.session_state[CLAVE] = True
