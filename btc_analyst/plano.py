"""Plano de swing trade: entrada, stop técnico, alvos com ganho/perda mínimo e tamanho da posição.

Regra central: um plano só é válido se o alvo ficar a pelo menos `rr_min` vezes o risco
(já descontadas as taxas) E não houver resistência relevante (suporte, no short) no
caminho até esse alvo. Se houver, o plano diz qual seria a entrada máxima que torna o
trade 2:1, para você deixar uma ordem limite lá em vez de entrar mal.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd

from .indicadores import Nivel


@dataclass
class Config:
    capital: float = 10_000.0        # em USDT
    risco_pct: float = 1.0           # % do capital arriscado por trade
    rr_min: float = 2.0              # ganho/perda mínimo
    taxa: float = 0.001              # taxa por lado (0,1% = taxa padrão spot da Binance)
    alavancagem_max: float = 1.0     # 1 = sem alavancagem (spot)
    stop_max_pct: float = 10.0       # recusa trades com stop mais longe que isso


@dataclass
class Plano:
    tipo: str
    direcao: str                     # "long" ou "short"
    entrada: float
    stop: float
    alvo1: float = 0.0
    alvo2: float = 0.0
    rr1: float = 0.0
    rr2: float = 0.0
    quantidade: float = 0.0
    valor_posicao: float = 0.0
    risco_usd: float = 0.0
    ganho_alvo1_usd: float = 0.0
    valido: bool = True
    motivo: str = ""
    entrada_max_2r: float | None = None
    avisos: list[str] = field(default_factory=list)

    @property
    def stop_pct(self) -> float:
        return abs(self.entrada - self.stop) / self.entrada * 100


def _n(v: float) -> str:
    return f"{v:,.0f}".replace(",", ".")


def _niveis_lado(niveis: list[Nivel], preco: float, s: int, folga: float):
    """s=+1 (long): suportes abaixo e resistências acima. s=-1 (short): o inverso."""
    a_favor = sorted((n for n in niveis if s * (preco - n.preco) > folga),
                     key=lambda n: s * (preco - n.preco))            # mais próximos primeiro
    contra = sorted((n for n in niveis if s * (n.preco - preco) > folga),
                    key=lambda n: s * (n.preco - preco))
    return a_favor, contra


def _montar(tipo: str, s: int, entrada: float, base_stop: Nivel | None,
            contra: list[Nivel], atr4: float, cfg: Config, risco_usd: float) -> Plano:
    direcao = "long" if s == 1 else "short"

    # Stop: além do nível que protege o trade, com folga de meio ATR (4h) contra violinadas
    if base_stop is not None:
        stop = base_stop.preco - s * 0.5 * atr4
    else:
        stop = entrada - s * 2 * atr4
    if s * (entrada - stop) < atr4:            # stop apertado demais é stopado pelo ruído
        stop = entrada - s * atr4
    entrada, stop = round(entrada, 1), round(stop, 1)   # passo de preço do BTCUSDT é 0,01
    plano = Plano(tipo, direcao, entrada, stop)
    risco = abs(entrada - stop)
    custo = entrada * cfg.taxa * 2             # entrada + saída
    risco_ef = risco + custo

    if plano.stop_pct > cfg.stop_max_pct:
        plano.valido = False
        plano.motivo = f"stop a {plano.stop_pct:.1f}%, acima do máximo de {cfg.stop_max_pct:.0f}%"
        return plano

    # Alvo mínimo para render rr_min já descontando taxas
    alvo_min = entrada + s * (cfg.rr_min * risco_ef + custo)
    obstaculos = [n for n in contra
                  if s * (n.preco - entrada) > 0 and s * (alvo_min - n.preco) > 0]
    relevantes = [n for n in obstaculos if n.toques >= 2]
    fracos = [n for n in obstaculos if n.toques < 2]
    if fracos:
        plano.avisos.append("nível fraco no caminho em " + ", ".join(_n(n.preco) for n in fracos)
                            + ": considere parcial ali")
    if relevantes:
        o = relevantes[0]
        limite = o.preco - s * 0.1 * atr4
        # maior entrada (menor, no short) que deixa o obstáculo a rr_min do stop, com taxas:
        # limite - e >= rr*(e - stop + c) + c, com c = 2*taxa*e
        rr, t2 = cfg.rr_min, 2 * cfg.taxa
        plano.entrada_max_2r = round((limite + rr * stop) / (1 + rr + s * (rr + 1) * t2), 1)
        plano.valido = False
        nome = "resistência" if s == 1 else "suporte"
        plano.motivo = (f"{nome} {o.forca} ({o.toques} toques) em {_n(o.preco)} antes do alvo "
                        f"{cfg.rr_min:g}:1 ({_n(alvo_min)})")
        return plano

    # arredonda sempre para o lado que mantém o ganho/perda >= rr_min
    plano.alvo1 = (math.ceil if s == 1 else math.floor)(alvo_min * 10) / 10
    seguintes = [n for n in contra if s * (n.preco - alvo_min) > risco / 2 and n.toques >= 2]
    if seguintes and s * (seguintes[0].preco - entrada) <= 5 * risco:
        plano.alvo2 = round(seguintes[0].preco - s * 0.1 * atr4, 1)
    else:
        plano.alvo2 = round(max(abs(alvo_min - entrada) + risco, 3 * risco) * s + entrada, 1)
    plano.rr1 = (abs(plano.alvo1 - entrada) - custo) / risco_ef
    plano.rr2 = (abs(plano.alvo2 - entrada) - custo) / risco_ef

    # Tamanho da posição pelo risco, limitado pelo capital/alavancagem
    qtd = risco_usd / risco_ef
    teto = cfg.capital * cfg.alavancagem_max / entrada
    if qtd > teto:
        plano.avisos.append(f"posição limitada pelo capital (alavancagem máx. {cfg.alavancagem_max:g}x): "
                            f"risco real menor que o planejado")
        qtd = teto
    qtd = math.floor(qtd * 1e5) / 1e5          # passo de quantidade do BTCUSDT: 0,00001
    plano.quantidade = qtd
    plano.valor_posicao = round(qtd * entrada, 2)
    plano.risco_usd = round(qtd * risco_ef, 2)
    plano.ganho_alvo1_usd = round(qtd * (abs(plano.alvo1 - entrada) - custo), 2)
    if s == -1:
        plano.avisos.append("short exige conta de futuros ou margem")
    return plano


def gerar(direcao: str | None, quadros: dict[str, pd.DataFrame], niveis: list[Nivel],
          cfg: Config, evento_no_radar: bool = False, preco: float | None = None) -> list[Plano]:
    preco = float(quadros["4h"]["close"].iloc[-1]) if preco is None else preco
    atr4 = float(quadros["4h"]["atr"].iloc[-1])
    atr1 = float(quadros["1d"]["atr"].iloc[-1])
    risco_usd = cfg.capital * cfg.risco_pct / 100
    if evento_no_radar:
        risco_usd /= 2

    lados = [1] if direcao == "long" else [-1] if direcao == "short" else [1, -1]
    planos = []
    for s in lados:
        a_favor, contra = _niveis_lado(niveis, preco, s, 0.2 * atr4)

        # 1) Entrada a mercado, stop além do nível mais próximo a favor
        protecao = next((n for n in a_favor if abs(preco - n.preco) >= 0.5 * atr4), None)
        p = _montar("A mercado", s, preco, protecao, contra, atr4, cfg, risco_usd)
        rsi4 = float(quadros["4h"]["rsi"].iloc[-1])
        if (s == 1 and rsi4 > 70) or (s == -1 and rsi4 < 30):
            p.avisos.append(f"RSI 4h em {rsi4:.0f}: entrada a mercado agora é perseguir preço")
        planos.append(p)

        # 2) Pullback: ordem limite no nível médio/forte mais próximo, até 4 ATRs diários
        zona = next((n for n in a_favor if n.toques >= 2 and abs(preco - n.preco) <= 4 * atr1), None)
        if zona is not None:
            entrada = zona.preco + s * 0.15 * atr4       # um pouco antes do nível para ser executado
            abaixo = [n for n in a_favor if s * (zona.preco - n.preco) > 0.5 * atr4]
            # stop além do próprio nível da entrada; se houver outro muito perto, além dele
            protecao = zona if not abaixo or s * (zona.preco - abaixo[0].preco) > atr4 else abaixo[0]
            _, contra_pb = _niveis_lado(niveis, entrada, s, 0.2 * atr4)
            planos.append(_montar(f"Pullback (ordem limite em nível {zona.forca})", s, entrada,
                                  protecao, contra_pb, atr4, cfg, risco_usd))

        # 3) Se algum plano falhou por obstáculo, propõe a ordem limite que torna o trade rr_min:1
        for p in [x for x in planos if x.entrada_max_2r and x.direcao == ("long" if s == 1 else "short")]:
            e = p.entrada_max_2r
            if s * (preco - e) <= 0 or s * (e - p.stop) < atr4 or any(abs(x.entrada - e) < 0.2 * atr4 for x in planos):
                continue
            base = next((n for n in a_favor if abs(n.preco - (p.stop + s * 0.5 * atr4)) < 1), None)
            _, contra_e = _niveis_lado(niveis, e, s, 0.2 * atr4)
            novo = _montar(f"Ordem limite para {cfg.rr_min:g}:1", s, e, base, contra_e, atr4, cfg, risco_usd)
            if novo.valido:
                novo.avisos.insert(0, f"só vale se o preço recuar até {_n(e)}; o stop técnico fica onde está")
                planos.append(novo)

    if direcao is None:
        for p in planos:
            p.avisos.insert(0, "viés neutro: plano apenas condicional, não é recomendação de entrada")
    if evento_no_radar:
        for p in planos:
            p.avisos.append("evento macro no radar: risco reduzido pela metade")
    return planos


GESTAO = [
    "Arrisque no máximo {risco:g}% do capital por trade e tenha no máximo 2 trades abertos.",
    "Coloque o stop junto com a entrada (ordem OCO na Binance) e nunca o afaste.",
    "No alvo 1 ({rr:g}:1) realize 50% e mova o stop do restante para o preço de entrada.",
    "Conduza o restante até o alvo 2 ou feche se o 4h fechar do lado errado da EMA20.",
    "Ordem limite de pullback não executada em 5 dias: cancele e refaça a análise.",
    "Trade aberto há mais de 15 dias sem atingir o alvo 1: reavalie e considere sair.",
    "Depois de 3 stops seguidos, pare uma semana e revise o processo.",
]
