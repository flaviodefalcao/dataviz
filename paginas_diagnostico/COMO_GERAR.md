# Como gerar o site (guia para o programador)

Só precisa de **Python 3.8+**, sem nenhuma biblioteca extra.

## 1. Testar agora, com a base fictícia

```bash
cd paginas_diagnostico
python3 scripts/gerar_base_ficticia.py                    # cria base_alunos_ficticia.csv (81.550 alunos, ~2 s)
python3 gerar_site.py base_alunos_ficticia.csv --amostra 3 # 3 páginas por grupo + build/site/_previa.html
```

Abra `build/site/_previa.html` no navegador para ver todos os grupos de uma vez.

> A base fictícia tem nomes e notas **inventados**, só para testar. Ela respeita a quantidade de alunos
> de cada grupo da prévia (A 4.770, A topo 1.457, A0 486, B 2.025, C 10.035, D 1.842, E 17.496, F 21.377,
> G 11.337, H 214, M aluno 2.469, M grátis 8.042).

## 2. Gerar com os dados reais

1. Exporte do banco um `base_alunos.csv` no formato da seção 3.
2. Rode:

```bash
python3 gerar_site.py base_alunos.csv \
    --dominio www.seusite.com.br \
    --logo-topo  https://cdn.seusite.com.br/diagnostico/logo_topo.png \
    --logo-marca https://cdn.seusite.com.br/diagnostico/logo_marca.png
```

3. Leia o `build/relatorio.txt`, que traz a contagem por grupo, avisos (questão sem conteúdo, numeração faltando,
   faixa de plano faltando) e campos obrigatórios vazios. **Corrija em `dados/` e rode de novo** até não sobrar aviso.
4. Publique a pasta `build/site/` como arquivos estáticos. É uma página por aluno: `<aluno_id>.html`.

**Passe os logos por URL.** Sem URL, o logo vai embutido em base64 em toda página: ~105 KB por página e
~8,5 GB no total. Com URL: ~22 KB por página e ~1,8 GB no total.

### Datas: só muda a flag, a base é a mesma

| Quando | Comando |
|---|---|
| Até ~25/11 | `python3 gerar_site.py base_alunos.csv ...` |
| ~25/11 (2ª fase) | `... --fase2-aberta` (liga o card de 2ª fase para A topo, A0 e D) |
| A partir de 27/11 (Black Friday) | `... --bf-aberta --fase2-aberta` (troca "Me avise" por checkout) |

### Tempo (81.550 alunos, 1 CPU)

| Etapa | Tempo |
|---|---|
| `base_alunos.csv` → `build/alunos.csv` (447 MB) | ~22 s |
| Páginas HTML | ~1,5 min (≈ 6,5 s a cada 5.000) |

## 3. O que o export do banco precisa ter (`base_alunos.csv`)

UTF-8, separador `;`, 1 linha por aluno, com estas colunas e este cabeçalho (a ordem não importa).
Listas dentro de uma célula vão separadas por `|`.

| Coluna | Tipo | Exemplo | Origem / regra |
|---|---|---|---|
| `aluno_id` | texto único | `a8f3k2…` | Vira o nome do arquivo. **Use um id não sequencial ou um token**, já que a página é pessoal |
| `nome` | texto | `Ana` | Só o primeiro nome |
| `tipo_conta` | `pagante` / `gratuito` | `pagante` | Aluno do Chapéu ou usuário gratuito do Matrix |
| `dia1_lancado` | `sim` / `nao` | `sim` | Lançou o gabarito do dia 1 (LC + CH) |
| `dia2_lancado` | `sim` / `nao` | `sim` | Lançou o gabarito do dia 2 (CN + MT) |
| `caderno_dia1`, `caderno_dia2` | cor | `Amarelo` | Cor do caderno lançado em cada dia |
| `lingua` | `ingles` / `espanhol` | `ingles` | Reservado (LC 1–5) |
| `nota_LC`, `nota_CH`, `nota_CN`, `nota_MT` | número | `724` | Nota TRI estimada. **Vazia** se o dia não foi lançado ou se a área ficou incompleta |
| `acertos_LC` … `acertos_MT` | 0–45 | `33` | Acertos na área |
| `media` | número | `752.5` | Média das 4 objetivas, **sem arredondar**. Vazia = o script calcula |
| `curso_id` | texto | `MEDICINA_UFMG` | 1ª opção no Sisu. Precisa existir em `dados/ref_cursos.csv`. Vazio = sem curso |
| `area_prioritaria` | `LC`/`CH`/`CN`/`MT` | `CN` | Área de maior déficit em relação aos alunos do mesmo curso, ponderado pelo peso |
| `area_mais_perto` | área | `CH` | Só usado no grupo B |
| `faceis_ids` | lista | `129\|107\|97` | Entre as 15 questões **da área prioritária** com maior % de acerto: as que o aluno errou ou deixou em branco. **Número canônico** (= caderno Azul), por % de acerto decrescente, no máximo 5 |
| `faceis_marcadas` | lista | `E\|-\|B` | Letra marcada em cada questão de `faceis_ids`, na mesma ordem. `-` = em branco |
| `modelos_errados_ids` | lista | `116\|125` | Questões modelo da área prioritária que o aluno errou (número canônico). Vazio = acertou todas |

**O grupo (A, A0, B… M) é calculado pelo script**, não vem do banco. A regra está em `montar_csv.py`, na função `classificar()`.

Exemplo de linha:
```
aluno_id;nome;tipo_conta;dia1_lancado;dia2_lancado;caderno_dia1;caderno_dia2;lingua;nota_LC;nota_CH;nota_CN;nota_MT;acertos_LC;acertos_CH;acertos_CN;acertos_MT;media;curso_id;area_prioritaria;area_mais_perto;faceis_ids;faceis_marcadas;modelos_errados_ids
a8f3k2;Ana;gratuito;sim;sim;Amarelo;Amarelo;ingles;687;759;724;840;39;41;33;36;752.5;MEDICINA_UFMG;CN;;129|107|97;E|E|E;116|125|101
```

## 4. Mapa dos arquivos

```
paginas_diagnostico/
├── gerar_site.py          ← o único comando que o programador precisa rodar
├── montar_csv.py          base compacta + dados/ → alunos.csv de 324 colunas (regras de grupo e de copy)
├── gerar.py               alunos.csv + template.html → páginas (não mexer)
├── template.html          layout (não mexer)
├── dados/                 tabelas: questões, numeração, modelos, plano, cursos, áreas, grupos, copy
├── scripts/
│   ├── gerar_base_ficticia.py
│   └── extrair_dos_exemplos.py
├── testes/
│   ├── conferir.py        teste de regressão: remonta as 14 páginas da prévia (tem que dar 0 diferenças)
│   ├── base_exemplos.csv
│   └── alunos_exemplo.csv
├── COMO_GERAR.md          este guia
└── OTIMIZACAO.md          por que a base é assim e o que ainda falta completar em dados/
```

Depois de qualquer mudança em `dados/` ou nos scripts, rode `python3 testes/conferir.py`.

## 5. Antes de ir para produção

Os dados de referência em `dados/` saíram das 14 páginas da prévia e **ainda estão incompletos**. O
`relatorio.txt` vai acusar o que faltar, e a lista completa está no fim do `OTIMIZACAO.md`. Os principais:

- todas as questões no `ref_questoes.csv`: as 15 mais acertadas de cada área, com a explicação de cada alternativa;
- a numeração das 4 cores no `ref_numeracao.csv` (o Azul não precisa: o número do Azul é o canônico);
- todos os cursos no `ref_cursos.csv`, com a nota dos 10% e os pesos;
- os cortes de acertos do `textos_plano.csv`;
- a copy de Black Friday para os grupos B, E e M.

A base fictícia só usa Natureza e Humanas como área prioritária, porque são as únicas áreas com questões fáceis em `dados/`.
