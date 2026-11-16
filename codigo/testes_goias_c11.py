"""Testes dos pontos levantados sobre o trabalho do Mario Barroso — Goiás, Coleção 11.

Só leitura do cubo local da dissertação (data/raw/cubo_go_col11, 41 bandas 1985–2025, 30 m).
Grupos de classe e regras de episódio copiados do repositório do Mario:
  - config/constants.js (CLASS_CODES)
  - docs/decisions/024_reconstruction_of_observed_pasture_spell_age.md
  - docs/methods/entry_reentry_auxiliary_decomposition_v1.md

Saída: testes/saida/*.csv e resumo.json. Uso:
  python -I testes_goias_c11.py --cubo <pasta> --mestrado <pasta Mestrado> --saida <pasta>
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.windows import Window

ANOS = list(range(1985, 2026))
NY = len(ANOS)
T0S = list(range(1985, 2021, 5))  # 1985..2020 (o último é diagnóstico 2020–2025)

# códigos de grupo
NONE, NAT, PAS, TMP, MOS, SIL, PER, OUT, WAT, NOD = range(10)
NOMES = ["fora", "NAT", "PAS", "TMP", "MOS21", "SILV9", "PEREN", "OUT", "AGUA", "NODATA27"]
GR = {
    NAT: [1, 3, 4, 5, 6, 7, 10, 11, 12, 13, 29, 32, 49, 50, 84],
    PAS: [15], TMP: [19, 20, 39, 40, 41, 62], MOS: [21], SIL: [9],
    PER: [35, 36, 46, 47, 48], OUT: [22, 23, 24, 25, 30, 75, 91],
    WAT: [26, 31, 33], NOD: [27],
}
LUT = np.full(256, NOD, np.uint8)  # código inesperado = perda de observação (como o Mario)
LUT[0] = NONE
for g, cs in GR.items():
    LUT[cs] = g

R = 6371007.2  # raio autálico
JANELA = 1024


def area_linhas(transform, top, h):
    lat_top = transform.f + transform.e * top
    edges = lat_top + transform.e * np.arange(h + 1)
    s = np.sin(np.radians(edges))
    dlon = np.radians(transform.a)
    return (R * R * dlon * np.abs(s[:-1] - s[1:])) / 1e4  # ha


def motor(G, A, fill_k=0):
    """Reconstrução do episódio (Decisão 024 + decomposição de entrada).

    G: (NY, N) grupos. fill_k>0: interrupções não-PAS confiantes de até k anos entre dois
    PAS são tratadas como PAS (teste de alternância). Devolve, por ano, estado do episódio:
      orig: 0 não-PAS, 1 inicial contínuo desde 1985, 2 entrada confirmada, 3 não resolvido
      kind: 1 primeira entrada, 2 reentrada, 3 histórico anterior incerto
      prev: grupo do ano anterior à entrada (classe que antecedeu a pastagem)
      gap:  anos de interrupção desde o último PAS antes da entrada (só reentrada)
    """
    G = G.copy()
    if fill_k:
        isp = G == PAS
        conf = (G != PAS) & (G != NOD) & (G != NONE)
        for k in range(1, fill_k + 1):
            for y in range(1, NY - k):
                m = isp[y - 1] & isp[y + k]
                for j in range(k):
                    m &= conf[y + j]
                for j in range(k):
                    G[y + j][m] = PAS
            isp = G == PAS
            conf = (G != PAS) & (G != NOD) & (G != NONE)
    N = G.shape[1]
    orig = np.zeros((NY, N), np.uint8)
    kind = np.zeros((NY, N), np.uint8)
    prev = np.zeros((NY, N), np.uint8)
    gap = np.zeros((NY, N), np.int16)
    ever_pas = np.zeros(N, bool)
    ever_gap = np.zeros(N, bool)
    last_pas = np.full(N, -1, np.int16)
    o = np.zeros(N, np.uint8); k = np.zeros(N, np.uint8); p = np.zeros(N, np.uint8); gp = np.zeros(N, np.int16)
    for y in range(NY):
        g = G[y]
        isp = g == PAS
        if y == 0:
            o = np.where(isp, 1, 0).astype(np.uint8)
        else:
            gprev = G[y - 1]
            cont = isp & (o > 0)  # continua o mesmo episódio
            new = isp & (o == 0)
            conf_prev = (gprev != PAS) & (gprev != NOD) & (gprev != NONE)
            ent = new & conf_prev
            unr = new & ~conf_prev
            o2 = np.zeros(N, np.uint8)
            o2[cont] = o[cont]
            o2[ent] = 2
            o2[unr] = 3
            k2 = np.zeros(N, np.uint8); p2 = np.zeros(N, np.uint8); g2 = np.zeros(N, np.int16)
            k2[cont] = k[cont]; p2[cont] = p[cont]; g2[cont] = gp[cont]
            kk = np.where(ever_pas, 2, np.where(ever_gap, 3, 1)).astype(np.uint8)
            k2[ent] = kk[ent]
            p2[ent] = gprev[ent]
            g2[ent & ever_pas] = (y - 1 - last_pas[ent & ever_pas]).astype(np.int16)
            o, k, p, gp = o2, k2, p2, g2
        ever_gap |= (g == NOD) | (g == NONE)  # máscara/0 também é perda de observação (revisão 14/11)
        ever_pas |= isp
        last_pas = np.where(isp, y, last_pas).astype(np.int16)
        orig[y], kind[y], prev[y], gap[y] = o, k, p, gp
    return orig, kind, prev, gap


def acumula(G, A, add):
    """Contas de uma janela (G: grupos por ano x pixel, A: área em ha)."""
    for y in range(NY):
        add(("estoque", ANOS[y], NOMES[0]), 0)
        for g in range(1, 10):
            add(("estoque", ANOS[y], NOMES[g]), A[G[y] == g].sum())
    # anual: transições y-1 -> y
    for y in range(1, NY):
        a, b = G[y - 1], G[y]
        for dest in (TMP, MOS, SIL, PER, NAT):
            add(("anual_PAS_para", ANOS[y], NOMES[dest]), A[(a == PAS) & (b == dest)].sum())
        if 1 <= y < NY - 1:
            c = G[y + 1]
            m1 = (a == PAS) & (b != PAS) & (b != NOD) & (b != NONE) & (c == PAS)
            add(("interrupcao_1ano_PAS", ANOS[y], "total"), A[m1].sum())
            for dest in (TMP, MOS, NAT):
                add(("interrupcao_1ano_PAS", ANOS[y], NOMES[dest]), A[m1 & (b == dest)].sum())
    orig, kind, prev, gap = motor(G, A)
    origK = {kk: motor(G, A, kk)[:2] for kk in (1, 2)}
    for t0 in T0S:
        i0, i1 = ANOS.index(t0), ANOS.index(t0 + 5)
        lab = f"{t0}-{t0 + 5}"
        pt = (G[i0] == PAS) & (G[i1] == TMP)
        add(("PAS_TMP", lab, "total"), A[pt].sum())
        for v, n in ((1, "inicial"), (2, "entrada"), (3, "nao_resolvido")):
            add(("PAS_TMP", lab, n), A[pt & (orig[i0] == v)].sum())
        for v, n in ((1, "primeira"), (2, "reentrada"), (3, "incerto")):
            me = pt & (orig[i0] == 2) & (kind[i0] == v)
            add(("PAS_TMP_entrada", lab, n), A[me].sum())
            for g in range(1, 10):
                add(("PAS_TMP_classe_antes", lab, f"{n}|{NOMES[g]}"), A[me & (prev[i0] == g)].sum())
        # reentrada vinda da coorte de 1985 (era PAS em 1985) x de episódio pós-1985
        mr = pt & (orig[i0] == 2) & (kind[i0] == 2)
        add(("PAS_TMP_reentrada_por", lab, "coorte1985"), A[mr & (G[0] == PAS)].sum())
        add(("PAS_TMP_reentrada_por", lab, "pos1985"), A[mr & (G[0] != PAS)].sum())
        for lim, n in ((1, "1ano"), (2, "2anos"), (4, "3-4anos"), (99, "5+anos")):
            lo = {1: 1, 2: 2, 4: 3, 99: 5}[lim]
            add(("PAS_TMP_reentrada_intervalo", lab, n), A[mr & (gap[i0] >= lo) & (gap[i0] <= lim)].sum())
        for kk, (ok, kd) in origK.items():
            for v, n in ((1, "inicial"), (2, "entrada"), (3, "nao_resolvido")):
                add((f"PAS_TMP_suav{kk}", lab, n), A[pt & (ok[i0] == v)].sum())
            add((f"PAS_TMP_suav{kk}", lab, "reentrada"), A[pt & (ok[i0] == 2) & (kd[i0] == 2)].sum())
        # definição ampla de lavoura (como na dissertação): TMP + silvicultura + perenes
        for dest in (MOS, SIL, PER):
            add(("PAS_para", lab, NOMES[dest]), A[(G[i0] == PAS) & (G[i1] == dest)].sum())
        # RQ3: NAT(t0) -> TMP(t1)
        nt = (G[i0] == NAT) & (G[i1] == TMP)
        mid = G[i0 + 1:i1]
        pas_mid = (mid == PAS).any(0)
        mos_mid = (mid == MOS).any(0)
        oag_mid = np.isin(mid, (MOS, SIL, PER)).any(0)
        pas_ever = (G[:i1] == PAS).any(0)
        pas_before = (G[:i0] == PAS).any(0)
        add(("NAT_TMP", lab, "total"), A[nt].sum())
        add(("NAT_TMP", lab, "pasto_no_quinquenio"), A[nt & pas_mid].sum())
        add(("NAT_TMP", lab, "pasto_antes_de_t0"), A[nt & pas_before].sum())
        add(("NAT_TMP", lab, "pasto_em_qualquer_ano_ate_t1"), A[nt & pas_ever].sum())
        add(("NAT_TMP", lab, "mosaico_no_quinquenio_sem_pasto"), A[nt & mos_mid & ~pas_mid].sum())
        add(("NAT_TMP", lab, "outro_agro_no_quinquenio_sem_pasto"), A[nt & oag_mid & ~pas_mid].sum())
        # NAT ininterrupta desde 1985 até t0 e lavoura em t1 (primeira abertura observada)
        nat_cont = (G[:i0 + 1] == NAT).all(0)
        add(("NAT_TMP", lab, "nat_continua_desde_1985"), A[nt & nat_cont].sum())
        add(("NAT_TMP", lab, "nat_continua_desde_1985_pasto_no_quinquenio"), A[nt & nat_cont & pas_mid].sum())
    # RQ1 x RQ2: coorte fixa de 1985 em PAS em 2020 x inicial contínuo em 2020
    i20 = ANOS.index(2020)
    add(("RQ1xRQ2", 2020, "coorte1985_em_PAS"), A[(G[0] == PAS) & (G[i20] == PAS)].sum())
    add(("RQ1xRQ2", 2020, "inicial_continuo"), A[orig[i20] == 1].sum())
    add(("RQ1xRQ2", 2020, "coorte1985_reentrada"), A[(G[0] == PAS) & (orig[i20] == 2)].sum())
    add(("RQ1xRQ2", 2020, "coorte1985_nao_resolvido"), A[(G[0] == PAS) & (orig[i20] == 3)].sum())
    # entradas por ano (para ver 2003/2004)
    for y in range(1, NY):
        e = (orig[y] == 2) & (orig[y - 1] == 0)
        add(("entradas_ano", ANOS[y], "primeira"), A[e & (kind[y] == 1)].sum())
        add(("entradas_ano", ANOS[y], "reentrada"), A[e & (kind[y] == 2)].sum())


def processa(args):
    caminho, geom_pkl = args
    geoms = pickle.loads(geom_pkl)
    acc = {}

    def add(key, v):
        acc[key] = acc.get(key, 0.0) + float(v)

    with rasterio.open(caminho) as src:
        mask_all = rasterize(((g, 1) for g in geoms), out_shape=(src.height, src.width),
                             transform=src.transform, fill=0, dtype=np.uint8)
        if not mask_all.any():
            return acc
        for top in range(0, src.height, JANELA):
            h = min(JANELA, src.height - top)
            msk = mask_all[top:top + h] > 0
            if not msk.any():
                continue
            arr = src.read(window=Window(0, top, src.width, h))  # (41, h, w)
            ah = area_linhas(src.transform, top, h)
            A = np.broadcast_to(ah[:, None], (h, src.width))[msk].astype(np.float64)
            G = LUT[arr[:, msk]]  # (41, N)
            del arr
            acumula(G, A, add)
    return acc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cubo", required=True)
    ap.add_argument("--mestrado", required=True)
    ap.add_argument("--saida", required=True)
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    sys.path.insert(0, str(Path(a.mestrado) / "scripts"))
    import processa_cubo_idade as pc  # malha municipal do IBGE (geobr), como na dissertação
    gdf = pc.carregar_municipios()
    geom_pkl = pickle.dumps(list(gdf.geometry))
    tifs = sorted(Path(a.cubo).glob("*.tif"))
    t = time.time()
    total = {}
    with ProcessPoolExecutor(a.workers) as ex:
        for i, acc in enumerate(ex.map(processa, [(str(f), geom_pkl) for f in tifs])):
            for k, v in acc.items():
                total[k] = total.get(k, 0.0) + v
            print(f"shard {i + 1}/{len(tifs)} ok ({time.time() - t:.0f}s)", flush=True)
    out = Path(a.saida); out.mkdir(parents=True, exist_ok=True)
    import csv
    with open(out / "acumulados.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["tabela", "chave", "item", "ha"])
        for (tb, ch, it), v in sorted(total.items(), key=lambda x: (x[0][0], str(x[0][1]), x[0][2])):
            w.writerow([tb, ch, it, f"{v:.3f}"])
    print("fim", time.time() - t)


if __name__ == "__main__":
    main()
