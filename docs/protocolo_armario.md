# Protocolo de fotografía del armario

Conjunto de test out-of-distribution. Se fija ANTES de disparar y no se cambia a
mitad: cambiarlo invalida las fotos ya hechas.

## 1. Para qué es este conjunto

No es para entrenar. Nunca. Son ~130 imágenes: entrenar con ellas no aportaría
nada y contaminaría la evaluación.

Sirve para una sola cosa, y es la que sostiene la memoria a partir de ahora:
medir cuánto se degrada un sistema entrenado con fotografía de catálogo cuando
la entrada es una foto de móvil. Tras el resultado de modelado —la ventaja de
las cabezas por atributo no se transfiere a atributos no vistos— esta medición
pasa a ser la contribución principal. Si las fotos salen mal, no hay medición y
no hay contribución.

## 2. Por qué el protocolo es rígido

Toda variable libre en la captura entra en el embedding y se confunde con el
efecto que queremos medir.

Si la mitad de las fotos están hechas con bombilla cálida y la otra mitad con
luz de ventana, la diferencia que midamos frente a DeepFashion incluirá esa
variación interna, y no habrá forma de decir cuánta parte es "dominio" y cuánta
es "hice las fotos de dos maneras distintas". Fijar las condiciones no hace las
fotos más bonitas: hace que la diferencia medida sea atribuible a algo.

## 3. Reglas de captura

1. **Una prenda por foto.** Nada más en el encuadre: ni percha, ni manos, ni una
   segunda prenda asomando por la esquina, ni etiquetas.

2. **Prenda estirada sobre superficie lisa de un solo color.** Mangas
   extendidas, sin dobleces que oculten el corte. Como la pondrías en un
   escaparate, no como sale de la lavadora.

3. **Fondo que contraste con la prenda.** Claro para prendas oscuras, oscuro o
   gris para prendas claras. Una camisa beige sobre sábana beige es una foto
   perdida. Anota cuál usaste en la columna `fondo` del CSV: así después se
   comprueba si el fondo explica algo, en lugar de discutirlo.

4. **Luz de ventana, de día. Sin flash.** La prenda no a sol directo: las
   sombras duras cambian la textura aparente, y textura es una de las tres
   dimensiones que el modelo compara. A ser posible, mismo sitio y franja
   horaria para todas.

5. **Móvil paralelo al suelo, cenital, centrado, misma altura siempre.** Un
   ángulo distinto deforma la silueta, y forma es otra de las tres dimensiones.

6. **Mismo teléfono, misma app, mismo objetivo.** No cambies entre gran angular
   y 1x a mitad de la sesión: cambia la geometría de la imagen.

7. **La prenda ocupa el 70-85% del encuadre**, entera, sin cortar.

8. **Sin filtros, sin modo retrato, sin edición posterior, sin recortes.** JPG o
   PNG. Si el móvil guarda en HEIC, cambia a "Más compatible" antes de empezar.

9. **Mínimo ~1000 px de lado.** CLIP escala a 224, pero de una foto pequeña ya
   no se recupera resolución.

## 4. Las cinco prendas repetidas

Elige cinco prendas variadas: una clara, una oscura, una estampada, un pantalón,
un abrigo. Fotografía cada una, retírala de la superficie, vuelve a colocarla
desde cero y fotografíala otra vez. Diez fotos en total, cinco minutos.

Esto da el **suelo de ruido**: cuánto se mueve el embedding de la MISMA prenda
por el mero hecho de recolocarla. Es la referencia contra la que se lee todo lo
demás. Si volver a colocar una camisa ya mueve el vector un 6%, una caída del 4%
atribuida al dominio no es un resultado, es ruido.

Sin este dato el número del domain gap no se puede interpretar, y es la primera
pregunta que hace un tribunal que sepa de esto.

Nómbralas con prefijo `dup_`: `dup_01_a.jpg`, `dup_01_b.jpg`, `dup_02_a.jpg`...
El script las empareja por ese prefijo.

## 5. Orden de trabajo

Agrupa por categoría y dispara seguido: todas las camisas, luego todos los
pantalones, luego los abrigos. El CSV sale casi ordenado y etiquetar después
cuesta la mitad.

## 6. Dónde van las fotos

    data/raw/wardrobe/img/

Fuera de git: `.gitignore` excluye `data/`. Las fotos no van a GitHub.

## 7. Después de disparar

    python src/plantilla_armario.py init --fotos data/raw/wardrobe/img --out data/raw/wardrobe/armario.csv
    python src/plantilla_armario.py validar --csv data/raw/wardrobe/armario.csv

Se rellena categoría, color base y las notas libres de corte, textura y tejido.
Solo la categoría es obligatoria. Las notas se escriben ANTES de ver ninguna
salida del modelo — eso es lo que las hace utilizables como etiqueta.

## 8. Cuántas prendas hacen falta

Entrega 2 comprometió 80-150. Por debajo de ~60 los intervalos de confianza se
abren tanto que la medición deja de distinguir nada. 90 es suficiente; 40 obliga
a volver otro día.

## 9. Diferencia entre dominios que este protocolo NO elimina

DeepFashion (Category and Attribute Prediction) contiene mayoritariamente
prendas fotografiadas **sobre una persona**. Este conjunto son prendas planas
sobre una superficie. Por tanto la diferencia medida no es solo de captura
(dispositivo, luz, fondo): incluye la presentación (con cuerpo frente a sin
cuerpo).

No se corrige fotografiando las prendas puestas: eso no es el flujo del
producto, que pide al usuario una foto de la prenda estirada. Se declara. Para
poder cuantificar de qué estamos hablando, se anota a mano una muestra
aleatoria de 100 imágenes de DeepFashion clasificándolas en
"sobre persona / plana / colgada", y esa proporción se reporta en la memoria
junto al resultado.

Es una limitación conocida y acotada, no un agujero.
