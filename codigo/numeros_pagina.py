"""Refaz, a partir das tabelas em resultados/, cada número que aparece na página (docs/index.html).

    python -I numeros_pagina.py
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
RES = Path(__file__).resolve().parent.parent / "resultados"
GRUPOS = [("GO, MG e MS", {"GO", "MG", "MS"}), ("TO", {"TO"}), ("MT", {"MT"}),
          ("BA, MA e PI", {"BA", "MA", "PI"}), ("Cerrado", None)]
QUINQ = [f"{t}-{t + 5}" for t in range(1985, 2020, 5)]  # 1985-1990 .. 2015-2020


def le(nome):
    D = defaultdict(float)
    with open(RES / nome, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            D[tuple(v for k, v in r.items() if k != "ha")] += float(r["ha"])
    return D


def pct(a, b):
    return f"{100 * a / b:.1f}%"


A, E, R = le("cerrado_acumulados.csv"), le("cerrado_extra.csv"), le("cerrado_rq3.csv")


def soma(D, tabela, item, ufs=None, chaves=None):
    return sum(v for (u, tb, ch, it), v in D.items()
               if tb == tabela and it == item and (ufs is None or u in ufs) and (chaves is None or ch in chaves))


print("== Ponto 1: lavoura nova sobre vegetação nativa (1986-2020), cada pixel uma vez")
ufs_rq3 = sorted({k[5:] for k, _ in R if k.startswith("meso:")})
for nome, ufs in GRUPOS + [("-- por estado", "")] + [(u, {u}) for u in ufs_rq3]:
    if ufs == "":
        print("  -- por estado (com mais de 100 mil ha)"); continue
    ks = [f"meso:{u}" for u in (ufs or ufs_rq3)]
    t = sum(R[(k, "total")] for k in ks)
    if t < 1e5 and nome not in dict(GRUPOS):
        continue
    p, m, d = (sum(R[(k, i)] for k in ks) for i in ("pasto_entre", "mosaico_entre_sem_pasto", "direto_1_ano"))
    print(f"  {nome:12s} {t / 1e6:5.2f} Mha  teve pasto {pct(p, t)} ({p / 1e6:.1f} Mha)  "
          f"Mosaico sem pasto {pct(m, t)}  direto {pct(d, t)}  outros {pct(t - p - m - d, t)}")
nt = soma(A, "NAT_TMP", "total", chaves=QUINQ)
print(f"  fluxo de 5 anos vegetação -> lavoura (RQ3, 1985-2020): {nt / 1e6:.3f} Mha, "
      f"com pasto nos anos do meio {pct(soma(A, 'NAT_TMP', 'pasto_no_quinquenio', chaves=QUINQ), nt)}")

print("\n== Ponto 2: reentradas que viraram lavoura (1990-2020), o que houve fora do pasto")
for nome, ufs in GRUPOS:
    t = soma(E, "E4_interrupcao", "total", ufs)
    vals = [pct(soma(E, "E4_interrupcao", i, ufs), t)
            for i in ("teve_TMP", "Mosaico_sem_TMP", "so_NAT_sem_TMP_nem_Mosaico")]
    print(f"  {nome:12s} lavoura {vals[0]}  Mosaico sem lavoura {vals[1]}  só vegetação nativa {vals[2]}")

print("\n== Ponto 3: reentradas que viraram lavoura, pasto de 1985 x pasto novo")
for nome, ufs in GRUPOS:
    c, p = (soma(A, "PAS_TMP_reentrada_por", i, ufs, QUINQ) for i in ("coorte1985", "pos1985"))
    print(f"  {nome:12s} pasto de 1985 {pct(c, c + p)}")
p85 = {u: v for (u, tb, ch, it), v in A.items() if tb == "estoque" and ch == "1985" and it == "PAS"}
print(f"  GO, MG e MS tinham {pct(sum(p85.get(u, 0) for u in ('GO', 'MG', 'MS')), sum(p85.values()))} "
      f"do pasto do Cerrado em 1985")
a, b = soma(A, "RQ1xRQ2", "coorte1985_em_PAS"), soma(A, "RQ1xRQ2", "inicial_continuo")
print(f"  RQ1 (pasto em 1985 e em 2020) {a / 1e6:.2f} Mha; RQ2 (contínuo) {b / 1e6:.2f} Mha; "
      f"diferença {(a - b) / 1e6:.2f} Mha = {pct(a - b, a)}")

print("\n== Ponto 4: pastagem -> lavoura e pastagem -> Mosaico, de um ano para o seguinte (mil ha)")
serie = {y: (soma(A, "anual_PAS_para", "TMP", chaves={str(y)}) / 1e3,
             soma(A, "anual_PAS_para", "MOS21", chaves={str(y)}) / 1e3) for y in range(1990, 2026)}
print("  " + "  ".join(f"{y}: {l:.0f}/{m:.0f}" for y, (l, m) in serie.items()))
for rot, anos in (("2016-2020", range(2016, 2021)), ("2021-2024", range(2021, 2025)), ("2025", [2025])):
    l = sum(serie[y][0] for y in anos) / len(anos); m = sum(serie[y][1] for y in anos) / len(anos)
    print(f"  média {rot}: lavoura {l:.0f}, Mosaico {m:.0f}")

print("\n== Ponto 5: duração da saída do pasto e reentrada sem as saídas curtas")
gi = {n: soma(A, "PAS_TMP_reentrada_intervalo", n, chaves=QUINQ) for n in ("1ano", "2anos", "3-4anos", "5+anos")}
print("  " + "  ".join(f"{n}: {pct(v, sum(gi.values()))}" for n, v in gi.items()))
tot = soma(A, "PAS_TMP", "total", chaves=QUINQ)
for rot, tb in (("regra atual", "PAS_TMP_entrada"), ("sem saídas de 1 ano", "PAS_TMP_suav1"),
                ("sem saídas de até 2 anos", "PAS_TMP_suav2")):
    print(f"  {rot:25s} reentrada / toda a conversão pasto -> lavoura: {pct(soma(A, tb, 'reentrada', chaves=QUINQ), tot)}")
