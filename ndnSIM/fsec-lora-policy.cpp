/* -*- Mode:C++; c-file-style:"gnu" -*- */
/**
 * fsec-lora-policy.cpp
 * --------------------
 * Implementation de la politique de Content Store FSEC-LoRa.
 * Voir fsec-lora-policy.hpp pour la description et les avertissements de version.
 */
#include "fsec-lora-policy.hpp"
#include "lora-constraints.hpp"
#include "table/cs.hpp"      // definition complete de nfd::cs::Cs (necessaire pour getCs()->size())

#include "ns3/simulator.h"   // ns3::Simulator::Now()

#include <cmath>
#include <cstdlib>
#include <string>
#include <iostream>

namespace nfd {
namespace cs {
namespace fsec {

const std::string FsecLoRaPolicy::POLICY_NAME = "fsec-lora";
NFD_REGISTER_CS_POLICY(FsecLoRaPolicy);

FsecLoRaPolicy::FsecLoRaPolicy()
  : Policy(POLICY_NAME)
{
}

// Compteurs FHR (statiques : agreges sur toutes les instances de CS).
// A chaque hit (doBeforeUse), on compte le total et la part encore fraiche.
static long g_fhrTotal = 0;
static long g_fhrFresh = 0;

FsecLoRaPolicy::~FsecLoRaPolicy()
{
  if (g_fhrTotal > 0) {
    std::cout << ">>> FHR FSEC : hits=" << g_fhrTotal
              << " frais=" << g_fhrFresh
              << " FHR=" << (100.0 * g_fhrFresh / g_fhrTotal) << "%"
              << std::endl;
  }
}

// --------------------------------------------------------------------------
// Parsing des metadonnees portees par le paquet Data.
// Convention de nommage : /fsec/<sensorId>/<seq>
// Convention de contenu : chaine "value;tgen" (tgen en secondes simulees).
// La position (x,y) et l'energie du capteur sont lues dans LoraContext via
// l'identifiant du capteur.
// --------------------------------------------------------------------------
bool
FsecLoRaPolicy::parseMeta(EntryRef i, uint32_t& sensorId,
                          double& value, double& tGen, double& ttl)
{
  const ndn::Data& data = i->getData();
  const ndn::Name& name = data.getName();
  if (name.size() < 2) {
    return false;
  }
  // Le nom peut porter le numero via un composant typed "sequence" (ndnSIM :
  // /fsec/seq=<n>) ou un composant numerique brut (/fsec/<n>). On gere les deux.
  try {
    sensorId = static_cast<uint32_t>(name.get(1).toSequenceNumber());
  }
  catch (...) {
    try { sensorId = static_cast<uint32_t>(std::stoul(name.get(1).toUri())); }
    catch (...) { return false; }
  }

  // contenu "value;tgen"
  const ndn::Block& content = data.getContent();
  std::string s(reinterpret_cast<const char*>(content.value()), content.value_size());
  auto pos = s.find(';');
  if (pos == std::string::npos) {
    return false;
  }
  try {
    value = std::stod(s.substr(0, pos));
    tGen  = std::stod(s.substr(pos + 1));
  }
  catch (...) {
    return false;
  }

  // TTL = FreshnessPeriod (ms) -> secondes
  ttl = data.getFreshnessPeriod().count() / 1000.0;
  if (ttl <= 0.0) {
    ttl = 1.0;
  }
  return true;
}

// --------------------------------------------------------------------------
// Score d'utilite U = F^alpha (1-S)^beta (1 + kappa (1-E)).
// L'energie entre comme un COUT D'UN MISS : plus le producteur est faible
// (E -> 0), plus garder sa donnee est prioritaire ; le plancher 1 evite toute
// degradation a batterie pleine (E -> 1).
// --------------------------------------------------------------------------
double
FsecLoRaPolicy::utility(EntryRef i) const
{
  uint32_t sensorId;
  double value, tGen, ttl;
  if (!parseMeta(i, sensorId, value, tGen, ttl)) {
    return 0.0;
  }
  double now = ns3::Simulator::Now().GetSeconds();

  // Fraicheur
  double age = now - tGen;
  double F = std::max(0.0, (ttl - age) / ttl);

  // Energie du capteur producteur
  auto& ctx = ::fsec::LoraContext::instance();
  ::fsec::SensorState* prod = ctx.sensor(sensorId);
  double E = (prod != nullptr) ? prod->energyFrac() : 1.0;

  // Redondance spatiale : noyau gaussien avec les voisins caches frais
  double S = 0.0;
  if (prod != nullptr) {
    double sd2 = 2.0 * ctx.sigmaD() * ctx.sigmaD();
    double sv2 = 2.0 * ctx.sigmaV() * ctx.sigmaV();
    for (uint32_t nb : ctx.neighbors(sensorId)) {
      // recherche du voisin dans les entrees suivies
      for (EntryRef e : m_entries) {
        uint32_t sid2; double v2, tg2, ttl2;
        if (!parseMeta(e, sid2, v2, tg2, ttl2) || sid2 != nb) {
          continue;
        }
        if ((now - tg2) > ttl2) {
          continue; // voisin expire
        }
        ::fsec::SensorState* sb = ctx.sensor(nb);
        if (sb == nullptr) continue;
        double d = ::fsec::LoraContext::distance(*prod, *sb);
        double r = std::exp(-(d * d) / sd2) *
                   std::exp(-((value - v2) * (value - v2)) / sv2);
        if (r > S) S = r;
        break;
      }
    }
  }

  return std::pow(F, m_alpha) * std::pow(1.0 - S, m_beta) * (1.0 + m_kappa * (1.0 - E));
}

// --------------------------------------------------------------------------
// Interface Policy
// --------------------------------------------------------------------------
void
FsecLoRaPolicy::doAfterInsert(EntryRef i)
{
  // Purge active : on retire d'abord les entrees expirees pour ne jamais servir
  // de donnee perimee (comportement du prototype).
  purgeExpired();

  // Filtre de placement : on rejette immediatement une donnee de trop faible
  // utilite (transfert sans mise en cache). On evite ainsi le cache thrashing.
  if (utility(i) < m_uSeuil) {
    this->emitSignal(beforeEvict, i);   // la CS supprime l'entree
    return;
  }
  m_entries.push_back(i);
  this->evictEntries();
}

void
FsecLoRaPolicy::doAfterRefresh(EntryRef i)
{
  // L'entree existe deja ; rien de specifique (sa fraicheur sera reevaluee).
}

void
FsecLoRaPolicy::doBeforeErase(EntryRef i)
{
  m_entries.remove(i);
}

void
FsecLoRaPolicy::doBeforeUse(EntryRef i)
{
  // Mesure du FHR : a chaque hit de cache, comparer l'age reel de la donnee
  // servie a son TTL (FreshnessPeriod). La fraicheur est un concept natif NDN.
  uint32_t sid; double v, tg, ttl;
  if (parseMeta(i, sid, v, tg, ttl)) {
    double age = ns3::Simulator::Now().GetSeconds() - tg;
    ++g_fhrTotal;
    if (age <= ttl) {
      ++g_fhrFresh;
    }
  }
}

void
FsecLoRaPolicy::purgeExpired()
{
  double now = ns3::Simulator::Now().GetSeconds();
  for (auto it = m_entries.begin(); it != m_entries.end(); ) {
    EntryRef e = *it;
    uint32_t sid; double v, tg, ttl;
    if (parseMeta(e, sid, v, tg, ttl) && (now - tg) > ttl) {
      it = m_entries.erase(it);          // retirer du suivi d'abord
      this->emitSignal(beforeEvict, e);  // puis demander la suppression a la CS
    }
    else {
      ++it;
    }
  }
}

void
FsecLoRaPolicy::evictEntries()
{
  BOOST_ASSERT(this->getCs() != nullptr);
  // Tant que le cache depasse sa capacite, evincer l'entree de plus faible
  // utilite (politique de remplacement unifiee avec le placement).
  while (this->getCs()->size() > this->getLimit()) {
    if (m_entries.empty()) {
      break;
    }
    auto worst = m_entries.begin();
    double uMin = utility(*worst);
    for (auto it = std::next(m_entries.begin()); it != m_entries.end(); ++it) {
      double u = utility(*it);
      if (u < uMin) {
        uMin = u;
        worst = it;
      }
    }
    EntryRef victim = *worst;
    m_entries.erase(worst);
    this->emitSignal(beforeEvict, victim);
  }
}

} // namespace fsec
} // namespace cs
} // namespace nfd
