"""Saída do analista: relatório no terminal, JSON e página HTML com gráfico interativo."""
from __future__ import annotations

import html
import json
from dataclasses import asdict
from datetime import datetime

import pandas as pd

from .analise import Pilar
from .plano import GESTAO, Config, Plano


def _n(v: float, casas: int = 0) -> str:
    return f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _sinal_entrada(p: Plano) -> str:
    return "máxima" if p.direcao == "long" else "mínima"


# ------------------------------------------------------------ recomendação
def recomendacao(r: dict) -> tuple[str, list[str]]:
    """Resumo em linguagem direta do que fazer agora: (título, itens)."""
    c = r["consolidado"]
    validos = [p for p in r["planos"] if p.valido]
    mercado = next((p for p in validos if p.tipo == "A mercado"), None)
    limites = [p for p in validos if p.tipo != "A mercado"]
    itens: list[str] = []

    def desc(p: Plano) -> str:
        return (f"stop {_n(p.stop)}, alvo 1 {_n(p.alvo1)} ({p.rr1:.1f}:1), alvo 2 {_n(p.alvo2)}, "
                f"{p.quantidade:.5f} BTC (risco {_n(p.risco_usd, 2)} USDT)")

    if c["direcao"] is None:
        titulo = "Fique de fora: os sinais estão divididos"
        itens.append("Nenhum lado tem vantagem clara. Os planos abaixo só valem se o preço chegar aos níveis.")
    elif mercado:
        lado = "Comprar" if mercado.direcao == "long" else "Vender"
        titulo = f"{lado} agora a {_n(mercado.entrada)}"
        itens.append(f"Entrada a mercado com {desc(mercado)}. Envie a entrada e o stop juntos (OCO).")
    elif limites:
        p = limites[0]
        lado = "compra" if p.direcao == "long" else "venda"
        titulo = f"Não entre agora: deixe ordem limite de {lado} em {_n(p.entrada)}"
        itens.append(f"Ordem limite com {desc(p)}. Se não executar em 5 dias, cancele e rode a análise de novo.")
        for extra in limites[1:]:
            itens.append(f"Alternativa: ordem limite em {_n(extra.entrada)} ({extra.tipo.lower()}).")
    else:
        titulo = "Fique de fora: nenhum trade com 2:1 agora"
        for p in r["planos"]:
            if p.entrada_max_2r:
                itens.append(f"Só ficaria 2:1 com entrada em {_n(p.entrada_max_2r)} e stop em {_n(p.stop)}.")

    if any(p.direcao == "short" for p in validos):
        itens.append("Venda exige conta de futuros ou margem. Se você só opera spot, a recomendação é aguardar.")

    # Alertas de contexto contra a direção do trade
    tec = next((p for p in r["pilares"] if p.nome == "Técnico" and p.disponivel), None)
    sent = next((p for p in r["pilares"] if p.nome == "Sentimento e índices" and p.disponivel), None)
    rsi = tec.dados.get("rsi_1d") if tec else None
    fg = (sent.dados.get("fear_greed") or {}).get("valor") if sent else None
    if c["direcao"] == "short" and ((rsi is not None and rsi < 25) or (fg is not None and fg <= 20)):
        itens.append("Cuidado: mercado sobrevendido e em medo extremo. Repiques fortes são comuns; "
                     "não venda depois de quedas grandes, espere o repique até a resistência.")
    if c["direcao"] == "long" and ((rsi is not None and rsi > 75) or (fg is not None and fg >= 80)):
        itens.append("Cuidado: mercado sobrecomprado e em euforia. Não compre depois de altas grandes, "
                     "espere o recuo até o suporte.")
    noticias = next((p for p in r["pilares"] if p.nome == "Notícias" and p.disponivel), None)
    if noticias and noticias.dados.get("eventos"):
        itens.append("Evento macro no radar (" + ", ".join(noticias.dados["eventos"])
                     + "): o risco por trade já foi reduzido pela metade.")
    return titulo, itens


# ---------------------------------------------------------------- terminal
def texto(r: dict) -> str:
    c, cfg = r["consolidado"], r["config"]
    linhas = [
        "=" * 72,
        f"  ANALISTA BTC  |  {r['gerado_em']}  |  preço {_n(r['preco'])} USDT",
        "=" * 72,
    ]
    if r.get("demo"):
        linhas.append("  ** DADOS SIMULADOS (modo --demo): não use para operar **")
    linhas += [f"  VIÉS: {c['vies']}  (nota {c['nota']:+.0f} de -100 a +100; {c['confluencia']}; "
               f"{c['cobertura']})", ""]
    titulo, itens = recomendacao(r)
    linhas += [f"RECOMENDAÇÃO: {titulo}"] + [f"   > {i}" for i in itens] + [""]
    for p in r["pilares"]:
        if not p.disponivel:
            linhas.append(f"[{p.nome}]  indisponível: {p.erro}")
            continue
        linhas.append(f"[{p.nome}]  nota {p.score:+.0f}  (peso {p.peso}%)")
        for t, pts in p.sinais:
            marca = "+" if pts > 0 else "-" if pts < 0 else "·"
            linhas.append(f"   {marca} {t}")
        linhas.append("")

    linhas.append("NÍVEIS-CHAVE")
    for nome, lista in (("Resistências", r["resistencias"]), ("Suportes", r["suportes"])):
        linhas.append(f"   {nome}: " + ("; ".join(f"{_n(n.preco)} ({n.forca})" for n in lista) or "nenhum"))
    linhas.append("")

    linhas.append(f"PLANOS (capital {_n(cfg.capital)} USDT, risco {cfg.risco_pct:g}%, "
                  f"ganho/perda mínimo {cfg.rr_min:g}:1)")
    for p in r["planos"]:
        cab = f"   {p.direcao.upper()} | {p.tipo}"
        if not p.valido:
            linhas.append(f"{cab}  ->  NÃO OPERAR: {p.motivo}")
            if p.entrada_max_2r:
                linhas.append(f"      entrada {_sinal_entrada(p)} para {cfg.rr_min:g}:1 com stop em "
                              f"{_n(p.stop)}: {_n(p.entrada_max_2r)}")
            continue
        linhas += [
            f"{cab}  ->  VÁLIDO",
            f"      entrada {_n(p.entrada)} | stop {_n(p.stop)} ({p.stop_pct:.1f}%)",
            f"      alvo 1 {_n(p.alvo1)} ({p.rr1:.1f}:1) | alvo 2 {_n(p.alvo2)} ({p.rr2:.1f}:1)",
            f"      quantidade {p.quantidade:.5f} BTC ({_n(p.valor_posicao)} USDT) | "
            f"risco {_n(p.risco_usd, 2)} | ganho no alvo 1 {_n(p.ganho_alvo1_usd, 2)} USDT",
        ]
        linhas += [f"      ! {a}" for a in p.avisos]
    linhas.append("")
    linhas.append("GESTÃO DO TRADE")
    linhas += [f"   {i}. {g.format(risco=cfg.risco_pct, rr=cfg.rr_min)}" for i, g in enumerate(GESTAO, 1)]
    linhas += ["", "Análise automática e educativa, não é recomendação de investimento.", ""]
    return "\n".join(linhas)


# -------------------------------------------------------------------- JSON
def para_json(r: dict) -> str:
    def conv(o):
        if isinstance(o, (datetime, pd.Timestamp)):
            return o.isoformat()
        if isinstance(o, Config):
            return asdict(o)
        if hasattr(o, "__dataclass_fields__"):
            return asdict(o)
        return str(o)
    saida = {k: v for k, v in r.items() if k not in ("quadros", "graficos")}
    saida["pilares"] = [asdict(p) | {"peso": p.peso} for p in r["pilares"]]
    return json.dumps(saida, default=conv, ensure_ascii=False, indent=2)


# -------------------------------------------------------------------- HTML
def _serie_grafico(df: pd.DataFrame, n: int) -> dict:
    df = df.iloc[-n:]
    t = [int(x.timestamp()) for x in df.index]
    def linha(col):
        return [{"time": a, "value": round(float(v), 2)} for a, v in zip(t, df[col]) if pd.notna(v)]
    return {
        "candles": [{"time": a, "open": o, "high": h, "low": l, "close": c}
                    for a, o, h, l, c in zip(t, df["open"].round(2), df["high"].round(2),
                                             df["low"].round(2), df["close"].round(2))],
        "ema20": linha("ema20"), "ema50": linha("ema50"), "ema200": linha("ema200"),
        "rsi": linha("rsi"),
    }


def _esc(v) -> str:
    return html.escape(str(v), quote=True)


def _cartao_plano(p: Plano, cfg: Config) -> str:
    titulo = f"{'Compra' if p.direcao == 'long' else 'Venda'} · {_esc(p.tipo)}"
    if not p.valido:
        extra = ""
        if p.entrada_max_2r:
            extra = (f"<p>Entrada {_sinal_entrada(p)} para {cfg.rr_min:g}:1 com stop em {_n(p.stop)}: "
                     f"<strong>{_n(p.entrada_max_2r)}</strong></p>")
        return (f'<article class="plano invalido"><header><h3>{titulo}</h3>'
                f'<span class="selo selo-ruim">✕ Não operar</span></header>'
                f"<p>{_esc(p.motivo)}</p>{extra}</article>")
    avisos = "".join(f"<li>{_esc(a)}</li>" for a in p.avisos)
    return f"""<article class="plano">
  <header><h3>{titulo}</h3><span class="selo selo-bom">✓ Válido</span></header>
  <dl class="grade">
    <div><dt>Entrada</dt><dd>{_n(p.entrada)}</dd></div>
    <div><dt>Stop</dt><dd>{_n(p.stop)} <small>{p.stop_pct:.1f}%</small></dd></div>
    <div><dt>Alvo 1</dt><dd>{_n(p.alvo1)} <small>{p.rr1:.1f}:1</small></dd></div>
    <div><dt>Alvo 2</dt><dd>{_n(p.alvo2)} <small>{p.rr2:.1f}:1</small></dd></div>
    <div><dt>Quantidade</dt><dd>{p.quantidade:.5f} BTC <small>{_n(p.valor_posicao)} USDT</small></dd></div>
    <div><dt>Risco / ganho alvo 1</dt><dd>{_n(p.risco_usd, 2)} / {_n(p.ganho_alvo1_usd, 2)} <small>USDT</small></dd></div>
  </dl>
  {f'<ul class="avisos">{avisos}</ul>' if avisos else ''}
</article>"""


def _barra_pilar(p: Pilar) -> str:
    if not p.disponivel:
        return (f'<div class="pilar"><span class="pilar-nome">{_esc(p.nome)}</span>'
                f'<span class="pilar-off">sem dados</span><span class="pilar-valor">—</span></div>')
    largura = abs(p.score) / 2  # metade da trilha = 100 pontos
    lado = "pos" if p.score >= 0 else "neg"
    estilo = f"left:50%;width:{largura}%" if lado == "pos" else f"right:50%;width:{largura}%"
    return (f'<div class="pilar" title="{_esc(p.nome)}: {p.score:+.0f} (peso {p.peso}%)">'
            f'<span class="pilar-nome">{_esc(p.nome)} <small>{p.peso}%</small></span>'
            f'<span class="trilha"><span class="zero"></span><span class="barra {lado}" style="{estilo}"></span></span>'
            f'<span class="pilar-valor">{p.score:+.0f}</span></div>')


def _detalhes(p: Pilar) -> str:
    if not p.disponivel:
        return f"<details><summary>{_esc(p.nome)}: indisponível</summary><p>{_esc(p.erro)}</p></details>"
    itens = "".join(
        f'<li><span class="pts {"pos" if pts > 0 else "neg" if pts < 0 else ""}">'
        f'{"▲" if pts > 0 else "▼" if pts < 0 else "·"}</span>{_esc(t)}</li>' for t, pts in p.sinais)
    return f"<details><summary>{_esc(p.nome)} <small>{p.score:+.0f}</small></summary><ul class='sinais'>{itens}</ul></details>"


def _noticias(pilares: list[Pilar]) -> str:
    p = next((x for x in pilares if x.nome == "Notícias"), None)
    if not p or not p.disponivel or not p.dados.get("manchetes"):
        return "<p class='mudo'>Sem manchetes disponíveis.</p>"
    linhas = []
    for n in p.dados["manchetes"]:
        link = n.get("link", "")
        titulo = _esc(n["titulo"])
        if link.startswith(("http://", "https://")):
            titulo = f'<a href="{_esc(link)}" target="_blank" rel="noopener noreferrer">{titulo}</a>'
        quando = n["data"].strftime("%d/%m %H:%M") if n.get("data") else ""
        linhas.append(f"<li><span class='tom tom-{n['tom']}'>{n['tom']}</span>{titulo}"
                      f"<small>{_esc(n['fonte'])} · {quando}</small></li>")
    return "<ul class='noticias'>" + "".join(linhas) + "</ul>"


def pagina(r: dict) -> str:
    c, cfg = r["consolidado"], r["config"]
    dados = {
        "4h": _serie_grafico(r["graficos"]["4h"], 240),
        "1d": _serie_grafico(r["graficos"]["1d"], 260),
        "planos": [asdict(p) for p in r["planos"] if p.valido],
    }
    dados_js = json.dumps(dados).replace("</", "<\\/")
    planos = "".join(_cartao_plano(p, cfg) for p in r["planos"])
    barras = "".join(_barra_pilar(p) for p in r["pilares"])
    detalhes = "".join(_detalhes(p) for p in r["pilares"])
    niveis = "".join(
        f"<tr><td>{tipo}</td><td>{_n(n.preco)}</td><td>{n.forca} ({n.toques})</td><td>{_esc(n.fontes)}</td></tr>"
        for tipo, lista in (("Resistência", r["resistencias"]), ("Suporte", r["suportes"])) for n in lista)
    gestao = "".join(f"<li>{_esc(g.format(risco=cfg.risco_pct, rr=cfg.rr_min))}</li>" for g in GESTAO)
    demo = ('<div class="faixa-demo">Dados simulados (modo demo): não use para operar.</div>'
            if r.get("demo") else "")
    rec_titulo, rec_lista = recomendacao(r)
    rec_itens = "".join(f"<li>{_esc(i)}</li>" for i in rec_lista)
    tom_vies = "pos" if c["nota"] >= 15 else "neg" if c["nota"] <= -15 else "neutro"

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Analista BTC</title>
<style>
:root {{
  color-scheme: light;
  --surface-0:#f4f3f0; --surface-1:#fcfcfb; --borda:#e2e1dc;
  --text-primary:#0b0b0b; --text-secondary:#52514e; --text-muted:#76756f;
  --alta:#2a78d6; --baixa:#e34948; --ema20:#eb6834; --ema50:#6250d6; --ema200:#76756f;
  --bom:#0ca30c; --bom-texto:#006300; --ruim:#d03b3b; --neutro:#f0efec; --grade:#ecebe7;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    color-scheme: dark;
    --surface-0:#111110; --surface-1:#1a1a19; --borda:#2e2e2c;
    --text-primary:#f0efec; --text-secondary:#c3c2b7; --text-muted:#8f8e86;
    --alta:#3987e5; --baixa:#e66767; --ema20:#d95926; --ema50:#9085e9; --ema200:#8f8e86;
    --bom:#0ca30c; --bom-texto:#3fc23f; --ruim:#e66767; --neutro:#383835; --grade:#262624;
  }}
}}
:root[data-theme="dark"] {{
  color-scheme: dark;
  --surface-0:#111110; --surface-1:#1a1a19; --borda:#2e2e2c;
  --text-primary:#f0efec; --text-secondary:#c3c2b7; --text-muted:#8f8e86;
  --alta:#3987e5; --baixa:#e66767; --ema20:#d95926; --ema50:#9085e9; --ema200:#8f8e86;
  --bom:#0ca30c; --bom-texto:#3fc23f; --ruim:#e66767; --neutro:#383835; --grade:#262624;
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--surface-0); color:var(--text-primary);
  font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }}
main {{ max-width:1120px; margin:0 auto; padding:24px 16px 48px; }}
h1 {{ font-size:24px; margin:0; }} h2 {{ font-size:17px; margin:0 0 12px; }}
h3 {{ font-size:15px; margin:0; }}
small, .mudo {{ color:var(--text-muted); }}
.cartao {{ background:var(--surface-1); border:1px solid var(--borda); border-radius:12px; padding:18px; margin-top:16px; }}
.topo {{ display:flex; flex-wrap:wrap; justify-content:space-between; align-items:baseline; gap:8px; }}
.faixa-demo {{ background:var(--neutro); border-left:4px solid var(--ruim); padding:10px 14px; margin-top:12px; border-radius:6px; font-weight:600; }}
.tiles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:12px; margin-top:16px; }}
.tile {{ background:var(--surface-1); border:1px solid var(--borda); border-radius:12px; padding:14px 16px; }}
.tile span {{ display:block; color:var(--text-secondary); font-size:13px; }}
.tile strong {{ font-size:26px; font-variant-numeric:tabular-nums; }}
.tile .pos {{ color:var(--alta); }} .tile .neg {{ color:var(--baixa); }}
.recomendacao {{ border-left:4px solid var(--text-primary); }}
.rec-titulo {{ font-size:19px; font-weight:700; margin:0 0 8px; }}
.recomendacao ul {{ margin:0; padding-left:20px; color:var(--text-secondary); }}
.recomendacao li {{ margin:4px 0; }}
.pilar {{ display:grid; grid-template-columns:minmax(120px,190px) 1fr 44px; align-items:center; gap:12px; padding:6px 0; }}
.pilar-nome {{ color:var(--text-secondary); font-size:14px; }}
.pilar-valor {{ text-align:right; font-variant-numeric:tabular-nums; font-weight:600; }}
.pilar-off {{ color:var(--text-muted); font-size:13px; }}
.trilha {{ position:relative; height:14px; background:var(--neutro); border-radius:4px; }}
.zero {{ position:absolute; left:50%; top:-3px; bottom:-3px; width:1px; background:var(--text-muted); }}
.barra {{ position:absolute; top:0; bottom:0; }}
.barra.pos {{ background:var(--alta); border-radius:0 4px 4px 0; }}
.barra.neg {{ background:var(--baixa); border-radius:4px 0 0 4px; }}
@media (max-width: 560px) {{
  .pilar {{ grid-template-columns:1fr 44px; gap:4px 12px; }}
  .trilha {{ grid-column:1 / -1; grid-row:2; }}
  .legenda-eixo {{ margin:0 !important; }}
  #grafico {{ height:340px; }}
}}
.legenda-eixo {{ display:flex; justify-content:space-between; color:var(--text-muted); font-size:12px;
  margin-left:calc(min(190px, 35%) + 12px); margin-right:56px; }}
.controles {{ display:flex; gap:8px; margin-bottom:10px; flex-wrap:wrap; align-items:center; }}
.controles button {{ font:inherit; font-size:13px; padding:5px 12px; border-radius:8px; border:1px solid var(--borda);
  background:var(--surface-0); color:var(--text-primary); cursor:pointer; }}
#seletor-plano button:first-child {{ margin-left:8px; }}
.controles button[aria-pressed="true"] {{ background:var(--text-primary); color:var(--surface-1); }}
.leitura {{ flex-basis:100%; font-size:13px; color:var(--text-secondary); font-variant-numeric:tabular-nums; min-height:20px; }}
.leitura b {{ color:var(--text-primary); }}
.chave {{ display:flex; flex-wrap:wrap; gap:14px; font-size:13px; color:var(--text-secondary); margin:6px 0 8px; }}
.chave i {{ display:inline-block; width:16px; height:2px; vertical-align:middle; margin-right:6px; }}
.chave i.tracejada {{ background:none !important; border-top:2px dashed; height:0; }}
#grafico {{ height:420px; }} #grafico-rsi {{ height:120px; margin-top:6px; }}
.planos {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:12px; }}
.plano {{ border:1px solid var(--borda); border-radius:10px; padding:14px; }}
.plano header {{ display:flex; justify-content:space-between; gap:8px; align-items:center; margin-bottom:10px; }}
.plano.invalido p {{ margin:6px 0 0; color:var(--text-secondary); }}
.selo {{ font-size:12px; font-weight:600; padding:2px 8px; border-radius:999px; white-space:nowrap; background:var(--neutro); }}
.selo-bom {{ color:var(--bom-texto); }} .selo-ruim {{ color:var(--ruim); }}
.grade {{ display:grid; grid-template-columns:1fr 1fr; gap:8px 16px; margin:0; }}
.grade dt {{ font-size:12px; color:var(--text-muted); }}
.grade dd {{ margin:0; font-weight:600; font-variant-numeric:tabular-nums; }}
.avisos {{ margin:10px 0 0; padding-left:18px; font-size:13px; color:var(--text-secondary); }}
details {{ border-top:1px solid var(--borda); padding:10px 0; }}
summary {{ cursor:pointer; font-weight:600; }}
.sinais {{ list-style:none; padding:0; margin:8px 0 0; }}
.sinais li {{ display:flex; gap:8px; padding:3px 0; font-size:14px; color:var(--text-secondary); }}
.pts {{ width:14px; flex:none; color:var(--text-muted); }} .pts.pos {{ color:var(--alta); }} .pts.neg {{ color:var(--baixa); }}
table {{ width:100%; border-collapse:collapse; font-size:14px; font-variant-numeric:tabular-nums; }}
th, td {{ text-align:left; padding:6px 8px; border-bottom:1px solid var(--borda); }}
th {{ color:var(--text-muted); font-weight:500; font-size:12px; }}
.noticias {{ list-style:none; padding:0; margin:0; }}
.noticias li {{ padding:8px 0; border-bottom:1px solid var(--borda); display:flex; flex-wrap:wrap; gap:4px 10px; align-items:baseline; }}
.noticias a {{ color:var(--text-primary); }} .noticias small {{ width:100%; }}
.tom {{ font-size:11px; padding:1px 7px; border-radius:999px; background:var(--neutro); color:var(--text-secondary); }}
.tom-positiva::before {{ content:"▲ "; color:var(--alta); }} .tom-negativa::before {{ content:"▼ "; color:var(--baixa); }}
.duas {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); gap:16px; }}
.duas > .cartao {{ margin-top:0; }}
ol {{ padding-left:20px; margin:0; }} ol li {{ margin:4px 0; }}
.rodape {{ margin-top:24px; font-size:13px; color:var(--text-muted); }}
</style>
</head>
<body>
<main>
  <div class="topo"><h1>Analista BTC · swing trade</h1><small>{_esc(r['gerado_em'])}</small></div>
  {demo}
  <section class="tiles" aria-label="Resumo">
    <div class="tile"><span>Preço BTC/USDT</span><strong>{_n(r['preco'])}</strong></div>
    <div class="tile"><span>Viés</span><strong class="{tom_vies}">{_esc(c['vies'])}</strong></div>
    <div class="tile"><span>Nota consolidada</span><strong>{c['nota']:+.0f}</strong> <small>de −100 a +100</small></div>
    <div class="tile"><span>Confluência</span><strong>{_esc(c['confluencia'].split(' ')[0])}</strong> <small>pilares concordam</small></div>
  </section>

  <section class="cartao recomendacao">
    <h2>O que fazer agora</h2>
    <p class="rec-titulo">{_esc(rec_titulo)}</p>
    <ul>{rec_itens}</ul>
  </section>

  <section class="cartao">
    <h2>Nota por pilar</h2>
    {barras}
    <div class="legenda-eixo"><span>−100 baixista</span><span>0</span><span>altista +100</span></div>
  </section>

  <section class="cartao">
    <h2>Gráfico</h2>
    <div class="controles" role="group" aria-label="Timeframe">
      <button data-tf="4h" aria-pressed="true">4 horas</button>
      <button data-tf="1d" aria-pressed="false">Diário</button>
      <span id="seletor-plano" role="group" aria-label="Plano exibido" style="display:contents"></span>
      <span class="leitura" id="leitura"></span>
    </div>
    <div class="chave">
      <span><i style="background:var(--ema20)"></i>EMA20</span>
      <span><i style="background:var(--ema50)"></i>EMA50</span>
      <span><i style="background:var(--ema200)"></i>EMA200</span>
      <span><i class="tracejada" style="color:var(--text-primary)"></i>entrada</span>
      <span><i class="tracejada" style="color:var(--ruim)"></i>stop</span>
      <span><i class="tracejada" style="color:var(--bom)"></i>alvos</span>
    </div>
    <div id="grafico"></div>
    <div class="chave"><span>RSI (14) · linhas em 30 e 70</span></div>
    <div id="grafico-rsi"></div>
  </section>

  <section class="cartao">
    <h2>Planos de trade <small>capital {_n(cfg.capital)} USDT · risco {cfg.risco_pct:g}% · mínimo {cfg.rr_min:g}:1</small></h2>
    <div class="planos">{planos}</div>
  </section>

  <div class="duas" style="margin-top:16px">
    <section class="cartao"><h2>Por que essa nota</h2>{detalhes}</section>
    <section class="cartao"><h2>Notícias recentes</h2>{_noticias(r['pilares'])}</section>
  </div>

  <div class="duas" style="margin-top:16px">
    <section class="cartao"><h2>Suportes e resistências</h2>
      <table><thead><tr><th>Tipo</th><th>Preço</th><th>Força (toques)</th><th>Timeframes</th></tr></thead>
      <tbody>{niveis}</tbody></table></section>
    <section class="cartao"><h2>Gestão do trade</h2><ol>{gestao}</ol></section>
  </div>

  <p class="rodape">Análise automática e educativa, não é recomendação de investimento.
  Confira o gráfico antes de qualquer ordem.</p>
</main>

<script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
<script>
const DADOS = {dados_js};
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const fmt = v => v.toLocaleString('pt-BR', {{maximumFractionDigits: 0}});
let tf = '4h', planoAtivo = 0, graf, grafRsi;

function montar() {{
  if (!window.LightweightCharts) {{
    document.getElementById('grafico').textContent = 'Não foi possível carregar a biblioteca do gráfico (sem internet?).';
    return;
  }}
  document.getElementById('grafico').innerHTML = '';
  document.getElementById('grafico-rsi').innerHTML = '';
  const base = {{
    layout: {{ background: {{ color: css('--surface-1') }}, textColor: css('--text-secondary'), fontSize: 12 }},
    grid: {{ vertLines: {{ visible: false }}, horzLines: {{ color: css('--grade') }} }},
    rightPriceScale: {{ borderVisible: false }},
    timeScale: {{ borderVisible: false, timeVisible: tf === '4h' }},
    crosshair: {{ mode: 0 }},
    localization: {{ priceFormatter: fmt, locale: 'pt-BR' }},
    autoSize: true,
  }};
  const d = DADOS[tf];
  graf = LightweightCharts.createChart(document.getElementById('grafico'), base);
  const plano = DADOS.planos[planoAtivo];
  const precosPlano = plano ? [plano.entrada, plano.stop, plano.alvo1, plano.alvo2] : [];
  const velas = graf.addCandlestickSeries({{
    // a escala inclui entrada, stop e alvos mesmo quando estão longe do preço atual
    autoscaleInfoProvider: original => {{
      const r = original();
      if (r && precosPlano.length) {{
        r.priceRange.minValue = Math.min(r.priceRange.minValue, ...precosPlano);
        r.priceRange.maxValue = Math.max(r.priceRange.maxValue, ...precosPlano);
      }}
      return r;
    }},
    upColor: css('--alta'), downColor: css('--baixa'), borderVisible: false,
    wickUpColor: css('--alta'), wickDownColor: css('--baixa'),
  }});
  velas.setData(d.candles);
  const linhas = {{}};
  for (const [k, cor] of [['ema20', '--ema20'], ['ema50', '--ema50'], ['ema200', '--ema200']]) {{
    linhas[k] = graf.addLineSeries({{ color: css(cor), lineWidth: 2, priceLineVisible: false,
      lastValueVisible: false, crosshairMarkerVisible: false }});
    linhas[k].setData(d[k]);
  }}
  const tracejada = LightweightCharts.LineStyle.Dashed;
  for (const p of plano ? [plano] : []) {{
    const lado = p.direcao === 'long' ? 'compra' : 'venda';
    velas.createPriceLine({{ price: p.entrada, color: css('--text-primary'), lineWidth: 1, lineStyle: tracejada, title: 'entrada ' + lado }});
    velas.createPriceLine({{ price: p.stop, color: css('--ruim'), lineWidth: 1, lineStyle: tracejada, title: 'stop' }});
    velas.createPriceLine({{ price: p.alvo1, color: css('--bom'), lineWidth: 1, lineStyle: tracejada, title: 'alvo 1' }});
    velas.createPriceLine({{ price: p.alvo2, color: css('--bom'), lineWidth: 1, lineStyle: tracejada, title: 'alvo 2' }});
  }}
  graf.timeScale().fitContent();

  grafRsi = LightweightCharts.createChart(document.getElementById('grafico-rsi'), base);
  const rsi = grafRsi.addLineSeries({{ color: css('--text-secondary'), lineWidth: 2, priceLineVisible: false }});
  rsi.setData(d.rsi);
  for (const nivel of [30, 70]) rsi.createPriceLine({{ price: nivel, color: css('--text-muted'), lineWidth: 1, lineStyle: tracejada, axisLabelVisible: false }});

  // RSI acompanha o zoom do gráfico de preço
  graf.timeScale().subscribeVisibleLogicalRangeChange(r => r && grafRsi.timeScale().setVisibleLogicalRange(r));
  grafRsi.timeScale().subscribeVisibleLogicalRangeChange(r => r && graf.timeScale().setVisibleLogicalRange(r));

  const leitura = document.getElementById('leitura');
  const mostrar = (vela, extras) => {{
    leitura.replaceChildren();
    if (!vela) return;
    const partes = [['A', vela.open], ['Máx', vela.high], ['Mín', vela.low], ['F', vela.close], ...extras];
    for (const [rotulo, v] of partes) {{
      if (v == null) continue;
      const b = document.createElement('b'); b.textContent = fmt(v);
      leitura.append(rotulo + ' ', b, '  ');
    }}
  }};
  const ultimo = d.candles[d.candles.length - 1];
  mostrar(ultimo, []);
  graf.subscribeCrosshairMove(p => {{
    if (!p.time || !p.seriesData.get(velas)) return mostrar(ultimo, []);
    mostrar(p.seriesData.get(velas), [
      ['EMA20', p.seriesData.get(linhas.ema20)?.value],
      ['EMA50', p.seriesData.get(linhas.ema50)?.value],
      ['EMA200', p.seriesData.get(linhas.ema200)?.value],
    ]);
  }});
}}

const seletor = document.getElementById('seletor-plano');
DADOS.planos.forEach((p, i) => {{
  const b = document.createElement('button');
  b.textContent = (p.direcao === 'long' ? 'Compra: ' : 'Venda: ') + p.tipo.split(' (')[0];
  b.setAttribute('aria-pressed', String(i === planoAtivo));
  b.addEventListener('click', () => {{
    planoAtivo = i;
    seletor.querySelectorAll('button').forEach((x, j) => x.setAttribute('aria-pressed', String(j === i)));
    graf?.remove(); grafRsi?.remove(); montar();
  }});
  seletor.append(b);
}});
document.querySelectorAll('[data-tf]').forEach(b => b.addEventListener('click', () => {{
  tf = b.dataset.tf;
  const seletor = document.getElementById('seletor-plano');
DADOS.planos.forEach((p, i) => {{
  const b = document.createElement('button');
  b.textContent = (p.direcao === 'long' ? 'Compra: ' : 'Venda: ') + p.tipo.split(' (')[0];
  b.setAttribute('aria-pressed', String(i === planoAtivo));
  b.addEventListener('click', () => {{
    planoAtivo = i;
    seletor.querySelectorAll('button').forEach((x, j) => x.setAttribute('aria-pressed', String(j === i)));
    graf?.remove(); grafRsi?.remove(); montar();
  }});
  seletor.append(b);
}});
document.querySelectorAll('[data-tf]').forEach(x => x.setAttribute('aria-pressed', String(x === b)));
  graf?.remove(); grafRsi?.remove(); montar();
}}));
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {{ graf?.remove(); grafRsi?.remove(); montar(); }});
montar();
</script>
</body>
</html>"""
