"""
exp_A_fair_dc.py
================
Exp A (revision PEMWN) - Comparaison a DUTY CYCLE EGAL (repond a R1 et R13).

Le relecteur reproche a juste titre que seul FSEC applique la regle d'emission
(offload backhaul pres du quota), les baselines etant autorisees a violer. On
compare donc toutes les strategies dans DEUX regimes :

  - "free"    : regime historique (seul FSEC est conscient du duty cycle) ;
  - "enforce" : regime EQUITABLE (dc_enforce_all=True : la regle d'emission
                s'applique a TOUTES les strategies).

Sous "enforce", le DCVR tombe a ~0 partout et n'est plus discriminant : la
comparaison porte alors sur la QUALITE DE SERVICE a conformite egale (CHR exact
et semantique, FHR, EUB, reponses backhaul/differees, latence).

Deux baselines demandees par R13 sont incluses :
  - LRU (avec regle d'emission = "LRU+DC" sous enforce) ;
  - FreshEnergy : fraicheur + energie SANS terme spatial ni hit semantique
    (= "Fraicheur/Energie+DC" sous enforce), pour isoler l'apport propre de la
    correlation spatiale de FSEC.

Sorties :
  - rev/expA_fair_dc.csv  (une ligne par run : scenario, strategy, seed, metriques)
  - tableaux agreges (moyenne +/- IC95) imprimes a l'ecran.

Usage :
    python3 exp_A_fair_dc.py [n_seeds]      # defaut 30
"""
from __future__ import annotations
import csv
import os
import sys
from concurrent.futures import ProcessPoolExecutor

from fsec_sim import Config, Simulator

HERE = os.path.dirname(__file__)
OUTDIR = os.path.join(HERE, "rev")
OUTCSV = os.path.join(OUTDIR, "expA_fair_dc.csv")

# config de reference du memoire
BASE = dict(cache_size=100, sf=7, battery_init_frac=1.0)
STRATS = ["No-cache", "LRU", "LFU", "Prob", "AdaptiveTTL",
          "pCASTING", "CFPC", "FreshEnergy", "FSEC"]
SCENARIOS = {"free": False, "enforce": True}   # nom -> dc_enforce_all

METRICS = ["CHR", "CHR_exact", "CHR_sem", "FHR", "EUB", "DCVR",
           "n_backhaul", "latency_ms", "lifetime"]


def _job(args):
    scenario, enforce, strat, seed = args
    cs = 0 if strat == "No-cache" else BASE["cache_size"]
    cfg = Config(strategy=strat, seed=seed, dc_enforce_all=enforce,
                 **{**BASE, "cache_size": cs})
    m = Simulator(cfg).run()
    row = {"scenario": scenario, "strategy": strat, "seed": seed}
    for k in METRICS:
        row[k] = m[k]
    return row


def _mean_ci(xs):
    import math
    n = len(xs)
    mu = sum(xs) / n
    if n < 2:
        return mu, 0.0
    var = sum((x - mu) ** 2 for x in xs) / (n - 1)
    return mu, 1.96 * math.sqrt(var) / math.sqrt(n)


def main(n_seeds: int):
    os.makedirs(OUTDIR, exist_ok=True)
    jobs = [(name, enforce, strat, seed)
            for name, enforce in SCENARIOS.items()
            for strat in STRATS
            for seed in range(n_seeds)]
    print(f"Exp A : {len(jobs)} runs ({len(STRATS)} strategies x "
          f"{len(SCENARIOS)} regimes x {n_seeds} graines)...")
    with ProcessPoolExecutor() as ex:
        rows = list(ex.map(_job, jobs))

    with open(OUTCSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["scenario", "strategy", "seed"] + METRICS)
        w.writeheader()
        w.writerows(rows)
    print(f"Ecrit : {OUTCSV}\n")

    # agregation
    agg = {}
    for r in rows:
        agg.setdefault((r["scenario"], r["strategy"]), []).append(r)

    for scenario in SCENARIOS:
        print(f"===== Regime '{scenario}' "
              f"({'equitable : regle d emission pour TOUS' if scenario=='enforce' else 'historique : seul FSEC conscient'}) =====")
        print(f"{'strategie':12} {'CHR':>7} {'exact':>7} {'sem':>7} {'FHR':>7} "
              f"{'EUB':>8} {'DCVR':>7} {'backhaul':>9} {'lat(ms)':>8}")
        for strat in STRATS:
            rs = agg[(scenario, strat)]
            def col(k):
                return _mean_ci([x[k] for x in rs])[0]
            print(f"{strat:12} {col('CHR'):7.1f} {col('CHR_exact'):7.1f} "
                  f"{col('CHR_sem'):7.1f} {col('FHR'):7.1f} {col('EUB'):8.4f} "
                  f"{col('DCVR'):7.1f} {col('n_backhaul'):9.0f} {col('latency_ms'):8.1f}")
        print()


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    main(n)
