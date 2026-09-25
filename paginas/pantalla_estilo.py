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


def _tarjeta(o: dict, k: int, estilo: str, prendas: list[dict], arm,
             ancla: int | None = None, forzado: bool = False) -> str:
    pos = [p for p in ("arriba", "encima", "abajo") if p in o["prendas"]]
    celdas = []
    for p in pos:
        r = arm.iloc[prendas[o["prendas"][p]]["i"]]
        uri = dato_uri(r["fichero"], ancho=300, rellenar=False)
        # La prenda de partida va en todos los looks: basta un contorno, sin
        # etiquetas encima de la foto.
        suya = " suya" if ancla is not None and o["prendas"][p] == ancla else ""
        celdas.append(f'<div class="{p}{suya}"><img src="{uri}" alt=""></div>')
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
    nom = outfits.ESTILOS[estilo]["nombre"]
    # El estilo ya está en el título; en la tarjeta solo se avisa si no cumple.
    chip = (f'<span class="chip fuera">No cumple {_html.escape(nom)}</span>' if forzado
            else "")
    return (f'<article class="lk {"tres" if len(pos) == 3 else ""}">'
            f'{chip}<span class="num">{k:02d}</span>'
            f'<div class="lienzo">{"".join(celdas)}</div>'
            f'<div class="ficha-look"><p class="t">Look {k:02d}</p>'
            f'<p class="d">{_html.escape(desc)}</p>'
            f'<p class="por"><b>Por qué</b> {_html.escape(por)}</p>{wada}</div>'
            f'</article>')


def _paso(n: int, texto: str) -> str:
    return (f'<p class="paso-e"><span>{n}</span>{_html.escape(texto)}</p>')


def _detalle_prenda(p: dict) -> str:
    """Lo que las reglas saben de la prenda, para que se vea qué cuenta."""
    partes = [busqueda.ETIQUETA[p["posicion"]]]
    if p.get("tejido"):
        partes.append(outfits.LEGIBLE.get(p["tejido"], p["tejido"]))
    if p.get("estampado") and p["estampado"] != "liso":
        partes.append(p["estampado"])
    if p.get("corte"):
        partes.append(p["corte"])
    if p.get("formalidad"):
        partes.append(f'formalidad {p["formalidad"]}/5 '
                      f'({outfits.FORMAL_NOMBRE[p["formalidad"]]})')
    return " · ".join(partes)


def _nombre_prenda(p: dict) -> str:
    return (busqueda.nombre(p["tipo"]) + (f' {p["color"]}' if p["color"] else "")).strip()


@st.dialog("Elige la prenda", width="large")
def _elegir_prenda(arm, prendas: list[dict]):
    """Tu armario en rejilla; «Elegir» fija la prenda de partida."""
    pos = st.pills("Posición", ["arriba", "abajo", "encima"], selection_mode="single",
                   default="arriba", key="est_pick_pos", format_func=busqueda.ETIQUETA.get,
                   label_visibility="collapsed") or "arriba"
    lista = [p for p in prendas if p["posicion"] == pos]
    if not lista:
        st.markdown('<p class="nota-form">No tienes prendas en esta posición.</p>',
                    unsafe_allow_html=True)
        return
    for fila in range(0, len(lista), 6):
        cols = st.columns(6, gap="small")
        for col, p in zip(cols, lista[fila:fila + 6]):
            with col:
                uri = dato_uri(arm.iloc[p["i"]]["fichero"], ancho=220)
                st.markdown(f'<div class="pick"><img src="{uri}" alt=""><p>'
                            f'{_html.escape(_nombre_prenda(p))}</p></div>',
                            unsafe_allow_html=True)
                if st.button("Elegir", key=f"est_pick_{p['id']}", use_container_width=True):
                    st.session_state["est_ancla"] = p["id"]
                    st.session_state["est_semilla"] = 0
                    st.rerun()


def _con_palabras(clave: str) -> None:
    """Petición en palabras: la IA la traduce a estilo, color y capa, que se
    ven marcados abajo y se pueden cambiar. No elige ningún look."""
    from paginas import gemini
    with st.form(clave, clear_on_submit=False, border=False):
        texto = st.text_area("Petición", placeholder="Una cena informal, algo en azul…",
                             height=76, max_chars=200, label_visibility="collapsed")
        enviar = st.form_submit_button("Traducir a opciones", use_container_width=True)
    st.markdown('<p class="nota-form">La IA solo marca estilo, color y capa por ti; '
                'los looks los eligen las reglas.</p>', unsafe_allow_html=True)
    if enviar and texto.strip():
        try:
            r = outfits.interpretar_peticion(texto.strip())
        except gemini.ErrorGemini as e:
            st.warning(gemini.resumen_error(e))
            return
        if r and r.get("entendido"):
            st.session_state["est_pendiente"] = r
            st.rerun()
        st.info("No lo he entendido como una petición de ropa.")


def por_estilo(u: dict, arm, panel, res, pie):
    _aplicar_pendiente()
    prendas = outfits.prendas_de(arm)
    por_id = {p["id"]: p for p in prendas}

    with panel, st.container(key="est_panel"):
        # Tres pasos numerados y, plegado, lo opcional. Elegir (chips) se
        # pinta en burdeos claro; actuar (botones), en tinta: así un botón
        # nunca se confunde con una opción marcada.
        st.markdown(_paso(1, "Por dónde empiezas"), unsafe_allow_html=True)
        modo = st.segmented_control(
            "Cómo empiezas", ["prenda", "libre"], default="prenda", key="est_modo",
            format_func={"prenda": "Una prenda mía",
                         "libre": "No sé qué ponerme"}.get,
            label_visibility="collapsed") or "prenda"
        st.markdown('<p class="nota-form">'
                    + ("Eliges qué quieres llevar; te digo si encaja en el estilo y con "
                       "qué combinarlo." if modo == "prenda" else
                       "Looks del estilo con todo tu armario.")
                    + '</p>', unsafe_allow_html=True)

        pa = None
        if modo == "prenda":
            pa = por_id.get(st.session_state.get("est_ancla"))
            st.markdown(_paso(2, "Tu prenda"), unsafe_allow_html=True)
            if pa:
                uri = dato_uri(arm.iloc[pa["i"]]["fichero"], ancho=260)
                st.markdown(f'<div class="ancla"><img src="{uri}" alt=""><div>'
                            f'<p class="t">{_html.escape(_nombre_prenda(pa))}</p>'
                            f'<p class="d">{_html.escape(_detalle_prenda(pa))}</p>'
                            f'</div></div>', unsafe_allow_html=True)
                if st.button("Cambiar de prenda", key="est_cambiar", type="tertiary"):
                    _elegir_prenda(arm, prendas)
            elif st.button("＋  Elige la prenda que quieres llevar", key="est_elegir",
                           use_container_width=True):
                _elegir_prenda(arm, prendas)

        from paginas import gemini
        hay_ia = gemini.disponible()
        if modo == "libre" and hay_ia:
            # Sin prenda de partida, decirlo con palabras es lo natural: va
            # abierto y antes del estilo (visto en uso: plegado no se veía).
            st.markdown(_paso(2, "Dímelo con palabras"), unsafe_allow_html=True)
            _con_palabras("est_form_libre")
        st.markdown(_paso(3 if modo == "prenda" or hay_ia else 2, "Estilo"),
                    unsafe_allow_html=True)
        # Con una prenda elegida, los estilos donde encaja llevan una marca:
        # se ve de un vistazo antes de elegir.
        encajan = ({k for k in outfits.ORDEN_ESTILOS if outfits.encaje(pa, k)["nivel"]}
                   if pa else set())
        estilo = st.pills("Estilo", outfits.ORDEN_ESTILOS, selection_mode="single",
                          default="casual", key="est_estilo",
                          format_func=lambda k: outfits.ESTILOS[k]["nombre"]
                          + ("\u00a0✓" if k in encajan else ""),
                          label_visibility="collapsed") or "casual"
        st.markdown(f'<p class="nota-form">{_html.escape(outfits.ESTILOS[estilo]["idea"])}'
                    + (' ✓ = tu prenda encaja.' if pa else '')
                    + '</p>', unsafe_allow_html=True)

        # Al cambiar de estilo, «algo encima» vuelve a lo que pide el estilo
        # (Business Casual, Rocker y Grunge lo llevan; el resto, opcional).
        if st.session_state.get("est_ultimo") != estilo:
            st.session_state["est_encima"] = outfits.ESTILOS[estilo]["capa"] == "recomendado"
            st.session_state["est_ultimo"] = estilo
        # La altura solo cambia algo por debajo de ALTURA_ALARGAR: por encima
        # no se enseña el interruptor, porque no haría nada.
        altura = (auth.datos(BD_USUARIOS, u["id"]) or {}).get("altura_cm")
        aplica_altura = bool(altura) and altura < outfits.ALTURA_ALARGAR

        st.markdown('<div style="height:14px;"></div>', unsafe_allow_html=True)
        with st.expander("Afinar (opcional)"):
            st.markdown('<p class="rot-f" style="margin:4px 0 6px 0;">Un color que salga</p>',
                        unsafe_allow_html=True)
            color = st.pills("Color", list(outfits.COLORES_PEDIDO), selection_mode="single",
                             key="est_color", format_func=NOMBRE_COLOR.get,
                             label_visibility="collapsed")
            st.markdown('<div style="height:8px;"></div>', unsafe_allow_html=True)
            encima = st.toggle("Con algo encima", key="est_encima")
            st.markdown('<p class="nota-form ayuda">Añade una capa: chaqueta, blazer, '
                        'sobrecamisa. Business Casual, Rocker y Grunge la llevan de serie.</p>',
                        unsafe_allow_html=True)
            solo_wada = st.toggle("Solo combinaciones de Wada", key="est_wada")
            st.markdown('<p class="nota-form ayuda">Sanzo Wada recopiló 348 combinaciones '
                        'de colores (Japón, 1933). Sin marcar, seguir una da puntos extra; '
                        'marcado, solo salen looks que sigan una.</p>', unsafe_allow_html=True)
            usar_altura = False
            if aplica_altura:
                usar_altura = st.toggle("Priorizar looks que alargan", value=True,
                                        key="est_altura")
                st.markdown(f'<p class="nota-form ayuda">Mides {altura / 100:.2f} m'
                            .replace(".", ",") + ': primero los looks con poco contraste '
                            'entre arriba y abajo. No quita ninguno.</p>',
                            unsafe_allow_html=True)
        activo = ([NOMBRE_COLOR[color]] if color else []) \
            + (["con capa"] if encima else []) + (["solo Wada"] if solo_wada else []) \
            + (["alargar"] if usar_altura else [])
        if activo:
            st.markdown(f'<p class="nota-form">Activo: {" · ".join(activo)}</p>',
                        unsafe_allow_html=True)

        # Con una prenda elegida, la petición en palabras es secundaria.
        if modo == "prenda" and hay_ia:
            with st.expander("Pídelo con tus palabras"):
                _con_palabras("est_form")

    # ---------------------------------------------------------- resultados
    with res:
        _resultados(u, arm, prendas, modo, pa, estilo, color, encima, solo_wada,
                    altura if usar_altura else None)
    pie()


def _resultados(u, arm, prendas, modo, pa, estilo, color, encima, solo_wada, altura):
    # «Otras propuestas» sortea con una semilla; cualquier cambio en la petición
    # vuelve a la primera tanda (la determinista).
    firma = (modo, pa["id"] if pa else None, estilo, color, encima, solo_wada, altura)
    if st.session_state.get("est_firma") != firma:
        st.session_state["est_firma"] = firma
        st.session_state["est_semilla"] = 0
    semilla = st.session_state.get("est_semilla", 0)
    if modo == "prenda" and not pa:
        st.markdown('<div style="padding:40px 0 0 0;max-width:64ch;">'
                    '<div class="filete"></div><p class="seccion" style="margin-top:18px;">'
                    'Empieza por una prenda</p><p class="cuerpo" style="font-size:13.5px;'
                    'line-height:21px;">Elige una prenda de tu armario y un estilo. Akin '
                    'te dice si encaja en ese estilo y por qué, y te propone con qué '
                    'combinarla, con colores que casen según el diccionario de Wada.</p>'
                    '</div>', unsafe_allow_html=True)
        return

    forzado = False
    if pa:
        v = outfits.encaje(pa, estilo)
        nom = outfits.ESTILOS[estilo]["nombre"]
        titulo = (f"Encaja en {nom}" if v["nivel"] else f"No es {nom}")
        st.markdown(
            f'<div class="veredicto {"ok" if v["nivel"] else "no"}">'
            f'<span class="marca">{"✓" if v["nivel"] else "✕"}</span><div>'
            f'<p class="vt">{_html.escape(titulo)}</p>'
            + "".join(f'<p class="vr">{_html.escape(x)}</p>' for x in v["razones"])
            + '</div></div>', unsafe_allow_html=True)
        if v["alternativas"]:
            st.markdown('<p class="rot" style="margin:10px 0 4px 0;">Donde sí encaja'
                        if not v["nivel"] else
                        '<p class="rot" style="margin:10px 0 4px 0;">También encaja en',
                        unsafe_allow_html=True)
            otro = st.pills("Probar en", v["alternativas"], selection_mode="single",
                            key=f"est_alt_{pa['id']}_{estilo}",
                            format_func=lambda k: outfits.ESTILOS[k]["nombre"],
                            label_visibility="collapsed")
            if otro:
                st.session_state["est_pendiente"] = {"estilo": otro}
                st.rerun()
        if not v["nivel"]:
            k_f = f"est_forzar_{pa['id']}_{estilo}"
            if not st.session_state.get(k_f):
                if st.button("Montar el look igualmente", key=f"b_{k_f}"):
                    st.session_state[k_f] = True
                    st.rerun()
                return
            forzado = True

    r = outfits.generar(prendas, estilo, color_pedido=color, con_encima=encima,
                        solo_wada=solo_wada, altura=altura,
                        ancla=pa["i"] if pa else None, forzar=forzado, semilla=semilla)

    nom = outfits.ESTILOS[estilo]["nombre"]
    titulo = (f"{nom} con tu {_nombre_prenda(pa).lower()}" if pa else f"{nom}, con tu ropa")
    titulo += f" · en {color}" if color else ""
    c_t, c_b = st.columns([3, 1], vertical_alignment="bottom")
    with c_t:
        st.markdown(f'<div class="filete" style="margin-top:22px;"></div>'
                    f'<p class="seccion" style="margin-top:16px;">{_html.escape(titulo)}</p>',
                    unsafe_allow_html=True)
    with c_b:
        if r["outfits"] and st.button("Otras propuestas", key="est_otras", icon=":material/refresh:",
                                      use_container_width=True):
            st.session_state["est_semilla"] = semilla + 1
            st.rerun()
    if semilla and r["outfits"]:
        st.markdown(f'<p class="nota-form" style="margin-bottom:10px;">Tanda {semilla + 1}. '
                    'Cambia cualquier opción para volver a la primera.</p>',
                    unsafe_allow_html=True)
    if r["aviso"]:
        st.markdown(f'<p class="falta">{_html.escape(r["aviso"])}</p>',
                    unsafe_allow_html=True)
    if r["outfits"]:
        tarjetas = "".join(_tarjeta(o, k + 1, estilo, prendas, arm,
                                    pa["i"] if pa else None, forzado)
                           for k, o in enumerate(r["outfits"]))
        st.markdown(busqueda.compactar(f'<div class="carrusel"><div class="riel">'
                                       f'{tarjetas}</div></div>'), unsafe_allow_html=True)
    for pos, tipos in r["faltan"]:
        nombres = ", ".join(busqueda.nombre(t).lower() for t in tipos[:3])
        st.markdown(f'<p class="falta">Para {nom} te falta algo para '
                    f'<b>{busqueda.ETIQUETA[pos].lower()}</b>: {nombres}.'
                    + (' Quita «Con algo encima» para verlo sin capa.' if pos == "encima" else '')
                    + '</p>',
                    unsafe_allow_html=True)

    if r["outfits"]:
        _valorar(u, r["outfits"], estilo, color, prendas)
    st.markdown('<p class="falta" style="font-size:11.5px;">Cómo se eligen: '
                'reglas de estilista escritas en el código (qué prendas encajan '
                'en cada estilo, cuántos colores, qué estampados) y, si cuadra, '
                'una paleta de Wada. «Otras propuestas» sortea entre los buenos '
                'en proporción a su puntuación. La IA solo traduce lo que pides '
                'con palabras; no elige el outfit.</p>', unsafe_allow_html=True)


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
