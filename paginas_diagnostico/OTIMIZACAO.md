# CSV otimizado: base compacta + tabelas + `montar_csv.py`

## O problema

O `alunos.csv` que o `gerar.py` lê tem **324 colunas** e cerca de **7 KB por aluno**. Quase tudo é texto
que se repete: a mesma explicação da questão 107, o mesmo card do Seguro Aprovação, o mesmo plano de
Natureza, copiados em milhares de linhas. Para os ~81.550 alunos da prévia, isso dá **~570 MB**,
difícil de abrir, revisar e corrigir: mudar uma vírgula na copy obriga a regravar a base inteira.

## A solução

Cada informação é guardada **uma vez só**, no lugar certo, e o `montar_csv.py` monta o CSV de 324 colunas
na hora de gerar as páginas. `template.html` e `gerar.py` **não mudam**.

```
base_alunos.csv  ─┐
dados/*.csv      ─┼─>  montar_csv.py  ─>  alunos.csv (324 col.)  ─>  gerar.py  ─>  páginas
flags de data    ─┘
```

| | Antes | Agora |
|---|---|---|
| Por aluno | 324 colunas, ~7 KB | **23 colunas, ~120 bytes** |
| 81.550 alunos | ~570 MB | **~10 MB** + 35 KB de tabelas |
| Corrigir um texto | regravar a base | editar 1 linha de `dados/copy.csv` |
| Black Friday / 2ª fase | outra versão da base | `--bf-aberta` / `--fase2-aberta` |

**Conferido:** as 14 linhas da prévia, montadas a partir da base compacta, batem **coluna por coluna**
com o `alunos.csv` original (`python3 testes/conferir.py` → 0 diferenças), e as 14 páginas HTML geradas
saem **byte a byte iguais** às da prévia.

## Como rodar

```
python3 montar_csv.py base_alunos.csv                      # antes de 27/11
python3 montar_csv.py base_alunos.csv --fase2-aberta       # a partir de ~25/11
python3 montar_csv.py base_alunos.csv --bf-aberta --fase2-aberta --dominio www.seusite.com.br
python3 gerar.py alunos.csv
python3 testes/conferir.py                                 # teste de regressão
```

O script imprime a contagem por grupo, avisos de dado faltando (questão sem conteúdo, numeração
não encontrada, faixa de plano inexistente) e as linhas com bloco ligado e campo obrigatório vazio.

---

## `base_alunos.csv`: o que vem do banco (1 linha por aluno)

UTF-8, separador `;`. Listas dentro de uma célula usam `|`. Exemplo pronto: `testes/base_exemplos.csv`.

| Coluna | Exemplo | Para que serve |
|---|---|---|
| `aluno_id` | `123456` | Nome do arquivo da página |
| `nome` | `Ana` | Primeiro nome |
| `tipo_conta` | `pagante` / `gratuito` | Separa M_aluno de M_gratis |
| `dia1_lancado`, `dia2_lancado` | `sim` / `nao` | Grupos F, G e M |
| `caderno_dia1`, `caderno_dia2` | `Amarelo` | Converte o número canônico no número do caderno do aluno |
| `lingua` | `ingles` | Reservado (numeração de LC 1–5) |
| `nota_LC` … `nota_MT` | `724` | Plano e barras parciais. Vazio com o dia lançado = "incompleta" (grupo H) |
| `acertos_LC` … `acertos_MT` | `33` | "33 de 45" e faixa do texto do plano |
| `media` | `752.5` | Média das 4 objetivas. Vazio = média das 4 notas. **Use o valor sem arredondar** |
| `curso_id` | `MEDICINA_UFMG` | Chave de `ref_cursos.csv`. Vazio = grupo E |
| `area_prioritaria` | `CN` | Área de maior déficit ponderado pelo peso do curso |
| `area_mais_perto` | `CH` | Só no texto do grupo B ("em Humanas, você está mais perto…") |
| `faceis_ids` | `129\|107\|97` | Fáceis da área prioritária que errou, **nº canônico**, % de acerto decrescente |
| `faceis_marcadas` | `E\|E\|E` | Letra marcada em cada uma; `-` = branco |
| `modelos_errados_ids` | `116\|125\|101` | Questões modelo da área prioritária que errou (nº canônico). Vazio = acertou as 5 |
| `grupo_forcado` | | Opcional: força um grupo, ignorando a regra |

**O grupo não vem da base**, ele é calculado (`distância = nota_top10 − média`): M (nenhum dia),
F/G (um dia), H (nota faltando), E (sem curso), D (≤ −5), A0 (|d| < 5), A_topo (5 ≤ d < 20),
A (20 ≤ d ≤ 60), B (> 60, Medicina), C (> 60, outros cursos).

## `dados/`: o que é igual para todo mundo

| Arquivo | Conteúdo | Chave |
|---|---|---|
| `ref_questoes.csv` | tema, % de acerto, gabarito, `engana_A`…`engana_E`, coelho, etiqueta/vídeo de questão modelo | `questao_id` |
| `ref_numeracao.csv` | número no caderno de cada cor | `cor_caderno` + `questao_id` |
| `ref_modelos.csv` | as 20 questões modelo: título, %, professor/data, texto, vídeo, ordem | `questao_id` |
| `textos_plano.csv` | título, texto, itens, "como a gente trabalha" | `area` + faixa (`acertos_min`–`acertos_max`) |
| `ref_cursos.csv` | curso, IES, artigo (na/no), é Medicina, nota dos 10%, pesos | `curso_id` |
| `ref_areas.csv` | nome, slug do Matrix, dia, pontos de uma fácil / difícil | `area` |
| `grupos.csv` | camadas de copy de cada grupo, UTM, rótulo da prévia, se recebe 2ª fase | `grupo` |
| `copy.csv` | **todos os textos fixos**, com `{variáveis}` | `camada` + `campo` |
| `colunas.txt` | as 324 colunas do `alunos.csv`, na ordem | |

### Copy em camadas

Cada grupo junta camadas, e a última sobrescreve a anterior. Por exemplo, o A usa
`COMUM DIAG CURSO SEGURO A`, e com `--bf-aberta` ganha também `SEGURO_BF`. Assim o card do Seguro
Aprovação está escrito **uma vez** e serve A, A_topo, A0 e D.

As variáveis que o `montar_csv.py` preenche são `{area}`, `{area_mais_perto}`, `{curso}`, `{ies}`,
`{na_ies}`, `{media}`, `{pontos}`, `{nota_top10}`, `{n_faceis}`, `{n_modelos}`, `{pct_min}`, `{pct_max}`,
`{pontos_facil}`, `{pontos_dificil}`, `{considerando}`, `{dominio}`, `{utm}` e `{utm_grupo}`.
`{nome}` continua sendo trocado pelo `gerar.py`.

As regras que estão no código, e não em texto:
- **Facil:** o número no caderno sai de `ref_numeracao` e a URL é montada a partir do número canônico. "Por que a X engana" usa o texto da letra marcada, cortado em ~180 caracteres. O coelho só aparece quando não há explicação para a letra marcada (ou quando o aluno deixou em branco).
- **Modelos:** o título muda entre "errou N das 5", "errou as 5" e "acertou as 5". Quando o aluno acertou todas, não há lista e a nota de rodapé muda. Nos grupos M entram as 20 questões, com números do Azul e agrupadas por área (CN, MT, LC, CH).
- **Plano:** a área prioritária vem primeiro e as outras seguem na ordem LC, CH, CN, MT.
- **Nota parcial:** cada área recebe a nota, "falta lançar" ou "incompleta".
- **Rótulo da prévia:** a contagem de pessoas é calculada a partir da base.

---

## O que falta confirmar ou completar

As tabelas de `dados/` foram extraídas das 14 linhas da prévia, então só cobrem o que aparece nelas:

1. **`ref_questoes.csv`** tem 14 questões. Faltam as 15 mais acertadas de cada área (60), com a explicação de todas as alternativas.
2. **`ref_numeracao.csv`** tem 44 pares. Faltam as 4 cores × 180 questões, a partir dos gabaritos oficiais. LC 1–5 depende da língua.
3. **Faixas do plano (`acertos_min`/`acertos_max`)** são **provisórias**: cobrem os acertos vistos na prévia, mas os cortes reais não aparecem nela. Humanas só tem 1 faixa nos exemplos, então quem tiver poucos acertos em CH receberia "Humanas pode compensar a sua área mais fraca".
4. **`ref_cursos.csv`**: a `nota_top10` de Direito/UFU (714) foi deduzida do exemplo C. Os pesos estão vazios. Hoje `area_prioritaria` e `area_mais_perto` vêm prontas na base. Com os pesos e a média de cada área por curso, dá para calculá-las no script.
5. **Pontos de uma fácil / difícil** só existem para CN (24/11) e CH (14/8). Faltam LC e MT.
6. **Copy de Black Friday** só existe para A (Seguro) e C (proposta). Com `--bf-aberta`:
   - A_topo, A0 e D usam o `SEGURO_BF` do A, conforme as instruções;
   - **B, E e M continuam com "Me avise quando abrir"**, porque não há copy de BF para eles. É preciso escrever essas camadas (`B_BF`, `E_BF`, `M_BF`) em `copy.csv` e incluí-las em `grupos.csv`.
7. **Seguro Aprovação** fala em "Extensivo Medicina 2027". Se A, A_topo, A0 ou D tiverem alunos de outros cursos, falta a copy para eles.
8. **Arredondamento:** a média e a distância são arredondadas como na prévia (0,5 vai para o par: 752,5 → 752). No exemplo do A0, a média exibida (762) não é a média das notas inteiras (761,25), por isso `media` está explícita na base de exemplo. Na base real, use a média sem arredondar.
9. **Domínio:** os links usam `SEU-DOMINIO`. Passe o real com `--dominio`.
