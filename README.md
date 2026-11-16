# Testes repositório pasture-crop-dynamic

Testes feitos com o motor de episódios de pastagem do [pasture-crop-dynamic](https://github.com/barroso2501/pasture-crop-dynamic), aplicados ao Cerrado inteiro, pixel a pixel.

**Páginas com os resultados:**
- Testes no Cerrado: https://victorgit10.github.io/testes-pasture-crop-dynamic/
- Teste de lacunas nas reentradas: https://victorgit10.github.io/testes-pasture-crop-dynamic/lacunas.html

## Dados e recorte

- MapBiomas Coleção 11 (41 anos, 1985–2025), grade nativa de 30 m, sem reamostragem. Os dados foram exportados do Earth Engine em quadrados de 8192 × 8192 px que tocam o Cerrado.
- O recorte usa o bioma Cerrado do IBGE (geobr, 2019), dividido por UF (geobr, 2020).
- Os grupos de classe vêm de `config/constants.js`. As regras de episódio (entrada, reentrada, pasto inicial de 1985) vêm da Decisão 024 e de `docs/methods/entry_reentry_auxiliary_decomposition_v1.md`.
- Não há Amazônia nem a grade de hexágonos: tudo vale para o Cerrado, por estado.

## Código (`codigo/`)

| Arquivo | O que faz |
|---|---|
| `exporta_cerrado.py` | Exporta a Coleção 11 do Cerrado pelo Earth Engine, um quadrado por tarefa. A variável de ambiente `GEE_PROJECT` define o projeto. |
| `testes_goias_c11.py` | É o motor: grupos de classe, episódios de pastagem por pixel (`motor`) e as contas acumuladas (`acumula`). Foi escrito primeiro para Goiás. O `main` dele usa a malha municipal de outro projeto, então aqui ele serve só como módulo. |
| `rq3_trajetoria.py` | Faz a trajetória de cada pixel, da última vegetação nativa à primeira lavoura temporária (`acumula_rq3`). |
| `testes_cerrado.py` | Roda `acumula` e `acumula_rq3` no Cerrado por UF. Gera `cerrado_acumulados.csv` e `cerrado_rq3.csv`. |
| `testes_extra_cerrado.py` | Testes extras no Cerrado por UF. Gera `cerrado_extra.csv`. Os testes são: o que houve no intervalo fora do pasto; a diferença entre RQ1 e RQ2 ignorando saídas de 1 e 2 anos; e a trajetória com o histórico de pasto. |
| `test_motor.py` | Casos sintéticos do motor: cada sequência de classes e o episódio esperado. Para rodar: `python -I test_motor.py`. |
| `resumo_testes.py` | Gera um resumo em JSON a partir das tabelas. Para rodar: `python -I resumo_testes.py cerrado [UF,UF,...]`. |
| `numeros_pagina.py` | Refaz, a partir das tabelas, cada número da página. Para rodar: `python -I numeros_pagina.py`. |
| `teste_lacunas.py` | Teste de lacunas nas reentradas: roda o motor sem suavização (r0), preenchendo interrupções de 1 ano (r1) e de até 2 anos (r2), e separa a reentrada por grupo (interrupção inteiramente observada ou com lacuna) e por faixa de duração (1, 2, 3–4 e 5 anos ou mais). Gera `cerrado_lacunas.csv`. Casos sintéticos: `python -I teste_lacunas.py --casos`. |
| `resumo_lacunas.py` | Soma os sete quinquênios 1985–2020, monta as tabelas do teste de lacunas e para com erro se as somas não fecharem. Para rodar: `python -I resumo_lacunas.py`. |
| `figura_lacunas.py` | Gera `figura_lacunas.png`. Para rodar: `python -I figura_lacunas.py`. |

Para rodar do zero, primeiro exporte os quadrados com `exporta_cerrado.py --todos` e baixe-os do Drive. Depois rode:

```
python -I codigo/testes_cerrado.py --dados <pasta dos tifs> --cerrado <cerrado.gpkg> --saida resultados
python -I codigo/testes_extra_cerrado.py --dados <pasta dos tifs> --cerrado <cerrado.gpkg> --saida resultados
python -I codigo/teste_lacunas.py --dados <pasta dos tifs> --cerrado <cerrado.gpkg> --saida resultados
python -I codigo/resumo_lacunas.py
```

O teste de lacunas leva cerca de 1 hora no Cerrado inteiro com 5 processos (`--workers`); cada processo usa alguns GB de memória.

Dependências: `numpy`, `rasterio`, `geopandas`, `shapely`, `geobr` e, para a exportação, `earthengine-api`.

## Resultados (`resultados/`)

As tabelas estão em hectares. A coluna `uf` traz a sigla do estado e é a parte dele dentro do Cerrado.

- `cerrado_acumulados.csv`: estoques por ano, fluxo de 5 anos vegetação → lavoura, conversão pasto → lavoura por tipo de episódio, transições anuais da pastagem, RQ1 × RQ2.
- `cerrado_rq3.csv`: trajetória da última vegetação nativa à primeira lavoura, por ano (`AAAA`), período (`per:`) e estado (`meso:`).
- `cerrado_extra.csv`: testes extras.
- `resumo_*.json`: saída de `resumo_testes.py` para o Cerrado e para grupos de estados.
- `cerrado_lacunas.csv`: saída completa do teste de lacunas, em hectares, para o Cerrado inteiro. Colunas: `quinquenio`, `grupo`, `faixa`, `regra`, `estado_na_regra`, `ha`.
  - `grupo`: `observada` (todos os anos do intervalo têm classe válida diferente de pasto) ou `lacuna` (algum ano sem classe: código 0, 27 ou desconhecido). Linhas especiais: `total_PAS_TMP` (o denominador), `composicao_r0` (o total por tipo de episódio sem suavização), `nao_resolvido_com_pasto_antes` (ano sem classe logo antes da volta ao pasto, que o motor não conta como reentrada) e `nao_resolvido_sem_pasto_antes`.
  - O intervalo vai do último ano de pasto antes da interrupção ao primeiro ano do episódio em curso em t0, sem contar esses dois anos. Grupo e faixa são sempre os da regra r0.
  - `estado_na_regra`: o que a área de reentrada de r0 vira em r1 ou r2. `reentrada_anterior` quer dizer que o preenchimento juntou o episódio a um episódio anterior que também era reentrada.
- `resumo_lacunas.csv`, `resumo_lacunas_quinquenios.csv`, `resumo_lacunas_composicao.csv`: as tabelas da página do teste de lacunas. Os percentuais são sobre o total original de PAS→TMP.
- `figura_lacunas.png`: reentrada por duração da interrupção em cada regra e por quinquênio.

## Página (`docs/`)

`docs/index.html` é a página publicada pelo GitHub Pages. É um arquivo único: os números estão no próprio HTML e saem de `numeros_pagina.py`. `docs/lacunas.html` é a página do teste de lacunas; os números saem de `resumo_lacunas.py`.
