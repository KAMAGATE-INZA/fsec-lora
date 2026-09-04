"""
exp_B_semantic_error.py
=======================
Exp B (revision PEMWN) - Erreur d'approximation semantique (R6, R20, R21).

Quand une requete pour le capteur A est servie par la valeur cachee d'un voisin
B, ce n'est pas un hit exact : il faut mesurer l'erreur e = |v_A - v_B| et ne
pas la compter comme service utile si elle depasse une tolerance eps_max.

Deux sorties :
 1. Distribution de l'erreur semantique (MAE, RMSE, p50/p90/p95/p99, max),
    agregee sur toutes les graines, en regime non filtre (eps_max = inf).
 2. Balayage de eps_max : CHR total / exact / semantique et taux de rejet
    semantique en fonction de la tolerance, pour montrer que le gain n'est pas
    obtenu au prix de la fidelite.

Usage : python3 exp_B_semantic_error.py [n_seeds]     # defaut 30
"""
from __future__ import annotations
import csv
import math
import os
import sys
from concurrent.futures import ProcessPoolExecutor

from fsec_sim import Config, Simulator

HERE = os.path.dirname(__file__)
OUTDIR = os.path.join(HERE, "rev")
OUTCSV = os.path.join(OUTDIR, "expB_semantic_error.csv")
BASE = dict(strategy="FSEC", cache_size=100, sf=7, battery_init_frac=1.0)
EPS_GRID = [float("inf"), 2.0, 1.0, 0.5, 0.25]


def _errors_job(seed):
    """Retourne la liste brute des erreurs semantiques d'un run (eps_max=inf)."""
    s = Simulator(Config(seed=seed, eps_max=float("inf"), **BASE))
    s.run()
    return s.sem_errors


def _eps_job(args):
    eps, seed = args
    m = Simulator(Config(seed=seed, eps_max=eps, **BASE)).run()
    return eps, seed, m


def _pct(sorted_xs, q):
    if not sorted_xs:
        return 0.0
    k = min(len(sorted_xs) - 1, max(0, int(math.ceil(q * len(sorted_xs))) - 1))
    return sorted_xs[k]


def main(n_seeds: int):
    os.makedirs(OUTDIR, exist_ok=True)
    seeds = list(range(n_seeds))

    # --- 1. distribution de l'erreur (eps_max = inf) ---
    with ProcessPoolExecutor() as ex:
        per_run = list(ex.map(_errors_job, seeds))
    all_err = [e for run in per_run for e in run]
    all_err_sorted = sorted(all_err)
    n = len(all_err)
    mae = sum(all_err) / n if n else 0.0
    rmse = math.sqrt(sum(e * e for e in all_err) / n) if n else 0.0

    print("===== Exp B.1 : distribution de l'erreur semantique |vA - vB| (degres C) =====")
    print(f"  hits semantiques mesures : {n}")
    print(f"  MAE  = {mae:.3f}")
    print(f"  RMSE = {rmse:.3f}")
    print(f"  p50  = {_pct(all_err_sorted, 0.50):.3f}")
    print(f"  p90  = {_pct(all_err_sorted, 0.90):.3f}")
    print(f"  p95  = {_pct(all_err_sorted, 0.95):.3f}")
    print(f"  p99  = {_pct(all_err_sorted, 0.99):.3f}")
    print(f"  max  = {all_err_sorted[-1] if n else 0.0:.3f}")

    # --- 2. balayage eps_max ---
    jobs = [(eps, seed) for eps in EPS_GRID for seed in seeds]
    with ProcessPoolExecutor() as ex:
        res = list(ex.map(_eps_job, jobs))

    rows = []
    print("\n===== Exp B.2 : CHR utile en fonction de la tolerance eps_max =====")
    print(f"{'eps_max':>8} {'CHR_total':>10} {'CHR_exact':>10} {'CHR_sem':>9} "
          f"{'sem_rejete':>11} {'FHR':>7}")
    for eps in EPS_GRID:
        sub = [m for (e, s, m) in res if e == eps]
        def avg(k):
            return sum(x[k] for x in sub) / len(sub)
        label = "inf" if eps == float("inf") else f"{eps:.2f}"
        print(f"{label:>8} {avg('CHR'):10.1f} {avg('CHR_exact'):10.1f} "
              f"{avg('CHR_sem'):9.1f} {avg('n_sem_rejected'):11.0f} {avg('FHR'):7.1f}")
        rows.append({"eps_max": label, "CHR": avg("CHR"), "CHR_exact": avg("CHR_exact"),
                     "CHR_sem": avg("CHR_sem"), "n_sem_rejected": avg("n_sem_rejected"),
                     "FHR": avg("FHR"), "EUB": avg("EUB")})

    with open(OUTCSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["eps_max", "CHR", "CHR_exact", "CHR_sem",
                                          "n_sem_rejected", "FHR", "EUB"])
        w.writeheader()
        w.writerows(rows)
    print(f"\nEcrit : {OUTCSV}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 30)
