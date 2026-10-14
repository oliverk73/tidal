"""OSM-Auszug -> Kueste, Gewaesserflaechen, benannte Objekte (fuer Positions-/Namenspruefung)."""
import sys, json, osmium
from osmium.filter import KeyFilter
PBF, AUS = sys.argv[1], sys.argv[2]
NAMEN = ('name', 'name:ko-Latn', 'name:en', 'name:ko_rm', 'name:ko', 'old_name', 'alt_name', 'name:ko-Latn-alt', 'official_name:en')
def art(t):
    if t.get('place'): return 'place:' + t['place']
    if t.get('power') == 'plant': return 'power_plant'
    if t.get('amenity') == 'ferry_terminal': return 'ferry_terminal'
    if t.get('man_made') in ('pier', 'breakwater', 'quay', 'lighthouse'): return t['man_made']
    if t.get('harbour') or t.get('landuse') == 'harbour' or t.get('seamark:type') in ('harbour',): return 'harbour'
    if t.get('leisure') == 'marina': return 'marina'
    if t.get('natural') in ('bay', 'strait', 'cape', 'peninsula', 'beach'): return 'natural:' + t['natural']
    if t.get('bridge') and t.get('name'): return 'bridge'
    return None
kueste, wasser, objekte = [], [], []
fp = osmium.FileProcessor(PBF).with_locations().with_areas(KeyFilter('natural', 'waterway', 'landuse', 'place', 'power', 'harbour', 'leisure', 'amenity', 'man_made', 'water'))
for o in fp:
    t = dict(o.tags)
    if not t: continue
    if o.is_way() and t.get('natural') == 'coastline':
        try: kueste.append([(n.lat, n.lon) for n in o.nodes])
        except osmium.InvalidLocationError: pass
        continue
    if o.is_area():
        istwasser = t.get('natural') == 'water' or t.get('waterway') == 'riverbank' or t.get('landuse') in ('reservoir', 'basin')
        if istwasser or art(t):
            ringe = []
            for r in o.outer_rings():
                ringe.append([(n.lat, n.lon) for n in r])
            if istwasser:
                wasser.append(dict(ringe=ringe, typ=t.get('water') or t.get('natural') or t.get('waterway'), name=t.get('name', '')))
            a = art(t)
            if a and any(k in t for k in NAMEN):
                pts = [p for r in ringe for p in r]
                if pts:
                    objekte.append(dict(art=a, lat=sum(p[0] for p in pts) / len(pts), lon=sum(p[1] for p in pts) / len(pts),
                                        namen={k: t[k] for k in NAMEN if k in t}))
        continue
    if o.is_node():
        a = art(t)
        if a and any(k in t for k in NAMEN):
            objekte.append(dict(art=a, lat=o.location.lat, lon=o.location.lon, namen={k: t[k] for k in NAMEN if k in t}))
    elif o.is_way() and not o.is_closed():
        a = art(t)
        if a and any(k in t for k in NAMEN):
            try:
                pts = [(n.lat, n.lon) for n in o.nodes]
                objekte.append(dict(art=a, lat=sum(p[0] for p in pts) / len(pts), lon=sum(p[1] for p in pts) / len(pts), namen={k: t[k] for k in NAMEN if k in t}))
            except osmium.InvalidLocationError: pass
json.dump(dict(kueste=kueste, wasser=wasser, objekte=objekte), open(AUS, 'w'), ensure_ascii=False)
print(len(kueste), 'Kuestenwege', len(wasser), 'Gewaesserflaechen', len(objekte), 'benannte Objekte')
