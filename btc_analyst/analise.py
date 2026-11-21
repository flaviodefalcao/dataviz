"""Os cinco pilares da análise. Cada um gera uma nota de -100 (baixista) a +100 (altista)
e uma lista de sinais explicando de onde a nota veio."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import indicadores as ind

PESOS = {"Tendência": 30, "Técnico": 25, "Macro": 20, "Sentimento e índices": 15, "Notícias": 10}


@dataclass
class Pilar:
    nome: str
    score: float = 0.0
    sinais: list[tuple[str, float]] = field(default_factory=list)
    disponivel: bool = True
    erro: str = ""
    dados: dict = field(default_factory=dict)

    @property
    def peso(self) -> int:
        return PESOS[self.nome]

    def add(self, texto: str, pontos: float = 0.0):
        self.sinais.append((texto, pontos))

    def fechar(self, escala: float = 1.0) -> "Pilar":
        self.score = float(np.clip(sum(p for _, p in self.sinais) * escala, -100, 100))
        return self


def indisponivel(nome: str, erro: Exception | str) -> Pilar:
    return Pilar(nome, disponivel=False, erro=str(erro)[:200])


def _fmt(v: float) -> str:
    return f"{v:,.0f}".replace(",", ".")


def _pct(a: float, b: float) -> float:
    return (a / b - 1) * 100


# ------------------------------------------------------------- tendência
def tendencia(quadros: dict[str, pd.DataFrame]) -> Pilar:
    """Semanal, diário e 4h: posição contra as médias, inclinação, estrutura e força (ADX)."""
    pilar = Pilar("Tendência")
    pesos_tf = {"1w": 0.30, "1d": 0.45, "4h": 0.25}
    nomes = {"1w": "Semanal", "1d": "Diário", "4h": "4h"}
    total = 0.0
    for tf, peso in pesos_tf.items():
        df = quadros[tf]
        u = df.iloc[-1]
        pts = []
        if len(df) >= 200:
            pts.append(("acima da EMA200" if u.close > u.ema200 else "abaixo da EMA200",
                        25 if u.close > u.ema200 else -25))
        pts.append(("acima da EMA50" if u.close > u.ema50 else "abaixo da EMA50",
                    15 if u.close > u.ema50 else -15))
        pts.append(("EMA20 > EMA50" if u.ema20 > u.ema50 else "EMA20 < EMA50",
                    15 if u.ema20 > u.ema50 else -15))
        inclinacao = df["ema50"].iloc[-1] - df["ema50"].iloc[-10]
        pts.append(("EMA50 subindo" if inclinacao > 0 else "EMA50 caindo", 10 if inclinacao > 0 else -10))
        est = ind.estrutura(df, 2 if tf == "1w" else 3)
        pts.append((f"estrutura de {est}", {"alta": 20, "baixa": -20, "lateral": 0}[est]))
        bruto = sum(p for _, p in pts)
        maximo = sum(abs(p) for _, p in pts) or 1
        lado = "de alta" if u.di_mais > u.di_menos else "de baixa"
        forca = (f"tendência forte {lado}" if u.adx >= 25 else "sem tendência definida" if u.adx < 20
                 else f"tendência moderada {lado}")
        fator = 1.0 if u.adx >= 20 else 0.7  # ADX baixo = mercado sem direção: reduz a convicção
        nota = bruto / maximo * 100 * fator
        total += nota * peso
        descricao = ", ".join(t for t, _ in pts)
        pilar.add(f"{nomes[tf]}: {descricao}; ADX {u.adx:.0f} ({forca})", round(nota * peso, 1))
        pilar.dados[tf] = {"nota": nota, "estrutura": est, "adx": float(u.adx)}
    return pilar.fechar()


# --------------------------------------------------------------- técnico
def tecnico(quadros: dict[str, pd.DataFrame]) -> Pilar:
    pilar = Pilar("Técnico")
    d, h4 = quadros["1d"], quadros["4h"]
    u, u4 = d.iloc[-1], h4.iloc[-1]

    # RSI
    if u.rsi >= 70:
        pilar.add(f"RSI diário {u.rsi:.0f}: sobrecomprado, risco de correção", -15)
    elif u.rsi >= 50:
        pilar.add(f"RSI diário {u.rsi:.0f}: momento comprador saudável", 15)
    elif u.rsi > 30:
        pilar.add(f"RSI diário {u.rsi:.0f}: momento vendedor", -10)
    else:
        pilar.add(f"RSI diário {u.rsi:.0f}: sobrevendido, possível repique", 15)
    if u4.rsi >= 70:
        pilar.add(f"RSI 4h {u4.rsi:.0f}: sobrecomprado no curto prazo (espere recuo para entrar)", -10)
    elif u4.rsi <= 30:
        pilar.add(f"RSI 4h {u4.rsi:.0f}: sobrevendido no curto prazo", 10)

    # MACD
    hist, hist_ant = d["macd_hist"].iloc[-1], d["macd_hist"].iloc[-2]
    pilar.add("MACD diário positivo" if hist > 0 else "MACD diário negativo", 15 if hist > 0 else -15)
    pilar.add("histograma do MACD diário ganhando força" if hist > hist_ant
              else "histograma do MACD diário perdendo força", 10 if hist > hist_ant else -10)
    h4h = h4["macd_hist"].iloc[-1]
    pilar.add("MACD 4h positivo" if h4h > 0 else "MACD 4h negativo", 10 if h4h > 0 else -10)

    # Bollinger e distância da média
    if u.bb_pct > 1:
        pilar.add("preço acima da banda de Bollinger superior (esticado)", -10)
    elif u.bb_pct < 0:
        pilar.add("preço abaixo da banda de Bollinger inferior (esticado para baixo)", 10)
    dist = (u.close - u.ema20) / u.atr
    if dist > 2.5:
        pilar.add(f"preço {dist:.1f} ATRs acima da EMA20 diária: esticado, espere recuo", -10)
    elif dist < -2.5:
        pilar.add(f"preço {abs(dist):.1f} ATRs abaixo da EMA20 diária: esticado para baixo", 10)

    # Volume confirmando o movimento dos últimos 5 dias
    var5 = _pct(d["close"].iloc[-1], d["close"].iloc[-6])
    vol = d["volume"].iloc[-5:].mean() / d["vol_media20"].iloc[-1]
    if vol > 1.2:
        pilar.add(f"volume {vol:.1f}x a média confirmando {'alta' if var5 > 0 else 'queda'} de {var5:+.1f}% em 5 dias",
                  10 if var5 > 0 else -10)
    obv_sobe = d["obv"].iloc[-1] > d["obv"].iloc[-20]
    pilar.add("OBV subindo em 20 dias (acumulação)" if obv_sobe else "OBV caindo em 20 dias (distribuição)",
              5 if obv_sobe else -5)

    # Divergências
    for tf, df in (("diário", d), ("4h", h4)):
        div = ind.divergencia_rsi(df)
        if div:
            pilar.add(f"divergência {div} de RSI no {tf}", 20 if div == "altista" else -20)

    pilar.dados = {"rsi_1d": float(u.rsi), "rsi_4h": float(u4.rsi), "atr_1d": float(u.atr),
                   "atr_4h": float(u4.atr)}
    return pilar.fechar()


# ----------------------------------------------------------------- macro
def macro(series: dict[str, pd.Series], btc_diario: pd.DataFrame) -> Pilar:
    pilar = Pilar("Macro")

    def var20(s):
        return _pct(s.iloc[-1], s.iloc[-21]) if len(s) > 21 else 0.0

    if "DXY" in series:
        v = var20(series["DXY"])
        pts = 20 if v < -1 else -20 if v > 1 else round(-v * 15)
        pilar.add(f"Dólar (DXY) {series['DXY'].iloc[-1]:.1f}, {v:+.1f}% em 20 dias "
                  f"({'dólar fraco favorece o BTC' if v < 0 else 'dólar forte pesa no BTC'})", pts)
    if "US10Y" in series:
        s = series["US10Y"]
        bps = (s.iloc[-1] - s.iloc[-21]) * 100 if len(s) > 21 else 0
        pts = 15 if bps < -15 else -15 if bps > 15 else round(-bps / 2)
        pilar.add(f"Juros de 10 anos dos EUA {s.iloc[-1]:.2f}%, {bps:+.0f} pontos-base em 20 dias", pts)
    if "Nasdaq" in series:
        s = series["Nasdaq"]
        acima = s.iloc[-1] > s.rolling(50).mean().iloc[-1]
        v = var20(s)
        pilar.add(f"Nasdaq {'acima' if acima else 'abaixo'} da média de 50 dias, {v:+.1f}% em 20 dias",
                  (15 if acima else -15) + (10 if v > 3 else -10 if v < -3 else 0))
    if "VIX" in series:
        vix = series["VIX"].iloc[-1]
        pts = 10 if vix < 16 else 0 if vix < 22 else -10 if vix < 30 else -20
        humor = ("calmo" if vix < 16 else "normal" if vix < 22 else "tenso" if vix < 30 else "em pânico")
        pilar.add(f"VIX {vix:.1f}: mercado {humor}", pts)
    if "Ouro" in series:
        pilar.add(f"Ouro {var20(series['Ouro']):+.1f}% em 20 dias (informativo)", 0)

    # Correlação do BTC com a bolsa: indica o quanto o macro está mandando
    if "Nasdaq" in series:
        btc = btc_diario["close"].copy()
        btc.index = btc.index.normalize()
        nq = series["Nasdaq"].copy()
        nq.index = nq.index.normalize()
        juntos = pd.concat([btc.pct_change(), nq.pct_change()], axis=1, join="inner").dropna().iloc[-60:]
        if len(juntos) > 20:
            corr = juntos.corr().iloc[0, 1]
            pilar.dados["correlacao_nasdaq_60d"] = float(corr)
            pilar.add(f"Correlação BTC × Nasdaq (60 dias): {corr:+.2f}"
                      + (" (BTC andando junto com a bolsa)" if corr > 0.5 else ""), 0)
    pilar.dados.update({k: float(v.iloc[-1]) for k, v in series.items()})
    return pilar.fechar(escala=1.25)


# --------------------------------------------------- sentimento e índices
def sentimento(fg: dict | None, deriv: dict | None, glob: dict | None,
               btc_diario: pd.DataFrame) -> Pilar:
    """Leitura contrária: multidão eufórica e alavancada comprada é risco, medo é oportunidade."""
    pilar = Pilar("Sentimento e índices")
    if not any((fg, deriv, glob)):
        raise RuntimeError("Nenhum índice disponível")

    if fg:
        v = fg["valor"]
        pts = 25 if v <= 20 else 10 if v <= 40 else 0 if v <= 60 else -10 if v < 80 else -25
        pilar.add(f"Fear & Greed {v} ({fg['classificacao']}), média 7d {fg['media_7d']:.0f}, "
                  f"há 30 dias {fg['valor_30d_atras']} (leitura contrária)", pts)
    if deriv:
        f = deriv["funding_atual"] * 100
        pts = -20 if f > 0.05 else -10 if f > 0.02 else 25 if f < -0.02 else 15 if f < 0 else 0
        pilar.add(f"Funding dos perpétuos {f:+.4f}% a cada 8h (média 7d {deriv['funding_media_7d']*100:+.4f}%)"
                  + (": comprados alavancados pagando caro" if f > 0.02 else
                     ": vendidos pagando, combustível para short squeeze" if f < 0 else ""), pts)
        if deriv.get("oi_var_7d") is not None:
            oi = deriv["oi_var_7d"] * 100
            preco = _pct(btc_diario["close"].iloc[-1], btc_diario["close"].iloc[-8])
            if oi > 5 and preco > 0:
                txt, pts = "dinheiro novo entrando na alta", 10
            elif oi > 5 and preco <= 0:
                txt, pts = "posições novas apostando na queda", -10
            elif oi < -5 and preco > 0:
                txt, pts = "alta puxada por fechamento de vendidos (menos sustentável)", 0
            elif oi < -5:
                txt, pts = "desalavancagem: limpeza de posições", 5
            else:
                txt, pts = "sem mudança relevante", 0
            pilar.add(f"Open interest {oi:+.1f}% em 7 dias com preço {preco:+.1f}%: {txt}", pts)
        if deriv.get("ls_top"):
            r = deriv["ls_top"]
            pts = -10 if r > 2 else 10 if r < 0.8 else 0
            pilar.add(f"Razão long/short dos maiores traders {r:.2f}", pts)
    if glob:
        pilar.add(f"Dominância do BTC {glob['dominancia_btc']:.1f}%, mercado cripto "
                  f"{glob['var_mcap_24h']:+.1f}% em 24h (informativo)", 0)
    pilar.dados = {"fear_greed": fg, "derivativos": deriv, "global": glob}
    return pilar.fechar()


# ---------------------------------------------------------------- notícias
_POSITIVAS = [
    r"approv", r"inflow", r"rall(y|ies)", r"surg", r"record high", r"all[- ]time high", r"\bath\b",
    r"bullish", r"adopt", r"accumulat", r"rate cut", r"cuts? rates", r"dovish", r"easing",
    r"strategic (bitcoin )?reserve", r"buys?\b", r"purchas", r"breakout", r"soar", r"jump",
    r"recovers?", r"rebound", r"gains?\b", r"alta\b", r"recorde", r"aprova",
]
_NEGATIVAS = [
    r"hack", r"exploit", r"\bban", r"crash", r"plung", r"outflow", r"bearish", r"sell-?off",
    r"liquidat", r"lawsuit", r"\bsues?\b", r"charges?\b", r"rate hike", r"hawkish", r"fraud",
    r"bankrupt", r"dump", r"tariff", r"slump", r"tumbl", r"drops?\b", r"falls?\b", r"sinks?",
    r"selling pressure", r"recession", r"queda", r"proib",
]
_RELEVANTES = r"bitcoin|\bbtc\b|crypto|etf|fed\b|fomc|powell|inflation|cpi|treasury|dollar|stablecoin|saylor|strategy|blackrock|sec\b"
EVENTOS = {
    r"fomc|fed (meeting|decision)|powell|interest rate decision": "reunião/fala do Fed",
    r"\bcpi\b|inflation (data|report)|\bpce\b": "dado de inflação",
    r"payrolls?|jobs report|nonfarm|unemployment": "relatório de emprego",
    r"options expir|expiry": "vencimento de opções",
}


def _conta(padroes, texto):
    return sum(1 for p in padroes if re.search(p, texto))


def noticias(itens: list[dict]) -> Pilar:
    pilar = Pilar("Notícias")
    relevantes, pos_total, neg_total, eventos = [], 0, 0, set()
    for n in itens:
        t = n["titulo"].lower()
        if not re.search(_RELEVANTES, t):
            continue
        p, q = _conta(_POSITIVAS, t), _conta(_NEGATIVAS, t)
        pos_total += p
        neg_total += q
        tom = "positiva" if p > q else "negativa" if q > p else "neutra"
        relevantes.append({**n, "tom": tom})
        for padrao, nome in EVENTOS.items():
            if re.search(padrao, t):
                eventos.add(nome)
    if not relevantes:
        pilar.add("nenhuma manchete relevante nas últimas 72h", 0)
        return pilar.fechar()
    # suavizado: poucas manchetes não geram nota extrema
    nota = 100 * (pos_total - neg_total) / (pos_total + neg_total + 3)
    pilar.add(f"{len(relevantes)} manchetes relevantes: {pos_total} termos positivos, {neg_total} negativos", nota)
    for e in sorted(eventos):
        pilar.add(f"evento de volatilidade no radar: {e}", 0)
    pilar.dados = {"manchetes": relevantes[:15], "eventos": sorted(eventos)}
    return pilar.fechar()


# ---------------------------------------------------------------- consolidação
def consolidar(pilares: list[Pilar]) -> dict:
    ativos = [p for p in pilares if p.disponivel]
    peso_total = sum(p.peso for p in ativos) or 1
    nota = sum(p.score * p.peso for p in ativos) / peso_total
    concordam = sum(1 for p in ativos if np.sign(p.score) == np.sign(nota) and abs(p.score) >= 10)
    if nota >= 35:
        vies, direcao = "ALTA FORTE", "long"
    elif nota >= 15:
        vies, direcao = "ALTA", "long"
    elif nota > -15:
        vies, direcao = "NEUTRO", None
    elif nota > -35:
        vies, direcao = "BAIXA", "short"
    else:
        vies, direcao = "BAIXA FORTE", "short"
    return {
        "nota": float(nota),
        "vies": vies,
        "direcao": direcao,
        "confluencia": f"{concordam}/{len(ativos)} pilares concordam",
        "cobertura": f"{len(ativos)}/{len(pilares)} pilares com dados",
    }
