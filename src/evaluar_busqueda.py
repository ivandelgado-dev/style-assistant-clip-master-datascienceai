"""
¿Qué orden encuentra mejor la prenda de una foto con modelo?

Protocolo (escrito antes de ver ningún resultado)
-------------------------------------------------
Pregunta: con la foto de una persona que lleva una prenda, ¿sale esa misma
prenda la primera entre las candidatas?

Datos: parejas de la MISMA prenda de una tienda, en dos fotos de su página:
    data/eval_color/producto/<pos>_<nn>.<ext>   la prenda sola
    data/eval_color/modelo/<pos>_<nn>.<ext>     un modelo que la lleva puesta
<pos> es arriba, encima o abajo. Una foto de producto sin foto de modelo entra
solo como distractor. Las fotos no salen de la máquina salvo hacia la API de
Gemini (método «etiquetas»): data/ está en .gitignore y son de un tercero.

Consulta: la foto del modelo recortada como la recorta la aplicación en modo
«Una persona» (busqueda.cajas_look, cintura 0,52). Galería: todos los
productos de la misma posición; con --armario, además las 118 prendas del
autor, que es la situación real de su cuenta.

Métodos:
  clip_plano     coseno sin proyección (el baseline del trabajo)
  actual         coseno en la proyección conjunta (lo que hace hoy la app)
  color_primero  franja de color por píxeles (umbrales calibrados en el
                 armario ANTES de esta prueba) y, dentro, el orden «actual»
  etiquetas      penalización por etiquetas de Gemini (tipo, manga/largo,
                 color, estampado, tejido; pesos fijados en
                 paginas/etiquetas.py) y, a igualdad, el orden «actual»

Métricas: acierto@1, acierto@3, rango recíproco medio; frente a «actual»,
consultas que mejoran / empeoran / igual, con prueba de signos. Con 24
parejas los intervalos son anchos: se reportan las cuentas.

Regla de decisión (escrita antes): un método entra en la aplicación si
mejora el acierto@1 de «actual» sin empeorar el @3. Si entran los dos, gana
el de más acierto@1; a igualdad, @3; a igualdad, MRR.

Además, con --armario se mide la fiabilidad de las etiquetas contra lo que
el autor anotó a mano en sus 118 prendas: el tipo (su categoría) y la manga
(cuando su descripción dice «manga corta» o «manga larga»).

Uso
---
    python src/evaluar_busqueda.py
    python src/evaluar_busqueda.py --armario
    python src/evaluar_busqueda.py --sin-gemini      (sin red / sin clave)
"""

from __future__ import annotations

import argparse
import ast
import json
import math
import pathlib
import sys
import warnings

import numpy as np
import pandas as pd
import torch
from PIL import Image

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "src"))
warnings.filterwarnings("ignore")

from embeddings_clip import extraer_vector          # noqa: E402
from entrenar_proyecciones import Proyeccion        # noqa: E402
from paginas import color, etiquetas, gemini        # noqa: E402

MODELO = "openai/clip-vit-base-patch32"
CABEZA = RAIZ / "experiments/conjunta/cabeza_conjunta.pt"
CALIB = RAIZ / "experiments/color_primero/calibracion.json"
SALIDA = RAIZ / "experiments/busqueda_modelo_producto"
POSICIONES = ("arriba", "encima", "abajo")
METODOS = ("clip_plano", "actual", "color_primero", "etiquetas", "estructura",
           "prioridades", "prioridades_ia")
# «estructura» se añadió DESPUÉS de ver los resultados de los otros cuatro:
# es un análisis a posteriori, no confirmatorio, y se reporta así. Sale de
# hechos medidos antes de decidirlo: el orden por etiquetas fallaba por el
# color leído con otra luz, y tipo, manga y largo fueron los campos estables
# y fiables. Reproduce lo que hace la aplicación con ORDEN_ESTRUCTURA:
#   - candidatos: los de la posición + los del mismo tipo en otra posición
#   - penalización solo de tipo, manga y largo (etiquetas.penalizacion_estructura)
#   - si la IA ve algo abierto encima, lo de arriba se busca en la franja
#     central (busqueda.caja_interior)
# Su galería puede ser mayor que la de los demás métodos (n_galeria_estructura).
#
# «prioridades» (segunda ronda a posteriori, 24/09). Motivo: con la
# aplicación en uso, el autor vio la prenda exacta de la foto salir segunda
# por detrás de otra de distinto color, y los datos de la primera ronda lo
# confirman (arriba_02: puesto 29 con «actual», 1 con CLIP plano y con el
# color primero). La proyección conjunta se entrenó con atributos de
# DeepFashion, casi sin colores: ordena por forma y el color le es ajeno.
# Implementa el orden que el autor pidió (color, luego tela, luego corte) con
# la estructura delante; claves, de más a menos importante:
#   1. estructura dura: familia de tipo, manga, largo (etiquetas.niveles_prioridad)
#   2. franja de color por píxeles (la de color_primero)
#   3. estructura blanda: otro tipo del mismo grupo (vaquero / pantalón)
#   4. parecido en la proyección conjunta
# Misma galería, recorte y candidatos que «estructura».
# REGLA, escrita antes de medirlo: entra (sustituye a «estructura» en la
# aplicación) si en la galería real (--armario) no empeora ni el acierto@1
# ni el @3 de «estructura». Se reporta también la galería limpia y el
# recuento consulta a consulta frente a «estructura».
# RESULTADO: no entra (real 16/23 frente a 17/22; limpia 20/24 frente a 17/22).
#
# TERCERA RONDA — «prioridades_ia», confirmatoria, con parejas NUEVAS.
# Protocolo escrito el 24/09, ANTES de recoger las parejas:
#   Qué cambia: la clave 2 (color) sale de las etiquetas de la IA
#   (etiquetas.franja_color: 0 mismo color, 1 misma familia, 2 otro) y no de
#   los píxeles. Motivo, visto en la segunda ronda: el color de la IA cae en
#   la misma familia en modelo y producto en 19 de 24 parejas; la franja por
#   píxeles es 0 o 1 solo en 15 de 24. Como eso se vio en las mismas 24
#   parejas, se prueba en otras.
#   Datos: data/eval_color2, mismo formato. Productos seguidos del listado de
#   hombre de la tienda, en su orden, saltando solo los que no tengan una
#   foto de modelo en la que se vea la prenda y los que ya estén en
#   data/eval_color. Objetivo: 6 arriba, 6 abajo, 4 encima o más.
#   Galería: los productos nuevos + los 24 de la primera prueba como
#   distractores (--distractores) + las 118 del autor (--armario).
#   Regla: entra si en esa galería no empeora ni el acierto@1 ni el @3 de
#   «estructura». «prioridades» (píxeles) se mide también, solo como réplica:
#   ya no puede entrar.
#   Resultados en experiments/busqueda_ronda3 (--salida), aparte de los de
#   las dos primeras rondas.


def _de_busqueda(nombre: str):
    """Lee una definición de paginas/busqueda.py sin importarlo (arrastraría
    Streamlit). Así el recorte y el mapa de posiciones son LOS MISMOS."""
    src = (RAIZ / "paginas/busqueda.py").read_text(encoding="utf-8")
    for n in ast.parse(src).body:
        if isinstance(n, ast.FunctionDef) and n.name == nombre:
            ns: dict = {}
            exec(compile(ast.Module(body=[n], type_ignores=[]), nombre, "exec"), ns)
            return ns[nombre]
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == nombre:
            return ast.literal_eval(n.value)
    raise KeyError(nombre)


def recortar(im, caja):
    w, h = im.size
    x0, y0, x1, y1 = caja
    return im.crop((int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)))


def signos(mejor: int, peor: int) -> float:
    """p bilateral de la prueba de signos (binomial exacta, empates fuera)."""
    n = mejor + peor
    if n == 0:
        return 1.0
    k = min(mejor, peor)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--carpeta", type=pathlib.Path, default=RAIZ / "data/eval_color")
    ap.add_argument("--armario", action="store_true",
                    help="añadir las 118 prendas del autor como distractores")
    ap.add_argument("--sin-gemini", action="store_true")
    ap.add_argument("--distractores", type=pathlib.Path, nargs="*", default=[],
                    help="carpetas con producto/ que entran solo como distractores")
    ap.add_argument("--salida", type=pathlib.Path, default=SALIDA)
    ap.add_argument("--lote", type=int, default=10,
                    help="fotos por petición a Gemini (la cuota cuenta peticiones)")
    args = ap.parse_args()

    cal = json.loads(CALIB.read_text(encoding="utf-8"))
    if cal["version_color"] != color.VERSION:
        print("ERROR: calibración de otra versión del color. Lanza calibrar_color.py.")
        return 1
    t1, t2 = cal["umbral_mismo_color"], cal["umbral_color_cercano"]

    prod = {f.stem: f for f in sorted((args.carpeta / "producto").glob("*.*"))}
    mod = {f.stem: f for f in sorted((args.carpeta / "modelo").glob("*.*"))}
    claves = sorted(set(prod) & set(mod))
    if set(mod) - set(prod):
        print(f"AVISO: modelo sin producto, se ignoran: {sorted(set(mod) - set(prod))}")
    malas = [c for c in prod if c.split("_")[0] not in POSICIONES]
    if malas or not claves:
        print(f"ERROR: nombres sin posición {malas} o sin parejas en {args.carpeta}")
        return 1

    usar_gemini = not args.sin_gemini and gemini.disponible()
    modelo_vlm = None
    if usar_gemini:
        try:
            modelo_vlm = gemini.elegir_modelo()
            print(f"Gemini: {modelo_vlm}")
        except gemini.ErrorGemini as e:
            print(f"AVISO: Gemini no disponible ({e}). Se sigue sin etiquetas.")
            usar_gemini = False
    elif not args.sin_gemini:
        print("AVISO: no hay GEMINI_API_KEY; se sigue sin etiquetas.")

    def etiquetar(ruta: pathlib.Path) -> dict | None:
        """Solo lee la caché: el etiquetado se hace antes, por lotes."""
        if not usar_gemini:
            return None
        return etiquetas.en_cache(ruta.read_bytes(), modelo_vlm)

    from transformers import AutoImageProcessor, CLIPModel
    disp = "cuda" if torch.cuda.is_available() else "cpu"
    proc = AutoImageProcessor.from_pretrained(MODELO)
    clip = CLIPModel.from_pretrained(MODELO).eval().to(disp)
    ck = torch.load(CABEZA, map_location="cpu", weights_only=False)
    cab = Proyeccion(512, ck["dim"], mlp=ck["mlp"]).eval()
    cab.load_state_dict(ck["state_dict"])

    @torch.no_grad()
    def vec(im):
        px = proc(images=im.convert("RGB"), return_tensors="pt")["pixel_values"]
        return extraer_vector(clip.get_image_features(pixel_values=px.to(disp))).cpu()

    @torch.no_grad()
    def proyectar(v):
        return cab(v).numpy()

    def plano(v):
        v = v.numpy()
        return v / np.linalg.norm(v, axis=1, keepdims=True)

    cajas = _de_busqueda("cajas_look")(0.52)

    # ---------------- etiquetado por lotes (pocas peticiones)
    rutas_armario = []
    extra = [f for d in args.distractores for f in sorted((d / "producto").glob("*.*"))]
    if args.armario:
        pa = pd.read_csv(RAIZ / "data/raw/wardrobe/pares.csv", encoding="utf-8-sig", dtype=str)
        rutas_armario = [RAIZ / "data/raw/wardrobe/img" / f.replace("\\", "/")
                         for f in pa[pa["toma"] == "a"]["fichero"]]
    if usar_gemini:
        todas = ([prod[c] for c in sorted(prod)] + [mod[c] for c in claves]
                 + rutas_armario + extra)
        print(f"Etiquetando con Gemini ({len(todas)} fotos, {args.lote} por petición)…")
        etiquetas.analizar_lote([r.read_bytes() for r in todas], modelo_vlm, args.lote)
        falta = sum(etiquetas.en_cache(r.read_bytes(), modelo_vlm) is None for r in todas)
        if falta:
            print(f"AVISO: {falta} fotos sin etiquetar. El método «etiquetas» se "
                  "mide solo si están TODAS: vuelve a lanzar el script cuando "
                  "haya cuota (lo ya etiquetado no se repite).")
            usar_gemini = False

    # ---------------- galería
    print("Galería…")
    gal = []
    for c in sorted(prod):
        v = vec(Image.open(prod[c]))
        e = etiquetar(prod[c])
        gal.append({"id": c, "pos": c.split("_")[0], "tienda": True,
                    "lab": color.color_prenda(Image.open(prod[c]))[0],
                    "etq": e["piezas"][0] if e and e["piezas"] else None,
                    "v_c": proyectar(v)[0], "v_p": plano(v)[0]})
    for f in extra:
        pos_f = f.stem.split("_")[0]
        if pos_f not in POSICIONES:
            continue
        v = vec(Image.open(f))
        e = etiquetar(f)
        gal.append({"id": f"{f.parent.parent.name}/{f.stem}", "pos": pos_f, "tienda": False,
                    "lab": color.color_prenda(Image.open(f))[0],
                    "etq": e["piezas"][0] if e and e["piezas"] else None,
                    "v_c": proyectar(v)[0], "v_p": plano(v)[0]})
    fiab = []
    if args.armario:
        print("Armario del autor como distractor…")
        POS = _de_busqueda("POSICION")
        V = np.load(RAIZ / "data/embeddings_armario/embeddings.npy").astype(np.float32)
        rutas = (pd.read_csv(RAIZ / "data/embeddings_armario/embeddings_index.csv")
                 ["image_path"].str.replace("\\", "/", regex=False).tolist())
        p = pd.read_csv(RAIZ / "data/raw/wardrobe/pares.csv", encoding="utf-8-sig", dtype=str)
        p["fichero"] = p["fichero"].str.replace("\\", "/", regex=False)
        e_ = pd.read_csv(RAIZ / "data/raw/wardrobe/armario.csv", encoding="utf-8-sig",
                         dtype=str, keep_default_na=False)
        cat = dict(zip(e_["item_id"], e_["categoria"].str.strip().str.lower()))
        desc = dict(zip(e_["item_id"], e_["descripcion_libre"].str.lower()))
        for r in p[p["toma"] == "a"].itertuples():
            pos = POS.get(cat.get(r.prenda_id))
            if r.fichero not in rutas or pos is None:
                continue
            ruta = RAIZ / "data/raw/wardrobe/img" / r.fichero
            v = torch.from_numpy(V[rutas.index(r.fichero)][None])
            e = etiquetar(ruta)
            pz = e["piezas"][0] if e and e["piezas"] else None
            gal.append({"id": r.prenda_id, "pos": pos, "tienda": False,
                        "lab": color.color_prenda(Image.open(ruta))[0], "etq": pz,
                        "v_c": proyectar(v)[0], "v_p": plano(v)[0]})
            d = desc.get(r.prenda_id, "")
            manga = ("corta" if "manga corta" in d else
                     "larga" if "manga larga" in d else None)
            fiab.append({"prenda": r.prenda_id, "tipo_autor": cat.get(r.prenda_id),
                         "tipo_gemini": pz["tipo"] if pz else None,
                         "manga_autor": manga,
                         "manga_gemini": pz["manga"] if pz else None,
                         "persona_gemini": e["hay_persona"] if e else None})

    # ---------------- consultas
    print("Consultas…")
    filas = []
    for c in claves:
        pos = c.split("_")[0]
        im = Image.open(mod[c]).convert("RGB")
        banda = recortar(im, cajas["abajo"] if pos == "abajo" else cajas["arriba"])
        v = vec(banda)
        q_c, q_p = proyectar(v)[0], plano(v)[0]
        lab_q = color.color_persona(banda, pos)[0]
        e_q = etiquetar(mod[c])
        pz_q = etiquetas.pieza(e_q, pos)
        G = [g for g in gal if g["pos"] == pos]
        s_c = np.array([g["v_c"] @ q_c for g in G])
        s_p = np.array([g["v_p"] @ q_p for g in G])
        de = color.delta_cmc(lab_q, np.array([g["lab"] for g in G]))
        franja = np.where(de <= t1, 0, np.where(de <= t2, 1, 2))
        pen = np.array([etiquetas.penalizacion(pz_q, g["etq"]) for g in G])
        # --- «estructura», como la aplicación
        encima_q = bool(e_q) and any(q["posicion"] == "encima" for q in e_q["piezas"])
        if pos == "arriba" and encima_q:
            v_e = proyectar(vec(recortar(im, _de_busqueda("caja_interior")(0.52))))[0]
        else:
            v_e = q_c
        GE = [g for g in gal if g["pos"] == pos or etiquetas.compatibles(pz_q, g["etq"])]
        s_e = np.array([g["v_c"] @ v_e for g in GE])
        est = np.array([etiquetas.penalizacion_estructura(pz_q, g["etq"]) for g in GE])
        orden_e = np.lexsort((-s_e, est))
        # --- «prioridades»: mismo recorte para el vector y para el color
        if pos == "arriba" and encima_q:
            lab_e = color.color_persona(recortar(im, _de_busqueda("caja_interior")(0.52)), pos)[0]
        else:
            lab_e = lab_q
        de_e = color.delta_cmc(lab_e, np.array([g["lab"] for g in GE]))
        franja_e = np.where(de_e <= t1, 0, np.where(de_e <= t2, 1, 2))
        niv = np.array([etiquetas.niveles_prioridad(pz_q, g["etq"]) for g in GE],
                       dtype=int).reshape(-1, 2)
        orden_p = np.lexsort((-s_e, niv[:, 1], franja_e, niv[:, 0]))
        franja_ia = np.array([etiquetas.franja_color(pz_q, g["etq"]) for g in GE])
        orden_pi = np.lexsort((-s_e, niv[:, 1], franja_ia, niv[:, 0]))
        obj_e = next(k for k, g in enumerate(GE) if g["id"] == c and g["tienda"])
        orden = {
            "clip_plano": np.argsort(-s_p, kind="stable"),
            "actual": np.argsort(-s_c, kind="stable"),
            "color_primero": np.lexsort((-s_c, franja)),
            "etiquetas": np.lexsort((-s_c, pen)),
        }
        obj = next(k for k, g in enumerate(G) if g["id"] == c and g["tienda"])
        fila = {"consulta": c, "pos": pos, "n_galeria": len(G),
                "color_modelo": color.nombre_color(lab_q),
                "color_producto": color.nombre_color(G[obj]["lab"]),
                "franja_objetivo": int(franja[obj]),
                "persona_gemini": e_q["hay_persona"] if e_q else None,
                "pieza_gemini": (f'{pz_q["tipo"]}/{pz_q["color"]}/{pz_q["manga"]}'
                                 f'/{pz_q["largo"]}' if pz_q else None),
                "producto_gemini": (f'{G[obj]["etq"]["tipo"]}/{G[obj]["etq"]["color"]}'
                                    f'/{G[obj]["etq"]["manga"]}/{G[obj]["etq"]["largo"]}'
                                    if G[obj]["etq"] else None),
                "pen_objetivo": float(pen[obj])}
        for m, o in orden.items():
            fila[f"rango_{m}"] = int(np.where(o == obj)[0][0]) + 1
        fila["rango_estructura"] = int(np.where(orden_e == obj_e)[0][0]) + 1
        fila["rango_prioridades"] = int(np.where(orden_p == obj_e)[0][0]) + 1
        fila["rango_prioridades_ia"] = int(np.where(orden_pi == obj_e)[0][0]) + 1
        fila["n_galeria_estructura"] = len(GE)
        filas.append(fila)

    d = pd.DataFrame(filas)
    met = {}
    for m in METODOS:
        r = d[f"rango_{m}"]
        met[m] = {"acierto@1": round(float((r == 1).mean()), 3),
                  "acierto@3": round(float((r <= 3).mean()), 3),
                  "mrr": round(float((1 / r).mean()), 3),
                  "n@1": int((r == 1).sum()), "n@3": int((r <= 3).sum())}
    frente = {}
    for m in ("color_primero", "etiquetas", "estructura"):
        mejor = int((d[f"rango_{m}"] < d["rango_actual"]).sum())
        peor = int((d[f"rango_{m}"] > d["rango_actual"]).sum())
        frente[m] = {"mejora": mejor, "empeora": peor, "igual": len(d) - mejor - peor,
                     "p_signos": round(signos(mejor, peor), 3)}

    mejor = int((d["rango_prioridades"] < d["rango_estructura"]).sum())
    peor = int((d["rango_prioridades"] > d["rango_estructura"]).sum())
    frente["prioridades_frente_a_estructura"] = {
        "mejora": mejor, "empeora": peor, "igual": len(d) - mejor - peor,
        "p_signos": round(signos(mejor, peor), 3)}
    mp, me = met["prioridades"], met["estructura"]
    prioridades_entra = (usar_gemini and mp["n@1"] >= me["n@1"]
                         and mp["n@3"] >= me["n@3"])
    mejor = int((d["rango_prioridades_ia"] < d["rango_estructura"]).sum())
    peor = int((d["rango_prioridades_ia"] > d["rango_estructura"]).sum())
    frente["prioridades_ia_frente_a_estructura"] = {
        "mejora": mejor, "empeora": peor, "igual": len(d) - mejor - peor,
        "p_signos": round(signos(mejor, peor), 3)}
    mi = met["prioridades_ia"]
    ia_entra = usar_gemini and mi["n@1"] >= me["n@1"] and mi["n@3"] >= me["n@3"]

    a = met["actual"]
    entran = [m for m in ("color_primero", "etiquetas", "estructura")
              if (m not in ("etiquetas", "estructura") or usar_gemini)
              and met[m]["n@1"] > a["n@1"] and met[m]["n@3"] >= a["n@3"]]
    ganador = (max(entran, key=lambda m: (met[m]["n@1"], met[m]["n@3"], met[m]["mrr"]))
               if entran else "actual")
    res = {
        "n_parejas": len(d), "n_galeria_total": len(gal),
        "armario_como_distractor": args.armario,
        "gemini": modelo_vlm if usar_gemini else "no usado",
        "azar_acierto@1": round(float((1 / d["n_galeria"]).mean()), 3),
        "umbrales_color": {"mismo": t1, "cercano": t2},
        "metodos": met, "frente_a_actual": frente,
        "decision": {"entran": entran, "ganador": ganador,
                     "nota": "estructura es a posteriori (ver METODOS)",
                     "prioridades_no_empeora_a_estructura": bool(prioridades_entra),
                     "prioridades_ia_no_empeora_a_estructura": bool(ia_entra),
                     "nota_prioridades": "segunda ronda a posteriori; la regla que "
                                         "cuenta es la de la galería real (--armario)"},
    }
    if usar_gemini:
        res["gemini_consultas"] = {
            "persona_detectada": int(d["persona_gemini"].fillna(False).astype(bool).sum()),
            "pieza_de_su_posicion_encontrada": int(d["pieza_gemini"].notna().sum())}
    if fiab:
        f = pd.DataFrame(fiab)
        ok_t = f["tipo_gemini"].notna()
        m = f["manga_autor"].notna() & f["manga_gemini"].notna()
        res["fiabilidad_etiquetas_armario"] = {
            "tipo_igual_categoria_autor": f"{int((f.tipo_gemini == f.tipo_autor)[ok_t].sum())}/{int(ok_t.sum())}",
            "manga_igual_descripcion_autor": f"{int((f.manga_gemini == f.manga_autor)[m].sum())}/{int(m.sum())}",
            "prenda_suelta_bien_detectada": f"{int((f.persona_gemini == False).sum())}/{len(f)}",  # noqa: E712
        }

    salida = args.salida
    salida.mkdir(parents=True, exist_ok=True)
    suf = "_armario" if args.armario else ""
    (salida / f"metricas{suf}.json").write_text(
        json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    d.to_csv(salida / f"por_consulta{suf}.csv", index=False)
    if fiab:
        pd.DataFrame(fiab).to_csv(salida / "etiquetas_armario.csv", index=False)
    (salida / "config.yaml").write_text(
        f"clip: {MODELO}\ncabeza: experiments/conjunta/cabeza_conjunta.pt\n"
        f"cintura: 0.52\nversion_color: {color.VERSION}\n"
        f"umbral_mismo: {t1}\numbral_cercano: {t2}\ndistancia_color: CMC(2:1)\n"
        f"gemini: {modelo_vlm if usar_gemini else 'no'}\n"
        f"version_etiquetas: {etiquetas.VERSION}\n"
        f"carpeta: {args.carpeta.name}\n"
        f"distractores: {[d.name for d in args.distractores]}\n"
        f"torch: {torch.__version__}\ndispositivo: {disp}\n", encoding="utf-8")

    pd.set_option("display.width", 200)
    print(d.to_string(index=False))
    print()
    print(json.dumps(res, indent=2, ensure_ascii=False))
    print()
    print(f"prioridades frente a estructura ({'galería real' if args.armario else 'galería limpia'}): "
          f"@1 {mp['n@1']} vs {me['n@1']}, @3 {mp['n@3']} vs {me['n@3']} -> "
          + ("NO EMPEORA" if prioridades_entra else "EMPEORA"))
    print(f"prioridades_ia frente a estructura: @1 {mi['n@1']} vs {me['n@1']}, "
          f"@3 {mi['n@3']} vs {me['n@3']} -> " + ("NO EMPEORA" if ia_entra else "EMPEORA"))
    print(f"(galería: {len(gal)} prendas; parejas: {len(d)}; carpeta: {args.carpeta.name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
