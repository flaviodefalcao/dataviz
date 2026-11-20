# E-mails do diagnóstico

Um e-mail curto por pessoa, que leva à página de diagnóstico dela. O título chama atenção, o texto tem 2 parágrafos e há um botão.
Cada grupo tem o seu texto, personalizado com nome, curso, IES, média, pontos que faltam, área e quantidade de questões fáceis.

## Arquivos

| Arquivo | O que é | Editar? |
|---|---|---|
| `textos_email.csv` | assunto, pré-cabeçalho, título, `p1`, `p2`, `p3` (opcional) e botão **por grupo**, com `{variáveis}` | **sim: é aqui que se muda o texto** |
| `template_email.html` | layout do e-mail (tabelas e estilos inline: Gmail, Outlook, Apple Mail, celular) com campos `{{...}}` | só o visual |
| `gerar_emails.py` | cruza a base com o arquivo de usuários e gera `saida/emails.csv` e `saida/emails_previa.html` | — |

## Rodar

Já roda dentro do `python3 gerar_tudo.py`. Para rodar sozinho:

```bash
python3 emails/gerar_emails.py \
    --url-pagina "https://www.seusite.com.br/diagnostico/{aluno_id}.html" \
    --logo-url https://cdn.seusite.com.br/diagnostico/logo_topo.png \
    --descadastro-url "{{unsubscribe}}"        # o código de descadastro da sua ferramenta de disparo
```

Saídas:
- **`saida/emails.csv`**: 1 linha por pessoa, com `user_id;email;grupo;assunto;preheader;titulo;p1;p2;p3;botao;link`.
  O link já vem com UTM (`utm_source=email&utm_content=<grupo>`).
- **`saida/emails_previa.html`**: um e-mail de cada grupo, com o assunto em cima, para revisar.
- `saida/emails_html/<user_id>.html` (com `--html`): o e-mail pronto de cada pessoa, para ferramentas que pedem o HTML inteiro.

## Como disparar

**Ferramenta com campos de mesclagem** (Mailchimp, RD Station, Brevo, SendGrid, Amazon SES…):
1. Importe `saida/emails.csv` como lista ou contatos. As colunas viram campos.
2. Cole o `template_email.html` como template e troque `{{campo}}` pela sintaxe da ferramenta
   (ex.: Mailchimp `*|TITULO|*`, Brevo `{{ contact.TITULO }}`).
3. Assunto = campo `assunto`; pré-cabeçalho = campo `preheader`.

**Ferramenta que só aceita HTML pronto:** rode com `--html` e envie `saida/emails_html/<user_id>.html` para o `email` da linha.

## Variáveis disponíveis em `textos_email.csv`

`{nome}` · `{saudacao}` ("Oi, Ana!" / "Oi!") · `{curso}` · `{ies}` · `{na_ies}` ("na UFMG") · `{media}` · `{pontos}` ·
`{nota_top10}` · `{area}` · `{frase_faceis}` ("separamos as 6 questões fáceis que escaparam, com a explicação de cada uma.") ·
`{nota_LC}` `{nota_CH}` `{nota_CN}` `{nota_MT}` · `{areas_sem_nota}` ("Linguagens e Humanas ainda não têm nota")

Sem nome, um texto que começa com `{nome}, ` começa direto: "Faltam 33 pontos para…".

## Grupos

Os mesmos da página, mais duas variações do V:
- **V**: comprou ou tem plano pago e lançou os dois dias.
- **V_sem_gabarito**: comprou ou tem plano pago, mas não lançou gabarito.

Quem é V e lançou só um dia recebe o e-mail do F, G ou H. Nenhum e-mail tem oferta: a venda fica na página.

| Grupo | Assunto (exemplo real) |
|---|---|
| A | Lany, faltam 33 pontos para Direito na UESPI |
| A_topo | Ludmilla, você está a 10 pontos de Medicina na UFES |
| A0 | Aloisio, você está empatado em Medicina na UFAL |
| B | O seu caminho até Medicina começa por aqui |
| C | O seu ponto de partida para Ciência da Computação está pronto |
| D | Você está entre os 10% em Direito 🎉 |
| E | Sua média estimada é 677. Onde ela te leva? |
| F / G | Falta só o dia 2 (ou 1) para fechar a sua nota |
| H | A sua nota está quase pronta |
| M_gratis | Saiu o gabarito oficial: corrija a sua prova em 3 minutos |
| V | Bruna, o seu diagnóstico do Enem está pronto |
| V_sem_gabarito | Pedro, veja onde o seu estudo apareceu no Enem |

## Antes de disparar

- Passe o **domínio** e o **caminho real** das páginas em `--url-pagina` e o **logo** por URL (a imagem precisa estar hospedada).
- Configure o **descadastro** (`--descadastro-url` ou o código da ferramenta).
- Mande para você mesmo um e-mail de cada grupo (use a prévia) e teste no Gmail e no Outlook.
