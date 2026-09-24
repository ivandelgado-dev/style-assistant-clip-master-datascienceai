"""
Pantalla «Mi armario»: ver, añadir y quitar prendas.

Cómo se organiza, y por qué así
-------------------------------
Por POSICIÓN primero (arriba, abajo, encima) y por categoría dentro. No es un
criterio estético: es el mismo eje con el que busca Akin. La búsqueda compara
cada parte de la referencia solo con las prendas de su posición, así que
enseñar el armario así deja ver de un vistazo qué cubre la búsqueda y qué no.
Si una posición está vacía, esa parte del look no puede salir.

Se descartó organizar por atributos (manga corta o larga, color…) porque la
base no los tiene de forma fiable: son opcionales, los escribe el usuario, y
agrupar por un campo medio vacío deja la mitad del armario en «sin dato».

Cómo se añade una prenda
------------------------
En un diálogo, sin salir de la página, con la guía de la foto al lado del
formulario: es en ese momento cuando hace falta, no en otra pantalla.

Lo único obligatorio es la foto y qué prenda es. La categoría no es un
adorno: decide la posición, y la posición decide contra qué se compara. Los
detalles (talla, color, corte, tejido) son opcionales y el formulario lo dice:
la búsqueda no los usa, compara la foto. Sirven para que el usuario distinga
sus prendas, y quedan guardados para cuando haya filtros.

Tras guardar, el diálogo se queda abierto y vacío para la siguiente: quien
digitaliza un armario sube muchas prendas seguidas.
"""

from __future__ import annotations

import hashlib
import html as _html

import streamlit as st
from streamlit.errors import StreamlitAPIException

from paginas import armario, bienvenida, busqueda
from paginas.busqueda import ETIQUETA, NOMBRES, POSICION, nombre
from paginas.nucleo import (BD_USUARIOS, DATOS, armario_usuario, dato_uri,
                            exige_sesion, usuario)
from paginas.vistas import PAGINAS, pie

ORDEN_POS = ("arriba", "abajo", "encima")
OTRA = "__otra__"
COLUMNAS = 6


def _predefinidas() -> list[str]:
    """Categorías en el orden en que se piensan: por posición."""
    return [c for p in ORDEN_POS for c in NOMBRES if POSICION.get(c) == p]


# ---------------------------------------------------------------------------
# Guía de la foto
# ---------------------------------------------------------------------------

# Una camiseta extendida sobre un fondo liso, dentro de las esquinas de un
# visor. Es la foto que se pide, dibujada: se entiende antes que leída.
_DIBUJO = """
<svg viewBox="0 0 240 150" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <rect width="240" height="150" fill="#E3DACB"/>
  <path d="M104 30 Q120 42 136 30 L163 40 L182 66 L163 76 L155 64
           L155 124 Q120 127 85 124 L85 64 L77 76 L58 66 L77 40 Z"
        fill="#F7F3EC" stroke="#1C1B1A" stroke-width="1.1" stroke-linejoin="round"/>
  <path d="M109 32 Q120 39 131 32" fill="none" stroke="#1C1B1A" stroke-width=".8"/>
  <g stroke="#7B2D40" stroke-width="1.6" fill="none">
    <path d="M52 16 H40 V28"/><path d="M188 16 H200 V28"/>
    <path d="M52 134 H40 V122"/><path d="M188 134 H200 V122"/>
  </g>
</svg>"""

GUIA = f"""
<div class="guia">
  {_DIBUJO}
  <p class="rot-f" style="margin:18px 0 6px 0;">Cómo hacer la foto</p>
  <ol>
    <li><b>La prenda sola y extendida.</b> Sin percha y sin llevarla puesta.
        Una prenda por foto.</li>
    <li><b>Sobre un fondo liso.</b> Una sábana, el suelo o una pared de un
        solo color que contraste con la prenda. Sin estampados.</li>
    <li><b>Desde arriba y entera.</b> El móvil paralelo a la prenda y toda
        ella dentro del encuadre.</li>
    <li><b>Con luz de día.</b> Sin flash y sin sombras fuertes encima.</li>
    <li><b>Bien estirada.</b> Las arrugas también salen en la foto.</li>
  </ol>
  <p class="porque">Por qué importa: Akin aprendió con fotos de tienda, con la
  prenda centrada y el fondo limpio. Cuanto más se parezca tu foto a eso, mejor
  distingue una prenda de otra. Con fotos de móvil sin cuidar los parecidos se
  aprietan: es el salto de dominio que mide este trabajo.</p>
  <p class="porque">La foto se guarda en este equipo, sin los datos de
  ubicación que añade el móvil.</p>
</div>"""


# ---------------------------------------------------------------------------
# Diálogos
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False, max_entries=8)
def _previa(datos: bytes) -> tuple[bytes | None, str | None]:
    """La foto como se va a guardar, o el motivo por el que no vale."""
    try:
        return armario.preparar_foto(datos), None
    except ValueError as e:
        return None, str(e)


@st.cache_data(show_spinner=False, max_entries=16)
def _sugerencia(jpeg: bytes) -> dict | None:
    """Lo que Gemini ve en la foto de la prenda, o None (sin clave, sin red).

    Se le pasa la foto YA preparada: son exactamente los bytes que se
    guardan, así que la etiqueta queda en caché para esa prenda.
    """
    from paginas import etiquetas, gemini
    if not gemini.disponible():
        return None
    try:
        r = etiquetas.analizar(jpeg)
    except gemini.ErrorGemini:
        return None
    return r["piezas"][0] if r.get("piezas") else None


def _vectorizar(jpeg: bytes):
    return busqueda.vector(jpeg, None)


@st.dialog("Añadir una prenda", width="large", on_dismiss="rerun")
def _dialogo_anadir(uid: int):
    k = st.session_state.setdefault("arm_k", 0)
    hechas = st.session_state.setdefault("arm_hechas", [])
    propias = armario.categorias_propias(BD_USUARIOS, uid)

    guia, _, form = st.columns([1, 0.08, 1.15])
    with guia:
        st.markdown(GUIA, unsafe_allow_html=True)

    with form:
        if hechas:
            st.markdown(f'<div class="aviso" style="margin-bottom:14px;">'
                        f'<p class="cuerpo" style="margin:0;">Guardada: '
                        f'{_html.escape(hechas[-1])}. Sube la siguiente o '
                        f'termina.</p></div>', unsafe_allow_html=True)

        subida = st.file_uploader("Foto de la prenda",
                                  type=["jpg", "jpeg", "png", "webp"],
                                  key=f"arm_foto_{k}")
        jpeg, error = (_previa(subida.getvalue()) if subida is not None
                       else (None, None))
        if error:
            st.markdown(f'<p class="rot" style="color:var(--burdeos);">'
                        f'{_html.escape(error)}</p>', unsafe_allow_html=True)
        elif jpeg:
            st.image(jpeg, width="stretch")

        # La IA propone; el usuario confirma. Las claves de los campos llevan
        # la huella de la foto para que la propuesta se aplique a cada foto
        # nueva (un campo de Streamlit solo toma su valor inicial una vez).
        sug = None
        if jpeg:
            with st.spinner("Mirando la prenda…"):
                sug = _sugerencia(jpeg)
        h = hashlib.sha1(jpeg).hexdigest()[:8] if jpeg else "0"
        s_ = f"{k}_{h}"

        opciones = _predefinidas() + sorted(propias) + [OTRA]
        cat_sug = sug["tipo"] if sug and sug["tipo"] in opciones else None
        cat = st.selectbox(
            "Qué prenda es", opciones,
            index=opciones.index(cat_sug) if cat_sug else None,
            key=f"arm_cat_{s_}", placeholder="Elige una categoría",
            format_func=lambda c: "Otra…" if c == OTRA else nombre(c))
        if sug:
            st.markdown(f'<p class="nota-form">Propuesto por la IA: '
                        f'{_html.escape(busqueda.describir(sug))}. Si no es '
                        f'así, cámbialo.</p>', unsafe_allow_html=True)

        nuevo, pos_nueva = "", None
        if cat == OTRA:
            c1, c2 = st.columns([1.3, 1])
            nuevo = c1.text_input("Nombre", max_chars=40, key=f"arm_nom_{s_}",
                                  placeholder="Por ejemplo: sobrecamisa")
            pos_nueva = c2.selectbox("Dónde va", ORDEN_POS, index=None,
                                     key=f"arm_pos_{s_}", placeholder="Elige",
                                     format_func=ETIQUETA.get)
            st.markdown('<p class="nota-form">'
                        'La posición decide con qué se '
                        'compara: lo que va arriba solo compite con lo de '
                        'arriba. Calzado y complementos aún no entran en la '
                        'búsqueda.</p>', unsafe_allow_html=True)

        with st.expander("Más detalles (opcional)"):
            c1, c2 = st.columns(2)
            talla = c1.text_input("Talla", key=f"arm_ta_{s_}", placeholder="M, 42…")
            color = c2.text_input("Color", key=f"arm_co_{s_}",
                                  value=(sug or {}).get("color") or "",
                                  placeholder="Azul marino…")
            c3, c4 = st.columns(2)
            # Desplegable y no texto libre: «holgado» es lo que usa el estilo
            # Oversize (paginas/outfits.py). La IA no mide el ajuste de una
            # prenda extendida, así que esto solo lo sabe el usuario.
            corte = c3.selectbox("Corte", ["", "ajustado", "recto", "holgado"],
                                 key=f"arm_cu_{s_}",
                                 format_func=lambda v: v.capitalize() if v else "Sin decir")
            tejido = c4.text_input("Tejido", key=f"arm_te_{s_}",
                                   value=((sug or {}).get("tejido") or "").replace("otro", ""),
                                   placeholder="Algodón, lino…")
            manga = (sug or {}).get("manga")
            notas = st.text_input("Notas", key=f"arm_no_{s_}",
                                  value=f"manga {manga}" if manga in ("corta", "larga") else "",
                                  placeholder="Manga corta, sin capucha…")
            st.markdown('<p class="nota-form">'
                        'Son para que distingas tus prendas. Lo que ordena la '
                        'búsqueda es la foto y, si hay IA, su descripción.</p>',
                        unsafe_allow_html=True)

        listo = bool(jpeg) and cat is not None and (
            cat != OTRA or (armario.clave_categoria(nuevo) and pos_nueva))
        st.markdown('<div style="height:8px;"></div>', unsafe_allow_html=True)
        b1, b2 = st.columns([1.5, 1])
        guardar = b1.button("Guardar prenda", type="primary", disabled=not listo,
                            use_container_width=True, key=f"arm_ok_{k}")
        cerrar = b2.button("Terminar" if hechas else "Cancelar",
                           use_container_width=True, key=f"arm_x_{k}")

    if cerrar:
        st.rerun()

    if guardar and listo:
        if cat == OTRA:
            categoria = armario.clave_categoria(nuevo)
            # Si lo que escribe ya existe, manda la posición que ya tenía:
            # «Pantalón» no puede acabar arriba por haberlo escrito a mano.
            posicion = (POSICION.get(categoria) or propias.get(categoria)
                        or pos_nueva)
        else:
            categoria = cat
            posicion = POSICION.get(cat) or propias.get(cat)
        detalles = {"talla": talla, "color": color, "corte": corte,
                    "tejido": tejido, "notas": notas}
        try:
            with form, st.spinner("Guardando…"):
                armario.anadir(BD_USUARIOS, DATOS, uid, categoria, posicion,
                               subida.getvalue(), _vectorizar, detalles,
                               etiquetas=sug)
            if cat == OTRA and categoria not in POSICION:
                armario.guardar_categoria(BD_USUARIOS, uid, categoria, posicion)
        except ValueError as e:
            with form:
                st.markdown(f'<p class="rot" style="color:var(--burdeos);">'
                            f'{_html.escape(str(e))}</p>',
                            unsafe_allow_html=True)
            return
        hechas.append(nombre(categoria).lower())
        # Claves nuevas = formulario vacío para la siguiente prenda.
        st.session_state["arm_k"] = k + 1
        # Repintar SOLO el diálogo, que así sigue abierto. Pulsar «Guardar» es
        # una interacción dentro del diálogo, así que en el navegador esto
        # siempre ocurre en un repintado parcial. Si no lo fuera (en las
        # pruebas automáticas, que repintan todo), se repinta la página.
        try:
            st.rerun(scope="fragment")
        except StreamlitAPIException:
            st.rerun()


@st.dialog("Quitar prenda")
def _dialogo_quitar(uid: int, fila: dict):
    uri = dato_uri(fila["foto"], ancho=420)
    extra = ("La foto original no se borra: forma parte del conjunto de test "
             "del trabajo." if fila.get("origen") != "subida" else
             "También se borra su foto.")
    st.markdown(
        f'<div class="marco" style="margin-bottom:14px;"><img class="a" '
        f'src="{uri}" alt=""></div>'
        f'<p class="cuerpo">Deja de estar en tu armario y de salir en las '
        f'búsquedas. {extra}</p>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    if c1.button("Quitar", type="primary", use_container_width=True):
        armario.borrar(BD_USUARIOS, DATOS, uid, int(fila["id"]))
        st.session_state["aviso_armario"] = "Prenda quitada."
        st.rerun()
    if c2.button("Cancelar", use_container_width=True):
        st.rerun()


@st.dialog("Detalles de la prenda")
def _dialogo_editar(uid: int, fila: dict):
    """Talla, color, corte, tejido y notas de una prenda que ya está. El corte
    es lo que usa el estilo Oversize; el resto, para distinguir tus prendas."""
    uri = dato_uri(fila["foto"], ancho=420)
    st.markdown(f'<div class="marco" style="margin-bottom:14px;"><img class="a" '
                f'src="{uri}" alt=""></div>', unsafe_allow_html=True)
    k = f'ed_{fila["id"]}'
    ia = fila.get("etiquetas") if isinstance(fila.get("etiquetas"), dict) else {}
    ve = ", ".join(str(_legible(x)) for x in (
        ia.get("color"), ia.get("tejido") if ia.get("tejido") != "otro" else None,
        f'manga {ia["manga"]}' if ia.get("manga") in ("corta", "larga") else None,
        ia.get("estampado") if ia.get("estampado") not in (None, "liso") else None) if x)
    st.markdown(
        '<p class="nota-form">'
        + (f'<b>La IA ya ve:</b> {_html.escape(ve)}. Eso ya se usa al buscar y al '
           'montar outfits, no hace falta copiarlo aquí. ' if ve else
           'La IA aún no ha descrito esta prenda. ')
        + 'Rellena solo lo que quieras corregir o lo que la IA no puede saber: '
          'la <b>talla</b> y el <b>corte</b> (holgado = estilo Oversize). Lo que '
          'escribas aquí manda sobre lo que ve la IA.</p>', unsafe_allow_html=True)

    def v(c):          # None o NaN de pandas -> ""
        x = fila.get(c)
        return x if isinstance(x, str) else ""
    # Qué es: la categoría manda sobre lo que diga la IA (etiquetas.efectivas)
    # y decide la posición. Se puede corregir aquí.
    propias = armario.categorias_propias(BD_USUARIOS, uid)
    cats = _predefinidas() + sorted(c for c in propias if c not in POSICION)
    actual_cat = str(fila.get("categoria") or "")
    if actual_cat and actual_cat not in cats:
        cats.append(actual_cat)
    cat = st.selectbox("Qué es", cats, index=cats.index(actual_cat) if actual_cat in cats else 0,
                       key=f"{k}_cat", format_func=nombre)
    nueva_pos = POSICION.get(cat) or propias.get(cat) or fila.get("posicion")
    if cat != actual_cat and nueva_pos != fila.get("posicion"):
        st.markdown(f'<p class="nota-form">Pasará a <b>{ETIQUETA[nueva_pos].lower()}'
                    f'</b>.</p>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    talla = c1.text_input("Talla", value=v("talla"), key=f"{k}_ta")
    color = c2.text_input("Color", value=v("color"), key=f"{k}_co",
                          placeholder=_legible(ia.get("color")) or "")
    c3, c4 = st.columns(2)
    opciones = ["", "ajustado", "recto", "holgado"]
    actual = v("corte").strip().lower()
    corte = c3.selectbox("Corte", opciones + ([actual] if actual not in opciones else []),
                         index=(opciones + [actual]).index(actual) if actual else 0,
                         key=f"{k}_cu",
                         format_func=lambda v: v.capitalize() if v else "Sin decir")
    tejido = c4.text_input("Tejido", value=v("tejido"), key=f"{k}_te",
                           placeholder=_legible(ia.get("tejido")) or "")
    notas = st.text_input("Notas", value=v("notas"), key=f"{k}_no")
    b1, b2 = st.columns(2)
    if b1.button("Guardar", type="primary", use_container_width=True):
        if cat != actual_cat:
            armario.actualizar_categoria(BD_USUARIOS, uid, int(fila["id"]), cat, nueva_pos)
        armario.actualizar_detalles(BD_USUARIOS, uid, int(fila["id"]),
                                    {"talla": talla, "color": color, "corte": corte,
                                     "tejido": tejido, "notas": notas})
        st.session_state["aviso_armario"] = "Detalles guardados."
        st.rerun()
    if b2.button("Cancelar", use_container_width=True):
        st.rerun()


def _describir_pendientes(uid: int):
    """Botón para que la IA describa las prendas que aún no tienen etiquetas
    (las de antes de existir esto). Una a una, con pausa: el nivel gratuito
    de la API limita las peticiones por minuto."""
    from paginas import etiquetas, gemini
    if not gemini.disponible():
        return
    pend = armario.sin_etiquetas(BD_USUARIOS, uid)
    if not pend:
        return
    minutos = round(len(pend) * 4.5 / 60)
    duracion = "menos de un minuto" if minutos < 1 else (
        "un minuto" if minutos == 1 else f"unos {minutos} minutos")
    c1, c2 = st.columns([3, 1.2], vertical_alignment="center")
    c1.markdown(f'<p class="nota-form" style="margin:14px 0 0 0;">{len(pend)} '
                f'prenda{"s" if len(pend) != 1 else ""} sin describir por la '
                f'IA. Sin descripción, la búsqueda solo usa el parecido visual '
                f'para ellas. Tarda {duracion}; las fotos se envían a '
                f'Gemini (Google).</p>', unsafe_allow_html=True)
    if not c2.button("Describirlas", key="arm_describir"):
        return
    barra = st.progress(0.0, text="Describiendo…")
    fallos = 0
    for n, (pid, foto) in enumerate(pend, 1):
        try:
            r = etiquetas.analizar((DATOS / foto).read_bytes(), pausa=4.0)
            if r.get("piezas"):
                armario.guardar_etiquetas(BD_USUARIOS, uid, pid, r["piezas"][0])
        except (gemini.ErrorGemini, OSError):
            fallos += 1
            if fallos >= 3:
                st.session_state["aviso_armario"] = ("La IA no responde (sin red o "
                                                     "límite de uso). Prueba más tarde.")
                break
        barra.progress(n / len(pend), text=f"Describiendo… {n}/{len(pend)}")
    st.rerun()


def abrir_anadir(uid: int):
    st.session_state["arm_hechas"] = []
    _dialogo_anadir(uid)


# ---------------------------------------------------------------------------
# Pantalla
# ---------------------------------------------------------------------------

MINIATURA = 300   # px de ancho; la tarjeta se ve a ~190 px en pantalla


def _tarjeta(f) -> str:
    # Sin la segunda toma al pasar el cursor, a diferencia de la búsqueda:
    # aquí hay cien tarjetas, cada foto va incrustada en la página y la
    # segunda toma la duplicaba (5,2 MB medidos, reenviados en cada clic).
    a = dato_uri(f["fichero"], ancho=MINIATURA)
    desc = f["descripcion_libre"] or "\u00a0"
    return (f'<div class="ficha fija"><div class="marco">'
            f'<img class="a" src="{a}" alt="">'
            f'</div><div class="pie"><p class="nom">{_html.escape(nombre(f["categoria"]))}'
            f'</p><p class="desc">{_html.escape(desc)}</p></div></div>')


# Cómo se leen los valores de la IA (se guardan sin tildes).
LEGIBLE = {"algodon": "algodón", "sintetico": "sintético", "marron": "marrón",
           "pantalon": "pantalón", "cardigan": "cárdigan"}


def _legible(v):
    return LEGIBLE.get(v, v) if v else v


CINTA_MAX = 16     # tarjetas en la cinta (van duplicadas: 32 imágenes)


def _cinta(arm) -> str:
    """Cinta automática de prendas, como la de profesores de Evolve: tarjeta
    con la etiqueta arriba y una ficha blanca abajo, en bucle, que se para al
    pasar el cursor. Solo CSS (clases .cinta/.pista de estilo.py).

    Qué prendas: una de cada categoría por turnos, empezando por las más
    recientes, hasta CINTA_MAX, para que se vea la variedad del armario y no
    diez camisetas seguidas. Determinista: mismo armario, misma cinta.
    """
    grupos = {}
    for _, f in arm.sort_values("creado", ascending=False).iterrows():
        grupos.setdefault(f["categoria"], []).append(f)
    elegidas, k = [], 0
    while len(elegidas) < CINTA_MAX and any(k < len(g) for g in grupos.values()):
        for g in grupos.values():
            if k < len(g) and len(elegidas) < CINTA_MAX:
                elegidas.append(g[k])
        k += 1
    tarjetas = []
    for f in elegidas:
        e = f["etiquetas"] if isinstance(f["etiquetas"], dict) else {}
        uri = dato_uri(f["fichero"], ancho=300, rellenar=False)
        titulo = nombre(f["categoria"]) + (f' {_legible(e["color"])}' if e.get("color") else "")
        sub = " · ".join(x for x in (
            _legible(e.get("tejido")) if e.get("tejido") not in (None, "otro") else None,
            f'manga {e["manga"]}' if e.get("manga") in ("corta", "larga") else None,
            ETIQUETA.get(f["posicion"], "")) if x)
        tarjetas.append(
            f'<article class="lk cintalk"><span class="chip">'
            f'{_html.escape(nombre(f["categoria"]))}</span>'
            f'<div class="lienzo uno"><div><img src="{uri}" alt="" loading="lazy">'
            f'</div></div><div class="ficha-look"><p class="t">{_html.escape(titulo)}</p>'
            f'<p class="d">{_html.escape(sub)}</p></div></article>')
    fila = "".join(tarjetas)
    # Duplicada: la pista se desplaza un -50 % y vuelve al principio sin salto.
    return busqueda.compactar(f'<div class="cinta cinta-armario"><div class="pista">'
                              f'{fila}{fila}</div></div>')


def mi_armario():
    if not exige_sesion(PAGINAS["acceso"]):
        return
    u = usuario()
    bienvenida.mostrar_si_toca(u)
    _, arm = armario_usuario(u["id"])

    aviso = st.session_state.pop("aviso_armario", None)
    if aviso:
        st.toast(aviso)

    n = len(arm)
    por_pos = arm["posicion"].value_counts().to_dict() if n else {}
    resumen = (" · ".join([f"{n} prenda{'s' if n != 1 else ''}"] +
                          [f"{por_pos.get(p, 0)} {ETIQUETA[p].lower()}"
                           for p in ORDEN_POS]) if n else "Todavía sin prendas")

    cab, _, bot = st.columns([3, 0.3, 1], vertical_alignment="bottom")
    with cab:
        st.markdown('<div style="height:34px;"></div>'
                    '<div class="filete revela"></div>'
                    '<p class="seccion revela" style="margin-top:18px;">'
                    'Mi armario</p>'
                    f'<p class="rot revela">{resumen}</p>',
                    unsafe_allow_html=True)
    with bot:
        if n and st.button("Añadir prenda", type="primary",
                           use_container_width=True, key="arm_abrir"):
            abrir_anadir(u["id"])

    if not n:
        izq, _, der = st.columns([1.1, 0.15, 1], gap="large")
        with izq:
            st.markdown(
                '<div style="height:40px;"></div>'
                '<p class="titular revela">Empieza por lo que más te pones.</p>'
                '<p class="cuerpo revela" style="max-width:52ch;margin-top:14px;">'
                'Akin busca en tus prendas, así que lo primero es tenerlas '
                'aquí. Una foto por prenda y qué es: el resto es opcional.</p>'
                '<p class="cuerpo revela" style="max-width:52ch;margin-top:12px;">'
                'Cada parte de un look se busca en su posición. Para que '
                'Akin pueda proponerte algo de arriba y algo de abajo, '
                'necesita al menos una prenda de cada.</p>'
                '<div style="height:26px;"></div>', unsafe_allow_html=True)
            c, _ = st.columns([1.1, 1])
            with c:
                if st.button("Añadir tu primera prenda", type="primary",
                             use_container_width=True, key="arm_primera"):
                    abrir_anadir(u["id"])
        with der:
            st.markdown('<div style="height:40px;"></div>' + GUIA,
                        unsafe_allow_html=True)
        pie()
        return

    _describir_pendientes(u["id"])

    # Qué posiciones faltan: la búsqueda no puede cubrirlas.
    faltan = [ETIQUETA[p].lower() for p in ("arriba", "abajo")
              if not por_pos.get(p)]
    if faltan:
        st.markdown(f'<div class="aviso revela" style="margin-top:16px;">'
                    f'<p class="cuerpo" style="margin:0;">No tienes prendas de '
                    f'{" ni de ".join(faltan)}: esa parte de un look no puede '
                    f'salir en la búsqueda.</p></div>', unsafe_allow_html=True)

    if n >= 6:
        st.markdown('<div style="height:22px;"></div>' + _cinta(arm),
                    unsafe_allow_html=True)

    st.markdown('<div style="height:26px;"></div>', unsafe_allow_html=True)
    etiquetas = ["Todo"] + [f"{ETIQUETA[p]} · {por_pos[p]}"
                            for p in ORDEN_POS if por_pos.get(p)]
    elegida = st.radio("Ver", etiquetas, horizontal=True, key="arm_filtro",
                       label_visibility="collapsed")
    posiciones = ([p for p in ORDEN_POS if por_pos.get(p)] if elegida == "Todo"
                  else [p for p in ORDEN_POS
                        if elegida.startswith(ETIQUETA[p])])

    for p in posiciones:
        sub = arm[arm["posicion"] == p]
        st.markdown(f'<div class="regla" style="margin:34px 0 0 0;"></div>'
                    f'<p class="seccion revela" style="margin-top:18px;'
                    f'font-size:24px;">{ETIQUETA[p]}</p>',
                    unsafe_allow_html=True)
        # Categorías de más a menos prendas: lo que más tienes, primero.
        for cat, grupo in sorted(sub.groupby("categoria"),
                                 key=lambda t: (-len(t[1]), t[0])):
            st.markdown(f'<p class="rot-f revela" style="margin:22px 0 10px 0;">'
                        f'{_html.escape(nombre(cat, plural=len(grupo) != 1))}'
                        f' · {len(grupo)}</p>', unsafe_allow_html=True)
            filas = [r for _, r in grupo.iterrows()]
            for i in range(0, len(filas), COLUMNAS):
                cols = st.columns(COLUMNAS, gap="small")
                for col, f in zip(cols, filas[i:i + COLUMNAS]):
                    with col:
                        st.markdown(_tarjeta(f), unsafe_allow_html=True)
                        e1, e2 = st.columns(2, gap="small")
                        if e1.button("Detalles", key=f"arm_e_{f['id']}",
                                     type="tertiary"):
                            _dialogo_editar(u["id"], f.to_dict())
                        if e2.button("Quitar", key=f"arm_q_{f['id']}",
                                     type="tertiary"):
                            _dialogo_quitar(u["id"], f.to_dict())
    pie()
