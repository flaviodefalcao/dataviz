#!/usr/bin/env python3
"""
Monta o alunos.csv completo (324 colunas, o formato que o gerar.py lê) a partir de:

    base_alunos.csv            1 linha por aluno, só os dados do aluno (~23 colunas)
    dados/ref_questoes.csv     conteúdo de cada questão (tema, % de acerto, gabarito, "por que a X engana", coelho)
    dados/ref_numeracao.csv    número no caderno de cada cor  <->  número canônico (link do Matrix)
    dados/ref_modelos.csv      as 20 questões modelo
    dados/textos_plano.csv     textos do plano por área x faixa de acertos
    dados/ref_cursos.csv       curso + IES: nota dos 10% mais bem colocados, se é Medicina, artigo (na/no)
    dados/ref_areas.csv        nome da área, pontos médios de uma fácil e de uma difícil
    dados/grupos.csv           regra de cada grupo: quais camadas de copy ele usa
    dados/copy.csv             todos os textos fixos, com {variáveis}
    dados/colunas.txt          as colunas do alunos.csv, na ordem

Uso:
    python3 montar_csv.py base_alunos.csv                      # grava alunos.csv
    python3 montar_csv.py base_alunos.csv -o saida.csv --bf-aberta --fase2-aberta --dominio www.exemplo.com.br
    python3 gerar.py alunos.csv

Só biblioteca padrão. Determinístico: a mesma entrada gera sempre a mesma saída.
"""
import argparse
import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

AQUI = Path(__file__).resolve().parent
DADOS = AQUI / "dados"
ORDEM_AREAS = ["LC", "CH", "CN", "MT"]
UTM = "utm_source=pagina&utm_medium=diagnostico&utm_campaign=bf2026"
MATRIX = "https://matrix.chapeudomago.com.br/enem/2026/regular/{slug}/questao-{qid}?" + UTM + "&utm_content=questao"
LIMITE_ENGANA = 180
FACIL_CAMPOS = ["num", "url", "titulo", "pct", "marcada", "correta", "engana", "coelho", "modelo", "modelo_url"]


# ------------------------------------------------------------------ leitura
def ler_csv(caminho):
    texto = Path(caminho).read_text(encoding="utf-8-sig")
    cab = texto.split("\n", 1)[0]
    sep = ";" if cab.count(";") >= cab.count(",") else ","
    return [{(k or "").strip(): (v or "").strip() for k, v in l.items()}
            for l in csv.DictReader(texto.splitlines(), delimiter=sep)]


CANONICA = "Azul"  # o número canônico (link do Matrix) é o número no caderno Azul


class Refs:
    def __init__(self, pasta=DADOS):
        p = Path(pasta)
        self.questoes = {int(r["questao_id"]): r for r in ler_csv(p / "ref_questoes.csv")}
        self.numeracao = {(r["cor_caderno"], int(r["questao_id"])): r["numero_caderno"] for r in ler_csv(p / "ref_numeracao.csv")}
        self.modelos = defaultdict(list)
        for r in ler_csv(p / "ref_modelos.csv"):
            self.modelos[r["area"]].append(r)
        for a in self.modelos:
            self.modelos[a].sort(key=lambda r: int(r["ordem"]))
        self.plano = defaultdict(list)
        for r in ler_csv(p / "textos_plano.csv"):
            self.plano[r["area"]].append(r)
        self.numeracao = _NumeracaoComAzul(self.numeracao)
        self.cursos = {r["curso_id"]: r for r in ler_csv(p / "ref_cursos.csv")}
        self.areas = {r["area"]: r for r in ler_csv(p / "ref_areas.csv")}
        self.grupos = {r["grupo"]: r for r in ler_csv(p / "grupos.csv")}
        self.copy = defaultdict(dict)
        for r in ler_csv(p / "copy.csv"):
            self.copy[r["camada"]][r["campo"]] = r["texto"]
        self.colunas = [c for c in (p / "colunas.txt").read_text(encoding="utf-8").split("\n") if c]


class _NumeracaoComAzul(dict):
    """No caderno Azul o número é o próprio número canônico, então não precisa estar na tabela."""
    def get(self, chave, padrao=None):
        if chave in self:
            return self[chave]
        return str(chave[1]) if chave[0] == CANONICA else padrao


# ------------------------------------------------------------------ utilidades
def num(v):
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def inteiro(v):
    """Arredonda para o inteiro mais próximo (0,5 vai para o par, como na prévia: 752,5 -> 752)."""
    n = num(v)
    return "" if n is None else str(int(round(n)))


def lista(v):
    return [x.strip() for x in (v or "").split("|") if x.strip()]


def cortar(texto, limite=LIMITE_ENGANA):
    if len(texto) <= limite + 1:  # +1: o texto já cortado termina em "…"
        return texto
    corte = texto[:limite].rsplit(" ", 1)[0].rstrip(" ,;:.—–-")
    return corte + "…"


def preencher(texto, var):
    """Troca {variavel} pelos valores calculados. O que não for variável (ex.: {nome}) fica para o gerar.py."""
    return re.sub(r"\{([a-z_0-9]+)\}", lambda m: str(var[m.group(1)]) if m.group(1) in var else m.group(0), texto)


# ------------------------------------------------------------------ regras
def classificar(a, refs):
    """Devolve (grupo, distância). distância = nota_top10 − média."""
    if a.get("grupo_forcado"):
        return a["grupo_forcado"], None
    d1, d2 = a.get("dia1_lancado") == "sim", a.get("dia2_lancado") == "sim"
    if not d1 and not d2:
        return ("M_aluno" if a.get("tipo_conta") == "pagante" else "M_gratis"), None
    if d1 and not d2:
        return "F", None
    if d2 and not d1:
        return "G", None
    if any(num(a.get(f"nota_{x}")) is None for x in ORDEM_AREAS):
        return "H", None
    curso = refs.cursos.get(a.get("curso_id", ""))
    if not curso:
        return "E", None
    dist = num(curso["nota_top10"]) - media_de(a)
    if abs(dist) < 5:
        return "A0", dist
    if dist <= -5:
        return "D", dist
    if dist < 20:
        return "A_topo", dist
    if dist <= 60:
        return "A", dist
    return ("B" if curso.get("eh_medicina") in ("1", "sim") else "C"), dist


def media_de(a):
    m = num(a.get("media"))
    if m is None:
        m = sum(num(a[f"nota_{x}"]) for x in ORDEM_AREAS) / 4
    return m


def faixa_plano(refs, area, acertos, avisos):
    n = num(acertos)
    for r in refs.plano.get(area, []):
        if n is not None and num(r["acertos_min"]) <= n <= num(r["acertos_max"]):
            return r
    avisos["sem faixa de plano para " + area].append(acertos)
    return {}


# ------------------------------------------------------------------ uma linha
def montar_linha(a, refs, bf=False, fase2=False, dominio="SEU-DOMINIO", avisos=None):
    avisos = avisos if avisos is not None else defaultdict(list)
    grupo, dist = classificar(a, refs)
    G = refs.grupos[grupo]
    camadas = G["camadas"].split()
    if bf:
        camadas += G["camadas_bf"].split()
    tem_fase2 = fase2 and G["recebe_fase2"] == "sim"
    if tem_fase2:
        camadas.append("FASE2")

    area = a.get("area_prioritaria", "")
    curso = refs.cursos.get(a.get("curso_id", ""), {})
    modelos_area = refs.modelos.get(area, [])
    pcts = [int(m["pct_acerto"]) for m in modelos_area] or [0]
    ref_area = refs.areas.get(area, {})
    faceis = lista(a.get("faceis_ids"))
    marcadas = lista(a.get("faceis_marcadas"))
    errados = lista(a.get("modelos_errados_ids"))
    var = {
        "dominio": dominio, "utm": UTM, "utm_grupo": G["utm_grupo"],
        "area": ref_area.get("nome", ""), "area_mais_perto": refs.areas.get(a.get("area_mais_perto", ""), {}).get("nome", ""),
        "curso": curso.get("curso", ""), "ies": curso.get("ies", ""),
        "na_ies": f'{curso.get("artigo_ies", "na")} {curso.get("ies", "")}' if curso else "",
        "nota_top10": curso.get("nota_top10", ""),
        "considerando": f', considerando {curso["curso"]}' if curso else "",
        "media": inteiro(media_de(a)) if grupo not in ("F", "G", "H", "M_aluno", "M_gratis") else "",
        "pontos": str(abs(int(round(dist)))) if dist is not None else "",
        "n_faceis": len(faceis), "n_modelos": len(errados),
        "pct_min": min(pcts), "pct_max": max(pcts),
        "pontos_facil": ref_area.get("pontos_facil", ""), "pontos_dificil": ref_area.get("pontos_dificil", ""),
        "fase2_rotulo": " · com a oferta de 2ª fase ligada" if tem_fase2 else "",
        "pessoas": "{pessoas}",
    }
    texto = {}
    for c in camadas:
        if c not in refs.copy:
            avisos[f"camada de copy inexistente: {c}"].append(a["aluno_id"])
        texto.update(refs.copy.get(c, {}))
    texto = {k: preencher(v, var) for k, v in texto.items()}

    L = {c: "" for c in refs.colunas}
    L.update({k: v for k, v in texto.items() if k in L})
    L["aluno_id"], L["nome"] = a["aluno_id"], a.get("nome", "")
    L["grupo"] = (G["grupo_bf"] or grupo) if bf else grupo
    L["rotulo_previa"] = preencher((G["rotulo_previa_bf"] if bf and G["rotulo_previa_bf"] else G["rotulo_previa"]), var)

    dia_area = {x: refs.areas[x]["dia"] for x in ORDEM_AREAS}
    cor = a.get(f'caderno_dia{dia_area.get(area, "")}', "") if area else ""

    if "DIAG" in camadas:
        # pontos fáceis
        if faceis:
            L["faceis_caderno"] = cor
            for i, (qid, marc) in enumerate(zip(faceis, marcadas + ["-"] * len(faceis)), 1):
                q = refs.questoes.get(int(qid))
                if not q:
                    avisos["questão fácil sem conteúdo em ref_questoes"].append(qid)
                    continue
                p = f"facil{i}_"
                marc = "" if marc == "-" else marc
                engana = cortar(q.get(f"engana_{marc}", "")) if marc else ""
                n_cad = refs.numeracao.get((cor, int(qid)))
                if not n_cad:
                    avisos[f"sem numeração no caderno {cor or '(sem cor)'}"].append(qid)
                valores = {
                    "num": n_cad or "", "url": MATRIX.format(slug=refs.areas[q["area"]]["slug_matrix"], qid=qid),
                    "titulo": q["titulo"], "pct": q["pct_acerto"], "marcada": marc, "correta": q["gabarito"],
                    "engana": engana, "coelho": "" if engana else q.get("coelho", ""),
                    "modelo": q.get("modelo_rotulo", ""), "modelo_url": q.get("modelo_url", ""),
                }
                for k, v in valores.items():
                    L[p + k] = v
        else:
            for k in ("faceis_titulo", "faceis_rodape"):
                L[k] = ""
        # modelos
        n = len(errados)
        if n == 0:
            L["modelos_titulo"], L["modelos_nota"], L["modelos_resumo"] = texto["modelos_titulo_nenhum"], texto["modelos_nota_nenhum"], texto["modelos_resumo_nenhum"]
        elif n == len(modelos_area):
            L["modelos_titulo"] = texto["modelos_titulo_todos"]
        por_id = {m["questao_id"]: m for m in modelos_area}
        ordenados = [por_id[q] for q in [m["questao_id"] for m in modelos_area] if q in errados]
        for faltando in set(errados) - set(por_id):
            avisos["questão modelo não está entre os modelos da área prioritária"].append(faltando)
        for i, m in enumerate(ordenados, 1):
            preencher_modelo(L, i, m, refs.numeracao.get((cor, int(m["questao_id"])), ""), refs, "")
        # plano
        for i, cod in enumerate([area] + [x for x in ORDEM_AREAS if x != area], 1):
            p = f"area{i}_"
            f = faixa_plano(refs, cod, a.get(f"acertos_{cod}"), avisos)
            L.update({p + "codigo": cod, p + "nota": a.get(f"nota_{cod}", ""), p + "acertos": a.get(f"acertos_{cod}", ""),
                      p + "titulo": f.get("titulo", ""), p + "texto": f.get("texto", ""), p + "itens": f.get("itens", ""), p + "como": f.get("como", "")})

    if "PARCIAL" in camadas:
        for cod in ORDEM_AREAS:
            lancou = a.get(f"dia{dia_area[cod]}_lancado") == "sim"
            nota = a.get(f"nota_{cod}", "")
            L[f"parcial_{cod}"] = nota if (lancou and nota) else ("incompleta" if lancou else "falta lançar")

    if "M" in camadas:  # as 20 questões modelo, caderno Azul, agrupadas por área
        i = 0
        for cod in sorted(refs.modelos, key=lambda x: int(refs.areas[x]["ordem_lista_m"])):
            ms = refs.modelos[cod]
            ps = [int(m["pct_acerto"]) for m in ms]
            rotulo = preencher(refs.copy["M"]["modelos_grupo"], {"area": refs.areas[cod]["nome"], "pct_min": min(ps), "pct_max": max(ps)})
            for m in ms:
                i += 1
                preencher_modelo(L, i, m, refs.numeracao.get(("Azul", int(m["questao_id"])), m["questao_id"]), refs, rotulo)
    return L, grupo


def preencher_modelo(L, i, m, numero, refs, rotulo):
    p = f"modelo{i}_"
    L.update({p + "grupo": rotulo, p + "num": numero, p + "titulo": m["titulo"], p + "pct": m["pct_acerto"],
              p + "fonte": m["fonte"], p + "texto": m["texto"], p + "aula_url": m["aula_url"],
              p + "questao_url": MATRIX.format(slug=refs.areas[m["area"]]["slug_matrix"], qid=m["questao_id"])})


# ------------------------------------------------------------------ validação
OBRIGATORIOS = {
    "facil{i}_num": ["facil{i}_url", "facil{i}_titulo", "facil{i}_pct", "facil{i}_correta"],
    "modelo{i}_num": ["modelo{i}_titulo", "modelo{i}_pct", "modelo{i}_questao_url"],
    "area{i}_codigo": ["area{i}_nota", "area{i}_acertos", "area{i}_titulo", "area{i}_texto"],
}
OBRIGATORIOS_FIXOS = {"curso_nome": ["curso_media", "curso_ref_nota", "curso_ies_linha"],
                      "faceis_titulo": ["faceis_caderno", "facil1_num"], "seguro_titulo": ["seguro_cta_url"],
                      "proposta_titulo": ["proposta_cta_url"]}


def validar(L):
    erros = []
    for chave, deps in OBRIGATORIOS_FIXOS.items():
        if L.get(chave):
            erros += [f"{chave} sem {d}" for d in deps if not L.get(d)]
    for chave, deps in OBRIGATORIOS.items():
        for i in range(1, 30):
            k = chave.format(i=i)
            if k in L and L[k]:
                erros += [f"{k} sem {d.format(i=i)}" for d in deps if not L.get(d.format(i=i))]
    return erros


def colunas_saida(refs, linhas):
    """Mesmas colunas do exemplo. Se algum aluno tiver mais de 5 fáceis, cria facil6_... logo depois do facil5."""
    cols = list(refs.colunas)
    extra = max([int(m.group(1)) for L in linhas for k, v in L.items() if v for m in [re.match(r"facil(\d+)_", k)] if m] + [0])
    if extra > 5:
        pos = cols.index("facil5_modelo_url") + 1
        novas = [f"facil{i}_{c}" for i in range(6, extra + 1) for c in FACIL_CAMPOS]
        cols = cols[:pos] + novas + cols[pos:]
    return cols


def gravar(caminho, cols, linhas):
    with open(caminho, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, cols, delimiter=";", extrasaction="ignore", restval="")
        w.writeheader()
        w.writerows(linhas)


def fmt(n):
    return f"{n:,}".replace(",", ".")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base", help="base_alunos.csv (1 linha por aluno)")
    ap.add_argument("-o", "--saida", default=str(AQUI / "alunos.csv"))
    ap.add_argument("--bf-aberta", action="store_true", help="a partir de 27/11: copy de Black Friday aberta")
    ap.add_argument("--fase2-aberta", action="store_true", help="liga o card de 2ª fase para A_topo, A0 e D")
    ap.add_argument("--dominio", default="SEU-DOMINIO")
    ap.add_argument("--dados", default=str(DADOS))
    a = ap.parse_args()

    refs = Refs(a.dados)
    avisos = defaultdict(list)
    linhas, grupos, problemas = [], Counter(), []
    for aluno in ler_csv(a.base):
        L, g = montar_linha(aluno, refs, a.bf_aberta, a.fase2_aberta, a.dominio, avisos)
        linhas.append(L)
        grupos[L["grupo"]] += 1
        problemas += [(L["aluno_id"], e) for e in validar(L)]
    for L in linhas:
        L["rotulo_previa"] = L["rotulo_previa"].replace("{pessoas}", fmt(grupos[L["grupo"]]))
    cols = colunas_saida(refs, linhas)
    gravar(a.saida, cols, linhas)

    print(f"{len(linhas)} aluno(s) -> {a.saida} ({len(cols)} colunas)")
    print("Por grupo:", ", ".join(f"{g} {fmt(n)}" for g, n in sorted(grupos.items())))
    for msg, itens in avisos.items():
        c = Counter(itens)
        print(f"AVISO {msg}: {len(itens)} ocorrência(s) · " + ", ".join(f"{k} ({v})" for k, v in c.most_common(10)))
    if problemas:
        print(f"ATENÇÃO {len(problemas)} campo(s) obrigatório(s) vazio(s). Primeiros:")
        for aid, e in problemas[:20]:
            print("  ", aid, e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
