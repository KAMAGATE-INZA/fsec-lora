# FSEC-LoRa sous ndnSIM (code C++)

Ce dossier contient l'implémentation C++ de la stratégie de cache **FSEC-LoRa**
pour **ndnSIM** (basé sur ns-3 / NFD). Il est destiné à valider, dans
l'environnement de référence de la communauté NDN, les résultats obtenus avec le
prototype Python (`../fsec_sim.py`).

> **Avertissement honnête.** Ce code n'a pas pu être compilé dans
> l'environnement de préparation du mémoire (ndnSIM est une pile lourde qui
> demande une installation complète de ns-3). Il est écrit au plus près de l'API
> réelle de `nfd::cs::Policy` (la même que la `LruPolicy` native), mais les
> signatures et les chemins d'en-têtes **varient selon la version**. Il faut
> donc le **compiler et l'adapter** sur la machine cible. Les métriques publiées
> au chapitre Résultats proviennent du prototype Python ; cette implémentation
> ndnSIM sert à les confirmer et constitue la base du dépôt open-source.

## Fichiers

| Fichier | Rôle |
|---|---|
| `lora-constraints.hpp` | Time-on-Air, `DutyCycleTracker`, `LoraContext` (positions, énergie, voisinage, noyau spatial). |
| `fsec-lora-policy.hpp/.cpp` | Politique de Content Store `nfd::cs::fsec::FsecLoRaPolicy` (placement + remplacement unifiés par `U = F^α (1−S)^β (1 + κ(1−E))`). |
| `fsec-scenario.cpp` | Scénario ns-3 modèle (capteurs → passerelle → serveur). |

## Conventions

- **Nommage** : chaque donnée est nommée `/fsec/<sensorId>/<seq>`.
- **Contenu** : la charge utile encode `"value;tgen"` (valeur mesurée et instant
  de génération en secondes simulées).
- **TTL** : porté par la `FreshnessPeriod` du paquet Data.
- La position `(x,y)` et l'énergie du capteur sont lues dans `LoraContext` via
  `sensorId` (peuplé par le scénario).

## Intégration dans l'arbre ndnSIM

1. Copier `lora-constraints.hpp`, `fsec-lora-policy.hpp` et `.cpp` dans le module
   NFD de ndnSIM, par exemple :
   `ns-3/src/ndnSIM/NFD/daemon/table/`.
2. Ajouter les fichiers à la compilation. Selon ta version, soit ils sont
   ramassés automatiquement par le `wscript` du module NFD, soit il faut les
   déclarer. Vérifie après un `./waf configure`.
3. La macro `NFD_REGISTER_CS_POLICY(FsecLoRaPolicy)` enregistre la politique sous
   le nom `"fsec-lora"`. On la sélectionne ensuite dans le scénario par
   `ndnHelper.setPolicy("nfd::cs::fsec-lora")`.

## Compilation et exécution

```bash
# depuis la racine ns-3
cp simulation/ndnSIM/*.hpp simulation/ndnSIM/*.cpp scratch/      # variante simple
./waf configure --enable-examples
./waf --run "fsec-scenario --nSensors=200 --cacheSize=100 --simTime=3600"
```

(La variante « tout dans `scratch/` » est la plus rapide pour tester ; pour une
intégration propre, place la politique dans le module NFD comme indiqué plus
haut et garde le scénario dans `scratch/`.)

## Métriques

- **CHR** : se déduit de `cs-trace.txt` (`CacheHits / (CacheHits + CacheMisses)`).
- **Latence** : `app-delay-trace.txt`.
- **FHR, EUB, DCVR** : demandent des traceurs personnalisés. Le `FHR` se calcule
  en comparant l'âge de la donnée servie à l'exigence de fraîcheur ; l'`EUB`
  agrège l'énergie via `LoraContext` (chaque uplink capteur décrémente la
  batterie) ; le `DCVR` se lit sur le `DutyCycleTracker`. Le squelette de ces
  traceurs est laissé en exercice d'intégration, la logique étant identique à
  celle du prototype Python (`../fsec_sim.py`), qui sert de référence.

## Notes de conception

- **Le duty cycle ne figure pas dans le score de placement.** Comme démontré au
  chapitre Modèle et confirmé par la recherche en grille, la disponibilité `C`
  est commune à tous les paquets à un instant `t` et se simplifie dans la
  comparaison d'éviction. La conformité au duty cycle se joue **à l'émission** :
  près du quota, la réponse est déléguée au backhaul (méthode
  `DutyCycleTracker::tryTransmit(..., aware=true)`), ce qui garantit un DCVR nul.
  Dans ndnSIM, ce point se réalise au niveau d'une **stratégie de transfert**
  personnalisée ou de l'application de service, et non dans la politique de CS.
- **Hits sémantiques (corrélation spatiale).** Servir une requête pour un
  capteur B depuis la valeur cachée d'un voisin A relève également du plan de
  transfert (résolution de nom), pas de la seule politique de CS. La politique
  fournit la brique d'éviction consciente de la redondance (`S` dans `U`) ; le
  service sémantique se branche dans la stratégie. Voir le prototype Python pour
  la logique complète.

## Points à vérifier selon ta version de NFD

- Signature exacte de `nfd::cs::Policy` : `doAfterInsert/doAfterRefresh/`
  `doBeforeErase/doBeforeUse/evictEntries` et le type `EntryRef`.
- Mécanisme d'éviction : `this->emitSignal(beforeEvict, i)` (vérifier le nom du
  signal `beforeEvict`).
- Accès au Content Store : `this->getCs()->size()` et `this->getLimit()`.
- En-tête de la politique : `#include "table/cs-policy.hpp"`.
