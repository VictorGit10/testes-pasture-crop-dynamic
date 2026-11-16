"""Os mesmos testes de Goiás (testes_goias_c11.py + rq3_trajetoria.py), no Cerrado inteiro.

Dados: quadrados da Col. 11 exportados em 14/11/2026 (dados-mapbiomas/cerrado_col11, 41 bandas).
Recorte: bioma Cerrado do IBGE (geobr 2019), dividido por UF (geobr 2020).
As contas por pixel são as funções `acumula` e `acumula_rq3`, sem nenhuma mudança de regra.

    python -I testes_cerrado.py --dados <pasta tifs> --cerrado <gpkg> --saida <pasta>
Saída: cerrado_acumulados.csv (uf, tabela, chave, item, ha) e cerrado_rq3.csv (chave, item, ha).
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
import rq3_trajetoria as R  # noqa: E402


def processa(args):
    caminho, zonas_pkl = args
    zonas = pickle.loads(zonas_pkl)  # [(geom, codigo, sigla)], codigo 1..k; 255 = Cerrado sem UF
    nomes = {c: s for _, c, s in zonas}
    acc_main, acc_rq3 = {}, {}

    def add_rq3(k, v):
        acc_rq3[k] = acc_rq3.get(k, 0.0) + float(v)

    with rasterio.open(caminho) as src:
        Z = rasterize(((g, c) for g, c, _ in zonas), out_shape=(src.height, src.width),
                      transform=src.transform, fill=0, dtype=np.uint8)
        if not Z.any():
            return acc_main, acc_rq3, 0
        npx = 0
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
            npx += G.shape[1]
            for c in np.unique(MZ):
                sel = MZ == c
                uf = nomes[int(c)]

                def add(key, v, uf=uf):
                    k = (uf,) + key
                    acc_main[k] = acc_main.get(k, 0.0) + float(v)
                T.acumula(G[:, sel], A[sel], add)
            R.acumula_rq3(G, A, MZ, nomes, add_rq3)
    return acc_main, acc_rq3, npx


def zonas(cerrado_gpkg):
    import geobr
    import geopandas as gpd
    cer = gpd.read_file(cerrado_gpkg).to_crs(4326).geometry.union_all()
    ufs = geobr.read_state(year=2020).to_crs(4326)
    out, cod = [], 1
    resto = cer
    for sig, g in sorted(zip(ufs.abbrev_state, ufs.geometry)):
        inter = g.intersection(cer)
        if inter.is_empty or inter.area < 1e-6:
            continue
        out.append((inter, cod, sig)); cod += 1
        resto = resto.difference(g)
    if not resto.is_empty and resto.area > 0:
        out.append((resto, 255, "sem_UF"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dados", required=True); ap.add_argument("--cerrado", required=True)
    ap.add_argument("--saida", required=True); ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    zs = zonas(a.cerrado)
    print("zonas:", [(s, round(g.area, 2)) for g, _, s in zs], flush=True)
    zpkl = pickle.dumps(zs)
    tifs = sorted(Path(a.dados).glob("*.tif"))
    t = time.time(); tm, tr, npx = {}, {}, 0
    with ProcessPoolExecutor(a.workers) as ex:
        for i, (am, ar, n) in enumerate(ex.map(processa, [(str(f), zpkl) for f in tifs])):
            for k, v in am.items():
                tm[k] = tm.get(k, 0.0) + v
            for k, v in ar.items():
                tr[k] = tr.get(k, 0.0) + v
            npx += n
            print(f"quadrado {i + 1}/{len(tifs)} ({time.time() - t:.0f}s)", flush=True)
    out = Path(a.saida); out.mkdir(parents=True, exist_ok=True)
    with open(out / "cerrado_acumulados.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["uf", "tabela", "chave", "item", "ha"])
        for k, v in sorted(tm.items(), key=lambda x: tuple(map(str, x[0]))):
            w.writerow(list(k) + [f"{v:.3f}"])
    with open(out / "cerrado_rq3.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["chave", "item", "ha"])
        for (k, it), v in sorted(tr.items()):
            w.writerow([k, it, f"{v:.3f}"])
    print(f"pixels: {npx}  fim {time.time() - t:.0f}s")


if __name__ == "__main__":
    main()
