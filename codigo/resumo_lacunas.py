"""Tabela do teste de lacunas (Cerrado inteiro, sete quinquênios 1985-2020 somados).

    python -I resumo_lacunas.py [resultados/cerrado_lacunas.csv]

Três grupos de interrupção (o tempo fora do pasto antes do episódio em curso em t0):
  observada       todos os anos têm classe válida diferente de pasto      -> o motor conta reentrada
  lacuna_no_meio  algum ano sem classe, mas o ano logo antes da volta tem classe -> reentrada
  lacuna_na_borda o ano logo antes da volta ao pasto não tem classe        -> o motor NÃO conta
                  reentrada (episódio "não resolvido"); entra aqui só para mostrar o tamanho
Para cada grupo e faixa de duração (regra r0): área em ha e em % do total original de PAS -> TMP,
quanto continua reentrada em r1 e r2 (ha, % do total e % da própria linha) e quanto disso vem de
uma reentrada anterior (a suavização juntou o episódio a outro mais antigo, também reentrada).

Grava resumo_lacunas.csv (a tabela), resumo_lacunas_composicao.csv (o total por estado em r0)
e resumo_lacunas_quinquenios.csv (a reentrada em cada quinquênio).
Para com erro se as somas não fecharem.
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ARQ = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "resultados" / "cerrado_lacunas.csv"
QUINQ = {f"{t}-{t + 5}" for t in range(1985, 2020, 5)}
FAIXAS = ("1ano", "2anos", "3-4anos", "5+anos")

D = defaultdict(float)
vistos = set()
with open(ARQ, encoding="utf-8") as f:
    for r in csv.DictReader(f):
        if r["quinquenio"] not in QUINQ:
            continue
        k = (r["quinquenio"], r["grupo"], r["faixa"], r["regra"], r["estado_na_regra"])
        if k in vistos:
            sys.exit(f"linha repetida no CSV: {k}")
        vistos.add(k)
        D[k[1:]] += float(r["ha"])
if {q for q, *_ in vistos} != QUINQ:
    sys.exit(f"faltam quinquênios no CSV: {sorted(QUINQ - {q for q, *_ in vistos})}")

TOT = D[("total_PAS_TMP", "", "", "")]
COMP = {e: D[("composicao_r0", "", "r0", e)] for e in ("inicial", "primeira", "reentrada", "incerto", "nao_resolvido")}


def reent(gr, fx, regra, estados=("reentrada", "reentrada_anterior")):
    return sum(D[(gr, x, regra, e)] for x in (FAIXAS if fx is None else (fx,)) for e in estados)


def borda(fx):
    return sum(D[("nao_resolvido_com_pasto_antes", x, "r0", t)] for x in (FAIXAS if fx is None else (fx,))
               for t in ("so_lacuna", "lacuna_e_classe_valida"))


linhas = []
for gr, nome in (("observada", "observada"), ("lacuna", "lacuna_no_meio"), ("borda", "lacuna_na_borda"), (None, "reentrada (motor)")):
    for fx in FAIXAS + (None,):
        if gr == "borda":
            a0 = borda(fx); a1 = a2 = an1 = an2 = float("nan")  # não se aplica: não é reentrada
        else:
            grs = ("observada", "lacuna") if gr is None else (gr,)
            a0 = sum(reent(g, fx, "r0", ("reentrada",)) for g in grs)
            a1 = sum(reent(g, fx, "r1") for g in grs); an1 = sum(reent(g, fx, "r1", ("reentrada_anterior",)) for g in grs)
            a2 = sum(reent(g, fx, "r2") for g in grs); an2 = sum(reent(g, fx, "r2", ("reentrada_anterior",)) for g in grs)
        linhas.append(dict(grupo=nome, faixa=fx or "todas", r0=a0, r1=a1, r2=a2, r1_ant=an1, r2_ant=an2))

# fechamentos
tot_motor = next(L for L in linhas if L["grupo"] == "reentrada (motor)" and L["faixa"] == "todas")
erros = []
if abs(sum(COMP.values()) - TOT) > 1e-6 * TOT:
    erros.append(f"composição {sum(COMP.values()):.1f} != total {TOT:.1f}")
if abs(tot_motor["r0"] - COMP["reentrada"]) > 1e-6 * TOT:
    erros.append(f"reentrada da tabela {tot_motor['r0']:.1f} != composição {COMP['reentrada']:.1f}")
nr_total = sum(D[("nao_resolvido_com_pasto_antes", x, "r0", t)] for x in FAIXAS
               for t in ("so_lacuna", "lacuna_e_classe_valida")) + D[("nao_resolvido_sem_pasto_antes", "", "r0", "")]
if abs(nr_total - COMP["nao_resolvido"]) > 1e-6 * TOT:
    erros.append(f"não resolvido por faixa {nr_total:.1f} != composição {COMP['nao_resolvido']:.1f}")
if erros:
    sys.exit("as somas não fecham: " + "; ".join(erros))


def pct(v, b):
    return 100 * v / b if b else float("nan")


def h(v, w=11):
    """ha com casas decimais só quando o valor é pequeno, para as linhas de lacuna fecharem na tela."""
    if v != v:
        return f"{'nan':>{w}s}"
    return f"{v:{w},.0f}" if abs(v) >= 100 or v == 0 else f"{v:{w},.2f}"


print(f"Total original PAS -> TMP (denominador): {TOT:,.0f} ha")
print(f"{'grupo':18s} {'faixa':8s} {'r0 ha':>11s} {'r0 %':>6s} {'r1 ha':>11s} {'r1 %':>6s} {'r1/r0':>6s}"
      f" {'r2 ha':>11s} {'r2 %':>6s} {'r2/r0':>6s} {'r1 de anterior':>14s} {'r2 de anterior':>14s}")
for L in linhas:
    print(f"{L['grupo']:18s} {L['faixa']:8s} {h(L['r0'])} {pct(L['r0'], TOT):6.2f} {h(L['r1'])} {pct(L['r1'], TOT):6.2f}"
          f" {pct(L['r1'], L['r0']):6.1f} {h(L['r2'])} {pct(L['r2'], TOT):6.2f} {pct(L['r2'], L['r0']):6.1f}"
          f" {h(L['r1_ant'], 14)} {h(L['r2_ant'], 14)}")
print("\nlacuna_na_borda: o motor já não conta como reentrada (r0 = área; r1 e r2 não se aplicam).")
print("Divisão da lacuna na borda: só lacuna no intervalo x lacuna e classe válida:")
for fx in FAIXAS:
    print(f"  {fx:8s} {h(D[('nao_resolvido_com_pasto_antes', fx, 'r0', 'so_lacuna')], 12)}"
          f" {h(D[('nao_resolvido_com_pasto_antes', fx, 'r0', 'lacuna_e_classe_valida')], 12)}")
print("\nComposição do total original em r0:")
for e, v in COMP.items():
    print(f"  {e:14s} {v:14,.0f} ha {pct(v, TOT):6.2f}%")
print(f"  (não resolvido sem pasto antes: {D[('nao_resolvido_sem_pasto_antes', '', 'r0', '')]:,.0f} ha)")
print("\nDestino da reentrada original em cada regra (ha):")
for r in ("r1", "r2"):
    print(" ", r, {e: round(sum(reent(g, None, r, (e,)) for g in ("observada", "lacuna")))
                   for e in ("reentrada", "reentrada_anterior", "primeira", "incerto", "inicial", "nao_resolvido")})
print("\nSomas conferidas: composição = total; reentrada da tabela = composição; não resolvido fecha.")

with open(ARQ.with_name("resumo_lacunas.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["grupo", "faixa", "r0_ha", "r0_pct_total", "r1_ha", "r1_pct_total", "r1_pct_r0",
                "r2_ha", "r2_pct_total", "r2_pct_r0", "r1_de_reentrada_anterior_ha", "r2_de_reentrada_anterior_ha",
                "total_PAS_TMP_ha"])
    for L in linhas:
        w.writerow([L["grupo"], L["faixa"], f"{L['r0']:.1f}", f"{pct(L['r0'], TOT):.3f}",
                    f"{L['r1']:.1f}", f"{pct(L['r1'], TOT):.3f}", f"{pct(L['r1'], L['r0']):.1f}",
                    f"{L['r2']:.1f}", f"{pct(L['r2'], TOT):.3f}", f"{pct(L['r2'], L['r0']):.1f}",
                    f"{L['r1_ant']:.1f}", f"{L['r2_ant']:.1f}", f"{TOT:.1f}"])
with open(ARQ.with_name("resumo_lacunas_composicao.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["estado_r0", "ha", "pct_total"])
    for e, v in COMP.items():
        w.writerow([e, f"{v:.1f}", f"{pct(v, TOT):.3f}"])
    w.writerow(["total_PAS_TMP", f"{TOT:.1f}", "100.000"])

# Por quinquênio: o agregado esconde que a série é curta no começo (1985-1990 não pode ter reentrada).
Q = defaultdict(float)
with open(ARQ, encoding="utf-8") as f:
    for r in csv.DictReader(f):
        if r["quinquenio"] not in QUINQ:
            continue
        q, g, est, reg = r["quinquenio"], r["grupo"], r["estado_na_regra"], r["regra"]
        if g == "total_PAS_TMP":
            Q[(q, "total")] += float(r["ha"])
        elif g in ("observada", "lacuna") and est in ("reentrada", "reentrada_anterior"):
            Q[(q, reg)] += float(r["ha"])
with open(ARQ.with_name("resumo_lacunas_quinquenios.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["quinquenio", "total_PAS_TMP_ha", "r0_ha", "r1_ha", "r2_ha", "r0_pct", "r1_pct", "r2_pct", "r1_pct_r0", "r2_pct_r0"])
    print("\nPor quinquênio (% do PAS -> TMP do próprio quinquênio):")
    for q in sorted(QUINQ):
        t, a0, a1, a2 = Q[(q, "total")], Q[(q, "r0")], Q[(q, "r1")], Q[(q, "r2")]
        w.writerow([q, f"{t:.1f}", f"{a0:.1f}", f"{a1:.1f}", f"{a2:.1f}", f"{pct(a0, t):.3f}", f"{pct(a1, t):.3f}",
                    f"{pct(a2, t):.3f}", f"{pct(a1, a0):.1f}", f"{pct(a2, a0):.1f}"])
        print(f"  {q} {pct(a0, t):6.2f} {pct(a1, t):6.2f} {pct(a2, t):6.2f}   retém {pct(a1, a0):5.1f} {pct(a2, a0):5.1f}")
