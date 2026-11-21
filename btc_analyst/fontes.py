"""Coleta de dados: candles, derivativos, índices, macro e notícias.

Todas as fontes são públicas e não pedem API key. Cada função levanta
exceção se falhar; quem chama decide o que fazer (o analista marca o pilar
como indisponível e segue com o resto).
"""
from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import pandas as pd
import requests

TIMEOUT = 15
_sessao = requests.Session()
_sessao.headers["User-Agent"] = "Mozilla/5.0 (btc-analyst)"


def _get(url: str, params: dict | None = None) -> requests.Response:
    ultimo_erro: Exception | None = None
    for tentativa in range(3):
        try:
            r = _sessao.get(url, params=params, timeout=TIMEOUT)
            if r.status_code == 429:  # limite de requisições: espera e tenta de novo
                time.sleep(2 * (tentativa + 1))
                continue
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            ultimo_erro = e
            time.sleep(1)
    raise RuntimeError(f"{url}: {ultimo_erro or 'limite de requisições'}")


# ---------------------------------------------------------------- candles
_COLUNAS = ["open", "high", "low", "close", "volume"]


def _df_binance(dados: list) -> pd.DataFrame:
    df = pd.DataFrame(dados).iloc[:, :7]
    df.columns = ["t", *_COLUNAS, "fechamento"]
    df["t"] = pd.to_datetime(df["t"], unit="ms", utc=True)
    df[_COLUNAS] = df[_COLUNAS].astype(float)
    df["fechada"] = df["fechamento"].astype("int64") < int(time.time() * 1000)
    return df.set_index("t")[[*_COLUNAS, "fechada"]]


def candles(intervalo: str, limite: int = 500, simbolo: str = "BTCUSDT") -> pd.DataFrame:
    """OHLCV com índice em UTC. intervalo: '4h', '1d' ou '1w'.

    A coluna 'fechada' indica se a vela já fechou (a última costuma estar em formação).
    """
    erros = []
    for base in ("https://api.binance.com", "https://data-api.binance.vision"):
        try:
            dados = _get(f"{base}/api/v3/klines",
                         {"symbol": simbolo, "interval": intervalo, "limit": limite}).json()
            return _df_binance(dados)
        except Exception as e:  # noqa: BLE001
            erros.append(str(e))

    # Reserva: Bybit (útil onde a Binance é bloqueada)
    try:
        mapa = {"1h": "60", "4h": "240", "1d": "D", "1w": "W"}
        dados = _get("https://api.bybit.com/v5/market/kline",
                     {"category": "spot", "symbol": simbolo,
                      "interval": mapa[intervalo], "limit": min(limite, 1000)}).json()
        linhas = dados["result"]["list"][::-1]  # Bybit devolve do mais novo para o mais antigo
        df = pd.DataFrame(linhas).iloc[:, :6]
        df.columns = ["t", *_COLUNAS]
        df["t"] = pd.to_datetime(df["t"].astype("int64"), unit="ms", utc=True)
        df[_COLUNAS] = df[_COLUNAS].astype(float)
        df["fechada"] = True
        df.iloc[-1, df.columns.get_loc("fechada")] = False
        return df.set_index("t")
    except Exception as e:  # noqa: BLE001
        erros.append(str(e))
    raise RuntimeError("Não consegui baixar candles: " + " | ".join(erros))


# ------------------------------------------------------------ derivativos
def derivativos(simbolo: str = "BTCUSDT") -> dict:
    """Funding, open interest e razão long/short dos futuros perpétuos da Binance."""
    base = "https://fapi.binance.com"
    premium = _get(f"{base}/fapi/v1/premiumIndex", {"symbol": simbolo}).json()
    historico = _get(f"{base}/fapi/v1/fundingRate", {"symbol": simbolo, "limit": 21}).json()
    oi = _get(f"{base}/futures/data/openInterestHist",
              {"symbol": simbolo, "period": "1d", "limit": 8}).json()
    ls_top = _get(f"{base}/futures/data/topLongShortPositionRatio",
                  {"symbol": simbolo, "period": "4h", "limit": 1}).json()
    ls_geral = _get(f"{base}/futures/data/globalLongShortAccountRatio",
                    {"symbol": simbolo, "period": "4h", "limit": 1}).json()
    oi_valores = [float(x["sumOpenInterestValue"]) for x in oi]
    return {
        "funding_atual": float(premium["lastFundingRate"]),
        "funding_media_7d": sum(float(x["fundingRate"]) for x in historico) / max(len(historico), 1),
        "oi_usd": oi_valores[-1] if oi_valores else None,
        "oi_var_7d": (oi_valores[-1] / oi_valores[0] - 1) if len(oi_valores) > 1 else None,
        "ls_top": float(ls_top[0]["longShortRatio"]) if ls_top else None,
        "ls_geral": float(ls_geral[0]["longShortRatio"]) if ls_geral else None,
    }


# ----------------------------------------------------------------- índices
def medo_ganancia(dias: int = 30) -> dict:
    """Crypto Fear & Greed Index (alternative.me). 0 = medo extremo, 100 = ganância extrema."""
    dados = _get("https://api.alternative.me/fng/", {"limit": dias}).json()["data"]
    valores = [int(x["value"]) for x in dados]  # mais recente primeiro
    return {
        "valor": valores[0],
        "classificacao": dados[0]["value_classification"],
        "media_7d": sum(valores[:7]) / min(7, len(valores)),
        "valor_30d_atras": valores[-1],
    }


def mercado_global() -> dict:
    """Dominância do BTC e variação do mercado cripto (CoinGecko)."""
    d = _get("https://api.coingecko.com/api/v3/global").json()["data"]
    return {
        "dominancia_btc": d["market_cap_percentage"]["btc"],
        "var_mcap_24h": d["market_cap_change_percentage_24h_usd"],
    }


# -------------------------------------------------------------------- macro
ATIVOS_MACRO = {
    "DXY": "DX-Y.NYB",       # índice do dólar
    "US10Y": "^TNX",         # juros do Tesouro americano de 10 anos (%)
    "Nasdaq": "^IXIC",
    "S&P 500": "^GSPC",
    "VIX": "^VIX",           # volatilidade implícita da bolsa americana
    "Ouro": "GC=F",
}


def serie_yahoo(ticker: str, periodo: str = "1y") -> pd.Series:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    r = _get(url, {"range": periodo, "interval": "1d"}).json()["chart"]["result"][0]
    s = pd.Series(r["indicators"]["quote"][0]["close"],
                  index=pd.to_datetime(r["timestamp"], unit="s", utc=True), dtype=float)
    return s.dropna()


def macro() -> dict[str, pd.Series]:
    series = {}
    for nome, ticker in ATIVOS_MACRO.items():
        try:
            series[nome] = serie_yahoo(ticker)
        except Exception:  # noqa: BLE001 - um ativo faltando não derruba o pilar
            pass
    if not series:
        raise RuntimeError("Nenhuma série macro disponível (Yahoo Finance)")
    return series


# ------------------------------------------------------------------ notícias
FEEDS = {
    "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "Cointelegraph": "https://cointelegraph.com/rss",
    "Decrypt": "https://decrypt.co/feed",
    "Bitcoin Magazine": "https://bitcoinmagazine.com/feed",
    "The Block": "https://www.theblock.co/rss.xml",
}


def _data(texto: str | None) -> datetime | None:
    if not texto:
        return None
    try:
        d = parsedate_to_datetime(texto)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(texto.replace("Z", "+00:00"))
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def noticias(horas: int = 72) -> list[dict]:
    """Manchetes recentes dos principais sites de cripto (RSS e Atom)."""
    limite = datetime.now(timezone.utc).timestamp() - horas * 3600
    itens, vistos, falhas = [], set(), 0
    for fonte, url in FEEDS.items():
        try:
            raiz = ET.fromstring(_get(url).content)
        except Exception:  # noqa: BLE001
            falhas += 1
            continue
        for item in raiz.iter():
            tag = item.tag.rsplit("}", 1)[-1]
            if tag not in ("item", "entry"):
                continue
            campos = {c.tag.rsplit("}", 1)[-1]: c for c in item}
            titulo = (campos["title"].text or "").strip() if "title" in campos else ""
            link_el = campos.get("link")
            link = (link_el.text or link_el.get("href", "")).strip() if link_el is not None else ""
            data_el = campos.get("pubDate") or campos.get("published") or campos.get("updated")
            data = _data(data_el.text if data_el is not None else None)
            chave = re.sub(r"\W+", "", titulo.lower())[:80]
            if not titulo or chave in vistos or (data and data.timestamp() < limite):
                continue
            vistos.add(chave)
            itens.append({"fonte": fonte, "titulo": titulo, "link": link, "data": data})
    if falhas == len(FEEDS):
        raise RuntimeError("Nenhum feed de notícias respondeu")
    itens.sort(key=lambda x: x["data"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return itens
