"""
run_campaign.py
===============
Campagne de simulation FSEC-LoRa, reproductible et REPRENABLE.

Chaque resultat est ecrit immediatement dans results.csv. Au redemarrage, les
configurations deja presentes sont ignorees, ce qui permet de lancer la campagne
en plusieurs passes (utile sous contrainte de temps). Execution parallele sur
tous les coeurs disponibles.

Usage :
    python3 run_campaign.py [budget_secondes]

Experiences :
  - cache    : balayage de la taille du cache (figure CHR/FHR/EUB/DCVR vs cache)
  - sf       : balayage du Spreading Factor (effet du Time-on-Air)
  - battery  : balayage du niveau de batterie initial
  - grid     : recherche en grille des exposants FSEC (alpha,beta,kappa,u_seuil)
"""

from __future__ import annotations
import csv
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace

from fsec_sim import Config, run_one

RESULTS = os.path.join(os.path.dirname(__file__), "results.csv")
STRATS = ["No-cache", "LRU", "LFU", "Prob", "AdaptiveTTL", "pCASTING", "CFPC", "FSEC"]
FIELDS = ["experiment", "strategy", "cache_size", "sf", "battery_frac",
          "alpha", "beta", "kappa", "u_seuil", "gamma", "lam", "seed",
          "CHR", "FHR", "EUB", "DCVR", "lifetime", "latency_ms", "n_requests"]


def base_config(**kw) -> Config:
    return Config(**kw)


def build_jobs() -> list[dict]:
    """Liste des configurations (chaque job = dict de parametres)."""
    jobs = []

    # --- EXP 1 : balayage taille de cache (sf=7, batterie pleine) ---
    for seed in range(80):
        jobs.append(dict(experiment="cache", strategy="No-cache",
                         cache_size=0, sf=8, battery_init_frac=1.0, seed=seed))
        for strat in ["LRU", "LFU", "Prob", "AdaptiveTTL", "pCASTING", "CFPC", "FSEC"]:
            for cs in [50, 100, 250, 500]:
                jobs.append(dict(experiment="cache", strategy=strat,
                                 cache_size=cs, sf=8, battery_init_frac=1.0, seed=seed))

    # --- EXP 2 : balayage Spreading Factor (cache=100) ---
    for seed in range(80):
        for strat in STRATS:
            for sf in [7, 8, 9, 10, 11, 12]:
                cs = 0 if strat == "No-cache" else 100
                jobs.append(dict(experiment="sf", strategy=strat,
                                 cache_size=cs, sf=sf, battery_init_frac=1.0, seed=seed))

    # --- EXP 3 : balayage batterie initiale (cache=100, sf=7) ---
    for seed in range(80):
        for strat in STRATS:
            for bf in [1.0, 0.75, 0.5, 0.25]:
                cs = 0 if strat == "No-cache" else 100
                jobs.append(dict(experiment="battery", strategy=strat,
                                 cache_size=cs, sf=7, battery_init_frac=bf, seed=seed))

    # --- EXP 4 : grid search des parametres FSEC (alpha, beta, kappa, u_seuil) ---
    # kappa=0 inclus pour montrer l'apport du terme d'energie (cout d'un miss).
    # u_seuil testee sur l'intervalle 0.0..0.5 avec pas de 0.01.
    u_values = [round(i * 0.01, 2) for i in range(0, 51)]
    for seed in range(20):
        for a in [0.5, 1.0, 1.5, 2.0]:
            for b in [0.5, 1.0, 1.5, 2.0]:
                for k in [0.0, 1.0, 2.0, 3.0]:
                    for u in u_values:
                        jobs.append(dict(experiment="grid", strategy="FSEC",
                                         cache_size=100, sf=7, battery_init_frac=1.0,
                                         alpha=a, beta=b, kappa=k, u_seuil=u, seed=seed,
                                         n_sensors=120, sim_time=1800.0))
    return jobs


def job_key(j: dict) -> tuple:
    return (j["experiment"], j["strategy"], j["cache_size"], j["sf"],
            j["battery_frac"] if "battery_frac" in j else j.get("battery_init_frac"),
            round(j.get("alpha", 1.5), 3), round(j.get("beta", 1.0), 3),
            round(j.get("kappa", 3.0), 3), round(j.get("u_seuil", 0.05), 6),
            round(j.get("gamma", 1.0), 3), round(j.get("lam", 2.0), 3), j["seed"])


def _normalize_row(header: list[str], row: list[str]) -> dict:
    if len(header) == len(row):
        return dict(zip(header, row))

    # Ancien format sans u_seuil : insere la colonne par defaut.
    if len(header) == len(FIELDS) and len(row) == len(FIELDS) - 1:
        row = row[:8] + ["0.05"] + row[8:]
        return dict(zip(header, row))

    # Cas inverse (header sans u_seuil et ligne nouvelle) : on ignore la colonne en trop.
    if len(header) == len(FIELDS) - 1 and len(row) == len(FIELDS):
        header = FIELDS
        return dict(zip(header, row))

    # Format inattendu : on remplit au mieux.
    row = row[:len(header)] + [""] * max(0, len(header) - len(row))
    return dict(zip(header, row))


def row_key(r: dict) -> tuple:
    seed = r.get("seed", "0")
    try:
        seed = int(seed)
    except ValueError:
        try:
            seed = int(float(seed))
        except ValueError:
            seed = 0
    return (r["experiment"], r["strategy"], int(float(r["cache_size"])), int(float(r["sf"])),
            float(r["battery_frac"]), round(float(r["alpha"]), 3),
            round(float(r["beta"]), 3), round(float(r["kappa"]), 3),
            round(float(r.get("u_seuil", 0.05)), 6),
            round(float(r["gamma"]), 3), round(float(r["lam"]), 3), seed)


def run_job(j: dict) -> dict:
    cfg_kw = {k: v for k, v in j.items() if k != "experiment"}
    cfg = base_config(**cfg_kw)
    m = run_one(cfg)
    return {
        "experiment": j["experiment"], "strategy": cfg.strategy,
        "cache_size": cfg.cache_size, "sf": cfg.sf,
        "battery_frac": cfg.battery_init_frac,
        "alpha": cfg.alpha, "beta": cfg.beta, "kappa": cfg.kappa,
        "u_seuil": cfg.u_seuil, "gamma": cfg.gamma, "lam": cfg.lam,
        "seed": cfg.seed,
        "CHR": m["CHR"], "FHR": m["FHR"], "EUB": m["EUB"], "DCVR": m["DCVR"],
        "lifetime": m["lifetime"], "latency_ms": m["latency_ms"],
        "n_requests": m["n_requests"],
    }


def load_done() -> set:
    done = set()
    if os.path.exists(RESULTS):
        with open(RESULTS, newline="") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if header is None:
                return done
            for row in reader:
                if not row:
                    continue
                r = _normalize_row(header, row)
                done.add(row_key(r))
    return done


def main(budget: float):
    jobs = build_jobs()
    done = load_done()
    todo = [j for j in jobs if job_key(j) not in done]
    print(f"Total jobs: {len(jobs)} | deja faits: {len(done)} | a faire: {len(todo)}")
    if not todo:
        print("Campagne terminee.")
        return

    new_file = not os.path.exists(RESULTS)
    f = open(RESULTS, "a", newline="")
    writer = csv.DictWriter(f, fieldnames=FIELDS)
    if new_file:
        writer.writeheader()

    deadline = time.time() + budget
    n_done = 0
    nworkers = os.cpu_count() or 4
    with ProcessPoolExecutor(max_workers=nworkers) as ex:
        futures = {}
        it = iter(todo)
        # amorcage : une vague de taches
        for _ in range(nworkers):
            try:
                j = next(it)
                futures[ex.submit(run_job, j)] = j
            except StopIteration:
                break
        while futures:
            fut = next(as_completed(futures))
            futures.pop(fut)
            writer.writerow(fut.result())
            f.flush()
            n_done += 1
            # soumettre une nouvelle tache seulement si le budget n'est pas epuise
            if time.time() < deadline:
                try:
                    nj = next(it)
                    futures[ex.submit(run_job, nj)] = nj
                except StopIteration:
                    pass
    f.close()
    print(f"Cette passe: {n_done} runs ecrits. Restant ~{len(todo) - n_done}.")


if __name__ == "__main__":
    budget = float(sys.argv[1]) if len(sys.argv) > 1 else 40.0
    main(budget)
