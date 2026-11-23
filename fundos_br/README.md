# Triagem de fundos brasileiros (CVM) — nov/2026

Fonte: CVM (informe diário de todos os fundos, 2019–nov/2026) e BCB/SGS (CDI série 12, PTAX série 1).

Janela: 29/10/2021 → 18/11/2026 (~5 anos). Critérios:
- fundo ativo, com cota em out/2021 e em nov/2026 (≥ 5 anos);
- nenhum ano-calendário (2020–2026 YTD) abaixo de -10%;
- retorno acumulado ≥ 150% do CDI do mesmo período (CDI no período ≈ 83,4%, logo fundo ≥ ~125%);
- não exclusivo, PL ≥ R$ 30 mi, ≥ 50 cotistas.

```
python3 panel.py <pasta_zips_cvm> panel.parquet
python3 analise.py <pasta_trabalho> <pasta_zips_cvm>
```
`candidatos.csv` traz os 36 fundos (incluindo feeders do mesmo master) que passaram.
