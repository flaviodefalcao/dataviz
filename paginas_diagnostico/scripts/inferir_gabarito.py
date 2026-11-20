#!/usr/bin/env python3
"""
Infere o gabarito de cada cor de caderno e a numeração canônica (= caderno Azul) a partir dos exports de respostas.

Por que existe: os exports trazem as respostas e o número de acertos de cada aluno, mas não o gabarito
nem a correspondência de numeração entre as cores. Os dois saem dos próprios dados:

  1. Gabarito: para cada cor e área, escolhe a letra de cada questão que faz o acerto calculado bater com
     o `acertos_<area>` informado. Começa pela resposta mais marcada e faz busca local (inclui "anulada").
     Resultado esperado: 100% dos alunos batendo. O script avisa se não bater.
  2. Numeração: dentro de cada área, casa as questões de cada cor com as do Azul pelo perfil de respostas
     (proporção de A, B, C, D, E e branco) e pelo gabarito, com o algoritmo húngaro.
     Cores com o mesmo gabarito de outra maior (ex.: Marrom = prova adaptada) herdam a numeração dela.

Grava dados/gabarito.csv:
  dia;cor_caderno;lingua;numero_caderno;area;questao_id;gabarito;confianca
  - lingua só nas questões 1–5 (língua estrangeira); questao_id = número no Azul
  - gabarito = A–E ou ANULADA
  - confianca = distância entre os perfis (0 = idêntico). Acima de ~0,3, conferir.

Se você tiver o gabarito oficial, pode montar dados/gabarito.csv à mão no mesmo formato e pular este script.

Uso:  python3 scripts/inferir_gabarito.py --dia1 dia1.csv --dia2 dia2.csv     (~10 min)
"""
import argparse
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
LETRAS = "ABCDE"
CANONICA = "Azul"
AREAS = {
    1: [("LC", "acertos_linguagens", range(1, 46)), ("CH", "acertos_ciencias_humanas", range(46, 91))],
    2: [("CN", "acertos_ciencias_natureza", range(91, 136)), ("MT", "acertos_matematica", range(136, 181))],
}


def ler(caminho):
    return list(csv.DictReader(Path(caminho).read_text(encoding="utf-8-sig").splitlines(), delimiter=";"))


def chave(r, q):
    """Questões 1–5 dependem da língua estrangeira."""
    return f"{q}_{r.get('lingua', '')}" if q <= 5 else str(q)


# ------------------------------------------------------------------ 1. gabarito
def resolver_gabarito(rs, col, faixa):
    rs = [r for r in rs if r[col]]
    alvo = [int(r[col]) for r in rs]
    ids = sorted({chave(r, q) for r in rs for q in faixa})
    marc = {i: {L: [] for L in LETRAS} for i in ids}
    for k, r in enumerate(rs):
        for q in faixa:
            v = r[f"q{q}"]
            if v in LETRAS and v:
                marc[chave(r, q)][v].append(k)

    def descida(G):
        res = list(alvo)
        for i in ids:
            if G[i] != "X":
                for k in marc[i][G[i]]:
                    res[k] -= 1
        for _ in range(60):
            mudou = 0
            for i in ids:
                antes = G[i]
                if antes != "X":
                    for k in marc[i][antes]:
                        res[k] += 1
                melhor = ("X", 0)
                for L in LETRAS:
                    ganho = sum(1 - 2 * res[k] for k in marc[i][L])
                    if ganho < melhor[1]:
                        melhor = (L, ganho)
                G[i] = melhor[0]
                if G[i] != "X":
                    for k in marc[i][G[i]]:
                        res[k] -= 1
                mudou += G[i] != antes
            if not mudou:
                break
        return G, sum(x * x for x in res), sum(1 for x in res if x == 0)

    G, obj, ok = descida({i: max(LETRAS, key=lambda L: len(marc[i][L])) for i in ids})
    while obj > 0:  # busca local em pares: anular uma questão / desanular outra
        cands = [(i, "X") for i in ids if G[i] != "X"] + [(i, L) for i in ids if G[i] == "X" for L in LETRAS]
        melhor = None
        for i, L in cands:
            H, o, k = descida({**G, i: L})
            if o < obj and (melhor is None or o < melhor[1]):
                melhor = (H, o, k)
        if not melhor:
            break
        G, obj, ok = melhor
    return G, ok / max(1, len(alvo)), len(alvo)


# ------------------------------------------------------------------ 2. numeração
def hungaro(custo):
    n = len(custo)
    INF = float("inf")
    u, v, p, way = [0] * (n + 1), [0] * (n + 1), [0] * (n + 1), [0] * (n + 1)
    for i in range(1, n + 1):
        p[0], j0 = i, 0
        minv, usado = [INF] * (n + 1), [False] * (n + 1)
        while True:
            usado[j0] = True
            i0, d, j1 = p[j0], INF, 0
            for j in range(1, n + 1):
                if not usado[j]:
                    cur = custo[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j], way[j] = cur, j0
                    if minv[j] < d:
                        d, j1 = minv[j], j
            for j in range(n + 1):
                if usado[j]:
                    u[p[j]] += d
                    v[j] -= d
                else:
                    minv[j] -= d
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    res = [0] * n
    for j in range(1, n + 1):
        res[p[j] - 1] = j - 1
    return res


def perfil(rs, q, lingua=None):
    c = Counter(r[f"q{q}"] for r in rs if lingua is None or r.get("lingua") == lingua)
    n = sum(c.values()) or 1
    return [c.get(L, 0) / n for L in LETRAS] + [c.get("", 0) / n]


def casar(rs_cor, rs_azul, G_cor, G_azul, qs, lingua=None):
    pc = {q: perfil(rs_cor, q, lingua) for q in qs}
    pa = {q: perfil(rs_azul, q, lingua) for q in qs}
    k = (lambda q: f"{q}_{lingua}") if lingua else str
    custo = [[sum(abs(a - b) for a, b in zip(pc[qc], pa[qa])) + (0 if G_cor.get(k(qc)) == G_azul.get(k(qa)) else 5)
              for qa in qs] for qc in qs]
    m = hungaro(custo)
    return {qc: (qs[m[i]], custo[i][m[i]]) for i, qc in enumerate(qs)}


# ------------------------------------------------------------------ execução
def processar_dia(dia, linhas, saida):
    por_cor = defaultdict(list)
    for r in linhas:
        if r["cor_caderno"]:
            por_cor[r["cor_caderno"]].append(r)
    G = defaultdict(dict)
    for cor, rs in sorted(por_cor.items(), key=lambda x: -len(x[1])):
        for area, col, faixa in AREAS[dia]:
            g, ok, n = resolver_gabarito(rs, col, faixa)
            G[cor].update(g)
            print(f"  dia {dia} {cor:<8} {area}: {n} alunos, acertos batem em {100 * ok:.2f}%", "" if ok == 1 else "  << CONFERIR")
    if CANONICA not in G:
        raise SystemExit(f"Sem caderno {CANONICA} no dia {dia}: não há como definir a numeração canônica.")
    # cores pequenas com o mesmo gabarito de uma maior herdam a numeração dela
    equivalente = {}
    cores = sorted(G, key=lambda c: -len(por_cor[c]))
    for c in cores:
        for maior in cores:
            if maior == c or len(por_cor[maior]) <= len(por_cor[c]):
                continue
            iguais = sum(G[c].get(k) == G[maior].get(k) for k in G[c])
            if iguais >= 0.95 * len(G[c]):
                equivalente[c] = maior
                print(f"  dia {dia} {c} tem o gabarito de {maior} ({iguais}/{len(G[c])}): usa a numeração dela")
                break
    mapa = {}
    for cor in cores:
        base = equivalente.get(cor, cor)
        for area, _, faixa in AREAS[dia]:
            qs = [q for q in faixa if q > 5]
            for qc, (qa, c) in casar(por_cor[base], por_cor[CANONICA], G[base], G[CANONICA], qs).items():
                mapa[(cor, "", qc)] = (area, qa, c)
            if dia == 1:
                for lg in ("ingles", "espanhol"):
                    for qc, (qa, c) in casar(por_cor[base], por_cor[CANONICA], G[base], G[CANONICA], list(range(1, 6)), lg).items():
                        mapa[(cor, lg, qc)] = ("LC", qa, c)
    for (cor, lg, qc), (area, qa, c) in sorted(mapa.items(), key=lambda x: (x[0][0], x[0][2], x[0][1])):
        g = G[cor].get(f"{qc}_{lg}" if lg else str(qc), "X")
        saida.append({"dia": dia, "cor_caderno": cor, "lingua": lg, "numero_caderno": qc, "area": area, "questao_id": qa,
                      "gabarito": "ANULADA" if g == "X" else g, "confianca": f"{c:.3f}"})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dia1", required=True)
    ap.add_argument("--dia2", required=True)
    ap.add_argument("-o", "--saida", default=str(RAIZ / "dados" / "gabarito.csv"))
    a = ap.parse_args()
    linhas = []
    for dia, arq in ((1, a.dia1), (2, a.dia2)):
        print(f"Dia {dia}: {arq}", flush=True)
        processar_dia(dia, ler(arq), linhas)
    with open(a.saida, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, list(linhas[0].keys()), delimiter=";")
        w.writeheader()
        w.writerows(linhas)
    print(f"{len(linhas)} linhas -> {a.saida}")


if __name__ == "__main__":
    sys.exit(main())
