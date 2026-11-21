# Analista BTC para swing trade

Analisa o Bitcoin em cinco pilares, dá uma nota de -100 (baixista) a +100 (altista) e monta
planos de trade com **ganho/perda mínimo de 2:1 já descontadas as taxas**, stop técnico e
tamanho de posição pelo risco.

| Pilar | Peso | O que olha |
|---|---|---|
| Tendência | 30% | Semanal, diário e 4h: EMAs 20/50/200, inclinação, topos e fundos, ADX |
| Técnico | 25% | RSI, MACD, Bollinger, distância da média em ATRs, volume, OBV, divergências |
| Macro | 20% | Dólar (DXY), juros de 10 anos dos EUA, Nasdaq, VIX, ouro, correlação BTC × bolsa |
| Sentimento e índices | 15% | Fear & Greed, funding, open interest, long/short, dominância (leitura contrária) |
| Notícias | 10% | Manchetes de CoinDesk, Cointelegraph, Decrypt, Bitcoin Magazine e The Block; eventos como FOMC e CPI |

Todas as fontes são públicas e **não pedem API key**. Se uma fonte falhar, o pilar fica
"indisponível" e a nota usa só os outros.

## Instalação

```bash
pip install -r requirements.txt
```

## Uso

```bash
# análise real (precisa de internet)
python -m btc_analyst --capital 5000 --risco 1 --html relatorio_btc.html

# demonstração com dados simulados, sem internet
python -m btc_analyst --demo --html demo.html
```

| Opção | Padrão | Significado |
|---|---|---|
| `--capital` | 10000 | capital em USDT |
| `--risco` | 1 | % do capital arriscado por trade |
| `--rr` | 2 | ganho/perda mínimo |
| `--taxa` | 0.1 | taxa por lado em % (0,1% = spot Binance sem BNB) |
| `--alavancagem` | 1 | alavancagem máxima (1 = spot) |
| `--html` / `--json` | | salva o relatório nesses formatos |

## Como o plano é montado

1. **Viés:** nota ≥ +15 só procura compras; ≤ -15 só vendas; entre os dois mostra os dois lados
   como planos condicionais.
2. **Entradas:** a mercado e por pullback (ordem limite no suporte médio/forte mais próximo).
3. **Stop:** além do nível que protege o trade, com folga de 0,5 ATR (4h); nunca mais perto
   que 1 ATR (4h) nem mais longe que 10%.
4. **Alvo 1:** exatamente 2R líquido de taxas. Se houver resistência (suporte, no short) com
   2 ou mais toques antes dele, o plano é recusado e o analista calcula a **entrada máxima**
   que tornaria o trade 2:1. Se ela for viável, cria um plano de ordem limite nesse preço.
5. **Alvo 2:** próxima resistência relevante até 5R, ou 3R.
6. **Tamanho:** `risco em USDT / (distância do stop + taxas)`, limitado pelo capital.
   Com evento macro no radar (FOMC, CPI, payroll) o risco cai pela metade.

O relatório HTML traz gráfico interativo (4h e diário, com EMAs, entrada, stop e alvos),
RSI, notas por pilar, motivos de cada nota, notícias e níveis.

## Testes

```bash
pip install pytest && python -m pytest tests
```

> Análise automática e educativa, não é recomendação de investimento.

## Site com senha na Vercel

A pasta `api/` tem uma função da Vercel que gera o relatório a cada acesso (dados
reaproveitados por 10 minutos) e pede senha.

1. Em vercel.com, **Add New → Project** e importe este repositório.
2. Em **Settings → Environment Variables**, crie `RELATORIO_SENHA` com a senha desejada.
3. Faça o deploy. O navegador pede usuário e senha: o usuário pode ser qualquer um.

O `vercel.json` roda a função em São Paulo (`gru1`), onde a Binance responde. Parâmetros
opcionais: `?capital=5000&risco=1&rr=2`. Sem a variável `RELATORIO_SENHA`, o site não abre.
