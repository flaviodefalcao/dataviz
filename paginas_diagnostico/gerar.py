#!/usr/bin/env python3
"""
Gera as páginas de diagnóstico a partir de alunos.csv + template.html.

Uso:
    python3 gerar.py                         # lê alunos.csv, grava em saida/
    python3 gerar.py minha_base.csv -o pasta
    python3 gerar.py --logo-topo https://cdn/.../logo.png --logo-marca https://cdn/.../marca.png
    python3 gerar.py --json                  # também grava o modelo de dados de cada aluno (.json)

Saída:
    saida/<aluno_id>.html   uma página por linha do CSV
    saida/_previa.html      todas as páginas empilhadas, com navegação (para revisar)

Só usa a biblioteca padrão do Python (3.8+). O template é Mustache padrão,
então o mesmo template.html roda em mustache.js (Node), chevron (Python), PHP etc.
Para isso, basta replicar a função montar_modelo() — ou usar o --json.
"""
import argparse
import base64
import csv
import html
import json
import re
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent

AREAS = {"LC": "Linguagens", "CH": "Humanas", "CN": "Natureza", "MT": "Matemática"}
CARDS = [  # ordem em que aparecem na página
    ("seguro", True),
    ("fase2", True),
    ("proposta", True),
    ("indicacao", False),  # card simples, sem a borda de oferta
]
SIM = {"sim", "s", "1", "true", "x", "verdadeiro", "yes"}
ARCO_TOTAL = 157.08  # comprimento do arco do medidor (pi * 50)


# ---------------------------------------------------------------- Mustache mínimo
TOKEN = re.compile(r"\{\{(\{[^}]+\}|[#^/!&]?[^}]*)\}\}")


def _parse(tpl):
    raiz = []
    pilha = [("", raiz)]
    pos = 0
    for m in TOKEN.finditer(tpl):
        if m.start() > pos:
            pilha[-1][1].append(("txt", tpl[pos:m.start()]))
        pos = m.end()
        tag = m.group(1).strip()
        if tag.startswith("!"):
            continue
        if tag.startswith("{"):
            pilha[-1][1].append(("raw", tag.strip("{} ")))
        elif tag.startswith("&"):
            pilha[-1][1].append(("raw", tag[1:].strip()))
        elif tag[0] in "#^":
            filhos = []
            pilha[-1][1].append(("sec" if tag[0] == "#" else "inv", tag[1:].strip(), filhos))
            pilha.append((tag[1:].strip(), filhos))
        elif tag.startswith("/"):
            nome = tag[1:].strip()
            if pilha[-1][0] != nome:
                raise ValueError(f"Template: fechamento {{{{/{nome}}}}} sem abertura correspondente")
            pilha.pop()
        else:
            pilha[-1][1].append(("var", tag))
    if len(pilha) != 1:
        raise ValueError(f"Template: seção {{{{#{pilha[-1][0]}}}}} não foi fechada")
    if pos < len(tpl):
        raiz.append(("txt", tpl[pos:]))
    return raiz


def _busca(nome, pilha):
    if nome == ".":
        return pilha[-1]
    partes = nome.split(".")
    for ctx in reversed(pilha):
        if isinstance(ctx, dict) and partes[0] in ctx:
            val = ctx[partes[0]]
            for p in partes[1:]:
                val = val.get(p) if isinstance(val, dict) else None
            return val
    return None


def _render(nos, pilha):
    out = []
    for no in nos:
        tipo = no[0]
        if tipo == "txt":
            out.append(no[1])
        elif tipo in ("var", "raw"):
            v = _busca(no[1], pilha)
            v = "" if v is None or v is False else str(v)
            out.append(v if tipo == "raw" else html.escape(v, quote=True))
        elif tipo == "sec":
            v = _busca(no[1], pilha)
            if isinstance(v, list):
                for item in v:
                    out.append(_render(no[2], pilha + [item]))
            elif v:
                out.append(_render(no[2], pilha + [v]))
        elif tipo == "inv":
            v = _busca(no[1], pilha)
            if not v:
                out.append(_render(no[2], pilha))
    return "".join(out)


def mustache(tpl, dados):
    return _render(_parse(tpl), [dados])


# ---------------------------------------------------------------- utilidades
def numero(v):
    try:
        return float(str(v).replace(",", ".").strip())
    except ValueError:
        return None


def arco(nota):
    n = numero(nota)
    return "" if n is None else f"{max(0.0, min(n, 1000.0)) * ARCO_TOTAL / 1000:.1f}"


def ler_csv(caminho):
    texto = Path(caminho).read_text(encoding="utf-8-sig")
    cabecalho = texto.split("\n", 1)[0]
    sep = ";" if cabecalho.count(";") > cabecalho.count(",") else ","
    linhas = list(csv.DictReader(texto.splitlines(), delimiter=sep))
    return [{(k or "").strip(): (v or "").strip() for k, v in l.items()} for l in linhas]


def aplicar_placeholders(linha):
    """{coluna} dentro de qualquer célula é trocado pelo valor daquela coluna (ex.: {nome})."""
    def troca(m):
        return linha.get(m.group(1), m.group(0))
    return {k: re.sub(r"\{([a-zA-Z0-9_]+)\}", troca, v) for k, v in linha.items()}


def slots(linha, prefixo):
    """Índices preenchidos de colunas repetidas: facil1_, facil2_... (sem limite fixo)."""
    idx = set()
    for k in linha:
        m = re.match(rf"{prefixo}(\d+)_", k)
        if m:
            idx.add(int(m.group(1)))
    return sorted(idx)


def link(texto, url):
    return {"texto": texto, "url": url} if texto else None


# ---------------------------------------------------------------- linha do CSV -> modelo de dados
def montar_modelo(l):
    g = l.get
    m = {
        "titulo_pagina": g("titulo_pagina", "") or "Seu diagnóstico · Enem 2026",
        "topo_titulo": g("topo_titulo", ""),
        "rodape": g("rodape_texto", ""),
        "hero": {
            "titulo": g("hero_titulo", ""),
            "texto": g("hero_texto", ""),
            "cta": link(g("hero_cta_texto", ""), g("hero_cta_url", "")),
            "cta_nota": g("hero_cta_nota", ""),
        },
    }

    # Curso
    m["curso"] = None
    if g("curso_nome"):
        m["curso"] = {
            "ok": g("curso_ok", "").lower() in SIM,
            "opcao": g("curso_opcao", ""),
            "nome": g("curso_nome", ""),
            "ies_linha": g("curso_ies_linha", ""),
            "media": g("curso_media", ""),
            "media_arco": arco(g("curso_media", "")),
            "status": g("curso_status", ""),
            "distancia": g("curso_distancia", ""),
            "ref_texto": g("curso_ref_texto", ""),
            "ref_nota": g("curso_ref_nota", ""),
            "aviso": g("curso_aviso", ""),
        }

    # Alerta
    m["alerta"] = None
    if g("alerta_titulo"):
        m["alerta"] = {"eyebrow": g("alerta_eyebrow", ""), "titulo": g("alerta_titulo"), "texto": g("alerta_texto", "")}

    # Pontos fáceis
    m["faceis"] = None
    if g("faceis_titulo"):
        qs = []
        for i in slots(l, "facil"):
            p = f"facil{i}_"
            if not g(p + "num"):
                continue
            marcada = g(p + "marcada", "")
            qs.append({
                "num": g(p + "num"),
                "url": g(p + "url", ""),
                "titulo": g(p + "titulo", ""),
                "pct": g(p + "pct", ""),
                "branco": marcada == "",
                "marcada": marcada,
                "correta": g(p + "correta", ""),
                "engana": g(p + "engana", "") if marcada else "",
                "coelho": g(p + "coelho", ""),
                "modelo": g(p + "modelo", ""),
                "modelo_url": g(p + "modelo_url", ""),
            })
        if g("faceis_chips"):
            chips = [c.strip() for c in re.split(r"[|,;]", g("faceis_chips")) if c.strip()]
        else:
            chips = sorted((q["num"] for q in qs), key=lambda n: (numero(n) is None, numero(n) or 0, n))
        m["faceis"] = {
            "titulo": g("faceis_titulo"),
            "caderno": g("faceis_caderno", ""),
            "chips": chips,
            "questoes": qs,
            "rodape": g("faceis_rodape", ""),
        }

    # Modelos que caíram
    m["modelos"] = None
    if g("modelos_titulo"):
        grupos = []
        for i in slots(l, "modelo"):
            p = f"modelo{i}_"
            if not g(p + "num"):
                continue
            item = {
                "num": g(p + "num"),
                "titulo": g(p + "titulo", ""),
                "pct": g(p + "pct", ""),
                "fonte": g(p + "fonte", ""),
                "texto": g(p + "texto", ""),
                "aula_url": g(p + "aula_url", ""),
                "questao_url": g(p + "questao_url", ""),
                "ambos": bool(g(p + "aula_url")) and bool(g(p + "questao_url")),
            }
            rotulo = g(p + "grupo", "")
            if not grupos or grupos[-1]["rotulo"] != rotulo:
                grupos.append({"rotulo": rotulo, "aberto": False, "itens": []})
            grupos[-1]["itens"].append(item)
        if grupos and grupos[0]["rotulo"]:
            grupos[0]["aberto"] = True
        m["modelos"] = {
            "titulo": g("modelos_titulo"),
            "nota": g("modelos_nota", ""),
            "resumo": g("modelos_resumo", ""),
            "grupos": grupos,
        }

    # Plano por área (area1 = prioritária)
    m["plano"] = None
    areas = []
    for i in slots(l, "area"):
        p = f"area{i}_"
        cod = g(p + "codigo", "").upper()
        if not cod:
            continue
        areas.append({
            "codigo": cod,
            "nome": AREAS.get(cod, cod),
            "nota": g(p + "nota", ""),
            "arco": arco(g(p + "nota", "")),
            "acertos": g(p + "acertos", ""),
            "titulo": g(p + "titulo", ""),
            "texto": g(p + "texto", ""),
            "itens": [x.strip() for x in g(p + "itens", "").split("|") if x.strip()],
            "como": g(p + "como", ""),
        })
    if areas:
        m["plano"] = {
            "titulo": g("plano_titulo", ""),
            "nota": g("plano_nota", ""),
            "prio": areas[0],
            "outras": areas[1:],
            "tem_outras": len(areas) > 1,
        }

    # Nota parcial
    m["parcial"] = None
    barras = []
    for cod in ("LC", "CH", "CN", "MT"):
        v = g(f"parcial_{cod}", "")
        if not v:
            continue
        n = numero(v)
        barras.append({
            "codigo": cod,
            "nome": AREAS[cod],
            "valor": v,
            "bloq": n is None,
            "largura": 0 if n is None else round(max(0, min(100, (n - 300) / 700 * 100))),
        })
    if barras:
        m["parcial"] = {"barras": barras}

    # Cards de oferta
    m["cards"] = []
    for bloco, oferta in CARDS:
        p = bloco + "_"
        if not g(p + "titulo"):
            continue
        m["cards"].append({
            "bloco": bloco,
            "oferta": oferta,
            "eyebrow": g(p + "eyebrow", ""),
            "titulo": g(p + "titulo"),
            "texto1": g(p + "texto1", ""),
            "texto2": g(p + "texto2", ""),
            "nota": g(p + "nota", ""),
            "cta": link(g(p + "cta_texto", ""), g(p + "cta_url", "")),
            "cta2": link(g(p + "cta2_texto", ""), g(p + "cta2_url", "")),
            "link": link(g(p + "link_texto", ""), g(p + "link_url", "")),
            "nota_final": g(p + "nota_final", ""),
        })
    return m


# ---------------------------------------------------------------- execução
def logo(valor, padrao):
    alvo = valor or str(AQUI / "assets" / padrao)
    if re.match(r"^(https?:|data:)", alvo):
        return alvo
    dados = Path(alvo).read_bytes()
    return "data:image/png;base64," + base64.b64encode(dados).decode()


def nome_arquivo(aluno_id, i):
    base = re.sub(r"[^A-Za-z0-9_.-]+", "_", aluno_id or "").strip("_")
    return (base or f"linha_{i:05d}") + ".html"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", nargs="?", default=str(AQUI / "alunos.csv"))
    ap.add_argument("-t", "--template", default=str(AQUI / "template.html"))
    ap.add_argument("-o", "--saida", default=str(AQUI / "saida"))
    ap.add_argument("--logo-topo", default="", help="caminho ou URL do logo do topo (padrão: assets/logo_topo.png)")
    ap.add_argument("--logo-marca", default="", help="caminho ou URL do logo do rodapé (padrão: assets/logo_marca.png)")
    ap.add_argument("--json", action="store_true", help="grava também o modelo de dados de cada aluno")
    ap.add_argument("--sem-previa", action="store_true", help="não gera o _previa.html")
    a = ap.parse_args()

    tpl = Path(a.template).read_text(encoding="utf-8")
    arvore = _parse(tpl)
    logos = {"logo_topo": logo(a.logo_topo, "logo_topo.png"), "logo_marca": logo(a.logo_marca, "logo_marca.png")}
    saida = Path(a.saida)
    saida.mkdir(parents=True, exist_ok=True)

    linhas = ler_csv(a.csv)
    paginas = []
    for i, bruta in enumerate(linhas, 1):
        linha = aplicar_placeholders(bruta)
        modelo = montar_modelo(linha)
        pagina = _render(arvore, [{**modelo, **logos}])
        arq = nome_arquivo(linha.get("aluno_id"), i)
        (saida / arq).write_text(pagina, encoding="utf-8")
        if a.json:
            (saida / arq.replace(".html", ".json")).write_text(
                json.dumps(modelo, ensure_ascii=False, indent=2), encoding="utf-8")
        paginas.append((linha, pagina))

    if not a.sem_previa and paginas:
        cabeca = paginas[0][1].split("<body>", 1)[0]
        estilo_previa = ('<style>.nav{position:sticky;top:0;z-index:5;background:#081b50;display:flex;gap:4px;overflow-x:auto;padding:8px 10px}'
                         '.nav a{color:#fff;text-decoration:none;font:600 14px Inter,system-ui;padding:6px 10px;border-radius:999px;background:#ffffff1f;white-space:nowrap}'
                         '.sep{max-width:640px;margin:28px auto 0;padding:10px 16px;font:700 13px Inter,system-ui;color:#081b50;background:#ffffffcc;border-radius:12px}</style>')
        cabeca = cabeca.replace("</head>", estilo_previa + "</head>")
        nav, corpo = [], []
        for j, (linha, pagina) in enumerate(paginas):
            ancora = f"p{j}"
            curto = linha.get("grupo") or linha.get("aluno_id") or str(j + 1)
            rotulo = linha.get("rotulo_previa") or " · ".join(x for x in (linha.get("grupo"), linha.get("aluno_id"), linha.get("nome")) if x)
            nav.append(f'<a href="#{ancora}">{html.escape(curto)}</a>')
            miolo = pagina.split("<body>", 1)[1].rsplit("</body>", 1)[0]
            corpo.append(f'<div class="sep" id="{ancora}">{html.escape(rotulo)}</div>{miolo}')
        previa = cabeca + '<body><nav class="nav">' + "".join(nav) + "</nav>" + "".join(corpo) + "</body></html>\n"
        (saida / "_previa.html").write_text(previa, encoding="utf-8")

    print(f"{len(paginas)} página(s) gerada(s) em {saida}/")


if __name__ == "__main__":
    sys.exit(main())
