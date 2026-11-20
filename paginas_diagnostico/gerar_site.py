#!/usr/bin/env python3
"""
Gera o site inteiro com um comando: base_alunos.csv -> alunos.csv (324 col.) -> uma página por aluno.

    python3 gerar_site.py base_alunos.csv --amostra 3            # prévia rápida: 3 alunos por grupo
    python3 gerar_site.py base_alunos.csv --dominio www.site.com.br \\
        --logo-topo https://cdn.site.com.br/logo_topo.png --logo-marca https://cdn.site.com.br/logo_marca.png
    python3 gerar_site.py base_alunos.csv --bf-aberta --fase2-aberta ...    # a partir de 27/11

Saída (pasta --saida, padrão saida/):
    saida/alunos.csv                    CSV completo que o gerar.py lê
    saida/site/<aluno_id>.html          uma página por aluno
    saida/site/_previa.html             só com --amostra: as páginas da amostra empilhadas, para revisão
    saida/relatorio.txt                 contagem por grupo, avisos e campos obrigatórios vazios

Usa o montar_csv.py e o gerar.py sem modificá-los. O gerar.py roda em lotes (--lote, padrão 5.000 alunos)
para não carregar 80 mil linhas de 324 colunas na memória de uma vez.
"""
import argparse
import contextlib
import csv
import io
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import montar_csv as M  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base", help="base_alunos.csv (1 linha por aluno)")
    ap.add_argument("-o", "--saida", default=str(AQUI / "saida"))
    ap.add_argument("--bf-aberta", action="store_true")
    ap.add_argument("--fase2-aberta", action="store_true")
    ap.add_argument("--dominio", default="SEU-DOMINIO")
    ap.add_argument("--logo-topo", default="", help="URL do logo. Sem URL, o logo vai embutido e cada página fica ~5x maior")
    ap.add_argument("--logo-marca", default="")
    ap.add_argument("--amostra", type=int, default=0, help="gera só N alunos por grupo, com _previa.html")
    ap.add_argument("--lote", type=int, default=5000)
    a = ap.parse_args()

    saida = Path(a.saida)
    site = saida / "site"
    site.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    # 1. base compacta -> alunos.csv completo (mesmo código do montar_csv.py)
    args = [a.base, "-o", str(saida / "alunos.csv"), "--dominio", a.dominio]
    args += ["--bf-aberta"] if a.bf_aberta else []
    args += ["--fase2-aberta"] if a.fase2_aberta else []
    rel = io.StringIO()
    sys.argv = ["montar_csv.py"] + args
    with contextlib.redirect_stdout(rel):
        M.main()
    print(rel.getvalue(), end="")
    (saida / "relatorio.txt").write_text(rel.getvalue(), encoding="utf-8")

    # 2. amostra (opcional)
    linhas = M.ler_csv(saida / "alunos.csv")
    cols = list(linhas[0].keys()) if linhas else []
    if a.amostra:
        por_grupo = defaultdict(list)
        for L in linhas:
            if len(por_grupo[L["grupo"]]) < a.amostra:
                por_grupo[L["grupo"]].append(L)
        linhas = [L for g in sorted(por_grupo) for L in por_grupo[g]]

    # 3. páginas, em lotes, chamando o gerar.py
    extra = []
    if a.logo_topo:
        extra += ["--logo-topo", a.logo_topo]
    if a.logo_marca:
        extra += ["--logo-marca", a.logo_marca]
    with tempfile.TemporaryDirectory() as tmp:
        for ini in range(0, len(linhas), a.lote):
            lote = Path(tmp) / f"lote_{ini}.csv"
            M.gravar(lote, cols, linhas[ini:ini + a.lote])
            cmd = [sys.executable, str(AQUI / "gerar.py"), str(lote), "-o", str(site)] + extra
            if not a.amostra:
                cmd.append("--sem-previa")
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
            print(f"  páginas {ini + 1}–{min(ini + a.lote, len(linhas))} de {len(linhas)}")
    print(f"Pronto: {len(linhas)} página(s) em {site}/ ({time.time() - t0:.0f} s)")


if __name__ == "__main__":
    main()
