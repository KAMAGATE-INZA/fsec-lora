# FSEC-LoRa — code de simulation et d'analyse

Dépôt reproductible accompagnant le mémoire *« Stratégies de Cache Distribué
pour ICN over LoRaWAN »*. Il contient deux implémentations complémentaires de la
stratégie **FSEC-LoRa** et de ses politiques de référence :

1. un **prototype Python** autonome, qui produit les résultats du chapitre
   Résultats (rapide à exécuter, sans dépendance lourde) ;
2. une **implémentation ndnSIM (C++)**, pour validation dans l'environnement de
   référence de la communauté NDN (dossier `ndnSIM/`).

## Arborescence

```
simulation/
├── fsec_sim.py          # cœur du simulateur (modèle, politiques, métriques)
├── run_campaign.py      # campagne reproductible et reprenable (parallèle)
├── analyze.py           # agrégation, figures (IC 95 %), ANOVA, Pearson
├── results.csv          # 1875 exécutions (généré)
├── figures/             # figures PNG + PDF (générées)
└── ndnSIM/              # implémentation C++ pour ndnSIM (voir ndnSIM/README.md)
```

## Prérequis (prototype Python)

```bash
pip install numpy pandas matplotlib
# (scipy n'est PAS requis : ANOVA et Pearson sont implémentés dans analyze.py)
```

## Reproduire les résultats

```bash
# 1. Démonstration rapide : compare les 6 stratégies sur un scénario
python3 fsec_sim.py

# 2. Campagne complète (reprenable : relancer jusqu'à « Campagne terminee »)
python3 run_campaign.py 60     # 60 = budget en secondes par passe

# 3. Figures + statistiques (écrit dans figures/ et imprime ANOVA/Pearson)
python3 analyze.py
```

La campagne couvre la comparaison des stratégies, le balayage de la taille du
cache, du Spreading Factor et du niveau de batterie, ainsi qu'une recherche en
grille sur les exposants de la fonction d'utilité. Chaque configuration est
rejouée 30 fois (graines distinctes) ; les figures portent les intervalles de
confiance à 95 %.

## Modèle, en bref

- Topologie LoRaWAN en étoile : capteurs (producteurs) → passerelle (cache) →
  serveur (consommateur).
- Données transitoires (TTL), corrélation spatiale (champ latent par cluster).
- **Hit servi par le backhaul IP** (pas de duty cycle) ; **miss récupéré par la
  radio** (duty cycle + énergie capteur).
- FSEC-LoRa : score `U = F^α (1−S)^β (1 + κ(1−E))` pour le placement et l'éviction ; le
  duty cycle `C` se simplifie dans la décision de placement et est appliqué à
  l'émission (offload near-quota → DCVR = 0) ; corrélation spatiale réalisée par
  des **hits sémantiques** (un voisin proche sert la requête) ; **fraîcheur
  dirigée par le consommateur** (on ne sert pas une donnée trop vieille).

Voir les commentaires de `fsec_sim.py` pour le détail des hypothèses.

## Licence

Code publié dans une démarche de science ouverte. Réutilisation et reproduction
encouragées avec citation du mémoire.
