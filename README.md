# FSEC-LoRa — code de simulation et d'analyse

Dépôt reproductible de la stratégie de cache **FSEC-LoRa** (ICN over LoRaWAN) et de
ses politiques de référence. Deux implémentations :

1. un **prototype Python** autonome qui produit tous les résultats (rapide, sans
   dépendance lourde) ;
2. une **implémentation ndnSIM (C++)** pour validation dans l'environnement de
   référence NDN (dossier `ndnSIM/`).

## Arborescence

```
simulation/
├── fsec_sim.py                # cœur : modèle, TOUTES les politiques, métriques, canal radio
├── run_campaign.py            # campagne principale reproductible (parallèle, reprenable)
├── analyze.py                 # agrégation, figures (IC 95 %), ANOVA, post-hoc (Welch+Holm), tailles d'effet
├── real_trace.py              # rejoue de vraies traces de capteurs (Intel Lab, Melbourne)
├── exp_A_fair_dc.py           # Exp A — comparaison à duty-cycle égal
├── exp_B_semantic_error.py    # Exp B — erreur d'approximation sémantique
├── exp_C_correlation.py       # Exp C — sensibilité à la corrélation spatiale
├── exp_D_params_split.py      # Exp D — réglage sans fuite (train/val/test)
├── exp_E_query_patterns.py    # Exp E — sensibilité aux motifs de trafic
├── exp_F_radio_reliability.py # Exp F — fiabilité radio (pertes, collisions, retransmissions)
├── exp_adr.py / exp_robustesse.py / exp_modele.py   # études complémentaires
├── rev/                       # sorties CSV des expériences de révision + notes de résultats
├── data/                      # jeux de données réels (non versionnés, voir plus bas)
├── figures/                   # figures PNG + PDF (générées)
└── ndnSIM/                    # implémentation C++ (voir ndnSIM/README.md)
```

## Où se trouve chaque politique dans le code

Toutes les politiques vivent dans `fsec_sim.py`, dans deux méthodes : `_try_place`
(décision de placement) et `_evict_for` (décision d'éviction). Numéros de ligne
indicatifs (version courante).

| Politique | Placement | Éviction | Référence |
|---|---|---|---|
| No-cache | `_try_place` L423 | — | pire cas |
| LRU | insertion générique | `_evict_for` L392 (accès le plus ancien) | standard |
| LFU | insertion générique | `_evict_for` L395 (compteur d'accès min) | standard |
| Prob (p=0.5) | `_try_place` L425 (tirage) | LRU (L399) | ProbCache |
| Adaptive-TTL | insertion générique | `_evict_for` L402 (least fresh first) | fraîcheur seule |
| pCASTING | `_try_place` L427 (proba EN/OC/FR) | LRU (L399) | Hail et al. 2015 |
| CFPC | `_try_place` L438 (popularité) | LRU (L399) | Amadeo et al. 2020 |
| FreshEnergy | `_try_place` L449 (utilité sans terme spatial) | `_evict_for` L407 | baseline R13 |
| **FSEC-LoRa** | `_try_place` L449 (seuil d'utilité) | `_evict_for` L407 (utilité min) | ce travail |

Mécanismes clés (aussi dans `fsec_sim.py`) :

- **Score d'utilité FSEC** `U = F^α (1−S)^β (1+κ(1−E))` : `fsec_utility` (L352).
- **Corrélation spatiale** (noyau gaussien) : `spatial_redundancy` (L336).
- **Hit sémantique** (un voisin corrélé sert la requête) : dans `handle_request` (L468).
- **Règle d'émission / duty cycle** : `_do_radio_tx` (L282) et `_dc_aware` (L264).
  Le duty cycle **n'entre pas dans le score** ; il est géré à l'émission (délégation
  au backhaul près du quota), ce qui donne un DCVR nul. Le drapeau `dc_enforce_all`
  applique cette règle à **toutes** les stratégies (comparaison équitable, Exp A).
- **Canal radio stochastique** (PER + collisions) : `_radio_lost` (L310), activé par
  `per_base` / `collision` / `max_retx` (Exp F).
- **Time-on-Air LoRa** : `time_on_air` (L52).

## Prérequis (prototype Python)

```bash
pip install numpy pandas matplotlib
# SciPy n'est PAS requis : ANOVA, Welch, Holm et tailles d'effet sont
# implémentés à la main dans analyze.py.
```

## Reproduire les résultats

```bash
# Démonstration rapide (compare les stratégies sur un scénario)
python3 fsec_sim.py

# Campagne principale (reprenable : relancer jusqu'à « Campagne terminee »)
python3 run_campaign.py 60          # 60 = budget en secondes par passe

# Figures + statistiques (ANOVA, post-hoc Welch+Holm, tailles d'effet)
python3 analyze.py

# Expériences de révision (chacune écrit un CSV dans rev/)
python3 exp_A_fair_dc.py 30         # duty-cycle égal
python3 exp_B_semantic_error.py 30  # erreur sémantique
python3 exp_C_correlation.py 20     # corrélation spatiale
python3 exp_D_params_split.py       # réglage sans fuite
python3 exp_E_query_patterns.py 20  # motifs de trafic
python3 exp_F_radio_reliability.py 20  # fiabilité radio
```

Non-régression : tous les ajouts de la révision ont des valeurs par défaut neutres.
En rejouant une configuration déjà publiée, on retrouve exactement les chiffres de
`results.csv` (écart nul).

## Validation sur données réelles

```bash
# Intel Berkeley Lab (dense, intérieur)
python3 real_trace.py intel data/data.txt data/mote_locs.txt temperature
# City of Melbourne Microclimate (épars, extérieur)
python3 real_trace.py melbourne data/microclimate-sensors-data.csv data/microclimate-sensor-locations.csv
```

Les jeux de données réels sont **volumineux et non versionnés** (ignorés par git).
Instructions de téléchargement et détail des résultats : `rev/README_traces_reelles.md`
et `rev/real_intel_results.md`.

## Modèle, en bref

Topologie LoRaWAN en étoile : capteurs (producteurs) → passerelle (cache) → serveur
(consommateur). Données transitoires (TTL), corrélation spatiale (champ latent).
Un **hit** est servi par le backhaul IP (pas de duty cycle) ; un **miss** est
récupéré par la radio (duty cycle + énergie capteur, pertes possibles). FSEC-LoRa
décide placement et éviction par le même score d'utilité, sert la corrélation par
des **hits sémantiques**, et applique la **fraîcheur dirigée par le consommateur**
(on ne sert pas une donnée trop vieille pour le besoin exprimé).

## Licence

Code publié dans une démarche de science ouverte. Réutilisation et reproduction
encouragées avec citation.
