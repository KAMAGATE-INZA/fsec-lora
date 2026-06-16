"""
analyze.py
==========
Analyse statistique et graphique de la campagne FSEC-LoRa (results.csv).

Produit, dans simulation/figures/ :
  - fig_cache_sweep.(png|pdf)   : CHR, FHR, EUB, DCVR en fonction de la taille du
                                  cache, avec intervalles de confiance a 95 %.
  - fig_bars_cache100.(png|pdf) : comparaison des 6 strategies a cache=100.
  - fig_sf_effect.(png|pdf)     : effet du Spreading Factor (DCVR, EUB).
  - fig_battery_effect.(png|pdf): effet de la batterie (duree de vie, EUB).
  - fig_grid_sensitivity.(png|pdf) : sensibilite aux exposants FSEC.

Et imprime :
  - le tableau de synthese a cache=100 ;
  - les meilleurs exposants (grid search) ;
  - les tests ANOVA (FSEC vs references) et la correlation de Pearson.

Les p-values sont calculees sans SciPy, via la fonction beta incomplete
regularisee (continued fraction, Numerical Recipes), ce qui rend le script
autonome.
"""

from __future__ import annotations
import math
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(__file__)
FIGDIR = os.path.join(HERE, "figures")
os.makedirs(FIGDIR, exist_ok=True)

STRAT_ORDER = ["No-cache", "LRU", "LFU", "Prob", "AdaptiveTTL", "pCASTING", "CFPC", "FSEC"]
COLORS = {"No-cache": "#888888", "LRU": "#1f77b4", "LFU": "#2ca02c",
          "Prob": "#9467bd", "AdaptiveTTL": "#ff7f0e",
          "pCASTING": "#17becf", "CFPC": "#8c564b", "FSEC": "#d62728"}


# ---------------------------------------------------------------------------
# Statistiques sans SciPy
# ---------------------------------------------------------------------------
def _betacf(a, b, x, itmax=200, eps=3e-12):
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < 1e-30:
        d = 1e-30
    d = 1.0 / d
    h = d
    for m in range(1, itmax + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def betai(a, b, x):
    """Fonction beta incomplete regularisee I_x(a,b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    bt = math.exp(lbeta + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def anova_oneway(groups):
    """ANOVA a un facteur. Renvoie (F, p, df1, df2)."""
    k = len(groups)
    n = sum(len(g) for g in groups)
    grand = np.concatenate(groups).mean()
    ssb = sum(len(g) * (np.mean(g) - grand) ** 2 for g in groups)
    ssw = sum(((np.array(g) - np.mean(g)) ** 2).sum() for g in groups)
    df1, df2 = k - 1, n - k
    if ssw == 0:
        return float("inf"), 0.0, df1, df2
    F = (ssb / df1) / (ssw / df2)
    p = betai(df2 / 2.0, df1 / 2.0, df2 / (df2 + df1 * F))
    return F, p, df1, df2


def pearson(x, y):
    """Correlation de Pearson r et p-value bilaterale."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    r = np.corrcoef(x, y)[0, 1]
    n = len(x)
    if abs(r) >= 1.0 or n <= 2:
        return r, 0.0
    df = n - 2
    t2 = r * r * df / (1 - r * r)
    p = betai(df / 2.0, 0.5, df / (df + t2))
    return r, p


def agg(df, group_cols, metric):
    """Moyenne, demi-largeur d'IC 95 % (t approx 1.96) par groupe."""
    g = df.groupby(group_cols)[metric]
    mean = g.mean()
    sem = g.std(ddof=1) / np.sqrt(g.count())
    ci = 1.96 * sem
    return mean, ci


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------
def fig_cache_sweep(df):
    d = df[df.experiment == "cache"]
    metrics = [("CHR", "Cache Hit Ratio (%)"), ("FHR", "Freshness Hit Ratio (%)"),
               ("EUB", "Energy per Useful Bit (mJ/bit)"), ("DCVR", "Duty Cycle Violation Rate (%)")]
    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    for ax, (m, label) in zip(axes.flat, metrics):
        for strat in STRAT_ORDER:
            sub = d[d.strategy == strat]
            if strat == "No-cache":
                # ligne horizontale (independante de la taille du cache)
                val = sub[m].mean()
                ax.axhline(val, color=COLORS[strat], ls=":", lw=1.5, label=strat)
                continue
            mean, ci = agg(sub, "cache_size", m)
            ax.errorbar(mean.index, mean.values, yerr=ci.values, marker="o",
                        capsize=3, color=COLORS[strat], label=strat)
        ax.set_xlabel("Taille du cache (entrées)")
        ax.set_ylabel(label)
        ax.grid(True, alpha=0.3)
    axes.flat[0].legend(fontsize=8, ncol=2)
    fig.suptitle("Performances en fonction de la taille du cache (IC 95 %)", fontweight="bold")
    fig.tight_layout()
    fig.savefig(os.path.join(FIGDIR, "fig_cache_sweep.png"), dpi=150)
    fig.savefig(os.path.join(FIGDIR, "fig_cache_sweep.pdf"))
    plt.close(fig)


def fig_bars_cache100(df):
    d = df[(df.experiment == "cache") & ((df.cache_size == 100) | (df.strategy == "No-cache"))]
    metrics = [("CHR", "CHR (%)"), ("FHR", "FHR (%)"),
               ("EUB", "EUB (mJ/bit)"), ("DCVR", "DCVR (%)")]
    fig, axes = plt.subplots(1, 4, figsize=(15, 4))
    for ax, (m, label) in zip(axes, metrics):
        means = [d[d.strategy == s][m].mean() for s in STRAT_ORDER]
        cis = []
        for s in STRAT_ORDER:
            v = d[d.strategy == s][m]
            cis.append(1.96 * v.std(ddof=1) / np.sqrt(len(v)) if len(v) > 1 else 0)
        xs = range(len(STRAT_ORDER))
        ax.bar(xs, means, yerr=cis, capsize=3,
               color=[COLORS[s] for s in STRAT_ORDER])
        ax.set_ylabel(label)
        ax.set_xticks(list(xs))
        ax.set_xticklabels(STRAT_ORDER, rotation=45, ha="right", fontsize=8)
        ax.grid(True, axis="y", alpha=0.3)
    fig.suptitle("Comparaison des stratégies (cache = 100, SF7, batterie pleine)", fontweight="bold")
    fig.tight_layout()
    fig.savefig(os.path.join(FIGDIR, "fig_bars_cache100.png"), dpi=150)
    fig.savefig(os.path.join(FIGDIR, "fig_bars_cache100.pdf"))
    plt.close(fig)


def fig_sf_effect(df):
    d = df[df.experiment == "sf"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, (m, label) in zip(axes, [("DCVR", "DCVR (%)"), ("EUB", "EUB (mJ/bit)")]):
        for strat in STRAT_ORDER:
            sub = d[d.strategy == strat]
            mean, ci = agg(sub, "sf", m)
            ax.errorbar(mean.index, mean.values, yerr=ci.values, marker="s",
                        capsize=3, color=COLORS[strat], label=strat)
        ax.set_xlabel("Spreading Factor")
        ax.set_ylabel(label)
        ax.set_xticks([7, 9, 12])
        ax.grid(True, alpha=0.3)
    axes[0].legend(fontsize=8, ncol=2)
    fig.suptitle("Effet du Spreading Factor (cache = 100, IC 95 %)", fontweight="bold")
    fig.tight_layout()
    fig.savefig(os.path.join(FIGDIR, "fig_sf_effect.png"), dpi=150)
    fig.savefig(os.path.join(FIGDIR, "fig_sf_effect.pdf"))
    plt.close(fig)


def fig_battery_effect(df):
    d = df[df.experiment == "battery"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, (m, label) in zip(axes, [("lifetime", "Durée de vie réseau (s)"),
                                      ("EUB", "EUB (mJ/bit)")]):
        for strat in STRAT_ORDER:
            sub = d[d.strategy == strat]
            mean, ci = agg(sub, "battery_frac", m)
            ax.errorbar(mean.index * 100, mean.values, yerr=ci.values, marker="^",
                        capsize=3, color=COLORS[strat], label=strat)
        ax.set_xlabel("Batterie initiale (%)")
        ax.set_ylabel(label)
        ax.grid(True, alpha=0.3)
    axes[0].legend(fontsize=8, ncol=2)
    fig.suptitle("Effet du niveau de batterie initial (cache = 100, IC 95 %)", fontweight="bold")
    fig.tight_layout()
    fig.savefig(os.path.join(FIGDIR, "fig_battery_effect.png"), dpi=150)
    fig.savefig(os.path.join(FIGDIR, "fig_battery_effect.pdf"))
    plt.close(fig)


def fig_grid_sensitivity(df):
    d = df[df.experiment == "grid"].copy()
    # objectif : maximiser CHR*FHR sous DCVR=0, EUB en departage
    d["score"] = d.CHR * d.FHR / 100.0
    params = [("alpha", "Exposant α (fraîcheur)"),
              ("beta", "Exposant β (corrélation)"),
              ("kappa", "Poids κ (coût d'un miss)")]
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.5))
    for ax, (expo, label) in zip(axes, params):
        mean, ci = agg(d, expo, "score")
        ax.errorbar(mean.index, mean.values, yerr=ci.values, marker="o", capsize=3,
                    color="#d62728")
        ax.set_xlabel(label)
        ax.set_ylabel("Score CHR·FHR/100")
        ax.grid(True, alpha=0.3)
    fig.suptitle("Sensibilité aux paramètres FSEC (grid search)", fontweight="bold")
    fig.tight_layout()
    fig.savefig(os.path.join(FIGDIR, "fig_grid_sensitivity.png"), dpi=150)
    fig.savefig(os.path.join(FIGDIR, "fig_grid_sensitivity.pdf"))
    plt.close(fig)


# ---------------------------------------------------------------------------
# Synthese imprimee
# ---------------------------------------------------------------------------
def print_summary(df):
    print("\n================ SYNTHESE (cache = 100, SF7, batterie pleine) ================")
    d = df[(df.experiment == "cache") & ((df.cache_size == 100) | (df.strategy == "No-cache"))]
    hdr = f"{'strategie':12} {'CHR':>7} {'FHR':>7} {'EUB':>9} {'DCVR':>7} {'vie(s)':>8} {'lat(ms)':>8}"
    print(hdr)
    for s in STRAT_ORDER:
        sub = d[d.strategy == s]
        # FHR sans objet pour No-cache (aucun hit) -> N/A
        fhr = "    N/A" if s == "No-cache" else f"{sub.FHR.mean():7.1f}"
        print(f"{s:12} {sub.CHR.mean():7.1f} {fhr} {sub.EUB.mean():9.4f} "
              f"{sub.DCVR.mean():7.1f} {sub.lifetime.mean():8.0f} {sub.latency_ms.mean():8.0f}")

    # --- grid search : meilleurs parametres (alpha, beta, kappa) ---
    g = df[df.experiment == "grid"].copy()
    gg = g.groupby(["alpha", "beta", "kappa"]).agg(
        CHR=("CHR", "mean"), FHR=("FHR", "mean"),
        EUB=("EUB", "mean"), DCVR=("DCVR", "mean")).reset_index()
    feasible = gg[gg.DCVR == 0]
    feasible = feasible if len(feasible) else gg
    feasible = feasible.assign(score=feasible.CHR * feasible.FHR / 100.0)
    best = feasible.sort_values(["score", "EUB"], ascending=[False, True]).iloc[0]
    print("\n================ GRID SEARCH : meilleurs parametres ================")
    print(f"alpha={best.alpha}, beta={best.beta}, kappa={best.kappa}  "
          f"-> CHR={best.CHR:.1f}%, FHR={best.FHR:.1f}%, EUB={best.EUB:.4f}, DCVR={best.DCVR:.1f}%")

    # --- ANOVA : FSEC vs references sur le CHR (cache=100) ---
    print("\n================ ANOVA (cache=100) : FSEC vs references ================")
    for metric in ["CHR", "FHR", "EUB", "DCVR"]:
        groups = [d[d.strategy == s][metric].values
                  for s in ["LRU", "LFU", "Prob", "AdaptiveTTL", "pCASTING", "CFPC", "FSEC"]]
        F, p, df1, df2 = anova_oneway(groups)
        sig = "significatif" if p < 0.05 else "non significatif"
        print(f"  {metric:5} : F({df1},{df2})={F:8.2f}  p={p:.3e}  ({sig})")

    # --- Pearson : lien taille de cache / performances ---
    print("\n================ Correlation de Pearson (taille de cache) ================")
    lru = df[(df.experiment == "cache") & (df.strategy == "LRU")]
    r, p = pearson(lru.cache_size.values, lru.CHR.values)
    print(f"  LRU  : cache vs CHR  r={r:+.3f}, p={p:.3e}  "
          f"(les politiques classiques ont besoin de memoire)")
    r, p = pearson(lru.cache_size.values, lru.EUB.values)
    print(f"  LRU  : cache vs EUB  r={r:+.3f}, p={p:.3e}")
    fs = df[(df.experiment == "cache") & (df.strategy == "FSEC")]
    chr50 = fs[fs.cache_size == 50].CHR.mean()
    chr500 = fs[fs.cache_size == 500].CHR.mean()
    print(f"  FSEC : CHR sature tot ({chr50:.1f}% a cache=50 vs {chr500:.1f}% a cache=500) :")
    print(f"         grace aux hits semantiques, peu de memoire suffit.")


def main():
    df = pd.read_csv(os.path.join(HERE, "results.csv"))
    print(f"Resultats charges : {len(df)} runs.")
    fig_cache_sweep(df)
    fig_bars_cache100(df)
    fig_sf_effect(df)
    fig_battery_effect(df)
    fig_grid_sensitivity(df)
    print(f"Figures ecrites dans {FIGDIR}/")
    print_summary(df)


if __name__ == "__main__":
    main()
