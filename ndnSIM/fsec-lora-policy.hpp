/* -*- Mode:C++; c-file-style:"gnu" -*- */
/**
 * fsec-lora-policy.hpp
 * --------------------
 * Politique de Content Store FSEC-LoRa pour ndnSIM / NFD.
 *
 * Derive de nfd::cs::Policy (meme interface que la LruPolicy native). Le
 * placement et le remplacement sont unifies par une fonction d'utilite
 *      U(D) = F^alpha * (1 - S)^beta * (1 + kappa * (1 - E))
 * ou F est la fraicheur, S la redondance spatiale (noyau gaussien) et E
 * l'energie du capteur producteur. Le facteur de duty cycle C est COMMUN a
 * tous les paquets a un instant donne : il se simplifie dans la comparaison
 * d'eviction et n'apparait donc pas ici (resultat etabli au chapitre Modele et
 * confirme par la recherche en grille). La conformite au duty cycle est geree
 * a l'emission, par un DutyCycleTracker interroge cote strategie/application.
 *
 * IMPORTANT : ce code cible ndnSIM 2.8+ / NFD. Les signatures exactes de
 * nfd::cs::Policy peuvent varier selon la version. A compiler et adapter sur la
 * machine cible (voir README.md).
 *
 * Auteur : KAMAGATE Inza (memoire M2).
 */
#ifndef FSEC_LORA_POLICY_HPP
#define FSEC_LORA_POLICY_HPP

#include "table/cs-policy.hpp"
#include <list>

namespace nfd {
namespace cs {
namespace fsec {

/**
 * Politique de cache multi-criteres FSEC-LoRa.
 */
class FsecLoRaPolicy : public Policy {
public:
  FsecLoRaPolicy();

  static const std::string POLICY_NAME;

  // Parametres de la fonction d'utilite (reglables via attributs/scenario).
  void setAlpha(double a) { m_alpha = a; }
  void setBeta(double b)  { m_beta = b; }
  void setKappa(double k) { m_kappa = k; }   // poids du cout d'un miss (energie)
  void setUSeuil(double u) { m_uSeuil = u; }

private:
  // Interface nfd::cs::Policy
  void doAfterInsert(EntryRef i) override;
  void doAfterRefresh(EntryRef i) override;
  void doBeforeErase(EntryRef i) override;
  void doBeforeUse(EntryRef i) override;
  void evictEntries() override;

  // Calcul du score d'utilite d'une entree :
  //   U = F^alpha (1-S)^beta (1 + kappa (1-E)).
  double utility(EntryRef i) const;

  // Outils de parsing des metadonnees portees par le Data.
  static bool parseMeta(EntryRef i, uint32_t& sensorId,
                        double& value, double& tGen, double& ttl);

private:
  std::list<EntryRef> m_entries;   // entrees suivies par la politique
  double m_alpha = 1.5;
  double m_beta  = 1.0;
  double m_kappa = 3.0;
  double m_uSeuil = 0.05;
};

} // namespace fsec
} // namespace cs
} // namespace nfd

#endif // FSEC_LORA_POLICY_HPP
