/* -*- Mode:C++; c-file-style:"gnu" -*- */
/**
 * lfu-policy.hpp
 * -------------
 * Politique de Content Store LFU (Least Frequently Used) pour ndnSIM / NFD.
 *
 * Reference classique de comparaison, absente de NFD par defaut (qui ne fournit
 * que `lru` et `priority_fifo`). Chaque entree porte un compteur d'acces,
 * incremente a chaque hit ; en cas de saturation, on evince l'entree de plus
 * faible frequence. Meme interface que la LruPolicy native (nfd::cs::Policy).
 *
 * Auteur : KAMAGATE Inza (memoire M2).
 */
#ifndef LFU_POLICY_HPP
#define LFU_POLICY_HPP

#include "table/cs-policy.hpp"
#include <list>
#include <utility>
#include <cstdint>

namespace nfd {
namespace cs {

class LfuPolicy : public Policy {
public:
  LfuPolicy();

  static const std::string POLICY_NAME;

private:
  // Interface nfd::cs::Policy
  void doAfterInsert(EntryRef i) override;
  void doAfterRefresh(EntryRef i) override;
  void doBeforeErase(EntryRef i) override;
  void doBeforeUse(EntryRef i) override;
  void evictEntries() override;

  // Suivi (entree, compteur d'acces). Le cache d'un routeur IoT reste petit
  // (quelques centaines d'entrees), une recherche lineaire suffit.
  using EntryList = std::list<std::pair<EntryRef, uint64_t>>;
  EntryList::iterator find(EntryRef i);

  EntryList m_entries;
};

} // namespace cs
} // namespace nfd

#endif // LFU_POLICY_HPP
