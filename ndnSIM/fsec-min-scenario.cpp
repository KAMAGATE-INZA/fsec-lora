/* -*- Mode:C++; c-file-style:"gnu" -*- */
/**
 * fsec-min-scenario.cpp
 * ---------------------
 * Mini-scénario de VALIDATION (palier M1b) : vérifie seulement que la politique
 * "nfd::cs::fsec-lora" est bien enregistrée, sélectionnable, et qu'une simulation
 * tourne jusqu'au bout sans erreur. Topologie linéaire consumer -- routeur -- producer.
 *
 * Le CHR sera ~0 ici (ConsumerCbr ne répète pas les noms, et le Data stock n'est
 * pas au format "value;tgen") : c'est NORMAL. On confirme juste l'intégration.
 * Le scénario fidèle (avec producteur custom) vient au palier M2.
 *
 * Placer dans scratch/ puis : ./waf --run fsec-min-scenario
 */
#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/point-to-point-module.h"
#include "ns3/ndnSIM-module.h"

namespace ns3 {

int
main(int argc, char* argv[])
{
  CommandLine cmd;
  cmd.Parse(argc, argv);

  NodeContainer nodes;
  nodes.Create(3);   // 0 = consumer, 1 = routeur (cache FSEC), 2 = producer

  PointToPointHelper p2p;
  p2p.Install(nodes.Get(0), nodes.Get(1));
  p2p.Install(nodes.Get(1), nodes.Get(2));

  ndn::StackHelper ndnHelper;
  ndnHelper.SetDefaultRoutes(true);

  // Routeur : notre politique FSEC-LoRa
  ndnHelper.setCsSize(100);
  ndnHelper.setPolicy("nfd::cs::fsec-lora");
  ndnHelper.Install(nodes.Get(1));

  // Consumer et producer : cache minimal
  ndnHelper.setCsSize(1);
  ndnHelper.setPolicy("nfd::cs::lru");
  ndnHelper.Install(nodes.Get(0));
  ndnHelper.Install(nodes.Get(2));

  ndn::AppHelper consumer("ns3::ndn::ConsumerCbr");
  consumer.SetPrefix("/fsec/0");
  consumer.SetAttribute("Frequency", StringValue("10"));
  consumer.Install(nodes.Get(0));

  ndn::AppHelper producer("ns3::ndn::Producer");
  producer.SetPrefix("/fsec/0");
  producer.SetAttribute("Freshness", StringValue("60s"));
  producer.SetAttribute("PayloadSize", StringValue("20"));
  producer.Install(nodes.Get(2));

  ndn::GlobalRoutingHelper routing;
  routing.InstallAll();
  routing.AddOrigins("/fsec/0", nodes.Get(2));
  routing.CalculateRoutes();

  ndn::CsTracer::InstallAll("cs-trace.txt", Seconds(1.0));

  Simulator::Stop(Seconds(20.0));
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
