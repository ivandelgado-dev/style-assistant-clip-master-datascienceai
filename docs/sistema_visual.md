# Sistema visual del frontal

16/09/2026. Derivado de una especificación medida de tres referencias reales,
no de una impresión.

## 1. De dónde sale

Se inspeccionaron en navegador los listados de producto de Zara, Pull&Bear y
Bershka leyendo estilos calculados (`getComputedStyle`),
`getBoundingClientRect` y las variables CSS de cada sistema de diseño. El
documento de partida está en la conversación del proyecto; aquí queda lo que se
adoptó y lo que se descartó.

Importa el método: la primera versión del mockup se hizo "de memoria", con una
idea general de cómo se ve una tienda de moda. Al contrastarla con medidas, tres
decisiones estaban mal.

## 2. Rasgos comunes a las tres marcas

- Fondo y texto de máximo contraste, sin grises decorativos.
- Imagen de producto **2:3**, `object-fit: cover`, sin marco, sin esquinas y sin
  sombra.
- Tarjeta = imagen + texto. **Sin borde, sin fondo y sin elevación.**
- Filetes de 1 píxel físico para las líneas estructurales.
- Estado activo o seleccionado marcado con **peso tipográfico**, nunca con
  color de fondo ni chips.
- Filtros como texto plano: sin chips, sin desplegables, sin casillas.
- **Una sola familia tipográfica sans-serif** por marca.
- Cero sombras y cero esquinas redondeadas en toda la interfaz.

## 3. Lo que se corrigió del mockup anterior

| | las tres marcas | versión anterior | ahora |
|---|---|---|---|
| tipografía | sans-serif | Georgia serif | Helvetica/Arial |
| proporción de imagen | 2:3 | ~1,2:1 | 2:3 |
| estado activo | peso | color burdeos | peso 700 |
| letter-spacing | 0 / 0,7 / 0,8px | 0,22em (~2px) | 0,4-0,8px |
| texto de producto | 11-13px | 9,5-12,5px | 11-12px |
| barra superior | 40px con filete | 62px sin filete | 40px con filete |

El cambio de mayor calado es el del **estado activo**. Las tres marcas coinciden
en marcarlo solo con el peso; la versión anterior lo hacía con burdeos. Se
resolvió separando dos cosas que estaban mezcladas:

- **Estado** (filtro seleccionado, sección activa) → peso 700, sin color.
- **Acción** (enlaces, botones) → burdeos.

Eso respeta a la vez la regla de la referencia y la regla de la paleta propia
("burdeos solo para lo interactivo"), que no eran incompatibles: un filtro
seleccionado es un estado, no una acción.

## 4. Lo que NO se adoptó, y por qué

- **Fondo blanco y texto negro puros.** La paleta viene del chatbot del módulo
  de IA Generativa y es deliberada: beige neutro porque el color lo pone la
  ropa. Se mantiene.
- **Gutter 0 y sangrado total (Bershka).** Funciona en una tienda donde la
  rejilla ocupa toda la ventana; aquí hay una columna de referencia y controles
  a la izquierda, y las fotos pegadas al borde chocarían con ella.
- **Rejilla editorial de módulos mixtos (Zara).** Es una decisión de escaparate,
  no de herramienta: aquí el orden lo fija la proximidad medida y agrandar un
  resultado por composición induciría a leer jerarquía donde no la hay.
- **Iconos sobre la foto (Bershka), corazón de favoritos (Pull&Bear).** No hay
  cesta ni lista de deseos en este producto.
- **Rojo de descuento.** No hay precios.

## 5. La barra de proximidad

Es el único elemento sin equivalente en la referencia, porque las tiendas no
muestran confianza de un modelo. Va sobre el borde inferior de la imagen —el
sitio donde Bershka pone sus controles— y no debajo del nombre, donde se leía
como un subrayado del texto.

Codifica proximidad con la **longitud y la intensidad del burdeos**. No hay
escala rojo-verde: implicaría "bien/mal", y el modelo produce distancias, no
juicios.

## 6. Accesibilidad

Contraste medido contra WCAG 2.1 AA. Todos los colores de texto cumplen 4,5:1
sobre el beige; dos valores se corrigieron al medirlos. Tabla completa en
`docs/entregas/05_diseno_frontal.md` §3.3.

Sin evaluar: tamaño de tipografía, navegación por teclado y lectores de
pantalla.
