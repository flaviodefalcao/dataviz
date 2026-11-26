"""Calibração TRI (a, b, c) do Simulado 1 CDM a partir das respostas de 100 IAs.
Entrada: respostas em answers/ai_XXX.txt (linhas '91:E'), gabarito em key.json, agentes em agents.json.
Saída: CSV por questão, gráficos e resumo."""
import os, sys, json, csv
import numpy as np
from scipy.optimize import minimize

S = sys.argv[1]            # pasta scratchpad com answers/, key.json, agents.json
OUT = sys.argv[2]          # pasta de saída
NBOOT = int(sys.argv[3]) if len(sys.argv) > 3 else 100
D = 1.7
key = json.load(open(f"{S}/key.json"))
agents = {a[0]: a for a in json.load(open(f"{S}/agents.json"))}
Q = [str(q) for q in range(91, 181)]

ids, rows, resp = [], [], []
for f in sorted(os.listdir(f"{S}/answers")):
    i = int(f[3:6])
    a = dict(l.strip().split(":") for l in open(f"{S}/answers/{f}") if ":" in l)
    if len(a) != 90: continue
    ids.append(i); resp.append([a[q] for q in Q]); rows.append([int(a[q] == key[q]) for q in Q])
X = np.array(rows, dtype=float); resp = np.array(resp)
N, J = X.shape
print("respondentes:", N, "itens:", J, "| escore médio:", X.sum(1).mean().round(1))
model_of = [agents[i][1] for i in ids]

grid = np.linspace(-4, 4, 41); w = np.exp(-grid**2/2); w /= w.sum()

def icc(a, b, c): return c + (1-c)/(1+np.exp(-D*a*(grid[:, None]-b)))

def fit(X, c_mode="prior", iters=80):
    n, J = X.shape
    p = np.clip(X.mean(0), .02, .98)
    a = np.full(J, 1.0); b = -np.log(p/(1-p))/ (D*1.0); c = np.full(J, 0.2)
    prev = -np.inf
    for it in range(iters):
        P = np.clip(icc(a, b, c), 1e-9, 1-1e-9)
        L = X @ np.log(P).T + (1-X) @ np.log(1-P).T + np.log(w)
        m = L.max(1, keepdims=True); post = np.exp(L-m); s = post.sum(1, keepdims=True); post /= s
        ll = (m[:, 0]+np.log(s[:, 0])).sum()
        nk = post.sum(0); rk = post.T @ X
        for j in range(J):
            def nll(pp):
                aa, bb = pp[0], pp[1]
                cc = pp[2] if c_mode == "prior" else 0.2
                P_ = np.clip(cc+(1-cc)/(1+np.exp(-D*aa*(grid-bb))), 1e-9, 1-1e-9)
                v = -(rk[:, j]*np.log(P_)+(nk-rk[:, j])*np.log(1-P_)).sum()
                v += 0.5*((np.log(aa)-np.log(1.0))/0.5)**2        # prior em a: lognormal(0, 0.5)
                v += 0.5*(bb/3.0)**2                               # prior fraca em b: N(0, 3^2)
                if c_mode == "prior": v -= (30-1)*np.log(cc)+(120-1)*np.log(1-cc)   # Beta(30,120): c ~ 0.20 +- 0.03 (informa pouco o dado)
                return v
            x0 = [a[j], b[j]] + ([c[j]] if c_mode == "prior" else [])
            bd = [(0.2, 4), (-4, 4)] + ([(0.05, 0.4)] if c_mode == "prior" else [])
            r = minimize(nll, x0, bounds=bd, method="L-BFGS-B")
            a[j], b[j] = r.x[:2]
            if c_mode == "prior": c[j] = r.x[2]
        if abs(ll-prev) < 0.05: break
        prev = ll
    return a, b, c, post @ grid

a, b, c, theta = fit(X, "prior")
a2, b2, c2, _ = fit(X, "fixo")           # c fixo em 0,20 (convenção ENEM)

# bootstrap sobre respondentes para incerteza de b e a
rng = np.random.default_rng(7)
Ba = np.zeros((NBOOT, J)); Bb = np.zeros((NBOOT, J))
for r in range(NBOOT):
    idx = rng.integers(0, N, N)
    ar, br, cr, _ = fit(X[idx], "fixo", iters=40)
    Ba[r] = ar; Bb[r] = br
b_lo, b_hi = np.percentile(Bb, [5, 95], axis=0); a_lo, a_hi = np.percentile(Ba, [5, 95], axis=0)

acerto = X.mean(0)
# confiabilidade da estimativa
def flag(j):
    if acerto[j] >= 0.98: return "nao_estimavel (>=98% acerto)"
    if acerto[j] >= 0.90: return "pouco_informativo (>=90% acerto)"
    if (b_hi[j]-b_lo[j]) > 2.5: return "incerto (IC90% largo)"
    return "ok"

os.makedirs(OUT, exist_ok=True)
with open(f"{OUT}/parametros_por_questao.csv", "w", newline="") as f:
    wr = csv.writer(f)
    wr.writerow(["questao","gabarito","pct_acerto_100IAs","a","a_IC90_inf","a_IC90_sup","b","b_IC90_inf","b_IC90_sup","b_ENEM_like","c","b_c_fixo_0.20","situacao","alternativa_mais_marcada_errada"])
    for j, q in enumerate(Q):
        wrong = [x for x in resp[:, j] if x != key[q]]
        top = max(set(wrong), key=wrong.count) if wrong else ""
        wr.writerow([q, key[q], round(acerto[j], 3), *(round(v, 2) for v in (a2[j], a_lo[j], a_hi[j], b2[j], b_lo[j], b_hi[j])),
                     round(500+100*b2[j]), round(c[j], 2), round(b2[j], 2), flag(j), top])
with open(f"{OUT}/respondentes.csv", "w", newline="") as f:
    wr = csv.writer(f); wr.writerow(["ia","modelo","fracao_intuicao","acertos","theta_est"])
    for k, i in enumerate(ids): wr.writerow([i, agents[i][1], agents[i][2], int(X[k].sum()), round(theta[k], 2)])
np.save(f"{OUT}/matriz_acertos.npy", X)

print("situação dos itens:", {s: sum(flag(j) == s for j in range(J)) for s in set(flag(j) for j in range(J))})
print("corr(b, logit acerto):", np.corrcoef(b2, np.log(np.clip(acerto,.02,.98)/(1-np.clip(acerto,.02,.98))))[0,1].round(3))
print("theta por modelo:", {m: round(float(np.mean([theta[k] for k in range(N) if model_of[k] == m])), 2) for m in set(model_of)})
bad = [j for j in range(J) if flag(j) == "ok"]
print("itens 'ok':", len(bad))
for j in np.argsort(-b2)[:10]: print("difícil", Q[j], "acerto", acerto[j].round(2), "a", a2[j].round(2), "b", b2[j].round(2), flag(j))
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
fig, ax = plt.subplots(1, 3, figsize=(16, 4.8))
ax[0].hist(X.sum(1), bins=range(int(X.sum(1).min()), 92), color="#2e75b6"); ax[0].set_title("Acertos por IA (de 90)")
ax[1].hist(acerto, bins=20, color="#d1495b"); ax[1].set_title("% de acerto por questão")
ok = np.array([flag(j) == "ok" for j in range(J)])
ax[2].errorbar(acerto[ok], b2[ok], yerr=[np.clip(b2[ok]-b_lo[ok],0,None), np.clip(b_hi[ok]-b2[ok],0,None)], fmt="o", color="#2e75b6", ecolor="#aaa")
ax[2].scatter(acerto[~ok], b2[~ok], c="#d1495b", s=14); ax[2].set_xlabel("% acerto"); ax[2].set_ylabel("b"); ax[2].set_title("b estimado (IC90%) — vermelho: pouco informativo")
fig.tight_layout(); fig.savefig(f"{OUT}/resumo_ias.png", dpi=130)
