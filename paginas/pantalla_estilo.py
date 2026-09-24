"""
Buscar → «Por estilo»: outfits con tu ropa según un estilo y, si quieres, un
color. La lógica está en `paginas/outfits.py`; aquí solo la pantalla.

Qué hace cada parte y quién decide:
- Eliges estilo, color, si llevas algo encima y si te limitas al Diccionario
  de Wada. O lo pides con tus palabras y la IA lo traduce a esas mismas
  opciones, que ves marcadas y puedes cambiar.
- Las reglas eligen y ordenan los outfits. La IA no elige ninguno.
- «Me lo pondría / No me convence» se guarda (tablas outfits, outfit_items,
  feedback): es lo que permitiría medir después si las reglas aciertan.
"""

from __future__ import annotations

import html as _html

import streamlit as st

from paginas import armario, auth, busqueda, outfits
from paginas.nucleo import BD_USUARIOS, dato_uri

NOMBRE_COLOR = {k: k.capitalize() for k in outfits.COLORES_PEDIDO}


def _aplicar_pendiente():
    """Lo que la IA ha entendido de la petición se aplica ANTES de pintar los
    controles: Streamlit no deja cambiar el valor de un control ya pintado."""
    pend = st.session_state.pop("est_pendiente", None)
    if not pend:
        return
    if "estilo" in pend:
        st.session_state["est_estilo"] = pend["estilo"]
        st.session_state["est_ultimo"] = pend["estilo"]
        if "encima" not in pend:
            st.session_state["est_encima"] = (
                outfits.ESTILOS[pend["estilo"]]["capa"] == "recomendado")
    if "color" in pend:
        st.session_state["est_color"] = pend["color"]
    if "encima" in pend:
        st.session_state["est_encima"] = pend["encima"]


def _tarjeta(o: dict, k: int, estilo: str, prendas: list[dict], arm) -> str:
    pos = [p for p in ("arriba", "encima", "abajo") if p in o["prendas"]]
    celdas = []
    for p in pos:
        r = arm.iloc[prendas[o["prendas"][p]]["i"]]
        uri = dato_uri(r["fichero"], ancho=300, rellenar=False)
        celdas.append(f'<div class="{p}"><img src="{uri}" alt=""></div>')
    desc = " · ".join(
        f'{busqueda.nombre(prendas[o["prendas"][p]]["tipo"]).lower()}'
        + (f' {prendas[o["prendas"][p]]["color"]}' if prendas[o["prendas"][p]]["color"] else "")
        for p in pos)
    wada = ""
    if o["wada"]:
        cols, pal, _ = outfits.wada()
        muestras = "".join(f'<i style="background:{cols[j]["hex"]}" title="'
                           f'{_html.escape(cols[j]["nombre"])}"></i>' for j in pal[o["wada"]])
        wada = f'<div class="w">{muestras}<span>Wada, combinación {o["wada"]}</span></div>'
    por = " · ".join(dict.fromkeys(o["razones"]))
    return (f'<article class="lk {"tres" if len(pos) == 3 else ""}">'
            f'<span class="chip">{_html.escape(outfits.ESTILOS[estilo]["nombre"])}</span>'
            f'<span class="num">{k:02d}</span>'
            f'<div class="lienzo">{"".join(celdas)}</div>'
            f'<div class="ficha-look"><p class="t">Look {k:02d}</p>'
            f'<p class="d">{_html.escape(desc)}</p>'
            f'<p class="d" style="color:var(--faint);">{_html.escape(por)}</p>{wada}</div>'
            f'</article>')


def por_estilo(u: dict, arm, panel, res, pie):
    _aplicar_pendiente()
    prendas = outfits.prendas_de(arm)

    with panel:
        st.markdown('<div style="height:20px;"></div><p class="rot-f" '
                    'style="margin-bottom:6px;">Estilo</p>', unsafe_allow_html=True)
        estilo = st.pills("Estilo", outfits.ORDEN_ESTILOS, selection_mode="single",
                          default="casual", key="est_estilo",
                          format_func=lambda k: outfits.ESTILOS[k]["nombre"],
                          label_visibility="collapsed") or "casual"
        st.markdown(f'<p class="nota-form">{_html.escape(outfits.ESTILOS[estilo]["idea"])}</p>',
                    unsafe_allow_html=True)

        st.markdown('<div style="height:10px;"></div><p class="rot-f" '
                    'style="margin-bottom:6px;">Color (opcional)</p>', unsafe_allow_html=True)
        color = st.pills("Color", list(outfits.COLORES_PEDIDO), selection_mode="single",
                         key="est_color", format_func=NOMBRE_COLOR.get,
                         label_visibility="collapsed")

        st.markdown('<div style="height:10px;"></div>', unsafe_allow_html=True)
        # Al cambiar de estilo, «algo encima» vuelve a lo que pide el estilo
        # (Business Casual, Rocker y Grunge lo llevan; el resto, opcional).
        if st.session_state.get("est_ultimo") != estilo:
            st.session_state["est_encima"] = outfits.ESTILOS[estilo]["capa"] == "recomendado"
            st.session_state["est_ultimo"] = estilo
        encima = st.toggle("Con algo encima", key="est_encima")
        solo_wada = st.toggle("Solo paletas de Wada", key="est_wada")
        # La altura solo cuenta si el usuario la ha dado en Mi cuenta, y se
        # apaga aquí mismo. Suma a unos looks; no quita ninguno.
        altura = (auth.datos(BD_USUARIOS, u["id"]) or {}).get("altura_cm")
        usar_altura = False
        if altura:
            usar_altura = st.toggle(f"Tener en cuenta mi altura ({altura / 100:.2f} m)".replace(".", ","),
                                    value=True, key="est_altura")
            if usar_altura and altura < outfits.ALTURA_ALARGAR:
                st.markdown('<p class="nota-form">Primero, los looks con poco contraste '
                            'entre arriba y abajo: alargan la figura. Es una sugerencia; '
                            'no quita ninguno.</p>', unsafe_allow_html=True)
        st.markdown('<p class="nota-form">Sanzo Wada, <i>A Dictionary of Color '
                    'Combinations</i> (Japón, 1933): 348 combinaciones de colores. '
                    'Una prenda cuenta como un color de la paleta si se le parece '
                    'tanto como dos fotos de la misma prenda.</p>', unsafe_allow_html=True)

        # Con tus palabras: la IA lo traduce a las opciones de arriba.
        from paginas import gemini
        if gemini.disponible():
            st.markdown('<div style="height:14px;"></div><p class="rot-f" '
                        'style="margin-bottom:6px;">O pídelo con tus palabras</p>',
                        unsafe_allow_html=True)
            with st.form("est_form", clear_on_submit=False, border=False):
                texto = st.text_input("Petición", placeholder="Una cena informal, algo en azul…",
                                      label_visibility="collapsed")
                enviar = st.form_submit_button("Proponer", type="primary",
                                               use_container_width=True)
            if enviar and texto.strip():
                try:
                    r = outfits.interpretar_peticion(texto.strip())
                except gemini.ErrorGemini as e:
                    st.warning(gemini.resumen_error(e))
                    r = None
                if r and r.get("entendido"):
                    st.session_state["est_pendiente"] = r
                    st.rerun()
                elif r is not None:
                    st.info("No lo he entendido como una petición de ropa.")

    r = outfits.generar(prendas, estilo, color_pedido=color, con_encima=encima,
                        solo_wada=solo_wada, altura=altura if usar_altura else None)

    with res:
        titulo = f'{outfits.ESTILOS[estilo]["nombre"]}' + (f' en {color}' if color else "")
        st.markdown(f'<div class="filete"></div><p class="seccion" style="margin-top:16px;">'
                    f'{_html.escape(titulo)}, con tu ropa</p>', unsafe_allow_html=True)
        if r["aviso"]:
            st.markdown(f'<p class="falta">{_html.escape(r["aviso"])}</p>',
                        unsafe_allow_html=True)
        if r["outfits"]:
            tarjetas = "".join(_tarjeta(o, k + 1, estilo, prendas, arm)
                               for k, o in enumerate(r["outfits"]))
            st.markdown(busqueda.compactar(f'<div class="carrusel"><div class="riel">'
                                           f'{tarjetas}</div></div>'), unsafe_allow_html=True)
        for pos, tipos in r["faltan"]:
            nombres = ", ".join(busqueda.nombre(t).lower() for t in tipos[:3])
            st.markdown(f'<p class="falta">Para {outfits.ESTILOS[estilo]["nombre"]} te falta '
                        f'algo para <b>{busqueda.ETIQUETA[pos].lower()}</b>: {nombres}.</p>',
                        unsafe_allow_html=True)

        if r["outfits"]:
            _valorar(u, r["outfits"], estilo, color, prendas)
        st.markdown('<p class="falta" style="font-size:11.5px;">Cómo se eligen: '
                    'reglas de estilista escritas en el código (qué prendas encajan '
                    'en cada estilo, cuántos colores, qué estampados) y, si cuadra, '
                    'una paleta de Wada. Mismas prendas, mismo resultado. La IA solo '
                    'traduce lo que pides con palabras; no elige el outfit.</p>',
                    unsafe_allow_html=True)
    pie()


def _valorar(u: dict, looks: list[dict], estilo: str, color, prendas: list[dict]):
    """Me lo pondría / No me convence, por número de look. Se guarda al marcar."""
    ids = {k + 1: {p: prendas[i]["id"] for p, i in o["prendas"].items()}
           for k, o in enumerate(looks)}
    claves = {k: (estilo + "|" + ",".join(f"{p}:{v[p]}" for p in sorted(v)))
              for k, v in ids.items()}
    hechas = armario.valoraciones(BD_USUARIOS, u["id"])
    si_def = [k for k in ids if hechas.get(claves[k]) == 1]
    no_def = [k for k in ids if hechas.get(claves[k]) == -1]
    firma = f"{estilo}|{color}|" + "|".join(claves.values())

    st.markdown('<div style="height:8px;"></div><p class="rot-f" style="margin-bottom:6px;">'
                '¿Te los pondrías?</p>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        si = st.pills("Me lo pondría", list(ids), selection_mode="multi", default=si_def,
                      key=f"est_si_{hash(firma)}", format_func=lambda k: f"{k:02d}")
    with c2:
        no = st.pills("No me convence", list(ids), selection_mode="multi", default=no_def,
                      key=f"est_no_{hash(firma)}", format_func=lambda k: f"{k:02d}")
    cambios = [(k, 1) for k in si if k not in si_def] + [(k, -1) for k in no if k not in no_def]
    for k, rating in cambios:
        o = looks[k - 1]
        armario.valorar_outfit(BD_USUARIOS, u["id"], ids[k], rating, estilo=estilo,
                               color=color, puntos=o["puntos"], wada=o["wada"],
                               restricciones={"estilo": estilo, "color": color})
    if cambios:
        st.toast("Guardado. Sirve para medir si las reglas aciertan.")
