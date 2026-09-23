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
from PIL import Image

from paginas import armario, auth, bienvenida, busqueda, cupula
from paginas.nucleo import (BD_USUARIOS, CIFRAS, DIMENSIONES, armario_usuario,
                            cargar_armario, exige_sesion,
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
    _, arm = cargar_armario()
    n = len(arm) if arm is not None else 0

    st.markdown(
        '<div class="heroe">'
        '<h1 class="revela">Ya lo tienes.<br>Solo hay que encontrarlo.</h1>'
        '<p>Subes la foto de una prenda que has visto y Akin ordena tu armario '
        'por parecido a ella. Por el conjunto, o por una sola dimensión: el '
        'corte, la textura o el tejido.</p></div>', unsafe_allow_html=True)

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
        st.markdown('<div style="height:70px;"></div>', unsafe_allow_html=True)
        componentes.html(cupula.html(malla, rellenar, alto=520), height=528)
        if rellenar:
            pie_fig = (f'{len(rellenar)} posiciones rellenas, una por prenda '
                       f'de tu armario · cada prenda ocupa la más próxima a su '
                       f'vector real, proyectado sobre la base PCA del corpus '
                       f'de catálogo — tres componentes, {explicada*100:.1f} % '
                       f'de la varianza')
        else:
            pie_fig = (f'Retículo de {len(malla)} posiciones sobre la esfera '
                       f'unidad, todas vacías · inicia sesión y se rellenan '
                       f'tantas como prendas tengas')
        st.markdown(f'<p class="marca-agua">{pie_fig}</p>',
                    unsafe_allow_html=True)

    st.markdown(
        '<div style="height:52px;"></div>'
        '<div class="filete" style="margin:0 auto 22px auto;"></div>'
        '<p class="seccion revela" style="text-align:center;">Por qué una esfera</p>'
        '<p class="cuerpo revela" style="max-width:58ch;margin:0 auto;'
        'text-align:center;font-size:13.5px;line-height:21px;">'
        'Los vectores de este sistema están normalizados: cada prenda tiene '
        'norma 1, así que todas viven sobre la superficie de una esfera. La '
        'similitud coseno con la que se ordenan los resultados es el coseno '
        'del ángulo entre dos puntos de esa superficie. La figura de arriba es '
        'esa esfera. Las posiciones forman un retículo uniforme, que es '
        'estructura; lo que es dato es cuáles se rellenan, porque cada prenda '
        'ocupa la más próxima a su vector real. Si tus prendas se concentran '
        'en una zona en vez de repartirse, eso es el salto de dominio que '
        'este trabajo mide.</p>',
        unsafe_allow_html=True)

    st.markdown('<div style="height:64px;"></div>'
                '<div class="filete revela" style="margin-bottom:14px;"></div>'
                '<p class="rot-f revela" style="margin-bottom:18px;">Cómo '
                'funciona</p>' +
                _tarjetas(3, [
                    '<div class="n">01</div><h3>Digitalizas el armario</h3>'
                    '<p>Dos fotografías por prenda, extendida sobre una '
                    'superficie lisa. El protocolo de captura está fijado y '
                    'documentado para que las condiciones no varíen entre '
                    'prendas.</p>',
                    '<div class="n">02</div><h3>Se proyecta el espacio</h3>'
                    '<p>CLIP ViT-B/32 congelado convierte cada foto en un '
                    'vector de 512 dimensiones. Encima, una proyección '
                    'supervisada de 128 dimensiones entrenada sobre '
                    'DeepFashion reordena ese espacio para que la distancia '
                    'signifique parecido de prenda.</p>',
                    '<div class="n">03</div><h3>Se ordena por distancia</h3>'
                    '<p>La referencia pasa por la misma proyección y las '
                    'prendas se ordenan por similitud coseno. Una distancia '
                    'entre vectores: la misma consulta devuelve siempre el '
                    'mismo orden.</p>']),
                unsafe_allow_html=True)

    # Franja oscura: corta el beige a media pagina y da el unico momento de
    # contraste fuerte de la portada.
    # Esta franja decia lo mismo que la de "El sistema" — que el LLM no
    # decide — y eran las dos piezas visualmente mas fuertes de la web
    # gastadas en el mismo argumento. Aqui va la promesa del producto, que no
    # se repite en ninguna otra pagina.
    st.markdown(_franja(
        'No te dice qué ponerte.<br>Te dice <em>qué tienes</em>.',
        'La mayoría de los sistemas de moda existen para venderte algo. Este '
        'empieza por el armario que ya has pagado, y solo mira fuera cuando '
        'dentro no hay nada que se parezca.'), unsafe_allow_html=True)

    # Aquí NO van fotos de prendas: son del armario de una persona concreta
    # y la portada la ve cualquiera sin haber entrado. Viven en Mi armario.

    st.markdown('<div class="filete revela" style="margin-bottom:14px;"></div>'
                '<p class="rot-f revela" style="margin-bottom:20px;">Lo que se '
                'ha medido</p>' + _banda(CIFRAS), unsafe_allow_html=True)

    st.markdown('<div style="height:52px;"></div>'
                '<p class="rot-f revela" style="margin-bottom:8px;">Estado del '
                'proyecto</p>'
                '<div class="aviso revela" style="max-width:66ch;">'
                '<p class="cuerpo revela">Primera versión. Es el prototipo de un '
                'Trabajo de Fin de Máster, no un producto: se evalúa la '
                'calidad del ordenamiento, y las partes que no afectan a esa '
                'medida están deliberadamente fuera. La página de '
                '<b>resultados y límites</b> detalla qué funciona, con cuánta '
                'confianza, y qué no se ha construido.</p></div>',
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
                'line-height:21px;">Todo el recorrido, desde una fotografía '
                'hasta una lista ordenada. Cada pieza está aquí porque mejora '
                'una métrica o porque sostiene una decisión; ninguna está por '
                'completar el diagrama.</p>'
                '<div style="height:34px;"></div>', unsafe_allow_html=True)

    st.markdown('<p class="rot-f revela" style="margin-bottom:8px;">La tubería</p>' +
                _tarjetas(4, [
                    '<div class="n">01</div><h3>Captura</h3><p>Dos tomas por '
                    'prenda, extendida, sobre el mismo fondo y con la misma '
                    'luz. La segunda toma no es un duplicado: sirve para medir '
                    'el suelo de ruido del sistema.</p>',
                    '<div class="n">02</div><h3>Codificación</h3><p>CLIP '
                    'ViT-B/32 <b>congelado</b>. No se reentrena el backbone: '
                    'exige semanas de cómputo y más datos de los que hay, y '
                    'sin congelarlo no se puede atribuir la mejora a la '
                    'proyección.</p>',
                    '<div class="n">03</div><h3>Proyección</h3><p>Una cabeza '
                    'ligera de 512 a 128 dimensiones, entrenada con pérdida '
                    'contrastiva sobre las etiquetas de DeepFashion. Se '
                    'entrenaron dos variantes: una conjunta y tres '
                    'específicas por atributo.</p>',
                    '<div class="n">04</div><h3>Recuperación</h3><p>Producto '
                    'escalar entre vectores normalizados sobre unos 44.000 '
                    'elementos. Cabe en memoria y no necesita índice '
                    'aproximado a esta escala.</p>']),
                unsafe_allow_html=True)

    st.markdown('<div style="height:48px;"></div>'
                '<p class="rot-f revela" style="margin-bottom:8px;">Decisiones que '
                'hay que poder defender</p>' +
                _tarjetas(3, [
                    '<h4>Backbone congelado</h4><p>Si se afina el backbone, '
                    'cualquier mejora puede venir de ahí. Congelándolo, la '
                    'diferencia entre condiciones solo puede atribuirse a la '
                    'proyección, que es lo que se quiere medir.</p>',
                    '<h4>Partición disjunta</h4><p>Los conjuntos de Polyvore '
                    'se parten de forma que ninguna prenda aparezca en dos '
                    'particiones. La partición no disjunta permite memorizar '
                    'prendas concretas e infla los resultados.</p>',
                    '<h4>Sin base de datos todavía</h4><p>El diseño en '
                    'PostgreSQL con pgvector está documentado y defendido en '
                    'la entrega 3. Lo que cambia es el orden de construcción: '
                    'levantarla antes de tener una métrica no produce ninguna '
                    'métrica.</p>']),
                unsafe_allow_html=True)

    st.markdown(_franja(
        'Un modelo de lenguaje puede explicar un resultado.<br>'
        'Nunca <em>decidirlo</em>.',
        'Puede traducir una petición en lenguaje natural a restricciones, y '
        'puede redactar por qué salió una prenda. Lo que no hace en ningún '
        'punto es elegir cuál sale ni en qué orden: esa decisión tiene que ser '
        'reproducible y evaluable, y dos ejecuciones de un LLM pueden diferir '
        'sin que haya métrica que las compare.'), unsafe_allow_html=True)

    st.markdown('<div style="height:48px;"></div>'
                '<p class="rot-f revela" style="margin-bottom:10px;">Herramientas'
                '</p>', unsafe_allow_html=True)
    a, b = st.columns(2, gap="large")
    with a:
        for k, v in [("Backbone", "CLIP ViT-B/32 · HuggingFace"),
                     ("Entrenamiento", "PyTorch · pérdida contrastiva"),
                     ("Datos", "pandas · NumPy · parquet"),
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
                     ("Contenedores", "Docker"),
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
                'line-height:21px;">Lo que el sistema hace bien, lo que hace '
                'mal y lo que no se puede afirmar con los datos que hay. Los '
                'resultados negativos están aquí con el mismo detalle que los '
                'positivos: un resultado negativo bien medido es un '
                'resultado.</p><div style="height:34px;"></div>',
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
            '<p class="cuerpo revela" style="margin-top:12px;">Supervisar el espacio '
            'funciona, y la mejora sobrevive a vocabulario que el modelo no vio '
            'al entrenar. Ese segundo número es el que importa: sin él, la '
            'mejora podría ser memorización.</p>', unsafe_allow_html=True)
    with b:
        st.markdown(
            '<p class="rot" style="margin-bottom:6px;">Cabezas por atributo '
            'frente a proyección conjunta</p>'
            '<div class="dato revela"><span>Atributos vistos</span>'
            '<span>+0,0035</span></div>'
            '<div class="dato revela"><span>Atributos no vistos</span>'
            '<span>−0,0058 · no significativo</span></div>'
            '<p class="cuerpo revela" style="margin-top:12px;">La contribución '
            'original del trabajo <b>no gana</b>. Desacoplar por atributo '
            'mejora solo sobre el vocabulario con el que se entrenó, y fuera de '
            'él no se distingue del ruido. Es una mejora de especialización, no '
            'de representación, y se reporta como tal.</p>',
            unsafe_allow_html=True)

    st.markdown('<div style="height:44px;"></div>'
                '<p class="rot-f revela" style="margin-bottom:8px;">El salto de '
                'dominio</p>' +
                _tarjetas(3, [
                    '<h4>Suelo de ruido</h4><p>Dos tomas de la misma prenda '
                    'quedan a 0,991–0,995 de similitud. Dos prendas distintas '
                    'llegan a 0,925–0,951 en el percentil 95. El margen útil '
                    'es de apenas 0,044–0,069: el armario está muy concentrado '
                    'en el espacio.</p>',
                    '<h4>Separabilidad</h4><p>Una sonda lineal distingue '
                    'fotografía de catálogo de fotografía de móvil con AUC '
                    '1,000, frente a un nulo por composición de 0,57–0,64. Los '
                    'dos dominios son trivialmente separables.</p>',
                    '<h4>Caída en la tarea</h4><p>Sobre el conjunto de test '
                    'ninguna caída resulta significativa: los intervalos se '
                    'solapan. Eso es ausencia de evidencia, no evidencia de '
                    'ausencia, y así se reporta.</p>']),
                unsafe_allow_html=True)

    st.markdown('<div style="height:52px;"></div>'
                '<div class="filete revela" style="margin-bottom:14px;"></div>'
                '<p class="rot-f revela" style="margin-bottom:6px;">Lo que no '
                'salió, y se cuenta igual</p>'
                '<p class="cuerpo revela" style="max-width:62ch;'
                'margin-bottom:14px;">Tres cosas que no funcionaron. Están aquí '
                'desplegables porque cada una tiene su diagnóstico, y un '
                'resultado negativo sin diagnóstico no vale nada.</p>',
                unsafe_allow_html=True)

    # Acordeon: convierte tres parrafos apretados en algo que se explora, y
    # es la unica pieza de la web con interaccion real ademas de la cupula.
    for titulo, cuerpo in [
        ("El corpus de atributos resultó ser 81–93 % ropa de mujer",
         "El filtro del análisis exploratorio seleccionaba por nombre de "
         "categoría, y esos nombres —camisa, pantalón, chaqueta— son unisex. "
         "No invalida la comparación entre condiciones, porque las tres vieron "
         "exactamente los mismos datos, pero sí obliga a corregir la "
         "afirmación de alcance que aparecía en las entregas anteriores. Se "
         "declara como cuarto factor de confusión del análisis de dominio y no "
         "se descompone: aislarlo habría costado más de lo que aportaba a dos "
         "semanas de la entrega."),
        ("Etiquetar el género con CLIP sin entrenamiento previo: 29 % frente "
         "a un 89 % de referencia",
         "La afinidad de base de cada clase domina sobre la variación dentro "
         "de la clase: la distancia media al texto de una clase (≈0,04) es "
         "mayor que la desviación típica dentro de ella (≈0,025), así que el "
         "argumento máximo lo decide la clase, no la imagen. Es un fallo de "
         "calibración conocido de CLIP en clasificación sin entrenamiento. Se "
         "reportó y se descartó."),
        ("La hipótesis del fondo quedó falsada",
         "Se sospechaba que la colcha de rayas sobre la que están fotografiadas "
         "las prendas explicaba parte del salto de dominio. Una ablación "
         "recortando el fondo no encontró efecto medible en ningún nivel de "
         "análisis. La hipótesis se descarta y se sustituye por la correlación "
         "con la categoría, que sí aparece en los datos."),
    ]:
        with st.expander(titulo):
            st.markdown(f'<p class="cuerpo revela" style="max-width:74ch;">{cuerpo}'
                        f'</p>', unsafe_allow_html=True)

    st.markdown('<div style="height:44px;"></div>'
                '<p class="rot-f revela" style="margin-bottom:8px;">Lo que el sistema '
                'no hace</p>' +
                _celdas("tres", [
                    '<h4>No compone conjuntos</h4><p>Ordena prendas por '
                    'parecido a una referencia. La compatibilidad entre prendas '
                    'es otro problema y no está implementada.</p>',
                    '<h4>No dice si te favorece</h4><p>No hay modelo de '
                    'adecuación corporal. No existen datos públicos, y uno '
                    'entrenado sobre juicios estéticos de cuerpos aprendería '
                    'sesgos corporales por construcción.</p>',
                    '<h4>No da una probabilidad</h4><p>La barra de cada '
                    'resultado es proximidad relativa dentro de esa lista. Las '
                    'bandas calibradas se midieron sobre catálogo y no se '
                    'aplican a estas fotos.</p>']),
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
                'line-height:21px;">Nada de esta lista está construido. Está '
                'aquí porque se diseñó y se dejó fuera con una razón, no '
                'porque se olvidara — y esa distinción importa tanto como lo '
                'que sí está hecho.</p><div style="height:34px;"></div>',
                unsafe_allow_html=True)

    for titulo, estado, texto in [
        ("Compatibilidad entre prendas", "Diseñado · sin implementar",
         "Un módulo entrenado sobre Polyvore con partición disjunta que "
         "puntúe si dos prendas funcionan juntas. Métricas previstas: "
         "precisión en «rellena el hueco» y AUC. Referencias externas sitúan "
         "el estado del arte en torno al 55–62 % en esa tarea, cifras que "
         "sirven para situar un resultado, no para prometerlo."),
        ("Catálogo comercial y enlace a producto", "Diseñado · sin implementar",
         "Cuando el armario no cubre una posición, recuperar del catálogo la "
         "prenda más próxima y enlazar al producto real. Se almacenarían "
         "embeddings, metadatos y URL. Nunca imágenes: la aplicación las "
         "cargaría desde el servidor de origen."),
        ("Lenguaje natural como entrada", "Diseñado · sin implementar",
         "Un modelo de lenguaje que traduzca «algo parecido pero más "
         "abrigado» a restricciones sobre los metadatos. Seguiría sin decidir "
         "el orden: filtra y explica, no ordena."),
        ("Base de datos y servicio", "Diseñado · sin implementar",
         "PostgreSQL con pgvector resuelve el filtrado relacional y la "
         "búsqueda vectorial en una sola consulta, y FastAPI separa el núcleo "
         "de la interfaz. El diseño está completo en la entrega 3; solo falta "
         "levantarlo."),
        ("Etiquetado asistido al subir", "Diseñado · sin implementar",
         "Hoy cada usuario sube sus prendas y dice qué son; los detalles "
         "(color, corte, tejido) los escribe a mano si quiere. Un modelo de "
         "visión y lenguaje podría proponerlos al subir la foto. Propondría, "
         "no decidiría: el usuario confirma, y la búsqueda sigue comparando "
         "la foto."),
        ("Reducir el salto de dominio", "Línea de investigación abierta",
         "Es lo que este trabajo midió y no resolvió. Las vías razonables son "
         "aumentar los datos de entrenamiento con fotografía de prenda "
         "extendida, o adaptar el dominio con una transformación aprendida "
         "entre ambos tipos de imagen."),
    ]:
        st.markdown(
            f'<div class="revela" style="border-top:1px solid var(--line);'
            f'padding:20px 0 22px 0;display:flex;gap:40px;'
            f'align-items:flex-start;">'
            f'<div style="flex:0 0 250px;">'
            f'<h3 style="font-size:16px;font-weight:400;margin:0;">{titulo}</h3>'
            f'<p class="rot" style="margin-top:7px;">{estado}</p></div>'
            f'<p class="cuerpo revela" style="margin:0;max-width:62ch;">{texto}</p>'
            f'</div>', unsafe_allow_html=True)
    st.markdown(_nav(3),
                unsafe_allow_html=True)

    pie()


# ===========================================================================
# 5. SOBRE EL PROYECTO
# ===========================================================================

def sobre():
    st.markdown('<div style="height:26px;"></div>'
                '<div class="filete revela"></div>'
                '<p class="seccion revela" style="margin-top:20px;">Sobre el '
                'proyecto</p><div style="height:22px;"></div>',
                unsafe_allow_html=True)

    a, b = st.columns([1.3, 1], gap="large")
    with a:
        st.markdown(
            '<p class="cuerpo revela" style="max-width:62ch;font-size:13.5px;'
            'line-height:21px;">Este sistema es el Trabajo de Fin de Máster '
            'del Máster en Data Science y Desarrollo de IA de Evolve Academy. '
            'La pregunta de partida era si se puede consultar el parecido '
            'entre prendas <b>por atributo</b> — parécete al corte, ignora el '
            'color — sobre un backbone visual congelado, y si eso mejora la '
            'recuperación frente a usar el embedding tal cual.</p>'
            # Aqui habia un resumen de los resultados que repetia, con otras
            # palabras, la seccion "Que aporta cada pieza" de la pagina de
            # Resultados. Se queda solo el giro del proyecto, que es contexto
            # y no resultado, y el numero vive en su pagina.
            '<p class="cuerpo revela" style="max-width:62ch;margin-top:14px;'
            'font-size:13.5px;line-height:21px;">A mitad de camino, la '
            'aportación principal cambió: pasó a ser la medición del salto '
            'entre fotografía de catálogo y fotografía real de armario. No fue '
            'una salida improvisada — estaba previsto por escrito desde antes '
            'de tener el primer número, como plan alternativo si la '
            'contribución original no ganaba. No ganó, y el plan se ejecutó.'
            '</p>',
            unsafe_allow_html=True)

        st.markdown('<div style="height:32px;"></div>'
                    '<p class="rot-f revela" style="margin-bottom:8px;">Datos y '
                    'procedencia</p>', unsafe_allow_html=True)
        for fuente, uso, lic in [
            ("DeepFashion · Category and Attribute Prediction",
             "Supervisión de atributos", "CUHK MMLab · uso académico"),
            ("Polyvore Outfits", "Compatibilidad · partición disjunta",
             "CC BY 4.0"),
            ("Fashion Product Images", "Catálogo",
             "Licencia no declarada · riesgo documentado"),
            ("Armario propio · 118 prendas", "Test fuera de distribución",
             "Fotografías del autor"),
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
            '<div class="aviso revela" style="margin-top:18px;max-width:64ch;">'
            '<p class="cuerpo revela">Las imágenes de los conjuntos de datos no se '
            'redistribuyen: el repositorio excluye <code>data/</code> desde el '
            'primer commit. La licencia no declarada de una de las fuentes '
            'queda registrada como riesgo y no sería asumible en un uso '
            'comercial.</p></div>', unsafe_allow_html=True)

    with b:
        st.markdown(
            '<div class="caja revela">'
            '<div class="ini">ID</div>'
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
            '<p class="cuerpo revela">Semillas y versiones de biblioteca fijadas. '
            'Cada corrida deja su configuración en YAML y sus métricas al lado, '
            'en <code>experiments/</code>. Los resultados que aparecen en esta '
            'aplicación se pueden regenerar desde el repositorio.</p>',
            unsafe_allow_html=True)
    st.markdown(_nav(4),
                unsafe_allow_html=True)

    pie()


# ===========================================================================
# 6. ACCESO
# ===========================================================================

def _mi_cuenta():
    """Página de cuenta: datos personales, contraseña y cierre de sesión.

    Qué se puede cambiar y qué no, y por qué:

    - **Nombre**: sí. No identifica la cuenta, solo es cómo se te saluda.
    - **Contraseña**: sí, exigiendo la actual. Ver `auth.cambiar_clave`.
    - **Correo**: no. Es la clave con la que se entra, y cambiarlo de forma
      segura exige verificar el nuevo correo, que esta versión no hace. Sin esa
      verificación, cualquiera con una sesión abierta podría llevarse la cuenta
      a un correo suyo.

    Lo que NO aparece, aunque el esquema de la entrega 3 lo contemple: altura,
    peso y preferencias. Ningún componente del sistema los usa, y pedir datos
    corporales que no se van a usar para nada va contra el principio de
    minimización de datos. Si algún día hay algo que los use, se piden ahí.
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
            nombre = st.text_input("Nombre", value=d["nombre"], key="c_nombre")
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
                ok, msg = auth.actualizar_nombre(BD_USUARIOS, d["id"], nombre)
                if ok:
                    st.session_state["usuario"]["nombre"] = nombre.strip()
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
                        f'{auth.MIN_CLAVE} caracteres</p>',
                        unsafe_allow_html=True)
            st.markdown('<div style="height:10px;"></div>',
                        unsafe_allow_html=True)
            if st.form_submit_button("Cambiar contraseña", type="primary"):
                ok, msg = auth.cambiar_clave(BD_USUARIOS, d["id"], actual,
                                             nueva, repe)
                st.session_state["aviso_cuenta"] = ("ok" if ok else "error", msg)
                st.rerun()

    with der:
        partes = [x for x in d["nombre"].split() if x]
        iniciales = "".join(x[0] for x in partes[:2]).upper() or "·"
        creado = str(d.get("creado") or "")[:10]
        if len(creado) == 10:
            creado = f"{creado[8:10]}/{creado[5:7]}/{creado[:4]}"
        n_prendas = armario.contar(BD_USUARIOS, d["id"])
        resumen = (f"{n_prendas} prenda{'s' if n_prendas != 1 else ''}"
                   if n_prendas else "Vacío")

        st.markdown(
            '<div style="height:26px;"></div>'
            f'<div class="caja revela"><div class="ini">{_html.escape(iniciales)}'
            f'</div><h3 style="font-size:19px;font-weight:400;margin:18px 0 0 0;">'
            f'{_html.escape(d["nombre"])}</h3>'
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
                    u = auth.acceder(BD_USUARIOS, c, p)
                    if u is None:
                        st.markdown('<p class="rot" style="color:var(--burdeos);'
                                    'margin-top:12px;">Correo o contraseña '
                                    'incorrectos.</p>', unsafe_allow_html=True)
                    else:
                        st.session_state["usuario"] = u
                        st.switch_page(destino_tras_entrar(u))

        with t_crear:
            st.markdown('<div style="height:10px;"></div>',
                        unsafe_allow_html=True)
            with st.form("crear", border=False):
                nom = st.text_input("Nombre", key="r_nombre")
                cor = st.text_input("Correo", key="r_correo")
                cl1 = st.text_input("Contraseña", type="password", key="r_c1")
                cl2 = st.text_input("Repite la contraseña", type="password",
                                    key="r_c2")
                st.markdown(f'<p class="rot" style="margin-top:10px;">Mínimo '
                            f'{auth.MIN_CLAVE} caracteres</p>',
                            unsafe_allow_html=True)
                if st.form_submit_button("Crear cuenta", type="primary",
                                         use_container_width=True):
                    err = auth.validar_registro(cor, nom, cl1, cl2)
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
                            armario="propio" if primera else None)
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
            'No hay recuperación de contraseña, verificación de correo ni '
            'limitación de intentos. Cada cuenta tiene su propio armario y solo '
            've el suyo; una cuenta nueva empieza vacía y sube sus prendas '
            'desde Mi armario.</p></div>',
            unsafe_allow_html=True)
    pie()


# ===========================================================================
# 7. BUSCAR
# ===========================================================================

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

    panel, _, res = st.columns([1, 0.06, 3.1], gap="large")

    with panel:
        st.markdown('<div class="panel-busqueda"></div>'
                    '<p class="rot-f" style="margin-bottom:6px;">Tu foto</p>',
                    unsafe_allow_html=True)
        subida = st.file_uploader("Foto de referencia",
                                  type=["jpg", "jpeg", "png", "webp"],
                                  label_visibility="collapsed")
        datos = subida.getvalue() if subida is not None else None
        if datos:
            ref = Image.open(io.BytesIO(datos)).convert("RGB")

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
        tipo = st.segmented_control(
            "Qué hay en la foto", ["persona", "prenda"], default=tipo_def,
            format_func={"persona": "Una persona",
                         "prenda": "Una prenda suelta"}.get,
            key=f"b_tipo_{huella}", label_visibility="collapsed") or tipo_def

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
        st.image(ref, width="stretch")

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
    umbrales = busqueda.umbrales_color() if busqueda.ORDEN_COLOR else None
    labs = arm[["color_l", "color_a", "color_b"]].to_numpy(dtype=float)
    etqs = arm["etiquetas"].tolist()
    # Ajustes pedidos en lenguaje natural para ESTA foto («de manga larga»).
    clave_aj = f"b_ajustes_{huella}"
    ajustes = st.session_state.setdefault(clave_aj, [])
    columnas = []
    for p in elegidas:
        caja = None
        if tipo == "persona":
            caja = cajas["abajo"] if p == "abajo" else cajas["arriba"]
        idx, _ = busqueda.ordenar(V_arm, pos_arm, busqueda.vector(datos, caja),
                                  p, ruta)
        leido = None
        if umbrales:
            from paginas import color
            lab_ref = (color.color_persona(busqueda.recortar(ref, caja), p)[0]
                       if caja is not None else color.color_prenda(ref)[0])
            idx = busqueda.ordenar_por_color(idx, labs, lab_ref, umbrales)
            leido = (color.nombre_color(lab_ref), color.lab_a_rgb(lab_ref))
        # Etiquetas: lo que la IA ve en esta posición, con los ajustes que
        # haya pedido el usuario. Un ajuste explícito ordena SIEMPRE por
        # etiquetas: es una petición del usuario, no una conjetura.
        from paginas import etiquetas as _etq
        pz = (_etq.pieza(etq_ref, p) if tipo == "persona"
              else (etq_ref["piezas"][0] if etq_ref and etq_ref.get("piezas") else None))
        for aj in ajustes:
            pz = _etq.aplicar_ajuste(pz, p, aj)
        if pz and (busqueda.ORDEN_ETIQUETAS or ajustes):
            idx = busqueda.ordenar_por_etiquetas(idx, etqs, pz)
        filas = [arm.iloc[int(i)]
                 for i in idx[:1 + busqueda.ALTERNATIVAS + busqueda.MAS]]
        uri = (busqueda.uri_pil(busqueda.recortar(ref, caja), 300)
               if caja is not None else None)
        columnas.append(busqueda.html_columna(p, filas, uri, leido))

    with res:
        titulo = ("Tu versión de este look" if tipo == "persona"
                  else "Lo más parecido en tu armario")
        st.markdown(f'<div class="filete"></div>'
                    f'<p class="seccion" style="margin-top:16px;">{titulo}</p>'
                    + busqueda.html_resultado(columnas),
                    unsafe_allow_html=True)

        # ------------------------------------------------ ajuste en palabras
        # La IA traduce la petición a cambios sobre lo buscado («manga
        # larga», «más oscuro») y se vuelve a ordenar. No elige prendas.
        if etq_ref is not None:
            st.markdown('<div style="height:34px;"></div>'
                        '<p class="rot-f" style="margin-bottom:6px;">¿Algo '
                        'distinto?</p>', unsafe_allow_html=True)
            with st.form(f"b_form_{huella}", border=False, clear_on_submit=True):
                c1, c2 = st.columns([4, 1], vertical_alignment="bottom")
                texto = c1.text_input(
                    "Pídelo", label_visibility="collapsed",
                    placeholder="Por ejemplo: de manga larga, más oscuro, "
                                "sin estampado, un vaquero corto…")
                enviar = c2.form_submit_button("Ajustar", type="primary",
                                               use_container_width=True)
            if enviar and texto.strip():
                import json as _json
                with st.spinner("Entendiendo lo que pides…"):
                    aj = busqueda.interpretar(
                        texto.strip(), _json.dumps(etq_ref.get("piezas", []),
                                                   ensure_ascii=False))
                if aj and aj.get("entendido"):
                    ajustes.append(aj)
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
                c1, c2 = st.columns([4, 1], vertical_alignment="center")
                c1.markdown(f'<p class="nota-form" style="margin:0;"><b>Ajustado:'
                            f'</b> {_html.escape(", ".join(cambios))}</p>',
                            unsafe_allow_html=True)
                if c2.button("Quitar ajustes", type="tertiary",
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
            ("Polyvore Outfits", "https://github.com/xthan/polyvore-dataset"),
        ]),
        ("Límites", [("Sin composición de conjuntos", None),
                     ("Sin adecuación corporal", None),
                     ("Sin etiquetado automático", None)]),
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
