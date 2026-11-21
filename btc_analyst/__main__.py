"""Analista de BTC para swing trade.

Uso:
    python -m btc_analyst --capital 5000 --risco 1 --html relatorio_btc.html
    python -m btc_analyst --demo --html demo.html     # dados simulados, sem internet
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import analise, fontes
from . import indicadores as ind
from . import plano as pl
from . import relatorio


# ------------------------------------------------------------ dados demo
def _simular(freq: str, n: int, semente: int) -> pd.DataFrame:
    """Passeio aleatório com ciclos em velas de 4h, reamostrado para o timeframe pedido."""
    passo = {"4h": 1, "1d": 6, "1w": 42}[freq]
    total = n * passo
    rng = np.random.default_rng(semente)
    ciclos = np.sin(np.linspace(0, 10 * np.pi, total)) * 0.0012
    close = np.exp(np.cumsum(rng.normal(0.0002, 0.011, total) + ciclos))
    close *= 95_000 / close[-1]                      # termina perto de 95 mil
    abertura = np.r_[close[0], close[:-1]]
    amp = np.abs(rng.normal(0, 0.006, total)) * close
    fim = pd.Timestamp.now(tz="UTC").floor("4h")
    idx = pd.date_range(end=fim, periods=total, freq="4h")
    df = pd.DataFrame({"open": abertura, "high": np.maximum(abertura, close) + amp,
                       "low": np.minimum(abertura, close) - amp, "close": close,
                       "volume": rng.lognormal(8, 0.4, total)}, index=idx)
    if passo > 1:
        regra = "1D" if freq == "1d" else "W-MON"
        df = df.resample(regra, label="left", closed="left").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    df["fechada"] = True
    df.iloc[-1, df.columns.get_loc("fechada")] = False
    return df


def _demo() -> dict:
    agora = datetime.now(timezone.utc)
    d = _simular("1d", 500, 1)
    datas = d.index
    macro = {
        "DXY": pd.Series(np.linspace(104, 101.5, 500), index=datas),
        "US10Y": pd.Series(np.linspace(4.5, 4.2, 500), index=datas),
        "Nasdaq": pd.Series(15_000 * d["close"].to_numpy() / 60_000 * 0.3 + 12_000, index=datas),
        "VIX": pd.Series(np.full(500, 17.5), index=datas),
        "Ouro": pd.Series(np.linspace(2_300, 2_650, 500), index=datas),
    }
    return {
        "1w": _simular("1w", 200, 1), "1d": d, "4h": _simular("4h", 500, 1),
        "macro": macro,
        "fg": {"valor": 38, "classificacao": "Fear", "media_7d": 42, "valor_30d_atras": 61},
        "deriv": {"funding_atual": 0.00008, "funding_media_7d": 0.0001, "oi_usd": 3.1e10,
                  "oi_var_7d": 0.07, "ls_top": 1.4, "ls_geral": 1.9},
        "glob": {"dominancia_btc": 57.8, "var_mcap_24h": 1.2},
        "noticias": [
            {"fonte": "Demo", "titulo": "Bitcoin ETF inflows hit record as institutions accumulate",
             "link": "", "data": agora},
            {"fonte": "Demo", "titulo": "Crypto exchange hack drains $40M in stablecoins",
             "link": "", "data": agora},
            {"fonte": "Demo", "titulo": "Traders brace for FOMC decision; Powell expected to stay hawkish",
             "link": "", "data": agora},
        ],
    }


# ------------------------------------------------------------- coleta real
def _coletar(log) -> dict:
    tarefas = {
        "1w": lambda: fontes.candles("1w", 300),
        "1d": lambda: fontes.candles("1d", 500),
        "4h": lambda: fontes.candles("4h", 500),
        "macro": fontes.macro,
        "fg": fontes.medo_ganancia,
        "deriv": fontes.derivativos,
        "glob": fontes.mercado_global,
        "noticias": fontes.noticias,
    }
    dados, erros = {}, {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futuros = {k: ex.submit(f) for k, f in tarefas.items()}
        for k, f in futuros.items():
            try:
                dados[k] = f.result()
            except Exception as e:  # noqa: BLE001
                dados[k], erros[k] = None, e
                log(f"  aviso: {k} indisponível ({str(e)[:120]})")
    for tf in ("1w", "1d", "4h"):
        if dados[tf] is None:
            raise SystemExit(f"Sem candles {tf}: a análise precisa do preço. Erro: {erros[tf]}")
    dados["erros"] = erros
    return dados


# ---------------------------------------------------------------- pipeline
def analisar(dados: dict, cfg: pl.Config, demo: bool = False) -> dict:
    # Indicadores só com velas fechadas; preço atual vem da vela em formação
    preco = float(dados["4h"]["close"].iloc[-1])
    quadros, graficos = {}, {}
    for tf in ("1d", "4h"):  # o gráfico mostra também a vela em formação
        graficos[tf] = ind.enriquecer(dados[tf].drop(columns="fechada", errors="ignore"))
    for tf in ("1w", "1d", "4h"):
        df = dados[tf]
        fechadas = df[df["fechada"]] if "fechada" in df else df
        q = ind.enriquecer(fechadas.drop(columns="fechada", errors="ignore"))
        quadros[tf] = q

    erros = dados.get("erros", {})
    pilares = [analise.tendencia(quadros), analise.tecnico(quadros)]
    try:
        pilares.append(analise.macro(dados["macro"], quadros["1d"]) if dados.get("macro")
                       else analise.indisponivel("Macro", erros.get("macro", "sem dados")))
    except Exception as e:  # noqa: BLE001
        pilares.append(analise.indisponivel("Macro", e))
    try:
        pilares.append(analise.sentimento(dados.get("fg"), dados.get("deriv"), dados.get("glob"),
                                          quadros["1d"]))
    except Exception as e:  # noqa: BLE001
        pilares.append(analise.indisponivel("Sentimento e índices", e))
    if dados.get("noticias") is not None:
        pilares.append(analise.noticias(dados["noticias"]))
    else:
        pilares.append(analise.indisponivel("Notícias", erros.get("noticias", "sem dados")))

    consolidado = analise.consolidar(pilares)

    # Níveis: pivôs de semanal, diário e 4h agrupados com tolerância de 0,35 ATR diário
    atr1 = float(quadros["1d"]["atr"].iloc[-1])
    recortes = {"1w": quadros["1w"].iloc[-104:], "1d": quadros["1d"].iloc[-180:], "4h": quadros["4h"].iloc[-240:]}
    niveis = ind.niveis(recortes, tolerancia=0.35 * atr1)
    for nome, col in (("EMA200 diária", "ema200"), ("EMA50 diária", "ema50")):
        niveis.append(ind.Nivel(float(quadros["1d"][col].iloc[-1]), 2, nome))
    niveis.sort(key=lambda n: n.preco)

    noticias = next((p for p in pilares if p.nome == "Notícias"), None)
    evento = bool(noticias and noticias.dados.get("eventos"))
    # Viés neutro com pouca convicção: mostra os dois lados como condicionais
    planos = pl.gerar(consolidado["direcao"], quadros, niveis, cfg, evento_no_radar=evento, preco=preco)

    perto = 5 * atr1
    return {
        "gerado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "demo": demo,
        "preco": preco,
        "config": cfg,
        "pilares": pilares,
        "consolidado": consolidado,
        "resistencias": [n for n in niveis if preco < n.preco <= preco + perto][:6],
        "suportes": [n for n in niveis if preco - perto <= n.preco < preco][::-1][:6],
        "planos": planos,
        "quadros": quadros,
        "graficos": graficos,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m btc_analyst", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--capital", type=float, default=10_000, help="capital em USDT (padrão 10000)")
    ap.add_argument("--risco", type=float, default=1.0, help="%% do capital arriscado por trade (padrão 1)")
    ap.add_argument("--rr", type=float, default=2.0, help="ganho/perda mínimo (padrão 2)")
    ap.add_argument("--taxa", type=float, default=0.1, help="taxa por lado em %% (padrão 0.1)")
    ap.add_argument("--alavancagem", type=float, default=1.0, help="alavancagem máxima (padrão 1 = spot)")
    ap.add_argument("--html", help="salva relatório HTML com gráfico neste arquivo")
    ap.add_argument("--json", help="salva o resultado em JSON neste arquivo")
    ap.add_argument("--demo", action="store_true", help="usa dados simulados (não precisa de internet)")
    a = ap.parse_args(argv)
    if a.rr < 2:
        print("Aviso: você pediu ganho/perda abaixo de 2:1.", file=sys.stderr)

    cfg = pl.Config(capital=a.capital, risco_pct=a.risco, rr_min=a.rr, taxa=a.taxa / 100,
                    alavancagem_max=a.alavancagem)
    log = lambda m: print(m, file=sys.stderr)  # noqa: E731
    if a.demo:
        dados = _demo()
    else:
        log("Coletando dados (Binance, Yahoo Finance, CoinGecko, alternative.me, RSS)...")
        dados = _coletar(log)
    r = analisar(dados, cfg, demo=a.demo)

    print(relatorio.texto(r))
    if a.html:
        with open(a.html, "w", encoding="utf-8") as f:
            f.write(relatorio.pagina(r))
        log(f"Relatório HTML salvo em {a.html}")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            f.write(relatorio.para_json(r))
        log(f"JSON salvo em {a.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
