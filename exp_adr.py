"""
exp_adr.py
==========
Extension : deploiement ADR (Adaptive Data Rate), ou les capteurs utilisent des
Spreading Factors HETEROGENES selon leur distance a la passerelle. Un capteur
lointain (SF12) a un Time-on-Air long : rafraichir sa donnee coute cher (energie
ET duty cycle). On evalue l'apport du terme ToA dans le cout d'un miss :

    M(i) = 1 + kappa*(1-E_i) + kappa_toa*(ToA_i / ToA_max)

Comparaison (SF mixtes) : LRU, FSEC (sans ToA), FSEC+ToA (kappa_toa=3).
Usage : python3 exp_adr.py
"""
from __future__ import annotations
from concurrent.futures import ProcessPoolExecutor
import numpy as np
from fsec_sim import Config, run_one

SEEDS = list(range(39))
BASE = dict(cache_size=100, adr=True, n_sensors=150, sim_time=3600.0)


def _job(args):
    name, kw, seed = args
    m = run_one(Config(seed=seed, **{**BASE, **kw}))
    return name, (m["CHR"], m["FHR"], m["EUB"], m["DCVR"], m["lifetime"])


def main():
    variants = {
        "LRU":        dict(strategy="LRU"),
        "FSEC":       dict(strategy="FSEC", kappa_toa=0.0),
        "FSEC+ToA":   dict(strategy="FSEC", kappa_toa=3.0),
    }
    jobs = [(n, kw, s) for n, kw in variants.items() for s in SEEDS]
    with ProcessPoolExecutor() as ex:
        res = list(ex.map(_job, jobs))
    print(f"{'variante':10} {'CHR':>6} {'FHR':>6} {'EUB':>8} {'DCVR':>6} {'vie':>7}")
    for n in variants:
        rows = np.array([r for (nm, r) in res if nm == n])
        m = rows.mean(axis=0)
        print(f"{n:10} {m[0]:6.1f} {m[1]:6.1f} {m[2]:8.4f} {m[3]:6.1f} {m[4]:7.0f}")


if __name__ == "__main__":
    main()
