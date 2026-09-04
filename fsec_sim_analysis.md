# Analyse de `fsec_sim.py`

Ce fichier décrit l'implémentation des politiques de cache dans `fsec_sim.py` et fournit un diagramme UML des classes présentes.

## Classes dans `fsec_sim.py`

### `Config`
- Dataclass contenant tous les paramètres de la simulation.
- Champs importants :
  - `strategy`: nom de la politique (`No-cache`, `LRU`, `LFU`, `Prob`, `AdaptiveTTL`, `FSEC`, `pCASTING`, `CFPC`).
  - `cache_size`, `sim_time`, `req_rate`, `ttl`, `sf`, `dc_max`, `dc_window`
  - Paramètres FSEC : `alpha`, `beta`, `kappa`, `kappa_toa`, `u_seuil`, `c_min`, `sigma_d`, `sigma_v`, `sem_threshold`
  - Paramètres de robustesse / probabilité : `prob_p`, `zipf_s`, `battery_init_frac`, `battery_capacity_j`

### `Sensor`
- Représente un capteur.
- Attributs principaux : `sid`, position `(x, y)`, `cluster`, `battery_j`, `sf`, `toa`, `last_value`, `last_gen_time`, `alive`, `death_time`.

### `CacheEntry`
- Représente une entrée dans le cache.
- Attributs : `sid`, `value`, `t_gen`, `ttl`, position `(x, y)`, `freq`.
- `freq` est utilisé par LFU.

### `Simulator`
- Cœur du simulateur.
- Initialise la topologie, la popularité, le cache, les compteurs et les métriques.
- Stocke :
  - `cfg: Config`
  - `rng`: générateur aléatoire
  - `sensors: list[Sensor]`
  - `cache: OrderedDict[int, CacheEntry]`
  - `toa`, `tx_times`, `dc_used`
  - `pop_weights`, `_pop_total`
  - `req_count` et métriques
- Méthodes principales :
  - `_build_topology`, `_build_popularity`, `reset_metrics`
  - `sensor_value`, `_dc_refresh`, `dc_available`, `_do_radio_tx`, `_sensor_uplink`
  - `spatial_redundancy`, `fsec_utility`
  - `_evict_for`, `_try_place`, `handle_request`, `run`, `metrics`

## Implémentation de chaque politique

### 1. `No-cache`
- Pas de placement dans le cache.
- Dans `_try_place`, si `strategy == "No-cache"` ou `cache_size == 0`, la fonction retourne immédiatement.
- Le cache reste toujours vide et chaque requête non satisfaite localement provoque un MISS.

### 2. `LRU`
- Éviction : dans `_evict_for`, si le cache est plein, on supprime la plus ancienne entrée avec `self.cache.popitem(last=False)`.
- Placement : l'entrée est insérée normalement si place disponible.
- Le cache est aussi mis à jour lors des hits avec `self.cache.move_to_end(entry.sid)`.

### 3. `LFU`
- Éviction : dans `_evict_for`, si le cache est plein, on enlève l'entrée ayant la fréquence `freq` minimale :
  - `victim = min(self.cache.values(), key=lambda e: e.freq)`
  - `del self.cache[victim.sid]`
- L’utilisation de `freq` se fait sur les hits dans `handle_request`.

### 4. `Prob`
- Placement : dans `_try_place`, la mise en cache est faite avec probabilité `prob_p`.
- Si `self.rng.random() > cfg.prob_p`: retour sans cache.
- Éviction : si le cache est plein, le script utilise LRU (`self.cache.popitem(last=False)`).

### 5. `AdaptiveTTL`
- Éviction : dans `_evict_for`, en cas de nécessité, on choisit la donnée la moins fraîche :
  - `victim = min(self.cache.values(), key=lambda e: (e.t_gen + e.ttl) - t)`
- Placement : ne cache pas les entrées expirées (`t - t_gen > cfg.ttl`).
- Hit aware fresher : dans `handle_request`, `aware_fresh` est vrai pour `AdaptiveTTL`, de sorte qu’une donnée trop vieille peut être refusée même si elle est en cache.

### 6. `pCASTING`
- Placement probabiliste basé sur trois facteurs :
  - `EN`: énergie restante du capteur
  - `OC`: occupation du cache
  - `FR`: fraîcheur résiduelle
- Calcul du score `fu = (EN + (1.0 - OC) + FR) / 3.0`
- Cache l’entrée si `self.rng.random() <= fu`.
- Éviction : LRU si le cache est plein.

### 7. `CFPC`
- Placement basé sur popularité historique.
- Si la donnée n’est pas populaire et le cache plein, elle n’est pas placée.
- Popularité : `counts[sid] >= avg`, avec `avg` calculé sur `self.req_count`.
- Éviction : LRU si le cache est plein.
- Note : si `t - t_gen > cfg.ttl`, l’entrée n’est pas placée.

### 8. `FSEC`
- Placement sélectif et utilité basée sur un score.
- Dans `_try_place`, l’entrée est rejetée si :
  - elle est expirée (`t - t_gen > cfg.ttl`)
  - son utilité `u` est inférieure à `cfg.u_seuil`
- Egalement, l’émission radio est gérée avec conscience du duty cycle dans `_do_radio_tx` :
  - si `aware=True` et l’émission dépasse le budget, le paquet n’est pas envoyé par radio et n’entraîne pas de violation.
- Utilité dans `fsec_utility` :
  - `F = max(0, (ttl - age) / ttl)`
  - `S = spatial_redundancy(sid, value)`
  - `E = batterie restante / capacité`
  - `miss_cost = 1 + kappa * (1 - E)`
  - `U = F^alpha * (1 - S)^beta * miss_cost`
- Éviction : compare l’utilité de la nouvelle entrée avec la plus faible utilité du cache.
- Hit sémantique : si l’objet demandé n’est pas en cache, FSEC peut servir un voisin suffisamment proche dont la corrélation dépasse `sem_threshold`.

## Où se trouvent les politiques dans le code

- `_evict_for`: logique d’éviction selon la stratégie pour faire place à une nouvelle entrée.
- `_try_place`: filtre et placement selon la stratégie.
- `handle_request`: hits, hits sémantiques, MISS, radio, rafraîchissement du cache, et mise à jour des métriques.

## Diagramme UML des classes

```mermaid
classDiagram
    Config <|-- Simulator
    Simulator o-- Sensor : sensors
    Simulator o-- CacheEntry : cache entries
    Simulator --> Config : cfg
    Simulator --> "OrderedDict[int, CacheEntry]" : cache
    Simulator --> "list[Sensor]" : sensors
    Simulator --> "dict[int, list[int]]" : neighbors
    Simulator --> "dict[int, int]" : req_count

    class Config {
        +int n_sensors
        +float area
        +int n_clusters
        +int cache_size
        +str strategy
        +float sim_time
        +float req_rate
        +float ttl
        +float gen_period
        +int sf
        +float dc_max
        +float dc_window
        +float battery_init_frac
        +float battery_capacity_j
        +float alpha
        +float beta
        +float kappa
        +float kappa_toa
        +bool adr
        +float gamma
        +float lam
        +float u_seuil
        +float c_min
        +float sigma_d
        +float sigma_v
        +float sem_threshold
        +float prob_p
        +float freshness_req_min
        +float freshness_req_max
        +float zipf_s
        +int seed
    }

    class Sensor {
        +int sid
        +float x
        +float y
        +int cluster
        +float battery_j
        +int sf
        +float toa
        +float last_value
        +float last_gen_time
        +bool alive
        +Optional[float] death_time
    }

    class CacheEntry {
        +int sid
        +float value
        +float t_gen
        +float ttl
        +float x
        +float y
        +int freq
    }

    class Simulator {
        +Config cfg
        +random.Random rng
        +list[Sensor] sensors
        +OrderedDict[int, CacheEntry] cache
        +float toa
        +list[float] tx_times
        +float dc_used
        +list[float] pop_weights
        +float _pop_total
        +int n_requests
        +int n_hits
        +int n_fresh_hits
        +int n_radio_tx
        +int n_dc_violations
        +int useful_bits
        +float energy_sensors_j
        +float energy_gateway_j
        +float latency_sum
        +Optional[float] first_death
        +dict[int, int] req_count
        +dict[int, list[int]] neighbors
        +list[float] cluster_base
        +dict[str, float] popularity weights
        +dict[str, float] metrics
        +void _build_topology()
        +void _build_popularity()
        +void reset_metrics()
        +float sensor_value(Sensor, float)
        +void _dc_refresh(float)
        +float dc_available(float)
        +bool _do_radio_tx(float, bool, float)
        +void _sensor_uplink(Sensor, float)
        +float spatial_redundancy(int, float)
        +float fsec_utility(int, float, float, float)
        +bool _evict_for(CacheEntry, float)
        +void _try_place(int, float, float, float)
        +void handle_request(int, float)
        +dict run()
        +dict metrics()
    }
```

## Résumé rapide des politiques

- `No-cache`: pas de cache, toutes les requêtes non satisfaites deviennent MISS.
- `LRU`: eviction du plus ancien accès.
- `LFU`: eviction du moins fréquent.
- `Prob`: cache probabiliste + eviction LRU.
- `AdaptiveTTL`: éviction selon la fraîcheur restante.
- `pCASTING`: placement probabiliste selon énergie, occupation, fraîcheur.
- `CFPC`: placement conditionné à la popularité.
- `FSEC`: placement basé sur utilité, éviction par utilité minimale, hit sémantique et gestion du duty cycle.

---

Fichier créé : `fsec_sim_analysis.md`
