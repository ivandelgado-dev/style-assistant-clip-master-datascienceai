"""
Animación de entrada de los elementos al aparecer en pantalla.

De dónde sale la especificación
-------------------------------
Leída directamente de la referencia (evolve.es) consultando sus instancias de
ScrollTrigger en tiempo de ejecución. Sus 25 disparadores son todos iguales:

    start: "top 80%"      dispara cuando el borde superior del elemento
                          llega al 80 % de la altura de la ventana
    once: true            se reproduce UNA vez y se queda; al subir no
                          se deshace
    propiedades: opacity y `y`. Nada más — ni escala, ni rotación, ni filtros
    duración: 0,8 a 1,8 s
    ease: power3.out      desaceleración cúbica
    stagger: 0,1 a 0,2 s  entre elementos hermanos

`power3.out` es 1-(1-t)³, que en CSS se aproxima muy de cerca con
cubic-bezier(0.215, 0.61, 0.355, 1).

Por qué esto y no CSS puro
--------------------------
Las animaciones dirigidas por scroll de CSS (`animation-timeline: view()`) van
**atadas a la posición de la barra**: si subes, se deshacen. La referencia usa
`once: true`, que es una entrada temporizada que se dispara y se queda. Esa
diferencia se nota mucho — una se siente como una entrada, la otra como un
control deslizante.

CSS no sabe hacer «una vez y se queda». Hace falta un IntersectionObserver.

Cómo se ejecuta el JavaScript
-----------------------------
`st.markdown` sanea `<script>`, así que no sirve. `st.components.v1.html` monta
un iframe que **sí** ejecuta JavaScript, y desde él se puede alcanzar el
documento padre. Es un apaño conocido de Streamlit, no una API oficial.

Por eso está escrito para **fallar sin romper nada**: los elementos son
visibles por defecto en el CSS, y el script solo añade la clase que los oculta
justo antes de observarlos. Si el iframe no puede alcanzar al padre —porque
una versión futura de Streamlit lo aísle— no pasa absolutamente nada: la
página se ve entera, sin animación. Nunca al revés.
"""

from __future__ import annotations

# Por qué el código se inyecta en la página y no corre en el iframe
# -----------------------------------------------------------------
# Antes, cada repintado cargaba el iframe de nuevo y cada carga creaba OTRO
# juego de observadores, que vivían en el iframe. Cuando Streamlit retiraba
# ese iframe, sus temporizadores dejaban de ejecutarse, pero sus observadores
# seguían marcando elementos: los ocultaban y nadie los volvía a enseñar.
# Así desapareció la columna «Abajo» de un resultado de búsqueda.
#
# Ahora el iframe solo mete un <script> en el documento de la página, UNA
# vez. Ese script vive en la página, que no se retira nunca: un solo juego
# de observadores y temporizadores que no mueren con ningún iframe.
_CODIGO = r"""
(function(){
  if (window.__akinEntradas) return;
  window.__akinEntradas = true;
  var doc = document;

  var css = doc.createElement('style');
  css.textContent = [
    '.oculto{opacity:0;transform:translateY(38px);}',
    '.entra{opacity:1 !important;transform:none !important;',
    '  transition:opacity 1.15s cubic-bezier(.215,.61,.355,1),',
    '             transform 1.15s cubic-bezier(.215,.61,.355,1);}',
    '@media (prefers-reduced-motion: reduce){',
    '  .oculto{opacity:1 !important;transform:none !important;}}'
  ].join('\n');
  doc.head.appendChild(css);

  var obs = new IntersectionObserver(function(entradas){
    entradas.forEach(function(e){
      if (!e.isIntersecting) return;
      var el = e.target;
      // Escalonado entre hermanos, como la referencia: 0,12 s.
      var retraso = parseFloat(el.dataset.akinRetraso || '0');
      setTimeout(function(){
        el.classList.remove('oculto');
        el.classList.add('entra');
      }, retraso);
      obs.unobserve(el);          // once: true
    });
  }, {
    // "top 80%": el elemento entra cuando su borde superior alcanza el 80 %
    // de la altura de la ventana: se recorta el 20 % inferior del área.
    rootMargin: '0px 0px -20% 0px',
    threshold: 0
  });

  // Streamlit pone target="_blank" en TODOS los enlaces de Markdown. Para los
  // internos eso es un fallo: abrían una pestaña nueva en vez de navegar.
  function enlaces(){
    doc.querySelectorAll('a[href^="/"][target="_blank"]').forEach(function(a){
      a.removeAttribute('target');
      a.removeAttribute('rel');
    });
  }

  function barrer(){
    var nodos = doc.querySelectorAll('.revela:not([data-akin])');
    var porPadre = new Map();
    nodos.forEach(function(el){
      el.setAttribute('data-akin', '1');
      // Si un ancestro ya entra, este entra con él: observar los dos produce
      // un doble desvanecido raro.
      if (el.parentElement && el.parentElement.closest('.revela')) return;
      var p = el.parentElement;
      var n = porPadre.get(p) || 0;
      porPadre.set(p, n + 1);
      el.dataset.akinRetraso = String(Math.min(n, 5) * 120);
      el.classList.add('oculto');
      obs.observe(el);
    });
  }

  enlaces();
  barrer();
  // Streamlit redibuja al cambiar de página o al interactuar: se vuelve a
  // barrer lo que aparezca después.
  new MutationObserver(function(){ enlaces(); barrer(); })
    .observe(doc.body, {childList: true, subtree: true});
})();
"""

GUION = """
<script>
(function(){
  // Si el iframe no alcanza la página (una versión futura de Streamlit podría
  // aislarlo), se sale en silencio: la página queda visible y sin animar.
  var doc;
  try { doc = window.parent.document; } catch (e) { return; }
  if (!doc || doc.getElementById('akin-entradas-js')) return;
  var s = doc.createElement('script');
  s.id = 'akin-entradas-js';
  s.textContent = %s;
  doc.head.appendChild(s);
})();
</script>
""" % __import__("json").dumps(_CODIGO)
