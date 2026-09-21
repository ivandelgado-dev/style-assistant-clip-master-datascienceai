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

import html as _html

import numpy as np
import streamlit as st
import streamlit.components.v1 as componentes
from PIL import Image

from paginas import auth, cupula
from paginas.nucleo import (BD_USUARIOS, CIFRAS, DIMENSIONES, cargar_armario,
                            cargar_clip, cargar_segundas_tomas, encajar,
                            exige_sesion, nube_para_cupula, proyectar, rejilla,
                            usuario)

# Rellenado por app.py: las páginas se necesitan para `st.switch_page`.
PAGINAS: dict = {}


def _celdas(clase: str, trozos: list[str]) -> str:
    return (f'<div class="{clase}">' +
            "".join(f'<div class="celda">{t}</div>' for t in trozos) +
            '</div>')


# ===========================================================================
# 1. INICIO
# ===========================================================================

def inicio():
    _, arm = cargar_armario()
    n = len(arm) if arm is not None else 0

    st.markdown(
        '<div class="heroe">'
        '<h1>Ya lo tienes.<br>Solo hay que encontrarlo.</h1>'
        '<p>Subes la foto de una prenda que has visto y Akin ordena tu armario '
        'por parecido a ella. Por el conjunto, o por una sola dimensión: el '
        'corte, la textura o el tejido.</p></div>', unsafe_allow_html=True)

    # El boton estaba en la PRIMERA columna de las tres, no en la del medio.
    _, c, _ = st.columns([2, 1.2, 2])
    with c:
        st.markdown('<div style="height:26px;"></div>', unsafe_allow_html=True)
        if st.button("Entrar en la aplicación", type="primary",
                     use_container_width=True):
            st.switch_page(PAGINAS["acceso"])

    # --- el héroe: embeddings reales, no una animación decorativa ---------
    dentro = usuario() is not None
    malla, rellenar, explicada = nube_para_cupula(dentro)
    if malla:
        st.markdown('<div style="height:54px;"></div>', unsafe_allow_html=True)
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
        '<p class="seccion" style="text-align:center;">Por qué una esfera</p>'
        '<p class="cuerpo" style="max-width:58ch;margin:0 auto;'
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

    st.markdown('<div style="height:56px;"></div>'
                '<p class="rot-f" style="margin-bottom:8px;">Cómo funciona</p>' +
                _celdas("tres", [
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
                    'prendas se ordenan por similitud coseno. La decisión es '
                    'reproducible y medible: ningún modelo de lenguaje '
                    'interviene en el orden.</p>']),
                unsafe_allow_html=True)

    st.markdown('<div style="height:52px;"></div>'
                '<p class="rot-f" style="margin-bottom:8px;">Lo que se ha '
                'medido</p>' +
                _celdas("cuatro",
                        [f'<div class="v">{v}</div><p>{t}</p>'
                         f'<span class="f">docs/{f}</span>'
                         for v, t, f in CIFRAS]),
                unsafe_allow_html=True)

    st.markdown('<div style="height:52px;"></div>'
                '<p class="rot-f" style="margin-bottom:8px;">Estado del '
                'proyecto</p>'
                '<div class="aviso" style="max-width:66ch;">'
                '<p class="cuerpo">Primera versión. Es el prototipo de un '
                'Trabajo de Fin de Máster, no un producto: se evalúa la '
                'calidad del ordenamiento, y las partes que no afectan a esa '
                'medida están deliberadamente fuera. La página de '
                '<b>resultados y límites</b> detalla qué funciona, con cuánta '
                'confianza, y qué no se ha construido.</p></div>',
                unsafe_allow_html=True)

    pie(f"{n} prendas digitalizadas")


# ===========================================================================
# 2. EL SISTEMA
# ===========================================================================

def sistema():
    st.markdown('<div style="height:26px;"></div>'
                '<div class="filete"></div>'
                '<p class="seccion" style="margin-top:20px;">El sistema por '
                'dentro</p>'
                '<p class="cuerpo" style="max-width:62ch;font-size:13.5px;'
                'line-height:21px;">Todo el recorrido, desde una fotografía '
                'hasta una lista ordenada. Cada pieza está aquí porque mejora '
                'una métrica o porque sostiene una decisión; ninguna está por '
                'completar el diagrama.</p>'
                '<div style="height:34px;"></div>', unsafe_allow_html=True)

    st.markdown('<p class="rot-f" style="margin-bottom:8px;">La tubería</p>' +
                _celdas("cuatro", [
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
                '<p class="rot-f" style="margin-bottom:8px;">Decisiones que '
                'hay que poder defender</p>' +
                _celdas("tres", [
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

    st.markdown('<div style="height:48px;"></div>'
                '<p class="rot-f" style="margin-bottom:8px;">El papel del '
                'modelo de lenguaje</p>'
                '<div class="aviso" style="max-width:70ch;">'
                '<p class="cuerpo">Un LLM puede traducir una petición en '
                'lenguaje natural a restricciones, y puede redactar la '
                'explicación de un resultado. Lo que <b>no</b> hace en ningún '
                'punto es elegir qué prenda sale ni en qué orden. Esa decisión '
                'tiene que ser reproducible y evaluable, y una decisión tomada '
                'por un modelo de lenguaje no lo es: dos ejecuciones pueden '
                'diferir y no hay métrica que las compare.</p></div>',
                unsafe_allow_html=True)

    st.markdown('<div style="height:48px;"></div>'
                '<p class="rot-f" style="margin-bottom:10px;">Herramientas'
                '</p>', unsafe_allow_html=True)
    a, b = st.columns(2, gap="large")
    with a:
        for k, v in [("Backbone", "CLIP ViT-B/32 · HuggingFace"),
                     ("Entrenamiento", "PyTorch · pérdida contrastiva"),
                     ("Datos", "pandas · NumPy · parquet"),
                     ("Evaluación", "scikit-learn · bootstrap propio")]:
            st.markdown(f'<div class="dato"><span>{k}</span><span>{v}</span>'
                        f'</div>', unsafe_allow_html=True)
    with b:
        for k, v in [("Interfaz", "Streamlit"),
                     ("Diseño previsto", "FastAPI · PostgreSQL + pgvector"),
                     ("Reproducibilidad", "semillas y versiones fijadas"),
                     ("Configuración", "un YAML por corrida en experiments/")]:
            st.markdown(f'<div class="dato"><span>{k}</span><span>{v}</span>'
                        f'</div>', unsafe_allow_html=True)

    pie()


# ===========================================================================
# 3. RESULTADOS Y LÍMITES
# ===========================================================================

def resultados():
    st.markdown('<div style="height:26px;"></div>'
                '<div class="filete"></div>'
                '<p class="seccion" style="margin-top:20px;">Resultados y '
                'límites</p>'
                '<p class="cuerpo" style="max-width:62ch;font-size:13.5px;'
                'line-height:21px;">Lo que el sistema hace bien, lo que hace '
                'mal y lo que no se puede afirmar con los datos que hay. Los '
                'resultados negativos están aquí con el mismo detalle que los '
                'positivos: un resultado negativo bien medido es un '
                'resultado.</p><div style="height:34px;"></div>',
                unsafe_allow_html=True)

    st.markdown('<p class="rot-f" style="margin-bottom:10px;">Qué aporta cada '
                'pieza</p>', unsafe_allow_html=True)
    a, b = st.columns(2, gap="large")
    with a:
        st.markdown(
            '<p class="rot" style="margin-bottom:6px;">Proyección supervisada '
            'frente a CLIP sin proyección · NDCG@10</p>'
            '<div class="dato"><span>Atributos vistos al entrenar</span>'
            '<span><b>+0,0217</b> · significativo</span></div>'
            '<div class="dato"><span>Atributos no vistos</span>'
            '<span><b>+0,0132</b> · significativo</span></div>'
            '<p class="cuerpo" style="margin-top:12px;">Supervisar el espacio '
            'funciona, y la mejora sobrevive a vocabulario que el modelo no vio '
            'al entrenar. Ese segundo número es el que importa: sin él, la '
            'mejora podría ser memorización.</p>', unsafe_allow_html=True)
    with b:
        st.markdown(
            '<p class="rot" style="margin-bottom:6px;">Cabezas por atributo '
            'frente a proyección conjunta</p>'
            '<div class="dato"><span>Atributos vistos</span>'
            '<span>+0,0035</span></div>'
            '<div class="dato"><span>Atributos no vistos</span>'
            '<span>−0,0058 · no significativo</span></div>'
            '<p class="cuerpo" style="margin-top:12px;">La contribución '
            'original del trabajo <b>no gana</b>. Desacoplar por atributo '
            'mejora solo sobre el vocabulario con el que se entrenó, y fuera de '
            'él no se distingue del ruido. Es una mejora de especialización, no '
            'de representación, y se reporta como tal.</p>',
            unsafe_allow_html=True)

    st.markdown('<div style="height:44px;"></div>'
                '<p class="rot-f" style="margin-bottom:8px;">El salto de '
                'dominio</p>' +
                _celdas("tres", [
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

    st.markdown('<div style="height:44px;"></div>'
                '<p class="rot-f" style="margin-bottom:8px;">Lo que no salió, '
                'y se cuenta igual</p>' +
                _celdas("tres", [
                    '<h4>Composición del corpus</h4><p>El corpus de atributos '
                    'resultó ser 81–93 % ropa de mujer. El filtro seleccionaba '
                    'por nombre de categoría, y esos nombres son unisex. No '
                    'invalida la comparación entre condiciones —todas vieron '
                    'los mismos datos— pero obliga a corregir la afirmación de '
                    'alcance.</p>',
                    '<h4>Etiquetado de género con CLIP</h4><p>Un clasificador '
                    'sin entrenamiento previo alcanzó un 29 % frente a un 89 % '
                    'de referencia. La afinidad de base por clase domina sobre '
                    'la variación dentro de clase. Se descartó.</p>',
                    '<h4>La hipótesis del fondo</h4><p>Se sospechaba que la '
                    'colcha de fondo explicaba parte del salto de dominio. Una '
                    'ablación con recorte no encontró efecto medible en ningún '
                    'nivel. Hipótesis falsada y sustituida.</p>']),
                unsafe_allow_html=True)

    st.markdown('<div style="height:44px;"></div>'
                '<p class="rot-f" style="margin-bottom:8px;">Lo que el sistema '
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
    pie()


# ===========================================================================
# 4. HACIA DÓNDE VA
# ===========================================================================

def futuro():
    st.markdown('<div style="height:26px;"></div>'
                '<div class="filete"></div>'
                '<p class="seccion" style="margin-top:20px;">Hacia dónde '
                'va</p>'
                '<p class="cuerpo" style="max-width:62ch;font-size:13.5px;'
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
        ("Subida de prendas por el usuario", "Necesario para ser producto",
         "Hoy solo existe un armario digitalizado. Para que la aplicación "
         "sirva a alguien más hace falta que cada usuario pueda fotografiar y "
         "etiquetar el suyo, con el etiquetado asistido por un modelo."),
        ("Reducir el salto de dominio", "Línea de investigación abierta",
         "Es lo que este trabajo midió y no resolvió. Las vías razonables son "
         "aumentar los datos de entrenamiento con fotografía de prenda "
         "extendida, o adaptar el dominio con una transformación aprendida "
         "entre ambos tipos de imagen."),
    ]:
        st.markdown(
            f'<div style="border-top:1px solid var(--line);padding:20px 0 '
            f'22px 0;display:flex;gap:40px;align-items:flex-start;">'
            f'<div style="flex:0 0 250px;">'
            f'<h3 style="font-size:16px;font-weight:400;margin:0;">{titulo}</h3>'
            f'<p class="rot" style="margin-top:7px;">{estado}</p></div>'
            f'<p class="cuerpo" style="margin:0;max-width:62ch;">{texto}</p>'
            f'</div>', unsafe_allow_html=True)
    pie()


# ===========================================================================
# 5. SOBRE EL PROYECTO
# ===========================================================================

def sobre():
    st.markdown('<div style="height:26px;"></div>'
                '<div class="filete"></div>'
                '<p class="seccion" style="margin-top:20px;">Sobre el '
                'proyecto</p><div style="height:22px;"></div>',
                unsafe_allow_html=True)

    a, b = st.columns([1.3, 1], gap="large")
    with a:
        st.markdown(
            '<p class="cuerpo" style="max-width:62ch;font-size:13.5px;'
            'line-height:21px;">Este sistema es el Trabajo de Fin de Máster '
            'del Máster en Data Science y Desarrollo de IA de Evolve Academy. '
            'La pregunta de partida era si se puede consultar el parecido '
            'entre prendas <b>por atributo</b> — parécete al corte, ignora el '
            'color — sobre un backbone visual congelado, y si eso mejora la '
            'recuperación frente a usar el embedding tal cual.</p>'
            '<p class="cuerpo" style="max-width:62ch;margin-top:14px;'
            'font-size:13.5px;line-height:21px;">La respuesta corta es que '
            'supervisar el espacio sí mejora, y que desacoplarlo por atributo '
            'no lo hace de forma que sobreviva fuera del vocabulario de '
            'entrenamiento. A partir de ahí, la aportación principal pasó a '
            'ser la medición del salto entre fotografía de catálogo y '
            'fotografía real de armario — un plan previsto desde antes de '
            'tener el primer número, no una salida improvisada.</p>',
            unsafe_allow_html=True)

        st.markdown('<div style="height:32px;"></div>'
                    '<p class="rot-f" style="margin-bottom:8px;">Datos y '
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
            st.markdown(f'<div class="dato"><span>{fuente}</span>'
                        f'<span>{uso}</span></div>'
                        f'<p class="rot" style="margin:-6px 0 10px 0;'
                        f'font-size:10px;">{lic}</p>', unsafe_allow_html=True)

        st.markdown(
            '<div class="aviso" style="margin-top:18px;max-width:64ch;">'
            '<p class="cuerpo">Las imágenes de los conjuntos de datos no se '
            'redistribuyen: el repositorio excluye <code>data/</code> desde el '
            'primer commit. La licencia no declarada de una de las fuentes '
            'queda registrada como riesgo y no sería asumible en un uso '
            'comercial.</p></div>', unsafe_allow_html=True)

    with b:
        st.markdown(
            '<div class="caja">'
            '<div class="ini">ID</div>'
            '<h3 style="font-size:19px;font-weight:400;margin:18px 0 0 0;">'
            'Iván Delgado</h3>'
            '<p class="rot" style="margin-top:7px;">Autor · desarrollo, '
            'experimentación y análisis</p>'
            '<div style="height:16px;"></div>'
            '<div class="dato"><span>Programa</span><span>Máster en Data '
            'Science y Desarrollo de IA</span></div>'
            '<div class="dato"><span>Centro</span><span>Evolve Academy</span>'
            '</div>'
            '<div class="dato"><span>Curso</span><span>2026</span></div>'
            '<div class="dato" style="border-bottom:none;"><span>Versión</span>'
            '<span>Primera · prototipo</span></div>'
            '</div>', unsafe_allow_html=True)

        st.markdown(
            '<div style="height:24px;"></div>'
            '<p class="rot-f" style="margin-bottom:8px;">Reproducibilidad</p>'
            '<p class="cuerpo">Semillas y versiones de biblioteca fijadas. '
            'Cada corrida deja su configuración en YAML y sus métricas al lado, '
            'en <code>experiments/</code>. Los resultados que aparecen en esta '
            'aplicación se pueden regenerar desde el repositorio.</p>',
            unsafe_allow_html=True)
    pie()


# ===========================================================================
# 6. ACCESO
# ===========================================================================

def acceso():
    if usuario():
        u = usuario()
        st.markdown(f'<div style="height:40px;"></div>'
                    f'<div class="filete"></div>'
                    f'<p class="seccion" style="margin-top:18px;">Hola, '
                    f'{_html.escape(u["nombre"].split()[0])}</p>'
                    f'<p class="cuerpo" style="max-width:56ch;">Ya has '
                    f'entrado. La sesión vive mientras no recargues la '
                    f'página.</p>', unsafe_allow_html=True)
        a, b, _ = st.columns([1, 1, 3])
        with a:
            if st.button("Ir a buscar", type="primary", use_container_width=True):
                st.switch_page(PAGINAS["buscar"])
        with b:
            if st.button("Cerrar sesión", use_container_width=True):
                del st.session_state["usuario"]
                st.rerun()
        pie()
        return

    izq, der = st.columns([1, 1.15], gap="large")

    with izq:
        st.markdown('<div style="height:34px;"></div>'
                    '<div class="filete"></div>'
                    '<p class="seccion" style="margin-top:18px;">Acceder</p>',
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
                        st.switch_page(PAGINAS["buscar"])

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
                        # La primera cuenta se queda el único armario
                        # digitalizado que existe. Ver paginas/auth.py.
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
                            st.session_state["usuario"] = auth.acceder(
                                BD_USUARIOS, cor, cl1)
                            st.switch_page(PAGINAS["buscar"])

    with der:
        st.markdown(
            '<div style="height:60px;"></div>'
            '<p class="rot-f" style="margin-bottom:10px;">Qué pasa con tu '
            'contraseña</p>'
            '<p class="cuerpo" style="max-width:54ch;">No se guarda. Se guarda '
            'el resultado de aplicarle <code>scrypt</code> con una sal '
            'aleatoria distinta para cada cuenta. <code>scrypt</code> es una '
            'función de derivación con coste de memoria: a diferencia de un '
            'hash rápido, encarece deliberadamente el ataque por fuerza bruta. '
            'La comparación se hace en tiempo constante para no filtrar '
            'información por la duración de la respuesta.</p>'
            '<p class="cuerpo" style="max-width:54ch;margin-top:14px;">El '
            'almacén es un fichero SQLite local que el repositorio excluye. '
            'Nada sale de tu máquina.</p>'
            '<div class="aviso" style="margin-top:22px;max-width:54ch;">'
            '<p class="cuerpo"><b>Límites declarados.</b> La sesión no '
            'sobrevive a recargar la página: mantenerla exigiría una cookie '
            'firmada, y Streamlit no expone cookies sin un componente externo. '
            'No hay recuperación de contraseña, verificación de correo ni '
            'limitación de intentos. Y solo existe un armario digitalizado, el '
            'del autor: una cuenta nueva entra sin prendas propias y puede '
            'explorar ese armario en modo demostración.</p></div>',
            unsafe_allow_html=True)
    pie()


# ===========================================================================
# 7. BUSCAR
# ===========================================================================

def buscar():
    V, arm = cargar_armario()
    if V is None:
        st.markdown('<div style="height:40px;"></div>'
                    '<p class="cuerpo">No hay embeddings del armario. Lánzalo '
                    'una vez:<br><br><code>python src/embeddings_clip.py '
                    '--carpeta data/raw/wardrobe/img --out '
                    'data/embeddings_armario</code></p>',
                    unsafe_allow_html=True)
        return

    if not exige_sesion(PAGINAS["acceso"]):
        return

    u = usuario()
    if not u.get("armario") and not st.session_state.get("demo"):
        st.markdown(
            '<div style="height:50px;"></div><div class="filete"></div>'
            '<p class="seccion" style="margin-top:18px;">Tu armario está '
            'vacío</p>'
            '<p class="cuerpo" style="max-width:60ch;font-size:13.5px;'
            'line-height:21px;">La subida y el etiquetado de prendas no están '
            'implementados en esta versión: forman parte del trabajo '
            'pendiente. El único armario digitalizado es el del autor, 118 '
            'prendas fotografiadas como conjunto de test fuera de '
            'distribución.</p>', unsafe_allow_html=True)
        c, _ = st.columns([1.2, 3])
        with c:
            st.markdown('<div style="height:20px;"></div>',
                        unsafe_allow_html=True)
            if st.button("Explorar el armario de demostración",
                         type="primary", use_container_width=True):
                st.session_state["demo"] = True
                st.rerun()
        pie()
        return

    if st.session_state.get("demo"):
        st.markdown('<div class="aviso" style="margin:10px 0 18px 0;">'
                    '<p class="cuerpo">Estás viendo el armario de '
                    'demostración, que no es tuyo.</p></div>',
                    unsafe_allow_html=True)

    segundas = cargar_segundas_tomas()

    nav, _ = st.columns([2, 1])
    with nav:
        dim = st.radio("dim", list(DIMENSIONES), horizontal=True,
                       label_visibility="collapsed")
    st.markdown('<div class="regla" style="margin:8px 0 16px 0;"></div>',
                unsafe_allow_html=True)

    c_sub, c_k, c_cmp = st.columns([3, 1, 1], gap="large")
    with c_sub:
        subida = st.file_uploader("Imagen de referencia",
                                  type=["jpg", "jpeg", "png", "webp"])
    with c_k:
        k = st.slider("Resultados", 3, 24, 9)
    with c_cmp:
        crudo = st.checkbox("Comparar con CLIP sin proyección")

    if subida is None:
        st.markdown(
            f'<div style="padding:56px 0 0 0;max-width:62ch;">'
            f'<p class="titular">Sube una referencia</p>'
            f'<p class="cuerpo" style="margin-top:12px;">El sistema ordena las '
            f'{len(arm)} prendas por proximidad a esa imagen, en la dimensión '
            f'que elijas arriba. Pasa el cursor por cualquier resultado para '
            f'ver la segunda fotografía de esa prenda.</p></div>',
            unsafe_allow_html=True)
        return

    proc, modelo, extraer = cargar_clip()
    import torch
    ref = Image.open(subida).convert("RGB")
    with torch.no_grad():
        px = proc(images=ref, return_tensors="pt")["pixel_values"]
        v_ref = extraer(modelo.get_image_features(pixel_values=px)).numpy()

    V_arm = V[arm["pos"].to_numpy()]

    def ranking(ruta):
        return proyectar(V_arm, ruta) @ proyectar(v_ref, ruta)[0]

    ruta = DIMENSIONES[dim] if DIMENSIONES[dim].exists() else None
    if ruta is None:
        st.markdown(f'<p class="rot">Sin checkpoint para «{dim}»: se usa CLIP '
                    f'sin proyección.</p>', unsafe_allow_html=True)
    sim = ranking(ruta)
    orden = np.argsort(-sim)[:k]

    izq, der = st.columns([1, 3.4], gap="large")
    with izq:
        st.markdown('<p class="rot">Referencia</p>', unsafe_allow_html=True)
        st.image(encajar(ref), use_container_width=True)
        st.markdown(f'<p class="rot" style="margin-top:10px;">{len(arm)} '
                    f'prendas comparadas</p><p class="rot" '
                    f'style="margin-top:2px;">Orden por {dim.lower()}</p>',
                    unsafe_allow_html=True)
    with der:
        st.markdown(f'<p class="rot-f">Más próximas · {dim}</p>',
                    unsafe_allow_html=True)
        st.markdown(rejilla(orden, arm, sim, segundas), unsafe_allow_html=True)
        if crudo:
            sim2 = ranking(None)
            o2 = np.argsort(-sim2)[:k]
            coincide = len(set(orden.tolist()) & set(o2.tolist()))
            st.markdown(
                f'<div class="regla" style="margin:40px 0 16px 0;"></div>'
                f'<p class="rot-f">CLIP sin proyección</p>'
                f'<p class="cuerpo" style="max-width:64ch;">Comparten '
                f'{coincide} de {k} resultados con la proyección entrenada. Las '
                f'diferencias son lo que aporta la proyección supervisada.</p>',
                unsafe_allow_html=True)
            st.markdown(rejilla(o2, arm, sim2, segundas, densa=True),
                        unsafe_allow_html=True)

    st.markdown('<div class="regla" style="margin:44px 0 20px 0;"></div>' +
                _celdas("tres", [
                    '<h4>Cómo se ha ordenado</h4><p>CLIP ViT-B/32 congelado '
                    'más una proyección supervisada de 128 dimensiones. El '
                    'orden es por similitud coseno. Ningún LLM interviene.</p>',
                    '<h4>La barra no es una probabilidad</h4><p>Indica '
                    'proximidad relativa dentro de estos resultados. Las bandas '
                    'calibradas se midieron sobre fotografía de catálogo, no '
                    'sobre estas fotos.</p>',
                    '<h4>Limitación conocida</h4><p>El modelo se entrenó con '
                    'fotografía de catálogo sobre cuerpo; estas son prendas '
                    'planas de móvil. Esa distancia es lo que mide el análisis '
                    'de salto de dominio.</p>']),
                unsafe_allow_html=True)
    pie()


# ===========================================================================

def pie(extra: str = ""):
    st.markdown(
        f'<div class="pie-pag">'
        f'<p>Asistente de Estilo · primera versión<br>'
        f'Trabajo de Fin de Máster · Evolve Academy · 2026</p>'
        f'<p style="text-align:right;">Prototipo académico, no un producto'
        f'{("<br>" + _html.escape(extra)) if extra else ""}</p></div>',
        unsafe_allow_html=True)
