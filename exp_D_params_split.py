"""
exp_D_params_split.py
=====================
Exp D (revision PEMWN) - Sensibilite des parametres SANS fuite reglage/test
(R9) + balayage du seuil d'admission Uth (R10).

Protocole anti-fuite : trois jeux de graines DISJOINTS.
  - reglage (train)  : recherche en grille de (alpha, beta, kappa) ;
  - validation       : confirmation du choix ;
  - test             : resultats finaux, sur graines JAMAIS vues au reglage.

Critere de selection : maximiser CHR x FHR (sous DCVR = 0, toujours vrai pour
FSEC). On compare la config selectionnee a la config par defaut du memoire
(1.5, 0.5, 3) sur les trois jeux, pour montrer qu'elle tient hors echantillon.
Enfin, balayage de Uth sur le jeu de test.

Scenario allege (n_sensors=120, sim_time=1800), comme la grille d'origine.
Usage : python3 exp_D_params_split.py
"""
from __future__ import annotations
import csv
import os
from concurrent.futures import ProcessPoolExecutor

from fsec_sim import Config, run_one

HERE = os.path.dirname(__file__)
OUTDIR = os.path.join(HERE, "rev")
OUTCSV = os.path.join(OUTDIR, "expD_params_split.csv")

BASE = dict(strategy="FSEC", cache_size=100, sf=7, battery_init_frac=1.0,
            n_sensors=120, sim_time=1800.0)
ALPHAS = [0.5, 1.0, 1.5, 2.0]
BETAS = [0.5, 1.0, 1.5, 2.0]
KAPPAS = [0.0, 1.0, 2.0, 3.0]
DEFAULT = (1.5, 0.5, 3.0)
UTHS = [0.01, 0.05, 0.10, 0.20]

TRAIN = list(range(0, 8))
VAL = list(range(50, 58))
TEST = list(range(100, 108))


def _job(args):
    a, b, k, u, seed = args
    m = run_one(Config(seed=seed, alpha=a, beta=b, kappa=k, u_seuil=u, **BASE))
    return (a, b, k, u, seed, m["CHR"], m["FHR"], m["DCVR"], m["EUB"])


def _score(rows):
    """moyenne de (CHR*FHR/100) sur les graines."""
    vals = [r[5] * r[6] / 100.0 for r in rows]
    return sum(vals) / len(vals) if vals else 0.0


def _avg(rows, idx):
    return sum(r[idx] for r in rows) / len(rows) if rows else 0.0


def eval_config(a, b, k, seeds, u=0.05):
    jobs = [(a, b, k, u, s) for s in seeds]
    with ProcessPoolExecutor() as ex:
        return list(ex.map(_job, jobs))


def main():
    os.makedirs(OUTDIR, exist_ok=True)

    # --- 1. GRILLE sur le jeu de reglage ---
    grid_jobs = [(a, b, k, 0.05, s)
                 for a in ALPHAS for b in BETAS for k in KAPPAS for s in TRAIN]
    print(f"Exp D : grille {len(ALPHAS)*len(BETAS)*len(KAPPAS)} configs "
          f"x {len(TRAIN)} graines reglage = {len(grid_jobs)} runs...")
    with ProcessPoolExecutor() as ex:
        grid_res = list(ex.map(_job, grid_jobs))

    by_cfg = {}
    for r in grid_res:
        by_cfg.setdefault((r[0], r[1], r[2]), []).append(r)
    ranked = sorted(by_cfg.items(), key=lambda kv: _score(kv[1]), reverse=True)

    print("\n--- Top 5 configs sur le jeu de REGLAGE (score = CHR x FHR / 100) ---")
    print(f"{'(alpha,beta,kappa)':>20} {'score':>8} {'CHR':>7} {'FHR':>7}")
    for cfg, rows in ranked[:5]:
        print(f"{str(cfg):>20} {_score(rows):8.1f} {_avg(rows,5):7.1f} {_avg(rows,6):7.1f}")
    best = ranked[0][0]
    print(f"\nConfig selectionnee (reglage) : {best}")
    print(f"Config par defaut du memoire   : {DEFAULT}")

    # --- 2. Confirmation sur VALIDATION et TEST ---
    print("\n--- Generalisation hors echantillon (score = CHR x FHR / 100) ---")
    print(f"{'config':>20} {'jeu':>10} {'score':>8} {'CHR':>7} {'FHR':>7} {'EUB':>8} {'DCVR':>6}")
    out_rows = []
    for name, cfg in [("selectionnee", best), ("defaut", DEFAULT)]:
        for jeu, seeds in [("reglage", TRAIN), ("validation", VAL), ("test", TEST)]:
            rows = eval_config(cfg[0], cfg[1], cfg[2], seeds)
            print(f"{str(cfg):>20} {jeu:>10} {_score(rows):8.1f} {_avg(rows,5):7.1f} "
                  f"{_avg(rows,6):7.1f} {_avg(rows,8):8.4f} {_avg(rows,7):6.1f}")
            out_rows.append({"config": name, "abk": str(cfg), "jeu": jeu,
                             "score": _score(rows), "CHR": _avg(rows, 5),
                             "FHR": _avg(rows, 6), "EUB": _avg(rows, 8), "DCVR": _avg(rows, 7)})

    # --- 3. Balayage Uth sur le jeu de TEST (config par defaut) ---
    print("\n--- Sensibilite au seuil d'admission Uth (jeu de TEST, config defaut) ---")
    print(f"{'Uth':>6} {'CHR':>7} {'FHR':>7} {'EUB':>8} {'DCVR':>6}")
    for u in UTHS:
        jobs = [(DEFAULT[0], DEFAULT[1], DEFAULT[2], u, s) for s in TEST]
        with ProcessPoolExecutor() as ex:
            rows = list(ex.map(_job, jobs))
        print(f"{u:6.2f} {_avg(rows,5):7.1f} {_avg(rows,6):7.1f} {_avg(rows,8):8.4f} {_avg(rows,7):6.1f}")
        out_rows.append({"config": "uth_sweep", "abk": str(DEFAULT), "jeu": f"test_uth={u}",
                         "score": _score(rows), "CHR": _avg(rows, 5), "FHR": _avg(rows, 6),
                         "EUB": _avg(rows, 8), "DCVR": _avg(rows, 7)})

    with open(OUTCSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["config", "abk", "jeu", "score", "CHR", "FHR", "EUB", "DCVR"])
        w.writeheader()
        w.writerows(out_rows)
    print(f"\nEcrit : {OUTCSV}")


if __name__ == "__main__":
    main()
