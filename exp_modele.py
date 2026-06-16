"""
exp_modele.py
=============
Expériences de validation des choix de modélisation FSEC-LoRa, demandées au
chapitre 3 :
  (A) sens du terme d'énergie : E (favorise les capteurs chargés) vs (1-E)
      (favorise/protège les capteurs faibles) ;
  (B) forme de la fonction d'utilité : multiplicative vs additive.

Le simulateur canonique (fsec_sim.py) n'est PAS modifié : on sous-classe le
Simulator et on redéfinit uniquement le calcul d'utilité, à graines identiques.

Usage :
    python3 exp_modele.py
"""
from __future__ import annotations
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from fsec_sim import Simulator, Config


class VariantSim(Simulator):
    """Simulateur FSEC avec sens d'énergie et forme d'utilité paramétrables."""
    def __init__(self, cfg, util_mode="mult", energy_dir="direct", kappa=2.0):
        self.util_mode = util_mode        # "mult" | "add" | "misscost"
        self.energy_dir = energy_dir      # "direct" (E) | "inverse" (1-E) | "adaptive"
        self.kappa = kappa                # poids du bonus énergie dans misscost
        self._emin = 1.0                  # stress énergétique réseau (min des E vivants)
        super().__init__(cfg)

    def handle_request(self, sid, t):
        if self.energy_dir == "adaptive":
            alive = [s.battery_j / self.cfg.battery_capacity_j
                     for s in self.sensors if s.alive]
            self._emin = min(alive) if alive else 0.0
        return super().handle_request(sid, t)

    def fsec_utility(self, sid, value, t_gen, t):
        cfg = self.cfg
        age = t - t_gen
        F = max(0.0, (cfg.ttl - age) / cfg.ttl)
        S = self.spatial_redundancy(sid, value)
        E = max(0.0, self.sensors[sid].battery_j / cfg.battery_capacity_j)
        if self.energy_dir == "inverse":
            E = 1.0 - E
        if self.util_mode == "misscost":
            # U = F^a (1-S)^b * (1 + kappa*(1-E))
            # "coût d'un miss" : garder en priorité les données dont la
            # ré-émission coûterait cher (producteur faible en batterie),
            # avec un plancher (le 1) qui évite l'effondrement à batterie pleine.
            Eraw = max(0.0, self.sensors[sid].battery_j / cfg.battery_capacity_j)
            miss_cost = 1.0 + self.kappa * (1.0 - Eraw)
            return (F ** cfg.alpha) * ((1.0 - S) ** cfg.beta) * miss_cost
        if self.util_mode == "add":
            a, b, g = cfg.alpha, cfg.beta, cfg.gamma
            tot = a + b + g
            return (a * F + b * (1.0 - S) + g * E) / tot
        if self.energy_dir == "adaptive":
            # protège les faibles SEULEMENT quand le réseau est sous stress :
            # gamma_eff -> 0 quand toutes les batteries sont pleines (E term -> 1,
            # CHR préservé) ; gamma_eff croît quand un noeud devient critique.
            gamma_eff = cfg.gamma * (1.0 - self._emin)
            return (F ** cfg.alpha) * ((1.0 - S) ** cfg.beta) * ((1.0 - E) ** gamma_eff)
        return (F ** cfg.alpha) * ((1.0 - S) ** cfg.beta) * (E ** cfg.gamma)


def run_variant(args):
    cfg, util_mode, energy_dir = args
    return VariantSim(cfg, util_mode=util_mode, energy_dir=energy_dir).run()


def mean(key, results):
    return sum(r[key] for r in results) / len(results)


def campaign(variants, base_kwargs, seeds):
    """Renvoie {nom_variant: [metrics par graine]} en parallèle."""
    jobs, index = [], {}
    for name, (um, ed) in variants.items():
        index[name] = []
        for s in seeds:
            cfg = Config(strategy="FSEC", seed=s, **base_kwargs)
            index[name].append(len(jobs))
            jobs.append((cfg, um, ed))
    with ProcessPoolExecutor() as ex:
        out = list(ex.map(run_variant, jobs))
    return {name: [out[i] for i in idx] for name, idx in index.items()}


def show(title, res):
    print(f"\n=== {title} ===")
    print(f"{'variante':16} {'CHR':>6} {'FHR':>6} {'EUB':>8} {'DCVR':>6} {'vie(s)':>8}")
    for name, rs in res.items():
        print(f"{name:16} {mean('CHR',rs):6.1f} {mean('FHR',rs):6.1f} "
              f"{mean('EUB',rs):8.4f} {mean('DCVR',rs):6.1f} {mean('lifetime',rs):8.0f}")


if __name__ == "__main__":
    seeds = list(range(10))

    # (A)+(B) sur la config de référence (cache=100, SF7, batterie pleine)
    variants = {
        "mult E":      ("mult", "direct"),
        "mult (1-E)":  ("mult", "inverse"),
        "add E":       ("add",  "direct"),
        "add (1-E)":   ("add",  "inverse"),
    }
    res = campaign(variants, dict(cache_size=100, sf=7), seeds)
    show("Référence (cache=100, SF7, batterie pleine)", res)

    # (A) balayage batterie : E vs (1-E) vs adaptatif sur la durée de vie
    for bf in (1.0, 0.5, 0.25):
        res = campaign({"mult E": ("mult", "direct"),
                        "mult (1-E)": ("mult", "inverse"),
                        "mult adaptatif": ("mult", "adaptive")},
                       dict(cache_size=100, sf=7, battery_init_frac=bf), seeds)
        show(f"Batterie initiale {int(bf*100)}%", res)
