"""Indicadores técnicos, pivôs, níveis de suporte/resistência e estrutura de mercado."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    ganho = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    perda = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = ganho / perda.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(100)


def macd(close: pd.Series, rapida=12, lenta=26, sinal=9):
    linha = ema(close, rapida) - ema(close, lenta)
    linha_sinal = ema(linha, sinal)
    return linha, linha_sinal, linha - linha_sinal


def true_range(df: pd.DataFrame) -> pd.Series:
    anterior = df["close"].shift()
    return pd.concat([df["high"] - df["low"],
                      (df["high"] - anterior).abs(),
                      (df["low"] - anterior).abs()], axis=1).max(axis=1)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    return true_range(df).ewm(alpha=1 / n, adjust=False).mean()


def adx(df: pd.DataFrame, n: int = 14):
    alta = df["high"].diff()
    baixa = -df["low"].diff()
    mais = pd.Series(np.where((alta > baixa) & (alta > 0), alta, 0.0), index=df.index)
    menos = pd.Series(np.where((baixa > alta) & (baixa > 0), baixa, 0.0), index=df.index)
    tr = true_range(df).ewm(alpha=1 / n, adjust=False).mean()
    di_mais = 100 * mais.ewm(alpha=1 / n, adjust=False).mean() / tr
    di_menos = 100 * menos.ewm(alpha=1 / n, adjust=False).mean() / tr
    dx = 100 * (di_mais - di_menos).abs() / (di_mais + di_menos).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False).mean(), di_mais, di_menos


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0):
    media = close.rolling(n).mean()
    desvio = close.rolling(n).std()
    sup, inf = media + k * desvio, media - k * desvio
    pct_b = (close - inf) / (sup - inf)
    return sup, media, inf, pct_b


def obv(df: pd.DataFrame) -> pd.Series:
    direcao = np.sign(df["close"].diff()).fillna(0)
    return (direcao * df["volume"]).cumsum()


def enriquecer(df: pd.DataFrame) -> pd.DataFrame:
    """Adiciona as colunas de indicadores usadas pelo analista."""
    df = df.copy()
    for n in (20, 50, 200):
        df[f"ema{n}"] = ema(df["close"], n)
    df["rsi"] = rsi(df["close"])
    df["macd"], df["macd_sinal"], df["macd_hist"] = macd(df["close"])
    df["atr"] = atr(df)
    df["adx"], df["di_mais"], df["di_menos"] = adx(df)
    df["bb_sup"], df["bb_meio"], df["bb_inf"], df["bb_pct"] = bollinger(df["close"])
    df["obv"] = obv(df)
    df["vol_media20"] = df["volume"].rolling(20).mean()
    return df


# ------------------------------------------------------- pivôs e estrutura
def pivos(df: pd.DataFrame, janela: int = 3) -> tuple[list[tuple], list[tuple]]:
    """Topos e fundos de swing: máxima (mínima) maior (menor) que as `janela` velas de cada lado.

    Retorna listas de (timestamp, preço, posição).
    """
    altas, baixas = df["high"].to_numpy(), df["low"].to_numpy()
    topos, fundos = [], []
    for i in range(janela, len(df) - janela):
        trecho = slice(i - janela, i + janela + 1)
        if altas[i] == altas[trecho].max():
            topos.append((df.index[i], float(altas[i]), i))
        if baixas[i] == baixas[trecho].min():
            fundos.append((df.index[i], float(baixas[i]), i))
    return topos, fundos


def estrutura(df: pd.DataFrame, janela: int = 3) -> str:
    """'alta' (topos e fundos ascendentes), 'baixa' (descendentes) ou 'lateral'."""
    topos, fundos = pivos(df, janela)
    if len(topos) < 2 or len(fundos) < 2:
        return "lateral"
    topo_sobe = topos[-1][1] > topos[-2][1]
    fundo_sobe = fundos[-1][1] > fundos[-2][1]
    if topo_sobe and fundo_sobe:
        return "alta"
    if not topo_sobe and not fundo_sobe:
        return "baixa"
    return "lateral"


def divergencia_rsi(df: pd.DataFrame, janela: int = 3, ultimas: int = 40) -> str | None:
    """Divergência entre preço e RSI nos dois últimos pivôs recentes."""
    topos, fundos = pivos(df, janela)
    limite = len(df) - ultimas
    topos = [p for p in topos if p[2] >= limite]
    fundos = [p for p in fundos if p[2] >= limite]
    r = df["rsi"].to_numpy()
    if len(topos) >= 2:
        (_, p1, i1), (_, p2, i2) = topos[-2], topos[-1]
        if p2 > p1 and r[i2] < r[i1] - 2:
            return "baixista"
    if len(fundos) >= 2:
        (_, p1, i1), (_, p2, i2) = fundos[-2], fundos[-1]
        if p2 < p1 and r[i2] > r[i1] + 2:
            return "altista"
    return None


# --------------------------------------------------- suportes e resistências
@dataclass
class Nivel:
    preco: float
    toques: int
    fontes: str  # timeframes que formaram o nível, ex.: "1d,4h"

    @property
    def forca(self) -> str:
        return "forte" if self.toques >= 3 else "média" if self.toques == 2 else "fraca"


def niveis(quadros: dict[str, pd.DataFrame], tolerancia: float) -> list[Nivel]:
    """Agrupa pivôs de vários timeframes em zonas de preço.

    `tolerancia` é a distância máxima (em preço) para dois pivôs contarem como o mesmo nível;
    normalmente uma fração do ATR diário.
    """
    janelas = {"1w": 2, "1d": 3, "4h": 5}
    pontos = []
    for tf, df in quadros.items():
        topos, fundos = pivos(df, janelas.get(tf, 3))
        pontos += [(p, tf) for _, p, _ in topos + fundos]
    pontos.sort()
    grupos: list[list[tuple[float, str]]] = []
    for p in pontos:
        if grupos and p[0] - grupos[-1][-1][0] <= tolerancia:
            grupos[-1].append(p)
        else:
            grupos.append([p])
    return [Nivel(preco=float(np.mean([x[0] for x in g])), toques=len(g),
                  fontes=",".join(sorted({x[1] for x in g})))
            for g in grupos]
