"""Testes com dados simulados (não usam internet)."""
import numpy as np
import pandas as pd
import pytest

from btc_analyst import __main__ as app
from btc_analyst import analise, relatorio
from btc_analyst import indicadores as ind
from btc_analyst import plano as pl


@pytest.fixture(scope="module")
def resultado():
    return app.analisar(app._demo(), pl.Config(capital=5000, risco_pct=1), demo=True)


def test_rsi_entre_0_e_100():
    df = app._simular("1d", 300, 7)
    r = ind.rsi(df["close"])
    assert r.between(0, 100).all()


def test_pivos_e_niveis():
    df = app._simular("1d", 300, 7)
    topos, fundos = ind.pivos(df, 3)
    assert topos and fundos
    niveis = ind.niveis({"1d": df}, tolerancia=500)
    assert all(n.toques >= 1 for n in niveis)
    assert niveis == sorted(niveis, key=lambda n: n.preco)


def test_planos_validos_respeitam_2_para_1(resultado):
    cfg = resultado["config"]
    for p in resultado["planos"]:
        if not p.valido:
            continue
        assert p.rr1 >= cfg.rr_min - 1e-6
        assert p.rr2 >= p.rr1
        assert p.risco_usd <= cfg.capital * cfg.risco_pct / 100 + 0.01
        if p.direcao == "long":
            assert p.stop < p.entrada < p.alvo1 <= p.alvo2
        else:
            assert p.stop > p.entrada > p.alvo1 >= p.alvo2


@pytest.mark.parametrize("semente", range(15))
def test_2_para_1_em_varios_cenarios(semente):
    dados = app._demo()
    for tf, n in (("1w", 200), ("1d", 500), ("4h", 500)):
        dados[tf] = app._simular(tf, n, 100 + semente)
    r = app.analisar(dados, pl.Config(), demo=True)
    for p in r["planos"]:
        if p.valido:
            assert p.rr1 >= 2 - 1e-6
            assert p.stop_pct <= 10


def test_entrada_max_torna_trade_2_para_1():
    """A entrada máxima sugerida deixa o obstáculo exatamente a 2R (com taxas)."""
    cfg = pl.Config(taxa=0.001)
    obstaculo = ind.Nivel(100_000, 3, "1d")
    p = pl._montar("teste", 1, 97_000, ind.Nivel(95_000, 3, "1d"), [obstaculo], 500, cfg, 100)
    assert not p.valido and p.entrada_max_2r
    e, stop, limite = p.entrada_max_2r, p.stop, 100_000 - 0.1 * 500
    custo = e * cfg.taxa * 2
    assert (limite - e - custo) / (e - stop + custo) == pytest.approx(2, abs=0.01)


def test_tamanho_limitado_pelo_capital():
    cfg = pl.Config(capital=1000, risco_pct=5)
    p = pl._montar("teste", 1, 100_000, None, [], 300, cfg, 50)
    assert p.valor_posicao <= cfg.capital + 0.01


def test_sem_fontes_externas_nao_quebra():
    dados = app._demo()
    dados.update(macro=None, fg=None, deriv=None, glob=None, noticias=None,
                 erros={"macro": "bloqueado", "noticias": "bloqueado"})
    r = app.analisar(dados, pl.Config(), demo=True)
    assert r["consolidado"]["cobertura"] == "2/5 pilares com dados"
    assert "indisponível" in relatorio.texto(r)


def test_noticias_html_escapado():
    itens = [{"fonte": "x", "titulo": "<script>alert(1)</script> bitcoin rally",
              "link": "javascript:alert(1)", "data": None}]
    p = analise.noticias(itens)
    html = relatorio._noticias([p])
    assert "<script>" not in html and "javascript:" not in html


def test_saidas(resultado):
    assert "VIÉS" in relatorio.texto(resultado)
    pagina = relatorio.pagina(resultado)
    assert pagina.startswith("<!doctype html>") and "lightweight-charts@4.2.0" in pagina
    assert '"planos"' in relatorio.para_json(resultado)


def test_sentimento_com_derivativos_do_coingecko():
    d = app._simular("1d", 300, 3)
    deriv = {"fonte": "CoinGecko", "funding_atual": -0.0003, "funding_media_mercado": -0.0001,
             "funding_media_7d": None, "oi_usd": 3e10, "oi_var_7d": None, "ls_top": None, "ls_geral": None}
    p = analise.sentimento(None, deriv, None, d)
    textos = " ".join(t for t, _ in p.sinais)
    assert "CoinGecko" in textos and p.score > 0


def test_recomendacao(resultado):
    titulo, itens = relatorio.recomendacao(resultado)
    assert titulo and isinstance(itens, list)
    assert "O que fazer agora" in relatorio.pagina(resultado)


def test_senha_da_vercel(monkeypatch):
    import base64
    import importlib.util
    spec = importlib.util.spec_from_file_location("vercel_index", "api/index.py")
    index = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(index)
    monkeypatch.setenv("RELATORIO_SENHA", "abc123")
    cab = lambda u, s: "Basic " + base64.b64encode(f"{u}:{s}".encode()).decode()  # noqa: E731
    assert index._senha_ok(cab("qualquer", "abc123"))
    assert not index._senha_ok(cab("qualquer", "errada"))
    assert not index._senha_ok(None)
    monkeypatch.setenv("RELATORIO_SENHA", "")
    assert not index._senha_ok(cab("x", ""))
