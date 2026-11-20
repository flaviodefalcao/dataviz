# CSV da página de diagnóstico — Enem 2026

Estrutura montada a partir da página "Página de diagnóstico Matrix" (grupos A, A topo, A0, B, C, D, E, F, G, H, M aluno, M grátis e as versões de Black Friday de A e C).

## A ideia da otimização

A página mistura três tipos de informação. Cada tipo vai para um arquivo diferente:

| Tipo | Onde fica | Tamanho |
|---|---|---|
| O que muda **por aluno** (notas, acertos, curso, questões que errou) | `alunos.csv` | 1 linha por aluno, 31 colunas |
| O que é **igual para todo mundo** (texto de cada questão, % de acerto, aulas, textos do plano) | `ref_*.csv` | algumas dezenas de linhas |
| O que muda **por data** (Black Friday aberta, 2ª fase ligada, links) | `config.csv` | 1 linha por chave |

Os textos do Matrix (tema, "por que a E engana", "tirando o coelho do chapéu", trecho da aula) **não se repetem em cada aluno**. O aluno guarda só o número da questão e a letra que marcou, e a página busca o resto em `ref_questoes_faceis.csv` / `ref_questoes_modelo.csv`. Com ~80 mil alunos, isso tira algumas centenas de MB de texto repetido do arquivo.

A versão "depois de 27/11" **não é um grupo novo**: é o mesmo A ou C com `bf_aberta = 1` no `config.csv`. Assim não é preciso duplicar 15 mil linhas.

**Formato:** UTF-8, vírgula como separador, ponto como decimal. Listas dentro de uma célula usam `|`, sempre na mesma ordem entre colunas irmãs (ex.: `faceis_erradas_ids` e `faceis_marcadas`). Célula vazia = não se aplica / não lançado.

---

## `alunos.csv` — 1 linha por aluno

| Coluna | Exemplo | Bloco da página | Observação |
|---|---|---|---|
| `aluno_id` | `exemplo_01` | — | Chave para o CRM / e-mail |
| `primeiro_nome` | `Ana` | Cabeçalho, hero | |
| `grupo` | `A` | Escolhe os blocos (ver `ref_grupos.csv`) | A, A_TOPO, A0, B, C, D, E, F, G, H, M_ALUNO, M_GRATIS |
| `tipo_conta` | `aluno_chapeu` | M aluno x M grátis | `aluno_chapeu` ou `gratuito` |
| `dia1_status`, `dia2_status` | `completo` | F, G, H, M | `completo`, `incompleto`, `nao_lancado` |
| `cor_caderno_d1`, `cor_caderno_d2` | `Amarelo` | "No seu caderno Amarelo" | D1 = LC/CH, D2 = CN/MT. Converte o nº canônico no nº do caderno do aluno |
| `lingua_estrangeira` | `ingles` | — | Necessário para corrigir LC 1–5 |
| `nota_lc`, `nota_ch`, `nota_cn`, `nota_mt` | `724` | Medidores do plano; barras de F/G/H | Vazio = "falta lançar" (dia não lançado) ou "incompleta" (dia incompleto) |
| `acertos_lc` … `acertos_mt` | `33` | "33 de 45 acertos" | |
| `media_objetiva` | `752.5` | Medidor "sua média estimada", hero do E e do D | Média das 4 objetivas, sem redação. Guardar com 1 casa; a página arredonda |
| `curso_id` | `MEDICINA_UFMG` | Cartão "1ª opção" | Junta com `ref_cursos.csv`. Vazio no grupo E |
| `nota_top10_curso` | `777` | "Nota dos 10% mais bem colocados" | Cópia de `ref_cursos.nota_top10`, no valor do dia do envio |
| `diferenca_top10` | `-24.5` | "Faltam 24 pontos" / "47 pontos acima" | `media − top10`. Define A / A_TOPO / A0 / B / C / D |
| `area_prioritaria` | `CN` | Hero, fáceis, modelos, "Por onde começar", oferta | LC, CH, CN ou MT |
| `area_mais_perto` | `CH` | Hero do B ("em Humanas, você está mais perto…") | Só no B |
| `ordem_areas` | `CN\|LC\|CH\|MT` | Ordem dos 4 cartões do plano | A 1ª é a prioritária |
| `faceis_erradas_ids` | `129\|107\|97` | "Os pontos fáceis de recuperar" | Nº **canônico** (= caderno Azul / link do Matrix), em ordem de % de acerto decrescente. Só da área prioritária, entre as 15 mais acertadas |
| `faceis_marcadas` | `E\|E\|E` | "Você marcou E" | `-` = deixou em branco |
| `modelos_errados_ids` | `116\|125\|101` | "Antes da prova, a gente mostrou" | Questões-modelo da área prioritária que o aluno errou. Acertos = 5 − nº de itens. Vazio = acertou as 5 |
| `faixa_lc` … `faixa_mt` | `CN2` | Texto do plano de cada área | Junta com `ref_plano_faixas.faixa_id` |

Contas que a página (ou o seu script) faz a partir dessas colunas, sem precisar de coluna própria:
- **"Você errou 3 das 15"**: nº de itens em `faceis_erradas_ids`.
- **"Você errou 3 das 5 questões modelo"**: nº de itens em `modelos_errados_ids`.
- **Nº no caderno do aluno**: `ref_caderno_numeracao` com (`cor_caderno_dX`, `questao_id`).
- **Gabarito, tema, % de acerto, explicação**: `ref_questoes_faceis` / `ref_questoes_modelo` pelo `questao_id`.
- **Link da questão**: `config.matrix_questao_url`.
- **Oferta de Medicina x outro curso**: `ref_cursos.eh_medicina`.

## `ref_questoes_faceis.csv` — 1 linha por questão

`questao_id, area, tema, pct_acerto, gabarito, eh_facil_top15, por_que_engana_A … _E, coelho, modelo_rotulo, modelo_video`

Cada linha mostra **ou** um "Por que a X engana" (da letra que o aluno marcou) **ou** o "Tirando o coelho do chapéu" (quando a questão não tem explicação daquela letra, ou quando o aluno deixou em branco). `modelo_rotulo`/`modelo_video` geram o selo azul "Questão modelo · …".

## `ref_questoes_modelo.csv` — as 20 questões-modelo (5 por área)

`questao_id, area, ordem, titulo, pct_acerto, professor_data, texto_aula, video_aula`. Os grupos M mostram as 20; os outros mostram só as erradas da área prioritária.

## `ref_caderno_numeracao.csv`

`cor_caderno, area, numero_no_caderno, questao_id`. O ID canônico é o número no caderno **Azul** (é o que aparece no link do Matrix).

## `ref_plano_faixas.csv`

`faixa_id, area, acertos_min, acertos_max, titulo, texto, o_que_estudar (lista com |), como_trabalhamos, acertos_vistos`.

## `ref_cursos.csv`

`curso_id, curso, ies, eh_medicina, nota_top10`. Uma linha por curso + IES, em vez de repetir a nota de corte em cada aluno.

## `ref_grupos.csv`

Regra, blocos visíveis, título e texto do hero com `{marcadores}`, oferta e botões antes e depois da Black Friday, por grupo. Os marcadores são `{nome}`, `{pontos}` = |`diferenca_top10`| arredondado, `{area}`, `{area_mais_perto}`, `{curso}`, `{ies}` e `{media}`.

## `config.csv`

Chaves que valem para todos: `bf_aberta`, `fase2_aberta`, domínio, UTMs, URL das questões e as frases de base ("cada fácil rendeu 24 pontos…").

---

## O que ainda falta confirmar

1. **`acertos_min` / `acertos_max` das faixas** estão vazios. A página só mostra exemplos (coluna `acertos_vistos`), não os limites. Preencher com o MD do projeto.
2. **Limites dos grupos** (5 / 20 / 60 pontos) vieram dos títulos da página. Conferir se `diferenca_top10` é calculada com média arredondada ou não. No exemplo A0, a página mostra 762, e a conta com as notas inteiras dá 761,2.
3. **`nota_top10` de B e C** (777 e 714) foi deduzida: média + 68 pontos.
4. **`ref_caderno_numeracao`** tem só os pares que aparecem na página. Completar com os gabaritos oficiais das 4 cores × 2 dias.
5. **`ref_questoes_faceis`** tem só as 14 questões que aparecem nos exemplos. É preciso completar com as 15 mais acertadas de cada área e todas as explicações por alternativa.

`scripts/extrair.py` regera os `ref_*` a partir do HTML: `python3 scripts/extrair.py pagina.html saida/`.
