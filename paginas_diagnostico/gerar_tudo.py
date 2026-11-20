#!/usr/bin/env python3
"""
Um comando só: exports do Matrix (pasta entrada/) -> CSV e páginas HTML (pasta saida/).

    python3 gerar_tudo.py                          # revisão: 3 páginas por grupo + saida/site/_previa.html
    python3 gerar_tudo.py --todas \\
        --dominio www.seusite.com.br \\
        --logo-topo  https://cdn.seusite.com.br/diagnostico/logo_topo.png \\
        --logo-marca https://cdn.seusite.com.br/diagnostico/logo_marca.png
    python3 gerar_tudo.py --todas --bf-aberta --fase2-aberta ...          # a partir de 27/11

Lê de entrada/ (pega o arquivo mais recente de cada tipo):
    matrix-gabarito-2026-dia1-respostas-alunos-*.csv
    matrix-gabarito-2026-dia2-respostas-alunos-*.csv
    matrix-opcoes-sisu-2026-*.csv
    matrix-usuarios-*.csv
    vendas*.csv          (opcional) vendas aprovadas: Destrinchando / Revisão Enem  -> grupo V
    campanhas*.xlsx      (opcional) usuários do Matrix com Nome e Plano (pago/gratuito) -> nome e grupo V

Grava em saida/:
    base_alunos.csv     1 linha por aluno, só os dados dele (~23 colunas)
    alunos.csv          o CSV completo que o gerar.py lê (324+ colunas, 1 linha por aluno)
    site/               uma página HTML por aluno (<aluno_id>.html)
    relatorio.txt       contagem por grupo e avisos
    emails.csv          1 e-mail por pessoa (assunto, textos, link da página) para a ferramenta de disparo
    emails_previa.html  um e-mail de cada grupo, para revisar

Etapas (cada uma também roda sozinha, ver README.md):
    1. scripts/inferir_gabarito.py  -> dados/gabarito.csv   (só se não existir, ou com --refazer-gabarito)
    2. montar_base.py               -> saida/base_alunos.csv (+ atualiza dados/)
    3. gerar_site.py                -> saida/alunos.csv + saida/site/
    4. emails/gerar_emails.py       -> saida/emails.csv + saida/emails_previa.html
"""
import argparse
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
PADROES = {
    "dia1": "matrix-gabarito-2026-dia1-respostas-alunos-*.csv",
    "dia2": "matrix-gabarito-2026-dia2-respostas-alunos-*.csv",
    "sisu": "matrix-opcoes-sisu-2026-*.csv",
    "usuarios": "matrix-usuarios-*.csv",
    "vendas": "vendas*.csv",
    "planos": "campanhas*.xlsx",
}


def mais_recente(pasta, padrao):
    achados = sorted(Path(pasta).glob(padrao))
    return achados[-1] if achados else None


def rodar(cmd):
    print("\n$ " + " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([sys.executable] + [str(c) for c in cmd], check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--entrada", default=str(AQUI / "entrada"))
    ap.add_argument("--saida", default=str(AQUI / "saida"))
    ap.add_argument("--todas", action="store_true", help="gera a página de todos os alunos (sem isso: 3 por grupo)")
    ap.add_argument("--refazer-gabarito", action="store_true", help="recalcula dados/gabarito.csv a partir das respostas (~10 min)")
    ap.add_argument("--bf-aberta", action="store_true")
    ap.add_argument("--fase2-aberta", action="store_true")
    ap.add_argument("--dominio", default="SEU-DOMINIO")
    ap.add_argument("--logo-topo", default="")
    ap.add_argument("--logo-marca", default="")
    ap.add_argument("--url-pagina", default="", help="endereço de cada página, com {aluno_id}. Padrão: https://<dominio>/diagnostico/{aluno_id}.html")
    a = ap.parse_args()

    arq = {k: mais_recente(a.entrada, p) for k, p in PADROES.items()}
    faltando = [PADROES[k] for k in ("dia1", "dia2", "sisu") if not arq[k]]
    if faltando:
        raise SystemExit(f"Faltam em {a.entrada}/: " + ", ".join(faltando))
    for k, v in arq.items():
        print(f"{k:<9} {v.name if v else '(não encontrado)'}")
    saida = Path(a.saida)
    saida.mkdir(parents=True, exist_ok=True)

    if a.refazer_gabarito or not (AQUI / "dados" / "gabarito.csv").exists():
        rodar([AQUI / "scripts" / "inferir_gabarito.py", "--dia1", arq["dia1"], "--dia2", arq["dia2"]])

    base = saida / "base_alunos.csv"
    cmd = [AQUI / "montar_base.py", "--dia1", arq["dia1"], "--dia2", arq["dia2"], "--sisu", arq["sisu"], "-o", base]
    for k in ("usuarios", "vendas", "planos"):
        if arq[k]:
            cmd += [f"--{k}", arq[k]]
    rodar(cmd)

    cmd = [AQUI / "gerar_site.py", base, "-o", saida, "--dominio", a.dominio]
    cmd += ["--bf-aberta"] if a.bf_aberta else []
    cmd += ["--fase2-aberta"] if a.fase2_aberta else []
    cmd += ["--logo-topo", a.logo_topo] if a.logo_topo else []
    cmd += ["--logo-marca", a.logo_marca] if a.logo_marca else []
    cmd += [] if a.todas else ["--amostra", "3"]
    rodar(cmd)

    # 4. e-mails (1 por pessoa, com o link da página dela)
    url = a.url_pagina or f"https://{a.dominio}/diagnostico/{{aluno_id}}.html"
    cmd = [AQUI / "emails" / "gerar_emails.py", "--base", base, "--saida", saida, "--url-pagina", url]
    cmd += ["--logo-url", a.logo_topo] if a.logo_topo else []
    if arq["usuarios"]:
        cmd += ["--usuarios", arq["usuarios"]]
    rodar(cmd)
    print(f"\nPronto. CSV: {saida / 'alunos.csv'} · páginas: {saida / 'site'}/ · e-mails: {saida / 'emails.csv'}"
          f" (prévia {saida / 'emails_previa.html'}) · relatório: {saida / 'relatorio.txt'}")


if __name__ == "__main__":
    sys.exit(main())
