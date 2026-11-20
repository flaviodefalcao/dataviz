#!/usr/bin/env python3
"""
Monta a base_alunos.csv (1 linha por aluno) a partir dos exports do Matrix:

    --dia1      matrix-gabarito-2026-dia1-respostas-alunos-*.csv   (respostas, cor, língua, notas, acertos)
    --dia2      matrix-gabarito-2026-dia2-respostas-alunos-*.csv
    --sisu      matrix-opcoes-sisu-2026-*.csv                      (1ª e 2ª opção de curso)
    --cadastro  (opcional) aluno_id;nome;tipo_conta                (nome e pagante/gratuito; traz também os grupos M)

E de dados/gabarito.csv (gabarito por cor + numeração canônica: ver scripts/inferir_gabarito.py).

Também atualiza, a partir dos mesmos dados:
    dados/ref_cursos.csv     um curso+IES por linha: nota dos 10% mais bem colocados (P90 da média dos alunos
                             do Matrix que escolheram o curso em 1ª ou 2ª opção) e notas P90 por área
    dados/ref_questoes.csv   % de acerto e gabarito de todas as questões (mantém os textos já escritos)
    dados/ref_numeracao.csv  numeração de todas as cores
    dados/ref_modelos.csv    % de acerto dos modelos

Uso:
    python3 montar_base.py --dia1 dia1.csv --dia2 dia2.csv --sisu sisu.csv [--cadastro cadastro.csv] [-o base_alunos.csv]
"""
import argparse
import csv
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

AQUI = Path(__file__).resolve().parent
DADOS = AQUI / "dados"
AREAS = ["LC", "CH", "CN", "MT"]
DIA_DA_AREA = {"LC": 1, "CH": 1, "CN": 2, "MT": 2}
COL_NOTA = {"LC": "nota_linguagens", "CH": "nota_ciencias_humanas", "CN": "nota_ciencias_natureza", "MT": "nota_matematica"}
COL_ACERTOS = {a: c.replace("nota_", "acertos_") for a, c in COL_NOTA.items()}
BASE_COLS = ["aluno_id", "nome", "tipo_conta", "dia1_lancado", "dia2_lancado", "caderno_dia1", "caderno_dia2", "lingua",
             "nota_LC", "nota_CH", "nota_CN", "nota_MT", "acertos_LC", "acertos_CH", "acertos_CN", "acertos_MT", "media",
             "curso_id", "area_prioritaria", "area_mais_perto", "faceis_ids", "faceis_marcadas", "modelos_errados_ids"]
MINUSCULAS = {"de", "da", "do", "das", "dos", "e", "em", "para", "com", "a", "o", "na", "no"}
SIGLA_MASCULINA = ("IF", "CEFET", "ITA", "IME", "INSPER", "IMPA")


# ------------------------------------------------------------------ utilidades
def ler(caminho):
    texto = Path(caminho).read_text(encoding="utf-8-sig")
    cab = texto.split("\n", 1)[0]
    sep = ";" if cab.count(";") >= cab.count(",") else ","
    return [{(k or "").strip(): (v or "").strip() for k, v in l.items()} for l in csv.DictReader(texto.splitlines(), delimiter=sep)]


def gravar(caminho, cols, linhas):
    with open(caminho, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, cols, delimiter=";", extrasaction="ignore", restval="")
        w.writeheader()
        w.writerows(linhas)


def num(v):
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def fmt(n, casas=1):
    return "" if n is None else f"{n:.{casas}f}".rstrip("0").rstrip(".")


def p90(valores):
    v = sorted(valores)
    if not v:
        return None
    k = (len(v) - 1) * 0.9
    i = int(k)
    return v[i] + (v[min(i + 1, len(v) - 1)] - v[i]) * (k - i)


def titulo_curso(nome):
    palavras = nome.lower().split()
    return " ".join(p if (i and p in MINUSCULAS) else p[:1].upper() + p[1:] for i, p in enumerate(palavras))


def slug(texto):
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]+", "_", t.upper()).strip("_")


# ------------------------------------------------------------------ gabarito e numeração
class Gabarito:
    def __init__(self, caminho):
        self.mapa = {}       # (dia, cor, lingua, numero_caderno) -> (area, questao_id, gabarito)
        self.canonico = {}   # (questao_id, lingua) -> gabarito no Azul
        for r in ler(caminho):
            k = (int(r["dia"]), r["cor_caderno"], r["lingua"], int(r["numero_caderno"]))
            self.mapa[k] = (r["area"], int(r["questao_id"]), r["gabarito"])
        self.cores = {(d, c) for d, c, _, _ in self.mapa}

    def corrigir(self, dia, linha):
        """Devolve {(area, questao_id, lingua): (resposta, gabarito)} na numeração canônica."""
        cor, lingua = linha.get("cor_caderno", ""), linha.get("lingua", "")
        if (dia, cor) not in self.cores:
            return None
        out = {}
        for k, v in linha.items():
            if not re.fullmatch(r"q\d+", k):
                continue
            n = int(k[1:])
            lg = lingua if n <= 5 else ""
            m = self.mapa.get((dia, cor, lg, n))
            if m:
                out[(m[0], m[1], lg)] = (v, m[2])
        return out


# ------------------------------------------------------------------ principal
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dia1", required=True)
    ap.add_argument("--dia2", required=True)
    ap.add_argument("--sisu", required=True)
    ap.add_argument("--cadastro", default="", help="aluno_id;nome;tipo_conta (pagante/gratuito)")
    ap.add_argument("-o", "--saida", default=str(AQUI / "base_alunos.csv"))
    ap.add_argument("--dados", default=str(DADOS))
    ap.add_argument("--min-alunos-curso", type=int, default=10, help="mínimo de alunos do Matrix no curso+IES para ter comparação")
    ap.add_argument("--max-faceis", type=int, default=0, help="limita a quantidade de fáceis por aluno (0 = sem limite)")
    a = ap.parse_args()
    dados = Path(a.dados)
    gab = Gabarito(dados / "gabarito.csv")
    avisos = Counter()

    d1 = {r["aluno_id"]: r for r in ler(a.dia1)}
    d2 = {r["aluno_id"]: r for r in ler(a.dia2)}
    sisu = defaultdict(dict)
    for r in ler(a.sisu):
        sisu[r["user_id"]][r["opcao"]] = r
    cadastro = {r["aluno_id"]: r for r in ler(a.cadastro)} if a.cadastro else {}

    # ---- 1. correção na numeração canônica + % de acerto por questão
    correcoes = {}
    acertos_q, total_q = Counter(), Counter()
    for dia, base in ((1, d1), (2, d2)):
        for aid, r in base.items():
            c = gab.corrigir(dia, r)
            if c is None:
                avisos[f"dia {dia}: cor de caderno desconhecida ({r.get('cor_caderno') or 'vazia'})"] += 1
                continue
            correcoes.setdefault(aid, {}).update(c)
            for k, (resp, g) in c.items():
                if g == "ANULADA":
                    continue
                total_q[k] += 1
                acertos_q[k] += resp == g
    pct = {k: round(100 * acertos_q[k] / total_q[k]) for k in total_q}
    canon_gab = {(m[0], m[1], lg): m[2] for (dia, cor, lg, n), m in gab.mapa.items() if cor == "Azul"}

    # 15 fáceis por área (sem língua estrangeira e sem anuladas), por % de acerto decrescente
    faceis_area = {}
    for area in AREAS:
        qs = [k for k in pct if k[0] == area and not k[2]]
        faceis_area[area] = sorted(qs, key=lambda k: (-pct[k], k[1]))[:15]

    # ---- 2. notas, médias e cursos
    def notas_de(aid):
        n = {}
        for area in AREAS:
            r = (d1 if DIA_DA_AREA[area] == 1 else d2).get(aid, {})
            n[area] = num(r.get(COL_NOTA[area]))
        return n

    todos = sorted(set(d1) | set(d2) | set(cadastro))
    notas = {aid: notas_de(aid) for aid in todos}
    completos = {aid for aid in todos if all(v is not None for v in notas[aid].values())}
    media = {aid: sum(notas[aid].values()) / 4 for aid in completos}

    def curso_id_de(r):
        return slug(f"{r['curso']}_{r['sigla']}")

    cursos = {}
    coorte = defaultdict(set)
    for uid, ops in sisu.items():
        for r in ops.values():
            cid = curso_id_de(r)
            cursos.setdefault(cid, {"curso_id": cid, "curso": titulo_curso(r["curso"]), "ies": r["sigla"],
                                    "artigo_ies": "no" if r["sigla"].upper().startswith(SIGLA_MASCULINA) else "na",
                                    "eh_medicina": 1 if slug(r["curso"]) == "MEDICINA" else 0})
            if uid in completos:
                coorte[cid].add(uid)
    antigos = {r["curso_id"]: r for r in ler(dados / "ref_cursos.csv")} if (dados / "ref_cursos.csv").exists() else {}
    for cid, c in cursos.items():
        ids = coorte[cid]
        c["alunos_matrix"] = len(ids)
        ok = len(ids) >= a.min_alunos_curso
        c["nota_top10"] = fmt(p90([media[i] for i in ids])) if ok else ""
        for area in AREAS:
            c[f"p90_{area}"] = fmt(p90([notas[i][area] for i in ids])) if ok else ""
        for k in ("curso", "ies", "artigo_ies", "peso_LC", "peso_CH", "peso_CN", "peso_MT", "obs"):  # ajustes manuais (nome, sigla, artigo, pesos) são mantidos
            if antigos.get(cid, {}).get(k):
                c[k] = antigos[cid][k]
    geral_p90 = {area: p90([notas[i][area] for i in completos]) for area in AREAS}

    # ---- 3. uma linha por aluno
    modelos = defaultdict(list)
    for m in ler(dados / "ref_modelos.csv"):
        modelos[m["area"]].append(m)
    linhas = []
    for aid in todos:
        r1, r2 = d1.get(aid), d2.get(aid)
        cad = cadastro.get(aid, {})
        L = {c: "" for c in BASE_COLS}
        L.update(aluno_id=aid, nome=cad.get("nome", ""), tipo_conta=cad.get("tipo_conta", ""),
                 dia1_lancado="sim" if r1 else "nao", dia2_lancado="sim" if r2 else "nao",
                 caderno_dia1=(r1 or {}).get("cor_caderno", ""), caderno_dia2=(r2 or {}).get("cor_caderno", ""),
                 lingua=(r1 or {}).get("lingua", ""))
        if not L["nome"]:
            avisos["aluno sem nome (passe --cadastro)"] += 1
        for area in AREAS:
            r = r1 if DIA_DA_AREA[area] == 1 else r2
            if r:
                L[f"nota_{area}"] = fmt(notas[aid][area])
                L[f"acertos_{area}"] = r.get(COL_ACERTOS[area], "")
        if aid in completos:
            L["media"] = fmt(media[aid], 2)
            ops = sisu.get(aid, {})
            escolha = ops.get("1") or ops.get("2")
            c = cursos.get(curso_id_de(escolha)) if escolha else None
            if c and c["nota_top10"]:
                L["curso_id"] = c["curso_id"]
                ref = {area: num(c[f"p90_{area}"]) for area in AREAS}
                peso = {area: num(c.get(f"peso_{area}")) or 1.0 for area in AREAS}
            else:
                if c:
                    avisos[f"curso com menos de {a.min_alunos_curso} alunos no Matrix: tratado como sem curso (grupo E)"] += 1
                ref, peso = geral_p90, {area: 1.0 for area in AREAS}
            deficit = {area: (ref[area] - notas[aid][area]) * peso[area] for area in AREAS}
            prio = max(AREAS, key=lambda x: (deficit[x], -AREAS.index(x)))
            L["area_prioritaria"] = prio
            L["area_mais_perto"] = min((x for x in AREAS if x != prio), key=lambda x: (deficit[x], AREAS.index(x)))
            corr = correcoes.get(aid, {})
            erradas = [k for k in faceis_area[prio] if k in corr and corr[k][0] != corr[k][1]]
            if a.max_faceis:
                erradas = erradas[:a.max_faceis]
            L["faceis_ids"] = "|".join(str(k[1]) for k in erradas)
            L["faceis_marcadas"] = "|".join(corr[k][0] or "-" for k in erradas)
            L["modelos_errados_ids"] = "|".join(
                m["questao_id"] for m in modelos[prio]
                if (prio, int(m["questao_id"]), "") in corr and corr[(prio, int(m["questao_id"]), "")][0] != corr[(prio, int(m["questao_id"]), "")][1])
        linhas.append(L)
    gravar(a.saida, BASE_COLS, linhas)

    # ---- 4. tabelas de referência atualizadas
    gravar(dados / "ref_cursos.csv",
           ["curso_id", "curso", "ies", "artigo_ies", "eh_medicina", "nota_top10", "alunos_matrix"] + [f"p90_{x}" for x in AREAS]
           + [f"peso_{x}" for x in AREAS] + ["obs"],
           sorted(cursos.values(), key=lambda c: (-c["alunos_matrix"], c["curso_id"])))
    antigos_q = {int(r["questao_id"]): r for r in ler(dados / "ref_questoes.csv")}
    cols_q = ["questao_id", "area", "titulo", "pct_acerto", "gabarito", "facil_top15"] + [f"engana_{x}" for x in "ABCDE"] + ["coelho", "modelo_rotulo", "modelo_url"]
    qs = []
    top = {k for v in faceis_area.values() for k in v}
    for k in sorted(pct, key=lambda k: (AREAS.index(k[0]), k[1])):
        if k[2]:
            continue  # língua estrangeira fica fora (ingles/espanhol têm questões diferentes)
        q = dict(antigos_q.get(k[1], {}))
        q.update(questao_id=k[1], area=k[0], pct_acerto=pct[k], gabarito=canon_gab.get(k, ""), facil_top15=1 if k in top else "")
        qs.append(q)
    gravar(dados / "ref_questoes.csv", cols_q, qs)
    gravar(dados / "ref_numeracao.csv", ["cor_caderno", "area", "numero_caderno", "questao_id"],
           [{"cor_caderno": cor, "area": m[0], "numero_caderno": n, "questao_id": m[1]}
            for (dia, cor, lg, n), m in sorted(gab.mapa.items(), key=lambda x: (x[0][1], x[0][3])) if not lg])
    ms = ler(dados / "ref_modelos.csv")
    for m in ms:
        m["pct_acerto"] = pct.get((m["area"], int(m["questao_id"]), ""), m["pct_acerto"])
    gravar(dados / "ref_modelos.csv", list(ms[0].keys()), ms)

    # ---- 5. resumo
    sem_texto = [k for k in top if not antigos_q.get(k[1], {}).get("titulo")]
    print(f"{len(linhas)} alunos -> {a.saida}")
    print(f"dia 1: {len(d1)} · dia 2: {len(d2)} · os dois completos: {len(completos)} · com curso válido: {sum(1 for l in linhas if l['curso_id'])}")
    print(f"{len(cursos)} cursos+IES · {sum(1 for c in cursos.values() if c['nota_top10'])} com {a.min_alunos_curso}+ alunos (têm nota dos 10%)")
    print("área prioritária:", dict(Counter(l["area_prioritaria"] for l in linhas if l["area_prioritaria"])))
    for msg, n in avisos.most_common():
        print(f"AVISO {msg}: {n}")
    if sem_texto:
        print(f"AVISO {len(sem_texto)} das 60 questões fáceis ainda sem texto (titulo/engana/coelho) em ref_questoes.csv: "
              + ", ".join(f"{k[0]} {k[1]}" for k in sorted(sem_texto)))


if __name__ == "__main__":
    sys.exit(main())
