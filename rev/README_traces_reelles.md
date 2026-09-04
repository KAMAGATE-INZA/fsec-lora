# Validation sur traces réelles (R8 / Exp 5.4)

L'adaptateur `simulation/real_trace.py` rejoue un jeu de données de capteurs réels
géolocalisés à la place du champ synthétique, pour vérifier que la corrélation
spatiale existe dans de vraies mesures et que l'avantage de FSEC-LoRa tient.

Ce n'est **pas** un déploiement matériel : on rejoue des données déjà enregistrées.

Le simulateur canonique n'est pas modifié : `real_trace.py` sous-classe `Simulator`
et redéfinit uniquement la topologie (positions réelles) et la lecture de valeur.
Les paramètres (TTL, exigence de fraîcheur, cache, σ_d) sont **calés automatiquement
sur la cadence et l'échelle du jeu de données**, pour une comparaison équitable.

## Test immédiat (sans fichier)
```
python3 real_trace.py
```
Utilise un repli synthétique géolocalisé et imprime FSEC vs LRU
(CHR, part sémantique, FHR, EUB, erreur sémantique MAE/p95). Sert à vérifier le
pipeline.

## Jeu de données 1 (recommandé) : Intel Berkeley Lab
Dense, intérieur (salle 40 × 30 m), 54 capteurs, température/humidité toutes les
31 s. Régime de **forte corrélation spatiale**, favorable à FSEC.

1. Télécharger depuis http://db.csail.mit.edu/labdata/labdata.html :
   - `data.txt.gz` (les relevés) puis décompresser : `gunzip data.txt.gz`
   - le fichier des positions des motes (`moteid  x  y`), à enregistrer en `mote_locs.txt`
2. Placer les deux dans `simulation/data/`.
3. Lancer :
```
python3 real_trace.py intel data/data.txt data/mote_locs.txt temperature
```
(remplacer `temperature` par `humidity` pour l'autre grandeur.)

## Jeu de données 2 (contraste extérieur épars) : City of Melbourne Microclimate
Vrais capteurs urbains **extérieurs**, dispersés dans la ville (dizaines à centaines
de mètres d'écart, microclimats) : régime de **corrélation plus faible**, contraste
avec l'Intel Lab dense. Un chargeur dédié (`load_melbourne`) fusionne lectures et
positions et projette lat/lon en mètres, avec auto-détection des colonnes.

1. Télécharger les **deux** fichiers CSV depuis le portail open data de Melbourne :
   - Lectures : dataset « Microclimate Sensor Readings »
     `https://data.melbourne.vic.gov.au/api/v2/catalog/datasets/microclimate-sensor-readings/exports/csv?delimiter=,`
     à enregistrer en `simulation/data/melbourne_readings.csv`
   - Positions : dataset « Microclimate Sensor Locations »
     `https://data.melbourne.vic.gov.au/api/v2/catalog/datasets/microclimate-sensor-locations/exports/csv?delimiter=,`
     à enregistrer en `simulation/data/melbourne_locations.csv`
2. Lancer :
```
python3 real_trace.py melbourne data/melbourne_readings.csv data/melbourne_locations.csv
```

Résultat attendu (honnête) : corrélation plus faible qu'en intérieur, donc avantage
CHR de FSEC réduit (comme le régime uniforme de l'Exp C et σ_d=3 m sur Intel), mais
FHR et EUB conservés.

### Variante : n'importe quel CSV `sid,x,y,t,value`
```
python3 real_trace.py csv chemin_du_fichier.csv
```

## Ce qu'on regarde
- CHR total et **part sémantique** : l'avantage vient-il des hits sémantiques ?
- FHR : FSEC doit rester à 100 % ; les baselines servent du périmé.
- EUB : FSEC doit rester plus bas.
- **Erreur sémantique** (MAE, p95) : la substitution voisine est-elle fidèle sur de
  vraies données ?
- Faire varier `sigma_d` (argument de `run_trace`) pour retrouver la courbe de
  l'Exp C sur données réelles : l'avantage doit croître avec la corrélation.

## Note d'honnêteté (à garder dans l'article)
Sur un jeu **dense** (Intel Lab), on s'attend à un avantage marqué de FSEC ; sur un
jeu **épars**, l'avantage CHR peut se réduire (comme en déploiement uniforme de
l'Exp C), tandis que FHR et EUB tiennent. C'est le résultat attendu et il faut le
rapporter tel quel.
