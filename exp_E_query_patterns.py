"""
exp_E_query_patterns.py
=======================
Exp E (revision PEMWN) - Sensibilite aux motifs de requetes (R17).

Le relecteur note une tension : le trafic LoRaWAN de supervision est periodique,
or l'evaluation utilise un processus de Poisson avec popularite Zipf. On evalue
donc une matrice de motifs, en distinguant :
  - la LOI D'ARRIVEE des requetes : poisson | periodic | bursty ;
  - la SELECTION du capteur demande : uniforme (zipf_s=0) | Zipf (zipf_s=0.8).

Comparaison FSEC / LRU / pCASTING (config de reference). On montre que FSEC est
robuste a la loi de trafic, la ou les politiques de popularite s'effondrent en
trafic uniforme (regime typique de la supervision LoRaWAN).

Usage : python3 exp_E_query_patterns.py [n_seeds]     # defaut 20
"""
from __future__ import annotations
import csv
import os
import sys
from concurrent.futures import ProcessPoolExecutor

from fsec_sim import Config, run_one

HERE = os.path.dirname(__file__)
OUTDIR = os.path.join(HERE, "rev")
OUTCSV = os.path.join(OUTDIR, "expE_query_patterns.csv")
BASE = dict(cache_size=100, sf=7, battery_init_frac=1.0)

ARRIVALS = ["poisson", "periodic", "bursty"]
SELECTIONS = [("uniforme", 0.0), ("zipf", 0.8)]
STRATS = ["FSEC", "LRU", "pCASTING"]


def _job(args):
    arrival, sel_name, zipf_s, strat, seed = args
    m = run_one(Config(strategy=strat, seed=seed, arrival=arrival, zipf_s=zipf_s, **BASE))
    return {"arrival": arrival, "selection": sel_name, "strategy": strat, "seed": seed,
            "CHR": m["CHR"], "CHR_sem": m["CHR_sem"], "FHR": m["FHR"], "EUB": m["EUB"]}


def _avg(rows, k):
    return sum(r[k] for r in rows) / len(rows) if rows else 0.0


def main(n_seeds: int):
    os.makedirs(OUTDIR, exist_ok=True)
    seeds = list(range(n_seeds))
    jobs = [(arr, sn, zs, st, s)
            for arr in ARRIVALS
            for (sn, zs) in SELECTIONS
            for st in STRATS
            for s in seeds]
    print(f"Exp E : {len(jobs)} runs...")
    with ProcessPoolExecutor() as ex:
        rows = list(ex.map(_job, jobs))

    with open(OUTCSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["arrival", "selection", "strategy", "seed",
                                          "CHR", "CHR_sem", "FHR", "EUB"])
        w.writeheader()
        w.writerows(rows)

    for arr in ARRIVALS:
        for (sn, zs) in SELECTIONS:
            print(f"\n===== arrivee = {arr} | selection = {sn} =====")
            print(f"{'strategie':10} {'CHR':>7} {'(sem)':>7} {'FHR':>7} {'EUB':>8}")
            for st in STRATS:
                sub = [r for r in rows if r["arrival"] == arr and r["selection"] == sn
                       and r["strategy"] == st]
                print(f"{st:10} {_avg(sub,'CHR'):7.1f} {_avg(sub,'CHR_sem'):7.1f} "
                      f"{_avg(sub,'FHR'):7.1f} {_avg(sub,'EUB'):8.4f}")
    print(f"\nEcrit : {OUTCSV}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 20)
