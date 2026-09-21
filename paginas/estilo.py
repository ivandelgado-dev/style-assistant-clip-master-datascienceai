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
  .block-container{padding:0.4rem 44px 90px 44px !important;max-width:100% !important;}
  div[data-testid="stVerticalBlock"]{gap:0.6rem;}
  iframe{border:none;background:transparent;}

  /* ---- barra superior (estructura de Evolve, reglas de Zara) --------- */
  .marca{height:42px;display:flex;align-items:center;}
  .marca img{height:17px;width:auto;display:block;}
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
  .heroe{text-align:center;padding:56px 0 6px 0;}
  /* Dos lineas, como la referencia. El salto va con <br> en el texto y no
     con un max-width en caracteres: asi no depende del ancho de pantalla. */
  .heroe h1{font-size:64px;line-height:1.04;font-weight:400;letter-spacing:-.022em;
            margin:0 auto;max-width:none;}
  .heroe p{font-size:15px;line-height:24px;color:var(--muted);margin:22px auto 0 auto;
           max-width:52ch;}
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
  .pista{height:2px;background:var(--plate2);margin-top:7px;}
  .barra{height:2px;background:var(--burdeos);transition:width .6s ease;}
  .desc{font-size:11px;line-height:15px;color:var(--muted);margin:6px 0 0 0;opacity:0;
        transform:translateY(-2px);transition:opacity .3s ease, transform .3s ease;min-height:15px;}
  .ficha:hover .desc{opacity:1;transform:translateY(0);}

  /* ---- pie de página ------------------------------------------------------ */
  .pie-pag{border-top:1px solid var(--ink);margin-top:70px;padding-top:22px;
           display:flex;justify-content:space-between;align-items:flex-start;}
  .pie-pag p{font-size:11px;letter-spacing:.3px;color:var(--faint);margin:0;line-height:17px;}

  @media (max-width:1100px){
    .heroe h1{font-size:40px;}
    .tres,.cuatro{grid-template-columns:1fr;}
    .celda{border-right:none;border-bottom:1px solid var(--line);
           padding:22px 0 24px 0 !important;}
    .rejilla{grid-template-columns:repeat(2,1fr);}
  }
</style>
"""
