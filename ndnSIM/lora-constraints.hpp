/* -*- Mode:C++; c-file-style:"gnu" -*- */
/**
 * lora-constraints.hpp
 * --------------------
 * Modules de contraintes LoRaWAN partages par la politique FSEC-LoRa :
 *   - calcul du Time-on-Air (ToA) d'une trame LoRa ;
 *   - traceur de duty cycle (fenetre glissante d'une heure, budget 1%) ;
 *   - registre des etats capteurs (energie, position, valeur) ;
 *   - index de voisinage et noyau de correlation spatiale.
 *
 * Conception : un contexte global (LoraContext) sert de pont entre le scenario
 * ns-3 (qui connait les positions, l'energie, le trafic) et la politique de
 * cache FSEC-LoRa, qui n'a acces qu'aux entrees du Content Store. Dans une
 * integration ns-3 complete, EnergyModel se brancherait sur ns3::energy, et
 * DutyCycleTracker sur le module LoRa ; ici, le contexte est tenu a jour par le
 * scenario. Voir README.md.
 *
 * Auteur : KAMAGATE Inza (memoire M2).
 */
#ifndef FSEC_LORA_CONSTRAINTS_HPP
#define FSEC_LORA_CONSTRAINTS_HPP

#include <cmath>
#include <cstdint>
#include <deque>
#include <unordered_map>
#include <vector>

namespace fsec {

// --------------------------------------------------------------------------
// Parametres physiques LoRa
// --------------------------------------------------------------------------
struct LoraPhy {
  static constexpr double BW = 125000.0;   // bande passante (Hz)
  static constexpr int    N_PREAMBLE = 8;  // symboles de preambule
  static constexpr int    PAYLOAD_BYTES = 20;

  /** Time-on-Air d'une trame LoRa (s), formule de Semtech simplifiee. */
  static double timeOnAir(int sf, int payloadBytes = PAYLOAD_BYTES)
  {
    double tSym = std::pow(2.0, sf) / BW;
    double tPreamble = (N_PREAMBLE + 4.25) * tSym;
    int de = (sf >= 11) ? 1 : 0;
    int num = 8 * payloadBytes - 4 * sf + 28 + 16;
    int payloadSymb = 8 + std::max(
        static_cast<int>(std::ceil(static_cast<double>(num) / (4 * (sf - 2 * de)))) * 5, 0);
    double tPayload = payloadSymb * tSym;
    return tPreamble + tPayload;
  }
};

// --------------------------------------------------------------------------
// Traceur de duty cycle (fenetre glissante)
// --------------------------------------------------------------------------
class DutyCycleTracker {
public:
  DutyCycleTracker(double dcMax = 36.0, double window = 3600.0)
    : m_dcMax(dcMax), m_window(window), m_used(0.0) {}

  /** Disponibilite normalisee C = 1 - DC_utilise / DC_max, dans [0,1]. */
  double available(double now)
  {
    refresh(now);
    return std::max(0.0, 1.0 - m_used / m_dcMax);
  }

  /**
   * Tente une emission radio de duree toa a l'instant now.
   * @param aware  true si la politique est consciente du duty cycle (FSEC) :
   *               elle delegue au backhaul si le quota serait depasse.
   * @return true si l'emission a eu lieu, false si elle a ete deleguee.
   * Met a jour le compteur de violations si une politique aveugle depasse.
   */
  bool tryTransmit(double now, double toa, bool aware)
  {
    refresh(now);
    ++m_txAttempts;
    bool wouldExceed = (m_used + toa) > m_dcMax;
    if (aware && wouldExceed) {
      return false;               // offload vers le backhaul : pas de violation
    }
    if (wouldExceed) {
      ++m_violations;
    }
    m_events.push_back({now, toa});
    m_used += toa;
    return true;
  }

  double violationRate() const
  {
    return (m_txAttempts == 0) ? 0.0 : 100.0 * m_violations / m_txAttempts;
  }

private:
  void refresh(double now)
  {
    while (!m_events.empty() && m_events.front().t < now - m_window) {
      m_used -= m_events.front().dur;
      m_events.pop_front();
    }
    if (m_used < 0.0) m_used = 0.0;
  }

  struct Tx { double t; double dur; };
  double m_dcMax, m_window, m_used;
  std::deque<Tx> m_events;
  std::uint64_t m_txAttempts = 0, m_violations = 0;
};

// --------------------------------------------------------------------------
// Etat d'un capteur (producteur)
// --------------------------------------------------------------------------
struct SensorState {
  uint32_t id;
  double   x, y;             // position (m)
  double   batteryJ;         // energie residuelle (J)
  double   batteryFullJ;     // energie totale (J)
  double   lastValue;        // derniere valeur produite
  bool     alive = true;

  double energyFrac() const
  {
    return (batteryFullJ > 0.0) ? std::max(0.0, batteryJ / batteryFullJ) : 0.0;
  }
};

// --------------------------------------------------------------------------
// Contexte global : positions, energie, voisinage, duty cycle
// --------------------------------------------------------------------------
class LoraContext {
public:
  static LoraContext& instance()
  {
    static LoraContext ctx;
    return ctx;
  }

  void addSensor(uint32_t id, double x, double y, double batteryFullJ)
  {
    SensorState s;
    s.id = id; s.x = x; s.y = y;
    s.batteryFullJ = batteryFullJ; s.batteryJ = batteryFullJ;
    s.lastValue = 0.0;
    m_sensors[id] = s;
  }

  SensorState* sensor(uint32_t id)
  {
    auto it = m_sensors.find(id);
    return (it == m_sensors.end()) ? nullptr : &it->second;
  }

  /** Precalcule les listes de voisinage (capteurs a moins de 3*sigma_d). */
  void buildNeighbors(double sigmaD)
  {
    m_sigmaD = sigmaD;
    m_neighbors.clear();
    for (auto& a : m_sensors) {
      for (auto& b : m_sensors) {
        if (a.first == b.first) continue;
        double d = distance(a.second, b.second);
        if (d < 3.0 * sigmaD) {
          m_neighbors[a.first].push_back(b.first);
        }
      }
    }
  }

  const std::vector<uint32_t>& neighbors(uint32_t id)
  {
    static const std::vector<uint32_t> empty;
    auto it = m_neighbors.find(id);
    return (it == m_neighbors.end()) ? empty : it->second;
  }

  static double distance(const SensorState& a, const SensorState& b)
  {
    double dx = a.x - b.x, dy = a.y - b.y;
    return std::sqrt(dx * dx + dy * dy);
  }

  DutyCycleTracker& dutyCycle() { return m_dutyCycle; }
  double sigmaD() const { return m_sigmaD; }
  double sigmaV() const { return m_sigmaV; }
  void setSigmaV(double s) { m_sigmaV = s; }

private:
  LoraContext() = default;
  std::unordered_map<uint32_t, SensorState> m_sensors;
  std::unordered_map<uint32_t, std::vector<uint32_t>> m_neighbors;
  DutyCycleTracker m_dutyCycle;
  double m_sigmaD = 80.0;
  double m_sigmaV = 0.8;
};

} // namespace fsec

#endif // FSEC_LORA_CONSTRAINTS_HPP
