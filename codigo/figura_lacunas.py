"""Figura do teste de lacunas: reentrada por duração da interrupção em cada regra e por quinquênio.

    python -I figura_lacunas.py [resultados/cerrado_lacunas.csv] [resultados/figura_lacunas.png]
"""
import csv, sys
from pathlib import Path
from collections import defaultdict
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RES = Path(__file__).resolve().parent.parent / "resultados"
ARQ = sys.argv[1] if len(sys.argv) > 1 else RES / "cerrado_lacunas.csv"
SAIDA = sys.argv[2] if len(sys.argv) > 2 else RES / "figura_lacunas.png"
D = defaultdict(float)
for r in csv.DictReader(open(ARQ, encoding="utf-8")):
    D[(r["quinquenio"], r["grupo"], r["faixa"], r["regra"], r["estado_na_regra"])] += float(r["ha"])
QS = [f"{t}-{t+5}" for t in range(1985, 2020, 5)]
FX = ["1ano", "2anos", "3-4anos", "5+anos"]
FXN = ["1 ano", "2 anos", "3–4 anos", "5 anos ou mais"]
REG = ["r0", "r1", "r2"]
REGN = ["Sem suavização", "Preenche 1 ano", "Preenche até 2 anos"]

def re(q, reg, fx):
    return sum(D[(q, g, fx, reg, e)] for g in ("observada", "lacuna") for e in ("reentrada", "reentrada_anterior"))
tot = {q: D[(q, "total_PAS_TMP", "", "", "")] for q in QS}
TOT = sum(tot.values())

INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
SEQ = ["#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]
CAT = ["#2a78d6", "#eb6834", "#1baf7a"]
plt.rcParams.update({"font.family": "Segoe UI", "font.size": 11, "text.color": INK, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.edgecolor": GRID})
fig, (a, b) = plt.subplots(1, 2, figsize=(13, 5.6), gridspec_kw={"width_ratios": [1, 1.25]}, facecolor=SURF)
for ax in (a, b):
    ax.set_facecolor(SURF)
    for s in ("top", "right"): ax.spines[s].set_visible(False)
    ax.grid(axis="y", color=GRID, lw=0.8); ax.set_axisbelow(True)

# A: reentrada por faixa em cada regra (% do total PAS->TMP, 7 quinquênios somados)
x = range(3)
base = [0, 0, 0]
for i, fx in enumerate(FX):
    v = [100 * sum(re(q, reg, fx) for q in QS) / TOT for reg in REG]
    a.bar(x, v, bottom=base, width=0.55, color=SEQ[i], edgecolor=SURF, lw=2, label=FXN[i])
    base = [p + w for p, w in zip(base, v)]
for xi, t in zip(x, base):
    a.text(xi, t + 0.15, f"{t:.2f}%".replace(".", ","), ha="center", va="bottom", fontsize=12, weight="bold")
a.set_xticks(list(x), REGN); a.set_ylim(0, 11.5)
a.set_ylabel("% de todo o pasto que virou lavoura")
a.set_title("Reentrada por duração da interrupção\nCerrado, 1985–2020 (13,6 Mha de pasto → lavoura)", loc="left", fontsize=12)
h, l = a.get_legend_handles_labels()
a.legend(h[::-1], l[::-1], title="Duração da interrupção", frameon=False, loc="upper center", ncol=2, fontsize=10, title_fontsize=10)

# B: por quinquênio
xs = list(range(len(QS)))
for reg, n, c in zip(REG, REGN, CAT):
    y = [100 * sum(re(q, reg, fx) for fx in FX) / tot[q] for q in QS]
    b.plot(xs, y, color=c, lw=2, marker="o", ms=8, mec=SURF, mew=2, label=n)
    dy = {"r0": 0.35, "r1": -0.35, "r2": 0}[reg]
    b.text(xs[-1] + 0.15, y[-1] + dy, f"{n}  {y[-1]:.1f}%".replace(".", ","), color=INK, va="center", fontsize=10)
b.set_xticks(xs, [q.replace("-", "–") for q in QS], rotation=0, fontsize=9.5)
b.set_xlim(-0.3, len(QS) + 1.6); b.set_ylim(0, 16)
b.set_ylabel("% do pasto que virou lavoura no quinquênio")
b.set_title("Reentrada em cada quinquênio\nNo início, a série ainda é curta para mostrar reentradas", loc="left", fontsize=12)
b.spines["bottom"].set_bounds(0, len(QS) - 1)
fig.text(0.01, 0.01, "MapBiomas Col. 11, 30 m. Reentrada = pasto que saiu, voltou e depois virou lavoura temporária. "
         "Interrupção com ano sem classe no mapa: ~1 ha (invisível na escala).", fontsize=9, color=INK2)
fig.tight_layout(rect=(0, 0.04, 1, 1))
fig.savefig(SAIDA, dpi=150, facecolor=SURF)
print("ok", SAIDA)
