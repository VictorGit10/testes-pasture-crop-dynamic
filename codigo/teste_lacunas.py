"""Reentrada com interrupção inteiramente observada x com lacuna, sob três regras de suavização.

Pedido do Mario (17/11/2026). Mesmo recorte (bioma Cerrado do IBGE), mesmos dados (Col. 11) e as
mesmas conversões PAS(t0) -> TMP(t0+5) dos sete quinquênios 1985-1990 .. 2015-2020 de
`testes_cerrado.py`. O motor é o mesmo (`testes_goias_c11.motor`); este script só acrescenta,
para cada entrada em pastagem, se a interrupção desde o último ano de pasto teve algum ano sem
classe válida.

Interrupção = anos entre o último ano de pastagem antes da interrupção e o primeiro ano do
episódio de pastagem em curso em t0 (sem incluir nenhum dos dois).
  observada: todos esses anos têm classe válida diferente de pastagem
  lacuna:    pelo menos um desses anos é código 0 (sem classe dentro do recorte), 27 (não
             observado) ou um código que não está em `CLASS_CODES`. No Cerrado da Col. 11, só o
             código 0 aparece (27 e códigos desconhecidos: 0 ha).
Como no motor do Mario, um ano sem classe válida logo antes da entrada já faz o episódio ser
"não resolvido" (não entra como reentrada). A lacuna aqui é, portanto, um ano sem classe válida
no meio da interrupção.

Regras (a mesma `fill_k` do motor; só preenche anos com classe válida, nunca lacunas):
  r0: sem suavização
  r1: interrupções válidas de 1 ano entre dois anos de pasto viram pasto
  r2: interrupções válidas de até 2 anos viram pasto

Saída: cerrado_lacunas.csv com (quinquenio, grupo, faixa, regra, estado_na_regra, ha), em que
grupo/faixa vêm da regra r0 e estado_na_regra é o que a mesma área vira na regra:
  reentrada           continua reentrada, com o mesmo episódio de pasto em curso em t0
  reentrada_anterior  continua reentrada, mas porque a suavização juntou o episódio a um
                      episódio anterior que também era reentrada (outra interrupção, mais antiga)
  primeira, incerto (entrada com histórico incerto), inicial (contínuo desde 1985), nao_resolvido
Linhas especiais (coluna grupo):
  total_PAS_TMP        o denominador
  composicao_r0        o total dividido pelo estado do episódio em t0 na regra r0
  nao_resolvido_com_pasto_antes   episódios que o motor deixa sem origem porque o ano logo antes
                       da entrada não tem classe, mas que tiveram pasto antes: são interrupções
                       com lacuna "na borda". faixa = duração da interrupção; estado_na_regra =
                       so_lacuna (nenhum ano com classe válida no intervalo) ou
                       lacuna_e_classe_valida
  nao_resolvido_sem_pasto_antes   idem, sem pasto antes (não é interrupção)
Nas regras r1 e r2, a lacuna nunca é preenchida: o grupo "lacuna" e as faixas de 3 anos ou mais
não mudam por construção.

    python -I teste_lacunas.py --dados <pasta tifs> --cerrado <cerrado.gpkg> --saida <pasta>
    python -I teste_lacunas.py --casos        (só os casos sintéticos)
"""
from __future__ import annotations

import argparse
import csv
import pickle
import sqlite3
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import testes_goias_c11 as T  # noqa: E402

PAS, NOD, NONE = T.PAS, T.NOD, T.NONE
FAIXAS = ((1, 1, "1ano"), (2, 2, "2anos"), (3, 4, "3-4anos"), (5, 99, "5+anos"))
ESTADOS = ("reentrada", "reentrada_anterior", "primeira", "incerto", "inicial", "nao_resolvido")


def lacuna_na_entrada(G):
    """(NY, N) bool: no ano da entrada, a interrupção desde o último PAS teve ano sem classe válida.

    Vale para qualquer ano; só é usado onde o motor marcou reentrada."""
    NY, N = G.shape
    out = np.zeros((NY, N), bool)
    desde = np.zeros(N, bool)  # houve ano sem classe válida desde o último PAS
    lac = np.zeros(N, bool)  # valor guardado no episódio em curso
    for y in range(NY):
        g = G[y]
        isp = g == PAS
        if y > 0:
            novo = isp & (G[y - 1] != PAS)
            lac = np.where(novo, desde, np.where(isp, lac, False))
        out[y] = lac
        desde = np.where(isp, False, desde | (g == NOD) | (g == NONE))
    return out


def estado(orig, kind):
    e = np.full(orig.shape, "", object)
    e[orig == 1] = "inicial"
    e[orig == 3] = "nao_resolvido"
    e[(orig == 2) & (kind == 1)] = "primeira"
    e[(orig == 2) & (kind == 2)] = "reentrada"
    e[(orig == 2) & (kind == 3)] = "incerto"
    return e


def inicio(orig, i0):
    """Primeiro ano (índice) do episódio de pasto em curso em i0."""
    ini = np.full(orig.shape[1], i0, np.int16)
    seg = orig[i0] > 0
    for y in range(i0 - 1, -1, -1):
        seg &= orig[y] > 0
        ini[seg] = y
    return ini


def acumula(G, A, add):
    o0, k0, _, gap = T.motor(G, A)
    lac = lacuna_na_entrada(G)
    regras = {0: (o0, k0), 1: T.motor(G, A, 1)[:2], 2: T.motor(G, A, 2)[:2]}
    for t0 in range(1985, 2020, 5):
        i0, i1 = T.ANOS.index(t0), T.ANOS.index(t0 + 5)
        q = f"{t0}-{t0 + 5}"
        pt = (G[i0] == PAS) & (G[i1] == T.TMP)
        add((q, "total_PAS_TMP", "", "", ""), A[pt].sum())
        if not pt.any():
            continue
        re = pt & (o0[i0] == 2) & (k0[i0] == 2)
        ini0 = inicio(o0, i0)
        # não resolvido (lacuna logo antes da entrada): fica fora da reentrada no motor
        # (só nas colunas não resolvidas, que são poucas: evita matrizes 41 x N grandes)
        cn = np.nonzero(pt & (o0[i0] == 3))[0]
        Gc = G[:, cn]
        fim = ini0[cn].astype(np.int64) - 1  # último ano da interrupção (-1 = episódio começa em 1985)
        anos = np.arange(G.shape[0])[:, None]
        antes_m = (Gc == PAS) & (anos <= fim[None, :])
        antes = antes_m.any(0)
        add((q, "nao_resolvido_sem_pasto_antes", "", "r0", ""), A[cn[~antes]].sum())
        if antes.any():
            Gc, fim, antes_m = Gc[:, antes], fim[antes], antes_m[:, antes]
            lp = np.where(antes_m, anos, -1).max(0)  # último PAS antes da interrupção
            dur = fim - lp
            valida = (Gc != PAS) & (Gc != NOD) & (Gc != NONE)
            nv = (valida & (anos > lp[None, :]) & (anos <= fim[None, :])).sum(0)
            a = A[cn[antes]]
            for lo, hi, fx in FAIXAS:
                mm = (dur >= lo) & (dur <= hi)
                add((q, "nao_resolvido_com_pasto_antes", fx, "r0", "so_lacuna"), a[mm & (nv == 0)].sum())
                add((q, "nao_resolvido_com_pasto_antes", fx, "r0", "lacuna_e_classe_valida"), a[mm & (nv > 0)].sum())
        e0 = estado(o0[i0], k0[i0])
        for nome in ESTADOS:
            if nome != "reentrada_anterior":
                add((q, "composicao_r0", "", "r0", nome), A[pt & (e0 == nome)].sum())
        est = {}
        for r, (o, k) in regras.items():
            e = estado(o[i0], k[i0])
            if r:
                e[(e == "reentrada") & (inicio(o, i0) != ini0)] = "reentrada_anterior"
            est[r] = e
        for gr, mg in (("observada", re & ~lac[i0]), ("lacuna", re & lac[i0])):
            for lo, hi, fx in FAIXAS:
                m = mg & (gap[i0] >= lo) & (gap[i0] <= hi)
                for r in regras:
                    e = est[r][m]
                    a = A[m]
                    for nome in ESTADOS:
                        add((q, gr, fx, f"r{r}", nome), a[e == nome].sum() if m.any() else 0.0)


def le_gpkg(caminho):
    """Geometrias de um GPKG pelo sqlite, sem GDAL."""
    from shapely import wkb
    con = sqlite3.connect(caminho)
    tab, = con.execute("select table_name from gpkg_contents where data_type='features'").fetchone()
    gcol, = con.execute("select column_name from gpkg_geometry_columns where table_name=?", (tab,)).fetchone()
    out = []
    for (b,) in con.execute(f"select \"{gcol}\" from '{tab}'"):
        env = (b[3] >> 1) & 7
        out.append(wkb.loads(bytes(b[8 + {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}[env]:])))
    return out


def processa(args):
    import rasterio
    from rasterio.features import rasterize
    from rasterio.windows import Window
    caminho, geom_pkl = args
    geoms = pickle.loads(geom_pkl)
    acc = {}

    def add(k, v):
        acc[k] = acc.get(k, 0.0) + float(v)

    with rasterio.open(caminho) as src:
        Z = rasterize(((g, 1) for g in geoms), out_shape=(src.height, src.width),
                      transform=src.transform, fill=0, dtype=np.uint8)
        if not Z.any():
            return acc
        for top in range(0, src.height, T.JANELA):
            h = min(T.JANELA, src.height - top)
            msk = Z[top:top + h] > 0
            if not msk.any():
                continue
            arr = src.read(window=Window(0, top, src.width, h))
            ah = T.area_linhas(src.transform, top, h)
            A = np.broadcast_to(ah[:, None], (h, src.width))[msk].astype(np.float64)
            G = T.LUT[arr[:, msk]]
            del arr
            acumula(G, A, add)
    return acc


def casos():
    P, X, N, D, M, Z = T.PAS, T.TMP, T.NAT, T.NOD, T.MOS, T.NONE
    # classes de 1985 a 1995 (completadas com pasto), pasto até 1999 e lavoura de 2000 em diante:
    # só o quinquênio 1995-2000 tem PAS -> TMP
    def pix(ini):
        s = (list(ini) + [P] * 11)[:11]
        return s + [P] * 4 + [X] * 26
    R, RA = "reentrada", "reentrada_anterior"
    C = {  # nome: (classes, grupo, faixa, estado em r0, r1, r2); grupo None = não resolvido
        "observada 2 anos": ([P, N, N], "observada", "2anos", (R, R, "inicial")),
        "observada 1 ano depois de 1 ano de pasto": ([N, P, M], "observada", "1ano", (R, "primeira", "primeira")),
        "observada 5 anos": ([P, N, N, N, N, N], "observada", "5+anos", (R, R, R)),
        "lacuna no meio": ([P, N, Z, N], "lacuna", "3-4anos", (R, R, R)),
        "lacuna no meio, 2 anos": ([P, D, N], "lacuna", "2anos", (R, R, R)),
        "1 ano junta com reentrada anterior": ([P, N, N, N, N, P, N], "observada", "1ano", (R, RA, RA)),
        "idem, a anterior com lacuna": ([P, D, N, N, N, P, N], "observada", "1ano", (R, RA, RA)),
        "1 ano junta com episódio não resolvido": ([P, D, P, N], "observada", "1ano", (R, "nao_resolvido", "nao_resolvido")),
        "1 ano junta com episódio incerto": ([D, N, P, M], "observada", "1ano", (R, "incerto", "incerto")),
        "lacuna logo antes, com pasto antes": ([P, N, N, D], "nr", ("3-4anos", "lacuna_e_classe_valida"), None),
        "só lacuna entre dois pastos": ([P, D], "nr", ("1ano", "so_lacuna"), None),
        "só lacuna, 2 anos": ([N, P, Z, D], "nr", ("2anos", "so_lacuna"), None),
        "lacuna logo antes, sem pasto antes": ([D], "nr0", ("", ""), None),
    }
    q = "1995-2000"
    ok = True
    for nome, (ini, gr, fx, esp) in C.items():
        G = np.array([pix(ini)], np.uint8).T
        acc = {}
        acumula(G, np.ones(1), lambda k, v: acc.__setitem__(k, acc.get(k, 0.0) + v))
        assert sum(v for k, v in acc.items() if k[1] == "total_PAS_TMP") == 1
        comp = sum(v for k, v in acc.items() if k[1] == "composicao_r0")
        if gr in ("nr", "nr0"):
            g2 = "nao_resolvido_com_pasto_antes" if gr == "nr" else "nao_resolvido_sem_pasto_antes"
            got = acc.get((q, g2, fx[0], "r0", fx[1]), 0) == 1 and comp == 1
            got &= acc.get((q, "composicao_r0", "", "r0", "nao_resolvido"), 0) == 1
            print("ok  " if got else "ERRO", nome, "-> não resolvido", fx); ok &= got
            continue
        ok &= acc.get((q, "composicao_r0", "", "r0", "reentrada"), 0) == 1 and comp == 1
        for r, e in enumerate(esp):
            got = acc.get((q, gr, fx, f"r{r}", e), 0) == 1
            # e nenhum outro estado na mesma regra
            got &= sum(v for k, v in acc.items() if k[:4] == (q, gr, fx, f"r{r}")) == 1
            ok &= got
            print("ok  " if got else "ERRO", nome, f"r{r}", gr, fx, e)
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dados"); ap.add_argument("--cerrado"); ap.add_argument("--saida")
    ap.add_argument("--workers", type=int, default=6); ap.add_argument("--casos", action="store_true")
    a = ap.parse_args()
    if a.casos:
        sys.exit(0 if casos() else 1)
    gpkl = pickle.dumps(le_gpkg(a.cerrado))
    tifs = sorted(Path(a.dados).glob("*.tif"))
    t = time.time(); tot = {}
    with ProcessPoolExecutor(a.workers) as ex:
        for i, acc in enumerate(ex.map(processa, [(str(f), gpkl) for f in tifs])):
            for k, v in acc.items():
                tot[k] = tot.get(k, 0.0) + v
            print(f"quadrado {i + 1}/{len(tifs)} ({time.time() - t:.0f}s)", flush=True)
    out = Path(a.saida); out.mkdir(parents=True, exist_ok=True)
    with open(out / "cerrado_lacunas.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["quinquenio", "grupo", "faixa", "regra", "estado_na_regra", "ha"])
        for k, v in sorted(tot.items()):
            w.writerow(list(k) + [f"{v:.3f}"])
    print(f"fim {time.time() - t:.0f}s")


if __name__ == "__main__":
    main()
