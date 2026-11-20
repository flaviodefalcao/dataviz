#!/usr/bin/env python3
"""
Extrai as tabelas de referência e a base compacta a partir das 14 linhas de exemplo (alunos.csv).

Serve para duas coisas:
  1. dar um ponto de partida para as tabelas de dados (questões, numeração, modelos, textos do plano);
  2. montar testes/base_exemplos.csv, a base compacta dos 14 exemplos, usada no teste de regressão.

Uso:  python3 scripts/extrair_dos_exemplos.py [alunos.csv]
Grava em dados/ e testes/. Não sobrescreve dados/ref_cursos.csv nem dados/ref_areas.csv se já existirem.
"""
import csv
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
AREA_SLUG = {"linguagens": "LC", "ciencias-humanas": "CH", "ciencias-natureza": "CN", "matematica": "MT"}
NOME_AREA = {"Linguagens": "LC", "Humanas": "CH", "Natureza": "CN", "Matemática": "MT"}
DIA = {"LC": 1, "CH": 1, "CN": 2, "MT": 2}


def ler(c):
    return list(csv.DictReader(Path(c).read_text(encoding="utf-8-sig").splitlines(), delimiter=";"))


def gravar(caminho, cols, linhas):
    with open(caminho, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, cols, delimiter=";", extrasaction="ignore")
        w.writeheader()
        w.writerows(linhas)


def canon(url):
    m = re.search(r"/(linguagens|ciencias-humanas|ciencias-natureza|matematica)/questao-(\d+)", url or "")
    return (AREA_SLUG[m.group(1)], int(m.group(2))) if m else (None, None)


def slots(r, p):
    return sorted({int(m.group(1)) for k in r for m in [re.match(rf"{p}(\d+)_", k)] if m})


def main():
    exemplos = ler(sys.argv[1] if len(sys.argv) > 1 else RAIZ / "alunos.csv")
    Q, NUM, MOD, PLANO = {}, set(), {}, {}
    base = []
    for r in exemplos:
        g = r["grupo"]
        cor = r["faceis_caderno"]
        if g.startswith("M_"):
            cor = "Azul"  # "Números do caderno Azul"
        faceis, marcadas, modelos = [], [], []
        for i in slots(r, "facil"):
            p = f"facil{i}_"
            if not r[p + "num"]:
                continue
            area, qid = canon(r[p + "url"])
            NUM.add((cor, area, int(r[p + "num"]), qid))
            q = Q.setdefault(qid, {"questao_id": qid, "area": area, "titulo": r[p + "titulo"], "pct_acerto": r[p + "pct"],
                                   "gabarito": r[p + "correta"], "coelho": "", "modelo_rotulo": "", "modelo_url": ""})
            if r[p + "marcada"] and r[p + "engana"]:
                q["engana_" + r[p + "marcada"]] = r[p + "engana"]
            if r[p + "coelho"]:
                q["coelho"] = r[p + "coelho"]
            if r[p + "modelo"]:
                q["modelo_rotulo"], q["modelo_url"] = r[p + "modelo"], r[p + "modelo_url"]
            faceis.append(str(qid))
            marcadas.append(r[p + "marcada"] or "-")
        for i in slots(r, "modelo"):
            p = f"modelo{i}_"
            if not r[p + "num"]:
                continue
            area, qid = canon(r[p + "questao_url"])
            NUM.add((cor, area, int(r[p + "num"]), qid))
            MOD.setdefault(qid, {"questao_id": qid, "area": area, "titulo": r[p + "titulo"], "pct_acerto": r[p + "pct"],
                                 "fonte": r[p + "fonte"], "texto": r[p + "texto"], "aula_url": r[p + "aula_url"]})
            if not g.startswith("M_"):
                modelos.append(str(qid))
        for i in slots(r, "area"):
            p = f"area{i}_"
            if not r[p + "codigo"]:
                continue
            k = (r[p + "codigo"], r[p + "titulo"])
            e = PLANO.setdefault(k, {"area": k[0], "titulo": k[1], "texto": r[p + "texto"], "itens": r[p + "itens"],
                                     "como": r[p + "como"], "vistos": set()})
            e["vistos"].add(int(r[p + "acertos"]))

        # ---- base compacta do exemplo
        notas = {a: "" for a in DIA}
        acertos = {a: "" for a in DIA}
        for i in slots(r, "area"):
            p = f"area{i}_"
            if r[p + "codigo"]:
                notas[r[p + "codigo"]] = r[p + "nota"]
                acertos[r[p + "codigo"]] = r[p + "acertos"]
        for a in DIA:
            v = r.get(f"parcial_{a}", "")
            if re.fullmatch(r"\d+([.,]\d+)?", v):
                notas[a] = v
        prio = r["area1_codigo"]
        if not prio and g.startswith(("A", "B", "C", "D", "E")):
            prio = ""
        lancou = {1: "sim", 2: "sim"}
        for a in DIA:
            if r.get(f"parcial_{a}") == "falta lançar":
                lancou[DIA[a]] = "nao"
        if g.startswith("M_"):
            lancou = {1: "nao", 2: "nao"}
        cad = {1: "", 2: ""}
        if prio and r["faceis_caderno"]:
            cad[DIA[prio]] = r["faceis_caderno"]
        curso = r["curso_nome"] or (re.search(r"dessa vez em ([^.]+)\.", r["hero_titulo"]) or [None, ""])[1]
        ies = r["curso_ies_linha"].split(" · ")[0] or (re.search(r"colocados n[ao] (\S+?)\.", r["hero_texto"]) or [None, ""])[1]
        curso_id = re.sub(r"\W+", "_", f"{curso}_{ies}".upper()) if curso and ies else ""
        perto = (re.search(r"em (\w+), você está mais perto", r["hero_texto"]) or [None, ""])[1]
        media = ""
        if all(notas.values()):
            mm = sum(float(v) for v in notas.values()) / 4
            exibida = r["curso_media"] or (re.search(r"Sua média é (\d+)", r["hero_titulo"]) or [None, None])[1]
            media = f"{mm:g}" if (not exibida or round(mm) == int(exibida)) else exibida
        base.append({
            "aluno_id": r["aluno_id"], "nome": r["nome"],
            "tipo_conta": {"M_aluno": "pagante", "M_gratis": "gratuito"}.get(g, ""),
            "dia1_lancado": lancou[1], "dia2_lancado": lancou[2],
            "caderno_dia1": cad[1], "caderno_dia2": cad[2], "lingua": "",
            **{f"nota_{a}": notas[a] for a in DIA}, **{f"acertos_{a}": acertos[a] for a in DIA},
            "media": media, "curso_id": curso_id,
            "area_prioritaria": prio, "area_mais_perto": NOME_AREA.get(perto, ""),
            "faceis_ids": "|".join(faceis), "faceis_marcadas": "|".join(marcadas),
            "modelos_errados_ids": "|".join(modelos),
            "_grupo_exemplo": g,
        })

    d = RAIZ / "dados"
    gravar(d / "ref_questoes.csv",
           ["questao_id", "area", "titulo", "pct_acerto", "gabarito"] + [f"engana_{l}" for l in "ABCDE"] + ["coelho", "modelo_rotulo", "modelo_url"],
           sorted(Q.values(), key=lambda q: (q["area"], -int(q["pct_acerto"]), q["questao_id"])))
    mods = sorted(MOD.values(), key=lambda m: ("CN MT LC CH".split().index(m["area"]), int(m["pct_acerto"]), m["questao_id"]))
    ordem = {}
    for m in mods:
        ordem[m["area"]] = ordem.get(m["area"], 0) + 1
        m["ordem"] = ordem[m["area"]]
    gravar(d / "ref_modelos.csv", ["questao_id", "area", "ordem", "titulo", "pct_acerto", "fonte", "texto", "aula_url"], mods)
    gravar(d / "ref_numeracao.csv", ["cor_caderno", "area", "numero_caderno", "questao_id"],
           [dict(cor_caderno=c, area=a, numero_caderno=n, questao_id=q) for c, a, n, q in sorted(NUM)])
    pl, cont = [], {}
    for v in sorted(PLANO.values(), key=lambda v: (v["area"], min(v["vistos"]))):
        cont[v["area"]] = cont.get(v["area"], 0) + 1
        pl.append({**v, "faixa": cont[v["area"]], "acertos_vistos": "|".join(map(str, sorted(v["vistos"])))})
    if not (d / "textos_plano.csv").exists():
        gravar(d / "textos_plano.csv", ["area", "faixa", "acertos_min", "acertos_max", "titulo", "texto", "itens", "como", "acertos_vistos"], pl)
    gravar(RAIZ / "testes" / "base_exemplos.csv", list(base[0].keys()), base)
    print(f"{len(Q)} questões, {len(mods)} modelos, {len(NUM)} numerações, {len(pl)} faixas, {len(base)} exemplos")


if __name__ == "__main__":
    main()
