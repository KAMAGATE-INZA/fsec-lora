"""
exp_C_correlation.py
====================
Exp C (revision PEMWN) - Sensibilite a la correlation spatiale (R7, R8).

Le CHR de FSEC depend fortement des hits semantiques, donc de la correlation
spatiale. On eprouve cette dependance en faisant varier :
  (1) sigma_d   : largeur du noyau spatial (force de la correlation exploitee) ;
  (2) sigma_v   : largeur du noyau de valeur ;
  (3) layout    : deploiement en grappes (correle) vs uniforme (decorrele).

FSEC est compare a LRU. On rapporte CHR total, part semantique, FHR, EUB.
Le message attendu (honnete) : l'avantage CHR de FSEC croit avec la correlation
et peut passer sous LRU en regime faiblement correle ; ses autres garanties
(FHR, EUB) n'en dependent pas.

Usage : python3 exp_C_correlation.py [n_seeds]     # defaut 20
"""
from __future__ import annotations
import csv
import os
import sys
from concurrent.futures import ProcessPoolExecutor

from fsec_sim import Config, run_one

HERE = os.path.dirname(__file__)
OUTDIR = os.path.join(HERE, "rev")
OUTCSV = os.path.join(OUTDIR, "expC_correlation.csv")
BASE = dict(cache_size=100, sf=7, battery_init_frac=1.0)


def _job(args):
    tag, strat, kw, seed = args
    m = run_one(Config(strategy=strat, seed=seed, **{**BASE, **kw}))
    return {"sweep": tag, "strategy": strat, "seed": seed,
            **{k: v for k, v in kw.items()},
            "CHR": m["CHR"], "CHR_sem": m["CHR_sem"], "FHR": m["FHR"], "EUB": m["EUB"]}


def _avg(rows, k):
    xs = [r[k] for r in rows]
    return sum(xs) / len(xs) if xs else 0.0


def main(n_seeds: int):
    os.makedirs(OUTDIR, exist_ok=True)
    seeds = list(range(n_seeds))
    jobs = []
    # (1) sigma_d
    for v in [40, 60, 80, 100, 120]:
        for st in ["FSEC", "LRU"]:
            for s in seeds:
                jobs.append(("sigma_d", st, {"sigma_d": v}, s))
    # (2) sigma_v
    for v in [0.4, 0.8, 1.6]:
        for st in ["FSEC", "LRU"]:
            for s in seeds:
                jobs.append(("sigma_v", st, {"sigma_v": v}, s))
    # (3) layout
    for lay in ["clustered", "uniform"]:
        for st in ["FSEC", "LRU"]:
            for s in seeds:
                jobs.append(("layout", st, {"layout": lay}, s))

    print(f"Exp C : {len(jobs)} runs...")
    with ProcessPoolExecutor() as ex:
        rows = list(ex.map(_job, jobs))

    with open(OUTCSV, "w", newline="") as f:
        keys = ["sweep", "strategy", "seed", "sigma_d", "sigma_v", "layout",
                "CHR", "CHR_sem", "FHR", "EUB"]
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    def table(tag, title, param, values):
        print(f"\n===== {title} =====")
        print(f"{param:>10} | {'FSEC CHR':>9} {'(sem)':>7} {'FHR':>6} {'EUB':>8} "
              f"| {'LRU CHR':>8} {'FHR':>6} {'EUB':>8}")
        for v in values:
            fs = [r for r in rows if r["sweep"] == tag and r["strategy"] == "FSEC" and r.get(param) == v]
            lr = [r for r in rows if r["sweep"] == tag and r["strategy"] == "LRU" and r.get(param) == v]
            print(f"{str(v):>10} | {_avg(fs,'CHR'):9.1f} {_avg(fs,'CHR_sem'):7.1f} "
                  f"{_avg(fs,'FHR'):6.1f} {_avg(fs,'EUB'):8.4f} | "
                  f"{_avg(lr,'CHR'):8.1f} {_avg(lr,'FHR'):6.1f} {_avg(lr,'EUB'):8.4f}")

    table("sigma_d", "sigma_d (correlation spatiale)", "sigma_d", [40, 60, 80, 100, 120])
    table("sigma_v", "sigma_v (correlation de valeur)", "sigma_v", [0.4, 0.8, 1.6])
    table("layout", "layout (deploiement)", "layout", ["clustered", "uniform"])
    print(f"\nEcrit : {OUTCSV}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 20)
