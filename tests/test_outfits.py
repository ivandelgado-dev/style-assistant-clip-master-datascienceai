"""
Reglas de los outfits por estilo (`paginas/outfits.py`) y valoraciones.

Sin torch, sin Streamlit, sin red: prendas inventadas y una base temporal.

    python tests/test_outfits.py
"""

import importlib.util
import pathlib
import sys
import tempfile
import types

import numpy as np

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
if importlib.util.find_spec("torch") is None:
    sys.modules["torch"] = types.ModuleType("torch")
from paginas import armario, auth, outfits  # noqa: E402

fallos = []


def check(nombre, cond, detalle=""):
    print(f"  {'OK  ' if cond else 'FALLA'}  {nombre} {detalle}")
    if not cond:
        fallos.append(nombre)


LAB = {"negro": (15, 0, 0), "blanco": (94, 0, 1), "azul marino": (22, 5, -25),
       "rojo": (48, 60, 40), "verde": (50, -35, 25), "beige": (78, 4, 18),
       "gris": (55, 0, 0), "rosa": (75, 25, 3)}


def P(i, pos, tipo, color, estampado="liso", tejido="algodon", corte=None):
    return {"i": i, "id": 100 + i, "posicion": pos, "tipo": tipo, "color": color,
            "lab": np.array(LAB[color], float), "estampado": estampado,
            "tejido": tejido, "manga": None, "corte": corte}


prendas = [
    P(0, "arriba", "camiseta", "blanco"),
    P(1, "arriba", "camiseta", "negro", "logo"),
    P(2, "arriba", "camisa", "azul marino"),
    P(3, "arriba", "sudadera", "gris"),
    P(4, "abajo", "vaquero", "azul marino", tejido="vaquero"),
    P(5, "abajo", "chino", "beige"),
    P(6, "abajo", "jogger", "negro", tejido="sintetico"),
    P(7, "encima", "cazadora", "negro", tejido="cuero"),
    P(8, "encima", "blazer", "gris"),
    P(9, "arriba", "camiseta", "rojo", "estampado"),
    P(10, "abajo", "bermuda", "verde"),
]

print("\n=== 1. Cada estilo solo usa sus prendas ===")
for est in outfits.ORDEN_ESTILOS:
    if est == "oversize":
        continue
    r = outfits.generar(prendas, est)
    E = outfits.ESTILOS[est]
    ok = all(prendas[o["prendas"][pos]]["tipo"] in E[pos]
             for o in r["outfits"] for pos in o["prendas"])
    check(f"{est}: tipos permitidos ({len(r['outfits'])} outfits)", ok)

print("\n=== 2. Reglas concretas ===")
r = outfits.generar(prendas, "athleisure")
check("athleisure sin vaquero", all(prendas[o["prendas"]["abajo"]]["tipo"] != "vaquero"
                                    for o in r["outfits"]))
r = outfits.generar(prendas, "minimalista")
check("minimalista: todo liso", all(prendas[i]["estampado"] == "liso"
                                    for o in r["outfits"] for i in o["prendas"].values()))
r = outfits.generar(prendas, "rocker")
check("rocker: lleva negro y algo encima",
      all(any(prendas[i]["color"] == "negro" for i in o["prendas"].values())
          and "encima" in o["prendas"] for o in r["outfits"]))
check("rocker: el primero tiene la cazadora de cuero",
      r["outfits"] and r["outfits"][0]["prendas"].get("encima") == 7)
r = outfits.generar(prendas, "business_casual")
check("business casual: sin camiseta ni vaquero",
      all(prendas[o["prendas"]["arriba"]]["tipo"] != "camiseta"
          and prendas[o["prendas"]["abajo"]]["tipo"] != "vaquero" for o in r["outfits"]))
r = outfits.generar(prendas, "oversize")
check("oversize sin corte declarado: avisa y no inventa", not r["outfits"] and r["aviso"])
pr2 = [dict(p, corte="holgado") if p["i"] in (0, 4) else p for p in prendas]
r = outfits.generar(pr2, "oversize")
check("oversize con corte declarado: sale", len(r["outfits"]) > 0)

print("\n=== 3. Color pedido ===")
r = outfits.generar(prendas, "casual", color_pedido="rojo")
check("todos llevan algo rojo",
      r["outfits"] and all(any(prendas[i]["color"] in outfits.COLORES_PEDIDO["rojo"]
                                for i in o["prendas"].values()) for o in r["outfits"]))
r = outfits.generar(prendas, "minimalista", color_pedido="verde")
check("imposible: aviso, sin inventar", not r["outfits"] and r["aviso"])

print("\n=== 4. Capas ===")
r = outfits.generar(prendas, "casual", con_encima=True)
check("encima siempre más exterior que arriba",
      all(outfits._etq.CAPA.get(prendas[o["prendas"]["encima"]]["tipo"], 3)
          > outfits._etq.CAPA.get(prendas[o["prendas"]["arriba"]]["tipo"], 1)
          for o in r["outfits"]))
check("una prenda no se repite dentro del outfit",
      all(len(set(o["prendas"].values())) == len(o["prendas"]) for o in r["outfits"]))

print("\n=== 5. Reproducible y variado ===")
a = outfits.generar(prendas, "streetwear")
b = outfits.generar(prendas, "streetwear")
check("mismo armario, mismo resultado", a == b)
from collections import Counter  # noqa: E402
usos = Counter(i for o in a["outfits"] for i in o["prendas"].values())
check("ninguna prenda más de 2 veces", max(usos.values()) <= 2, f"{usos.most_common(2)}")

print("\n=== 6. Wada ===")
cols, pal, L = outfits.wada()
check("348 combinaciones de 159 colores", len(pal) == 348 and len(cols) == 159)
n = next(k for k, v in pal.items() if len(v) == 2)
fal = [{"i": 0, "lab": L[pal[n][0]]}, {"i": 1, "lab": L[pal[n][1]]}]
pps = outfits.paletas_por_prenda(fal, 9.05)
check("dos prendas con los colores exactos de una paleta la siguen",
      outfits.paleta_comun(pps) is not None)
check("dos prendas del mismo color no forman paleta",
      outfits.paleta_comun([pps[0], pps[0]]) is None)

print("\n=== 6b. Proporción por altura ===")
sin = outfits.generar(prendas, "casual")
con = outfits.generar(prendas, "casual", altura=165)
alto = outfits.generar(prendas, "casual", altura=185)
check("con 1,85 no cambia nada", alto == sin)
tonales = [o for o in con["outfits"]
           if any("alarga" in r for r in o["razones"])]
check("con 1,65 hay looks marcados como que alargan", len(tonales) > 0)
check("y todos cumplen el contraste bajo",
      all(abs(prendas[o["prendas"]["arriba"]]["lab"][0]
              - prendas[o["prendas"]["abajo"]]["lab"][0]) < outfits.CONTRASTE_BAJO
          for o in tonales))
check("no quita outfits: mismos conjuntos posibles",
      len(con["outfits"]) == len(sin["outfits"]))

print("\n=== 6c. Partir de una prenda ===")
jog = P(11, "abajo", "jogger", "gris", tejido="punto")
jog["informal"] = True
pr3 = prendas + [jog]
v = outfits.encaje(jog, "business_casual")
check("jogger en Business Casual: no encaja, con razón", v["nivel"] == 0 and v["razones"])
check("y dice dónde sí", "athleisure" in v["alternativas"] and "streetwear" in v["alternativas"])
check("chino en Smart Casual: encaja", outfits.encaje(prendas[5], "smart_casual")["nivel"] == 2)
r = outfits.generar(pr3, "casual", ancla=4)
check("con prenda de partida, sale en todos", r["outfits"]
      and all(o["prendas"]["abajo"] == 4 for o in r["outfits"]))
r = outfits.generar(pr3, "business_casual", ancla=11)
check("si no encaja, no se inventa", not r["outfits"])
r = outfits.generar(pr3, "business_casual", ancla=11, forzar=True)
check("forzada: se monta igual y la lleva", r["outfits"]
      and all(o["prendas"]["abajo"] == 11 for o in r["outfits"]))
check("encima como prenda de partida: sale encima",
      all(o["prendas"].get("encima") == 7 for o in outfits.generar(prendas, "rocker", ancla=7)["outfits"]))
a0 = outfits.generar(prendas, "casual")
a1 = outfits.generar(prendas, "casual", semilla=1)
a1b = outfits.generar(prendas, "casual", semilla=1)
check("otra tanda: misma semilla, mismo resultado", a1 == a1b)
check("otra tanda: cambia algo", [o["prendas"] for o in a0["outfits"]] != [o["prendas"] for o in a1["outfits"]])

# Camisa de béisbol (visto en uso): por tipo es camisa, pero no es de oficina.
check("béisbol se detecta en la descripción",
      outfits._informal("camisa", {"descripcion": "Camisa de béisbol negra"}, "") == "de béisbol")
bb = dict(P(12, "arriba", "camisa", "negro", tejido="sintetico"), informal="de béisbol")
check("camisa de béisbol: ni Business Casual ni Preppy",
      outfits.encaje(bb, "business_casual")["nivel"] == 0
      and outfits.encaje(bb, "preppy")["nivel"] == 0
      and "béisbol" in outfits.encaje(bb, "business_casual")["razones"][0])
check("camisa de béisbol: sí Casual y Streetwear",
      outfits.encaje(bb, "casual")["nivel"] and outfits.encaje(bb, "streetwear")["nivel"])

print("\n=== 6d. Formalidad y capas ===")
F = outfits.formalidad
check("camisa de béisbol: 2", F("camisa", "rayas", None, None, "camisa de beisbol negra")[0] == 2)
check("chino de vestir: 5", F("chino", "liso", None, "largo", "pantalon chino de vestir")[0] == 5)
check("pantalón cargo: 2", F("pantalon", "liso", None, "largo", "pantalon cargo largo")[0] == 2)
check("camisa de franela: 3", F("camisa", "cuadros", None, None, "camisa de franela")[0] == 3)
check("«informal» no cuenta como «formal»", F("camisa", "liso", None, None, "camisa informal")[0] == 3)
check("bermuda tipo chino: 3, nunca más", F("bermuda", "liso", None, "corto", "bermuda tipo chino de vestir")[0] == 3)
check("jogger: 1", F("jogger", "liso", None, "largo", "")[0] == 1)
bc = dict(P(13, "arriba", "camisa", "negro"), formalidad=2, formal_por="de béisbol")
check("fuera de ventana: Business Casual lo dice con la formalidad",
      "formalidad 2/5" in (outfits.encaje(bc, "business_casual")["razones"][0]))
ch = dict(P(14, "abajo", "bermuda", "beige"), formalidad=3)
check("Athleisure: bermuda de sastre no", outfits.encaje(ch, "athleisure")["nivel"] == 0)
cam, blz, ber, vaq = P(0, "arriba", "camiseta", "blanco"), P(8, "encima", "blazer", "gris"), \
    P(10, "abajo", "bermuda", "verde"), P(4, "abajo", "vaquero", "azul marino")
check("americana con bermuda: no", not outfits.capas_ok(cam, blz, ber))
check("americana con vaquero: sí", outfits.capas_ok(cam, blz, vaq))
pol, sud = P(15, "arriba", "polo", "rojo"), P(3, "encima", "sudadera", "gris")
check("sudadera encima de un polo: no", not outfits.capas_ok(pol, sud, vaq))
cms = P(2, "arriba", "camisa", "azul marino")
jcv = dict(P(16, "encima", "jersey", "beige"), cuello_alto=True)
check("cuello vuelto sobre camisa: no", not outfits.capas_ok(cms, jcv, vaq))
cmc = dict(cms, manga_corta=True)
check("americana sobre camisa de manga corta: no", not outfits.capas_ok(cmc, blz, vaq))
check("salto de formalidad > 2 en un look: no",
      outfits.reglas_estilo("casual", [dict(cms, formalidad=5), dict(ber, formalidad=1)]) is None)

print("\n=== 6e. Rasgos de la IA y lo declarado ===")
check("rasgo cargo sin palabras: 2", F("pantalon", "liso", None, "largo", "", rasgos={"cargo": True})[0] == 2)
check("rasgo de vestir: chino 5", F("chino", "liso", None, "largo", "", rasgos={"de_vestir": True})[0] == 5)
check("rasgo fantasía: camisa 2", F("camisa", "liso", None, None, "", rasgos={"fantasia": True})[0] == 2)
check("las notas mandan sobre los rasgos",
      F("camisa", "liso", None, None, "", rasgos={"fantasia": True}, notas="camisa de vestir")[0] == 5)
check("notas sin nada de formalidad no borran los rasgos",
      F("camisa", "liso", None, None, "", rasgos={"fantasia": True}, notas="mi favorita")[0] == 2)
check("notas que solo describen no tapan los rasgos",
      F("jersey", "liso", None, None, "sudadera", rasgos={"deportiva": True},
        notas="jersey de cuello alto con cremallera")[0] == 2)
check("«casual» en las notas: manda lo declarado, sin rasgos",
      F("camisa", "liso", None, None, "", rasgos={"de_vestir": True}, notas="camisa lisa casual")[0] == 4)
check("rasgo deportiva solo: tope 2 (el 1 lo dan las palabras)",
      F("cazadora", "liso", None, None, "cazadora bomber", rasgos={"deportiva": True})[0] == 2)
check("logo discreto (rasgo): no es gráfico",
      F("polo", "logo", None, None, "", rasgos={"logo_discreto": True})[0] == 3)

print("\n=== 7. Valoraciones ===")
tmp = pathlib.Path(tempfile.mkdtemp())
BD = tmp / "u.db"
auth.registrar(BD, "a@a.es", "Ana", "clave-larga-1")
auth.registrar(BD, "b@b.es", "Bea", "clave-larga-2")
v = lambda s: np.random.default_rng(len(s)).normal(size=armario.DIM)  # noqa: E731
from PIL import Image  # noqa: E402
import io  # noqa: E402


def foto(c):
    b = io.BytesIO()
    Image.new("RGB", (400, 400), c).save(b, format="JPEG")
    return b.getvalue()


a1 = armario.anadir(BD, tmp / "d", 1, "camiseta", "arriba", foto((200, 0, 0)), v)
a2 = armario.anadir(BD, tmp / "d", 1, "vaquero", "abajo", foto((0, 0, 90)), v)
oid = armario.valorar_outfit(BD, 1, {"arriba": a1, "abajo": a2}, 1, estilo="casual")
oid2 = armario.valorar_outfit(BD, 1, {"arriba": a1, "abajo": a2}, -1, estilo="casual")
check("valorar dos veces actualiza, no duplica",
      oid == oid2 and list(armario.valoraciones(BD, 1).values()) == [-1])
try:
    armario.valorar_outfit(BD, 2, {"arriba": a1, "abajo": a2}, 1)
    check("no se valora con prendas ajenas", False)
except ValueError:
    check("no se valora con prendas ajenas", True)
check("detalles: el dueño sí", armario.actualizar_detalles(BD, 1, a1, {"corte": "holgado"}))
check("detalles: otro no", not armario.actualizar_detalles(BD, 2, a1, {"corte": "x"}))
check("altura: se guarda y se lee", auth.guardar_altura(BD, 1, 168)[0]
      and auth.datos(BD, 1)["altura_cm"] == 168)
check("altura: fuera de rango no", not auth.guardar_altura(BD, 1, 20)[0])
check("altura: se puede borrar", auth.guardar_altura(BD, 1, None)[0]
      and auth.datos(BD, 1)["altura_cm"] is None)
check("categoría: el dueño la cambia", armario.actualizar_categoria(BD, 1, a1, "Sudadera", "arriba")
      and [f for f in armario.listar(BD, 1)[1] if f["id"] == a1][0]["categoria"] == "sudadera")
check("categoría: otro no", not armario.actualizar_categoria(BD, 2, a1, "polo", "arriba"))
check("business casual sin chándal ni cargo",
      all(not prendas[o["prendas"]["abajo"]].get("informal")
          for o in outfits.generar([dict(p, informal=(p["tipo"] == "jogger")) for p in prendas],
                                   "business_casual")["outfits"]))
check("borrar una prenda valorada no falla", armario.borrar(BD, tmp / "d", 1, a1))

print()
if fallos:
    print(f"FALLAN {len(fallos)}: {fallos}")
    sys.exit(1)
print("Todo en orden.")
