"""
plot_experiments.py
===================
Trace une figure par expérience de révision (A à F) à partir des CSV de rev/,
plus une figure sur données réelles. Sorties : rev/figures/fig_exp*.png et .pdf.

Usage : python3 plot_experiments.py
"""
from __future__ import annotations
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(__file__)
REV = os.path.join(HERE, "rev")
OUT = os.path.join(REV, "figures")
os.makedirs(OUT, exist_ok=True)

COL = {"FSEC": "#d62728", "LRU": "#1f77b4", "pCASTING": "#17becf", "LFU": "#2ca02c",
       "Prob": "#9467bd", "AdaptiveTTL": "#ff7f0e", "CFPC": "#8c564b",
       "FreshEnergy": "#e377c2", "No-cache": "#888888"}
plt.rcParams.update({"font.size": 11, "axes.grid": True, "grid.alpha": 0.3,
                     "figure.dpi": 120})


def ci95(s):
    s = np.asarray(s, float)
    return 1.96 * s.std(ddof=1) / np.sqrt(len(s)) if len(s) > 1 else 0.0


def save(fig, name):
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, name + ".png"), dpi=150)
    fig.savefig(os.path.join(OUT, name + ".pdf"))
    plt.close(fig)
    print("écrit:", name + ".png/.pdf")


# ---------------------------------------------------------------- Exp A
def fig_A():
    d = pd.read_csv(os.path.join(REV, "expA_fair_dc.csv"))
    order = ["No-cache", "LRU", "LFU", "Prob", "AdaptiveTTL", "pCASTING", "CFPC", "FreshEnergy", "FSEC"]
    en = d[d.scenario == "enforce"]
    g = en.groupby("strategy")
    ex = [g.get_group(s).CHR_exact.mean() if s in g.groups else 0 for s in order]
    se = [g.get_group(s).CHR_sem.mean() if s in g.groups else 0 for s in order]
    bh = [g.get_group(s).n_backhaul.mean() if s in g.groups else 0 for s in order]
    x = np.arange(len(order))
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.4))
    ax[0].bar(x, ex, label="succès exact", color="#4c72b0")
    ax[0].bar(x, se, bottom=ex, label="succès sémantique", color="#dd8452")
    ax[0].set_ylabel("Cache Hit Ratio (%)"); ax[0].set_title("(a) Taux de succès à duty-cycle égal (DCVR = 0 pour toutes)")
    ax[0].set_xticks(x); ax[0].set_xticklabels(order, rotation=40, ha="right"); ax[0].legend()
    ax[1].bar(x, bh, color=[COL.get(s, "#999") for s in order])
    ax[1].set_ylabel("Réponses déléguées au backhaul"); ax[1].set_title("(b) Réponses différées (moins = mieux)")
    ax[1].set_xticks(x); ax[1].set_xticklabels(order, rotation=40, ha="right")
    save(fig, "fig_expA_duty_cycle_egal")


# ---------------------------------------------------------------- Exp B
def fig_B():
    d = pd.read_csv(os.path.join(REV, "expB_semantic_error.csv"))
    d["lab"] = d.eps_max.astype(str)
    order = ["inf", "2.0", "1.0", "0.5", "0.25"]
    d = d.set_index("lab").reindex([o for o in order if o in set(d.lab)]).reset_index()
    # distribution brute agrégée sur 30 graines (cohérent avec le texte : p95 ~5 °C)
    try:
        from fsec_sim import Config, Simulator
        err = []
        for sd in range(30):
            sim = Simulator(Config(strategy="FSEC", seed=sd)); sim.run()
            err.extend(sim.sem_errors)
        err = np.array(err)
    except Exception:
        err = None
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.4))
    if err is not None and len(err):
        ax[0].hist(err, bins=np.linspace(0, 15, 76), color="#d62728", alpha=0.8)
        ax[0].axvline(np.median(err), color="k", ls="--", lw=1.2, label=f"médiane {np.median(err):.2f} °C")
        ax[0].axvline(np.percentile(err, 95), color="gray", ls=":", lw=1.8, label=f"p95 {np.percentile(err,95):.2f} °C")
        ax[0].set_xlim(0, 15)
        ax[0].set_xlabel("Erreur d'approximation sémantique |v_A − v_B| (°C)")
        ax[0].set_ylabel(f"Occurrences (n = {len(err):,})"); ax[0].legend()
    ax[0].set_title("(a) Distribution de l'erreur sémantique (FSEC)")
    xp = np.arange(len(d))
    ax[1].bar(xp - 0.2, d.CHR_exact, 0.4, label="exact", color="#4c72b0")
    ax[1].bar(xp - 0.2, d.CHR_sem, 0.4, bottom=d.CHR_exact, label="sémantique", color="#dd8452")
    ax[1].plot(xp, d.CHR, "k-o", lw=1.5, label="CHR total")
    ax[1].set_xticks(xp); ax[1].set_xticklabels(["∞" if l == "inf" else l for l in d.lab])
    ax[1].set_xlabel("Tolérance ε_max (°C)"); ax[1].set_ylabel("CHR utile (%)")
    ax[1].set_title("(b) Taux de succès selon la tolérance"); ax[1].legend()
    save(fig, "fig_expB_erreur_semantique")


# ---------------------------------------------------------------- Exp C
def fig_C():
    d = pd.read_csv(os.path.join(REV, "expC_correlation.csv"))
    sd = d[d.sweep == "sigma_d"]
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.4))
    for st in ["FSEC", "LRU"]:
        s = sd[sd.strategy == st].groupby("sigma_d")
        xs = sorted(s.groups); m = [s.get_group(x).CHR.mean() for x in xs]
        e = [ci95(s.get_group(x).CHR) for x in xs]
        ax[0].errorbar(xs, m, yerr=e, marker="o", capsize=3, color=COL[st], label=st)
    fs = sd[sd.strategy == "FSEC"].groupby("sigma_d")
    xs = sorted(fs.groups)
    ax[0].plot(xs, [fs.get_group(x).CHR_sem.mean() for x in xs], "--", color="#d62728", alpha=0.6, label="FSEC part sémantique")
    ax[0].set_xlabel("σ_d : largeur du noyau spatial (m)"); ax[0].set_ylabel("CHR (%)")
    ax[0].set_title("(a) L'avantage croît avec la corrélation"); ax[0].legend()
    lay = d[d.sweep == "layout"]
    labs = ["clustered", "uniform"]; xl = np.arange(len(labs)); w = 0.35
    for i, st in enumerate(["FSEC", "LRU"]):
        m = [lay[(lay.strategy == st) & (lay.layout == l)].CHR.mean() for l in labs]
        ax[1].bar(xl + (i - 0.5) * w, m, w, color=COL[st], label=st)
    ax[1].axhline(lay[lay.strategy == "LRU"].CHR.mean(), color="#1f77b4", ls=":", alpha=0.5)
    ax[1].set_xticks(xl); ax[1].set_xticklabels(["en grappes", "uniforme (épars)"])
    ax[1].set_ylabel("CHR (%)"); ax[1].set_title("(b) Déploiement : dense vs épars"); ax[1].legend()
    save(fig, "fig_expC_correlation")


# ---------------------------------------------------------------- Exp D
def fig_D():
    d = pd.read_csv(os.path.join(REV, "expD_params_split.csv"))
    main = d[d.config.isin(["selectionnee", "defaut"])]
    jeux = ["reglage", "validation", "test"]
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.4))
    xj = np.arange(len(jeux)); w = 0.35
    for i, cfg in enumerate(["defaut", "selectionnee"]):
        vals = [main[(main.config == cfg) & (main.jeu == j)].CHR.mean() for j in jeux]
        lbl = "config par défaut (1,5;0,5;3)" if cfg == "defaut" else "config choisie au réglage"
        ax[0].bar(xj + (i - 0.5) * w, vals, w, label=lbl)
    ax[0].set_xticks(xj); ax[0].set_xticklabels(["réglage", "validation", "test"])
    ax[0].set_ylim(70, 85); ax[0].set_ylabel("CHR (%)")
    ax[0].set_title("(a) Généralisation sans fuite (test = jeu non vu)"); ax[0].legend()
    uth = d[d.config == "uth_sweep"].copy()
    uth["u"] = uth.jeu.str.replace("test_uth=", "").astype(float)
    uth = uth.sort_values("u")
    ax[1].plot(uth.u, uth.CHR, "-o", color="#2ca02c")
    ax[1].set_xlabel("Seuil d'admission U_th"); ax[1].set_ylabel("CHR (%)")
    ax[1].set_title("(b) Sensibilité au seuil U_th (jeu de test)")
    save(fig, "fig_expD_parametres")


# ---------------------------------------------------------------- Exp E
def fig_E():
    d = pd.read_csv(os.path.join(REV, "expE_query_patterns.csv"))
    combos = [(a, s) for a in ["poisson", "periodic", "bursty"] for s in ["uniforme", "zipf"]]
    labels = [f"{a}\n{s}" for a, s in combos]
    x = np.arange(len(combos)); w = 0.26
    fig, ax = plt.subplots(figsize=(11, 4.6))
    for i, st in enumerate(["FSEC", "LRU", "pCASTING"]):
        m = [d[(d.arrival == a) & (d.selection == s) & (d.strategy == st)].CHR.mean() for a, s in combos]
        e = [ci95(d[(d.arrival == a) & (d.selection == s) & (d.strategy == st)].CHR) for a, s in combos]
        ax.bar(x + (i - 1) * w, m, w, yerr=e, capsize=2, color=COL[st], label=st)
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel("CHR (%)")
    ax.set_title("Exp E — robustesse aux motifs de trafic (FSEC insensible ; popularité s'effondre en uniforme)")
    ax.legend()
    save(fig, "fig_expE_trafic")


# ---------------------------------------------------------------- Exp F
def fig_F():
    d = pd.read_csv(os.path.join(REV, "expF_radio_reliability.csv"))
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.4))
    for st in ["FSEC", "LRU", "pCASTING"]:
        s = d[d.strategy == st].groupby("per_base")
        xs = sorted(s.groups)
        ax[0].errorbar([x * 100 for x in xs], [s.get_group(x).CHR.mean() for x in xs],
                       yerr=[ci95(s.get_group(x).CHR) for x in xs], marker="o", capsize=3, color=COL[st], label=st)
        ax[1].errorbar([x * 100 for x in xs], [s.get_group(x).EUB.mean() for x in xs],
                       yerr=[ci95(s.get_group(x).EUB) for x in xs], marker="s", capsize=3, color=COL[st], label=st)
    ax[0].set_xlabel("Taux de perte de paquets (%)"); ax[0].set_ylabel("CHR (%)")
    ax[0].set_title("(a) FSEC tient sous pertes, les autres s'effondrent"); ax[0].legend()
    ax[1].set_xlabel("Taux de perte de paquets (%)"); ax[1].set_ylabel("EUB (mJ/bit)")
    ax[1].set_title("(b) Coût énergétique par bit utile"); ax[1].legend()
    save(fig, "fig_expF_fiabilite_radio")


if __name__ == "__main__":
    for f in (fig_A, fig_B, fig_C, fig_D, fig_E, fig_F):
        try:
            f()
        except Exception as e:
            print("ERREUR", f.__name__, ":", e)
    print("Figures dans", OUT)
