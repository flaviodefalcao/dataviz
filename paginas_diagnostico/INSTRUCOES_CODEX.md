# Tarefa: montar o alunos.csv a partir dos dados do repositório

## Contexto
A pasta `paginas_diagnostico/` tem um gerador de páginas de diagnóstico do Enem 2026:
- `template.html`: layout (não mexer)
- `gerar.py`: lê `alunos.csv` e gera uma página por aluno
- `dicionario_campos.csv`: o que cada coluna faz e quando o bloco aparece. **Leia antes de tudo.**
- `alunos.csv`: 14 linhas de exemplo, uma por grupo. São a **referência de copy e de formato**.

O seu trabalho é escrever um script determinístico, `montar_csv.py`, que lê os dados reais do
repositório e grava um `alunos.csv` completo, com uma linha por aluno e exatamente as mesmas colunas do exemplo.
**Não gere conteúdo aluno por aluno "na mão" nem com LLM**: são dezenas de milhares de linhas. Todo
texto variável sai de dado ou de regra.

## Etapa 1: mapear antes de codar (pare e me mostre)
1. Localize no repositório as fontes de:
   - cadastro do aluno (id, nome, se é aluno pagante ou gratuito)
   - gabarito lançado (respostas por questão, cor do caderno, dias lançados)
   - gabarito oficial e a tabela de correspondência de numeração caderno ↔ número canônico (URL do Matrix)
   - notas estimadas por área e média (TRI)
   - curso/IES escolhido no Sisu e a nota dos 10% mais bem colocados por curso+IES
   - % de acerto por questão na base do Matrix
   - conteúdo por questão: assunto, explicação do distrator por alternativa ("por que a X engana"),
     dica "tirando o coelho do chapéu", vínculo com questão modelo/vídeo
   - as 20 questões modelo (5 por área): título, professor, data, texto, link do vídeo com timestamp
   - textos do plano por área e por faixa de acertos (título, texto, itens, "como a gente trabalha")
   - pesos das áreas por curso
2. Entregue uma tabela **coluna do CSV → fonte (arquivo/tabela.campo) ou regra**, e liste o que
   **não encontrou**. Não invente fonte nem valor para o que faltar. Espere a minha confirmação.

## Etapa 2: regras de negócio (extraídas da prévia; confirme cada uma com os dados)

### Grupo de cada aluno (coluna `grupo`)
Use `distância = nota_top10_do_curso − média_do_aluno`.
| grupo | condição |
|---|---|
| M_aluno / M_gratis | não lançou gabarito (pagante / gratuito) |
| F | lançou só o dia 1 |
| G | lançou só o dia 2 |
| H | lançou os dois dias, mas com respostas em branco que impedem a nota de alguma área |
| E | dois dias completos, sem curso escolhido no Sisu |
| D | média acima da nota dos 10% (distância ≤ −5) |
| A0 | empatado: |distância| < 5 |
| A_topo | 5 ≤ distância < 20 |
| A | 20 ≤ distância ≤ 60 |
| B | distância > 60 e curso = Medicina |
| C | distância > 60, outros cursos |
Confirme os limites exatos (inclusive se ≤ ou <) com quem definiu a segmentação.

### Copy por grupo
Para cada grupo, a linha de exemplo correspondente em `alunos.csv` é o **modelo de texto**. Copie os
textos fixos dela e substitua só os valores do aluno: nome, pontos, curso, IES, área, notas,
contagens e caderno. Transforme cada frase de exemplo num template com variáveis. Por exemplo,
`"são 24 pontos até os mais bem colocados em Medicina na UFMG"` vira
`"são {distancia} pontos até os mais bem colocados em {curso} na {ies}"`.
Atenção a plural/singular ("1 ponto", "1 das 5 questões") e a "a"/"o" antes da IES.

### Datas (configuração do script, não coluna)
- `bf_aberta` (a partir de 27/11): os grupos A, A_topo, A0, D e C trocam pelo copy das linhas
  `A_BF` e `C_BF` (preço aberto, botão de checkout no lugar de "Me avise").
- `fase2_aberta` (por volta de 25/11): liga o card `fase2_*` para A_topo, A0 e D.
Os dois devem ser flags na linha de comando, por exemplo `--bf-aberta`.

### Área prioritária (`area1_codigo`)
É a área em que o aluno está mais abaixo dos outros alunos do mesmo curso, **ponderada pelo peso da
área no curso**. Sem curso (grupo E), use a área com maior déficit sem peso. As outras três áreas
seguem na ordem LC, CH, CN, MT.

### Pontos fáceis (`facilN_*`)
- Universo: as 15 questões da área prioritária com maior % de acerto na base do Matrix.
- Entram as que o aluno errou ou deixou em branco, ordenadas por % de acerto decrescente.
- `facilN_num` é o número **no caderno do aluno**. `facilN_url` usa o número **canônico**.
  Por exemplo, a 125 do Amarelo aponta para `questao-129`.
- `facilN_marcada` fica vazia se o aluno deixou em branco.
- `facilN_engana` é a explicação do distrator **da letra que o aluno marcou**. Se for maior que
  cerca de 180 caracteres, corte na palavra e termine com "…".
- `faceis_titulo` usa "Você errou {n} das 15 questões de {área} que mais alunos acertaram".
- `faceis_rodape` usa os pontos médios de uma fácil e de uma difícil **naquela área** (dado da base).
- Se o aluno não errou nenhuma fácil, deixe `faceis_titulo` vazio, e o bloco some.
- O CSV tem 5 posições. Se o aluno puder ter mais, crie `facil6_…` em diante (o gerador aceita).

### Modelos (`modeloN_*`)
- Use as 5 questões modelo da área prioritária. Liste as que o aluno errou, na ordem do exemplo.
- O número é o do caderno do aluno. `modeloN_questao_url` usa o número canônico.
- Se acertou todas, use o título "Você acertou as 5…" e o `modelos_resumo` da linha D, sem lista.
- Grupos M (sem gabarito): as 20 questões, números do caderno Azul, `modeloN_grupo` preenchido
  com "{Área}: {min}% a {max}% de acerto", na ordem CN, MT, LC, CH (igual ao exemplo).
- A faixa "Só entre X% e Y%" de `modelos_nota` sai do mínimo e do máximo de acerto dos 5 modelos da área.

### Plano (`areaN_*`)
- `areaN_nota` é a nota estimada da área. `areaN_acertos` são os acertos de 45.
- `areaN_titulo`, `areaN_texto`, `areaN_itens` (separados por " | ") e `areaN_como` vêm da tabela
  de textos por **área × faixa de acertos**. Entregue essa tabela como arquivo de dados
  (`textos_plano.csv`), não como `if` no código.

### Nota parcial (F, G, H)
`parcial_XX` recebe a nota da área se ela existir. Se o dia não foi lançado, recebe "falta lançar".
Se a área está incompleta, recebe "incompleta". As outras colunas de bloco ficam vazias.

### UTMs
Mantenha o padrão dos exemplos: `utm_source=pagina&utm_medium=diagnostico&utm_campaign=bf2026`,
com `utm_content` = grupo nos CTAs e `questao` nos links de questão. Troque `SEU-DOMINIO` pelo
domínio real (pergunte qual é).

## Etapa 3: validação (obrigatória antes de entregar)
1. Rode `montar_csv.py` e depois `python3 gerar.py alunos.csv`.
2. Teste de regressão: monte com o script as linhas dos alunos que originaram a prévia, se
   existirem nos dados, e compare com as 14 linhas de exemplo, coluna por coluna. Liste as diferenças.
3. Imprima a contagem de alunos por grupo e compare com a prévia: A 4.770, A topo 1.457, A0 486,
   B 2.025, C 10.035, D 1.842, E 17.496, F 21.377, G 11.337, H 214, M aluno 2.469, M grátis 8.042.
4. Liste as linhas com coluna-chave preenchida mas campo obrigatório do bloco vazio. Por exemplo,
   `facil2_num` sem `facil2_url`, ou `curso_nome` sem `curso_media`.
5. Abra 1 página gerada de cada grupo e confira visualmente.

## Restrições
- Não altere `template.html` nem `gerar.py`. Se precisar de um campo novo, me pergunte.
- Saída em UTF-8 com BOM, separador `;`, mesmas colunas e na mesma ordem do exemplo.
- Nada de dados pessoais além de `nome` e `aluno_id` no CSV.
