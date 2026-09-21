"""
Cúpula de puntos del héroe de la portada.

Qué se dibuja
-------------
Media esfera, con el centro por debajo del borde inferior y solo la cara
frontal visible. Rota despacio sobre el eje vertical.

Las posiciones son un **retículo de Fibonacci**: puntos repartidos por la
superficie de la esfera siguiendo el ángulo áureo. Es la forma estándar de
cubrir una esfera de manera uniforme, y es lo que hace que no se vean grumos
ni huecos. Una muestra de datos reales no se reparte así — se agrupa — y por
eso la versión anterior se veía irregular.

El retículo es la **estructura**. No representa nada por sí mismo, y el pie de
la figura lo dice.

El relleno sí son datos
-----------------------
Todas las posiciones existen desde el primer fotograma, dibujadas huecas: un
aro de trazo fino, todas del mismo tamaño. Al iniciar sesión se **rellenan**
tantas como prendas tenga el usuario, una a una.

Y cuáles se rellenan no es arbitrario: los embeddings del armario se proyectan
por PCA a la esfera y cada prenda ocupa **la posición del retículo más
próxima a su vector real**, sin repetir. Así el patrón de relleno reproduce la
distribución verdadera del armario sobre la esfera, mientras la estructura se
mantiene uniforme.

El resultado es que se ve lo que hay que ver: las prendas del usuario no se
esparcen por toda la cúpula, se concentran en una zona. Eso es el salto de
dominio que este trabajo mide — una sonda lineal separa fotografía de catálogo
de fotografía de móvil con AUC 1,000, y aquí se ve por qué.

Implementación
--------------
Canvas 2D, sin dependencias, dentro de `st.components.v1.html` (que monta un
iframe: `st.markdown` no ejecuta `<script>` porque Streamlit lo sanea).
"""

from __future__ import annotations

import json

import numpy as np


def reticulo(n: int = 1400) -> np.ndarray:
    """`n` puntos repartidos uniformemente por la esfera unidad.

    Espiral de Fibonacci: se avanza en altura a pasos iguales y se gira el
    ángulo áureo en cada paso. Reparte sin acumular en los polos, que es lo
    que pasa si se muestrean latitud y longitud por separado.
    """
    i = np.arange(n, dtype=np.float64) + 0.5
    z = 1 - 2 * i / n                       # altura uniforme
    r = np.sqrt(np.clip(1 - z * z, 0, 1))
    phi = np.pi * (1 + 5 ** 0.5) * i        # ángulo áureo
    return np.column_stack([np.cos(phi) * r, z, np.sin(phi) * r])


def proyectar_a_esfera(V: np.ndarray,
                       referencia: np.ndarray | None = None
                       ) -> tuple[np.ndarray, float]:
    """PCA a 3 componentes, renormalizada a la esfera.

    `referencia` es el conjunto sobre el que se AJUSTA la base. Importa mucho:

    - Sin referencia, la base se ajusta sobre `V` y recoge las direcciones de
      máxima varianza dentro de `V`. Un armario proyectado así sale repartido
      por toda la esfera **por construcción**, diga lo que diga el dato.
    - Con el catálogo como referencia, la base es la del espacio general y el
      armario se sitúa dentro de él. Entonces sí se ve dónde cae respecto al
      resto, que es lo que mide el análisis de salto de dominio.

    Medido sobre este proyecto: la dispersión del armario pasa de 0,56 (base
    propia) a 0,13 (base del catálogo). La primera cifra no significa nada;
    la segunda es el resultado.
    """
    X = np.asarray(V, dtype=np.float64)
    ajuste = X if referencia is None else np.asarray(referencia, dtype=np.float64)
    centro = ajuste.mean(axis=0, keepdims=True)
    # SVD en vez de la matriz de covarianza: con 512 columnas, formar una
    # covarianza 512x512 es innecesario y peor condicionado.
    _, S, Vt = np.linalg.svd(ajuste - centro, full_matrices=False)
    P = (X - centro) @ Vt[:3].T
    var = float((S ** 2).sum())
    explicada = float((S[:3] ** 2).sum()) / var if var > 0 else 0.0
    n = np.linalg.norm(P, axis=1, keepdims=True)
    return P / np.where(n == 0, 1, n), explicada


def orientar(P: np.ndarray,
             objetivo=(0.20, 0.42, 0.88)) -> np.ndarray:
    """Gira la nube para que su centroide mire hacia la parte visible.

    Por qué hace falta: la cúpula solo muestra la mitad superior frontal de la
    esfera, y el armario cae donde cae. Medido en este proyecto, su centroide
    apuntaba a (0,47, −0,81, −0,37) — abajo y atrás — y las 118 posiciones
    rellenas quedaban **todas** fuera de la vista.

    Por qué es legítimo: es una rotación **rígida**. Conserva todos los ángulos
    y todas las distancias entre puntos, así que el agrupamiento que se ve es
    exactamente el que hay en los datos. Además, la orientación absoluta de una
    proyección PCA es arbitraria de entrada: el signo de cada componente no
    está determinado. Elegir desde dónde se mira no es tocar el dato.

    Rotación de Rodrigues sobre el eje perpendicular a ambos vectores.
    """
    c = np.asarray(P, dtype=np.float64).mean(axis=0)
    n = np.linalg.norm(c)
    if n < 1e-9:
        return P
    c = c / n
    t = np.asarray(objetivo, dtype=np.float64)
    t = t / np.linalg.norm(t)

    v = np.cross(c, t)
    sen = np.linalg.norm(v)
    cos = float(np.dot(c, t))
    if sen < 1e-9:                          # ya alineados, o justo opuestos
        return P if cos > 0 else -P
    K = np.array([[0, -v[2], v[1]],
                  [v[2], 0, -v[0]],
                  [-v[1], v[0], 0]]) / sen
    R = np.eye(3) + sen * K + (1 - cos) * (K @ K)
    return P @ R.T


def asignar(malla: np.ndarray, datos: np.ndarray) -> list[int]:
    """Cada dato se queda la posición libre más próxima del retículo.

    Asignación voraz: se recorre en orden y cada punto toma su vecino más
    cercano entre los que quedan. No es el emparejamiento óptimo —eso sería
    un problema de asignación húngara— pero con 118 puntos sobre 1400
    posiciones la diferencia es invisible y esto es instantáneo.
    """
    sim = datos @ malla.T                   # ambos normalizados: coseno
    tomadas: set[int] = set()
    salida: list[int] = []
    for fila in sim:
        for j in np.argsort(-fila):
            if int(j) not in tomadas:
                tomadas.add(int(j))
                salida.append(int(j))
                break
    return salida


def html(malla: list, rellenar: list, alto: int = 520) -> str:
    j_malla = json.dumps([[round(v, 4) for v in p] for p in malla],
                         separators=(",", ":"))
    j_rell = json.dumps(rellenar, separators=(",", ":"))
    return f"""
<!doctype html><html><head><meta charset="utf-8"><style>
  html,body{{margin:0;padding:0;background:transparent;overflow:hidden;}}
  canvas{{display:block;width:100%;height:{alto}px;cursor:crosshair;}}
</style></head><body>
<canvas id="c"></canvas>
<script>
(function(){{
  const MALLA = {j_malla}, RELLENAR = {j_rell};
  const TINTA = '28,27,26', ACENTO = '123,45,64';
  // orden[i] = turno en el que se rellena la posicion i, o -1 si nunca
  const ORDEN = new Int32Array(MALLA.length).fill(-1);
  RELLENAR.forEach((idx, t) => {{ ORDEN[idx] = t; }});

  const cv = document.getElementById('c'), ctx = cv.getContext('2d');
  let W = 0, H = 0, dpr = Math.min(window.devicePixelRatio || 1, 2);
  let raton = null, giro = 0, velocidad = 0.0011, t0 = null;

  function medir(){{
    W = cv.clientWidth; H = {alto};
    cv.width = W * dpr; cv.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }}
  window.addEventListener('resize', medir); medir();
  cv.addEventListener('mousemove', e => {{
    const r = cv.getBoundingClientRect();
    raton = {{x: e.clientX - r.left, y: e.clientY - r.top}};
  }});
  cv.addEventListener('mouseleave', () => {{ raton = null; }});

  function pintar(ts){{
    if (t0 === null) t0 = ts;
    ctx.clearRect(0, 0, W, H);

    // El relleno avanza durante ~2,4 s y se queda. El ritmo es siempre el
    // mismo; lo que cambia con el armario es cuantos acaban rellenos.
    const avance = Math.min(1, (ts - t0 - 400) / 2400);
    const hechos = Math.floor(avance * RELLENAR.length);

    const cx = W / 2, cy = H * 1.05;
    const R = Math.min(W * 0.45, H * 1.02);
    const f = R * 4.0;

    const objetivo = raton ? 0.00035 : 0.0011;
    velocidad += (objetivo - velocidad) * 0.05;
    giro += velocidad;

    const sen = Math.sin(giro), cos = Math.cos(giro);
    const incl = 0.20, si = Math.sin(incl), ci = Math.cos(incl);
    const vis = [];

    for (let k = 0; k < MALLA.length; k++) {{
      const p = MALLA[k];
      const x =  p[0] * cos + p[2] * sen;
      const w = -p[0] * sen + p[2] * cos;
      const y = p[1] * ci - w * si;
      const z = p[1] * si + w * ci;
      if (z < 0) continue;                  // solo la cara frontal
      const esc = f / (f - z * R);
      const sy = cy - y * R * esc;
      if (sy > H + 10) continue;
      vis.push({{sx: cx + x * R * esc, sy: sy, z: z, esc: esc, k: k}});
    }}
    vis.sort((a, b) => a.z - b.z);

    for (const v of vis) {{
      let sx = v.sx, sy = v.sy;
      // Tamano constante: solo lo modula la perspectiva, nunca el estado.
      let r = 2.4 * v.esc;
      const t = ORDEN[v.k];
      const lleno = t >= 0 && t < hechos;
      let alfa = lleno ? (0.62 + v.z * 0.38) : (0.16 + v.z * 0.26);
      let color = TINTA;

      if (raton) {{
        const dx = sx - raton.x, dy = sy - raton.y;
        const d = Math.hypot(dx, dy);
        if (d < 130 && d > 0.001) {{
          // Cerca del cursor los puntos se apartan y se agrandan. La caida
          // es cuadratica para que el borde del efecto no se note.
          const k = (1 - d / 130) * (1 - d / 130);
          sx += (dx / d) * k * 16;
          sy += (dy / d) * k * 16;
          r += k * 2.2;
          alfa = Math.min(1, alfa + k * 0.5);
          if (d < 52) color = ACENTO;
        }}
      }}

      ctx.beginPath();
      ctx.arc(sx, sy, Math.max(r, 0.7), 0, 6.2832);
      if (lleno) {{
        ctx.fillStyle = 'rgba(' + color + ',' + alfa.toFixed(3) + ')';
        ctx.fill();
      }} else {{
        ctx.lineWidth = 1;
        ctx.strokeStyle = 'rgba(' + color + ',' + alfa.toFixed(3) + ')';
        ctx.stroke();
      }}
    }}
    requestAnimationFrame(pintar);
  }}
  requestAnimationFrame(pintar);
}})();
</script></body></html>"""
