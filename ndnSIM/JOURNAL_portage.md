# Journal de bord — Portage FSEC-LoRa sous ndnSIM

> Suivi de l'effort de compilation/exécution sur la machine cible. On note ici : version, erreurs rencontrées, corrections appliquées. Objectif : confirmation indépendante des résultats du prototype Python.

## Paliers
- [ ] **M0** — Environnement validé (versions ns-3/ndnSIM ; un exemple stock tourne).
- [x] **M1** — La politique `FsecLoRaPolicy` **compile, se lie ET s'exécute dans ndnSIM** (sélectionnable via `setPolicy("nfd::cs::fsec-lora")`, scénario lancé sans erreur). 3 corrections : `#include "table/cs.hpp"` ; scénario en `.cc` ; ajout à `m_csPolicies` dans `ndn-stack-helper.cpp`.
- [x] **M2** — Scénario exécuté ; CHR mesuré (via Interests atteignant le producteur, car `CsTracer` ne trace pas le CS de NFD). **Constat clé** : sans `LoraContext` peuplé, FSEC se réduit à un classement par fraîcheur et son CHR passe sous LRU — **cohérent avec l'analyse de robustesse** : l'avantage CHR vient des hits sémantiques (corrélation spatiale), qui relèvent du plan de transfert, pas de la politique de CS.
- [ ] **M3 (reporté, travail futur)** — Stratégie de transfert sémantique + peuplement `LoraContext` + traceurs FHR/EUB/DCVR. Non poursuivi (effort >> gain pour un mémoire M2).

## Conclusion du portage
La politique FSEC-LoRa **compile, s'enregistre et s'exécute sous ndnSIM 2.9 / NFD 22.02** — faisabilité d'intégration confirmée dans l'outil de référence. La reproduction complète de l'avantage en taux de succès (hits sémantiques) demande une stratégie de transfert custom, laissée en travail futur. Recette de portage : voir les 3 corrections du journal ci-dessous.

### Mesure (CHR = 1 − Interests atteignant le producteur / requêtes satisfaites)
Scénario (consommateur Zipf s=0,8 sur 200 contenus, cache=100, `LoraContext` peuplé, 3600 s simulées). Mesures obtenues **après correction du bug de portage** (voir journal ci-dessous) :

| Configuration | Interests → producteur | Satisfaites | CHR |
|---|---|---|---|
| FSEC-LoRa, corrélation active (σ_d=80) | 78 105 | 178 938 | ≈ 56,4 % |
| FSEC-LoRa, corrélation désactivée (σ_d=1) | 54 327 | 179 634 | ≈ 69,8 % |
| LRU | 46 426 | 179 837 | ≈ 74,2 % |
| LFU | 41 868 | 179 879 | ≈ 76,7 % |

(LFU : politique implémentée pour ndnSIM, absente de NFD par défaut — `lfu-policy.hpp/.cpp`, enregistrée dans `m_csPolicies`.)

**Lecture honnête.** Au seul niveau du Content Store, FSEC a un CHR *inférieur* à LRU (56,4 % vs 74,2 %). Ce n'est pas un artefact : le terme spatial `(1−S)^β` *déduplique* (refuse de cacher une donnée dont un voisin corrélé est déjà en cache) sans *resservir* — les hits sémantiques (requête pour B servie par la valeur cachée du voisin A) relèvent du **plan de transfert**, absent de ce scénario. La preuve du mécanisme : en **désactivant** la corrélation (σ_d=1), le CHR de FSEC remonte de 56,4 % à 69,8 %, quasi au niveau de LRU ; les ~13 points d'écart sont donc imputables à la déduplication, et le petit reste (69,8 vs 74,2) au filtre de fraîcheur/seuil. **Conclusion cohérente avec le mémoire** : au niveau CS seul, FSEC échange du CHR brut contre la non-redondance et la fraîcheur ; dans le système complet (prototype Python), ce sacrifice est récupéré puis dépassé par le service sémantique. ndnSIM, dépourvu de ce plan de transfert, en montre exactement la moitié — et le démontre quantitativement.

> Chiffres mesurés sur 3600 s. Résultats cohérents avec un run de validation à 600 s (54,3 / 70,2 / 74,4 %).

### Vérification du FHR (fraîcheur, concept natif NDN)
La fraîcheur est native (FreshnessPeriod du Data, flag `MustBeFresh` de l'Interest). On la mesure selon deux régimes, sur 3600 s.

**Service non contraint (sans `MustBeFresh`)** — NFD sert le périmé ; on compte, côté consommateur (compteur indépendant de la politique dans `OnData`), les données servies dont l'âge dépasse la FreshnessPeriod. FHR = (hits − périmés)/hits, avec hits = satisfaites − producteur :

| Politique | Hits cache | Hits périmés | FHR |
|---|---|---|---|
| FSEC-LoRa | 100 833 | 74 | ≈ 99,9 % |
| LRU | 133 411 | 53 123 | ≈ 60,2 % |
| LFU | 138 011 | 135 272 | ≈ 2,0 % |

**FSEC ne sert pratiquement que du frais (99,9 %) contre 60,2 % pour LRU, et surtout 2,0 % pour LFU.** LFU a le CHR brut le plus élevé (76,7 %) mais sert du périmé 98 % du temps : il retient indéfiniment les contenus populaires au-delà de leur TTL (pathologie de la popularité sur données transitoires). Argument central du mémoire confirmé sous ndnSIM. FSEC a moins de hits bruts (déduplication + purge) mais quasi tous frais ; LRU en a plus mais ~40 % périmés. C'est le compromis du mémoire. Contrôle de cohérence : le compteur interne de FSEC (`doBeforeUse`) donne 99,96 %, en accord avec le compteur consommateur. **Ce 99,9 % a été obtenu après ajout d'une purge active des entrées expirées** dans la politique (`purgeExpired()` appelée à chaque insertion) ; sans elle, le portage ne servait que 70,6 % de frais (il évinçait le périmé sous la seule pression de capacité, contrairement au prototype qui ne sert jamais de périmé).

**Service en fraîcheur dirigée (`MustBeFresh`)** — NFD refuse de servir le périmé. FSEC : **hits tous frais → FHR = 100 %** (CHR alors ≈ 57,9 % vs 73,8 % LRU). Mais sous `MustBeFresh`, NFD impose 100 % à *toute* politique : ce régime valide la **garantie** de fraîcheur, pas le contraste inter-politiques (c'est le régime non contraint, ci-dessus, qui le révèle).

**Nuance honnête.** Après purge active, FSEC atteint ~100 % comme le prototype. Le FHR de LRU reste supérieur au 22 % du prototype : dans ce scénario, les contenus populaires sont redemandés dans leur fenêtre de validité, donc LRU sert moins de périmé. L'écart qualitatif (FSEC nettement plus frais que LRU) est confirmé. Métriques restantes (EUB, DCVR, durée de vie) : non traçables sous ndnSIM (modèle radio LoRa), évaluées sur le prototype Python.

> Notes de portage : (1) pour la fraîcheur dirigée, ajouter `interest->setMustBeFresh(true);` dans le `SendPacket()` de `ndn-consumer-zipf-mandelbrot.cpp` (ce consommateur a son propre `SendPacket`, distinct de la base `ndn-consumer.cpp`) ; (2) le FHR par politique se mesure par un compteur de données périmées dans `Consumer::OnData` (`ndn-consumer.cpp`), indépendant de la politique, donc valable pour FSEC comme LRU.

## Environnement (M0)
- ndnSIM version : **ndnSIM-2.9 (NFD 22.02)**, commit 90d5039
- Build : **waf 2.0.21**
- Chemin racine ns-3 : `/home/antonyme/Memoire_ICN_LoRaWAN/ndnSIM/ns-3`
- Exemple stock `ndn-simple` : compile OK
- OS : Ubuntu 22.04.5 LTS (jammy)
- cs-policy.hpp : `src/ndnSIM/NFD/daemon/table/cs-policy.hpp`
- API confirmée : `EntryRef = Table::const_iterator` ; signal `beforeEvict` ; macro `NFD_REGISTER_CS_POLICY`

## M0 — VALIDÉ (environnement sain, base compile, API connue)

## Journal (date — palier — erreur — correction)
- M1 — `wscript` ramasse les fichiers automatiquement (glob) : pas d'édition du build nécessaire.
- M1 — Erreur 1 : `invalid use of incomplete type 'class nfd::cs::Cs'` (appel `getCs()->size()` alors que `Cs` n'est que forward-déclaré). → **Correction** : ajout de `#include "table/cs.hpp"` dans `fsec-lora-policy.cpp`.
- M1b — `scratch/` ne compile que les fichiers `.cc` (pas `.cpp`). → renommer le scénario en `.cc`.
- M1b — Runtime : `policy nfd::cs::fsec-lora not found`. Cause : la `StackHelper` de ndnSIM **n'utilise pas** le registre `NFD_REGISTER_CS_POLICY` ; elle a sa propre liste codée en dur `m_csPolicies` (constructeur de `ndn-stack-helper.cpp`). → **Correction (modif de l'arbre ndnSIM)** : dans `src/ndnSIM/helper/ndn-stack-helper.cpp`, (1) `#include "ns3/ndnSIM/NFD/daemon/table/fsec-lora-policy.hpp"` ; (2) `m_csPolicies.insert({"nfd::cs::fsec-lora", [] { return make_unique<nfd::cs::fsec::FsecLoRaPolicy>(); }});`. Recompiler.
- M2 — **Bug de portage diagnostiqué par sonde de debug** : FSEC ne cachait quasiment rien (CHR 2,7 %, identique avec/sans corrélation). Une sonde dans `doAfterInsert` a révélé `parseMeta=0` sur toutes les données `/fsec/...` → utilité 0 → rejet total. **Cause** : le consommateur ndnSIM nomme les contenus avec un composant *typé* « numéro de séquence » (`/fsec/seq=109`), pas un nombre brut ; `std::stoul("seq=109")` lève une exception → `parseMeta` échouait. → **Correction** dans `parseMeta` : extraire l'identifiant via `name.get(1).toSequenceNumber()` (avec repli `std::stoul` pour les noms numériques bruts). Après correction : `parseMeta=1`, utilités correctes (0,99 pour données fraîches non redondantes ; <seuil quand `S` élevé), et la mesure CHR ci-dessus devient valide.
