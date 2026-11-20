#!/usr/bin/env python3
"""
Gera o e-mail de cada pessoa que leva à página de diagnóstico dela.

Entradas:
    saida/base_alunos.csv                  (do montar_base.py)
    entrada/matrix-usuarios-*.csv          (user_id;email)
    emails/textos_email.csv                (assunto, pré-cabeçalho, título, parágrafos e botão por grupo, com {variáveis})
    emails/template_email.html             (layout do e-mail, com campos {{...}})

Saídas:
    saida/emails.csv            1 linha por pessoa: user_id;email;grupo;assunto;preheader;titulo;p1;p2;p3;botao;link
                                -> importar na ferramenta de disparo e usar com o template_email.html
    saida/emails_previa.html    um e-mail de cada grupo, já montado, para revisar
    saida/emails_html/          (só com --html) um .html pronto por pessoa

Uso:
    python3 emails/gerar_emails.py --url-pagina "https://www.seusite.com.br/diagnostico/{aluno_id}.html" \\
        --logo-url https://cdn.seusite.com.br/diagnostico/logo_marca_branco.png \\
        --descadastro-url "https://www.seusite.com.br/descadastro?u={aluno_id}"
"""
import argparse
import csv
import html
import re
import sys
from collections import Counter
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
sys.path.insert(0, str(RAIZ))
import montar_csv as M  # noqa: E402

UTM = "utm_source=email&utm_medium=diagnostico&utm_campaign=bf2026&utm_content={grupo}"
AREAS = {"LC": "Linguagens", "CH": "Humanas", "CN": "Natureza", "MT": "Matemática"}


def frase_faceis(n, area):
    if n == 0:
        return f"montamos um plano de {area} para o seu número de acertos."
    if n == 1:
        return "separamos a 1 questão fácil que escapou, com a explicação."
    return f"separamos as {n} questões fáceis que escaparam, com a explicação de cada uma."


def variaveis(a, grupo, dist, refs):
    curso = refs.cursos.get(a.get("curso_id", ""), {}) if grupo not in ("E",) else {}
    area = AREAS.get(a.get("area_prioritaria", ""), "")
    nome = a.get("nome", "")
    incompletas = [AREAS[x] for x in M.ORDEM_AREAS
                   if a.get(f"dia{refs.areas[x]['dia']}_lancado") == "sim" and not a.get(f"nota_{x}")]
    n_faceis = len(M.lista(a.get("faceis_ids")))
    return {
        "nome": nome,
        "saudacao": f"Oi, {nome}!" if nome else "Oi!",
        "area": area,
        "curso": curso.get("curso", ""),
        "ies": curso.get("ies", ""),
        "na_ies": f'{curso.get("artigo_ies", "na")} {curso.get("ies", "")}' if curso else "",
        "nota_top10": M.inteiro(curso.get("nota_top10")) if curso else "",
        "media": M.inteiro(M.media_de(a)) if a.get("media") else "",
        "pontos": str(abs(int(round(dist)))) if dist is not None else "",
        "frase_faceis": frase_faceis(n_faceis, area),
        "areas_sem_nota": (" e ".join(incompletas) or "uma das áreas") + (" ainda não têm nota" if len(incompletas) > 1 else " ainda não tem nota"),
        **{f"nota_{x}": M.inteiro(a.get(f"nota_{x}")) for x in M.ORDEM_AREAS},
    }


def aplicar(texto, var):
    t = re.sub(r"\{([a-z_A-Z0-9]+)\}", lambda m: str(var.get(m.group(1), m.group(0))), texto)
    if not var.get("nome"):  # sem nome: "{nome}, faltam…" vira "Faltam…"
        t = re.sub(r"^\{nome\}, (.)", lambda m: m.group(1).upper(), texto)
        t = re.sub(r"\{([a-z_A-Z0-9]+)\}", lambda m: str(var.get(m.group(1), m.group(0))), t)
    return t


def render(tpl, campos):
    corpo = tpl
    if not campos.get("p3"):
        corpo = re.sub(r"<!--p3-->.*?<!--/p3-->", "", corpo, flags=re.S)
    return re.sub(r"\{\{(\w+)\}\}", lambda m: html.escape(str(campos.get(m.group(1), "")), quote=True), corpo)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=str(RAIZ / "saida" / "base_alunos.csv"))
    ap.add_argument("--usuarios", default="", help="padrão: o matrix-usuarios-*.csv mais recente em entrada/")
    ap.add_argument("--url-pagina", default="https://SEU-DOMINIO/diagnostico/{aluno_id}.html",
                    help="endereço da página de cada pessoa; {aluno_id} é trocado pelo id")
    ap.add_argument("--logo-url", default="https://SEU-DOMINIO/diagnostico/logo.png")
    ap.add_argument("--descadastro-url", default="{{descadastro}}", help="link de descadastro (ou o código da sua ferramenta)")
    ap.add_argument("--saida", default=str(RAIZ / "saida"))
    ap.add_argument("--html", action="store_true", help="grava também um .html pronto por pessoa")
    a = ap.parse_args()

    refs = M.Refs()
    textos = {r["grupo"]: r for r in M.ler_csv(AQUI / "textos_email.csv")}
    tpl = (AQUI / "template_email.html").read_text(encoding="utf-8")
    usu = a.usuarios or max((RAIZ / "entrada").glob("matrix-usuarios-*.csv"), default=None)
    emails = {r.get("user_id") or r.get("aluno_id"): r.get("email", "") for r in M.ler_csv(usu)} if usu else {}
    saida = Path(a.saida)
    saida.mkdir(parents=True, exist_ok=True)
    if a.html:
        (saida / "emails_html").mkdir(exist_ok=True)

    cols = ["user_id", "email", "grupo", "assunto", "preheader", "titulo", "p1", "p2", "p3", "botao", "link"]
    contagem, sem_email, amostra = Counter(), 0, {}
    with open(saida / "emails.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, cols, delimiter=";")
        w.writeheader()
        for aluno in M.ler_csv(a.base):
            grupo, dist = M.classificar(aluno, refs)
            chave = grupo
            if aluno.get("ja_comprou") == "sim":  # V: texto próprio; quem só lançou 1 dia recebe o do F/G/H
                chave = "V_sem_gabarito" if grupo.startswith("M_") else (grupo if grupo in ("F", "G", "H") else "V")
            t = textos[chave]
            var = variaveis(aluno, grupo, dist, refs)
            aid = aluno["aluno_id"]
            link = a.url_pagina.replace("{aluno_id}", aid)
            link += ("&" if "?" in link else "?") + UTM.format(grupo=chave)
            linha = {"user_id": aid, "email": emails.get(aid, ""), "grupo": chave, "link": link}
            for k in ("assunto", "preheader", "titulo", "p1", "p2", "p3", "botao"):
                linha[k] = aplicar(t[k], var)
            if not linha["email"]:
                sem_email += 1
                continue
            w.writerow(linha)
            contagem[chave] += 1
            campos = {**linha, "logo_url": a.logo_url, "descadastro_url": a.descadastro_url.replace("{aluno_id}", aid)}
            if a.html:
                (saida / "emails_html" / f"{aid}.html").write_text(render(tpl, campos), encoding="utf-8")
            if chave not in amostra and (aluno.get("nome") or chave in ("M_gratis",)):
                amostra[chave] = campos

    # prévia: um e-mail de cada grupo, com o assunto em cima
    ordem = [r for r in textos if r in amostra]
    blocos = []
    logo_previa = a.logo_url
    if "SEU-DOMINIO" in logo_previa:  # sem URL real ainda: na prévia, o logo vai embutido
        import base64
        logo_previa = "data:image/png;base64," + base64.b64encode((RAIZ / "assets" / "logo_topo.png").read_bytes()).decode()
    for g in ordem:
        c = {**amostra[g], "logo_url": logo_previa}
        corpo = render(tpl, c).split("<body", 1)[1].split(">", 1)[1].rsplit("</body>", 1)[0]
        pessoas = f"{contagem[g]:,}".replace(",", ".")
        blocos.append(f'<div style="max-width:640px;margin:28px auto 6px;padding:12px 16px;background:#081b50;color:#fff;'
                      f'font-family:Inter,Arial,sans-serif;font-size:14px;font-weight:600;line-height:20px;border-radius:12px">'
                      f'<span style="opacity:.7">Grupo {html.escape(g)} · {pessoas} pessoas</span><br>'
                      f'Assunto: {html.escape(c["assunto"])}<br>'
                      f'<span style="opacity:.7;font-weight:400">Pré-cabeçalho: {html.escape(c["preheader"])}</span></div>' + corpo)
    previa = (tpl.split("<body", 1)[0] + '<body style="margin:0;background:#e9edf8">' + "".join(blocos) + "</body></html>")
    (saida / "emails_previa.html").write_text(previa, encoding="utf-8")
    print(f"{sum(contagem.values())} e-mails -> {saida / 'emails.csv'}  ({sem_email} sem e-mail, pulados)")
    print("Por grupo:", ", ".join(f"{g} {n}" for g, n in sorted(contagem.items())))
    print(f"Prévia: {saida / 'emails_previa.html'}")


if __name__ == "__main__":
    sys.exit(main())
