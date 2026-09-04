# Validation sur données réelles — Intel Berkeley Lab (R8)

Jeu : Intel Berkeley Lab, relevés réels de température, 43 capteurs actifs dans une
salle de 40×30 m, cadence ≈ 33 s. Fenêtre de 2 h autour du temps médian, valeurs
aberrantes filtrées ([-10 ; 60] °C). Paramètres auto-calibrés : TTL 198 s, cache 21.
Moyennes sur 5 graines. Commande :

```
python3 real_trace.py intel data/data.txt data/mote_locs.txt temperature
```

## Balayage σ_d (FSEC vs LRU)

| σ_d (m) | FSEC CHR | dont sém. | FHR | EUB | erreur sém. MAE | erreur sém. p95 |
|---|---|---|---|---|---|---|
| 3  | 62,0 | 5,6  | 100 | 0,0208 | 0,31 | 0,38 |
| 5  | 86,0 | 41,5 | 100 | 0,0092 | 0,30 | 0,67 |
| 8  | 91,2 | 55,3 | 100 | 0,0065 | 0,33 | 1,00 |
| 12 | 94,5 | 66,4 | 100 | 0,0047 | 0,39 | 1,07 |
| 20 | 97,5 | 81,8 | 100 | 0,0027 | 0,47 | 1,18 |
| LRU | 66,5 | 0,0 | 60,0 | 0,0351 | — | — |

## Enseignements
1. L'avantage de FSEC tient sur de vraies données : à σ_d = 8 m (auto), CHR 91 vs 66,
   FHR 100 vs 60, EUB 5× plus bas.
2. L'avantage CHR croît avec σ_d (comme l'Exp C synthétique) et repasse sous LRU à
   σ_d = 3 m : borne honnête confirmée sur du réel.
3. L'erreur d'approximation sémantique est faible et bornée (MAE ≈ 0,3 °C, p95 < 1,2 °C
   sur toute la plage) : la substitution spatiale est fidèle sur de vraies mesures
   d'intérieur. Cela valide empiriquement l'hypothèse centrale du travail.

---

# Contraste extérieur épars — City of Melbourne Microclimate (R8, 2/2)

Jeu : capteurs urbains extérieurs réels (température), 11 capteurs dispersés sur
~2,7 × 3,0 km, cadence ≈ 15 min. Positions embarquées (LatLong) dans le fichier de
relevés. Cache réduit à 6 (pression d'éviction), 5 graines. Commande :

```
python3 real_trace.py melbourne data/microclimate-sensors-data.csv data/microclimate-sensor-locations.csv
```

## Balayage σ_d (échelle du déploiement, cache = 6)

| σ_d (m) | FSEC CHR | dont sém. | FHR | EUB | erreur sém. MAE | LRU CHR | LRU FHR | LRU EUB |
|---|---|---|---|---|---|---|---|---|
| 200  | 62,9 | 0,0  | 100 | 0,0180 | — | 66,4 | 98,0 | 0,0300 |
| 400  | 84,3 | 22,1 | 100 | 0,0096 | 0,58 | 66,4 | 98,0 | 0,0300 |
| 600  | 97,8 | 44,2 | 100 | 0,0020 | 0,41 | 66,4 | 98,0 | 0,0300 |
| 1000 | 97,8 | 48,4 | 100 | 0,0020 | 0,40 | 66,4 | 98,0 | 0,0300 |
| 1500 | 97,8 | 59,4 | 100 | 0,0020 | 0,43 | 66,4 | 98,0 | 0,0300 |

## Enseignements (contraste avec l'intérieur dense)
1. En extérieur, les capteurs sont à des **centaines de mètres** l'un de l'autre :
   à noyau étroit (σ_d = 200 m), FSEC n'a **aucun hit sémantique** et repasse sous
   LRU (62,9 vs 66,4). La borne honnête est confirmée sur du réel extérieur.
2. La corrélation existe quand même, mais à une **échelle plus grande** : en élargissant
   σ_d à l'échelle du déploiement (≥ 400–600 m), FSEC domine à nouveau (97,8 vs 66,4),
   avec FHR 100 % (vs 98 %) et EUB 15× plus bas.
3. L'erreur d'approximation reste **modérée** (MAE ≈ 0,4–0,6 °C) : la température
   extérieure varie doucement même sur le km.

Conclusion : les deux jeux réels **encadrent les régimes**. Dense intérieur (Intel) :
forte corrélation, FSEC domine largement, erreur < 1 °C. Épars extérieur (Melbourne) :
corrélation à plus grande échelle, avantage conditionné à un σ_d adapté ; FHR et EUB
tiennent toujours.
