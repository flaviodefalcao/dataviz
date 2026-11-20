> **Para gerar o site, veja [COMO_GERAR.md](COMO_GERAR.md).** Um comando: `python3 gerar_site.py base_alunos.csv`.

# Páginas de diagnóstico parametrizadas

```
template.html          layout (Mustache padrão). Textos fixos ficam aqui.
montar_csv.py          base_alunos.csv (compacta) + dados/ -> alunos.csv de 324 colunas. Ver OTIMIZACAO.md
dados/                 tabelas de referência e copy (cada texto escrito uma vez só)
testes/                base_exemplos.csv, alunos_exemplo.csv (prévia de 18/11) e conferir.py
alunos.csv             gerado pelo montar_csv.py. 1 linha = 1 aluno (324 colunas, separador ;).
dicionario_campos.csv  o que cada coluna faz e quando o bloco aparece
gerar.py               CSV + template -> saida/<aluno_id>.html e saida/_previa.html
assets/                logos (embutidos nas páginas; ou passe URL com --logo-topo/--logo-marca)
```

## Rodar
```
python3 montar_csv.py base_alunos.csv [--bf-aberta] [--fase2-aberta] [--dominio X]
python3 gerar.py                 # usa alunos.csv
python3 gerar.py base.csv -o out --json
```
Só a biblioteca padrão do Python. O CSV pode estar com `;` ou `,`, em UTF-8.

## Regras
- **Um bloco aparece quando a coluna-chave dele está preenchida.** Não há lógica escondida por grupo:
  `curso_nome`, `alerta_titulo`, `faceis_titulo`, `modelos_titulo`, `area1_codigo`, `parcial_*`,
  `seguro_titulo`, `fase2_titulo`, `proposta_titulo`, `indicacao_titulo`.
- **Listas usam colunas numeradas**: `facil1_…`, `modelo1_…`, `area1_…`. Para ter mais itens, crie
  `facil6_…`, `modelo21_…`; o gerador lê quantas houver. Linha com `_num` vazio é ignorada.
- **Itens dentro de uma célula** (o que estudar, chips) são separados por `|`.
- **Placeholders**: `{coluna}` em qualquer célula vira o valor daquela coluna (`{nome}`, `{grupo}`).
  Colunas extras no CSV são ignoradas pelo layout, mas servem como placeholder.
- **Calculado pelo gerador** (não precisa coluna): arco dos medidores (a partir da nota), largura das
  barras parciais ((nota−300)/700), chips de pontos fáceis (números em ordem crescente), nome da área
  a partir do código, frase "Você marcou X / deixou em branco", "Por que a X engana:".

## Usar em outro sistema
O template é Mustache padrão (mustache.js, chevron, PHP Mustache...). Rode `gerar.py --json`
para ver o objeto que o template espera e porte a função `montar_modelo()`.

## Conferência
As 14 linhas de `testes/alunos_exemplo.csv` são as 14 versões da prévia de 18/11 (`python3 testes/conferir.py` remonta e compara). Gerando a partir delas, o conteúdo
renderizado bate com a prévia original, página por página.
