"""Synoptic Data: Windstationen im Umkreis der Reviere suchen, Juli 2026 zur Auswahl laden.
Token aus ~/.config/synoptic_token (nie ins Repo)."""
import json, os, sys, time, requests
Q = os.path.dirname(os.path.abspath(__file__))
TOK = open(os.path.expanduser("~/.config/synoptic_token")).read().strip().strip('"')
API = "https://api.synopticdata.com/v2/"
SPOTS = {
 'Silvaplana': (46.45, 9.79), 'Reschensee': (46.80, 10.53), 'Comer See Nord': (46.13, 9.33), 'Gardasee Nord': (45.86, 10.86),
 'Tarifa': (36.03, -5.62), 'Talamone': (42.55, 11.13), 'Porto Pollo': (41.19, 9.32), 'Lo Stagnone': (37.86, 12.45),
 'Rhodos Ialysos': (36.42, 28.15), 'Rhodos Prasonisi': (35.89, 27.77), 'Kos Marmari': (36.79, 27.06),
 'Karpathos Gun Bay': (35.42, 27.15), 'Naxos': (37.08, 25.37), 'Paros': (37.04, 25.06), 'Almanarre': (43.06, 6.13),
 'Leucate': (42.91, 3.05), 'Sylt': (54.91, 8.30), 'Fehmarn': (54.45, 11.10), 'Neusiedler See': (47.88, 16.77),
 'Essaouira': (31.49, -9.77), 'El Gouna': (27.40, 33.68), 'Dahab': (28.49, 34.51), 'Sotavento': (28.13, -14.23),
 'Sal Santa Maria': (16.60, -22.90), 'Bol': (43.26, 16.65), 'Split': (43.50, 16.40), 'Bodensee': (47.62, 9.40),
 'Genfer See': (46.45, 6.60), 'Lago Maggiore': (46.10, 8.75), 'Starnberger See': (47.90, 11.31), 'Ammersee': (48.00, 11.12),
 'El Medano': (28.05, -16.54), 'Pozo Izquierdo': (27.82, -15.42), 'Cumbuco': (-3.63, -38.73), 'Kapstadt Blouberg': (-33.81, 18.46),
 'Mauritius Le Morne': (-20.46, 57.31), 'Masirah': (20.41, 58.79), 'Boracay': (11.96, 121.93), 'Perth': (-31.95, 115.75),
 'Sydney': (-33.85, 151.25), 'Hood River': (45.71, -121.52), 'Sherman Island': (38.04, -121.75), 'Crissy Field': (37.81, -122.46),
 'Pacasmayo': (-7.40, -79.57), 'El Yaque': (10.90, -63.95), 'Barbados': (13.04, -59.52), 'Solent': (50.76, -1.30),
 'Annapolis': (38.97, -76.48), 'Miami': (25.73, -80.16), 'Barcelona': (41.38, 2.20), 'Mallorca Palma': (39.55, 2.70),
}
out = {}
for name, (la, lo) in SPOTS.items():
    r = requests.get(API + "stations/metadata", timeout=60, params=dict(
        token=TOK, radius="%s,%s,7" % (la, lo), vars="wind_speed", limit=12, complete=1,
        obrange="20260501,20260930")).json()
    st = r.get("STATION", [])
    out[name] = dict(lat=la, lon=lo, stationen=[dict(stid=s["STID"], name=s["NAME"], lat=float(s["LATITUDE"]),
        lon=float(s["LONGITUDE"]), mnet=s.get("MNET_ID"), restricted=s.get("RESTRICTED"),
        elev_ft=s.get("ELEVATION")) for s in st])
    print("%-20s %2d  %s" % (name, len(st), ", ".join("%s(%s)" % (s["STID"], s.get("MNET_ID")) for s in st[:8])), flush=True)
    time.sleep(0.3)
json.dump(out, open(os.path.join(Q, "synoptic_stationen.json"), "w"), indent=1, ensure_ascii=False)
