"""RQ3 em trajetória completa — Goiás, Coleção 11 (complemento de testes_goias_c11.py).

Para cada pixel que vira lavoura temporária (TMP) pela primeira vez no ano F (1986–2025)
depois de ter sido vegetação nativa (NAT) em algum ano antes de F:
  L = último ano NAT antes de F
  - passou por pasto entre L e F?               (definição "da última nativa à primeira lavoura")
  - teve Mosaico (21) entre L e F, sem pasto?
  - F - L = 1 (troca direta de um ano para o outro)?
Também: endpoints longos NAT(1985) -> TMP(Y), com pasto em qualquer ano entre eles.
"""
from __future__ import annotations

import argparse
import csv
import pickle
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.windows import Window

sys.path.insert(0, str(Path(__file__).resolve().parent))
import testes_goias_c11 as T  # noqa: E402

ANOS, NY = T.ANOS, T.NY


def acumula_rq3(G, A, MZ, nomes_meso, add):
    """Contas de uma janela (G: grupos por ano x pixel, A: área em ha)."""
    N = G.shape[1]
    ist = G == T.TMP
    first = np.where(ist.any(0), ist.argmax(0), -1)
    yy = np.arange(NY)[:, None]
    nat_before = (G == T.NAT) & (yy < first[None, :])
    has_nat = nat_before.any(0) & (first > 0)
    L = np.where(has_nat, NY - 1 - nat_before[::-1].argmax(0), -1)
    between = (yy > L[None, :]) & (yy < first[None, :])
    pas_b = ((G == T.PAS) & between).any(0)
    mos_b = ((G == T.MOS) & between).any(0)
    direct = has_nat & (first - L == 1)
    pb = (G == T.PAS) & between
    pas2 = (pb[1:] & pb[:-1]).any(0)  # pelo menos 2 anos seguidos de pasto entre L e F
    for y in range(1, NY):
        m = has_nat & (first == y)
        if not m.any():
            continue
        per = f"{(ANOS[y] - 1) // 5 * 5}-{(ANOS[y] - 1) // 5 * 5 + 5}"
        for key in (str(ANOS[y]), "per:" + per):
            add((key, "total"), A[m].sum())
            add((key, "pasto_entre"), A[m & pas_b].sum())
            add((key, "pasto_entre_2anos_seguidos"), A[m & pas2].sum())
            add((key, "mosaico_entre_sem_pasto"), A[m & mos_b & ~pas_b].sum())
            add((key, "direto_1_ano"), A[m & direct].sum())
        if ANOS[y] <= 2020:
            for mi in np.unique(MZ[m]):
                mm = m & (MZ == mi)
                key = "meso:" + nomes_meso.get(int(mi), "sem_meso")
                add((key, "total"), A[mm].sum())
                add((key, "pasto_entre"), A[mm & pas_b].sum())
                add((key, "pasto_entre_2anos_seguidos"), A[mm & pas2].sum())
                add((key, "mosaico_entre_sem_pasto"), A[mm & mos_b & ~pas_b].sum())
                add((key, "direto_1_ano"), A[mm & direct].sum())
    # endpoints longos NAT(1985) -> TMP(Y)
    for y in range(5, NY, 5):
        m = (G[0] == T.NAT) & (G[y] == T.TMP)
        add((f"end:1985-{ANOS[y]}", "total"), A[m].sum())
        add((f"end:1985-{ANOS[y]}", "pasto_entre"), A[m & (G[1:y] == T.PAS).any(0)].sum())
        add((f"end:1985-{ANOS[y]}", "mosaico_entre_sem_pasto"),
            A[m & (G[1:y] == T.MOS).any(0) & ~(G[1:y] == T.PAS).any(0)].sum())


def processa(args):
    caminho, geom_pkl, meso_pkl = args
    geoms = pickle.loads(geom_pkl)
    mesos = pickle.loads(meso_pkl)  # [(geom, idx, nome)]
    acc = {}

    def add(k, v):
        acc[k] = acc.get(k, 0.0) + float(v)

    with rasterio.open(caminho) as src:
        mask_all = rasterize(((g, 1) for g in geoms), out_shape=(src.height, src.width),
                             transform=src.transform, fill=0, dtype=np.uint8)
        if not mask_all.any():
            return acc
        meso_r = rasterize(((g, i) for g, i, _ in mesos), out_shape=(src.height, src.width),
                           transform=src.transform, fill=0, dtype=np.uint8)
        nomes_meso = {i: n for _, i, n in mesos}
        for top in range(0, src.height, T.JANELA):
            h = min(T.JANELA, src.height - top)
            msk = mask_all[top:top + h] > 0
            if not msk.any():
                continue
            arr = src.read(window=Window(0, top, src.width, h))
            ah = T.area_linhas(src.transform, top, h)
            A = np.broadcast_to(ah[:, None], (h, src.width))[msk].astype(np.float64)
            G = T.LUT[arr[:, msk]]
            MZ = meso_r[top:top + h][msk]
            del arr
            acumula_rq3(G, A, MZ, nomes_meso, add)
    return acc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cubo", required=True); ap.add_argument("--mestrado", required=True)
    ap.add_argument("--saida", required=True); ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    sys.path.insert(0, str(Path(a.mestrado) / "scripts"))
    import processa_cubo_idade as pc
    geom_pkl = pickle.dumps(list(pc.carregar_municipios().geometry))
    import geobr
    ms = geobr.read_meso_region(code_meso="GO", year=2020).to_crs(4326)
    meso_pkl = pickle.dumps([(g, i + 1, n) for i, (g, n) in enumerate(zip(ms.geometry, ms.name_meso))])
    tifs = sorted(Path(a.cubo).glob("*.tif"))
    t = time.time(); total = {}
    with ProcessPoolExecutor(a.workers) as ex:
        for i, acc in enumerate(ex.map(processa, [(str(f), geom_pkl, meso_pkl) for f in tifs])):
            for k, v in acc.items():
                total[k] = total.get(k, 0.0) + v
            print(f"shard {i + 1}/{len(tifs)} ({time.time() - t:.0f}s)", flush=True)
    out = Path(a.saida); out.mkdir(parents=True, exist_ok=True)
    with open(out / "rq3_trajetoria_v2.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["chave", "item", "ha"])
        for (k, it), v in sorted(total.items()):
            w.writerow([k, it, f"{v:.3f}"])
    print("fim", time.time() - t)


if __name__ == "__main__":
    main()
