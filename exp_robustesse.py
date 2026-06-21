"""
exp_robustesse.py
=================
Analyses de robustesse de FSEC-LoRa : on fait varier les hypothèses qui
pourraient « avantager » la stratégie et on vérifie que son avanatage tient.

Trois balayages (cache=100, SF7, batterie pleine) :
  (1) largeur du noyau spatial sigma_d   -> force de la corrélation spatiale ;
  (2) seuil de hit sémantique            -> sévérité de la réutilisation ;
  (3) skew de popularité zipf_s          -> loi de trafic (0 = uniforme).

Produit : figures/fig_robustesse.(png|pdf) + un résumé imprimé.
Usage : python3 exp_robustesse.py
"""
from __future__ import annotations
import os
from concurrent.futures import ProcessPoolExecutor
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from fsec_sim import Config, run_one

HERE = os.path.dirname(__file__)
FIGDIR = os.path.join(HERE, "figures")
SEEDS = list(range(15))
COLORS = {"FSEC": "#d62728", "LRU": "#1f77b4", "pCASTING": "#17becf"}


def _job(args):
    strat, kw, seed = args
    # scenario allege (comme la grille) : etude de sensibilite, pas resultat principal
    return strat, kw_key(kw), run_one(Config(strategy=strat, seed=seed,
                                              cache_size=100, sf=7,
                                              n_sensors=120, sim_time=1800.0, **kw))["CHR"]


def kw_key(kw):
    return tuple(sorted(kw.items()))


def sweep(strats, param, values):
    """Renvoie {strat: ([valeurs], [moyennes CHR], [demi-IC95])}."""
    jobs = [(s, {param: v}, seed) for s in strats for v in values for seed in SEEDS]
    with ProcessPoolExecutor() as ex:
        res = list(ex.map(_job, jobs))
    out = {}
    for s in strats:
        means, cis = [], []
        for v in values:
            chrs = [c for (st, k, c) in res if st == s and k == kw_key({param: v})]
            m = np.mean(chrs); ci = 1.96 * np.std(chrs, ddof=1) / np.sqrt(len(chrs))
            means.append(m); cis.append(ci)
        out[s] = (values, means, cis)
    return out


def main():
    sig = sweep(["FSEC", "LRU", "pCASTING"], "sigma_d", [40, 80, 120])
    sem = sweep(["FSEC"], "sem_threshold", [0.3, 0.5, 0.7])
    zipf = sweep(["FSEC", "LRU", "pCASTING"], "zipf_s", [0.0, 0.4, 0.8, 1.2])

    def show(title, d):
        print(f"\n=== {title} ===")
        for s, (xs, ms, _) in d.items():
            print(f"  {s:9} " + "  ".join(f"{x}:{m:.1f}" for x, m in zip(xs, ms)))
    show("sigma_d (corrélation spatiale) -> CHR", sig)
    show("seuil sémantique -> CHR (FSEC)", sem)
    show("zipf_s (popularité) -> CHR", zipf)

    fig, axes = plt.subplots(1, 3, figsize=(14, 3.6))
    for s, (xs, ms, cis) in sig.items():
        axes[0].errorbar(xs, ms, yerr=cis, marker="o", capsize=3, color=COLORS[s], label=s)
    axes[0].set_xlabel("σ_d : largeur du noyau spatial (m)"); axes[0].legend(fontsize=8)
    for s, (xs, ms, cis) in sem.items():
        axes[1].errorbar(xs, ms, yerr=cis, marker="s", capsize=3, color=COLORS[s], label=s)
    axes[1].set_xlabel("Seuil de hit sémantique"); axes[1].legend(fontsize=8)
    for s, (xs, ms, cis) in zipf.items():
        axes[2].errorbar(xs, ms, yerr=cis, marker="^", capsize=3, color=COLORS[s], label=s)
    axes[2].set_xlabel("s : skew de popularité (0 = uniforme)"); axes[2].legend(fontsize=8)
    for ax in axes:
        ax.set_ylabel("CHR (%)"); ax.grid(True, alpha=0.3)
    fig.suptitle("Robustesse de FSEC-LoRa aux hypothèses de modélisation (cache=100, SF7, IC 95 %)",
                 fontweight="bold")
    fig.tight_layout()
    fig.savefig(os.path.join(FIGDIR, "fig_robustesse.png"), dpi=150)
    fig.savefig(os.path.join(FIGDIR, "fig_robustesse.pdf"))
    print(f"\nFigure écrite : {FIGDIR}/fig_robustesse.(png|pdf)")


if __name__ == "__main__":
    main()
