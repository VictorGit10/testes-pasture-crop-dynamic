"""Tira dos CSVs acumulados os números do RELATORIO-TESTES.md (T1-T5, T7, T8).

    python -I resumo_testes.py goias                      (confere contra o relatório de Goiás)
    python -I resumo_testes.py cerrado [UF,UF,...]        (Cerrado inteiro ou só as UFs dadas)
Imprime JSON com os números.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

AQUI = Path(__file__).resolve().parent
JAN = [f"{t}-{t + 5}" for t in range(1985, 2020, 5)]  # 1985-90 .. 2015-20
JAN_ATE_2020 = JAN  # 7 quinquênios, t0 de 1985 a 2015


def carrega(modo, ufs=None):
    M = defaultdict(float)
    R = defaultdict(float)
    if modo == "goias":
        with open(AQUI / "saida/acumulados.csv", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                M[(r["tabela"], r["chave"], r["item"])] += float(r["ha"])
        with open(AQUI / "saida/rq3_trajetoria_v2.csv", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                R[(r["chave"], r["item"])] += float(r["ha"])
    else:
        with open(AQUI.parent / "resultados/cerrado_acumulados.csv", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if ufs and r["uf"] not in ufs:
                    continue
                M[(r["tabela"], r["chave"], r["item"])] += float(r["ha"])
        with open(AQUI.parent / "resultados/cerrado_rq3.csv", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                R[(r["chave"], r["item"])] += float(r["ha"])
    return M, R


def pct(a, b):
    return round(100 * a / b, 1) if b else None


def resumo(M, R, ufs=None):
    s = lambda tb, it, jans=JAN_ATE_2020: sum(M[(tb, j, it)] for j in jans)  # noqa: E731
    o = {}
    # T2 classe anterior à entrada (1985-2020)
    t2 = {}
    for tipo in ("primeira", "reentrada"):
        tot = sum(s("PAS_TMP_classe_antes", f"{tipo}|{g}") for g in
                  ("NAT", "PAS", "TMP", "MOS21", "SILV9", "PEREN", "OUT", "AGUA", "NODATA27"))
        d = {g: pct(s("PAS_TMP_classe_antes", f"{tipo}|{g}"), tot) for g in ("NAT", "TMP", "MOS21")}
        d["outros"] = round(100 - sum(v for v in d.values() if v is not None), 1)
        d["area_mil_ha"] = round(tot / 1e3)
        t2[tipo] = d
    o["T2_classe_antes"] = t2
    # T4 reentrada: coorte 1985 x pós-1985
    c = s("PAS_TMP_reentrada_por", "coorte1985"); p = s("PAS_TMP_reentrada_por", "pos1985")
    o["T4_reentrada_coorte1985_pct"] = {
        "1985-2020": pct(c, c + p),
        **{j: pct(M[("PAS_TMP_reentrada_por", j, "coorte1985")],
                  M[("PAS_TMP_reentrada_por", j, "coorte1985")] + M[("PAS_TMP_reentrada_por", j, "pos1985")])
           for j in JAN_ATE_2020}}
    # T5 RQ1 x RQ2
    a = M[("RQ1xRQ2", "2020", "coorte1985_em_PAS")]; b = M[("RQ1xRQ2", "2020", "inicial_continuo")]
    o["T5"] = {"coorte1985_em_PAS_Mha": round(a / 1e6, 2), "continua_Mha": round(b / 1e6, 2),
               "diferenca_pct": pct(a - b, a)}
    # T1 RQ3
    tot = s("NAT_TMP", "total")
    o["T1"] = {"NAT_TMP_mil_ha": round(tot / 1e3),
               "pasto_no_quinquenio": pct(s("NAT_TMP", "pasto_no_quinquenio"), tot),
               "pasto_desde_1985": pct(s("NAT_TMP", "pasto_em_qualquer_ano_ate_t1"), tot)}
    pers = [f"per:{j}" for j in JAN_ATE_2020]
    if ufs:  # cerrado_rq3.csv não tem coluna de UF: o agregado por UF vem das chaves meso:<UF> (1986-2020)
        pers = [f"meso:{u}" for u in ufs]
    tt = sum(R[(k, "total")] for k in pers)
    o["T1"]["trajetoria_pasto_entre"] = pct(sum(R[(k, "pasto_entre")] for k in pers), tt)
    o["T1"]["trajetoria_2anos"] = pct(sum(R[(k, "pasto_entre_2anos_seguidos")] for k in pers), tt)
    o["T1"]["trajetoria_mosaico_sem_pasto"] = pct(sum(R[(k, "mosaico_entre_sem_pasto")] for k in pers), tt)
    o["T1"]["trajetoria_direto"] = pct(sum(R[(k, "direto_1_ano")] for k in pers), tt)
    o["T1"]["trajetoria_area_mil_ha"] = round(tt / 1e3)
    o["T1"]["por_periodo"] = None if ufs else {k[4:]: pct(R[(k, "pasto_entre")], R[(k, "total")]) for k in pers}
    regs = sorted({k[0] for k in R if k[0].startswith("meso:")})
    if ufs:
        regs = [r for r in regs if r[5:] in ufs]
    o["T1"]["por_regiao"] = {r[5:]: {"mil_ha": round(R[(r, "total")] / 1e3),
                                     "pasto": pct(R[(r, "pasto_entre")], R[(r, "total")]),
                                     "mosaico_sem_pasto": pct(R[(r, "mosaico_entre_sem_pasto")], R[(r, "total")]),
                                     "direto": pct(R[(r, "direto_1_ano")], R[(r, "total")])}
                             for r in regs if R[(r, "total")] > 0}
    # T8 Mosaico no fim da série
    o["T8_anual_mil_ha"] = {y: {"TMP": round(M[("anual_PAS_para", y, "TMP")] / 1e3),
                                "MOS": round(M[("anual_PAS_para", y, "MOS21")] / 1e3)}
                            for y in ("2015", "2019", "2020", "2021", "2025")}
    o["T8_5anos_mil_ha"] = {j: {"TMP": round(M[("PAS_TMP", j, "total")] / 1e3),
                                "MOS": round(M[("PAS_para", j, "MOS21")] / 1e3)} for j in ("2015-2020", "2020-2025")}
    # T3 alternância
    t3 = {}
    for nome, tb in (("regra_Mario", None), ("ignora_1ano", "PAS_TMP_suav1"), ("ignora_2anos", "PAS_TMP_suav2")):
        tot = s("PAS_TMP", "total")
        if tb is None:
            re_ = s("PAS_TMP_entrada", "reentrada"); en = s("PAS_TMP", "entrada")
        else:
            re_ = s(tb, "reentrada"); en = s(tb, "entrada")
        t3[nome] = {"reentrada/entrada": pct(re_, en), "reentrada/total": pct(re_, tot)}
    gi = {n: s("PAS_TMP_reentrada_intervalo", n) for n in ("1ano", "2anos", "3-4anos", "5+anos")}
    t3["intervalo"] = {n: pct(v, sum(gi.values())) for n, v in gi.items()}
    o["T3"] = t3
    # T7 definição ampla de lavoura
    ef = []
    for j in JAN_ATE_2020:
        tmp = M[("PAS_TMP", j, "total")]
        ef.append((j, pct(M[("PAS_para", j, "SILV9")] + M[("PAS_para", j, "PEREN")], tmp)))
    o["T7_acrescimo_pct"] = dict(ef)
    return o


if __name__ == "__main__":
    modo = sys.argv[1]
    ufs = set(sys.argv[2].split(",")) if len(sys.argv) > 2 else None
    print(json.dumps(resumo(*carrega(modo, ufs), ufs), ensure_ascii=False, indent=1))
