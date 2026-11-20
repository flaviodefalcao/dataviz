# Como gerar o site (guia para o programador)

Só precisa de **Python 3.8+**, sem nenhuma biblioteca extra. São 3 comandos, todos dentro de `paginas_diagnostico/`.

```
exports do Matrix ──> montar_base.py ──> base_alunos.csv ──> gerar_site.py ──> build/site/<aluno_id>.html
 (dia 1, dia 2,          (+ dados/)        (1 linha/aluno)     (montar_csv.py + gerar.py)
  Sisu, cadastro)
```

## Passo a passo com os dados reais

### 0. Arquivos de entrada

| Arquivo | De onde vem | Colunas usadas |
|---|---|---|
| `dia1.csv` | export `matrix-gabarito-2026-dia1-respostas-alunos-*.csv` | `aluno_id`, `cor_caderno`, `lingua`, `q1`…`q90`, `nota_*`, `acertos_*` |
| `dia2.csv` | export `matrix-gabarito-2026-dia2-respostas-alunos-*.csv` | `aluno_id`, `cor_caderno`, `q91`…`q180`, `nota_*`, `acertos_*` |
| `sisu.csv` | export `matrix-opcoes-sisu-2026-*.csv` | `user_id`, `opcao`, `curso`, `sigla` |
| `cadastro.csv` | **falta exportar** | `aluno_id;nome;tipo_conta` (`pagante` = aluno do Chapéu, `gratuito`). Deve trazer **todos** os usuários, inclusive os que não lançaram gabarito (grupos M) |

Sem o cadastro, a página sai sem nome (", seus 24 pontos começam em…") e não existem os grupos M.

### 1. Gabarito e numeração (só uma vez, ou quando sair o gabarito oficial)

```bash
python3 scripts/inferir_gabarito.py --dia1 dia1.csv --dia2 dia2.csv      # ~10 min → dados/gabarito.csv
```

Infere, a partir das respostas e dos acertos de cada aluno, o gabarito de cada cor e a numeração de cada cor
para o número canônico (o do caderno Azul, que é o número usado no link do Matrix). Nos exports de 18/11, o
gabarito inferido reproduz **100%** dos acertos informados, em todas as cores. A anulada é a MT 159 (Azul).
Os 44 pares de numeração já conhecidos batem. `dados/gabarito.csv` já está pronto no repositório. Rode de novo só se
mudar o gabarito. Se tiver o gabarito oficial, pode montar o arquivo à mão no mesmo formato.

### 2. Base dos alunos

```bash
python3 montar_base.py --dia1 dia1.csv --dia2 dia2.csv --sisu sisu.csv --cadastro cadastro.csv   # ~25 s
```

Grava `base_alunos.csv` e atualiza as tabelas de `dados/` com os mesmos dados:
- `ref_cursos.csv`: cada curso + IES escolhido, com a **nota dos 10% mais bem colocados** (P90 da média dos
  alunos do Matrix que escolheram o curso em 1ª ou 2ª opção) e o P90 de cada área. Curso com menos de 10
  alunos no Matrix fica sem nota dos 10%, e o aluno vai para o grupo E (`--min-alunos-curso` muda o limite).
  Ajustes feitos à mão nas colunas `curso`, `ies`, `artigo_ies`, `peso_*` e `obs` **são preservados** quando o script roda de novo.
- `ref_questoes.csv`: % de acerto e gabarito de todas as questões, mais a marcação das 15 mais fáceis de cada área.
  Os textos (título, "por que a X engana", coelho) são mantidos.
- `ref_numeracao.csv` e `ref_modelos.csv` (% de acerto).

O script imprime avisos: alunos sem nome, cursos pequenos e questões fáceis ainda sem texto.

### 3. Site

```bash
python3 gerar_site.py base_alunos.csv --amostra 3            # revisão: 3 por grupo + build/site/_previa.html
python3 gerar_site.py base_alunos.csv \                       # produção
    --dominio www.seusite.com.br \
    --logo-topo  https://cdn.seusite.com.br/diagnostico/logo_topo.png \
    --logo-marca https://cdn.seusite.com.br/diagnostico/logo_marca.png
```

Publique `build/site/` como arquivos estáticos, uma página por aluno (`<aluno_id>.html`). Leia `build/relatorio.txt`
antes de publicar: contagem por grupo, avisos e campos obrigatórios vazios.

**Passe os logos por URL.** Embutidos, cada página fica com ~105 KB (~8 GB no total). Com URL, ~22 KB (~1,7 GB).

| Quando | Flags do `gerar_site.py` |
|---|---|
| Até ~25/11 | nenhuma |
| ~25/11 (2ª fase) | `--fase2-aberta` |
| A partir de 27/11 (Black Friday) | `--bf-aberta --fase2-aberta` |

### Resultado com os exports de 18/11 (sem cadastro)

76.878 alunos com gabarito: A 4.079 · A topo 1.465 · A0 1.068 · B 2.050 · C 7.093 · D 1.282 · E 23.740 ·
F 22.367 · G 12.228 · H 1.506. Os grupos M dependem do cadastro.
Tempo: montar_base 25 s, montar_csv 25 s, páginas ~1,5 min.

## Regras usadas para montar a base (`montar_base.py`)

| Campo | Regra |
|---|---|
| grupo | M: sem nenhum dia · F/G: um dia só · H: os dois dias, mas alguma área sem nota · E: sem curso (ou curso com < 10 alunos) · pelo resto, `distância = nota_top10 − média`: D ≤ −5 · A0 \|d\| < 5 · A_topo 5–20 · A 20–60 · B > 60 Medicina · C > 60 outros |
| curso | 1ª opção do Sisu (ou a 2ª, se não houver 1ª), agrupada por curso + IES |
| área prioritária | maior `(P90 da área no curso − nota do aluno) × peso`. Os pesos vêm de `ref_cursos.peso_*`, e vazio = 1. Sem curso, usa o P90 de todos os alunos |
| área mais perto (B) | a de menor déficit, tirando a prioritária |
| fáceis | as 15 questões da área prioritária com maior % de acerto, sem língua estrangeira e sem anulada. Entram as que o aluno errou ou deixou em branco (`--max-faceis` limita a quantidade) |
| modelos | as 5 questões modelo da área prioritária que o aluno errou ou deixou em branco |

Conferido com o único aluno da prévia que aparece nos exports (exemplo A topo): a área prioritária, as fáceis
(118, 131, 119, com C, branco e B), os modelos (116, 101) e a média (767,75) saem iguais.

## Sem dados reais: base fictícia

```bash
python3 scripts/gerar_base_ficticia.py            # 81.550 alunos inventados, nas contagens da prévia
python3 gerar_site.py base_alunos_ficticia.csv --amostra 3
```

## Testes

```bash
python3 testes/conferir.py      # remonta as 14 páginas da prévia (tabelas congeladas em testes/dados_exemplo): 0 diferenças
```

## Mapa dos arquivos

```
paginas_diagnostico/
├── montar_base.py         exports do Matrix → base_alunos.csv (+ atualiza dados/)
├── gerar_site.py          base_alunos.csv → build/site/  (chama montar_csv.py e gerar.py)
├── montar_csv.py          base compacta + dados/ → alunos.csv de 324+ colunas (regras de grupo e de copy)
├── gerar.py, template.html   layout das páginas (não mexer)
├── dados/                 gabarito, numeração, questões, modelos, plano, cursos, áreas, grupos, copy
├── scripts/               inferir_gabarito.py, gerar_base_ficticia.py, extrair_dos_exemplos.py
├── testes/                conferir.py + exemplos da prévia
├── COMO_GERAR.md          este guia
└── OTIMIZACAO.md          por que a base é assim, e o que falta completar
```

**Não versionar dados pessoais.** `base_alunos.csv`, os exports e `build/` estão no `.gitignore`.

## Antes de ir para produção

1. **Cadastro** (`nome`, `tipo_conta`, todos os usuários): sem ele a página fica sem nome e não há grupos M.
2. **Textos de 46 das 60 questões fáceis** (título, "por que a X engana" por alternativa, coelho) em
   `dados/ref_questoes.csv`. Só há texto para as 14 questões que estavam na prévia. O `montar_base.py` lista quais faltam.
3. **Pesos por curso** (`ref_cursos.peso_*`). Sem pesos, **Matemática é a área prioritária de 64% dos alunos**
   (a escala de MT na TRI é mais espalhada). Na prévia, para Medicina, a área prioritária costumava ser Natureza.
4. **Cortes de acertos** do plano (`textos_plano.csv`), hoje provisórios. Humanas só tem 1 faixa.
5. **Copy de Black Friday** para B, E e M.
6. Revisar a sigla e o artigo de cada IES em `ref_cursos.csv` (ex.: "UFSCAR" → "UFSCar"; "no IFMG").
