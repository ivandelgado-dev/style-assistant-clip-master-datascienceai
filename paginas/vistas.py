"""
Las siete pantallas de la aplicación.

Aquí solo se compone: ningún cálculo de modelo vive en este fichero. Todo lo
que toca datos o pesos está en `paginas/nucleo.py`, y la autenticación en
`paginas/auth.py`.

Regla que se respeta en todo el texto de estas pantallas: **ninguna cifra que
no esté medida**. Cada número visible cita el documento de `docs/` que lo
respalda, para que se pueda ir a comprobarlo.
"""

from __future__ import annotations

import hashlib
import html as _html
import io

import streamlit as st
import streamlit.components.v1 as componentes
import numpy as np
from PIL import Image

from paginas import armario, auth, bienvenida, busqueda, cupula
from paginas.nucleo import (BD_USUARIOS, CIFRAS, DATOS, DIMENSIONES, armario_usuario,
                            cargar_armario, dato_uri, exige_sesion,
                            nube_para_cupula, usuario)

# Rellenado por app.py: las páginas se necesitan para `st.switch_page`.
PAGINAS: dict = {}


def _tarjetas(cols: int, trozos: list[str]) -> str:
    """Tarjetas con caja propia: borde, relleno y estado al pasar encima."""
    return (f'<div class="tarjetas t{cols}">' +
            "".join(f'<div class="caja-t revela">{t}</div>' for t in trozos) +
            '</div>')


# El recorrido, en el orden en que la historia se entiende.
CADENA = [
    ("Inicio", "/inicio"),
    ("El sistema", "/sistema"),
    ("Resultados", "/resultados"),
    ("Futuro", "/futuro"),
    ("El proyecto", "/proyecto"),
]


def _nav(indice: int) -> str:
    """El recorrido completo al pie de cada página, marcando dónde estás.

    Por qué esto y no un «siguiente». Se probaron tres versiones importadas de
    fuera —un bloque grande, un enlace suelto, el par anterior/siguiente de la
    documentación técnica— y las tres se veían pegadas, porque no hablaban el
    idioma del resto de la aplicación.

    Esta sí: la aplicación ya numera las cosas (01, 02, 03 en las tarjetas y
    en la tubería), y las cinco páginas son una secuencia argumental, no una
    lista de apartados. Así que el elemento natural no es «lo siguiente» sino
    **el recorrido entero**, con la posición actual marcada.

    Ventaja adicional sobre un «siguiente»: orienta. Dice cuánto queda y de
    qué va lo que viene, y no repite lo que ya hace el pie de página, porque
    el pie no dice dónde estás.
    """
    piezas = []
    for i, (titulo, ruta) in enumerate(CADENA):
        estado = ("actual" if i == indice
                  else "visto" if i < indice else "pendiente")
        piezas.append(
            f'<a class="paso {estado}" href="{ruta}">'
            f'<span class="np">{i + 1:02d}</span>'
            f'<span class="tt">{titulo}</span></a>')
    return f'<div class="recorrido revela">{"".join(piezas)}</div>'


def _franja(dicho: str, nota: str = "") -> str:
    """Franja oscura a sangre, con una sola afirmación grande."""
    pie = f'<p class="nota">{nota}</p>' if nota else ""
    return (f'<div class="franja"><div class="interior">'
            f'<p class="dicho revela">{dicho}</p>{pie}</div></div>')


def _banda(items: list[tuple]) -> str:
    """Banda de cifras grandes. (valor, texto, fuente)."""
    return ('<div class="banda">' +
            "".join(f'<div class="revela"><span class="grande">{v}</span>'
                    f'<p>{t}</p><span class="fuente">docs/{f}</span></div>'
                    for v, t, f in items) +
            '</div>')


def _celdas(clase: str, trozos: list[str]) -> str:
    return (f'<div class="{clase}">' +
            "".join(f'<div class="celda revela">{t}</div>' for t in trozos) +
            '</div>')


# ===========================================================================
# 1. INICIO
# ===========================================================================

def inicio():
    aviso = st.session_state.pop("aviso_global", None)
    if aviso:
        st.toast(aviso)
    _, arm = cargar_armario()
    n = len(arm) if arm is not None else 0

    st.markdown(
        '<div class="heroe">'
        '<h1 class="revela">Ya lo tienes.<br>Solo hay que encontrarlo.</h1>'
        '<p>Subes la foto de un look que te gusta y Akin busca en tu armario '
        'lo más parecido, pieza a pieza. O eliges un estilo y te monta '
        'conjuntos con lo que ya tienes.</p></div>', unsafe_allow_html=True)

    # El boton estaba en la PRIMERA columna de las tres, no en la del medio.
    _, c, _ = st.columns([2, 1.2, 2])
    with c:
        st.markdown('<div style="height:34px;"></div>', unsafe_allow_html=True)
        if st.button("Entrar en la aplicación", type="primary",
                     use_container_width=True):
            st.switch_page(PAGINAS["acceso"])

    # --- el héroe: embeddings reales, no una animación decorativa ---------
    u = usuario()
    V_u = armario_usuario(u["id"])[0] if u else None
    malla, rellenar, explicada = nube_para_cupula(V_u)
    if malla:
        # Sin separador: el lienzo ya trae ~50 px vacíos encima de la cúpula,
        # así que no se solapa con el botón (antes había 135 px de hueco).
        with st.container(key="cupula_ini"):
            componentes.html(cupula.html(malla, rellenar, alto=520), height=528)
        if rellenar:
            pie_fig = (f'{len(rellenar)} puntos encendidos, uno por cada prenda '
                       f'de tu armario · cada prenda va al punto más cercano a su '
                       f'vector real, pasado a 3D con PCA sobre el catálogo '
                       f'(tres componentes, {explicada*100:.1f} % de la varianza)')
        else:
            pie_fig = (f'Una esfera con {len(malla)} puntos, todos apagados · '
                       f'cuando entras se encienden tantos como prendas tengas')
        st.markdown(f'<p class="marca-agua">{pie_fig}</p>',
                    unsafe_allow_html=True)

    # Las dos ideas que hay detrás, una junto a la otra y a todo lo ancho:
    # la forma (por qué una esfera) y el nombre (por qué Akin). Son la misma
    # idea dicha dos veces: parecerse es estar cerca. Antes eran dos párrafos
    # centrados, uno debajo del otro, que dejaban media pantalla vacía.
    st.markdown(
        '<div style="height:72px;"></div>'
        '<section class="ideas revela">'
        '<article class="idea">'
        '<p class="idx">01 · La forma</p>'
        '<div class="cuerpo-idea"><div>'
        '<p class="grande"><i>cos</i> θ</p>'
        '<p class="sub">‖ v ‖ = 1 para cada prenda</p></div><div>'
        '<h3>Por qué una esfera</h3>'
        '<p class="txt">Cada prenda se convierte en un vector de longitud 1, así '
        'que todas acaban en la superficie de una esfera. Que dos prendas se '
        'parezcan es que estén cerca, y lo que uso para ordenar los resultados es '
        'el coseno del ángulo entre ellas. La malla es solo el dibujo. Lo que es '
        'dato real es qué puntos se encienden, uno por prenda. Si tus prendas '
        'salen todas amontonadas en una zona, eso es el salto de dominio que mido '
        'en este trabajo.</p>'
        '</div></div></article>'
        '<article class="idea">'
        '<p class="idx">02 · El nombre</p>'
        '<div class="cuerpo-idea"><div>'
        '<p class="grande">akin</p>'
        '<p class="sub">/əˈkɪn/ · adjetivo<br>del inglés <i>of kin</i>, «de la familia»</p>'
        '</div><div>'
        '<h3>Por qué Akin</h3>'
        '<p class="txt">Quiere decir emparentado, de la misma familia. O sea, '
        'parecido. Es justo lo que hace la app: le enseñas una prenda que te gusta '
        'y busca en tu armario las que son de su familia. Y en la esfera de arriba, '
        'lo que es <i>akin</i> está cerca. Al final es la misma idea contada dos '
        'veces.</p>'
        '</div></div></article>'
        '</section>', unsafe_allow_html=True)

    st.markdown('<div style="height:64px;"></div>'
                '<div class="filete revela" style="margin-bottom:14px;"></div>'
                '<p class="rot-f revela" style="margin-bottom:18px;">Cómo '
                'funciona</p>' +
                _tarjetas(4, [
                    '<div class="n">01</div><h3>Subes tu armario</h3>'
                    '<p>Una foto por prenda, extendida sobre algo liso. Puedes '
                    'subirlas de una en una o varias de golpe. La IA describe '
                    'cada una (tipo, color, tejido) y tú corriges lo que esté '
                    'mal. Lo que pones tú manda.</p>',
                    '<div class="n">02</div><h3>Cada prenda, un vector</h3>'
                    '<p>CLIP convierte cada foto en un vector de 512 números. '
                    'Encima entrené una capa pequeña con DeepFashion que lo '
                    'reduce a 128 y lo reordena, para que estar cerca '
                    'signifique parecerse como prenda.</p>',
                    '<div class="n">03</div><h3>Desde una foto</h3>'
                    '<p>Akin corta la foto por zonas y cada zona solo se '
                    'compara con tus prendas de ese sitio. Primero la misma '
                    'clase de prenda y después lo más parecido, o lo del '
                    'mismo color o tela si lo pides.</p>',
                    '<div class="n">04</div><h3>Por estilo</h3>'
                    '<p>Eliges un estilo y, si quieres, un color. Los '
                    'conjuntos los montan reglas de estilista que escribí yo, '
                    'con las paletas de Sanzo Wada, un diccionario japonés de '
                    'combinaciones de color.</p>']),
                unsafe_allow_html=True)

    # Franja oscura: corta el beige a media pagina y da el unico momento de
    # contraste fuerte de la portada.
    # Esta franja decia lo mismo que la de "El sistema" — que el LLM no
    # decide — y eran las dos piezas visualmente mas fuertes de la web
    # gastadas en el mismo argumento. Aqui va la promesa del producto, que no
    # se repite en ninguna otra pagina.
    st.markdown(_franja(
        'No te vende nada.<br>Te enseña <em>lo que ya tienes</em>.',
        'Casi todas las apps de moda están hechas para venderte algo. Esta '
        'empieza por el armario que ya has pagado, y la idea es que solo mire '
        'fuera cuando dentro no haya nada parecido.'), unsafe_allow_html=True)

    # Aquí NO van fotos de prendas: son del armario de una persona concreta
    # y la portada la ve cualquiera sin haber entrado. Viven en Mi armario.

    st.markdown('<div class="filete revela" style="margin-bottom:14px;"></div>'
                '<p class="rot-f revela" style="margin-bottom:20px;">Lo que se '
                'ha medido</p>' + _banda(CIFRAS), unsafe_allow_html=True)

    st.markdown('<div style="height:52px;"></div>'
                '<p class="rot-f revela" style="margin-bottom:8px;">Estado del '
                'proyecto</p>'
                '<div class="aviso revela" style="max-width:66ch;">'
                '<p class="cuerpo revela">Es una primera versión: el prototipo de '
                'un TFM, no un producto terminado. Lo que he medido es el orden '
                'de la búsqueda desde una foto. Los conjuntos por estilo salen de '
                'reglas escritas y todavía no tienen medida. En <b>Resultados y '
                'límites</b> está qué funciona, con cuánta confianza, y qué no he '
                'construido.</p></div>',
                unsafe_allow_html=True)

    st.markdown(_nav(0),
                unsafe_allow_html=True)

    pie(f"{n} prendas digitalizadas")


# ===========================================================================
# 2. EL SISTEMA
# ===========================================================================

def sistema():
    st.markdown('<div style="height:26px;"></div>'
                '<div class="filete revela"></div>'
                '<p class="seccion revela" style="margin-top:20px;">El sistema por '
                'dentro</p>'
                '<p class="cuerpo revela" style="max-width:62ch;font-size:13.5px;'
                'line-height:21px;">Todo el camino, desde que haces la foto '
                'hasta que sale la lista ordenada. Cada pieza está porque mejora '
                'una métrica o porque sostiene una decisión, no por rellenar el '
                'diagrama.</p>'
                '<div style="height:34px;"></div>', unsafe_allow_html=True)

    st.markdown('<p class="rot-f revela" style="margin-bottom:8px;">La tubería</p>' +
                _tarjetas(3, [
                    '<div class="n">01</div><h3>Captura</h3><p>Una foto por '
                    'prenda, extendida sobre un fondo liso. Mis 118 prendas '
                    'tienen dos fotos cada una. La segunda no está repetida: '
                    'me sirve para medir cuánto ruido hay entre dos fotos de '
                    'la misma prenda.</p>',
                    '<div class="n">02</div><h3>Descripción</h3><p>Gemini '
                    'describe cada foto eligiendo de listas cerradas: tipo, '
                    'manga, largo, color, estampado y tejido. Comparado con lo '
                    'que anoté yo a mano, acierta el tipo en 105 de 118 y la '
                    'manga en 25 de 27. Si el usuario corrige algo, manda lo '
                    'suyo.</p>',
                    '<div class="n">03</div><h3>Codificación</h3><p>CLIP '
                    'ViT-B/32 <b>congelado</b>. No lo reentreno por dos '
                    'motivos: harían falta semanas de cómputo y más datos de '
                    'los que tengo, y si lo tocara no sabría si la mejora '
                    'viene de ahí o de mi proyección.</p>',
                    '<div class="n">04</div><h3>Proyección</h3><p>Una capa '
                    'ligera que pasa de 512 a 128 dimensiones, entrenada con '
                    'pérdida contrastiva sobre las etiquetas de DeepFashion. '
                    'Entrené dos versiones: una conjunta y otra con tres '
                    'cabezas, una por atributo.</p>',
                    '<div class="n">05</div><h3>Búsqueda desde una foto</h3>'
                    '<p>La foto se corta por zonas y por capas (lo de debajo y '
                    'lo de encima). Cada zona se compara con tus prendas de '
                    'ese sitio: primero la misma clase de prenda, manga y '
                    'largo, y después lo más parecido, o el color o la tela si '
                    'lo eliges.</p>',
                    '<div class="n">06</div><h3>Conjuntos por estilo</h3>'
                    '<p>Reglas escritas para cada estilo (qué prendas, cuántos '
                    'colores, qué estampados, cuánta formalidad) y las 348 '
                    'paletas de Sanzo Wada. Con el mismo armario y la misma '
                    'semilla sale lo mismo, y cada conjunto dice por qué.</p>']),
                unsafe_allow_html=True)

    st.markdown('<div style="height:48px;"></div>'
                '<p class="rot-f revela" style="margin-bottom:8px;">Decisiones que '
                'hay que poder defender</p>' +
                _tarjetas(3, [
                    '<h4>Backbone congelado</h4><p>Si hubiera afinado el '
                    'backbone, cualquier mejora podría venir de ahí. Al '
                    'dejarlo congelado, la diferencia entre versiones solo '
                    'puede venir de la proyección, que es justo lo que quiero '
                    'medir.</p>',
                    '<h4>La regla, antes que el número</h4><p>Cada cambio en '
                    'el orden de la búsqueda lo medí con una regla que escribí '
                    'antes de ver el resultado. Dos propuestas no la pasaron y '
                    'se quedaron fuera, aunque usándolas parecían mejores. La '
                    'última la probé con fotos nuevas, sacadas después.</p>',
                    '<h4>SQLite y no pgvector</h4><p>Cada usuario busca solo '
                    'en su armario, unas cien prendas. Compararlas todas una a '
                    'una tarda milisegundos, así que un índice aproximado no mejora nada '
                    'que se pueda medir. El esquema es el de la entrega 3 y se '
                    'puede pasar a PostgreSQL sin tocarlo.</p>']),
                unsafe_allow_html=True)

    st.markdown(_franja(
        'La IA describe y traduce.<br>'
        'Nunca <em>decide</em>.',
        'Gemini describe las fotos (tipo, color, si tiene capucha o un gráfico '
        'grande) y traduce cosas como «una cena informal, algo en azul» a las '
        'opciones de la pantalla, que puedes ver y cambiar. Lo que no hace nunca '
        'es elegir qué prenda sale ni en qué orden. La IA dice lo que ve, y lo '
        'que se hace con eso lo deciden los vectores y unas reglas escritas, '
        'porque tiene que ser '
        'reproducible y se tiene que poder evaluar. Si le preguntas dos veces a '
        'un modelo de lenguaje te puede contestar distinto, y no hay métrica '
        'para comparar eso.'), unsafe_allow_html=True)

    st.markdown('<div style="height:48px;"></div>'
                '<p class="rot-f revela" style="margin-bottom:10px;">Herramientas'
                '</p>', unsafe_allow_html=True)
    a, b = st.columns(2, gap="large")
    with a:
        for k, v in [("Backbone", "CLIP ViT-B/32 · HuggingFace"),
                     ("Entrenamiento", "PyTorch · pérdida contrastiva"),
                     ("Descripción", "Gemini 3.5 Flash-Lite · API"),
                     ("Datos", "pandas · NumPy · SQLite"),
                     ("Evaluación", "scikit-learn · bootstrap propio")]:
            st.markdown(f'<div class="dato revela"><span>{k}</span><span>{v}</span>'
                        f'</div>', unsafe_allow_html=True)
    with b:
        # Fuera "Diseño previsto" (la tarjeta de arriba ya explica por qué
        # no hay base de datos todavía) y fuera "Reproducibilidad" y
        # "Configuración", que tienen sección propia en la página del
        # proyecto. Esto es la pila técnica y nada más.
        for k, v in [("Interfaz", "Streamlit"),
                     ("Servicio previsto", "FastAPI"),
                     ("Contenedores", "Docker (previsto)"),
                     ("Entorno", "Python 3.11 · entorno virtual")]:
            st.markdown(f'<div class="dato revela"><span>{k}</span><span>{v}</span>'
                        f'</div>', unsafe_allow_html=True)

    st.markdown(_nav(1),
                unsafe_allow_html=True)

    pie()


# ===========================================================================
# 3. RESULTADOS Y LÍMITES
# ===========================================================================

def resultados():
    st.markdown('<div style="height:26px;"></div>'
                '<div class="filete revela"></div>'
                '<p class="seccion revela" style="margin-top:20px;">Resultados y '
                'límites</p>'
                '<p class="cuerpo revela" style="max-width:62ch;font-size:13.5px;'
                'line-height:21px;">Lo que hace bien, lo que hace mal y lo que '
                'no puedo afirmar con los datos que tengo. Los resultados '
                'negativos están con el mismo detalle que los positivos, porque '
                'un resultado negativo bien medido también es un resultado.</p>'
                '<div style="height:34px;"></div>',
                unsafe_allow_html=True)

    st.markdown('<p class="rot-f revela" style="margin-bottom:10px;">Qué aporta cada '
                'pieza</p>', unsafe_allow_html=True)
    a, b = st.columns(2, gap="large")
    with a:
        st.markdown(
            '<p class="rot" style="margin-bottom:6px;">Proyección supervisada '
            'frente a CLIP sin proyección · NDCG@10</p>'
            '<div class="dato revela"><span>Atributos vistos al entrenar</span>'
            '<span><b>+0,0217</b> · significativo</span></div>'
            '<div class="dato revela"><span>Atributos no vistos</span>'
            '<span><b>+0,0132</b> · significativo</span></div>'
            '<p class="cuerpo revela" style="margin-top:12px;">Entrenar la '
            'proyección funciona, y la mejora se mantiene con atributos que el '
            'modelo no vio al entrenar. Ese segundo número es el importante: sin '
            'él, podría ser que el modelo solo hubiera memorizado.</p>',
            unsafe_allow_html=True)
    with b:
        st.markdown(
            '<p class="rot" style="margin-bottom:6px;">Cabezas por atributo '
            'frente a proyección conjunta</p>'
            '<div class="dato revela"><span>Atributos vistos</span>'
            '<span>+0,0035</span></div>'
            '<div class="dato revela"><span>Atributos no vistos</span>'
            '<span>−0,0058 · no significativo</span></div>'
            '<p class="cuerpo revela" style="margin-top:12px;">Lo que yo '
            'proponía al principio, una cabeza por atributo, <b>no gana</b>. '
            'Solo mejora con el vocabulario con el que se entrenó, y fuera de ahí '
            'no se distingue del ruido. Se especializa, pero no representa '
            'mejor, y así lo cuento.</p>',
            unsafe_allow_html=True)

    st.markdown('<div style="height:44px;"></div>'
                '<p class="rot-f revela" style="margin-bottom:8px;">Buscar tu '
                'prenda desde una foto de tienda</p>'
                '<p class="cuerpo revela" style="max-width:64ch;'
                'margin-bottom:14px;">Parejas reales de una tienda: la foto de '
                'un modelo con la prenda puesta y la foto de producto de esa '
                'misma prenda, escondida entre las mías. ¿Sale la primera? Lo '
                'medí en dos tandas, la segunda con fotos que recogí después de '
                'fijar la regla.</p>' +
                _tarjetas(3, [
                    '<h4>La proyección gana a CLIP solo</h4><p>Con las fotos '
                    'nuevas (30 parejas, 172 prendas), la prenda exacta sale '
                    '<b>primera 22 veces</b> frente a 19, y entre las tres '
                    'primeras 27 frente a 23. Al azar acertaría un 2 %. En la '
                    'primera tanda, 17 frente a 16 y 22 frente a 18.</p>',
                    '<h4>El color, como opción</h4><p>Ordenar primero por '
                    'color empata con el orden normal: 41 aciertos frente a 40 '
                    'sumando las dos tandas. Falla cuando el color se ve mal en '
                    'la foto del modelo, sobre todo con los negros. Por eso no '
                    'va por defecto y lo eliges tú.</p>',
                    '<h4>El color de la IA no mejora</h4><p>Probé a leer el '
                    'color con Gemini en vez de con los píxeles, con parejas '
                    'nuevas y la regla escrita antes: 20 aciertos frente a 23. '
                    'No entra. Lo cuento igual que los que salieron bien.</p>']) +
                '<div style="height:44px;"></div>'
                '<p class="rot-f revela" style="margin-bottom:8px;">El salto de '
                'dominio</p>' +
                _tarjetas(3, [
                    '<h4>Suelo de ruido</h4><p>Dos fotos de la misma prenda '
                    'quedan a 0,991–0,995 de similitud. Dos prendas distintas '
                    'llegan a 0,925–0,951 (percentil 95). El margen útil es de '
                    'solo 0,044–0,069: mi armario está muy apretado en el '
                    'espacio.</p>',
                    '<h4>Separabilidad</h4><p>Un clasificador lineal distingue '
                    'foto de catálogo de foto de móvil con AUC 1,000. Dos '
                    'grupos de catálogo con prendas distintas a propósito solo '
                    'se separan con 0,57–0,64. Lo que separa no es la prenda, '
                    'es el tipo de foto.</p>',
                    '<h4>Caída en la tarea</h4><p>En el test ninguna caída sale '
                    'significativa, porque los intervalos se solapan. Eso no '
                    'quiere decir que no haya caída. Quiere decir que con '
                    'estos datos no la puedo demostrar.</p>']),
                unsafe_allow_html=True)

    st.markdown('<div style="height:52px;"></div>'
                '<div class="filete revela" style="margin-bottom:14px;"></div>'
                '<p class="rot-f revela" style="margin-bottom:6px;">Lo que no '
                'salió, y se cuenta igual</p>'
                '<p class="cuerpo revela" style="max-width:62ch;'
                'margin-bottom:14px;">Tres cosas que no funcionaron. Cada una '
                'tiene su explicación dentro, porque un resultado negativo sin '
                'explicación no sirve de mucho.</p>',
                unsafe_allow_html=True)

    # Acordeon: convierte tres parrafos apretados en algo que se explora, y
    # es la unica pieza de la web con interaccion real ademas de la cupula.
    for titulo, cuerpo in [
        ("El corpus de atributos resultó ser 81–93 % ropa de mujer",
         "En el análisis exploratorio filtré por nombre de categoría (camisa, "
         "pantalón, chaqueta) y esos nombres son unisex. La comparación entre "
         "versiones sigue valiendo, porque las tres vieron exactamente los "
         "mismos datos, pero tuve que corregir lo que decía sobre el alcance "
         "en las entregas anteriores. Lo apunto como cuarto factor de "
         "confusión del análisis de dominio y no lo separo: a dos semanas de "
         "la entrega, aislarlo costaba más de lo que aportaba."),
        ("Etiquetar el género con CLIP sin entrenamiento previo: 29 % frente "
         "a un 89 % de referencia",
         "Cada clase tiene una afinidad de base que pesa más que la foto: la "
         "diferencia media con el texto de una clase (≈0,04) es mayor que lo "
         "que varía dentro de ella (≈0,025). Así que quien gana lo decide la "
         "clase y no la imagen. Es un fallo de calibración conocido de CLIP "
         "cuando se usa sin entrenar. Lo medí, lo apunté y lo descarté."),
        ("La hipótesis del fondo quedó falsada",
         "Pensaba que la colcha de rayas sobre la que hice las fotos explicaba "
         "parte del salto de dominio. Probé a recortar el fondo y no cambió "
         "nada medible en ningún nivel del análisis. Así que la descarté y me "
         "quedé con lo que sí sale en los datos: la relación con la categoría "
         "de prenda."),
    ]:
        with st.expander(titulo):
            st.markdown(f'<p class="cuerpo revela" style="max-width:74ch;">{cuerpo}'
                        f'</p>', unsafe_allow_html=True)

    st.markdown('<div style="height:44px;"></div>'
                '<p class="rot-f revela" style="margin-bottom:8px;">Lo que el sistema '
                'no hace</p>' +
                _celdas("tres", [
                    '<h4>Los conjuntos no están medidos</h4><p>«Por estilo» '
                    'monta los conjuntos con reglas de estilista, no con un '
                    'modelo que haya aprendido qué combina. Nadie ha medido '
                    'todavía si aciertan. Por eso guardo cada «me lo pondría» '
                    'y cada «no me convence».</p>',
                    '<h4>No dice si te favorece</h4><p>No hay un modelo de qué '
                    'le queda bien a cada cuerpo. No hay datos públicos, y uno '
                    'entrenado con juicios estéticos aprendería sesgos sí o sí. '
                    'La altura, si la das, solo activa una regla de proporción '
                    'que puedes ver y quitar. El peso no lo pido.</p>',
                    '<h4>No lee bien todos los colores</h4><p>El color de la '
                    'foto depende de la luz. Con negros y tonos muy oscuros la '
                    'diferencia se dispara: en la primera prueba, 9 de 24 '
                    'lecturas salieron muy lejos. Por eso el orden por defecto '
                    'no usa el color.</p>']),
                unsafe_allow_html=True)
    st.markdown(_nav(2),
                unsafe_allow_html=True)

    pie()


# ===========================================================================
# 4. HACIA DÓNDE VA
# ===========================================================================

def futuro():
    st.markdown('<div style="height:26px;"></div>'
                '<div class="filete revela"></div>'
                '<p class="seccion revela" style="margin-top:20px;">Hacia dónde '
                'va</p>'
                '<p class="cuerpo revela" style="max-width:62ch;font-size:13.5px;'
                'line-height:21px;">Nada de esta lista está hecho. Está aquí '
                'porque lo pensé y lo dejé fuera por un motivo, no porque se me '
                'olvidara. Para mí eso cuenta tanto como lo que sí está '
                'hecho.</p><div style="height:34px;"></div>',
                unsafe_allow_html=True)

    for n_fila, (titulo, estado, texto) in enumerate([
        ("Medir los conjuntos por estilo", "En marcha · recogiendo datos",
         "Ahora los montan reglas escritas. Cada «me lo pondría» y «no me "
         "convence» se guarda junto al conjunto y el estilo pedido. Con "
         "suficientes valoraciones podré medir qué reglas aciertan y ajustar "
         "sus pesos con datos, en vez de a ojo."),
        ("Compatibilidad aprendida", "Diseñado · sin implementar",
         "Cambiar las reglas por un modelo entrenado con Polyvore (partición "
         "disjunta) que diga si dos prendas pegan. Lo mediría con «rellena el "
         "hueco» y AUC. Los trabajos publicados están entre el 55 y el 62 % en "
         "esa tarea: sirve para situar un resultado, no para prometerlo."),
        ("Decidir el color con más datos", "Siguiente medida",
         "Ordenar primero por color empató con el orden normal en 54 "
         "búsquedas. Necesito más parejas, y otras con looks de varias capas, "
         "para decidir de verdad si tiene que ir por defecto."),
        ("Catálogo comercial y enlace a producto", "Diseñado · sin implementar",
         "Cuando en tu armario no hay nada para una posición, buscar la prenda "
         "más parecida en un catálogo y enlazar al producto real. Guardaría "
         "vectores, datos y la URL. Nunca las imágenes: la app las cargaría "
         "desde la web de la tienda."),
        ("Servicio y base de datos compartida", "Diseñado · sin implementar",
         "FastAPI para separar el núcleo de la interfaz, y PostgreSQL con "
         "pgvector cuando haya muchos usuarios o un catálogo grande. El "
         "esquema de la entrega 3 ya es el que usa la app en SQLite."),
        ("Reducir el salto de dominio", "Línea de investigación abierta",
         "Es lo que medí y no resolví. Lo razonable sería entrenar con más "
         "fotos de prenda extendida, como las de un armario de verdad, o "
         "aprender una transformación entre los dos tipos de foto."),
    ], 1):
        # Número · título · texto · estado, a todo lo ancho. Antes el texto
        # acababa a mitad de pantalla y la otra mitad quedaba vacía.
        st.markdown(
            f'<div class="fila-futuro revela"><span class="n">{n_fila:02d}</span>'
            f'<h3>{titulo}</h3><p class="t">{texto}</p>'
            f'<p class="e">{estado}</p></div>', unsafe_allow_html=True)
    st.markdown(_nav(3),
                unsafe_allow_html=True)

    pie()


# ===========================================================================
# 5. SOBRE EL PROYECTO
# ===========================================================================

def _foto_autor() -> str:
    """La foto del autor si está en data/autor.jpg (no se sube al repositorio:
    data/ está excluido); si no, las iniciales."""
    if (DATOS / "autor.jpg").exists():
        return (f'<div class="ini foto"><img src="{dato_uri("autor.jpg", ancho=240)}" '
                f'alt="Iván Delgado"></div>')
    return '<div class="ini">ID</div>'


def sobre():
    st.markdown('<div style="height:26px;"></div>'
                '<div class="filete revela"></div>'
                '<p class="seccion revela" style="margin-top:20px;">Sobre el '
                'proyecto</p><div style="height:22px;"></div>',
                unsafe_allow_html=True)

    a, b = st.columns([1.3, 1], gap="large")
    with a:
        # Los dos párrafos lado a lado: uno debajo del otro, a 62ch, dejaban
        # media columna vacía en pantallas anchas.
        st.markdown(
            '<div class="dos-parrafos revela">'
            '<p class="cuerpo">Me interesa la moda y creo que se puede vestir '
            'mejor con lo que ya tienes. De ahí sale Akin, mi Trabajo de Fin '
            'de Máster en Data Science y Desarrollo de IA de Evolve Academy. '
            'Empecé con una pregunta: ¿se puede buscar el parecido entre '
            'prendas <b>por atributo</b>, tipo «parécete en el corte, ignora '
            'el color», sobre un modelo de visión congelado? ¿Y eso mejora la '
            'búsqueda frente a usar el vector tal cual?</p>'
            # Aqui habia un resumen de los resultados que repetia, con otras
            # palabras, la seccion "Que aporta cada pieza" de la pagina de
            # Resultados. Se queda solo el giro del proyecto, que es contexto
            # y no resultado, y el numero vive en su pagina.
            '<p class="cuerpo">A mitad de camino cambió lo principal del '
            'trabajo: pasó a ser medir el salto entre las fotos de catálogo y '
            'las fotos reales de un armario. No lo improvisé. Lo tenía escrito '
            'como plan B desde antes de ver el primer número, por si la idea '
            'original no ganaba. No ganó, y tiré del plan B.</p></div>',
            unsafe_allow_html=True)

        st.markdown('<div style="height:32px;"></div>'
                    '<p class="rot-f revela" style="margin-bottom:8px;">Datos y '
                    'procedencia</p>', unsafe_allow_html=True)
        for fuente, uso, lic in [
            ("DeepFashion · Category and Attribute Prediction",
             "Supervisión de atributos", "CUHK MMLab · uso académico"),
            ("Polyvore Outfits", "Compatibilidad · prevista, no usada",
             "CC BY 4.0 · queda para trabajo futuro"),
            ("Fashion Product Images", "Catálogo · previsto, no usado",
             "Licencia no declarada · riesgo documentado"),
            ("Armario propio · 118 prendas", "Test fuera de distribución",
             "Fotos mías"),
            ("Parejas modelo / producto · 54", "Evaluación de la búsqueda",
             "Fotos de una tienda · solo en local, no se redistribuyen"),
            ("A Dictionary of Color Combinations", "Paletas de «Por estilo»",
             "Sanzo Wada, 1933 · datos de mattdesl, MIT"),
        ]:
            # Antes esto eran dos bloques: la fila con su borde inferior y,
            # debajo, la licencia con margin-top NEGATIVO para acercarla. Ese
            # tirón la metía justo encima del borde de la fila siguiente. Se
            # arregla metiendo la licencia DENTRO de la fila y moviendo el
            # borde al contenedor, sin márgenes negativos en ninguna parte.
            st.markdown(f'<div class="fuente-dato revela">'
                        f'<div class="fila-f"><span>{fuente}</span>'
                        f'<span>{uso}</span></div>'
                        f'<p class="lic">{lic}</p></div>',
                        unsafe_allow_html=True)

        st.markdown(
            '<div class="aviso revela" style="margin-top:40px;max-width:72ch;">'
            '<p class="cuerpo revela" style="font-size:14.5px;line-height:23px;">'
            'Las imágenes de los datasets no se redistribuyen: el repositorio '
            'deja fuera <code>data/</code> desde el primer commit. Polyvore y '
            'Fashion Product Images estaban en el plan, pero la compatibilidad '
            'y el catálogo se quedaron fuera, así que no las llegué a usar. La '
            'segunda además no declara licencia: para un uso comercial no '
            'valdría.</p></div>', unsafe_allow_html=True)

    with b:
        st.markdown(
            '<div class="caja revela">'
            + _foto_autor() +
            '<h3 class="revela" style="font-size:19px;font-weight:400;margin:18px 0 0 0;">'
            'Iván Delgado</h3>'
            '<p class="rot" style="margin-top:7px;">Autor · desarrollo, '
            'experimentación y análisis</p>'
            '<div style="height:16px;"></div>'
            '<div class="dato revela"><span>Programa</span><span>Máster en Data '
            'Science y Desarrollo de IA</span></div>'
            '<div class="dato revela"><span>Centro</span><span>Evolve Academy</span>'
            '</div>'
            '<div class="dato revela"><span>Curso</span><span>2026</span></div>'
            '<div class="dato" style="border-bottom:none;"><span>Versión</span>'
            '<span>Primera · prototipo</span></div>'
            '</div>', unsafe_allow_html=True)

        st.markdown(
            '<div style="height:24px;"></div>'
            '<p class="rot-f revela" style="margin-bottom:8px;">Reproducibilidad</p>'
            '<p class="cuerpo revela">Semillas y versiones de librerías fijadas. '
            'Cada experimento guarda su configuración en YAML y sus métricas al '
            'lado, en <code>experiments/</code>. Todos los números de esta app '
            'se pueden volver a sacar desde el repositorio.</p>',
            unsafe_allow_html=True)
    st.markdown(_nav(4),
                unsafe_allow_html=True)

    pie()


# ===========================================================================
# 6. ACCESO
# ===========================================================================

@st.dialog("Eliminar la cuenta")
def _dialogo_eliminar(d: dict):
    """¿Seguro? con contraseña y casilla. Ver auth.eliminar_cuenta."""
    propio = d.get("armario") == "propio"
    st.markdown(
        '<p class="cuerpo" style="font-size:13.5px;line-height:21px;margin:0 0 10px 0;">'
        'Se borra <b>todo</b> y no se puede deshacer:</p>'
        '<p class="cuerpo" style="font-size:13px;line-height:21px;margin:0;">'
        '· tu cuenta y tus datos<br>· tu armario, con las fotos que subiste<br>'
        '· tus outfits valorados<br>· tu foto de perfil<br>'
        '· lo que la IA describió de tus fotos</p>'
        '<div style="height:14px;"></div>'
        + ('<p class="nota-form" style="margin-top:10px;">Esta cuenta tiene el armario '
           'del autor. Sus fotos originales no se borran: son el conjunto de test del '
           'trabajo.</p>' if propio else ''),
        unsafe_allow_html=True)
    with st.container(key="dlg_eliminar"), st.form("eliminar", border=False):
        clave = st.text_input("Tu contraseña", type="password", key="el_clave")
        conf = st.checkbox("Entiendo que no se puede deshacer", key="el_conf")
        c1, c2 = st.columns(2)
        cancelar = c1.form_submit_button("Cancelar", use_container_width=True)
        borrar = c2.form_submit_button("Eliminar", type="primary", use_container_width=True)
    if cancelar:
        st.rerun()
    if borrar:
        if not conf:
            st.markdown('<p class="rot" style="color:var(--burdeos);">Marca la casilla '
                        'para confirmar.</p>', unsafe_allow_html=True)
            return
        ok, msg = auth.eliminar_cuenta(BD_USUARIOS, DATOS, d["id"], clave)
        if not ok:
            st.markdown(f'<p class="rot" style="color:var(--burdeos);">'
                        f'{_html.escape(msg)}</p>', unsafe_allow_html=True)
            return
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.session_state["aviso_global"] = "Tu cuenta y todo lo suyo se han eliminado."
        st.switch_page(PAGINAS["inicio"])


def _mi_cuenta():
    """Página de cuenta: datos personales, contraseña y cierre de sesión.

    Qué se puede cambiar y qué no, y por qué:

    - **Nombre y apellidos**: sí. No identifican la cuenta; solo letras,
      espacios, guion y apóstrofo (`auth._texto_nombre`). Sin nombre de
      usuario: se entra con el correo y otro identificador no aporta nada.
    - **Foto de perfil**: opcional. Se recorta, se reduce a 400 px y se guarda
      sin metadatos (`auth.guardar_foto`).
    - **Contraseña**: sí, exigiendo la actual. Ver `auth.cambiar_clave`.
    - **Correo**: no. Es la clave con la que se entra, y cambiarlo de forma
      segura exige verificar el nuevo correo, que esta versión no hace. Sin esa
      verificación, cualquiera con una sesión abierta podría llevarse la cuenta
      a un correo suyo.

    - **Altura**: opcional, desde el 24/09. La usa UNA regla de «Por estilo»
      (paginas/outfits.py, proporción): con menos de 1,70 m sube los looks
      de poco contraste entre arriba y abajo. Se ve, se explica y se apaga.

    Lo que NO aparece, aunque el esquema de la entrega 3 lo contemple: peso y
    preferencias. El peso no lo usa nada: toda regla de estilismo basada en el
    peso sirve para «disimular», y eso ya es un juicio sobre el cuerpo. Pedir
    un dato corporal que no se usa va contra la minimización de datos.
    """
    u = usuario()
    d = auth.datos(BD_USUARIOS, u["id"]) or u

    # Los avisos sobreviven a la recarga que hace falta tras guardar: el
    # nombre de la barra superior se pinta ANTES que esta página, así que sin
    # recargar seguiría mostrando el antiguo.
    aviso = st.session_state.pop("aviso_cuenta", None)

    st.markdown('<div style="height:34px;"></div>'
                '<div class="filete revela"></div>'
                '<p class="seccion revela" style="margin-top:18px;">Mi cuenta</p>'
                f'<p class="cuerpo revela" style="max-width:60ch;">Hola, '
                f'{_html.escape(d["nombre"].split()[0])}. Desde aquí cambias '
                f'tus datos y tu contraseña.</p>', unsafe_allow_html=True)
    if aviso:
        tipo, texto = aviso
        color = "var(--ink)" if tipo == "ok" else "var(--burdeos)"
        st.markdown(f'<div class="aviso revela" style="margin:14px 0 0 0;">'
                    f'<p class="cuerpo" style="color:{color};margin:0;">'
                    f'{_html.escape(texto)}</p></div>', unsafe_allow_html=True)

    izq, _, der = st.columns([1.25, 0.12, 1], gap="large")

    with izq:
        st.markdown('<div style="height:26px;"></div>'
                    '<p class="rot-f revela" style="margin-bottom:4px;">Datos '
                    'personales</p>', unsafe_allow_html=True)
        with st.form("datos", border=False):
            nombre = st.text_input("Nombre", value=d["nombre"], key="c_nombre",
                                   max_chars=auth.MAX_NOMBRE)
            apellidos = st.text_input("Apellidos (opcional)", value=d.get("apellidos") or "",
                                      key="c_apellidos", max_chars=auth.MAX_APELLIDOS)
            st.text_input("Correo", value=d["correo"], disabled=True,
                          key="c_correo")
            st.markdown('<p class="rot" style="margin-top:6px;'
                        'text-transform:none;letter-spacing:.2px;">El correo '
                        'identifica la cuenta y no se puede cambiar sin '
                        'verificar el nuevo, un paso que esta versión no '
                        'tiene.</p>', unsafe_allow_html=True)
            st.markdown('<div style="height:10px;"></div>',
                        unsafe_allow_html=True)
            if st.form_submit_button("Guardar cambios", type="primary"):
                ok, msg = auth.actualizar_perfil(BD_USUARIOS, d["id"], nombre, apellidos)
                if ok:
                    st.session_state["usuario"]["nombre"] = " ".join(nombre.split())
                st.session_state["aviso_cuenta"] = ("ok" if ok else "error", msg)
                st.rerun()

        st.markdown('<div style="height:34px;"></div>'
                    '<p class="rot-f revela" style="margin-bottom:4px;">'
                    'Foto de perfil (opcional)</p>', unsafe_allow_html=True)
        with st.form("foto_perfil", border=False, clear_on_submit=True):
            subida = st.file_uploader("Foto", type=["jpg", "jpeg", "png", "webp"],
                                      key="c_foto", label_visibility="collapsed")
            st.markdown('<p class="nota-form" style="margin-top:6px;">JPG, PNG o WEBP, '
                        'hasta 8 MB. Se recorta en cuadrado y se guarda sin los datos '
                        'de la foto (ni ubicación ni móvil).</p>'
                        '<div style="height:10px;"></div>', unsafe_allow_html=True)
            f1, f2 = st.columns(2)
            guardar_f = f1.form_submit_button("Guardar foto", type="primary",
                                              use_container_width=True)
            quitar_f = f2.form_submit_button("Quitar foto", use_container_width=True,
                                             disabled=not d.get("foto"))
            if guardar_f and subida is not None:
                ok, msg = auth.guardar_foto(BD_USUARIOS, DATOS, d["id"], subida.getvalue())
                st.session_state["aviso_cuenta"] = ("ok" if ok else "error", msg)
                st.rerun()
            elif guardar_f:
                st.markdown('<p class="rot" style="color:var(--burdeos);">Elige una '
                            'foto primero.</p>', unsafe_allow_html=True)
            if quitar_f:
                ok, msg = auth.quitar_foto(BD_USUARIOS, DATOS, d["id"])
                st.session_state["aviso_cuenta"] = ("ok" if ok else "error", msg)
                st.rerun()

        st.markdown('<div style="height:34px;"></div>'
                    '<p class="rot-f revela" style="margin-bottom:4px;">'
                    'Altura (opcional)</p>', unsafe_allow_html=True)
        with st.form("altura", border=False):
            alt = st.number_input("Altura en cm", min_value=0, max_value=230, step=1,
                                  value=int(d.get("altura_cm") or 0), key="c_altura",
                                  help="0 = sin decir")
            st.markdown('<p class="nota-form" style="margin-top:6px;">Solo para '
                        'una sugerencia en «Por estilo»: con menos de 1,70 m, '
                        'primero los looks con poco contraste entre arriba y '
                        'abajo, que alargan la figura. No quita ningún look y se '
                        'puede apagar. El peso no se pide.</p>'
                        '<div style="height:12px;"></div>', unsafe_allow_html=True)
            if st.form_submit_button("Guardar altura", type="primary"):
                ok, msg = auth.guardar_altura(BD_USUARIOS, d["id"], int(alt) or None)
                st.session_state["aviso_cuenta"] = ("ok" if ok else "error", msg)
                st.rerun()

        st.markdown('<div style="height:34px;"></div>'
                    '<p class="rot-f revela" style="margin-bottom:4px;">'
                    'Contraseña</p>', unsafe_allow_html=True)
        with st.form("clave", border=False, clear_on_submit=True):
            actual = st.text_input("Contraseña actual", type="password",
                                   key="c_actual")
            nueva = st.text_input("Contraseña nueva", type="password",
                                  key="c_nueva")
            repe = st.text_input("Repite la contraseña nueva", type="password",
                                 key="c_repe")
            st.markdown(f'<p class="rot" style="margin-top:6px;">Mínimo '
                        f'{auth.MIN_CLAVE} caracteres, con letras y números</p>',
                        unsafe_allow_html=True)
            st.markdown('<div style="height:10px;"></div>',
                        unsafe_allow_html=True)
            if st.form_submit_button("Cambiar contraseña", type="primary"):
                ok, msg = auth.cambiar_clave(BD_USUARIOS, d["id"], actual,
                                             nueva, repe)
                st.session_state["aviso_cuenta"] = ("ok" if ok else "error", msg)
                st.rerun()

    with der:
        completo = " ".join(x for x in (d["nombre"], d.get("apellidos")) if x)
        partes = [x for x in completo.split() if x]
        iniciales = "".join(x[0] for x in partes[:2]).upper() or "·"
        if d.get("foto") and (DATOS / d["foto"]).exists():
            avatar = (f'<div class="ini foto"><img src="{dato_uri(d["foto"], ancho=240)}" '
                      f'alt=""></div>')
        else:
            avatar = f'<div class="ini">{_html.escape(iniciales)}</div>'
        creado = str(d.get("creado") or "")[:10]
        if len(creado) == 10:
            creado = f"{creado[8:10]}/{creado[5:7]}/{creado[:4]}"
        n_prendas = armario.contar(BD_USUARIOS, d["id"])
        resumen = (f"{n_prendas} prenda{'s' if n_prendas != 1 else ''}"
                   if n_prendas else "Vacío")

        st.markdown(
            '<div style="height:26px;"></div>'
            f'<div class="caja revela">{avatar}'
            f'<h3 style="font-size:19px;font-weight:400;margin:18px 0 0 0;">'
            f'{_html.escape(completo)}</h3>'
            f'<p class="rot" style="margin-top:7px;text-transform:none;'
            f'letter-spacing:.2px;">{_html.escape(d["correo"])}</p>'
            '<div style="height:16px;"></div>'
            f'<div class="dato"><span>Miembro desde</span><span>{creado}</span></div>'
            f'<div class="dato"><span>Armario</span><span>{resumen}</span></div>'
            '<div class="dato" style="border-bottom:none;"><span>Sesión</span>'
            '<span>Hasta que recargues la página</span></div>'
            '</div>', unsafe_allow_html=True)

        st.markdown('<div style="height:18px;"></div>', unsafe_allow_html=True)
        if st.button("Ir a buscar", type="primary", use_container_width=True):
            st.switch_page(PAGINAS["buscar"])
        if st.button("Cerrar sesión", use_container_width=True):
            for clave in ("usuario", bienvenida.CLAVE, "aviso_cuenta",
                          "arm_k", "arm_hechas", "arm_filtro"):
                st.session_state.pop(clave, None)
            st.rerun()
        # Mismo botón que «Cerrar sesión», en burdeos y separado: se reconoce
        # como botón, y como el único que destruye algo.
        st.markdown('<div style="height:22px;"></div>', unsafe_allow_html=True)
        if st.button("Eliminar mi cuenta", key="c_eliminar", use_container_width=True):
            _dialogo_eliminar(d)

    pie()


def destino_tras_entrar(u: dict):
    """Con el armario vacío no hay nada que buscar: primero, Mi armario."""
    from paginas.nucleo import asegurar_importacion
    asegurar_importacion(u)
    vacio = armario.contar(BD_USUARIOS, u["id"]) == 0
    return PAGINAS["armario"] if vacio else PAGINAS["buscar"]


def acceso():
    if usuario():
        _mi_cuenta()
        return

    izq, der = st.columns([1, 1.15], gap="large")

    with izq:
        st.markdown('<div style="height:34px;"></div>'
                    '<div class="filete revela"></div>'
                    '<p class="seccion revela" style="margin-top:18px;">Acceder</p>',
                    unsafe_allow_html=True)

        t_entrar, t_crear = st.tabs(["Entrar", "Crear cuenta"])

        with t_entrar:
            st.markdown('<div style="height:10px;"></div>',
                        unsafe_allow_html=True)
            with st.form("entrar", border=False):
                c = st.text_input("Correo", key="e_correo")
                p = st.text_input("Contraseña", type="password", key="e_clave")
                st.markdown('<div style="height:14px;"></div>',
                            unsafe_allow_html=True)
                if st.form_submit_button("Entrar", type="primary",
                                         use_container_width=True):
                    espera = auth.espera_bloqueo(c)
                    u = None if espera else auth.acceder(BD_USUARIOS, c, p)
                    espera = espera or auth.espera_bloqueo(c)
                    if u is None:
                        txt = (f"Demasiados intentos con este correo. Prueba dentro "
                               f"de {max(1, round(espera / 60))} min." if espera
                               else "Correo o contraseña incorrectos.")
                        st.markdown(f'<p class="rot" style="color:var(--burdeos);'
                                    f'margin-top:12px;">{txt}</p>', unsafe_allow_html=True)
                    else:
                        st.session_state["usuario"] = u
                        st.switch_page(destino_tras_entrar(u))

        with t_crear:
            st.markdown('<div style="height:10px;"></div>',
                        unsafe_allow_html=True)
            with st.form("crear", border=False):
                nom = st.text_input("Nombre", key="r_nombre", max_chars=auth.MAX_NOMBRE)
                ape = st.text_input("Apellidos (opcional)", key="r_apellidos",
                                    max_chars=auth.MAX_APELLIDOS)
                cor = st.text_input("Correo", key="r_correo")
                cl1 = st.text_input("Contraseña", type="password", key="r_c1")
                cl2 = st.text_input("Repite la contraseña", type="password",
                                    key="r_c2")
                st.markdown(f'<p class="rot" style="margin-top:10px;">Mínimo '
                            f'{auth.MIN_CLAVE} caracteres, con letras y números</p>',
                            unsafe_allow_html=True)
                if st.form_submit_button("Crear cuenta", type="primary",
                                         use_container_width=True):
                    err = auth.validar_registro(cor, nom, cl1, cl2, ape)
                    if err:
                        st.markdown(f'<p class="rot" style="color:var(--burdeos);'
                                    f'margin-top:12px;">{_html.escape(err)}</p>',
                                    unsafe_allow_html=True)
                    else:
                        # La primera cuenta se queda el armario del autor,
                        # que se importa al entrar. Ver paginas/auth.py.
                        primera = auth.cuantos(BD_USUARIOS) == 0
                        ok, msg = auth.registrar(
                            BD_USUARIOS, cor, nom, cl1,
                            armario="propio" if primera else None, apellidos=ape)
                        if not ok:
                            st.markdown(f'<p class="rot" style="color:'
                                        f'var(--burdeos);margin-top:12px;">'
                                        f'{_html.escape(msg)}</p>',
                                        unsafe_allow_html=True)
                        else:
                            u = auth.acceder(BD_USUARIOS, cor, cl1)
                            st.session_state["usuario"] = u
                            st.switch_page(destino_tras_entrar(u))

    with der:
        st.markdown(
            '<div style="height:60px;"></div>'
            '<p class="rot-f revela" style="margin-bottom:10px;">Qué pasa con tu '
            'contraseña</p>'
            '<p class="cuerpo revela" style="max-width:54ch;">No se guarda. Se guarda '
            'el resultado de aplicarle <code>scrypt</code> con una sal '
            'aleatoria distinta para cada cuenta. <code>scrypt</code> es una '
            'función de derivación con coste de memoria: a diferencia de un '
            'hash rápido, encarece deliberadamente el ataque por fuerza bruta. '
            'La comparación se hace en tiempo constante para no filtrar '
            'información por la duración de la respuesta.</p>'
            '<p class="cuerpo revela" style="max-width:54ch;margin-top:14px;">El '
            'almacén es un fichero SQLite local que el repositorio excluye. '
            'Nada sale de tu máquina.</p>'
            '<div class="aviso revela" style="margin-top:22px;max-width:54ch;">'
            '<p class="cuerpo revela"><b>Límites declarados.</b> La sesión no '
            'sobrevive a recargar la página: mantenerla exigiría una cookie '
            'firmada, y Streamlit no expone cookies sin un componente externo. '
            'No hay recuperación de contraseña ni verificación de correo: las dos '
            'exigen enviar correos y quedan como trabajo futuro. Sí hay límite '
            'de intentos: cinco fallos seguidos bloquean ese correo cinco '
            'minutos. Cada cuenta tiene su propio armario y solo '
            've el suyo; una cuenta nueva empieza vacía y sube sus prendas '
            'desde Mi armario.</p></div>',
            unsafe_allow_html=True)
    pie()


# ===========================================================================
# 7. BUSCAR
# ===========================================================================

@st.dialog("Tu foto", width="large")
def _ampliar(im):
    """La foto sola, grande y centrada sobre la página oscurecida (estilo.py,
    .amplia). Es un st.dialog sin caja: así Esc y la X siguen funcionando."""
    st.markdown(f'<div class="amplia"><img src="{busqueda.uri_pil(im, 1400)}" '
                f'alt="Tu foto"></div>', unsafe_allow_html=True)


def buscar():
    if not exige_sesion(PAGINAS["acceso"]):
        return

    u = usuario()
    # Una vez por sesión: tapa la carga real del modelo y la deja hecha, así
    # que el resto de esta pantalla ya no espera a nada.
    bienvenida.mostrar_si_toca(u)

    # El armario de ESTE usuario, de la base. Ya no hay un armario único en
    # ficheros ni modo demostración: cada cuenta busca en lo suyo.
    V_arm, arm = armario_usuario(u["id"])
    if len(arm) == 0:
        st.markdown(
            '<div style="height:50px;"></div><div class="filete revela"></div>'
            '<p class="seccion revela" style="margin-top:18px;">Tu armario está '
            'vacío</p>'
            '<p class="cuerpo revela" style="max-width:60ch;font-size:13.5px;'
            'line-height:21px;">Akin busca en tus prendas, así que primero hay '
            'que subirlas. Una foto por prenda y qué es.</p>',
            unsafe_allow_html=True)
        c, _ = st.columns([1.2, 3])
        with c:
            st.markdown('<div style="height:20px;"></div>',
                        unsafe_allow_html=True)
            if st.button("Ir a Mi armario", type="primary",
                         use_container_width=True):
                st.switch_page(PAGINAS["armario"])
        pie()
        return

    # La posición viene de la base, no del mapa de categorías: una categoría
    # creada por el usuario («sobrecamisa») lleva la posición que él eligió.
    pos_arm = arm["posicion"].to_numpy(dtype=object)

    # Dos maneras de buscar: parecerse a una foto, o vestir un estilo con tu
    # ropa (paginas/pantalla_estilo.py). Son dos pantallas, no un filtro: van
    # como pestañas a todo el ancho, encima de las columnas, con el mismo
    # subrayado que la barra de navegación (estilo.py, .st-key-b_modo).
    st.markdown('<div style="height:18px;"></div>', unsafe_allow_html=True)
    modo = st.segmented_control(
        "Cómo buscar", ["foto", "estilo"], default="foto", key="b_modo",
        format_func={"foto": "Desde una foto", "estilo": "Por estilo"}.get,
        label_visibility="collapsed") or "foto"

    panel, _, res = st.columns([1, 0.06, 3.1], gap="large")
    if modo == "estilo":
        from paginas import pantalla_estilo
        pantalla_estilo.por_estilo(u, arm, panel, res, pie)
        return

    with panel:
        st.markdown('<div class="panel-busqueda"></div>'
                    '<p class="rot-f" style="margin-bottom:12px;">Tu foto</p>',
                    unsafe_allow_html=True)
        subida = st.file_uploader("Foto de referencia",
                                  type=["jpg", "jpeg", "png", "webp"],
                                  key="b_foto", label_visibility="collapsed")
        datos = subida.getvalue() if subida is not None else None
        if datos:
            # Un fichero con extensión de imagen que no lo es (o está roto) no
            # debe tumbar la página: se dice y no se busca.
            try:
                ref = Image.open(io.BytesIO(datos)).convert("RGB")
            except Exception:
                st.markdown('<p class="nota-form"><b style="color:var(--burdeos);">'
                            'No se puede leer esa imagen.</b> Prueba con un JPG o '
                            'PNG.</p>', unsafe_allow_html=True)
                datos = None

    if not datos:
        with res:
            st.markdown(
                '<div style="padding:40px 0 0 0;max-width:64ch;">'
                '<div class="filete revela"></div>'
                '<p class="seccion revela" style="margin-top:18px;">Sube una '
                'referencia</p>'
                '<p class="cuerpo revela" style="font-size:13.5px;'
                f'line-height:21px;">Una foto de alguien vestido, o de una '
                f'prenda suelta. Akin busca en tus {len(arm)} prendas la más '
                f'parecida <b>de cada posición</b>: tu mejor pieza de arriba, '
                f'la de abajo y, si la pides, lo que va encima.</p>'
                '<p class="cuerpo revela" style="margin-top:12px;">Después '
                'de subirla, le dices qué hay en la foto y qué buscas.</p>'
                '</div>', unsafe_allow_html=True)
        # El pie va FUERA de las columnas. Dentro de la de la derecha empezaba
        # a media pantalla y sus márgenes negativos lo sacaban por el borde.
        pie()
        return

    # Dimensión fija: el parecido general, que es la que mejor ordenó al
    # medir. Sin cifras de similitud en pantalla: en este armario todo cae en
    # un margen minúsculo y tres decimales aparentan una precisión que no hay.
    ruta = (DIMENSIONES["Parecido general"]
            if DIMENSIONES["Parecido general"].exists() else None)

    # -------------------------------------------------- qué hay en la foto
    # NO se adivina. Se probó a detectar persona / sin persona con CLIP
    # zero-shot sobre el catálogo y acertó el 66 % calibrado, por debajo del
    # 89 % de responder siempre lo mismo (docs/resultados_anotacion_dominio.md,
    # §7). Así que se pregunta, con una respuesta por defecto razonable:
    #   - persona o prenda: por la forma de la foto. Una foto de calle de
    #     cuerpo entero es claramente vertical. Falla con un pantalón
    #     extendido, que también es vertical: por eso se puede cambiar.
    #   - la posición de una prenda suelta: la de su vecina más parecida en
    #     el armario (92,4 % medido; ver busqueda.detectar_posicion).
    # Las claves llevan la huella de la foto: con otra foto, los valores por
    # defecto se recalculan en vez de arrastrar la elección anterior.
    huella = hashlib.sha1(datos).hexdigest()[:12]
    w, h = ref.size
    tipo_def = "persona" if h >= 1.2 * w else "prenda"
    pos_def = busqueda.detectar_posicion(
        V_arm, pos_arm, busqueda.vector(datos, None), ruta)
    persona_def = ["arriba", "abajo"]

    # Si hay clave de Gemini, la IA mira la foto y PROPONE las respuestas:
    # si hay persona, qué piezas lleva y dónde. Se ve lo que propone y se
    # puede cambiar. Sin red o sin clave, todo sigue como arriba.
    with res:
        with st.spinner("Mirando la foto…"):
            etq_ref = busqueda.analizar_referencia(datos)
    if etq_ref and etq_ref.get("piezas"):
        tipo_def = "persona" if etq_ref["hay_persona"] else "prenda"
        vistas_ia = [q["posicion"] for q in etq_ref["piezas"]]
        persona_def = [q for q in busqueda.ORDEN if q in vistas_ia] or persona_def
        if not etq_ref["hay_persona"]:
            pos_def = etq_ref["piezas"][0]["posicion"]

    with panel:
        st.markdown('<div style="height:24px;"></div>'
                    '<p class="rot-f" style="margin-bottom:6px;">Qué hay en '
                    'la foto</p>', unsafe_allow_html=True)
        # Con IA, esto no se pregunta: lo decide ella (persona 24/24 en las
        # fotos de modelo, prenda suelta 118/118 en el armario) y se enseña,
        # con un botón por si se equivoca. Sin IA, se pregunta, explicando
        # para qué sirve cada opción.
        EXPLICA = {"persona": "Se corta la foto por zonas y cada parte se busca "
                              "en su posición.",
                   "prenda": "Se usa la foto entera y se busca en una sola "
                             "posición."}
        k_manual = f"b_tipo_manual_{huella}"
        if etq_ref and etq_ref.get("piezas") and not st.session_state.get(k_manual):
            tipo = tipo_def
            st.markdown(f'<p class="nota-form" style="margin:0;"><b>La IA ve '
                        f'{"una persona vestida" if tipo == "persona" else "una prenda suelta"}'
                        f'.</b> {EXPLICA[tipo]}</p>', unsafe_allow_html=True)
            if st.button("¿No es así? Cámbialo", key=f"b_tipo_btn_{huella}",
                         type="tertiary"):
                st.session_state[k_manual] = True
                st.rerun()
        else:
            # La IA ha mirado la foto y no ve ropa (un paisaje, un perro…).
            # La búsqueda siempre devuelve lo más cercano, así que se avisa:
            # sin ropa en la foto, ese «más cercano» no significa nada.
            if etq_ref is not None and not etq_ref.get("piezas"):
                # padding-bottom: el contenedor de Markdown lleva -16 px abajo
                # y el texto se montaba sobre los botones de debajo.
                st.markdown('<div style="padding-bottom:22px;"><p class="nota-form">'
                            '<b style="color:var(--burdeos);">La IA no ve ropa en '
                            'esta foto.</b> Akin te enseña igualmente lo más '
                            'cercano de tu armario, pero sin ropa en la foto no '
                            'se parece a nada.</p></div>', unsafe_allow_html=True)
            tipo = st.segmented_control(
                "Qué hay en la foto", ["persona", "prenda"], default=tipo_def,
                format_func={"persona": "Una persona",
                             "prenda": "Una prenda suelta"}.get,
                key=f"b_tipo_{huella}", label_visibility="collapsed") or tipo_def
            st.markdown(f'<p class="nota-form">{EXPLICA[tipo]}</p>',
                        unsafe_allow_html=True)
            if tipo == "prenda" and etq_ref and etq_ref.get("hay_persona"):
                st.markdown('<p class="nota-form">Ojo: la IA ve a una persona '
                            'vestida. Con «Una persona» sale mejor.</p>',
                            unsafe_allow_html=True)

        st.markdown('<div style="height:16px;"></div>'
                    '<p class="rot-f" style="margin-bottom:6px;">Qué buscas'
                    '</p>', unsafe_allow_html=True)
        if tipo == "persona":
            elegidas = st.pills(
                "Qué buscas", list(busqueda.ORDEN), selection_mode="multi",
                default=persona_def, format_func=busqueda.ETIQUETA.get,
                key=f"b_pos_p_{huella}", label_visibility="collapsed") or []
            if not etq_ref:
                st.markdown('<p class="nota-form">¿Lleva algo encima, como '
                            'una camisa abierta o una chaqueta? Marca '
                            '«Encima».</p>', unsafe_allow_html=True)
        else:
            una = st.pills(
                "Qué buscas", list(busqueda.ORDEN), selection_mode="single",
                default=pos_def, format_func=busqueda.ETIQUETA.get,
                key=f"b_pos_s_{huella}", label_visibility="collapsed")
            elegidas = [una] if una else []
            if not etq_ref:
                st.markdown(f'<p class="nota-form">Por cómo se parece a tus '
                            f'prendas, Akin cree que va '
                            f'{busqueda.ETIQUETA[pos_def].lower()}. Si no, '
                            f'cámbialo.</p>', unsafe_allow_html=True)
        # Qué pesa más al ordenar. Por defecto, el orden medido («estructura»);
        # color o tela solo si el usuario lo pide. Es la idea del trabajo
        # llevada a la pantalla: consultar por un atributo y no por el todo.
        st.markdown('<div style="height:12px;"></div><p class="rot-f" '
                    'style="margin-bottom:6px;">Qué pesa más</p>',
                    unsafe_allow_html=True)
        prioridad = st.segmented_control(
            "Qué pesa más", list(busqueda.PRIORIDADES_USUARIO), default="parecido",
            key="b_prioridad", format_func=busqueda.PRIORIDADES_USUARIO.get,
            label_visibility="collapsed") or "parecido"
        if prioridad != "parecido":
            st.markdown(f'<p class="nota-form">Primero lo del mismo '
                        f'{"color" if prioridad == "color" else "tejido"}; '
                        f'después, lo más parecido. «Parecido» es el orden que se '
                        f'midió en la evaluación.</p>', unsafe_allow_html=True)
        if etq_ref and etq_ref.get("piezas"):
            ve = " · ".join(_html.escape(busqueda.describir(q))
                            for q in sorted(etq_ref["piezas"],
                                            key=lambda q: busqueda.ORDEN.index(q["posicion"])))
            st.markdown(f'<p class="nota-form"><b>La IA ve:</b> {ve}. Lo ha '
                        f'propuesto ella: si no cuadra, cámbialo.</p>',
                        unsafe_allow_html=True)

        # La foto va DESPUÉS de las preguntas: si no, en un portátil las
        # preguntas quedaban por debajo del borde de la pantalla.
        st.markdown('<div style="height:20px;"></div>', unsafe_allow_html=True)
        # Sin el «pantalla completa» de Streamlit: dejaba los resultados por
        # encima de la foto ampliada (se veían las dos cosas a la vez). Se
        # amplía en un diálogo propio, que tapa la página entera.
        # El botón va DENTRO de la foto, en la esquina, y aparece al pasar el
        # ratón (estilo.py, .st-key-b_fotoref).
        with st.container(key="b_fotoref"):
            st.image(ref, width="stretch")
            if st.button(":material/open_in_full:", key=f"b_ampliar_{huella}",
                         help="Ampliar"):
                _ampliar(ref)

    elegidas = [p for p in busqueda.ORDEN if p in elegidas]
    if not elegidas:
        with res:
            st.markdown('<div style="padding:40px 0 0 0;"><p class="cuerpo">'
                        'Elige qué quieres buscar.</p></div>',
                        unsafe_allow_html=True)
        pie()
        return

    # ------------------------------------------------------------ búsqueda
    # Con una persona, cada posición mira su parte de la foto: lo de arriba y
    # lo de encima, la banda superior; lo de abajo, la inferior. Con una
    # prenda suelta, la foto entera. Cada parte se compara SOLO con las
    # prendas de su posición.
    cajas = busqueda.cajas_look(0.52)
    # El color de la foto se lee siempre (son píxeles, milisegundos): o
    # para ordenar, si se pide, o para avisar cuando la primera propuesta
    # no es de ese color.
    umbrales = busqueda.umbrales_color()
    color_cuenta = (busqueda.ORDEN_COLOR or busqueda.ORDEN_PRIORIDADES
                    or prioridad in ("color", "tela"))
    labs = arm[["color_l", "color_a", "color_b"]].to_numpy(dtype=float)
    etqs = arm["etiquetas"].tolist()
    # Ajustes pedidos en lenguaje natural para ESTA foto («de manga larga»).
    clave_aj = f"b_ajustes_{huella}"
    ajustes = st.session_state.setdefault(clave_aj, [])
    columnas = []
    usados: set = set()
    from paginas import etiquetas as _etq
    estructura = busqueda.ORDEN_ESTRUCTURA and etq_ref is not None
    hay_abierta = bool(etq_ref) and any(
        q["posicion"] == "encima" for q in (etq_ref or {}).get("piezas", []))
    # Columnas: una por posición, salvo «encima» con dos capas exteriores
    # (sudadera abierta y abrigo): una por capa, de dentro a fuera.
    capas = _etq.capas_encima(etq_ref) if tipo == "persona" else []
    huecos = []
    for p in elegidas:
        if p == "encima" and len(capas) >= 2:
            huecos += [(p, q, "Encima" if k == 0 else "Por fuera")
                       for k, q in enumerate(capas[:2])]
        else:
            huecos.append((p, None, None))
    for p, pz_capa, titulo in huecos:
        # Encima marcado y la IA no ve nada encima: no se inventa una capa
        # (saldría la prenda de encima más parecida a la camiseta, que no está
        # en la foto). Sin IA no se sabe, y se busca. Si la IA se equivoca, un
        # ajuste que hable de lo de encima lo reabre.
        if (p == "encima" and tipo == "persona" and etq_ref and not hay_abierta
                and not any(a.get("entendido") and a.get("posicion") == "encima"
                            for a in ajustes)):
            columnas.append(busqueda.html_columna(
                p, [], None, aviso="La IA no ve nada encima en esta foto.<br>"
                "Si lo lleva, díselo abajo: «encima una cazadora negra»."))
            continue
        # La pieza que se busca es la de ESTA posición. Con «prenda suelta»
        # antes se cogía la primera pieza que describía la IA, fuera la que
        # fuera: con una foto de persona marcada como prenda suelta y «Abajo»,
        # se buscaba la camiseta en la columna de abajo (visto en uso).
        piezas_ref = (etq_ref or {}).get("piezas") or []
        pz = pz_capa or _etq.pieza(etq_ref, p) or (
            piezas_ref[0] if tipo == "prenda" and len(piezas_ref) == 1 else None)
        for aj in ajustes:
            pz = _etq.aplicar_ajuste(pz, p, aj)
        caja = None
        if tipo == "persona":
            caja = cajas["abajo"] if p == "abajo" else cajas["arriba"]
            # Con algo abierto encima, «arriba» es lo de DEBAJO, se pida o
            # no la columna de encima: se mira el centro del torso.
            if p == "arriba" and estructura and hay_abierta:
                caja = busqueda.caja_interior(0.52)
        # Lo de debajo de una capa abierta no puede ser otra capa exterior.
        bajo_capa = p == "arriba" and tipo == "persona" and hay_abierta
        mascara = (busqueda.candidatos(pos_arm, etqs, p, pz, bajo_capa)
                   if (estructura or ajustes) and pz else None)
        idx, _ = busqueda.ordenar(V_arm, pos_arm, busqueda.vector(datos, caja),
                                  p, ruta, mascara)
        leido = lab_ref = None
        if umbrales:
            from paginas import color
            lab_ref = (color.color_persona(busqueda.recortar(ref, caja), p)[0]
                       if caja is not None else color.color_prenda(ref)[0])
            leido = ((color.nombre_color(lab_ref), color.lab_a_rgb(lab_ref))
                     if color_cuenta else None)
            if busqueda.ORDEN_COLOR:
                idx = busqueda.ordenar_por_color(idx, labs, lab_ref, umbrales)
        # Un ajuste explícito ordena SIEMPRE por etiquetas: es una petición
        # del usuario, no una conjetura.
        if pz and (busqueda.ORDEN_ETIQUETAS or ajustes):
            idx = busqueda.ordenar_por_etiquetas(idx, etqs, pz)
            if not busqueda.ORDEN_COLOR:
                leido = None      # el color leído no ha contado: no se enseña
        elif prioridad == "color" and lab_ref is not None:
            idx = busqueda.ordenar_por_prioridades(
                idx, etqs, pz if estructura else None, labs, lab_ref, umbrales,
                con_nombres=bool(pz and pz.get("color")))
        elif prioridad == "tela" and pz:
            idx = busqueda.ordenar_por_tela(idx, etqs, pz, labs, lab_ref, umbrales)
        elif busqueda.ORDEN_PRIORIDADES_IA and pz and estructura:
            idx = busqueda.ordenar_por_prioridades(
                idx, etqs, pz, labs, None, None, color_ia=True)
            leido = None          # el color que cuenta es el de la IA
        elif busqueda.ORDEN_PRIORIDADES and lab_ref is not None:
            idx = busqueda.ordenar_por_prioridades(
                idx, etqs, pz if estructura else None, labs, lab_ref, umbrales)
        elif pz and estructura:
            idx = busqueda.ordenar_por_estructura(idx, etqs, pz)
        # Una misma prenda no es la principal de dos columnas.
        if idx.size and int(idx[0]) in usados:
            libres = [i for i in idx if int(i) not in usados]
            idx = np.array(libres + [i for i in idx if int(i) in usados])
        if idx.size:
            usados.add(int(idx[0]))
        filas = [arm.iloc[int(i)]
                 for i in idx[:1 + busqueda.ALTERNATIVAS + busqueda.MAS]]
        uri = (busqueda.uri_pil(busqueda.recortar(ref, caja), 300)
               if caja is not None else None)
        # Con «Parecido», la proyección ordena por forma y no ve el color.
        # Si la primera es de otro color que el leído en la foto, se dice, y
        # se dice cómo pedirlo: es la consulta por atributo del trabajo.
        nota = None
        if (prioridad == "parecido" and lab_ref is not None and idx.size and umbrales
                and np.all(np.isfinite(labs[int(idx[0])]))):
            from paginas import color
            # Se avisa solo si tampoco coincide el nombre del color: con negros
            # la ΔE exagera (ver busqueda._franja_nombres).
            if (float(color.delta_cmc(lab_ref, labs[int(idx[0])][None])[0]) > umbrales[1]
                    and _etq.franja_color(pz, etqs[int(idx[0])]) == 2):
                nota = (f"No es del color que se lee en la foto "
                        f"({color.nombre_color(lab_ref)}). Con «Color» en «Qué pesa "
                        f"más» sale primero lo de ese color.")
        columnas.append(busqueda.html_columna(p, filas, uri, leido, titulo=titulo,
                                              nota=nota))

    with res:
        titulo = ("Tu versión de este look" if tipo == "persona"
                  else "Lo más parecido en tu armario")
        st.markdown(f'<div class="filete"></div>'
                    f'<p class="seccion" style="margin-top:16px;">{titulo}</p>'
                    + busqueda.html_resultado(columnas),
                    unsafe_allow_html=True)

        # ------------------------------------------------ pídelo con palabras
        # La IA traduce la petición a cambios sobre lo buscado («manga
        # larga», «más oscuro») y se vuelve a ordenar. No elige prendas.
        # Va en el panel de la izquierda, igual que en «Por estilo»: mismo
        # nombre, misma caja y mismo botón en las dos pantallas (antes aquí era
        # «¿Algo distinto?» debajo de los resultados, y allí otra cosa).
        if etq_ref is not None:
            with panel:
                st.markdown('<div style="height:18px;"></div>'
                            '<p class="rot-f" style="margin-bottom:6px;">Pídelo con '
                            'tus palabras</p>', unsafe_allow_html=True)
                with st.form(f"b_form_{huella}", border=False, clear_on_submit=True):
                    texto = st.text_area(
                        "Pídelo", label_visibility="collapsed", height=76,
                        max_chars=200,
                        placeholder="Por ejemplo: de manga larga, más oscuro, "
                                    "sin estampado, un vaquero corto…")
                    enviar = st.form_submit_button("Aplicar",
                                                   use_container_width=True)
                st.markdown('<p class="nota-form">La IA cambia lo que se busca (manga, '
                            'largo, color, estampado…); el orden lo deciden los '
                            'vectores.</p>', unsafe_allow_html=True)
                if enviar and texto.strip():
                    import json as _json
                    with st.spinner("Entendiendo lo que pides…"):
                        aj = busqueda.interpretar(
                            texto.strip(), _json.dumps(etq_ref.get("piezas", []),
                                                       ensure_ascii=False))
                    if aj and aj.get("entendido"):
                        ajustes.append(aj)
                        # Las prendas sin describir no se pueden comparar con
                        # «más oscuro»: se describen ahora, de diez en diez.
                        # Sin describir por la IA (en la base; la tabla ya lleva
                        # etiquetas mínimas sacadas de la categoría).
                        if armario.sin_etiquetas(BD_USUARIOS, u["id"]):
                            from paginas.nucleo import describir_pendientes_lote
                            with st.spinner("Describiendo tus prendas…"):
                                describir_pendientes_lote(u["id"])
                        st.rerun()
                    st.markdown('<p class="nota-form">No he entendido eso como un '
                                'cambio en la ropa. Prueba con el color, la manga, '
                                'el largo o el estampado.</p>', unsafe_allow_html=True)
                if ajustes:
                    cambios = []
                    for aj in ajustes:
                        for k, v in aj.items():
                            if k in ("posicion", "entendido"):
                                continue
                            cambios.append({"manga": f"manga {v}",
                                            "largo": f"largo {v}",
                                            "tipo": busqueda.nombre(v).lower()
                                            }.get(k, v.replace("_", " ")))
                    st.markdown(f'<p class="nota-form" style="margin:0;"><b style="'
                                f'color:var(--burdeos);">Ajustado: '
                                f'{_html.escape(", ".join(cambios))}.</b></p>',
                                unsafe_allow_html=True)
                    if st.button("Quitar", type="tertiary",
                                 key=f"b_quitar_{huella}"):
                        st.session_state[clave_aj] = []
                        st.rerun()
            st.markdown('<p class="nota-form" style="margin-top:14px;">La foto '
                        'se envía a Gemini (Google) para describirla. Con la '
                        'clave gratuita, Google puede usarla para mejorar sus '
                        'productos.</p>', unsafe_allow_html=True)

    st.markdown('<div class="regla" style="margin:48px 0 20px 0;"></div>' +
                _celdas("tres", [
                    '<h4>Cómo se ha buscado</h4><p>Si en la foto hay una '
                    'persona, se separa la zona de arriba y la de abajo, y cada '
                    'zona se compara solo con tus prendas de esa posición. Una '
                    'bermuda nunca compite con una camisa.</p>',
                    '<h4>Quién decide qué</h4><p>La IA (Gemini) describe la '
                    'foto con palabras y propone las respuestas; tú las '
                    'corriges. El orden lo calcula Akin, no la IA: misma '
                    'foto y mismo armario, mismo resultado.</p>',
                    '<h4>Lo que no hace</h4><p>No dice que las prendas combinen '
                    'entre sí: cada una es la más parecida a su parte de la '
                    'foto. Y aprendió con fotos de tienda: con fotos de móvil '
                    'los parecidos se aprietan, que es el salto de dominio '
                    'medido.</p>']),
                unsafe_allow_html=True)
    pie()


# ===========================================================================

REPO = ("https://github.com/ivandelgado-dev/"
        "style-assistant-clip-master-datascienceai")


def _logo_pie() -> str:
    """Logotipo en gris para el pie oscuro, incrustado."""
    import base64
    import pathlib
    f = (pathlib.Path(__file__).parent / "marca/logo_gris_texto.png")
    if not f.exists():
        return '<span style="font-size:14px;letter-spacing:2px;">AKIN</span>'
    b64 = base64.b64encode(f.read_bytes()).decode()
    return f'<img src="data:image/png;base64,{b64}" alt="Akin">'


def pie(extra: str = ""):
    """Pie de página oscuro.

    Ningún enlace es inventado: los internos apuntan a rutas que existen, y
    los externos a las fuentes de datos y al repositorio reales. Un pie con
    enlaces muertos se nota enseguida.
    """
    cols = [
        ("Akin", [("Inicio", "/inicio"), ("El sistema", "/sistema"),
                  ("Resultados", "/resultados"), ("Futuro", "/futuro")]),
        ("El proyecto", [("Sobre el proyecto", "/proyecto"),
                         ("Repositorio", REPO),
                         ("Evolve Academy", "https://evolve.es/")]),
        ("Datos", [
            ("DeepFashion",
             "https://mmlab.ie.cuhk.edu.hk/projects/DeepFashion/"
             "AttributePrediction.html"),
            ("Diccionario de Wada",
             "https://github.com/mattdesl/dictionary-of-colour-combinations"),
        ]),
        ("Límites", [("Conjuntos por reglas, sin medir", None),
                     ("Sin adecuación corporal", None),
                     ("Sin catálogo comercial", None)]),
    ]
    bloques = []
    for titulo, filas in cols:
        piezas = "".join(
            (f'<a href="{u}"'
             f'{" target=_blank rel=noopener" if u.startswith("http") else ""}'
             f'>{_html.escape(t)}</a>') if u
            else f'<span class="itm">{_html.escape(t)}</span>'
            for t, u in filas)
        bloques.append(f'<div><h5>{titulo}</h5>{piezas}</div>')

    st.markdown(
        f'<div class="pie-pag">'
        f'<div class="pie-col">{"".join(bloques)}</div>'
        f'<div class="pie-rule"></div>'
        f'<div class="pie-bajo">'
        f'{_logo_pie()}'
        f'<p style="text-align:right;">Trabajo de Fin de Máster · Evolve '
        f'Academy · 2026<br>Prototipo académico, no un producto'
        f'{("· " + _html.escape(extra)) if extra else ""}</p>'
        f'</div></div>', unsafe_allow_html=True)
