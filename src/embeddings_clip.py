"""
Paso 3 — Extracción de embeddings CLIP sobre el corpus.

Calcula el embedding visual de cada imagen de `corpus.parquet` con un backbone
CLIP CONGELADO. Es la entrada de las seis condiciones del protocolo: el baseline
CLIP plano usa estos vectores tal cual, y las cabezas de atributo se entrenan
encima sin tocar el backbone.

Se ejecuta UNA VEZ. A partir de aquí, entrenar y evaluar no vuelve a mirar una
sola imagen, que es lo que hace viable iterar en un portátil.

Diseño
------
**Reanudable.** Escribe en fragmentos (`shards`) de N imágenes. Si se corta la
corriente, se cierra la terminal o Windows decide actualizarse, al relanzar
detecta lo ya hecho y sigue. Con 155.369 imágenes, no tener esto significa
arriesgar la tirada entera cada vez.

**Tolerante a imágenes corruptas.** DeepFashion tiene ficheros que PIL no puede
abrir. Se registran en un CSV aparte y se continúa. Reventar en la imagen
140.000 por un JPEG malo sería absurdo.

**fp32 por defecto.** fp16 es ~2x más rápido, pero cambia los vectores en el
último decimal y el proyecto se compromete a resultados reproducibles. Con una
GPU moderna el ahorro no compensa. Existe --fp16 para quien lo quiera, y queda
registrado en el YAML de la corrida.

Uso
---
    python src/embeddings_clip.py \
        --data-root data/raw/deepfashion \
        --corpus data/processed/corpus.parquet \
        --out data/embeddings

    # prueba rápida antes de lanzar las 155k
    python src/embeddings_clip.py ... --limit 200
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import time

import numpy as np
import pandas as pd
import torch
import yaml
from PIL import Image, ImageFile
from torch.utils.data import DataLoader, Dataset

# Algunos JPEG de DeepFashion vienen truncados. Sin esto, PIL lanza
# OSError("image file is truncated") a mitad del corpus.
ImageFile.LOAD_TRUNCATED_IMAGES = True

MODELO_POR_DEFECTO = "openai/clip-vit-base-patch32"  # 512 dims, el de la entrega 3

# Extensiones aceptadas en modo --carpeta. HEIC no esta: PIL no lo abre sin
# pillow-heif, y el protocolo de foto ya pide JPG/PNG al movil.
EXTENSIONES_IMG = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def extraer_vector(salida) -> torch.Tensor:
    """Saca el tensor (batch, dim) de lo que devuelvan get_image_features o
    get_text_features.

    En transformers 4.x devolvia el tensor directamente. En 5.x devuelve un
    BaseModelOutputWithPooling, donde el embedding proyectado esta en
    `pooler_output` (el `last_hidden_state` son los estados de vision SIN
    proyectar, de dimension distinta: usarlo por error daria vectores del
    tamano equivocado sin que nada se queje hasta mucho despues).

    Se soportan las dos porque la version de transformers no esta clavada en
    requirements.txt hasta que se haga el pip freeze.
    """
    if isinstance(salida, torch.Tensor):
        return salida
    for campo in ("image_embeds", "text_embeds", "pooler_output"):
        v = getattr(salida, campo, None)
        if v is not None and v.dim() == 2:
            return v
    raise RuntimeError(
        f"No se reconoce la salida de get_image_features ({type(salida).__name__}, "
        f"campos: {list(getattr(salida, 'keys', lambda: [])())}). "
        f"Ha cambiado la API de transformers; revisa extraer_vector()."
    )


class CorpusImagenes(Dataset):
    """Devuelve (tensor preprocesado, indice, ok). Nunca lanza excepcion.

    Una imagen ilegible devuelve un tensor de ceros y ok=False. El fallo se
    propaga como dato, no como excepcion: asi un JPEG corrupto en la posicion
    140.000 no tira ocho minutos de trabajo, y ademas queda contado.
    """

    def __init__(self, raiz: pathlib.Path, rutas: list[str], preproceso,
                 recorte: float = 1.0):
        self.raiz = raiz
        self.rutas = rutas
        self.preproceso = preproceso
        self.recorte = recorte

    def __len__(self) -> int:
        return len(self.rutas)

    def __getitem__(self, i: int):
        try:
            with Image.open(self.raiz / self.rutas[i]) as im:
                im = im.convert("RGB")
                if self.recorte < 1.0:
                    # Recorte central. Existe por las fotos del armario: se
                    # tomaron sobre una colcha de rayas, y ese patron ocupa
                    # medio encuadre y entra en el embedding igual que la
                    # prenda. Recortar no elimina el fondo, pero reduce su peso
                    # de forma controlada.
                    #
                    # Que acota exactamente: recortar solo el armario acerca su
                    # ENCUADRE al de DeepFashion (imagenes de tienda, prenda
                    # ocupando casi todo el marco) ademas de quitar colcha. Las
                    # dos cosas se mueven juntas y no se pueden separar con este
                    # diseno. En la memoria se reporta como "contribucion
                    # conjunta de fondo y encuadre", no como "efecto de la
                    # colcha". Decir lo segundo seria vender mas de lo medido.
                    #
                    # Centrado y CONSERVANDO LA RELACION DE ASPECTO. La
                    # version anterior recortaba un cuadrado del lado corto:
                    # en una foto vertical 3:4 eso corta por arriba y por
                    # abajo y le quita las perneras a un pantalon. Entonces la
                    # ablation mediria "prendas cortadas", no "menos fondo",
                    # que es justo el confusor que intenta eliminar.
                    w, h = im.size
                    nw, nh = int(w * self.recorte), int(h * self.recorte)
                    izq, arr = (w - nw) // 2, (h - nh) // 2
                    im = im.crop((izq, arr, izq + nw, arr + nh))
                px = self.preproceso(images=im,
                                     return_tensors="pt")["pixel_values"][0]
            return px, i, True
        except Exception:
            return torch.zeros(3, 224, 224), i, False


def shards_existentes(out: pathlib.Path) -> tuple[set[str], int]:
    """Rutas ya procesadas y siguiente numero de shard libre.

    Un shard solo cuenta si tiene sus DOS ficheros (.npy e .parquet). Si el
    proceso murio entre escribir uno y el otro, el shard esta a medias y se
    descarta: reprocesar unas miles de imagenes es barato, mezclar vectores con
    rutas equivocadas no se detecta nunca.
    """
    hechas: set[str] = set()
    siguiente = 0
    for idx_f in sorted(out.glob("idx_*.parquet")):
        n = int(idx_f.stem.split("_")[1])
        npy_f = out / f"emb_{n:05d}.npy"
        if not npy_f.exists():
            print(f"  shard {n} incompleto (falta {npy_f.name}), se rehace")
            continue
        df = pd.read_parquet(idx_f)
        vecs = np.load(npy_f, mmap_mode="r")
        if len(df) != len(vecs):
            print(f"  shard {n} descuadrado ({len(df)} rutas vs {len(vecs)} "
                  f"vectores), se rehace")
            continue
        hechas |= set(df["image_path"])
        siguiente = max(siguiente, n + 1)
    return hechas, siguiente


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--data-root", type=pathlib.Path, default=None,
                   help="Raiz de DeepFashion; las rutas del corpus cuelgan de aqui")
    p.add_argument("--carpeta", type=pathlib.Path, default=None,
                   help="Modo armario: extrae de un directorio de imagenes en vez "
                        "de un corpus.parquet. Sustituye a --data-root/--corpus")
    p.add_argument("--corpus", type=pathlib.Path,
                   default=pathlib.Path("data/processed/corpus.parquet"))
    p.add_argument("--out", type=pathlib.Path, default=pathlib.Path("data/embeddings"))
    p.add_argument("--modelo", default=MODELO_POR_DEFECTO)
    p.add_argument("--batch-size", type=int, default=256)
    p.add_argument("--num-workers", type=int, default=4,
                   help="0 si el DataLoader da problemas en Windows")
    p.add_argument("--shard-size", type=int, default=20_000)
    p.add_argument("--fp16", action="store_true",
                   help="Mas rapido, pero cambia los vectores. Por defecto fp32")
    p.add_argument("--limit", type=int, default=None,
                   help="Procesa solo las N primeras. Para probar antes de lanzar")
    p.add_argument("--device", default=None)
    p.add_argument("--recorte", type=float, default=1.0,
                   help="Recorte central cuadrado como fraccion del lado corto "
                        "(1.0 = imagen entera, 0.6 = recorta al 60%%). Se usa "
                        "para la ablation de fondo del armario")
    args = p.parse_args()
    if not 0.1 <= args.recorte <= 1.0:
        print("ERROR: --recorte debe estar entre 0.1 y 1.0", file=sys.stderr)
        return 1

    # Antes de gastar GPU: comprobar que se puede escribir parquet. El volcado
    # de fragmentos ocurre DESPUES del computo, y descubrir alli que la ruta de
    # escritura esta rota tira todo el trabajo.
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    from compat_parquet import comprobar_parquet
    comprobar_parquet()

    from transformers import AutoImageProcessor, CLIPModel

    dev = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    if dev == "cpu":
        print("AVISO: no hay GPU disponible; en CPU esto tarda horas.\n"
              "       Si esperabas GPU, comprueba torch.cuda.is_available() "
              "ANTES de dejarlo corriendo.")
    else:
        print(f"GPU: {torch.cuda.get_device_name(0)}")

    args.out.mkdir(parents=True, exist_ok=True)

    # El armario no tiene corpus.parquet: son fotos sueltas en un directorio.
    # Se escanea y se ORDENA, porque el reparto en shards depende del orden y
    # una lista no determinista rompe la reanudacion (un shard ya escrito
    # dejaria de corresponder con lo que se recalcula).
    if args.carpeta is not None:
        args.data_root = args.carpeta
        rutas_todas = sorted(
            q.relative_to(args.carpeta).as_posix()
            for q in args.carpeta.rglob("*")
            if q.suffix.lower() in EXTENSIONES_IMG
        )
        if not rutas_todas:
            print(f"ERROR: no hay imagenes en {args.carpeta}")
            return 1
        print(f"carpeta: {len(rutas_todas):,} imagenes")
    else:
        if args.data_root is None:
            print("ERROR: hace falta --data-root (junto a --corpus) o bien --carpeta")
            return 1
        corpus = pd.read_parquet(args.corpus)
        rutas_todas = corpus["image_path"].tolist()
        print(f"corpus: {len(rutas_todas):,} imagenes")

    if args.limit:
        rutas_todas = rutas_todas[: args.limit]

    hechas, shard_n = shards_existentes(args.out)
    pendientes = [r for r in rutas_todas if r not in hechas]
    if hechas:
        print(f"ya procesadas: {len(hechas):,}  |  pendientes: {len(pendientes):,}")
    if not pendientes:
        print("Nada que hacer. Todo el corpus tiene embedding.")
        return 0

    print(f"cargando {args.modelo} ...")
    preproceso = AutoImageProcessor.from_pretrained(args.modelo)
    modelo = CLIPModel.from_pretrained(args.modelo).to(dev).eval()
    # Backbone CONGELADO: no se entrena, no se afina. Es la premisa del
    # proyecto y aqui se hace explicito.
    for q in modelo.parameters():
        q.requires_grad_(False)
    if args.fp16 and dev == "cuda":
        modelo = modelo.half()
    dim_esperada = int(modelo.config.projection_dim)
    print(f"  projection_dim = {dim_esperada}")

    ds = CorpusImagenes(args.data_root, pendientes, preproceso, args.recorte)
    dl = DataLoader(ds, batch_size=args.batch_size, shuffle=False,
                    num_workers=args.num_workers, pin_memory=(dev == "cuda"))

    buf_vec: list[np.ndarray] = []
    buf_ruta: list[str] = []
    fallos: list[str] = []
    hechas_ahora = 0
    t0 = time.time()

    def volcar_shard() -> None:
        nonlocal shard_n, buf_vec, buf_ruta
        if not buf_vec:
            return
        vecs = np.concatenate(buf_vec).astype(np.float32)
        # El .npy primero y el .parquet despues: si el proceso muere entre
        # ambos, shards_existentes() ve el parquet ausente y rehace el shard.
        # Al reves, veria un parquet sin vectores y lo daria por bueno.
        np.save(args.out / f"emb_{shard_n:05d}.npy", vecs)
        pd.DataFrame({"image_path": buf_ruta}).to_parquet(
            args.out / f"idx_{shard_n:05d}.parquet", index=False)
        print(f"  shard {shard_n:05d} escrito ({len(buf_ruta):,} vectores)")
        shard_n += 1
        buf_vec, buf_ruta = [], []

    with torch.inference_mode():
        for px, idxs, oks in dl:
            px = px.to(dev, non_blocking=True)
            if args.fp16 and dev == "cuda":
                px = px.half()
            feats = extraer_vector(modelo.get_image_features(pixel_values=px))
            if feats.shape[1] != dim_esperada:
                raise RuntimeError(
                    f"Los vectores salen de dimension {feats.shape[1]} y el "
                    f"modelo declara projection_dim={dim_esperada}. Se estaria "
                    f"guardando el tensor equivocado."
                )
            feats = feats.float().cpu().numpy()

            oks = oks.numpy()
            idxs = idxs.numpy()
            for j in range(len(idxs)):
                r = pendientes[idxs[j]]
                if oks[j]:
                    buf_vec.append(feats[j : j + 1])
                    buf_ruta.append(r)
                else:
                    fallos.append(r)

            hechas_ahora += len(idxs)
            if hechas_ahora % (args.batch_size * 10) < args.batch_size:
                tr = time.time() - t0
                vel = hechas_ahora / max(tr, 1e-9)
                queda = (len(pendientes) - hechas_ahora) / max(vel, 1e-9)
                print(f"  {hechas_ahora:>7,}/{len(pendientes):,}  "
                      f"{vel:6.1f} img/s  faltan ~{queda / 60:5.1f} min", flush=True)

            if len(buf_ruta) >= args.shard_size:
                volcar_shard()

    volcar_shard()

    if fallos:
        f = args.out / "imagenes_fallidas.csv"
        pd.DataFrame({"image_path": fallos}).to_csv(f, index=False)
        print(f"\n{len(fallos)} imagenes ilegibles, listadas en {f.name}")

    cfg = {
        "modelo": args.modelo,
        "dim": int(modelo.config.projection_dim),
        "precision": "fp16" if args.fp16 else "fp32",
        "device": dev,
        "batch_size": args.batch_size,
        "corpus": str(args.corpus),
        "n_corpus": len(rutas_todas),
        "n_fallidas": len(fallos),
        # str() explicito: torch.__version__ es un TorchVersion, no un str, y
        # yaml.safe_dump se niega a serializarlo.
        "torch": str(torch.__version__),
        "backbone_congelado": True,
        "recorte": float(args.recorte),
    }
    with open(args.out / "config_embeddings.yaml", "w", encoding="utf-8") as fh:
        yaml.safe_dump(cfg, fh, allow_unicode=True, sort_keys=False)

    print(f"\nHecho en {(time.time() - t0) / 60:.1f} min. "
          f"Ejecuta --verificar para consolidar y comprobar.")
    return 0


def verificar(out: pathlib.Path, corpus_f: pathlib.Path) -> int:
    """Consolida los shards y comprueba que cubren el corpus.

    Se ejecuta aparte porque es la comprobacion que decide si el paso 3 esta
    terminado. Un indice de embeddings al que le faltan imagenes en silencio
    envenena todo lo que viene despues.
    """
    idxs = sorted(out.glob("idx_*.parquet"))
    if not idxs:
        print("No hay shards.", file=sys.stderr)
        return 1

    rutas, vecs = [], []
    for f in idxs:
        n = int(f.stem.split("_")[1])
        rutas.append(pd.read_parquet(f))
        vecs.append(np.load(out / f"emb_{n:05d}.npy"))
    idx_df = pd.concat(rutas, ignore_index=True)
    V = np.concatenate(vecs).astype(np.float32)

    print(f"shards: {len(idxs)}  |  vectores: {V.shape}  |  rutas: {len(idx_df):,}")
    if len(idx_df) != len(V):
        print("ERROR: rutas y vectores no cuadran.", file=sys.stderr)
        return 1
    if idx_df["image_path"].duplicated().any():
        d = int(idx_df["image_path"].duplicated().sum())
        print(f"ERROR: {d} rutas duplicadas entre shards.", file=sys.stderr)
        return 1

    # El armario no tiene corpus.parquet contra el que contrastar: la lista de
    # imagenes SALE del directorio, asi que "faltar" no significa nada ahi.
    # Sin esta rama, verificar leeria el corpus de DeepFashion por defecto y
    # anunciaria 155.000 imagenes sin embedding, que es un error inventado.
    if corpus_f is None:
        faltan = set()
        print("sin corpus de referencia (modo carpeta): solo se consolida")
    else:
        corpus = pd.read_parquet(corpus_f)
        faltan = set(corpus["image_path"]) - set(idx_df["image_path"])
        print(f"corpus: {len(corpus):,}  |  sin embedding: {len(faltan):,}")

    normas = np.linalg.norm(V, axis=1)
    nulos = int((normas < 1e-6).sum())
    print(f"norma media {normas.mean():.3f} (min {normas.min():.3f}, "
          f"max {normas.max():.3f})  |  vectores nulos: {nulos}")
    if nulos:
        print("  AVISO: un vector nulo suele ser una imagen que se colo ilegible.")

    np.save(out / "embeddings.npy", V)
    idx_df.to_parquet(out / "embeddings_index.parquet", index=False)
    print(f"\nConsolidado -> embeddings.npy + embeddings_index.parquet")
    return 0 if not faltan and not nulos else 1


if __name__ == "__main__":
    if "--verificar" in sys.argv:
        pa = argparse.ArgumentParser()
        pa.add_argument("--verificar", action="store_true")
        pa.add_argument("--out", type=pathlib.Path,
                        default=pathlib.Path("data/embeddings"))
        pa.add_argument("--corpus", type=pathlib.Path,
                        default=pathlib.Path("data/processed/corpus.parquet"))
        pa.add_argument("--sin-corpus", action="store_true",
                        help="Modo carpeta: no hay lista de referencia que cuadrar")
        a, _ = pa.parse_known_args()
        raise SystemExit(verificar(a.out, None if a.sin_corpus else a.corpus))
    raise SystemExit(main())
