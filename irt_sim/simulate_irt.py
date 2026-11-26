"""Simulação de 10.000 alunos no Simulado 1 CDM (Q91-Q180) e recuperação cega de parâmetros TRI (a, b, c).

Etapas:
 1) gera parâmetros "verdadeiros" ocultos (julgamento de dificuldade por questão + ruído);
 2) sorteia theta ~ N(0,1) (escala ENEM: nota = 500 + 100*theta) para 10.000 alunos;
 3) simula respostas 0/1 pelo modelo 3PL;
 4) ESTIMA a, b, c só a partir da matriz de respostas (EM marginal, quadratura em grade);
 5) compara estimado x verdadeiro.
"""
import numpy as np, csv, json, sys
from scipy.optimize import minimize

rng = np.random.default_rng(2025)
import os
CA, CB = float(os.environ.get("CA", 6)), float(os.environ.get("CB", 24))
D = 1.7
N = 10_000
Q = list(range(91, 181))

# ---- julgamento de dificuldade (b "verdadeiro") por questão: -1 fácil, 0 média, 1 difícil, 2 muito difícil
tier = {q: 0.0 for q in Q}
easy = [93,99,103,104,105,112,115,117,119,120,122,126,128,130,134,135,150,151,157,163,164,166,168,169,171,173,178,179,
        101,102,124,125,134,140,145,146,152,153,154,155,156,161,165,170,172,174,175,176,177,180,139,143]
hard = [91,92,94,98,106,107,108,109,110,111,127,131,132,123,138,142,144,147,149,158,159,160,162,167,
        113,114,121,129,133,136,137,141,148]
vhard = [100,116,118,95,97,96,120,162,167,142,155,176,180]
for q in easy: tier[q] = -0.9
for q in hard: tier[q] = 0.6
for q in vhard: tier[q] = 1.3
# conflitos: o último grupo prevalece só se a questão não estiver em 'easy'
for q in vhard:
    if q in easy: tier[q] = 0.3
is_mat = np.array([q >= 136 for q in Q])
b_true = np.array([tier[q] for q in Q]) + rng.normal(0, 0.35, len(Q)) + np.where(is_mat, 0.35, 0.0)
a_true = np.clip(rng.lognormal(np.log(1.1), 0.35, len(Q)), 0.4, 2.6) * np.where(is_mat, 1.15, 1.0)
c_true = np.clip(rng.beta(6, 24, len(Q)), 0.05, 0.35)  # em torno de 0.20

theta = rng.normal(0, 1, N)

def p3(th, a, b, c):
    return c + (1 - c) / (1 + np.exp(-D * a * (th[:, None] - b)))

P = p3(theta, a_true, b_true, c_true)
X = (rng.random(P.shape) < P).astype(np.int8)
print("acerto médio por aluno:", X.mean().round(3))

# ======================= ESTIMAÇÃO CEGA (usa só X) =======================
K = 41
grid = np.linspace(-4, 4, K)
w = np.exp(-grid**2 / 2); w /= w.sum()          # prior N(0,1) fixa -> fixa a escala
J = X.shape[1]

def icc(a, b, c):          # K x J
    return c + (1 - c) / (1 + np.exp(-D * a * (grid[:, None] - b)))

def fit(model, iters=60):
    a = np.ones(J); b = -np.log((X.mean(0)+1e-3)/(1-X.mean(0)+1e-3)) ; c = np.full(J, 0.0 if model=="2PL" else 0.2)
    # b inicial por logit do p-valor; a inicial = 1
    prev = -np.inf
    for it in range(iters):
        Pk = icc(a, b, c)
        logL = X @ np.log(Pk).T + (1 - X) @ np.log(1 - Pk).T      # N x K
        logL += np.log(w)
        m = logL.max(1, keepdims=True)
        post = np.exp(logL - m); s = post.sum(1, keepdims=True); post /= s
        ll = (m[:, 0] + np.log(s[:, 0])).sum()
        n_k = post.sum(0)                  # K
        r_kj = post.T @ X                  # K x J  (acertos esperados)
        # M-step por item
        for j in range(J):
            def nll(p):
                aa, bb = p[0], p[1]
                cc = p[2] if model == "3PL" else 0.0
                P_ = np.clip(cc + (1-cc)/(1+np.exp(-D*aa*(grid-bb))), 1e-9, 1-1e-9)
                v = -(r_kj[:, j]*np.log(P_) + (n_k-r_kj[:, j])*np.log(1-P_)).sum()
                v += 0.5*((np.log(aa)-np.log(1.1))/0.6)**2*1.0         # prior fraca em a (lognormal)
                if model == "3PL":
                    v -= (CA-1)*np.log(cc) + (CB-1)*np.log(1-cc)       # prior Beta(6,24) em c (como no BILOG/ENEM)
                return v
            x0 = [a[j], b[j]] + ([max(c[j], 0.05)] if model == "3PL" else [])
            bnds = [(0.2, 4), (-4, 4)] + ([(0.01, 0.45)] if model == "3PL" else [])
            res = minimize(nll, x0, bounds=bnds, method="L-BFGS-B")
            a[j], b[j] = res.x[0], res.x[1]
            if model == "3PL": c[j] = res.x[2]
        if abs(ll - prev) < 0.5: break
        prev = ll
    print(model, "iterações:", it+1, "loglik:", round(ll, 1))
    return a, b, c, post

def corr(x, y): return float(np.corrcoef(x, y)[0, 1])
def rmse(x, y): return float(np.sqrt(np.mean((x-y)**2)))

out = {}
for model in ["3PL", "2PL"]:
    a_e, b_e, c_e, post = fit(model)
    th_e = post @ grid
    out[model] = dict(a=a_e, b=b_e, c=c_e, th=th_e)
    print(f"[{model}] a: r={corr(a_true,a_e):.3f} RMSE={rmse(a_true,a_e):.3f} | b: r={corr(b_true,b_e):.3f} RMSE={rmse(b_true,b_e):.3f}"
          f" | c: r={corr(c_true,c_e):.3f} RMSE={rmse(c_true,c_e):.3f} | theta: r={corr(theta,th_e):.3f}")

# resultados em escala ENEM (500 + 100 * b)
with open("/home/user/dataviz/irt_sim/itens_verdadeiro_vs_estimado.csv", "w", newline="") as f:
    wr = csv.writer(f)
    wr.writerow(["questao","a_verd","b_verd","c_verd","b_verd_enem","a_3PL","b_3PL","c_3PL","b_3PL_enem","a_2PL","b_2PL","pct_acerto"])
    for j, q in enumerate(Q):
        wr.writerow([q, *(round(v, 3) for v in (a_true[j], b_true[j], c_true[j], 500+100*b_true[j],
                     out["3PL"]["a"][j], out["3PL"]["b"][j], out["3PL"]["c"][j], 500+100*out["3PL"]["b"][j],
                     out["2PL"]["a"][j], out["2PL"]["b"][j], X[:, j].mean()))])
np.save("/home/user/dataviz/irt_sim/respostas_10000x90.npy", X)
np.save("/home/user/dataviz/irt_sim/theta_verdadeiro.npy", theta)

# ---- gráficos
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
fig, ax = plt.subplots(1, 3, figsize=(15, 4.8))
for k, (name, t, e, lim) in enumerate([("a (discriminação)", a_true, out["3PL"]["a"], (0, 3.2)),
                                        ("b (dificuldade)", b_true, out["3PL"]["b"], (-3, 3.5)),
                                        ("c (acerto ao acaso)", c_true, out["3PL"]["c"], (0, 0.45))]):
    ax[k].scatter(t, e, s=22, c=["#d1495b" if m else "#2e75b6" for m in is_mat], alpha=.85)
    ax[k].plot(lim, lim, "k--", lw=1)
    ax[k].set_title(f"{name}\nr = {corr(t,e):.2f}"); ax[k].set_xlabel("verdadeiro"); ax[k].set_ylabel("estimado (3PL)")
    ax[k].set_xlim(lim); ax[k].set_ylim(lim)
fig.suptitle("Recuperação de parâmetros — azul: Ciências da Natureza, vermelho: Matemática")
fig.tight_layout(); fig.savefig("/home/user/dataviz/irt_sim/recuperacao_parametros.png", dpi=130)
