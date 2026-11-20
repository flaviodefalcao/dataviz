# Páginas de diagnóstico · Enem 2026

Gera uma página HTML personalizada para cada usuário do Matrix, com nota estimada, comparação com o curso
escolhido no Sisu, questões fáceis que escaparam, questões modelo e plano por área. A partir dos exports
de **20/11** são **92.509 páginas**.

Só precisa de **Python 3.8+**, sem nenhuma biblioteca extra.

---

## 1. Rodar

```bash
cd paginas_diagnostico

# 1) coloque os 4 exports em entrada/ (os nomes podem ter outra data: o script pega o mais recente)
#    matrix-gabarito-2026-dia1-respostas-alunos-*.csv
#    matrix-gabarito-2026-dia2-respostas-alunos-*.csv
#    matrix-opcoes-sisu-2026-*.csv
#    matrix-usuarios-*.csv

# 2) revisão: 3 páginas de cada grupo, empilhadas em saida/site/_previa.html (~1 min)
python3 gerar_tudo.py

# 3) produção: todas as páginas (~3 min)
python3 gerar_tudo.py --todas \
    --dominio www.seusite.com.br \
    --logo-topo  https://cdn.seusite.com.br/diagnostico/logo_topo.png \
    --logo-marca https://cdn.seusite.com.br/diagnostico/logo_marca.png
```

**Saída em `saida/`:**

| Arquivo | O que é |
|---|---|
| `alunos.csv` | **CSV final**: 1 linha por aluno, todas as colunas que a página usa (424, separador `;`, UTF-8) |
| `site/<aluno_id>.html` | **HTML final**: uma página por aluno |
| `site/_previa.html` | só na revisão: as páginas da amostra empilhadas, com menu por grupo |
| `base_alunos.csv` | base intermediária: só os dados do aluno (23 colunas) |
| `relatorio.txt` | contagem por grupo, avisos e campos vazios. **Leia antes de publicar** |

Publique `saida/site/` como arquivos estáticos. O nome do arquivo é o `user_id` (UUID), que não dá para adivinhar.

**Logos por URL:** sem URL, os logos vão embutidos em toda página (~105 KB cada, ~9,7 GB no total). Com URL, ~22 KB (~2 GB).

### Datas

| Quando | Acrescente |
|---|---|
| ~25/11 (2ª fase) | `--fase2-aberta` (card de aulões de 2ª fase para A topo, A0 e D) |
| A partir de 27/11 (Black Friday) | `--bf-aberta --fase2-aberta` (troca "Me avise quando abrir" pelo checkout) |

Para reprocessar com exports novos, troque os arquivos em `entrada/` e rode de novo.

---

## 2. Como funciona

```
entrada/ (exports)                      dados/ (tabelas fixas)
   │                                        │
   ├─► scripts/inferir_gabarito.py ──► dados/gabarito.csv        (só 1ª vez, ou --refazer-gabarito)
   │
   ├─► montar_base.py ──► saida/base_alunos.csv   (1 linha por aluno; atualiza dados/ref_*.csv)
   │
   └─► gerar_site.py ──► montar_csv.py ──► saida/alunos.csv ──► gerar.py + template.html ──► saida/site/*.html
```

`gerar_tudo.py` só chama as três etapas em sequência. Cada uma também roda sozinha (`--help`).

| Arquivo | Função | Mexer? |
|---|---|---|
| `gerar_tudo.py` | ponto de entrada | — |
| `scripts/inferir_gabarito.py` | gabarito por cor + numeração canônica, a partir das respostas | — |
| `montar_base.py` | exports → `base_alunos.csv`; calcula grupo, curso, área prioritária, fáceis, modelos | regras de negócio |
| `montar_csv.py` | `base_alunos.csv` + `dados/` → `alunos.csv` com todos os textos da página | regras de copy |
| `gerar_site.py` | roda o `montar_csv.py` e o `gerar.py` em lotes de 5.000 | — |
| `gerar.py`, `template.html`, `assets/` | layout das páginas | **não** |
| `dados/` | tabelas de referência e todos os textos (ver seção 4) | **sim: é aqui que se edita conteúdo** |
| `docs/dicionario_campos.csv` | o que cada coluna do `alunos.csv` faz na página | — |
| `docs/briefing_original.md` | especificação original da tarefa | — |
| `testes/conferir.py` | teste de regressão: remonta as 14 páginas da prévia de 18/11 (precisa dar 0 diferenças) | — |
| `scripts/gerar_base_ficticia.py` | base inventada para testar sem dados reais | — |

---

## 3. Regras de negócio

### Grupo de cada usuário

`distância = nota dos 10% do curso − média do aluno`

| Grupo | Condição | 20/11 |
|---|---|---|
| M_gratis / M_aluno | não lançou nenhum dia (pagante → M_aluno) | 10.831 |
| F | só o dia 1 | 22.077 |
| G | só o dia 2 | 12.458 |
| H | os dois dias, mas alguma área sem nota (respostas em branco) | 1.630 |
| E | sem curso no Sisu, ou curso com menos de 10 alunos no Matrix | 23.282 |
| D | distância ≤ −5 (acima dos 10%) | 1.629 |
| A0 | \|distância\| < 5 | 1.435 |
| A_topo | 5 ≤ distância < 20 | 1.877 |
| A | 20 ≤ distância ≤ 60 | 5.507 |
| B | distância > 60, Medicina | 2.588 |
| C | distância > 60, outros cursos | 9.195 |

### Cálculos

| Item | Regra |
|---|---|
| Gabarito e numeração | Os exports não trazem o gabarito. `inferir_gabarito.py` escolhe, por cor, a letra de cada questão que faz bater os `acertos_*` informados. Resultado: **100% dos alunos batem**, em todas as cores e nos dois dias. A numeração de cada cor é casada com a do **Azul** (canônica, usada no link do Matrix) pelo perfil de respostas. Marrom = Branco (dia 1) e Cinza (dia 2). Anulada: MT 159 (Azul). Exports de 18/11 e 20/11 dão o mesmo resultado |
| Média | média das 4 notas objetivas, sem redação, sem arredondar (a página arredonda) |
| Curso | 1ª opção do Sisu (ou a 2ª, se não houver 1ª), agrupada por curso + IES |
| Nota dos 10% | P90 da média dos alunos do Matrix que escolheram o curso + IES em 1ª ou 2ª opção. Reproduz a prévia (Medicina UFMG = 777) |
| Área prioritária | maior `(P90 da área no curso − nota do aluno) × peso da área`. Os pesos ficam em `dados/ref_cursos.csv`, e vazio = 1. Sem curso, usa o P90 de todos os alunos |
| Área mais perto (grupo B) | a de menor déficit, tirando a prioritária |
| Questões fáceis | as 15 da área prioritária com maior % de acerto (sem língua estrangeira e sem anulada). Entram as que o aluno errou ou deixou em branco, por % de acerto. Média de 6 por aluno, máximo 15 |
| Questões modelo | as 5 da área prioritária (`dados/ref_modelos.csv`) que o aluno errou ou deixou em branco |
| Plano por área | texto por área × faixa de acertos (`dados/textos_plano.csv`) |
| Sem nome | os exports não trazem o nome, então os textos começam sem ele: "Seus 24 pontos começam em…", "O seu resultado…" |

Conferência: o único aluno da prévia que aparece nos exports (exemplo A topo) sai idêntico, com área prioritária,
fáceis, letras marcadas, modelos e média iguais. As 14 páginas da prévia, remontadas pelo
`testes/conferir.py`, saem iguais coluna por coluna e byte a byte.

---

## 4. Onde editar conteúdo (`dados/`)

| Arquivo | Conteúdo | Atualizado pelo script? |
|---|---|---|
| `copy.csv` | **todos os textos fixos** da página, em camadas, com `{variáveis}` (`{area}`, `{curso}`, `{pontos}`…) | não |
| `grupos.csv` | quais camadas de texto cada grupo usa, UTM, se recebe 2ª fase | não |
| `textos_plano.csv` | plano por área × faixa de acertos (`acertos_min`–`acertos_max`) | não |
| `ref_questoes.csv` | por questão: tema, % de acerto, gabarito, `engana_A`…`E`, coelho, etiqueta de questão modelo | % e gabarito, sim. **Os textos são mantidos** |
| `ref_modelos.csv` | as 20 questões modelo: título, professor, data, texto, vídeo | só o % |
| `ref_cursos.csv` | curso + IES: nome, sigla, artigo (na/no), nota dos 10%, P90 por área, **pesos** | números, sim. **Nome, sigla, artigo, pesos e obs são mantidos** |
| `ref_areas.csv` | nome da área, pontos médios de uma fácil e de uma difícil | não |
| `gabarito.csv` | gabarito e numeração por cor | por `inferir_gabarito.py` |
| `ref_numeracao.csv` | número no caderno de cada cor ↔ número canônico | sim |

Depois de editar, rode `python3 testes/conferir.py` (tem que dar 0 diferenças) e `python3 gerar_tudo.py`.

---

## 5. Pendências de conteúdo

O site já pode ser gerado, mas estes pontos ainda mudam o que o aluno lê:

1. **Textos de 46 das 60 questões fáceis** (`ref_questoes.csv`: `titulo`, `engana_*`, `coelho`). Só há texto para as
   14 que estavam na prévia. Sem texto, o cartão mostra número, %, letra marcada e resposta, mas fica sem título.
   O `relatorio.txt` lista quais faltam.
2. **Pesos das áreas por curso** (`ref_cursos.csv`, `peso_*`). Sem pesos, **Matemática é a área prioritária de ~60%**
   dos alunos, porque a nota de MT varia mais na TRI.
3. **Nome do aluno:** os exports não trazem. Se houver, acrescente uma coluna `nome` ao arquivo de usuários.
4. **Pagante × gratuito:** o arquivo de usuários não diz quem é aluno do Chapéu. Hoje todos os que não lançaram
   gabarito caem em **M_gratis**. Com uma coluna `tipo_conta` (`pagante`/`gratuito`), os pagantes vão para M_aluno.
5. **Cortes de acertos do plano** (`textos_plano.csv`): provisórios. Humanas tem uma faixa só.
6. **Copy de Black Friday para B, E e M** (`copy.csv`): hoje, com `--bf-aberta`, esses grupos continuam com
   "Me avise quando abrir".
7. **Siglas e artigos** em `ref_cursos.csv` (ex.: "UFSCAR" → "UFSCar", "na" → "no IFMG").
8. **Domínio e logos:** passar `--dominio`, `--logo-topo` e `--logo-marca`.
9. 104 usuários lançaram gabarito mas não estão no arquivo de usuários: entram assim mesmo.

## 6. Dados pessoais

`entrada/` e `saida/` estão no `.gitignore`: os exports e as páginas geradas não vão para o repositório.
O e-mail do arquivo de usuários não é usado em nenhum lugar.
