"""exporta_cerrado.py: exporta o MapBiomas Col. 11 (41 bandas, 1985-2025) do Cerrado.

Mesma lógica do `export_cubo_mapbiomas_go.py` da dissertação (grade nativa, sem
reamostragem, sem máscara), mas em vez de um retângulo único exporta só os
quadrados de 8192 px (~2,2°) que tocam o Cerrado do IBGE (geobr, 2019).
Cada quadrado é uma tarefa separada, e pode ser processado sozinho.

    python exporta_cerrado.py --plano            (só mostra os quadrados)
    python exporta_cerrado.py --piloto           (exporta 1 quadrado)
    python exporta_cerrado.py --todos            (exporta os que faltam)
    python exporta_cerrado.py --monitor          (estado e gasto de cota)
"""
from __future__ import annotations

import argparse
import math
import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import ee
import geopandas as gpd
from shapely.geometry import box

PROJETO = os.environ.get("GEE_PROJECT")  # projeto do Earth Engine de quem roda
ASSET = "projects/mapbiomas-public/assets/brazil/lulc/collection11/mapbiomas_brazil_collection11_coverage_v3"
ANOS = range(1985, 2026)
PX = 0.00026949458523585647
ORIGEM_X, ORIGEM_Y = -74.02073025380652, 5.405791885246045
LADO = 8192
PASTA = "cerrado_col11"
PREFIXO = "cerrado_c11"
# quadrado-piloto: oeste da Bahia (MATOPIBA), fora de Goiás
PILOTO_PONTO = (-45.6, -12.3)

AQUI = os.path.dirname(os.path.abspath(__file__))


def quadrados():
    arq = os.path.join(AQUI, "cerrado_ibge.gpkg")
    if not os.path.exists(arq):  # bioma Cerrado do IBGE (geobr, 2019)
        import geobr
        b = geobr.read_biomes(year=2019)
        b[b.name_biome == "Cerrado"].to_file(arq, driver="GPKG")
    cer = gpd.read_file(arq).geometry.union_all()
    lon0, lat0, lon1, lat1 = cer.bounds
    passo = LADO * PX
    i0 = math.floor((lon0 - ORIGEM_X) / passo)
    i1 = math.floor((lon1 - ORIGEM_X) / passo)
    j0 = math.floor((ORIGEM_Y - lat1) / passo)
    j1 = math.floor((ORIGEM_Y - lat0) / passo)
    out = []
    for j in range(j0, j1 + 1):
        for i in range(i0, i1 + 1):
            x0 = ORIGEM_X + i * LADO * PX
            y0 = ORIGEM_Y - j * LADO * PX
            q = box(x0, y0 - passo, x0 + passo, y0)
            inter = q.intersection(cer).area / q.area
            if inter > 0:
                out.append(dict(nome=f"{PREFIXO}_r{j:03d}_c{i:03d}", i=i, j=j, x0=x0, y0=y0, frac=inter))
    return out


def tarefa(q):
    img = ee.Image(ASSET).select([f"classification_{a}" for a in ANOS]).toByte()
    passo = LADO * PX
    reg = ee.Geometry.Rectangle([q["x0"], q["y0"] - passo, q["x0"] + passo, q["y0"]],
                                proj="EPSG:4326", geodesic=False)
    return ee.batch.Export.image.toDrive(
        image=img, description=q["nome"], folder=PASTA, fileNamePrefix=q["nome"],
        region=reg, crs="EPSG:4326", crsTransform=[PX, 0, q["x0"], 0, -PX, q["y0"]],
        fileDimensions=[LADO, LADO], fileFormat="GeoTIFF", maxPixels=int(1e13))


def operacoes():
    ops = [o for o in ee.data.listOperations() if o.get("metadata", {}).get("description", "").startswith(PREFIXO)]
    return {o["metadata"]["description"]: o for o in ops}


def main():
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    for a in ("--plano", "--piloto", "--todos", "--monitor"):
        g.add_argument(a, action="store_true")
    a = p.parse_args()

    qs = quadrados()
    if a.plano:
        print(f"{len(qs)} quadrados tocam o Cerrado; {sum(q['frac'] for q in qs):.1f} equivalentes inteiros")
        return

    if not PROJETO:
        sys.exit("defina GEE_PROJECT com o seu projeto do Earth Engine")
    ee.Initialize(project=PROJETO)
    print("projeto:", PROJETO)
    ops = operacoes()

    if a.monitor:
        tot = 0.0
        for nome, o in sorted(ops.items()):
            m = o["metadata"]
            s = float(m.get("batchEecuUsageSeconds", 0) or 0)
            tot += s
            print(f"  {nome}  {m.get('state')}  EECU-h={s / 3600:.3f}")
        print(f"total: {tot / 3600:.3f} EECU-h em {len(ops)} tarefas")
        return

    if a.piloto:
        px, py = PILOTO_PONTO
        alvo = [q for q in qs if q["x0"] <= px < q["x0"] + LADO * PX and q["y0"] - LADO * PX < py <= q["y0"]]
    else:
        alvo = [q for q in qs if q["nome"] not in ops or ops[q["nome"]]["metadata"].get("state") in ("FAILED", "CANCELLED")]
    for q in alvo:
        t = tarefa(q)
        t.start()
        print("enviada:", q["nome"], f"(Cerrado ocupa {q['frac']:.0%})")


if __name__ == "__main__":
    main()
