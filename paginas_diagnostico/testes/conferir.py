#!/usr/bin/env python3
"""
Teste de regressão: monta as 14 linhas a partir da base compacta (testes/base_exemplos.csv)
e compara, coluna por coluna, com as linhas da prévia (testes/alunos_exemplo.csv).

Uso:  python3 testes/conferir.py
"""
import sys
from collections import defaultdict
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
import montar_csv as M  # noqa: E402

IGNORAR = {"rotulo_previa"}  # só aparece na prévia; a contagem de pessoas vem da base real


def main():
    refs = M.Refs(AQUI / "dados_exemplo")  # tabelas congeladas da prévia de 18/11
    esperado = {r["aluno_id"]: r for r in M.ler_csv(AQUI / "alunos_exemplo.csv")}
    flags = {r["aluno_id"]: r for r in M.ler_csv(AQUI / "flags_exemplos.csv")}
    avisos = defaultdict(list)
    difs = 0
    for a in M.ler_csv(AQUI / "base_exemplos.csv"):
        f = flags.get(a["aluno_id"], {})
        L, _ = M.montar_linha(a, refs, f.get("bf_aberta") == "1", f.get("fase2_aberta") == "1", avisos=avisos)
        e = esperado[a["aluno_id"]]
        d = [c for c in e if c not in IGNORAR and (e[c] or "") != (L.get(c) or "")]
        if L["grupo"] != a["_grupo_exemplo"]:
            d.insert(0, f"grupo calculado {L['grupo']} != {a['_grupo_exemplo']}")
        status = "OK" if not d else f"{len(d)} diferença(s)"
        print(f"{a['aluno_id']:<22} {L['grupo']:<9} {status}")
        for c in d:
            if c in e:
                print(f"    {c}\n      esperado: {e[c][:160]}\n      montado:  {(L.get(c) or '')[:160]}")
            else:
                print("   ", c)
        difs += len(d)
    for msg, itens in avisos.items():
        print("AVISO", msg, sorted(set(itens)))
    print(f"\nTotal de diferenças: {difs}")
    return 1 if difs else 0


if __name__ == "__main__":
    sys.exit(main())
