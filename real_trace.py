"""
real_trace.py
=============
Adaptateur "traces reelles" pour FSEC-LoRa .

Objectif : remplacer le champ synthetique du simulateur (cluster_base + derive +
bruit) par de VRAIES mesures de capteurs geolocalises, afin de valider que la
correlation spatiale supposee existe dans des donnees reelles et que l'avantage
de FSEC-LoRa tient. Ce n'est PAS un deploiement materiel : on rejoue un jeu de
donnees enregistre.

Aucune modification du coeur : on sous-classe Simulator (comme exp_modele.py) et
on redefinit la topologie et la lecture de valeur.

Jeux de donnees recommandes (a telecharger separement) :
  1. Intel Berkeley Lab (dense, interieur, forte correlation) :
     http://db.csail.mit.edu/labdata/labdata.html
     - data.txt      : "date time epoch moteid temperature humidity light voltage"
     - mote_locs.txt : "moteid  x  y"   (metres)
  2. sensor.community / ClickHouse (epars, exterieur, correlation faible) :
     CSV avec colonnes lat, lon, timestamp, temperature (BME280/DHT22...).

Usage :
  # avec Intel Lab (fichiers telecharges dans simulation/data/) :
  python3 real_trace.py intel  data/data.txt  data/mote_locs.txt  temperature
  # avec un CSV generique (colonnes : sid,x,y,t,value) :
  python3 real_trace.py csv  chemin.csv
  # sans fichier (repli synthetique, pour tester le pipeline) :
  python3 real_trace.py
"""
from __future__ import annotations
import bisect
import math
import os
import sys
from collections import defaultdict

from fsec_sim import Config, Simulator, Sensor, time_on_air


# ---------------------------------------------------------------------------
# Structure d'une trace :  {"pos": {sid:(x,y)}, "series": {sid:(ts[], vs[])},
#                           "duration": float}
# ts normalises pour demarrer a 0.
# ---------------------------------------------------------------------------
def _finalize(pos, raw):
    """raw : {sid: [(t, v), ...]}. Trie, normalise le temps a 0, renvoie une trace."""
    t0 = min(t for lst in raw.values() for (t, _) in lst)
    series = {}
    tmax = 0.0
    for sid, lst in raw.items():
        lst = sorted(lst)
        ts = [t - t0 for (t, _) in lst]
        vs = [v for (_, v) in lst]
        series[sid] = (ts, vs)
        if ts:
            tmax = max(tmax, ts[-1])
    # ne garder que les capteurs ayant a la fois une position et des mesures
    common = sorted(set(pos) & set(series))
    pos = {s: pos[s] for s in common}
    series = {s: series[s] for s in common}
    return {"pos": pos, "series": series, "duration": tmax}


def load_intel_lab(data_path, locs_path, field="temperature", span=7200.0):
    """Charge le jeu Intel Berkeley Lab.
    - gere les fichiers .gz ;
    - reconstruit un temps absolu (date + heure), multi-jours ;
    - filtre les releves aberrants (le jeu contient des valeurs fautives) ;
    - selectionne une fenetre de `span` s bien couverte (autour du temps median),
      pour que la simulation dispose de mesures simultanees sur la plupart des motes.
    field in {temperature, humidity, light, voltage}."""
    import datetime as _dt
    import gzip as _gzip
    idx = {"temperature": 4, "humidity": 5, "light": 6, "voltage": 7}[field]
    lo, hi = {"temperature": (-10.0, 60.0), "humidity": (0.0, 100.0),
              "light": (0.0, 2000.0), "voltage": (1.0, 4.0)}[field]

    pos = {}
    with open(locs_path) as f:
        for line in f:
            p = line.split()
            if len(p) >= 3:
                try:
                    pos[int(float(p[0]))] = (float(p[1]), float(p[2]))
                except ValueError:
                    continue

    _opener = _gzip.open if str(data_path).endswith(".gz") else open
    _ord = {}
    raw = defaultdict(list)
    with _opener(data_path, "rt", errors="ignore") as f:
        for line in f:
            p = line.split()
            if len(p) < 8:
                continue
            try:
                y, mo, d = p[0].split("-")
                key = (int(y), int(mo), int(d))
                day = _ord.get(key)
                if day is None:
                    day = _dt.date(*key).toordinal()
                    _ord[key] = day
                hh, mm, ss = p[1].split(":")
                t = day * 86400.0 + int(hh) * 3600 + int(mm) * 60 + float(ss)
                mote = int(float(p[3]))
                val = float(p[idx])
            except (ValueError, IndexError):
                continue
            if not (lo <= val <= hi) or mote not in pos:
                continue
            raw[mote].append((t, val))

    # fenetre bien couverte : autour du temps median des relevés
    all_t = sorted(t for lst in raw.values() for (t, _) in lst)
    if all_t:
        t0 = all_t[len(all_t) // 2]
        win = {sid: [(t, v) for (t, v) in lst if t0 <= t < t0 + span]
               for sid, lst in raw.items()}
        raw = {sid: lst for sid, lst in win.items() if lst}
    return _finalize(pos, raw)


def load_generic_csv(path):
    """CSV avec en-tete contenant les colonnes : sid, x, y, t, value."""
    import csv
    pos = {}
    raw = defaultdict(list)
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            sid = r["sid"]
            pos.setdefault(sid, (float(r["x"]), float(r["y"])))
            raw[sid].append((float(r["t"]), float(r["value"])))
    return _finalize(pos, raw)


def _parse_ts(s):
    """Horodatage ISO 8601 (avec ou sans fuseau) -> secondes. Tolerant."""
    import datetime as _dt
    s = s.strip().replace("Z", "+00:00")
    try:
        return _dt.datetime.fromisoformat(s).timestamp()
    except ValueError:
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
            try:
                return _dt.datetime.strptime(s[:19], fmt).timestamp()
            except ValueError:
                continue
    return None


def _pick(cols, *cands):
    low = {c.lower(): c for c in cols}
    for cand in cands:
        if cand in low:
            return low[cand]
    for c in cols:                       # sous-chaine
        for cand in cands:
            if cand in c.lower():
                return c
    return None


def load_melbourne(readings_csv, locations_csv=None, field="temperature", span=7200.0):
    """Jeu 'City of Melbourne - Microclimate' : capteurs urbains EXTERIEURS epars
    (faible correlation, contraste avec Intel Lab). Le fichier de releves est
    auto-suffisant (Device_id, Time, LatLong embarque, AirTemperature) : on en tire
    directement positions ET series. locations_csv n'est utilise qu'en repli si le
    fichier de releves ne porte pas de coordonnees. Auto-detection des colonnes,
    projection lat/lon en metres."""
    import csv
    import gzip as _gzip
    import math as _m

    def _open(p):
        opener = _gzip.open if str(p).endswith(".gz") else open
        return opener(p, "rt", encoding="utf-8-sig", errors="ignore")

    raw = defaultdict(list)
    emb = {}                       # positions lat/lon embarquees, par capteur
    with _open(readings_csv) as f:
        rd = csv.DictReader(f, delimiter=_sniff(f))
        cols = rd.fieldnames or []
        c_id = _pick(cols, "device_id", "site_id", "sensor_id", "id")
        c_ts = _pick(cols, "time", "local_time", "datetime", "timestamp")
        c_ll = _pick(cols, "latlong", "lat_long", "geo_point", "geopoint")
        c_temp = _pick(cols, "airtemperature", "air_temp", "temperature", "ambient")
        c_type = _pick(cols, "type", "parameter", "param")
        c_val = _pick(cols, "value", "reading")
        for r in rd:
            try:
                sid = r[c_id]
                t = _parse_ts(r[c_ts])
                if t is None:
                    continue
                if c_type and c_val:                       # format long
                    if "temp" not in str(r[c_type]).lower():
                        continue
                    val = float(r[c_val])
                elif c_temp:                               # format large
                    val = float(r[c_temp])
                else:
                    continue
            except (ValueError, KeyError, TypeError):
                continue
            if not (-20.0 <= val <= 60.0):
                continue
            raw[sid].append((t, val))
            if c_ll and sid not in emb and r.get(c_ll):
                try:
                    a, b = str(r[c_ll]).strip('"[]() ').split(",")[:2]
                    emb[sid] = (float(a), float(b))
                except ValueError:
                    pass

    # positions : embarquees en priorite, sinon fichier de positions
    pos_ll = emb
    if not pos_ll and locations_csv:
        with _open(locations_csv) as f:
            rd = csv.DictReader(f, delimiter=_sniff(f))
            cols = rd.fieldnames or []
            c_id = _pick(cols, "site_id", "sensor_id", "id")
            c_lat = _pick(cols, "latitude", "lat")
            c_lon = _pick(cols, "longitude", "lon", "lng")
            for r in rd:
                try:
                    pos_ll[r[c_id]] = (float(r[c_lat]), float(r[c_lon]))
                except (ValueError, KeyError, TypeError):
                    continue
    if not pos_ll:
        raise ValueError("positions introuvables (ni LatLong embarque, ni fichier positions)")

    # projection equirectangulaire locale (metres) autour du barycentre
    lat0 = sum(a for a, _ in pos_ll.values()) / len(pos_ll)
    lon0 = sum(b for _, b in pos_ll.values()) / len(pos_ll)
    m_per_deg = 111320.0
    pos = {s: ((lon - lon0) * m_per_deg * _m.cos(_m.radians(lat0)),
               (lat - lat0) * m_per_deg) for s, (lat, lon) in pos_ll.items()}
    raw = {s: lst for s, lst in raw.items() if s in pos}

    all_t = sorted(t for lst in raw.values() for (t, _) in lst)
    if all_t:
        t0 = all_t[len(all_t) // 2]
        raw = {s: [(t, v) for (t, v) in lst if t0 <= t < t0 + span] for s, lst in raw.items()}
        raw = {s: lst for s, lst in raw.items() if lst}
    return _finalize(pos, raw)


def _sniff(f):
    """Detecte le delimiteur (',' ou ';') sur la 1ere ligne, puis rembobine."""
    pos = f.tell()
    line = f.readline()
    f.seek(pos)
    return ";" if line.count(";") > line.count(",") else ","


def make_synthetic(n=30, area=100.0, duration=3600.0, dt=31.0, n_clusters=6, seed=0):
    """Repli : trace synthetique geolocalisee (champ lisse par grappes + bruit),
    pour tester le pipeline sans fichier reel. Correlation spatiale reelle presente."""
    import random
    rng = random.Random(seed)
    centers = [(rng.uniform(0, area), rng.uniform(0, area)) for _ in range(n_clusters)]
    base = [rng.uniform(15, 30) for _ in range(n_clusters)]
    pos, raw = {}, defaultdict(list)
    for sid in range(n):
        c = sid % n_clusters
        cx, cy = centers[c]
        x = min(max(rng.gauss(cx, area * 0.05), 0), area)
        y = min(max(rng.gauss(cy, area * 0.05), 0), area)
        pos[sid] = (x, y)
        t = 0.0
        while t < duration:
            drift = 2.0 * math.sin(2 * math.pi * t / 600.0)
            raw[sid].append((t, base[c] + drift + rng.gauss(0, 0.3)))
            t += dt
    return _finalize(pos, raw)


# ---------------------------------------------------------------------------
# Simulateur alimente par une trace reelle
# ---------------------------------------------------------------------------
class RealTraceSim(Simulator):
    def __init__(self, cfg, trace):
        self.trace = trace
        self._ids = sorted(trace["pos"])
        super().__init__(cfg)

    def _build_topology(self):
        cfg = self.cfg
        self.sensors = []
        for idx, sid in enumerate(self._ids):
            x, y = self.trace["pos"][sid]
            bat = cfg.battery_capacity_j * cfg.battery_init_frac
            s = Sensor(idx, x, y, 0, bat)
            s.sf = cfg.sf
            s.toa = time_on_air(s.sf)
            self.sensors.append(s)
        self.cluster_base = [0.0]          # inutilise en mode trace
        self.neighbors = defaultdict(list)
        for i in range(len(self.sensors)):
            xi, yi = self.sensors[i].x, self.sensors[i].y
            for j in range(len(self.sensors)):
                if i == j:
                    continue
                d = math.dist((xi, yi), (self.sensors[j].x, self.sensors[j].y))
                if d < 3 * cfg.sigma_d:
                    self.neighbors[i].append(j)

    def _lookup(self, idx, t):
        """Derniere mesure du capteur (indice idx) a l'instant t : (valeur, t_mesure)."""
        ts, vs = self.trace["series"][self._ids[idx]]
        k = bisect.bisect_right(ts, t) - 1
        if k < 0:
            k = 0
        return vs[k], ts[k]

    def sensor_value(self, s: Sensor, t: float) -> float:
        v, tg = self._lookup(s.sid, t)
        s.last_value = v
        s.last_gen_time = tg               # fraicheur = age depuis la vraie mesure
        return v

    def _field_value(self, s: Sensor, t: float) -> float:
        v, _ = self._lookup(s.sid, t)      # vraie valeur du capteur demande (erreur semantique)
        return v


def _infer_dt(trace):
    """Cadence d'echantillonnage (mediane des intervalles) du jeu de donnees."""
    diffs = []
    for ts, _ in trace["series"].values():
        diffs += [ts[i + 1] - ts[i] for i in range(len(ts) - 1) if ts[i + 1] > ts[i]]
    if not diffs:
        return 31.0
    diffs.sort()
    return max(1.0, diffs[len(diffs) // 2])


def run_trace(trace, strategy="FSEC", sigma_d=None, sf=7, seed=1, sim_time=None,
              sigma_v=0.8, sem_threshold=0.5, cache_size=None, ttl=None,
              fresh_lo=None, fresh_hi=None):
    """Lance une simulation sur la trace, avec des parametres CALES SUR LE JEU :
    - sigma_d      : 20 % de l'etendue spatiale (echelle du deploiement) ;
    - TTL          : 6 x la cadence d'echantillonnage (une donnee reste valide
                     quelques mesures) ;
    - fraicheur    : exigence tiree dans [1x, 3x] la cadence (physiquement tenable
                     vu que la donnee est intrinsequement agee de ~1 cadence) ;
    - cache        : la moitie du nombre de capteurs (cree une pression d'eviction,
                     condition pour que la reutilisation spatiale ait un sens).
    Ces choix ne favorisent aucune strategie : ils rendent la comparaison equitable
    au regard de la dynamique reelle des donnees."""
    xs = [p[0] for p in trace["pos"].values()]
    ys = [p[1] for p in trace["pos"].values()]
    extent = max(max(xs) - min(xs), max(ys) - min(ys), 1.0)
    n = len(trace["pos"])
    dt = _infer_dt(trace)
    sigma_d = 0.2 * extent if sigma_d is None else sigma_d
    ttl = 6.0 * dt if ttl is None else ttl
    fresh_lo = 1.0 * dt if fresh_lo is None else fresh_lo
    fresh_hi = 3.0 * dt if fresh_hi is None else fresh_hi
    cache_size = max(10, n // 2) if cache_size is None else cache_size
    sim_time = sim_time or min(3600.0, trace["duration"] or 3600.0)
    cfg = Config(strategy=strategy, n_sensors=n, sf=sf, seed=seed, sim_time=sim_time,
                 sigma_d=sigma_d, sigma_v=sigma_v, sem_threshold=sem_threshold,
                 cache_size=cache_size, ttl=ttl,
                 freshness_req_min=fresh_lo, freshness_req_max=fresh_hi)
    sim = RealTraceSim(cfg, trace)
    m = sim.run()
    m.update({"sigma_d": sigma_d, "extent": extent, "n_sensors": n,
              "dt": dt, "ttl": ttl, "cache_size": cache_size})
    return m


def _report(trace, label):
    print(f"\n===== {label} : {len(trace['pos'])} capteurs, "
          f"duree {trace['duration']:.0f}s =====")
    xs = [p[0] for p in trace["pos"].values()]
    ys = [p[1] for p in trace["pos"].values()]
    dt = _infer_dt(trace)
    print(f"etendue spatiale : {max(xs)-min(xs):.1f} x {max(ys)-min(ys):.1f} (unites du jeu) | "
          f"cadence dt≈{dt:.0f}s -> TTL={6*dt:.0f}s, cache={max(10,len(trace['pos'])//2)}, "
          f"sigma_d={0.2*max(max(xs)-min(xs),max(ys)-min(ys)):.1f}")
    print(f"{'strategie':10} {'CHR':>7} {'(sem)':>7} {'FHR':>7} {'EUB':>9} "
          f"{'semMAE':>8} {'semP95':>8}")
    for strat in ["FSEC", "LRU"]:
        ms = [run_trace(trace, strategy=strat, seed=s) for s in range(5)]
        def avg(k): return sum(x[k] for x in ms) / len(ms)
        print(f"{strat:10} {avg('CHR'):7.1f} {avg('CHR_sem'):7.1f} {avg('FHR'):7.1f} "
              f"{avg('EUB'):9.4f} {avg('sem_mae'):8.3f} {avg('sem_p95'):8.3f}")


def main(argv):
    if len(argv) >= 4 and argv[1] == "intel":
        field = argv[4] if len(argv) > 4 else "temperature"
        trace = load_intel_lab(argv[2], argv[3], field)
        _report(trace, f"Intel Berkeley Lab ({field})")
    elif len(argv) >= 4 and argv[1] == "melbourne":
        # argv[2] = readings.csv, argv[3] = locations.csv
        trace = load_melbourne(argv[2], argv[3], "temperature")
        _report(trace, "City of Melbourne microclimate (exterieur, temperature)")
    elif len(argv) >= 3 and argv[1] == "csv":
        trace = load_generic_csv(argv[2])
        _report(trace, "CSV generique")
    else:
        print("Aucun fichier fourni -> repli synthetique (test du pipeline).")
        trace = make_synthetic()
        _report(trace, "Trace synthetique (repli)")


if __name__ == "__main__":
    main(sys.argv)
