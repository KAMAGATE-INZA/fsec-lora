"""
fsec_sim.py
===========
Simulateur a evenements discrets pour la strategie de cache FSEC-LoRa
(ICN over LoRaWAN), et ses politiques de reference.

Ce module N'EST PAS ndnSIM. C'est un simulateur dedie, ecrit pour reproduire
fidelement le modele du chapitre 4 du memoire et produire des resultats
reproductibles (CHR, FHR, EUB, DCVR, duree de vie du reseau, latence).

Hypotheses de modelisation (documentees pour le memoire) :
 H1. Topologie LoRaWAN en etoile : N capteurs (producteurs), 1 passerelle
     (routeur NDN avec Content Store), 1 serveur applicatif (consommateur).
 H2. Donnees transitoires : chaque mesure a une periode de fraicheur TTL.
 H3. Correlation spatiale : la valeur d'un capteur = champ latent lisse au point
     du capteur + bruit. Des capteurs proches ont donc des valeurs proches.
 H4. Duty cycle : la passerelle dispose d'un budget d'emission radio
     DC_max = 36 s/heure (1%). Servir une reponse par la radio consomme le
     Time-on-Air (ToA) du paquet, fonction du Spreading Factor (SF).
     Une politique consciente du duty cycle (FSEC) cesse d'emettre par la radio
     les reponses de faible utilite quand C = 1 - DC_used/DC_max < C_min, et les
     delegue au lien IP (backhaul, non soumis au duty cycle). Les politiques
     aveugles emettent toujours, ce qui peut provoquer des violations (DCVR>0).
 H5. Energie : chaque capteur a une batterie. Un MISS oblige le capteur a
     re-emettre (uplink), operation la plus couteuse. Un HIT l'evite. La duree
     de vie du reseau = instant ou le premier capteur epuise sa batterie.

Auteur : KAMAGATE Inza (memoire M2). Code destine au depot GitHub du projet.
"""

from __future__ import annotations
import math
import random
from dataclasses import dataclass, field
from collections import OrderedDict, defaultdict
from typing import Optional


# ---------------------------------------------------------------------------
# Parametres physiques LoRa
# ---------------------------------------------------------------------------
BW = 125_000.0          # bande passante (Hz)
N_PREAMBLE = 8          # symboles de preambule
PAYLOAD_BYTES = 20      # taille utile d'un paquet Data IoT (octets)

# Courants typiques (A) d'un noeud LoRa  (cf. tableau du chapitre 4)
I_TX = 0.045            # emission ~45 mA
V_BAT = 3.3             # tension (V)

# Energie consommee par la passerelle (radio) modelisee via le ToA.

def time_on_air(sf: int, payload_bytes: int = PAYLOAD_BYTES,
                bw: float = BW, n_preamble: int = N_PREAMBLE) -> float:
    """Time-on-Air d'une trame LoRa (s), formule de Semtech simplifiee."""
    t_sym = (2 ** sf) / bw
    t_preamble = (n_preamble + 4.25) * t_sym
    # nombre de symboles de charge utile (CR=4/5, header active, pas de low-DR-opt)
    de = 1 if sf >= 11 else 0
    payload_symb = 8 + max(
        math.ceil((8 * payload_bytes - 4 * sf + 28 + 16) / (4 * (sf - 2 * de))) * 5,
        0,
    )
    t_payload = payload_symb * t_sym
    return t_preamble + t_payload


# ---------------------------------------------------------------------------
# Configuration d'une simulation
# ---------------------------------------------------------------------------
@dataclass
class Config:
    n_sensors: int = 200           # nb de capteurs (= nb de contenus distincts)
    area: float = 1000.0           # cote de la zone (m)
    n_clusters: int = 8            # foyers de correlation spatiale
    cache_size: int = 100          # C_max (entrees). 0 = pas de cache
    strategy: str = "FSEC"         # No-cache, LRU, LFU, Prob, AdaptiveTTL, FSEC
    sim_time: float = 3600.0       # horizon (s)
    req_rate: float = 5.0          # requetes/s (processus de Poisson)
    ttl: float = 60.0              # periode de fraicheur (validite) des donnees (s)
    gen_period: float = 10.0       # periode de generation des capteurs (s)
    sf: int = 7                    # spreading factor
    dc_max: float = 36.0           # budget duty cycle (s / fenetre)
    dc_window: float = 3600.0      # fenetre glissante du duty cycle (s)
    battery_init_frac: float = 1.0 # fraction de batterie initiale
    battery_capacity_j: float = 4.0  # energie totale d'un capteur (J) -- dimensionnee pour stresser No-cache
    # parametres FSEC
    alpha: float = 1.5             # fraicheur (non influent : confirme par grid search)
    beta: float = 0.5              # correlation spatiale (optimum grid search : CHR x FHR max, EUB min)
    kappa: float = 3.0             # poids du cout d'un miss (energie / protection des noeuds faibles)
    kappa_toa: float = 0.0         # poids du Time-on-Air dans le cout d'un miss (scenario ADR)
    adr: bool = False              # SF heterogenes par capteur (Adaptive Data Rate)
    gamma: float = 1.0             # (obsolete) ancien exposant energie E^gamma, conserve pour compat
    lam: float = 2.0               # (obsolete) ancien exposant duty cycle, conserve pour compat
    u_seuil: float = 0.05          # seuil d'acceptation
    c_min: float = 0.1             # seuil critique de duty cycle
    sigma_d: float = 80.0          # largeur noyau spatial (m)
    sigma_v: float = 0.8           # largeur noyau valeur
    sem_threshold: float = 0.5     # seuil de similarite pour un hit semantique (FSEC)
    prob_p: float = 0.5            # probabilite pour la politique Prob
    freshness_req_min: float = 5.0 # exigence de fraicheur consommateur (s)
    freshness_req_max: float = 20.0
    zipf_s: float = 0.8            # skew de popularite des requetes (0 = uniforme)
    # --- instrumentation revision PEMWN (additif, defauts neutres) ---
    dc_enforce_all: bool = False   # True : la regle d'emission (offload backhaul) s'applique a TOUTES les strategies (Exp A)
    eps_max: float = float("inf")  # tolerance d'erreur semantique |vA-vB| ; inf = aucun filtrage (neutre) (Exp B)
    arrival: str = "poisson"       # loi d'arrivee des requetes : poisson (defaut) | periodic | bursty (Exp E)
    layout: str = "clustered"      # deploiement : clustered (defaut) | uniform (faible correlation, Exp C)
    burst_factor: float = 6.0      # intensite des rafales (mode bursty)
    burst_duty: float = 0.2        # fraction de temps en rafale (mode bursty)
    # --- fiabilite radio stochastique (R3/R15/R16 ; defauts = canal parfait) ---
    per_base: float = 0.0          # taux d'erreur paquet de base (0 = pas de perte)
    collision: bool = False        # terme de collision dependant de la charge et du ToA
    coll_coef: float = 2.0         # intensite des collisions (facteur type ALOHA)
    coll_window: float = 10.0      # fenetre d'estimation de l'occupation canal (s)
    max_retx: int = 0              # retransmissions max sur perte (0 = aucune)
    seed: int = 1


# ---------------------------------------------------------------------------
# Entites
# ---------------------------------------------------------------------------
@dataclass
class Sensor:
    sid: int
    x: float
    y: float
    cluster: int
    battery_j: float
    sf: int = 7
    toa: float = 0.0
    last_value: float = 0.0
    last_gen_time: float = -1e9
    alive: bool = True
    death_time: Optional[float] = None


@dataclass
class CacheEntry:
    sid: int
    value: float
    t_gen: float           # instant de generation
    ttl: float
    x: float
    y: float
    freq: int = 0          # compteur d'acces (pour LFU)


# ---------------------------------------------------------------------------
# Simulateur
# ---------------------------------------------------------------------------
class Simulator:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.rng = random.Random(cfg.seed)
        self._build_topology()
        self.cache: "OrderedDict[int, CacheEntry]" = OrderedDict()
        self.toa = time_on_air(cfg.sf)
        # compteurs de duty cycle (liste d'instants d'emission dans la fenetre)
        self.tx_times: list[float] = []
        self.dc_used = 0.0
        # popularite (Zipf) des capteurs pour les requetes
        self._build_popularity()
        # metriques
        self.reset_metrics()

    # --- construction ------------------------------------------------------
    def _build_topology(self):
        cfg = self.cfg
        centers = [(self.rng.uniform(0, cfg.area), self.rng.uniform(0, cfg.area))
                   for _ in range(cfg.n_clusters)]
        self.sensors: list[Sensor] = []
        for i in range(cfg.n_sensors):
            c = i % cfg.n_clusters
            cx, cy = centers[c]
            if cfg.layout == "uniform":
                # deploiement aleatoire : positions decorrelees des clusters de
                # valeur -> regime de faible correlation spatiale (Exp C, R7/R8)
                x = self.rng.uniform(0, cfg.area)
                y = self.rng.uniform(0, cfg.area)
            else:
                x = min(max(self.rng.gauss(cx, cfg.area * 0.04), 0), cfg.area)
                y = min(max(self.rng.gauss(cy, cfg.area * 0.04), 0), cfg.area)
            bat = cfg.battery_capacity_j * cfg.battery_init_frac
            s = Sensor(i, x, y, c, bat)
            if cfg.adr:
                # ADR : SF attribue selon la distance a la passerelle (centre)
                dg = math.dist((x, y), (cfg.area / 2.0, cfg.area / 2.0))
                s.sf = 7 if dg < cfg.area * 0.22 else (9 if dg < cfg.area * 0.38 else 12)
            else:
                s.sf = cfg.sf
            s.toa = time_on_air(s.sf)
            self.sensors.append(s)
        # champ latent par cluster (valeur de base ~ temperature)
        self.cluster_base = [self.rng.uniform(15, 30) for _ in range(cfg.n_clusters)]
        # voisinage spatial precalcule (pour S(D))
        self.neighbors: dict[int, list[int]] = defaultdict(list)
        for i in range(cfg.n_sensors):
            for j in range(cfg.n_sensors):
                if i == j:
                    continue
                d = math.dist((self.sensors[i].x, self.sensors[i].y),
                              (self.sensors[j].x, self.sensors[j].y))
                if d < 3 * cfg.sigma_d:
                    self.neighbors[i].append(j)

    def _build_popularity(self):
        cfg = self.cfg
        if cfg.zipf_s <= 0:
            self.pop_weights = [1.0] * cfg.n_sensors
        else:
            self.pop_weights = [1.0 / ((k + 1) ** cfg.zipf_s)
                                for k in range(cfg.n_sensors)]
        # melange pour ne pas correler popularite et position
        order = list(range(cfg.n_sensors))
        self.rng.shuffle(order)
        w = [0.0] * cfg.n_sensors
        for rank, sid in enumerate(order):
            w[sid] = self.pop_weights[rank]
        self.pop_weights = w
        self._pop_total = sum(self.pop_weights)

    def reset_metrics(self):
        self.n_requests = 0
        self.n_hits = 0
        self.n_fresh_hits = 0
        self.n_radio_tx = 0          # emissions radio tentees par la passerelle
        self.n_dc_violations = 0     # emissions depassant le quota
        self.useful_bits = 0
        self.energy_sensors_j = 0.0  # energie depensee par les capteurs (uplinks)
        self.energy_gateway_j = 0.0  # energie radio de la passerelle
        self.latency_sum = 0.0
        self.first_death = None
        self.req_count = defaultdict(int)  # popularite par capteur (pour CFPC)
        # --- instrumentation revision (additif) ---
        self.n_exact_hits = 0       # hits exacts (donnee du capteur demande)
        self.n_sem_hits = 0         # hits semantiques (voisin correle)
        self.n_sem_rejected = 0     # hits semantiques ecartes car |vA-vB| > eps_max
        self.n_backhaul = 0         # reponses de miss deleguees au backhaul (offload)
        self.sem_errors: list[float] = []  # |vA-vB| des hits semantiques servis
        self._last_sem_err = 0.0
        # --- fiabilite radio ---
        self.n_tx_lost = 0          # transmissions perdues definitivement (apres retx)
        self.n_retx = 0             # retransmissions effectuees
        self._chan_busy = 0.0       # occupation canal (somme ToA decroissante)
        self._last_chan_t = 0.0
        self._chan_load = 0.0       # occupation normalisee [0,1]

    # --- dynamique des valeurs --------------------------------------------
    def sensor_value(self, s: Sensor, t: float) -> float:
        """Valeur courante d'un capteur (champ latent + derive lente + bruit)."""
        if t - s.last_gen_time >= self.cfg.gen_period:
            base = self.cluster_base[s.cluster]
            drift = 2.0 * math.sin(2 * math.pi * t / 600.0)  # variation lente
            s.last_value = base + drift + self.rng.gauss(0, 0.3)
            s.last_gen_time = t
        return s.last_value

    def _field_value(self, s: Sensor, t: float) -> float:
        """Valeur DETERMINISTE du champ latent au point du capteur (sans bruit ni
        mutation d'etat, donc sans consommer d'alea). Sert a mesurer l'erreur
        d'approximation semantique |v_A - v_B| sans perturber la simulation."""
        return self.cluster_base[s.cluster] + 2.0 * math.sin(2 * math.pi * t / 600.0)

    def _dc_aware(self) -> bool:
        """Vrai si la regle d'emission (offload backhaul pres du quota) s'applique.
        Par defaut : seulement FSEC (comportement historique). En mode
        dc_enforce_all : toutes les strategies (comparaison equitable, Exp A)."""
        return self.cfg.dc_enforce_all or (self.cfg.strategy == "FSEC")

    # --- duty cycle --------------------------------------------------------
    def _dc_refresh(self, t: float):
        w = self.cfg.dc_window
        while self.tx_times and self.tx_times[0][0] < t - w:
            _, dur = self.tx_times.pop(0)
            self.dc_used -= dur
        self.dc_used = max(0.0, self.dc_used)

    def dc_available(self, t: float) -> float:
        self._dc_refresh(t)
        return 1.0 - self.dc_used / self.cfg.dc_max

    def _do_radio_tx(self, t: float, aware: bool, toa: float = None) -> bool:
        """Tente une emission radio. Renvoie True si emise, False si declinee.
        Compte une violation si une politique aveugle emet au-dela du quota.
        toa : Time-on-Air de la trame (par defaut celui de la passerelle)."""
        toa = self.toa if toa is None else toa
        self._dc_refresh(t)
        self.n_radio_tx += 1
        would_exceed = (self.dc_used + toa) > self.cfg.dc_max
        if aware and would_exceed:
            return False  # FSEC offloade vers le backhaul -> pas de violation
        if would_exceed:
            self.n_dc_violations += 1
        self.tx_times.append((t, toa))
        self.dc_used += toa
        self.energy_gateway_j += toa * I_TX * V_BAT
        return True

    # --- fiabilite radio (pertes / collisions) -----------------------------
    def _chan_add(self, t: float, toa: float):
        """Met a jour l'occupation du canal (somme des ToA, decroissance exp)."""
        w = self.cfg.coll_window
        dt = t - self._last_chan_t
        if dt > 0:
            self._chan_busy *= math.exp(-dt / w)
        self._chan_busy += toa
        self._last_chan_t = t
        self._chan_load = min(1.0, self._chan_busy / w)

    def _radio_lost(self, toa: float) -> bool:
        """Perte d'une trame : PER de base + terme de collision (charge x ToA).
        Canal parfait par defaut (per_base=0 et collision=False) -> jamais de perte,
        sans consommer d'alea (non-regression)."""
        cfg = self.cfg
        if cfg.per_base <= 0.0 and not cfg.collision:
            return False
        p = cfg.per_base
        if cfg.collision:
            # periode vulnerable ~ ToA : plus la trame est longue (SF eleve) et le
            # canal charge, plus la collision est probable (modele type ALOHA)
            p += 1.0 - math.exp(-cfg.coll_coef * self._chan_load * (toa / self.toa))
        return self.rng.random() < min(0.99, p)

    # --- energie capteur ---------------------------------------------------
    def _sensor_uplink(self, s: Sensor, t: float):
        e = s.toa * I_TX * V_BAT
        s.battery_j -= e
        self.energy_sensors_j += e
        if s.battery_j <= 0 and s.alive:
            s.alive = False
            s.death_time = t
            if self.first_death is None:
                self.first_death = t

    # --- correlation spatiale (S continue, noyau gaussien) -----------------
    def spatial_redundancy(self, sid: int, value: float) -> float:
        cfg = self.cfg
        best = 0.0
        for j in self.neighbors[sid]:
            e = self.cache.get(j)
            if e is None:
                continue
            d = math.dist((self.sensors[sid].x, self.sensors[sid].y),
                          (self.sensors[j].x, self.sensors[j].y))
            r = math.exp(-(d ** 2) / (2 * cfg.sigma_d ** 2)) * \
                math.exp(-((value - e.value) ** 2) / (2 * cfg.sigma_v ** 2))
            if r > best:
                best = r
        return best

    # --- score d'utilite FSEC ---------------------------------------------
    def fsec_utility(self, sid: int, value: float, t_gen: float, t: float) -> float:
        """Score de placement et de remplacement (modele "cout d'un miss").

        U(D) = F^alpha * (1 - S)^beta * (1 + kappa * (1 - E)).

        Interpretation : U(D) estime les RESSOURCES ECONOMISEES en gardant D en
        cache. F est la fenetre de validite restante (donc le nombre de hits que
        D peut encore servir), (1-S) la non-redondance (un voisin cache rend D
        inutile), et le facteur (1 + kappa(1-E)) est le COUT d'un miss pour le
        producteur : plus sa batterie est faible (E -> 0), plus une re-emission
        lui coute cher, donc plus il est prioritaire de cacher sa donnee. Le
        plancher 1 garantit qu'a batterie pleine (E -> 1) le terme vaut 1 et ne
        degrade pas le placement : l'energie ne discrimine que lorsqu'elle compte.

        Le duty cycle C reste COMMUN a tous les paquets a un instant t : il se
        simplifie dans la comparaison U(D) > U(D_min) et est gere a l'EMISSION
        (offload backhaul pres du quota, _do_radio_tx), ce qui garantit DCVR=0.
        """
        cfg = self.cfg
        age = t - t_gen
        F = max(0.0, (cfg.ttl - age) / cfg.ttl)
        # FreshEnergy : baseline fraicheur+energie SANS terme spatial (R13). Les
        # autres strategies conservent la correlation spatiale.
        S = 0.0 if cfg.strategy == "FreshEnergy" else self.spatial_redundancy(sid, value)
        E = max(0.0, self.sensors[sid].battery_j / cfg.battery_capacity_j)
        miss_cost = 1.0 + cfg.kappa * (1.0 - E)
        if cfg.kappa_toa > 0.0:
            # cout radio d'un miss : un producteur a fort SF (ToA long) coute plus
            # cher a rafraichir (pertinent en deploiement ADR / SF mixtes)
            toa_max = time_on_air(12)
            miss_cost += cfg.kappa_toa * (self.sensors[sid].toa / toa_max)
        return (F ** cfg.alpha) * ((1 - S) ** cfg.beta) * miss_cost

    # --- gestion du cache selon la politique ------------------------------
    def _evict_for(self, new_entry: CacheEntry, t: float) -> bool:
        """Fait de la place si necessaire. Renvoie True si on peut inserer."""
        cfg = self.cfg
        if len(self.cache) < cfg.cache_size:
            return True
        strat = cfg.strategy
        if strat == "LRU":
            self.cache.popitem(last=False)  # plus ancien acces
            return True
        if strat == "LFU":
            victim = min(self.cache.values(), key=lambda e: e.freq)
            del self.cache[victim.sid]
            return True
        if strat in ("Prob", "pCASTING", "CFPC"):
            self.cache.popitem(last=False)  # eviction LRU (conforme aux papiers)
            return True
        if strat == "AdaptiveTTL":
            # least fresh first : evince la donnee la plus proche de l'expiration
            victim = min(self.cache.values(), key=lambda e: (e.t_gen + e.ttl) - t)
            del self.cache[victim.sid]
            return True
        if strat in ("FSEC", "FreshEnergy"):
            u_new = self.fsec_utility(new_entry.sid, new_entry.value, new_entry.t_gen, t)
            victim, u_min = None, float("inf")
            for e in self.cache.values():
                u_c = self.fsec_utility(e.sid, e.value, e.t_gen, t)
                if u_c < u_min:
                    u_min, victim = u_c, e
            if u_new > u_min and victim is not None:
                del self.cache[victim.sid]
                return True
            return False  # nouvelle donnee moins utile -> pas de cache
        return False

    def _try_place(self, sid: int, value: float, t_gen: float, t: float):
        cfg = self.cfg
        strat = cfg.strategy
        if strat == "No-cache" or cfg.cache_size == 0:
            return
        if strat == "Prob" and self.rng.random() > cfg.prob_p:
            return
        if strat == "pCASTING":
            # Hail et al. 2015 : placement probabiliste, probabilite = moyenne de
            # (energie EN, 1-occupation OC, fraicheur residuelle FR) ; eviction LRU.
            if t - t_gen > cfg.ttl:
                return
            EN = max(0.0, self.sensors[sid].battery_j / cfg.battery_capacity_j)
            OC = (len(self.cache) / cfg.cache_size) if cfg.cache_size else 1.0
            FR = max(0.0, (cfg.ttl - (t - t_gen)) / cfg.ttl)
            fu = (EN + (1.0 - OC) + FR) / 3.0
            if self.rng.random() > fu:
                return
        if strat == "CFPC":
            # Amadeo et al. 2020 : les contenus populaires sont caches, les autres
            # seulement s'il reste de la place ; eviction LRU. La FreshnessPeriod
            # etant uniforme ici, la branche de seuil de fraicheur est neutre.
            if t - t_gen > cfg.ttl:
                return
            counts = self.req_count
            avg = (sum(counts.values()) / len(counts)) if counts else 0.0
            popular = counts.get(sid, 0) >= avg
            if not popular and len(self.cache) >= cfg.cache_size:
                return
        if strat in ("FSEC", "FreshEnergy"):
            # filtres durs : expiration et seuil d'utilite.
            # (le duty cycle est applique a l'emission, pas au placement)
            if t - t_gen > cfg.ttl:
                return
            u = self.fsec_utility(sid, value, t_gen, t)
            if u < cfg.u_seuil:
                return
        entry = CacheEntry(sid, value, t_gen, cfg.ttl,
                           self.sensors[sid].x, self.sensors[sid].y)
        if sid in self.cache:
            self.cache[sid] = entry
            self.cache.move_to_end(sid)
            return
        if self._evict_for(entry, t):
            self.cache[sid] = entry
            self.cache.move_to_end(sid)

    # --- traitement d'une requete -----------------------------------------
    def handle_request(self, sid: int, t: float):
        cfg = self.cfg
        self.n_requests += 1
        self.req_count[sid] += 1
        freshness_req = self.rng.uniform(cfg.freshness_req_min, cfg.freshness_req_max)
        aware = self._dc_aware()
        # Politiques conscientes de la fraicheur : elles refusent de servir une
        # donnee trop vieille pour le besoin du consommateur (fraicheur dirigee
        # par le consommateur, cf. Nour et al. 2021) et declenchent un refetch.
        aware_fresh = cfg.strategy in ("FSEC", "AdaptiveTTL", "FreshEnergy")

        def serves(e) -> bool:
            if e is None:
                return False
            age = t - e.t_gen
            if age > e.ttl:               # donnee expiree : invalide pour tous
                return False
            if aware_fresh and age > freshness_req:  # trop vieille pour le besoin
                return False
            return True

        entry = self.cache.get(sid)
        hit = serves(entry)
        semantic = False
        # Hit semantique : propre a FSEC. Une requete pour un capteur non cache
        # peut etre satisfaite par un voisin cache suffisamment proche, dont la
        # valeur est correlee (meme grandeur physique). C'est la traduction de la
        # correlation spatiale au moment du service.
        if not hit and cfg.strategy == "FSEC":
            best_e, best_r = None, 0.0
            for j in self.neighbors[sid]:
                e = self.cache.get(j)
                if not serves(e):
                    continue
                d = math.dist((self.sensors[sid].x, self.sensors[sid].y),
                              (self.sensors[j].x, self.sensors[j].y))
                r = math.exp(-(d ** 2) / (2 * cfg.sigma_d ** 2))
                if r > best_r:
                    best_r, best_e = r, e
            if best_e is not None and best_r >= cfg.sem_threshold:
                # Erreur d'approximation semantique : valeur servie (voisin B) vs
                # vraie valeur (champ) du capteur demande A, sans mutation d'etat.
                err = abs(self._field_value(self.sensors[sid], t) - best_e.value)
                if err <= cfg.eps_max:          # eps_max = inf par defaut -> toujours accepte
                    hit = True
                    semantic = True
                    entry = best_e
                    self._last_sem_err = err
                else:
                    self.n_sem_rejected += 1     # rejete : redevient un vrai miss

        if hit:
            # HIT (exact ou semantique) : servi depuis le Content Store via le
            # backhaul IP. Pas d'emission radio, donc aucun duty cycle consomme.
            entry.freq += 1
            self.cache.move_to_end(entry.sid)
            self.n_hits += 1
            if semantic:
                self.n_sem_hits += 1
                self.sem_errors.append(self._last_sem_err)
            else:
                self.n_exact_hits += 1
            # Un hit est FRAIS s'il satisfait l'exigence de fraicheur du
            # consommateur (age de la donnee servie <= besoin exprime).
            age = t - entry.t_gen
            if age <= freshness_req:
                self.n_fresh_hits += 1
            self.useful_bits += PAYLOAD_BYTES * 8
            self.latency_sum += 0.05  # latence locale faible (s)
        else:
            # MISS : recuperation de la donnee aupres du capteur par la radio LoRa.
            #  - le capteur emet (uplink, energie capteur), pertes/retransmissions
            #    possibles ; la passerelle emet la reponse (downlink), soumise au
            #    duty cycle, avec pertes possibles. Canal parfait par defaut.
            s = self.sensors[sid]
            if not s.alive:
                return
            value = self.sensor_value(s, t)
            # 1) uplink capteur -> passerelle (avec pertes / retransmissions)
            up_ok = False
            for attempt in range(cfg.max_retx + 1):
                self._sensor_uplink(s, t)
                self._chan_add(t, s.toa)
                if attempt > 0:
                    self.n_retx += 1
                    self.latency_sum += 0.5
                if not self._radio_lost(s.toa):
                    up_ok = True
                    break
            if not up_ok:
                self.n_tx_lost += 1
                self.latency_sum += 0.8    # donnee non recuperee : requete non servie
                return
            # 2) downlink passerelle -> consommateur (duty cycle + pertes)
            emitted = self._do_radio_tx(t, aware, s.toa)   # offload backhaul si quota epuise (et aware)
            if emitted:
                self._chan_add(t, s.toa)
                for _ in range(cfg.max_retx):
                    if not self._radio_lost(s.toa):
                        break
                    self._do_radio_tx(t, aware, s.toa)
                    self._chan_add(t, s.toa)
                    self.n_retx += 1
                    self.latency_sum += 0.5
            else:
                self.n_backhaul += 1   # miss servi par le backhaul (reponse differee)
            self.useful_bits += PAYLOAD_BYTES * 8
            self.latency_sum += 0.5 if emitted else 0.8  # offload = latence accrue
            self._try_place(sid, value, s.last_gen_time, t)

    # --- loi d'arrivee des requetes ---------------------------------------
    def _next_interval(self) -> float:
        """Intervalle jusqu'a la prochaine requete. Poisson par defaut (identique
        a l'historique). Modes 'periodic' (deterministe) et 'bursty' pour Exp E."""
        cfg = self.cfg
        if cfg.arrival == "periodic":
            return 1.0 / cfg.req_rate
        if cfg.arrival == "bursty":
            # alternance rafale (intense) / creux, meme debit moyen approximatif
            if self.rng.random() < cfg.burst_duty:
                return self.rng.expovariate(cfg.req_rate * cfg.burst_factor)
            return self.rng.expovariate(cfg.req_rate * cfg.burst_duty)
        return self.rng.expovariate(cfg.req_rate)  # poisson (defaut)

    # --- boucle principale -------------------------------------------------
    def run(self) -> dict:
        cfg = self.cfg
        t = 0.0
        # arrivee des requetes (Poisson par defaut)
        while t < cfg.sim_time:
            t += self._next_interval()
            if t >= cfg.sim_time:
                break
            sid = self.rng.choices(range(cfg.n_sensors), weights=self.pop_weights)[0]
            self.handle_request(sid, t)
        return self.metrics()

    # --- metriques ---------------------------------------------------------
    def metrics(self) -> dict:
        chr_ = 100.0 * self.n_hits / self.n_requests if self.n_requests else 0.0
        fhr = 100.0 * self.n_fresh_hits / self.n_hits if self.n_hits else 0.0
        dcvr = 100.0 * self.n_dc_violations / self.n_radio_tx if self.n_radio_tx else 0.0
        total_energy = self.energy_sensors_j + self.energy_gateway_j
        eub = (total_energy * 1000.0) / self.useful_bits if self.useful_bits else 0.0  # mJ/bit
        lifetime = self.first_death if self.first_death is not None else self.cfg.sim_time
        latency = 1000.0 * self.latency_sum / self.n_requests if self.n_requests else 0.0  # ms
        # --- metriques d'instrumentation (revision PEMWN) ---
        chr_exact = 100.0 * self.n_exact_hits / self.n_requests if self.n_requests else 0.0
        chr_sem = 100.0 * self.n_sem_hits / self.n_requests if self.n_requests else 0.0
        ne = len(self.sem_errors)
        if ne:
            mae = sum(self.sem_errors) / ne
            rmse = math.sqrt(sum(e * e for e in self.sem_errors) / ne)
            srt = sorted(self.sem_errors)
            p95 = srt[min(ne - 1, max(0, int(math.ceil(0.95 * ne)) - 1))]
            emax = srt[-1]
        else:
            mae = rmse = p95 = emax = 0.0
        return {
            "strategy": self.cfg.strategy,
            "cache_size": self.cfg.cache_size,
            "sf": self.cfg.sf,
            "battery_frac": self.cfg.battery_init_frac,
            "CHR": chr_,
            "FHR": fhr,
            "EUB": eub,
            "DCVR": dcvr,
            "lifetime": lifetime,
            "latency_ms": latency,
            "n_requests": self.n_requests,
            # instrumentation
            "CHR_exact": chr_exact,
            "CHR_sem": chr_sem,
            "n_backhaul": self.n_backhaul,
            "n_sem_rejected": self.n_sem_rejected,
            "sem_mae": mae,
            "sem_rmse": rmse,
            "sem_p95": p95,
            "sem_max": emax,
            "n_tx_lost": self.n_tx_lost,
            "n_retx": self.n_retx,
        }


def run_one(cfg: Config) -> dict:
    return Simulator(cfg).run()


if __name__ == "__main__":
    # demonstration rapide
    for strat in ["No-cache", "LRU", "LFU", "Prob", "AdaptiveTTL", "pCASTING", "CFPC", "FSEC"]:
        c = Config(strategy=strat, seed=1)
        print(run_one(c))
