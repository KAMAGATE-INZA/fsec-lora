"""
exp_F_radio_reliability.py
==========================
Exp F (revision PEMWN) - Fiabilite radio : pertes, collisions, retransmissions
(repond a R3 partiel, R16).

Le relecteur note que la couche radio etait deterministe. On introduit un canal
stochastique : chaque trame peut etre perdue avec une probabilite = PER de base
+ un terme de collision qui croit avec l'occupation du canal et le ToA (trames
longues, SF eleves). Les pertes declenchent des retransmissions (energie, duty
cycle, latence) et, au-dela de max_retx, une requete non servie.

On balaie le PER de base (collisions activees, 3 retransmissions max) et on
compare FSEC / LRU / pCASTING sur CHR, FHR, EUB, latence, retransmissions et
requetes perdues. Hypothese : FSEC, qui declenche moins d'emissions (plus de hits),
est plus robuste aux pertes.

Usage : python3 exp_F_radio_reliability.py [n_seeds]     # defaut 20
"""
from __future__ import annotations
import csv
import os
import sys
from concurrent.futures import ProcessPoolExecutor

from fsec_sim import Config, run_one

HERE = os.path.dirname(__file__)
OUTDIR = os.path.join(HERE, "rev")
OUTCSV = os.path.join(OUTDIR, "expF_radio_reliability.csv")
BASE = dict(cache_size=100, sf=7, battery_init_frac=1.0,
            collision=True, coll_coef=2.0, max_retx=3)
PER_GRID = [0.0, 0.05, 0.10, 0.20]
STRATS = ["FSEC", "LRU", "pCASTING"]


def _job(args):
    per, strat, seed = args
    m = run_one(Config(strategy=strat, seed=seed, per_base=per, **BASE))
    return {"per_base": per, "strategy": strat, "seed": seed,
            "CHR": m["CHR"], "FHR": m["FHR"], "EUB": m["EUB"],
            "latency_ms": m["latency_ms"], "n_retx": m["n_retx"],
            "n_tx_lost": m["n_tx_lost"]}


def _avg(rows, k):
    return sum(r[k] for r in rows) / len(rows) if rows else 0.0


def main(n_seeds: int):
    os.makedirs(OUTDIR, exist_ok=True)
    seeds = list(range(n_seeds))
    jobs = [(per, st, s) for per in PER_GRID for st in STRATS for s in seeds]
    print(f"Exp F : {len(jobs)} runs (collisions ON, max_retx=3)...")
    with ProcessPoolExecutor() as ex:
        rows = list(ex.map(_job, jobs))

    with open(OUTCSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["per_base", "strategy", "seed", "CHR", "FHR",
                                          "EUB", "latency_ms", "n_retx", "n_tx_lost"])
        w.writeheader()
        w.writerows(rows)

    for per in PER_GRID:
        print(f"\n===== PER de base = {per:.0%} (collisions activees) =====")
        print(f"{'strategie':10} {'CHR':>7} {'FHR':>7} {'EUB':>9} {'lat(ms)':>8} "
              f"{'retx':>8} {'perdus':>8}")
        for st in STRATS:
            sub = [r for r in rows if r["per_base"] == per and r["strategy"] == st]
            print(f"{st:10} {_avg(sub,'CHR'):7.1f} {_avg(sub,'FHR'):7.1f} "
                  f"{_avg(sub,'EUB'):9.4f} {_avg(sub,'latency_ms'):8.0f} "
                  f"{_avg(sub,'n_retx'):8.0f} {_avg(sub,'n_tx_lost'):8.0f}")
    print(f"\nEcrit : {OUTCSV}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 20)
