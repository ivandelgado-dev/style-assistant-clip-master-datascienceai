"""
Paso 4b — Entrenamiento de las proyecciones sobre CLIP congelado.

Entrena las condiciones 4, 5 y 6 del protocolo:

  4. proyeccion CONJUNTA 512->128, una sola cabeza, contrastiva sobre TODOS los
     atributos juntos. Es el baseline que controla "supervision": cualquier
     cabeza entrenada bate a CLIP zero-shot, asi que sin esta condicion no se
     puede atribuir la mejora al desacoplamiento.
  5. proyecciones POR ATRIBUTO 512->128, una cabeza por grupo. La contribucion.
  6. MLP por grupo (opcional): comprueba si la no linealidad aporta.

Las condiciones 1 (aleatorio), 2 (CLIP plano) y 3 (PCA a 128d) no requieren
entrenamiento y las construye el script de evaluacion.

Perdida
-------
Contrastiva supervisada con multiples positivos. Para un ancla y un grupo de
atributos, son positivos los ejemplares del lote que comparten al menos un
atributo SEEN de ese grupo.

Se usa solo la senal positiva: el -1 de DeepFashion no es un negativo
verificado (ver docs/resultados_eda_atributos.md). Los negativos salen del
resto del lote, que es lo que permite entrenar sin afirmar que una prenda NO
tiene un atributo.

Los atributos UNSEEN no entran en ningun par. Es lo que hace que la metrica
UNSEEN mida generalizacion y no memoria.

Uso
---
    python src/entrenar_proyecciones.py --condicion conjunta
    python src/entrenar_proyecciones.py --condicion por_atributo
    python src/entrenar_proyecciones.py --condicion por_atributo --mlp
"""

from __future__ import annotations

import argparse
import json
import pathlib
import time

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
import yaml

GRUPOS_CABEZA = ["forma", "textura", "tejido"]   # corte, textura, tejido


class Proyeccion(nn.Module):
    """Cabeza sobre el embedding congelado.

    Lineal sin sesgo por defecto: es la version interpretable y es la que el
    protocolo prefiere si iguala al MLP. El sesgo no aporta nada cuando la
    salida se normaliza a norma unitaria antes de calcular el coseno.
    """

    def __init__(self, dim_in: int, dim_out: int, mlp: bool = False,
                 oculta: int = 512, dropout: float = 0.1):
        super().__init__()
        if mlp:
            self.f = nn.Sequential(
                nn.Linear(dim_in, oculta), nn.GELU(), nn.Dropout(dropout),
                nn.Linear(oculta, dim_out, bias=False),
            )
        else:
            self.f = nn.Linear(dim_in, dim_out, bias=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return F.normalize(self.f(x), dim=-1)


def supcon(z: torch.Tensor, positivos: torch.Tensor, tau: float) -> torch.Tensor:
    """Contrastiva supervisada con multiples positivos.

    `positivos[i, j] = True` si j es positivo de i. La diagonal se excluye: una
    imagen es trivialmente positiva de si misma y dejarla dentro haria que la
    perdida se pudiera minimizar sin aprender nada.

    Las anclas sin ningun positivo en el lote se descartan; con ~3 atributos
    por imagen hay bastantes, y meterlas aportaria gradiente cero pero
    diluiria la media.
    """
    sim = z @ z.T / tau
    n = sim.size(0)
    diag = torch.eye(n, dtype=torch.bool, device=z.device)
    sim = sim.masked_fill(diag, -1e4)
    pos = positivos & ~diag

    log_prob = sim - torch.logsumexp(sim, dim=1, keepdim=True)
    n_pos = pos.sum(1)
    validos = n_pos > 0
    if not validos.any():
        return z.sum() * 0.0          # lote degenerado; gradiente cero
    media_pos = (pos.float() * log_prob).sum(1)[validos] / n_pos[validos]
    return -media_pos.mean()


def matriz_atributos(long: pd.DataFrame, orden: list[str],
                     atributos: list[str]) -> torch.Tensor:
    """Matriz binaria (n_imagenes x n_atributos), densa.

    Densa a proposito: 109.012 x 250 en bool son 27 MB. La alternativa dispersa
    complicaria el calculo de la mascara de positivos sin ahorrar nada.
    """
    pos_img = {r: i for i, r in enumerate(orden)}
    pos_at = {a: j for j, a in enumerate(atributos)}
    M = torch.zeros(len(orden), len(atributos), dtype=torch.bool)
    sub = long[long.attr_name.isin(pos_at)]
    filas = sub.image_path.map(pos_img).to_numpy()
    cols = sub.attr_name.map(pos_at).to_numpy()
    ok = ~pd.isna(filas)
    M[filas[ok].astype(int), cols[ok].astype(int)] = True
    return M


@torch.no_grad()
def perdida_val(modelo, Xv, Av, args, dev) -> float:
    """Misma perdida sobre validacion, con lotes fijos y sin barajar.

    Sirve para elegir epoca. No se toca test en ningun momento.
    """
    modelo.eval()
    utiles = torch.nonzero(Av.any(dim=1)).squeeze(1)
    # El lote de validacion se adapta al tamaño disponible en vez de exigir el
    # mismo que en entrenamiento. Exigirlo hacia que un grupo con pocas
    # imagenes de val devolviera NaN, no se guardara ningun punto de control y
    # el entrenamiento se quedara con la ultima epoca EN SILENCIO.
    #
    # El valor de la perdida contrastiva depende del tamaño de lote, asi que
    # este tiene que ser constante entre epocas — lo es, porque solo depende
    # de cuantas imagenes de val tienen atributos del grupo.
    lote = min(args.batch_size, len(utiles))
    if lote < 64:
        return float("nan")           # por debajo de esto el numero no dice nada
    total, n = 0.0, 0
    for ini in range(0, len(utiles) - lote + 1, lote):
        idx = utiles[ini : ini + lote].to(dev)
        a = Av[idx]
        pos = (a.float() @ a.float().T) > 0
        total += float(supcon(modelo(Xv[idx]), pos, args.tau).detach())
        n += 1
    return total / max(n, 1)


def entrenar_una(X, A, Xv, Av, args, dev: str,
                 etiqueta: str) -> tuple[nn.Module, list[dict]]:
    """Entrena una cabeza. X: embeddings (n,512). A: atributos (n,k) bool."""
    torch.manual_seed(args.seed)
    # Solo sirven de ancla las imagenes con al menos un atributo del grupo.
    utiles = torch.nonzero(A.any(dim=1)).squeeze(1)
    print(f"  [{etiqueta}] {len(utiles):,} imagenes con al menos un atributo "
          f"de los {A.shape[1]}")

    # Ablation de presupuesto de datos.
    #
    # La cabeza conjunta entrena con 94.488 anclas y las de grupo con 28-45k:
    # entre dos y tres veces mas. Comparar sus resultados sin igualar eso
    # confunde "desacoplar no aporta" con "las cabezas tenian menos datos", que
    # es la primera objecion que levanta el resultado negativo.
    #
    # Con --presupuesto-datos N se recorta el conjunto de anclas a N, con
    # semilla fija, para poder entrenar la conjunta con el mismo material que
    # la cabeza mas pequeña.
    if args.presupuesto_datos and len(utiles) > args.presupuesto_datos:
        g0 = torch.Generator().manual_seed(args.seed)
        sel = torch.randperm(len(utiles), generator=g0)[: args.presupuesto_datos]
        utiles = utiles[sel]
        print(f"    presupuesto aplicado: {len(utiles):,} anclas")

    modelo = Proyeccion(X.shape[1], args.dim, mlp=args.mlp).to(dev)
    opt = torch.optim.AdamW(modelo.parameters(), lr=args.lr,
                            weight_decay=args.weight_decay)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epocas)

    Xd, Ad = X.to(dev), A.to(dev)
    Xvd, Avd = Xv.to(dev), Av.to(dev)
    historial = []
    g = torch.Generator().manual_seed(args.seed)
    mejor, mejor_ep, mejor_estado = float("inf"), -1, None

    for ep in range(args.epocas):
        modelo.train()
        perm = utiles[torch.randperm(len(utiles), generator=g)]
        total, nlotes = 0.0, 0
        for ini in range(0, len(perm) - args.batch_size + 1, args.batch_size):
            idx = perm[ini : ini + args.batch_size].to(dev)
            a = Ad[idx]
            # Positivos: comparten al menos un atributo del grupo.
            pos = (a.float() @ a.float().T) > 0
            z = modelo(Xd[idx])
            loss = supcon(z, pos, args.tau)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(modelo.parameters(), 1.0)
            opt.step()
            # .detach(): sin esto torch avisa de convertir a escalar un tensor
            # con grafo, y ademas retendria el grafo del lote entero.
            total += float(loss.detach())
            nlotes += 1
        sched.step()

        vl = perdida_val(modelo, Xvd, Avd, args, dev)
        historial.append({"epoca": ep, "loss": total / max(nlotes, 1),
                          "val_loss": vl, "lr": sched.get_last_lr()[0]})
        # Seleccion de epoca por VALIDACION, nunca por test. Sin esto, las 30
        # epocas son un numero inventado y el MLP —que tiene mas capacidad—
        # podria estar sobreajustando sin que se note.
        if vl == vl and vl < mejor:      # vl == vl descarta NaN
            mejor, mejor_ep = vl, ep
            mejor_estado = {k: v.detach().clone()
                            for k, v in modelo.state_dict().items()}
        if ep % 5 == 0 or ep == args.epocas - 1:
            print(f"    epoca {ep:>3}  loss {historial[-1]['loss']:.4f}  "
                  f"val {vl:.4f}")

    if mejor_estado is not None:
        modelo.load_state_dict(mejor_estado)
        print(f"    -> se conserva la epoca {mejor_ep} (val {mejor:.4f})")
        if mejor_ep == args.epocas - 1:
            print("       AVISO: la mejor es la ultima; puede faltar entrenamiento")
    else:
        # Nunca en silencio: si no hubo seleccion, el resultado es la ultima
        # epoca por defecto, y eso hay que saberlo antes de reportar nada.
        print(f"    -> AVISO [{etiqueta}]: sin perdida de validacion utilizable, "
              f"NO ha habido seleccion de epoca. Se usa la ultima ({args.epocas - 1}). "
              f"Revisa cuantas imagenes de val tienen atributos de este grupo.")
    return modelo, historial


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--condicion", choices=["conjunta", "por_atributo"],
                   required=True)
    p.add_argument("--procesados", type=pathlib.Path,
                   default=pathlib.Path("data/processed"))
    p.add_argument("--embeddings", type=pathlib.Path,
                   default=pathlib.Path("data/embeddings"))
    p.add_argument("--out", type=pathlib.Path, default=pathlib.Path("experiments"))
    p.add_argument("--dim", type=int, default=128)
    p.add_argument("--mlp", action="store_true", help="Condicion 6")
    p.add_argument("--epocas", type=int, default=30)
    p.add_argument("--batch-size", type=int, default=2048)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--weight-decay", type=float, default=1e-4)
    p.add_argument("--tau", type=float, default=0.07)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--presupuesto-datos", type=int, default=None,
                   help="Recorta las anclas de entrenamiento a N. Para igualar\n"
                        "el material de la conjunta con el de la cabeza mas\n"
                        "pequeña y aislar el efecto del desacoplamiento")
    p.add_argument("--sufijo", default="",
                   help="Se añade al nombre del directorio de salida")
    p.add_argument("--device", default=None)
    args = p.parse_args()

    dev = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device: {dev}")
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    idx = pd.read_parquet(args.embeddings / "embeddings_index.parquet")
    V = np.load(args.embeddings / "embeddings.npy")
    splits = pd.read_parquet(args.procesados / "splits.parquet")
    long = pd.read_parquet(args.procesados / "attrs_long.parquet")
    meta = pd.read_parquet(args.procesados / "attrs_meta.parquet")

    idx = idx.merge(splits[["image_path", "split"]], on="image_path", how="left")
    if idx.split.isna().any():
        raise SystemExit("Hay embeddings sin particion asignada.")

    tren = (idx.split == "train").to_numpy()
    vald = (idx.split == "val").to_numpy()
    orden_tren = idx.loc[tren, "image_path"].tolist()
    orden_val = idx.loc[vald, "image_path"].tolist()
    # Se normaliza la ENTRADA: el protocolo trabaja en coseno, y asi la cabeza
    # no tiene que aprender a compensar diferencias de norma entre imagenes.
    X = F.normalize(torch.from_numpy(V[tren]).float(), dim=-1)
    Xv = F.normalize(torch.from_numpy(V[vald]).float(), dim=-1)
    print(f"train: {len(orden_tren):,} imagenes  |  val: {len(orden_val):,}")

    # Solo atributos SEEN: los UNSEEN no pueden formar ningun par.
    long_seen = long[long.particion == "seen"]
    long_tren = long_seen[long_seen.image_path.isin(set(orden_tren))]
    long_val = long_seen[long_seen.image_path.isin(set(orden_val))]
    meta_keep = meta[meta.keep & (meta.particion == "seen")]

    args.out.mkdir(parents=True, exist_ok=True)
    nombre = args.condicion + ("_mlp" if args.mlp else "") + args.sufijo
    dest = args.out / nombre
    dest.mkdir(exist_ok=True)

    t0 = time.time()
    resumen: dict[str, object] = {}

    if args.condicion == "conjunta":
        # Una sola cabeza sobre TODOS los atributos seen juntos.
        atributos = sorted(meta_keep.attr_name.tolist())
        A = matriz_atributos(long_tren, orden_tren, atributos)
        Av = matriz_atributos(long_val, orden_val, atributos)
        modelo, hist = entrenar_una(X, A, Xv, Av, args, dev, "conjunta")
        torch.save({"state_dict": modelo.state_dict(), "dim": args.dim,
                    "mlp": args.mlp, "atributos": atributos},
                   dest / "cabeza_conjunta.pt")
        resumen["n_atributos"] = len(atributos)
        resumen["historial"] = {"conjunta": hist}
    else:
        hists = {}
        for grupo in GRUPOS_CABEZA:
            atributos = sorted(
                meta_keep[meta_keep.attr_group == grupo].attr_name.tolist())
            if not atributos:
                print(f"  [{grupo}] sin atributos seen; se omite")
                continue
            A = matriz_atributos(long_tren, orden_tren, atributos)
            Av = matriz_atributos(long_val, orden_val, atributos)
            modelo, hist = entrenar_una(X, A, Xv, Av, args, dev, grupo)
            torch.save({"state_dict": modelo.state_dict(), "dim": args.dim,
                        "mlp": args.mlp, "atributos": atributos,
                        "grupo": grupo},
                       dest / f"cabeza_{grupo}.pt")
            hists[grupo] = hist
        resumen["historial"] = hists

    cfg = {
        "condicion": nombre,
        "dim": args.dim, "mlp": args.mlp, "epocas": args.epocas,
        "batch_size": args.batch_size, "lr": args.lr, "tau": args.tau,
        "weight_decay": args.weight_decay, "seed": args.seed,
        "presupuesto_datos": args.presupuesto_datos,
        "n_train": len(orden_tren),
        "grupos": GRUPOS_CABEZA if args.condicion == "por_atributo" else ["todos"],
        "minutos": round((time.time() - t0) / 60, 2),
        "torch": str(torch.__version__),
        "backbone": "congelado, embeddings precalculados",
    }
    with open(dest / "config.yaml", "w", encoding="utf-8") as fh:
        yaml.safe_dump(cfg, fh, allow_unicode=True, sort_keys=False)
    with open(dest / "historial.json", "w", encoding="utf-8") as fh:
        json.dump(resumen, fh, indent=2)

    print(f"\n{nombre} entrenada en {cfg['minutos']} min -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
