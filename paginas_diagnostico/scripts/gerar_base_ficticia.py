#!/usr/bin/env python3
"""
Gera uma base_alunos.csv FICTÍCIA, com a mesma quantidade de alunos por grupo da prévia (81.550),
para testar o fluxo completo (montar_csv.py -> gerar.py) antes de ter o export real.

  * nomes, notas, respostas: inventados (seed fixa, sempre a mesma saída);
  * cada aluno é construído para cair no grupo pedido pela regra do montar_csv.py;
  * só usa questões, cursos e numerações que existem em dados/, para não gerar aviso.

NÃO é dado real. Para produção, troque por um export do banco no mesmo formato (ver COMO_GERAR.md).

Uso:  python3 scripts/gerar_base_ficticia.py [-o base_alunos_ficticia.csv] [--escala 1.0] [--seed 2026]
"""
import argparse
import csv
import random
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
import montar_csv as M  # noqa: E402

CONTAGEM = {"A": 4770, "A_topo": 1457, "A0": 486, "B": 2025, "C": 10035, "D": 1842, "E": 17496,
            "F": 21377, "G": 11337, "H": 214, "M_aluno": 2469, "M_gratis": 8042}
FAIXA_DIST = {"A0": (-4.75, 4.75), "D": (-90, -5), "A_topo": (5, 19.75), "A": (20, 60), "B": (60.25, 220), "C": (60.25, 220)}
NOMES = ("Ana Beatriz Bruno Camila Carlos Daniela Eduardo Fernanda Gabriel Giovana Gustavo Helena Isabela João "
         "Júlia Larissa Leonardo Letícia Lucas Luiza Marcos Maria Mariana Mateus Miguel Natália Pedro Rafael "
         "Rafaela Sofia Thiago Valentina Vinícius Yasmin").split()
DIA = {"LC": 1, "CH": 1, "CN": 2, "MT": 2}
COLS = ["aluno_id", "nome", "tipo_conta", "dia1_lancado", "dia2_lancado", "caderno_dia1", "caderno_dia2", "lingua",
        "nota_LC", "nota_CH", "nota_CN", "nota_MT", "acertos_LC", "acertos_CH", "acertos_CN", "acertos_MT", "media",
        "curso_id", "area_prioritaria", "area_mais_perto", "faceis_ids", "faceis_marcadas", "modelos_errados_ids"]


def acertos_de(nota, rnd):
    return max(3, min(45, round((nota - 330) / 13 + rnd.uniform(-2, 2))))


class Fabrica:
    def __init__(self, refs, rnd):
        self.r, self.rnd = refs, rnd
        cursos = list(refs.cursos.values())
        self.medicina = [c for c in cursos if c["eh_medicina"] in ("1", "sim")]
        self.outros = [c for c in cursos if c["eh_medicina"] not in ("1", "sim")]
        # questões fáceis e modelos utilizáveis por (área, cor): precisam de número naquele caderno
        self.cores = {}
        for a in M.ORDEM_AREAS:
            for cor in ("Amarelo", "Azul"):
                faceis = sorted((q for q in refs.questoes.values() if q["area"] == a and refs.numeracao.get((cor, int(q["questao_id"])))),
                                key=lambda q: (-int(q["pct_acerto"]), int(q["questao_id"])))
                mods = [m for m in refs.modelos.get(a, []) if refs.numeracao.get((cor, int(m["questao_id"])))]
                if faceis and len(mods) == len(refs.modelos.get(a, [])):
                    self.cores.setdefault(a, []).append(cor)
        self.areas_prio = sorted(self.cores)  # só áreas com conteúdo completo em dados/

    def notas_com_media(self, alvo):
        rnd = self.rnd
        while True:
            n = {a: round(alvo + rnd.gauss(0, 55)) for a in M.ORDEM_AREAS}
            ajuste = round(alvo * 4 - sum(n.values()))
            n["MT"] += ajuste
            if all(320 <= v <= 990 for v in n.values()):
                return n

    def diagnostico(self, linha, notas, prio):
        rnd, r = self.rnd, self.r
        cor = rnd.choice(self.cores[prio])
        linha[f"caderno_dia{DIA[prio]}"] = cor
        outro_dia = 2 if DIA[prio] == 1 else 1
        linha[f"caderno_dia{outro_dia}"] = rnd.choice(["Amarelo", "Azul", "Branco", "Rosa"])
        ac = int(linha[f"acertos_{prio}"])
        p_erro = max(0.03, (45 - ac) / 45)
        faceis = sorted((q for q in r.questoes.values() if q["area"] == prio and r.numeracao.get((cor, int(q["questao_id"])))),
                        key=lambda q: (-int(q["pct_acerto"]), int(q["questao_id"])))
        erradas = [q for q in faceis if rnd.random() < p_erro * (1.4 - int(q["pct_acerto"]) / 100)][:5]
        marcadas = []
        for q in erradas:
            com_texto = [l for l in "ABCDE" if l != q["gabarito"] and q.get(f"engana_{l}")]
            if rnd.random() < 0.06:
                marcadas.append("-")
            elif com_texto and rnd.random() < 0.8:
                marcadas.append(rnd.choice(com_texto))
            else:
                marcadas.append(rnd.choice([l for l in "ABCDE" if l != q["gabarito"]]))
        linha["faceis_ids"] = "|".join(q["questao_id"] for q in erradas)
        linha["faceis_marcadas"] = "|".join(marcadas)
        mods = r.modelos[prio]
        linha["modelos_errados_ids"] = "|".join(m["questao_id"] for m in mods if rnd.random() < min(0.97, p_erro + 0.45))
        linha["area_prioritaria"] = prio

    def aluno(self, i, grupo):
        rnd = self.rnd
        L = {c: "" for c in COLS}
        L.update(aluno_id=f"ficticio_{i:06d}", nome=rnd.choice(NOMES), lingua=rnd.choice(["ingles", "espanhol"]))
        if grupo.startswith("M_"):
            L.update(tipo_conta="pagante" if grupo == "M_aluno" else "gratuito", dia1_lancado="nao", dia2_lancado="nao")
            return L
        L["tipo_conta"] = "pagante" if rnd.random() < 0.15 else "gratuito"
        L["dia1_lancado"], L["dia2_lancado"] = ("sim", "nao") if grupo == "F" else ("nao", "sim") if grupo == "G" else ("sim", "sim")
        if grupo in FAIXA_DIST:
            curso = rnd.choice(self.outros if grupo == "C" else self.medicina)
            dist = rnd.uniform(*FAIXA_DIST[grupo])
            notas = self.notas_com_media(float(curso["nota_top10"]) - dist)
            L["curso_id"] = curso["curso_id"]
        else:
            notas = self.notas_com_media(rnd.uniform(480, 760))
        for a in M.ORDEM_AREAS:
            if L[f"dia{DIA[a]}_lancado"] == "sim":
                L[f"nota_{a}"] = notas[a]
                L[f"acertos_{a}"] = acertos_de(notas[a], rnd)
        if grupo == "H":
            vazia = rnd.choice(M.ORDEM_AREAS)
            L[f"nota_{vazia}"] = ""
        if grupo in ("F", "G", "H"):
            return L
        L["media"] = f"{sum(notas.values()) / 4:g}"
        prio = min(self.areas_prio, key=lambda a: notas[a]) if rnd.random() < 0.7 else rnd.choice(self.areas_prio)
        self.diagnostico(L, notas, prio)
        if grupo == "B":
            L["area_mais_perto"] = max((a for a in M.ORDEM_AREAS if a != prio), key=lambda a: notas[a])
        return L


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--saida", default=str(RAIZ / "base_alunos_ficticia.csv"))
    ap.add_argument("--escala", type=float, default=1.0, help="0.01 = 1%% da base (teste rápido)")
    ap.add_argument("--seed", type=int, default=2026)
    a = ap.parse_args()
    refs = M.Refs()
    rnd = random.Random(a.seed)
    fab = Fabrica(refs, rnd)
    fila = [g for g, n in CONTAGEM.items() for _ in range(max(1, round(n * a.escala)))]
    rnd.shuffle(fila)
    linhas = []
    for i, g in enumerate(fila, 1):
        for _ in range(50):  # reamostra se o arredondamento empurrar o aluno para outro grupo
            L = fab.aluno(i, g)
            if M.classificar(L, refs)[0] == g:
                break
        else:
            raise SystemExit(f"não consegui gerar um aluno do grupo {g}")
        linhas.append(L)
    with open(a.saida, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, COLS, delimiter=";")
        w.writeheader()
        w.writerows(linhas)
    print(f"{len(linhas)} alunos fictícios -> {a.saida}  (áreas prioritárias usadas: {', '.join(fab.areas_prio)})")


if __name__ == "__main__":
    main()
