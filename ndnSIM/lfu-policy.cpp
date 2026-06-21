/* -*- Mode:C++; c-file-style:"gnu" -*- */
/**
 * lfu-policy.cpp
 * -------------
 * Implementation de la politique LFU (Least Frequently Used).
 * Voir lfu-policy.hpp.
 */
#include "lfu-policy.hpp"
#include "table/cs.hpp"   // definition complete de nfd::cs::Cs (getCs()->size())

#include <iterator>

namespace nfd {
namespace cs {

const std::string LfuPolicy::POLICY_NAME = "lfu";
NFD_REGISTER_CS_POLICY(LfuPolicy);

LfuPolicy::LfuPolicy()
  : Policy(POLICY_NAME)
{
}

LfuPolicy::EntryList::iterator
LfuPolicy::find(EntryRef i)
{
  for (auto it = m_entries.begin(); it != m_entries.end(); ++it) {
    if (it->first == i) {
      return it;
    }
  }
  return m_entries.end();
}

void
LfuPolicy::doAfterInsert(EntryRef i)
{
  m_entries.push_back(std::make_pair(i, static_cast<uint64_t>(1)));
  this->evictEntries();
}

void
LfuPolicy::doAfterRefresh(EntryRef i)
{
  auto it = find(i);
  if (it != m_entries.end()) {
    ++(it->second);
  }
}

void
LfuPolicy::doBeforeErase(EntryRef i)
{
  auto it = find(i);
  if (it != m_entries.end()) {
    m_entries.erase(it);
  }
}

void
LfuPolicy::doBeforeUse(EntryRef i)
{
  // Hit : on incremente la frequence d'acces de l'entree.
  auto it = find(i);
  if (it != m_entries.end()) {
    ++(it->second);
  }
}

void
LfuPolicy::evictEntries()
{
  BOOST_ASSERT(this->getCs() != nullptr);
  // Tant que le cache depasse sa capacite, evincer l'entree la moins frequemment
  // utilisee (compteur minimal).
  while (this->getCs()->size() > this->getLimit()) {
    if (m_entries.empty()) {
      break;
    }
    auto worst = m_entries.begin();
    for (auto it = std::next(m_entries.begin()); it != m_entries.end(); ++it) {
      if (it->second < worst->second) {
        worst = it;
      }
    }
    EntryRef victim = worst->first;
    m_entries.erase(worst);
    this->emitSignal(beforeEvict, victim);
  }
}

} // namespace cs
} // namespace nfd
