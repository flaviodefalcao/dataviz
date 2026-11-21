"""Função da Vercel: gera o relatório do analista BTC sob demanda, protegido por senha.

Configure na Vercel a variável de ambiente RELATORIO_SENHA. O navegador pede usuário e
senha: o usuário pode ser qualquer um, a senha é a da variável.
Parâmetros opcionais na URL: ?capital=5000&risco=1&rr=2
"""
from __future__ import annotations

import base64
import hmac
import os
import sys
import time
import traceback
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from btc_analyst import __main__ as app  # noqa: E402
from btc_analyst import plano as pl  # noqa: E402
from btc_analyst import relatorio  # noqa: E402

CACHE_SEGUNDOS = 600
_cache: dict = {}  # dados coletados, reaproveitados por 10 minutos entre chamadas


def _senha_ok(cabecalho: str | None) -> bool:
    senha = os.environ.get("RELATORIO_SENHA", "")
    if not senha or not cabecalho or not cabecalho.startswith("Basic "):
        return False
    try:
        _, _, enviada = base64.b64decode(cabecalho[6:]).decode("utf-8").partition(":")
    except Exception:  # noqa: BLE001
        return False
    return hmac.compare_digest(enviada.encode(), senha.encode())


def _numero(q: dict, nome: str, padrao: float, minimo: float, maximo: float) -> float:
    try:
        return min(max(float(q.get(nome, [padrao])[0]), minimo), maximo)
    except ValueError:
        return padrao


def gerar_pagina(query: str) -> str:
    q = parse_qs(query)
    cfg = pl.Config(capital=_numero(q, "capital", 10_000, 10, 1e9),
                    risco_pct=_numero(q, "risco", 1, 0.1, 5),
                    rr_min=_numero(q, "rr", 2, 2, 10))
    if not _cache or time.time() - _cache["quando"] > CACHE_SEGUNDOS:
        _cache.update(dados=app._coletar(lambda m: print(m, file=sys.stderr)), quando=time.time())
    return relatorio.pagina(app.analisar(_cache["dados"], cfg))


class handler(BaseHTTPRequestHandler):  # noqa: N801 - nome exigido pela Vercel
    def _responder(self, status: int, corpo: str, extra: dict | None = None):
        dados = corpo.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "private, no-store")
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def do_GET(self):  # noqa: N802
        if not os.environ.get("RELATORIO_SENHA"):
            return self._responder(500, "<h1>Configure a variável RELATORIO_SENHA na Vercel.</h1>")
        if not _senha_ok(self.headers.get("Authorization")):
            return self._responder(401, "<h1>Senha necessária</h1>",
                                   {"WWW-Authenticate": 'Basic realm="Analista BTC", charset="UTF-8"'})
        url = urlparse(self.path)
        if url.path not in ("/", "/api", "/api/index", "/api/index.py"):
            return self._responder(404, "<h1>Não encontrado</h1>")
        try:
            self._responder(200, gerar_pagina(url.query))
        except BaseException:  # noqa: BLE001 - inclui SystemExit de _coletar
            traceback.print_exc()
            self._responder(503, "<h1>Não foi possível coletar os dados agora.</h1>"
                                 "<p>Tente de novo em alguns minutos.</p>")
