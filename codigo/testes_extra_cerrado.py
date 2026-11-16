"""Testes extras pedidos nas revisões do DeepSeek e do Gemini (15/11/2026), no Cerrado por UF.

Mesmo motor (`T.motor`), mesmos grupos, mesmas zonas de `testes_cerrado.py`. Acrescenta:
  E1  código 0 (NONE) por ano dentro da máscara
  E2  T5 com suavização de 1 e 2 anos (coorte 1985 em PAS em 2020 x inicial contínuo)
  E3  trajetória (última NAT -> primeira TMP) separando pixels com pasto antes da última NAT,
      NAT contínua desde 1985, e "pasto em qualquer ano antes da primeira TMP"; por UF e UF x período
  E4  T2 olhando mais que 1 ano: na entrada (episódio que vira TMP no quinquênio), a classe do ano
      anterior se repete no ano anterior a ele? Na reentrada, houve TMP / Mosaico / só NAT na interrupção?

    python -I testes_extra_cerrado.py --dados <pasta tifs> --cerrado <gpkg> --saida <pasta>
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
import testes_cerrado as C  # noqa: E402

ANOS, NY = T.ANOS, T.NY
PAS, NAT, TMP, MOS, NONE = T.PAS, T.NAT, T.TMP, T.MOS, T.NONE


def inicio_episodio(orig, i0):
    """Ano (índice) em que começou o episódio em curso em i0 (só faz sentido onde orig[i0] > 0)."""
    N = orig.shape[1]
    e = np.full(N, i0, np.int16)
    ativo = orig[i0] > 0
    for y in range(i0 - 1, -1, -1):
        cont = ativo & (orig[y] > 0)
        e[cont] = y
        ativo = cont
        if not ativo.any():
            break
    return e


def extra(G, A, add):
    yy = np.arange(NY)[:, None]
    # E1
    for y in range(NY):
        add(("E1_codigo0", ANOS[y], "ha"), A[G[y] == NONE].sum())
    # E2
    i20 = ANOS.index(2020)
    coorte = (G[0] == PAS) & (G[i20] == PAS)
    orig, kind, prev, gap = T.motor(G, A)
    for k in (0, 1, 2):
        o = orig if k == 0 else T.motor(G, A, k)[0]
        add(("E2_RQ1xRQ2", k, "coorte1985_em_PAS"), A[coorte].sum())
        add(("E2_RQ1xRQ2", k, "inicial_continuo"), A[o[i20] == 1].sum())
    # E4
    for t0 in range(1990, 2020, 5):
        i0, i1 = ANOS.index(t0), ANOS.index(t0 + 5)
        pt = (G[i0] == PAS) & (G[i1] == TMP) & (orig[i0] == 2)
        if not pt.any():
            continue
        e = inicio_episodio(orig, i0)
        idx = np.arange(G.shape[1])
        p1 = G[np.maximum(e - 1, 0), idx]
        p2 = G[np.maximum(e - 2, 0), idx]
        lab = f"{t0}-{t0 + 5}"
        for tipo, v in (("primeira", 1), ("reentrada", 2)):
            m = pt & (kind[i0] == v)
            for g, n in ((NAT, "NAT"), (TMP, "TMP"), (MOS, "MOS21")):
                mg = m & (p1 == g)
                add(("E4_antes", lab, f"{tipo}|{n}|1ano"), A[mg].sum())
                add(("E4_antes", lab, f"{tipo}|{n}|2anos_iguais"), A[mg & (p2 == g) & (e >= 2)].sum())
            add(("E4_antes", lab, f"{tipo}|total"), A[m].sum())
        # reentrada: o que houve na interrupção (entre o último PAS anterior e a entrada)
        m = pt & (kind[i0] == 2)
        if m.any():
            ult = e - 1 - gap[i0]  # último ano PAS antes da interrupção
            dentro = (yy > ult[None, :]) & (yy < e[None, :])
            tmp_g = ((G == TMP) & dentro).any(0)
            mos_g = ((G == MOS) & dentro).any(0)
            nat_g = ((G == NAT) & dentro).any(0)
            add(("E4_interrupcao", lab, "total"), A[m].sum())
            add(("E4_interrupcao", lab, "teve_TMP"), A[m & tmp_g].sum())
            add(("E4_interrupcao", lab, "Mosaico_sem_TMP"), A[m & mos_g & ~tmp_g].sum())
            add(("E4_interrupcao", lab, "so_NAT_sem_TMP_nem_Mosaico"), A[m & nat_g & ~tmp_g & ~mos_g].sum())
    # E3
    ist = G == TMP
    first = np.where(ist.any(0), ist.argmax(0), -1)
    nat_before = (G == NAT) & (yy < first[None, :])
    has_nat = nat_before.any(0) & (first > 0)
    L = np.where(has_nat, NY - 1 - nat_before[::-1].argmax(0), -1)
    between = (yy > L[None, :]) & (yy < first[None, :])
    pas_b = ((G == PAS) & between).any(0)
    pas_antes_L = ((G == PAS) & (yy < L[None, :])).any(0)
    nat_cont = ((G == NAT) | (yy > L[None, :])).all(0)  # NAT em todos os anos de 1985 até L
    pas_algum = ((G == PAS) & (yy < first[None, :])).any(0)
    return first, has_nat, pas_b, pas_antes_L, nat_cont, pas_algum


def processa(args):
    caminho, zonas_pkl = args
    zonas = pickle.loads(zonas_pkl)
    nomes = {c: s for _, c, s in zonas}
    acc = {}
    with rasterio.open(caminho) as src:
        Z = rasterize(((g, c) for g, c, _ in zonas), out_shape=(src.height, src.width),
                      transform=src.transform, fill=0, dtype=np.uint8)
        if not Z.any():
            return acc
        for top in range(0, src.height, T.JANELA):
            h = min(T.JANELA, src.height - top)
            zw = Z[top:top + h]
            msk = zw > 0
            if not msk.any():
                continue
            arr = src.read(window=Window(0, top, src.width, h))
            ah = T.area_linhas(src.transform, top, h)
            A = np.broadcast_to(ah[:, None], (h, src.width))[msk].astype(np.float64)
            G = T.LUT[arr[:, msk]]
            MZ = zw[msk]
            del arr
            for c in np.unique(MZ):
                sel = MZ == c
                uf = nomes[int(c)]

                def add(key, v, uf=uf):
                    k = (uf,) + key
                    acc[k] = acc.get(k, 0.0) + float(v)
                Gs, As = G[:, sel], A[sel]
                first, has_nat, pas_b, pas_antes_L, nat_cont, pas_algum = extra(Gs, As, add)
                for y in range(1, NY):
                    m = has_nat & (first == y)
                    if not m.any() or ANOS[y] > 2020:
                        continue
                    per = f"{(ANOS[y] - 1) // 5 * 5}-{(ANOS[y] - 1) // 5 * 5 + 5}"
                    for chave in ("1986-2020", per):
                        add(("E3", chave, "total"), As[m].sum())
                        add(("E3", chave, "pasto_entre"), As[m & pas_b].sum())
                        add(("E3", chave, "pasto_antes_da_ultima_NAT"), As[m & pas_antes_L].sum())
                        add(("E3", chave, "sem_pasto_antes|total"), As[m & ~pas_antes_L].sum())
                        add(("E3", chave, "sem_pasto_antes|pasto_entre"), As[m & ~pas_antes_L & pas_b].sum())
                        add(("E3", chave, "nat_continua|total"), As[m & nat_cont].sum())
                        add(("E3", chave, "nat_continua|pasto_entre"), As[m & nat_cont & pas_b].sum())
                        add(("E3", chave, "pasto_em_algum_ano_antes_da_TMP"), As[m & pas_algum].sum())
    return acc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dados", required=True); ap.add_argument("--cerrado", required=True)
    ap.add_argument("--saida", required=True); ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    zpkl = pickle.dumps(C.zonas(a.cerrado))
    tifs = sorted(Path(a.dados).glob("*.tif"))
    t = time.time(); tot = {}
    with ProcessPoolExecutor(a.workers) as ex:
        for i, acc in enumerate(ex.map(processa, [(str(f), zpkl) for f in tifs])):
            for k, v in acc.items():
                tot[k] = tot.get(k, 0.0) + v
            print(f"quadrado {i + 1}/{len(tifs)} ({time.time() - t:.0f}s)", flush=True)
    out = Path(a.saida); out.mkdir(parents=True, exist_ok=True)
    with open(out / "cerrado_extra.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["uf", "tabela", "chave", "item", "ha"])
        for k, v in sorted(tot.items(), key=lambda x: tuple(map(str, x[0]))):
            w.writerow(list(k) + [f"{v:.3f}"])
    print(f"fim {time.time() - t:.0f}s")


if __name__ == "__main__":
    main()
