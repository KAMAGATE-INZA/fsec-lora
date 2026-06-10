/* -*- Mode:C++; c-file-style:"gnu" -*- */
/**
 * fsec-scenario.cpp
 * -----------------
 * Scenario ndnSIM minimal pour evaluer la politique FSEC-LoRa.
 *
 * Topologie : N capteurs (producteurs) -> 1 passerelle (Content Store FSEC) ->
 * 1 serveur applicatif (consommateur). Les capteurs publient des donnees
 * transitoires nommees /fsec/<sensorId>/<seq> avec une FreshnessPeriod et un
 * contenu "value;tgen". Le consommateur emet des Interest selon une popularite
 * de Zipf.
 *
 * Ce fichier est un MODELE a adapter a ton arborescence ndnSIM (voir README.md).
 * Il montre comment selectionner la politique FSEC, peupler le contexte LoRa
 * (positions, energie, voisinage) et brancher les traceurs de metriques.
 *
 * Compilation : placer dans scratch/ de ns-3 puis ./waf --run fsec-scenario
 *
 * Auteur : KAMAGATE Inza (memoire M2).
 */
#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/point-to-point-module.h"
#include "ns3/ndnSIM-module.h"

#include "lora-constraints.hpp"

#include <random>

namespace ns3 {

int
main(int argc, char* argv[])
{
  // ----- parametres en ligne de commande -----
  uint32_t nSensors = 200;
  uint32_t cacheSize = 100;
  double   area = 1000.0;
  uint32_t nClusters = 8;
  double   sigmaD = 80.0;
  double   simTime = 3600.0;

  CommandLine cmd;
  cmd.AddValue("nSensors", "Nombre de capteurs", nSensors);
  cmd.AddValue("cacheSize", "Taille du Content Store de la passerelle", cacheSize);
  cmd.AddValue("simTime", "Duree de simulation (s)", simTime);
  cmd.Parse(argc, argv);

  // ----- peuplement du contexte LoRa (positions, energie, voisinage) -----
  auto& ctx = ::fsec::LoraContext::instance();
  std::mt19937 rng(1);
  std::uniform_real_distribution<double> U(0.0, area);
  std::vector<std::pair<double, double>> centers;
  for (uint32_t c = 0; c < nClusters; ++c) {
    centers.emplace_back(U(rng), U(rng));
  }
  std::normal_distribution<double> jitter(0.0, area * 0.04);
  for (uint32_t i = 0; i < nSensors; ++i) {
    auto [cx, cy] = centers[i % nClusters];
    double x = std::min(std::max(cx + jitter(rng), 0.0), area);
    double y = std::min(std::max(cy + jitter(rng), 0.0), area);
    ctx.addSensor(i, x, y, /*batteryFullJ=*/4.0);
  }
  ctx.setSigmaV(0.8);
  ctx.buildNeighbors(sigmaD);

  // ----- topologie ns-3 : capteurs -- passerelle -- serveur -----
  NodeContainer sensors;  sensors.Create(nSensors);
  Ptr<Node> gateway = CreateObject<Node>();
  Ptr<Node> server  = CreateObject<Node>();

  PointToPointHelper p2p;
  p2p.SetDeviceAttribute("DataRate", StringValue("1Mbps"));
  p2p.SetChannelAttribute("Delay", StringValue("10ms"));
  for (uint32_t i = 0; i < nSensors; ++i) {
    p2p.Install(sensors.Get(i), gateway);
  }
  p2p.Install(gateway, server);

  // ----- pile NDN : politique FSEC sur la passerelle -----
  ndn::StackHelper ndnHelper;
  ndnHelper.SetDefaultRoutes(true);
  // Capteurs et serveur : cache nul (ils ne cachent pas)
  ndnHelper.setCsSize(1);
  ndnHelper.setPolicy("nfd::cs::lru");
  ndnHelper.Install(sensors);
  ndnHelper.Install(server);
  // Passerelle : Content Store FSEC-LoRa
  ndnHelper.setCsSize(cacheSize);
  ndnHelper.setPolicy("nfd::cs::fsec-lora");   // <-- notre politique enregistree
  ndnHelper.Install(gateway);

  // ----- routage par nom -----
  ndn::GlobalRoutingHelper routing;
  routing.InstallAll();

  // ----- producteurs : un prefixe par capteur /fsec/<id> -----
  ndn::AppHelper producer("ns3::ndn::Producer");
  producer.SetAttribute("Freshness", StringValue("60s")); // FreshnessPeriod = TTL
  producer.SetAttribute("PayloadSize", StringValue("20"));
  for (uint32_t i = 0; i < nSensors; ++i) {
    std::string prefix = "/fsec/" + std::to_string(i);
    producer.SetPrefix(prefix);
    producer.Install(sensors.Get(i));
    routing.AddOrigins(prefix, sensors.Get(i));
  }

  // ----- consommateur : requetes Zipf sur l'ensemble des capteurs -----
  // NB : ConsumerZipfMandelbrot demande des noms /fsec/<seq>. Pour respecter la
  // convention /fsec/<sensorId>/<seq>, on peut soit ecrire un consommateur
  // dedie, soit utiliser plusieurs ConsumerCbr. Voir README pour la variante
  // exacte selon ta version. Exemple minimal avec un consommateur Zipf :
  ndn::AppHelper consumer("ns3::ndn::ConsumerZipfMandelbrot");
  consumer.SetAttribute("NumberOfContents", StringValue(std::to_string(nSensors)));
  consumer.SetAttribute("q", StringValue("0.0"));
  consumer.SetAttribute("s", StringValue("0.8"));        // skew de popularite
  consumer.SetAttribute("Frequency", StringValue("5"));  // requetes/s
  consumer.SetPrefix("/fsec");
  consumer.Install(server);

  routing.CalculateRoutes();

  // ----- traceurs de metriques -----
  ndn::CsTracer::InstallAll("cs-trace.txt", Seconds(simTime));
  ndn::AppDelayTracer::InstallAll("app-delay-trace.txt");
  ndn::L3RateTracer::InstallAll("rate-trace.txt", Seconds(simTime));
  // Le CHR se deduit de cs-trace (CacheHits / (CacheHits + CacheMisses)).
  // Le FHR, l'EUB et le DCVR demandent des traceurs personnalises branches sur
  // LoraContext (energie capteurs) et DutyCycleTracker (voir README).

  Simulator::Stop(Seconds(simTime));
  Simulator::Run();
  Simulator::Destroy();
  return 0;
}

} // namespace ns3

int
main(int argc, char* argv[])
{
  return ns3::main(argc, argv);
}
