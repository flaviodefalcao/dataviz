# Calibração TRI do Simulado 1 CDM com 100 IAs

- `respostas_ias/ai_XXX.txt`: respostas de cada IA (000–029 haiku, 030–059 sonnet, 060–099 opus; fração de questões em "modo intuição" decresce dentro de cada modelo).
- `key.json`: gabarito usado na correção (Q128 corrigida para E).
- `parametros_por_questao.csv`: a, b (IC 90% por bootstrap), c e situação de cada questão. `b_ENEM_like = 500 + 100·b` é só convenção; a escala é a do grupo de IAs, não a da população do ENEM.
- `respondentes.csv`: acertos e θ estimado de cada IA. `resumo_ias.png`: gráficos.
- `estimar_ias.py`: EM marginal 2PL/3PL em grade, θ~N(0,1), c com prior forte em 0,20.

Limitações: as IAs acertam ~96% da prova (escore médio 86,5/90), então só ~6 questões têm a/b confiáveis; c não é estimável.
O "modo intuição" não foi respeitado de forma confiável pelos agentes. Fable indisponível (exige créditos).
