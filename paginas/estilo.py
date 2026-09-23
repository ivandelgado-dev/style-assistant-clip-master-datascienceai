"""
Sistema visual de la aplicación.

De dónde sale
-------------
Dos referencias, y no se mezclan a partes iguales porque son opuestas:

- **Zara / Pull&Bear / Bershka** (especificación medida, 16/09/2026). Su fuerza
  está en que la fotografía lo hace todo y la tipografía desaparece: una sola
  familia sans, tracking casi nulo, sin sombras, sin radios, y el estado activo
  marcado con PESO y nunca con color.
- **Evolve** (portada). Su fuerza es la contraria: no hay fotografía, y el peso
  lo llevan un titular enorme centrado y un gráfico abstracto.

Manda Evolve en la estructura de la portada, por una razón concreta y no de
gusto: este proyecto **no tiene fotografía de moda**. Tiene prendas extendidas
sobre una colcha. Eso no sostiene un héroe a sangre como el de Zara. La receta
de Evolve — titular grande, medida estrecha, un solo gráfico — es precisamente
la que funciona cuando no hay imagen que poner.

Manda Zara en la disciplina tipográfica de todo lo demás, y en dos reglas que
se respetan incluso donde Evolve haría otra cosa: **sin radios** (Evolve usa
botones de píldora) y **activo por peso**. La paleta es la propia, la misma del
chatbot del módulo de IA Generativa.

Contraste
---------
Los tonos apagados están elegidos para cumplir WCAG AA sobre el fondo base
(#F7F3EC): --faint #756E66 da 4,54:1 y --muted #5A5651 da 6,6:1, ambos por
encima del 4,5:1 exigido para texto normal.
"""

CSS = """
<style>
  :root{
    --base:#F7F3EC; --plate:#EFEAE0; --plate2:#E3DACB; --line:#DED3C3;
    --burdeos:#7B2D40; --ink:#1C1B1A; --muted:#5A5651; --faint:#756E66;
  }

  /* ---- lienzo -------------------------------------------------------- */
  .stApp{background:var(--base);}
  html, body, [class*="css"]{font-family:Helvetica,Arial,sans-serif;color:var(--ink);}
  #MainMenu, footer, header{visibility:hidden;}
  .block-container{padding:0.4rem 56px 90px 56px !important;max-width:100% !important;}
  div[data-testid="stVerticalBlock"]{gap:0.6rem;}
  iframe{border:none;background:transparent;}

  /* ---- barra superior (estructura de Evolve, reglas de Zara) --------- */
  .marca{height:42px;display:flex;align-items:center;}
  .marca img{height:19px;width:auto;display:block;}
  .regla-fuerte{height:1px;background:var(--ink);margin:0 0 4px 0;}
  .regla{height:1px;background:var(--line);}

  /* El subrayado va en el <a> y no en el contenedor: asi abraza la palabra
     en vez de ocupar toda la columna. El estado activo se marca con PESO
     (regla medida en Zara) mas subrayado (como Bershka); nunca con color. */
  div[data-testid="stPageLink"] a{
    padding:0 0 7px 0 !important;background:transparent !important;
    border-radius:0 !important;width:fit-content !important;
    border-bottom:2px solid transparent !important;
    transition:border-color .2s ease;}
  /* El subrayado de la pestana activa NO se decide aqui: Streamlit no marca
     cual esta activa en el DOM. La regla la emite app.py en cada recarga,
     apuntando al href de la pagina actual. Ver el comentario de alli. */

  /* Los tres bloques de la barra se alinean contra una fila de 42px, que es
     el alto del boton. Sin esto cada uno cae a su aire. */
  div[data-testid="stPageLink"]{height:42px;display:flex;align-items:center;}
  div[data-testid="stPageLink"] a p{
    font-size:12px !important;letter-spacing:.4px;text-transform:uppercase;
    color:var(--faint) !important;margin:0 !important;font-weight:400 !important;
    transition:color .2s ease;white-space:nowrap;
  }
  div[data-testid="stPageLink"] a:hover p{color:var(--ink) !important;}
  div[data-testid="stPageLink"] a[aria-current] p,
  div[data-testid="stPageLink"] a[aria-current="page"] p{
    color:var(--ink) !important;font-weight:700 !important;
  }

  /* ---- navegación de dimensiones (st.radio) --------------------------- */
  div[data-testid="stRadio"] > label{display:none;}
  div[data-testid="stRadio"] div[role="radiogroup"]{
    flex-direction:row !important;gap:30px !important;align-items:center;}
  div[data-testid="stRadio"] div[role="radiogroup"] label{margin:0 !important;padding:0 !important;}
  /* El circulo. La estructura real del label es:
       label > span(input oculto) + div(envoltorio) > div(circulo) + div(texto)
     El primer hijo del label es el SPAN, no un div: una regla sobre
     `label > div:first-child` no llega a coincidir con nada. */
  div[data-testid="stRadio"] label > div > div:first-child{display:none !important;}
  div[data-testid="stRadio"] label > div{gap:0 !important;}
  div[data-testid="stRadio"] div[role="radiogroup"] label p{
    font-size:12px !important;letter-spacing:.4px;text-transform:uppercase;
    color:var(--faint) !important;margin:0 !important;transition:color .2s ease;}
  div[data-testid="stRadio"] div[role="radiogroup"] label:hover p{color:var(--ink) !important;}
  div[data-testid="stRadio"] label[data-selected="true"] p,
  div[data-testid="stRadio"] label:has(input:checked) p{
    color:var(--ink) !important;font-weight:700 !important;}

  /* ---- controles ------------------------------------------------------ */
  section[data-testid="stFileUploaderDropzone"]{
    background:transparent;border:none;border-bottom:1px solid var(--line);
    border-radius:0;padding:6px 0;min-height:0;}
  section[data-testid="stFileUploaderDropzone"]:hover{border-bottom-color:var(--ink);}
  div[data-testid="stFileUploader"] label,
  div[data-testid="stSlider"] label, div[data-testid="stCheckbox"] label p,
  div[data-testid="stTextInput"] label p{
    font-size:11px !important;letter-spacing:.4px;text-transform:uppercase;
    color:var(--faint) !important;}
  [data-testid="stFileUploaderDropzoneInstructions"]{display:none !important;}

  /* Campos de texto: linea inferior, como el buscador de Pull&Bear. */
  div[data-testid="stTextInput"] div[data-baseweb="input"],
  div[data-testid="stTextInput"] div[data-baseweb="base-input"]{
    background:transparent !important;border:none !important;
    border-bottom:1px solid var(--line) !important;border-radius:0 !important;}
  div[data-testid="stTextInput"] div[data-baseweb="input"]:focus-within{
    border-bottom-color:var(--ink) !important;}
  div[data-testid="stTextInput"] input{
    background:transparent !important;font-size:13px !important;
    padding-left:0 !important;color:var(--ink) !important;}

  button[data-testid="stBaseButton-primary"]{
    background:var(--ink) !important;border:1px solid var(--ink) !important;
    color:var(--base) !important;border-radius:0 !important;box-shadow:none !important;
    font-size:11px !important;letter-spacing:.6px;text-transform:uppercase;height:42px;}
  button[data-testid="stBaseButton-primary"]:hover{
    background:var(--burdeos) !important;border-color:var(--burdeos) !important;}
  button[data-testid="stBaseButton-secondary"]{
    background:transparent !important;border:1px solid var(--ink) !important;
    color:var(--ink) !important;border-radius:0 !important;box-shadow:none !important;
    font-size:11px !important;letter-spacing:.6px;text-transform:uppercase;height:42px;}
  button[data-testid="stBaseButton-secondary"]:hover{
    background:var(--ink) !important;color:var(--base) !important;}
  div[data-testid="stTabs"] button{border-radius:0 !important;}
  div[data-testid="stTabs"] button p{
    font-size:11px !important;letter-spacing:.5px;text-transform:uppercase;}

  /* ---- tipografía ------------------------------------------------------ */
  .rot{font-size:11px;letter-spacing:.4px;text-transform:uppercase;color:var(--faint);margin:0;}
  .rot-f{font-size:11px;letter-spacing:.4px;text-transform:uppercase;color:var(--ink);
         font-weight:700;margin:0;}
  .cuerpo{font-size:12.5px;line-height:19px;color:var(--muted);text-wrap:pretty;}
  .titular{font-size:26px;font-weight:400;letter-spacing:.01em;margin:0;}
  .seccion{font-size:34px;font-weight:400;letter-spacing:-.005em;margin:0 0 6px 0;}
  .filete{width:44px;height:1px;background:var(--burdeos);}

  /* ---- héroe (Evolve) --------------------------------------------------- */
  .heroe{text-align:center;padding:64px 0 2px 0;}
  /* Dos lineas, como la referencia. El salto va con <br> en el texto y no
     con un max-width en caracteres: asi no depende del ancho de pantalla. */
  .heroe h1{font-size:64px;line-height:1.04;font-weight:400;letter-spacing:-.022em;
            margin:0 auto;max-width:none;}
  .heroe p{font-size:15px;line-height:24px;color:var(--muted);margin:26px auto 0 auto;
           max-width:50ch;}
  .marca-agua{text-align:center;font-size:10px;letter-spacing:.5px;
              text-transform:uppercase;color:var(--faint);margin:2px 0 0 0;}

  /* ---- retículas genéricas ---------------------------------------------- */
  .tres, .cuatro{display:grid;gap:0;border-top:1px solid var(--line);}
  .tres{grid-template-columns:repeat(3,1fr);}
  .cuatro{grid-template-columns:repeat(4,1fr);}
  .celda{padding:26px 32px 30px 0;border-right:1px solid var(--line);}
  .celda:last-child{border-right:none;padding-right:0;}
  .celda:not(:first-child){padding-left:32px;}
  .celda .n{font-size:11px;letter-spacing:.6px;color:var(--burdeos);}
  .celda h3{font-size:15px;font-weight:400;margin:10px 0 0 0;}
  .celda h4{font-size:12px;font-weight:700;letter-spacing:.4px;text-transform:uppercase;margin:0;}
  .celda p{font-size:12.5px;line-height:19px;color:var(--muted);margin:8px 0 0 0;}
  .celda .v{font-size:34px;font-weight:400;letter-spacing:-.01em;
            font-variant-numeric:tabular-nums;}
  .celda .f{font-size:10px;letter-spacing:.3px;color:var(--faint);margin-top:9px;display:block;}

  /* ---- listas de datos --------------------------------------------------- */
  .dato{display:flex;justify-content:space-between;align-items:baseline;
        padding:10px 0;border-bottom:1px solid var(--line);}
  .dato span:first-child{font-size:11.5px;letter-spacing:.3px;color:var(--faint);}
  .dato span:last-child{font-size:12.5px;font-variant-numeric:tabular-nums;}
  .dato b{font-weight:700;}

  .caja{border:1px solid var(--ink);padding:28px 30px;}

  /* Fuente de datos: fila + licencia dentro del MISMO bloque, y el borde en
     el contenedor. Sin margenes negativos, que es lo que provocaba que la
     linea de licencia cruzara el filete de la fila de al lado. */
  .fuente-dato{border-bottom:1px solid var(--line);padding:10px 0 9px 0;}
  .fuente-dato .fila-f{display:flex;justify-content:space-between;
                       align-items:baseline;gap:18px;}
  .fuente-dato .fila-f span:first-child{font-size:11.5px;letter-spacing:.3px;
                                        color:var(--faint);}
  .fuente-dato .fila-f span:last-child{font-size:12.5px;text-align:right;}
  .fuente-dato .lic{font-size:10px;letter-spacing:.4px;text-transform:uppercase;
                    color:var(--faint);margin:6px 0 0 0;opacity:.85;}
  .ini{width:52px;height:52px;background:var(--ink);color:var(--base);
       display:flex;align-items:center;justify-content:center;font-size:16px;letter-spacing:.5px;}

  .aviso{border-left:2px solid var(--burdeos);padding:2px 0 2px 16px;}

  /* ---- rejilla de resultados --------------------------------------------- */
  .rejilla{display:grid;grid-template-columns:repeat(3,1fr);gap:34px 20px;margin-top:14px;}
  .rejilla.densa{grid-template-columns:repeat(4,1fr);gap:26px 14px;}
  .ficha{position:relative;}
  .marco{position:relative;width:100%;aspect-ratio:3/2;background:var(--plate);overflow:hidden;}
  .marco img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;display:block;
             transition:opacity .5s ease, transform 4s ease;}
  .marco img.b{opacity:0;}
  /* Segunda toma al pasar el cursor: el gesto de las tres tiendas medidas. */
  .ficha:hover .marco img.b{opacity:1;}
  .ficha:hover .marco img.a{opacity:0;}
  .ficha:hover .marco img{transform:scale(1.03);}
  .puesto{position:absolute;top:8px;left:8px;z-index:2;font-size:10px;letter-spacing:.6px;
          color:var(--faint);font-variant-numeric:tabular-nums;}
  .ficha:hover .puesto{color:var(--ink);}
  .pie{margin-top:9px;}
  .nom{font-size:12px;letter-spacing:.4px;text-transform:uppercase;margin:0;
       white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
  .sub{font-size:11px;letter-spacing:.4px;color:var(--faint);margin:3px 0 0 0;
       font-variant-numeric:tabular-nums;}
  .medidor{height:2px;background:var(--plate2);margin-top:7px;}
  .barra{height:2px;background:var(--burdeos);transition:width .6s ease;}
  .desc{font-size:11px;line-height:15px;color:var(--muted);margin:6px 0 0 0;opacity:0;
        transform:translateY(-2px);transition:opacity .3s ease, transform .3s ease;min-height:15px;}
  .ficha:hover .desc{opacity:1;transform:translateY(0);}


  /* =====================================================================
     FORMAS DE SECCION
     El problema no era que faltaran efectos: era que habia UN solo modulo
     (rotulo + filete + columnas de texto) repetido quince veces. Estas son
     las siluetas alternativas, para que una pagina no sea la anterior con
     otras palabras.
     ===================================================================== */

  /* ---- 1. franja oscura a sangre --------------------------------------
     Corta el beige a media pagina y rima con el pie. No introduce ningun
     color: es --ink de fondo y --base de texto, tinta y papel invertidos. */
  .franja{background:var(--ink);color:var(--base);
          margin:88px -56px;padding:76px 56px;}
  .franja .interior{max-width:820px;margin:0 auto;text-align:center;}
  .franja p.dicho{font-size:34px;line-height:1.25;font-weight:400;
                  letter-spacing:-.012em;margin:0;text-wrap:balance;}
  .franja p.dicho em{font-style:normal;color:#C98A9B;}
  .franja p.nota{font-size:12.5px;line-height:20px;margin:24px 0 0 0;
                 color:rgba(247,243,236,.62);max-width:58ch;
                 margin-left:auto;margin-right:auto;}

  /* ---- 2. banda de cifras grandes --------------------------------------
     Los numeros medidos son lo mejor que tiene este trabajo y estaban a
     34 px, el mismo tamano que un titulo cualquiera. */
  .banda{display:grid;grid-template-columns:repeat(4,1fr);gap:0;
         border-top:1px solid var(--ink);border-bottom:1px solid var(--line);}
  .banda > div{padding:34px 30px 36px 0;border-right:1px solid var(--line);}
  .banda > div:last-child{border-right:none;padding-right:0;}
  .banda > div:not(:first-child){padding-left:30px;}
  .banda .grande{font-size:62px;line-height:1;font-weight:400;
                 letter-spacing:-.03em;font-variant-numeric:tabular-nums;
                 display:block;transition:transform .5s cubic-bezier(.22,1,.36,1);
                 transform-origin:left center;}
  .banda > div:hover .grande{transform:scale(1.04);}
  .banda p{font-size:12px;line-height:18px;color:var(--muted);margin:16px 0 0 0;}
  .banda .fuente{font-size:10px;letter-spacing:.3px;color:var(--faint);
                 margin-top:10px;display:block;}

  /* ---- 3. tarjetas de verdad -------------------------------------------
     Con caja, borde y padding propios. Lo anterior eran celdas de tabla
     separadas por filetes, y por eso se leia como una hoja de datos. */
  .tarjetas{display:grid;gap:14px;}
  .tarjetas.t3{grid-template-columns:repeat(3,1fr);}
  .tarjetas.t4{grid-template-columns:repeat(4,1fr);}
  .caja-t{border:1px solid var(--line);padding:28px 26px 30px 26px;
          background:transparent;position:relative;
          transition:border-color .35s ease, background .35s ease,
                     transform .35s cubic-bezier(.22,1,.36,1);}
  .caja-t:hover{border-color:var(--ink);background:var(--surface);
                transform:translateY(-4px);}
  .caja-t .n{font-size:11px;letter-spacing:.6px;color:var(--burdeos);
             display:block;transition:letter-spacing .35s ease;}
  .caja-t:hover .n{letter-spacing:3px;}
  .caja-t h3{font-size:16px;font-weight:400;margin:14px 0 0 0;}
  .caja-t h4{font-size:12px;font-weight:700;letter-spacing:.4px;
             text-transform:uppercase;margin:0;}
  .caja-t p{font-size:12.5px;line-height:19px;color:var(--muted);margin:10px 0 0 0;}
  /* Un filete burdeos crece en el borde inferior al pasar por encima. */
  .caja-t::after{content:"";position:absolute;left:-1px;bottom:-1px;height:2px;
                 width:0;background:var(--burdeos);
                 transition:width .45s cubic-bezier(.22,1,.36,1);}
  .caja-t:hover::after{width:calc(100% + 2px);}

  /* ---- 4. acordeon (st.expander) ---------------------------------------- */
  div[data-testid="stExpander"]{border:none !important;
       border-top:1px solid var(--line) !important;border-radius:0 !important;
       background:transparent !important;box-shadow:none !important;}
  div[data-testid="stExpander"] summary,
  div[data-testid="stExpander"] details > div:first-child{
       padding:18px 0 !important;background:transparent !important;}
  div[data-testid="stExpander"] summary p,
  div[data-testid="stExpander"] p.st-emotion-cache-0{
       font-size:15px !important;font-weight:400 !important;color:var(--ink);}
  div[data-testid="stExpander"] summary:hover p{color:var(--burdeos) !important;}
  div[data-testid="stExpander"] svg{fill:var(--faint) !important;}
  div[data-testid="stExpanderDetails"]{padding:0 0 22px 0 !important;}
  /* El marco redondeado de Streamlit va en <details>, no en el div de fuera
     (comprobado en el DOM): sin esto sale una caja dentro de la línea. */
  div[data-testid="stExpander"] details{border:none !important;
       border-radius:0 !important;}

  /* ---- recorrido ----------------------------------------------------------
     Cinco segmentos, uno por pagina, con el filete superior como barra de
     progreso. Usa el mismo idioma que el resto de la aplicacion: numeros de
     dos digitos en burdeos, versalitas pequenas, filetes finos. No es un
     patron importado; es el que ya hablaban las tarjetas.

     OJO: Streamlit estiliza los enlaces de Markdown con mas especificidad que
     una clase suelta, y los pinta de azul con subrayado. De ahi el selector
     con el contenedor delante. */
  .recorrido{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;
             margin-top:78px;}
  div[data-testid="stMarkdownContainer"] a.paso, a.paso{
    display:block;text-decoration:none !important;color:var(--ink) !important;
    border-top:2px solid var(--line);padding:14px 10px 4px 0;
    transition:border-color .4s ease, padding .35s cubic-bezier(.22,1,.36,1);}
  a.paso .np{display:block;font-size:10.5px;letter-spacing:1px;
             color:var(--faint);transition:color .3s ease;}
  a.paso .tt{display:block;font-size:14.5px;line-height:20px;margin-top:7px;
             color:var(--faint);transition:color .3s ease;}
  a.paso:hover{border-top-color:var(--ink);padding-left:6px;}
  a.paso:hover .np, a.paso:hover .tt{color:var(--ink) !important;}
  /* Ya visitado: el filete lleno, el texto en tinta. */
  a.paso.visto{border-top-color:var(--ink);}
  a.paso.visto .tt{color:var(--muted);}
  /* Donde estas: filete burdeos y el titulo en negrita. Activo por PESO,
     como manda la especificacion medida de las tres tiendas. */
  a.paso.actual{border-top-color:var(--burdeos);}
  a.paso.actual .np{color:var(--burdeos);}
  a.paso.actual .tt{color:var(--ink);font-weight:700;}
  a.paso.actual{pointer-events:none;}

  /* ---- busqueda por posiciones ----------------------------------------------
     La fila principal enseña LA prenda de cada posición, grande. Encima, en
     una esquina, el recorte de la referencia con el que se comparó: así se ve
     de un vistazo QUÉ se buscó y QUÉ se encontró. Al pasar el cursor el
     recorte se aparta y se ve la segunda toma de la prenda. */
  .look{display:grid;grid-template-columns:repeat(var(--n),1fr);gap:22px;
        margin-top:16px;}
  .pieza .pos{margin:0 0 9px 0;}
  .escena{position:relative;}
  .inserto{position:absolute;left:10px;bottom:10px;width:30%;aspect-ratio:1/1;
           overflow:hidden;border:2px solid var(--base);background:var(--plate);
           z-index:3;transition:opacity .35s ease, transform .35s ease;}
  .inserto img{width:100%;height:100%;object-fit:cover;display:block;}
  .pieza:hover .inserto{opacity:0;transform:translateY(6px);}
  .marco.hueco{display:flex;align-items:center;justify-content:center;
               border:1px dashed var(--line);background:transparent;}
  .marco.hueco p{font-size:12px;color:var(--faint);margin:0;padding:0 18px;
                 text-align:center;}
  .nota-pieza{font-size:11px;line-height:16px;color:var(--faint);
              margin:6px 0 0 0;}

  /* Panel izquierdo fijo al hacer scroll: la referencia siempre a la vista
     mientras se recorren las alternativas. */
  div[data-testid="stColumn"]:has(.panel-busqueda){
    position:sticky;top:12px;align-self:flex-start;}
  .recortes{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px;}
  .recortes figure{margin:0;}
  .recortes img{width:100%;aspect-ratio:1/1;object-fit:cover;display:block;
                background:var(--plate);}
  .recortes figcaption{font-size:10px;letter-spacing:.6px;text-transform:uppercase;
                       color:var(--faint);margin-top:5px;}
  div[data-testid="stRadio"] div[role="radiogroup"]{flex-wrap:wrap;row-gap:10px;}

  /* ---- pie pegado abajo -----------------------------------------------------
     En una pagina corta el pie se quedaba a media pantalla con papel debajo.
     Estructura real de Streamlit 1.64, comprobada sobre el DOM:
       stMain (flex columna, alto = ventana)
         > stMainBlockContainer (bloque normal: NO estira)
           > stVerticalBlock (flex columna)
             > stElementContainer que contiene el .pie-pag
     Se hace que el contenedor principal y su columna ocupen al menos el alto
     de la ventana, y el pie se empuja al fondo con margin-top:auto. */
  section[data-testid="stMain"] > div[data-testid="stMainBlockContainer"]{
    flex:1 0 auto;display:flex !important;flex-direction:column;}
  div[data-testid="stMainBlockContainer"] > div[data-testid="stVerticalBlock"]{
    flex:1 0 auto;}
  div[data-testid="stMainBlockContainer"] > div[data-testid="stVerticalBlock"]
    > div[data-testid="stElementContainer"]:has(.pie-pag){margin-top:auto;}

  /* ---- pie de página ------------------------------------------------------
     Oscuro, como la referencia. El color NO es nuevo: es --ink, el mismo con
     el que se escribe todo el texto de la aplicación. Invertir tinta y papel
     es el unico recurso que hacia falta, y mantiene la paleta en dos colores.

     Va a sangre: el contenedor de Streamlit tiene 56 px de margen lateral, y
     se compensan con margenes negativos para que la franja toque los bordes.
     ---------------------------------------------------------------------- */
  .pie-pag{background:var(--ink);color:var(--base);
           margin:96px -56px -90px -56px;padding:52px 56px 34px 56px;}
  .pie-col{display:grid;grid-template-columns:repeat(4,1fr);gap:0 36px;}
  .pie-col h5{font-size:11px;letter-spacing:.5px;text-transform:uppercase;
              font-weight:400;color:#FFFDF9;margin:0 0 16px 0;}
  .pie-col a, .pie-col span.itm{display:block;font-size:12.5px;line-height:30px;
              color:rgba(247,243,236,.62);text-decoration:none;
              transition:color .25s ease;}
  .pie-col a:hover{color:#FFFDF9;}
  .pie-rule{height:1px;background:rgba(247,243,236,.16);margin:38px 0 22px 0;}
  .pie-bajo{display:flex;justify-content:space-between;align-items:center;
            gap:20px;flex-wrap:wrap;}
  .pie-bajo p{font-size:11px;letter-spacing:.3px;
              color:rgba(247,243,236,.5);margin:0;line-height:18px;}
  .pie-bajo img{height:17px;width:auto;display:block;}

  /* ---- acceso en la barra: icono, como en las tres tiendas ---------------- */
  .acceso-icono{display:flex;justify-content:flex-end;align-items:center;
                height:42px;}
  div[data-testid="stPageLink"].acceso a{width:auto !important;}


  /* =====================================================================
     ANIMACION AL HACER SCROLL
     El movimiento NO se define aqui. Se probo con `animation-timeline:
     view()`, que es CSS puro y no necesita JavaScript, pero va atada a la
     posicion de la barra de scroll: al subir, los elementos se deshacen. La
     referencia usa `once: true` — entra una vez y se queda — y esa diferencia
     se nota mucho.

     Asi que la entrada la gobierna un IntersectionObserver desde
     `paginas/entrada.py`, que inyecta sus propias reglas. Aqui solo queda la
     marca de clase, sin efecto por si mismo: si el script no llega a
     ejecutarse, los elementos se ven con normalidad.
     ===================================================================== */
  .revela{}

  /* ---- tarjetas vivas --------------------------------------------------
     Sin sombras y sin radios: el sistema medido en las tres tiendas no los
     usa, y meterlos por parecerse a la referencia romperia la coherencia.
     La vida la da el movimiento, no el relieve. */
  .celda{transition:background .35s ease, transform .35s cubic-bezier(.22,1,.36,1);}
  .tres .celda:hover, .cuatro .celda:hover{
    background:linear-gradient(to bottom, rgba(239,234,224,.55), transparent 70%);
    transform:translateY(-3px);
  }
  .celda .n{transition:letter-spacing .35s ease;}
  .celda:hover .n{letter-spacing:2.4px;}
  .celda .v{transition:transform .45s cubic-bezier(.22,1,.36,1);transform-origin:left bottom;}
  .celda:hover .v{transform:scale(1.05);}


  /* =====================================================================
     CINTA AUTOMATICA
     La referencia mueve sus carruseles con JavaScript. Aqui basta CSS: la
     pista lleva los elementos DUPLICADOS y se desplaza un -50% en bucle.
     Al llegar al final, la segunda copia esta exactamente donde estaba la
     primera, asi que el salto no se ve. Sin JS y sin librerias.
     ===================================================================== */
  .cinta{position:relative;overflow:hidden;
         -webkit-mask-image:linear-gradient(to right, transparent, #000 7%,
                            #000 93%, transparent);
         mask-image:linear-gradient(to right, transparent, #000 7%,
                    #000 93%, transparent);}
  .pista{display:flex;gap:14px;width:max-content;
         animation:desfile 64s linear infinite;}
  /* Se para al pasar el cursor: si no, no se puede mirar una prenda. */
  .cinta:hover .pista{animation-play-state:paused;}
  @media (prefers-reduced-motion: reduce){.pista{animation:none;}}
  @keyframes desfile{from{transform:translateX(0);}
                     to{transform:translateX(-50%);}}

  .tarjeta{flex:0 0 208px;width:208px;}
  .tarjeta .lamina{position:relative;width:100%;aspect-ratio:3/2;
                   background:var(--plate);overflow:hidden;}
  .tarjeta .lamina img{width:100%;height:100%;object-fit:cover;display:block;
                       transition:transform .8s cubic-bezier(.22,1,.36,1);}
  .tarjeta:hover .lamina img{transform:scale(1.06);}
  .tarjeta p{font-size:11px;letter-spacing:.4px;text-transform:uppercase;
             margin:8px 0 0 0;color:var(--faint);
             white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}

  /* ---- pagina de acceso: pestanas de Streamlit ------------------------- */
  div[data-testid="stTabs"] div[data-baseweb="tab-list"]{
    gap:28px;background:transparent;border-bottom:1px solid var(--line);}
  div[data-testid="stTabs"] button[data-baseweb="tab"]{
    background:transparent !important;padding:0 0 10px 0 !important;
    height:auto !important;}
  div[data-testid="stTabs"] button[data-baseweb="tab"] p{
    font-size:11px !important;letter-spacing:.6px;text-transform:uppercase;
    color:var(--faint) !important;font-weight:400 !important;}
  div[data-testid="stTabs"] button[aria-selected="true"] p{
    color:var(--ink) !important;font-weight:700 !important;}
  div[data-testid="stTabs"] div[data-baseweb="tab-highlight"],
  div[data-testid="stTabs"] div[data-baseweb="tab-border"]{
    background:var(--ink) !important;height:2px !important;}
  div[data-testid="stTabs"] div[data-baseweb="tab-panel"]{padding-top:22px;}

  /* ---- movil ------------------------------------------------------------
     No se habia mirado ni una vez. La barra pasa a dos filas, las reticulas
     a una columna y el heroe baja de 64 a 34 px. */
  @media (max-width:820px){
    .look{grid-template-columns:1fr;}
    div[data-testid="stColumn"]:has(.panel-busqueda){position:static;}
    .recorrido{grid-template-columns:repeat(2,1fr);gap:8px 14px;}
    a.paso .tt{font-size:13px;line-height:18px;}
    .franja{margin:56px -20px;padding:48px 20px;}
    .franja p.dicho{font-size:23px;}
    .banda{grid-template-columns:repeat(2,1fr);}
    .banda .grande{font-size:42px;}
    .banda > div{padding:24px 16px 26px 0 !important;}
    .tarjetas.t3, .tarjetas.t4{grid-template-columns:1fr;}
    .pie-pag{margin:70px -20px -70px -20px;padding:40px 20px 26px 20px;}
    .pie-col{grid-template-columns:repeat(2,1fr);gap:0 20px;}
    .pie-col h5{margin-top:22px;}
    .block-container{padding:0.4rem 20px 70px 20px !important;}
    .heroe{padding:34px 0 4px 0;}
    .heroe h1{font-size:34px;letter-spacing:-.015em;}
    .heroe p{font-size:14px;line-height:22px;}
    .seccion{font-size:25px;}
    .rejilla{grid-template-columns:1fr;}
    .pie-pag{flex-direction:column;gap:14px;}
    .pie-pag p{text-align:left !important;}
    .marca img{height:16px;}
    div[data-testid="stPageLink"] a p{font-size:11px !important;}
    .marca-agua{font-size:9px;line-height:14px;}
  }

  @media (max-width:1100px){
    .heroe h1{font-size:40px;}
    .tres,.cuatro{grid-template-columns:1fr;}
    .celda{border-right:none;border-bottom:1px solid var(--line);
           padding:22px 0 24px 0 !important;}
    .rejilla{grid-template-columns:repeat(2,1fr);}
  }
  /* ---- mi armario ---------------------------------------------------------- */
  /* En el armario la descripción («manga corta») es lo que distingue dos
     prendas de la misma categoría: se ve siempre, no solo al pasar. */
  .ficha.fija .desc{opacity:1;transform:none;white-space:nowrap;overflow:hidden;
                    text-overflow:ellipsis;}
  .ficha.fija .pie{margin-top:7px;}
  /* Sin segunda toma: al pasar, la foto se queda (la regla general la oculta). */
  .ficha.fija:hover .marco img.a{opacity:1;}
  /* «Quitar»: texto pequeño bajo la tarjeta, no un botón que compita con ella. */
  button[data-testid="stBaseButton-tertiary"]{
    background:transparent !important;border:none !important;padding:0 !important;
    min-height:0 !important;height:auto !important;box-shadow:none !important;
    margin:2px 0 14px 0;}
  button[data-testid="stBaseButton-tertiary"] p{
    font-size:10px !important;letter-spacing:.7px;text-transform:uppercase;
    color:var(--faint) !important;}
  button[data-testid="stBaseButton-tertiary"]:hover p{color:var(--burdeos) !important;}
  /* Diálogos con el mismo lenguaje que el resto: sin esquinas redondas. */
  /* La caja visible del diálogo es el div hijo directo de stDialog (radio
     de 16 px); el <section role="dialog"> va por fuera y no pinta nada.
     Comprobado en el DOM de Streamlit 1.64. */
  [data-testid="stDialog"] > div{border-radius:0 !important;
       background:var(--base) !important;}
  [data-testid="stDialog"] h2{font-size:22px !important;font-weight:400 !important;
       letter-spacing:-.01em;}
  /* Campos del formulario: el texto no puede tocar el borde de la caja. La
     regla general quita el relleno porque allí los campos son una línea. */
  [data-testid="stDialog"] div[data-testid="stTextInput"] input{
       padding-left:12px !important;}
  [data-testid="stDialog"] div[data-testid="stExpander"] summary{
       padding:14px 0 !important;}
  [data-testid="stDialog"] div[data-testid="stExpander"] summary p{
       font-size:13px !important;}
  [data-testid="stDialog"] div[data-testid="stExpanderDetails"]{
       padding:2px 0 16px 0 !important;}
  /* Con !important porque el contenedor de markdown de Streamlit fija el
     tamaño de sus <p> con un selector más específico. */
  p.nota-form{font-size:11.5px !important;line-height:17px !important;
       color:var(--faint) !important;margin:6px 0 0 0 !important;}
  /* El botón del subidor viene en inglés («Upload») y Streamlit no lo
     traduce: se oculta el texto y se pinta otro. */
  [data-testid="stFileUploaderDropzone"] button [data-testid="stMarkdownContainer"] p{
       font-size:0 !important;}
  [data-testid="stFileUploaderDropzone"] button [data-testid="stMarkdownContainer"] p::after{
       content:"Subir foto";font-size:11px;letter-spacing:.6px;}
  .guia svg{display:block;width:100%;height:auto;}
  .guia ol{margin:0;padding:0 0 0 18px;}
  .guia li{font-size:13px;line-height:20px;color:var(--muted);margin:0 0 7px 0;}
  .guia li b{color:var(--ink);font-weight:600;}
  .guia .porque{font-size:12px;line-height:18px;color:var(--faint);margin:12px 0 0 0;}
  /* ---- resultado de la búsqueda (una columna por posición) ---------------
     Columnas de 330 px como mucho: el conjunto entero cabe en una pantalla
     sin bajar. Marcos cuadrados con la foto entera (contain): un pantalón
     vertical y una camiseta apaisada ocupan lo mismo sin recortarse.
     La entrada es una animación CSS y no el script de aparición: el
     resultado es lo único de la pantalla que NO puede depender de que un
     script llegue a ejecutarse. */
  .resultado{display:grid;grid-template-columns:repeat(var(--n),minmax(0,330px));
             gap:0 44px;margin-top:20px;align-items:start;}
  .col-pos{animation:akin-res .8s cubic-bezier(.215,.61,.355,1) both;}
  .col-pos:nth-child(2){animation-delay:.12s;}
  .col-pos:nth-child(3){animation-delay:.24s;}
  @keyframes akin-res{from{opacity:0;transform:translateY(18px);}
                      to{opacity:1;transform:none;}}
  .col-pos .pos{margin:0 0 10px 0;}
  .cuadro{position:relative;aspect-ratio:1/1;background:var(--plate);overflow:hidden;}
  .cuadro img{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;
              display:block;transition:opacity .45s ease;}
  .cuadro img.b{opacity:0;}
  .cuadro.grande:hover img.b{opacity:1;}
  .cuadro.grande:hover img.a{opacity:0;}
  .cuadro.grande:hover .inserto{opacity:0;transform:translateY(6px);}
  .cuadro.hueco{display:flex;align-items:center;justify-content:center;text-align:center;}
  .cuadro.hueco p{font-size:12px;line-height:18px;color:var(--faint);padding:0 24px;margin:0;}
  .col-pos .nom{margin-top:10px;}
  .col-pos .det{font-size:11px;line-height:15px;color:var(--muted);margin:3px 0 0 0;
                white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
  .sub-alt{margin:20px 0 8px 0;}
  .dos{display:grid;grid-template-columns:1fr 1fr;gap:10px;}
  .mini .nom{font-size:10.5px;margin-top:6px;}
  .mas{margin-top:16px;border-top:1px solid var(--line);}
  .mas summary{list-style:none;cursor:pointer;padding:12px 0 4px 0;font-size:11px;
               letter-spacing:.6px;text-transform:uppercase;color:var(--ink);}
  .mas summary::-webkit-details-marker{display:none;}
  .mas summary::after{content:"  +";}
  .mas[open] summary::after{content:"  −";}
  .mas summary:hover{color:var(--burdeos);}
  /* «Ver más» abre una tira que se desliza en horizontal: el carrusel. Sin
     giro automático: es un ranking, de más a menos parecida, no un sorteo. */
  .tira{display:flex;gap:10px;overflow-x:auto;scroll-snap-type:x mandatory;
        padding:8px 0 12px 0;scrollbar-width:thin;}
  .tira .mini{flex:0 0 120px;scroll-snap-align:start;}
  @media (max-width:820px){.resultado{grid-template-columns:1fr;gap:34px 0;}}
  /* ---- preguntas de la búsqueda (st.segmented_control y st.pills) ---------
     Streamlit las pinta rosas y redondeadas. Aquí: rectas, línea fina, y la
     elegida en tinta, como los botones del resto de la aplicación. La
     elegida se reconoce por aria-checked (comprobado en el DOM, 1.64). */
  [data-testid="stButtonGroup"] button{border-radius:0 !important;
       background:transparent !important;border:1px solid var(--line) !important;
       color:var(--muted) !important;box-shadow:none !important;}
  [data-testid="stButtonGroup"] button p{font-size:12px !important;color:inherit !important;}
  [data-testid="stButtonGroup"] button:hover{border-color:var(--ink) !important;
       color:var(--ink) !important;}
  [data-testid="stButtonGroup"] button[aria-checked="true"],
  [data-testid="stButtonGroup"] button[aria-pressed="true"]{
       background:var(--ink) !important;border-color:var(--ink) !important;
       color:var(--base) !important;}
  /* La foto de referencia, con altura máxima: si no, empuja las preguntas
     fuera de la pantalla. */
  div[data-testid="stColumn"]:has(.panel-busqueda) div[data-testid="stImage"] img{
       max-height:300px;width:auto !important;max-width:100%;object-fit:contain;}
  /* Color leído en la foto, junto al nombre de la posición. */
  .pos .leido{margin-left:12px;font-weight:400;color:var(--muted);
       text-transform:none;letter-spacing:.2px;}
  .pos .leido i{display:inline-block;width:10px;height:10px;margin:0 6px -1px 0;
       border:1px solid var(--line);}
  /* Botones de formulario: Streamlit les pone otro data-testid y salían
     con su rojo por defecto. */
  button[data-testid="stBaseButton-primaryFormSubmit"]{
    background:var(--ink) !important;border:1px solid var(--ink) !important;
    color:var(--base) !important;border-radius:0 !important;box-shadow:none !important;
    font-size:11px !important;letter-spacing:.6px;text-transform:uppercase;height:42px;}
  button[data-testid="stBaseButton-primaryFormSubmit"]:hover{
    background:var(--burdeos) !important;border-color:var(--burdeos) !important;}
  /* Vista previa en el diálogo de subida: que no ocupe toda la pantalla. */
  [data-testid="stDialog"] div[data-testid="stImage"] img{
    max-height:260px;width:auto !important;max-width:100%;object-fit:contain;}
</style>
"""
