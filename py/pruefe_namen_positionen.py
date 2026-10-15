"""Positions- und Namenspruefung gegen den OSM-Auszug (+ GeoNames).

Position: Land/Meer ueber die OSM-Kuestenlinie (Land links der Wegrichtung),
Gewaesserflaechen (Fluesse, Becken) zaehlen als Wasser.
Name: Wo liegt das, was der Name bezeichnet? Abstand zum naechsten passenden Objekt.
"""
import json, math, re, sys, os, difflib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '/home/oliver/weather/py')
from hangul_rr import rr, hat_hangul

ROOT = '/home/oliver/weather'
# Landesregeln. Korea ist an Olivers Korrekturen geeicht (14.10.2026); andere Laender erst nach Eichung ernst nehmen.
LAENDER = {
    'South Korea': dict(iso='KR', auszug='kr_auszug.json', koreanisch=True,
                        gattung=r'(hang|gang|do|to|ri|ni|li|dong|man|wan|sudo|haehyeop|hae|po|seom|gundo|yeolto|budu|eup|myeon|gun|si)$'),
    'Philippines': dict(iso='PH', auszug='ph_auszug.json', koreanisch=False, gattung=r'(?!)'),
    'Indonesia': dict(iso='ID', auszug='id_auszug.json', koreanisch=False, gattung=r'(?!)'),
    'Japan': dict(iso='JP', auszug='jp_auszug.json', koreanisch=False, gattung=r'(?!)'),
    'Vietnam': dict(iso='VN', auszug='vn_auszug.json', koreanisch=False, gattung=r'(?!)'),
    'Thailand': dict(iso='TH', auszug='th_auszug.json', koreanisch=False, gattung=r'(?!)'),
    'Malaysia': dict(iso='MY', auszug='mysgbn_auszug.json', koreanisch=False, gattung=r'(?!)'),
    'Singapore': dict(iso='SG', auszug='mysgbn_auszug.json', koreanisch=False, gattung=r'(?!)'),
    'Brunei': dict(iso='BN', auszug='mysgbn_auszug.json', koreanisch=False, gattung=r'(?!)'),
    'Myanmar': dict(iso='MM', auszug='mm_auszug.json', koreanisch=False, gattung=r'(?!)'),
    'Cambodia': dict(iso='KH', auszug='kh_auszug.json', koreanisch=False, gattung=r'(?!)'),
    'China': dict(iso='CN', auszug='cn_auszug.json', koreanisch=False, gattung=r'(?!)'),
}
LAND = os.environ.get('PRUEF_LAND') or (sys.argv[1] if __name__ == '__main__' and len(sys.argv) > 1 else 'South Korea')
CFG = LAENDER[LAND]
A = json.load(open(os.environ.get('OSM_AUSZUG', ROOT + '/harmonics/help/osm/' + CFG['auszug'])))
ZELLE = 0.05

def xy(lat0, lat, lon):
    return ((lon) * 111320 * math.cos(math.radians(lat0)), lat * 110574)

def m(a, b):  # Meter
    return math.hypot((a[0] - b[0]) * 110574, (a[1] - b[1]) * 111320 * math.cos(math.radians(a[0])))

# --- Kuestenindex
SEG = {}
for w in A['kueste']:
    for i in range(len(w) - 1):
        a, b = w[i], w[i + 1]
        for c in {(int(a[0] / ZELLE), int(a[1] / ZELLE)), (int(b[0] / ZELLE), int(b[1] / ZELLE))}:
            SEG.setdefault(c, []).append((a, b))

def kueste(lat, lon):
    """-> (abstand_m, 'land'|'wasser') zur naechsten Kuestenlinie."""
    ci, cj = int(lat / ZELLE), int(lon / ZELLE)
    best = None
    for r in range(0, 6):
        for i in range(ci - r, ci + r + 1):
            for j in range(cj - r, cj + r + 1):
                if max(abs(i - ci), abs(j - cj)) != r: continue
                for a, b in SEG.get((i, j), ()):
                    px, py = xy(lat, lat, lon); ax, ay = xy(lat, *a); bx, by = xy(lat, *b)
                    dx, dy = bx - ax, by - ay; L = dx * dx + dy * dy
                    t = 0 if L == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L))
                    qx, qy = ax + t * dx, ay + t * dy
                    d = math.hypot(px - qx, py - qy)
                    cross = dx * (py - ay) - dy * (px - ax)
                    if best is None or d < best[0] - 0.01:
                        best = (d, cross, t)
                    elif abs(d - best[0]) <= 0.01 and abs(cross) > abs(best[1]):
                        best = (d, cross, t)
        if best and best[0] < r * ZELLE * 90000:
            break
    if best is None:
        return 99999, 'wasser'
    return best[0], 'land' if best[1] > 0 else 'wasser'

# --- Gewaesserflaechen
WAS = []
for w in A['wasser']:
    for ring in w['ringe']:
        if len(ring) < 4: continue
        la = [p[0] for p in ring]; lo = [p[1] for p in ring]
        WAS.append((min(la), max(la), min(lo), max(lo), ring, w['typ'], w['name']))

def im_gewaesser(lat, lon):
    for s, n, w, e, ring, typ, name in WAS:
        if s <= lat <= n and w <= lon <= e:
            inside = False
            for i in range(len(ring) - 1):
                (y1, x1), (y2, x2) = ring[i], ring[i + 1]
                if (y1 > lat) != (y2 > lat) and lon < x1 + (lat - y1) * (x2 - x1) / (y2 - y1):
                    inside = not inside
            if inside:
                return typ or 'water', name
    return None

# --- Infrastruktur (benannt aus Auszug, unbenannt aus Overpass-Cache)
INFRA = [(o['lat'], o['lon']) for o in A['objekte'] if o['art'] in ('harbour', 'pier', 'breakwater', 'quay', 'ferry_terminal', 'marina', 'power_plant', 'lighthouse')]
try:
    INFRA += [(h['lat'], h['lon']) for h in json.load(open(ROOT + '/harmonics/help/geonames/osm_haefen_%s.json' % CFG['iso']))['haefen']]
except Exception:
    pass

def infra_abstand(lat, lon):
    return min((m((lat, lon), p) for p in INFRA if abs(p[0] - lat) < 0.1 and abs(p[1] - lon) < 0.1), default=99999)

# --- Namen
def norm(s):
    return re.sub(r'[^a-z0-9]', '', s.lower())

def skelett(s):
    s = norm(s)
    for a, b in (('eo', 'o'), ('eu', 'u'), ('ae', 'e'), ('oe', 'e'), ('yeo', 'yo'), ('kk', 'k'), ('g', 'k'), ('b', 'p'), ('d', 't'), ('j', 'ch'), ('r', 'l'), ('chh', 'ch'), ('ss', 's')):
        s = s.replace(a, b)
    return s

OBJ = []
for o in A['objekte']:
    v = set()
    for k, n in o['namen'].items():
        if hat_hangul(n):
            v.add(norm(rr(n)))
        elif re.match(r'^[\x00-\x7fÀ-ɏʼ’\s]+$', n):
            v.add(norm(n))
    # Anlagen (Kraftwerk, Hafen): auch das erste Namenswort ("Hanbit" aus "Hanbit Nuclear Power Site")
    if o['art'] in ('power_plant', 'harbour', 'ferry_terminal', 'marina', 'pier', 'quay'):
        for k_ in ('name:en', 'name:ko-Latn'):
            w_ = o['namen'].get(k_, '').split()
            if len(w_) > 1 and len(norm(w_[0])) >= 4:
                v.add(norm(w_[0]))
    v.discard('')
    lat_name = o['namen'].get('name:ko-Latn') or o['namen'].get('name:en') or (rr(o['namen']['name']) if 'name' in o['namen'] and hat_hangul(o['namen']['name']) else o['namen'].get('name', ''))
    _ko = o['namen'].get('name:ko') or o['namen'].get('name', '')
    _ko = _ko if hat_hangul(_ko) and ' ' not in _ko else ''
    OBJ.append(dict(art=o['art'], lat=o['lat'], lon=o['lon'], v=v, sk={skelett(x) for x in v}, anzeige=lat_name, ko=o['namen'].get('name', ''),
                    rrs={x for k_ in ('name', 'name:ko', 'alt_name', 'old_name') for h_ in [o['namen'].get(k_, '')] if hat_hangul(h_) and ' ' not in h_ and len(h_) > 1
                         for x in (norm(rr(h_)), norm(rr(h_[:-1]) + rr(h_[-1])))}, rr=norm(rr(o['namen'].get('name:ko') or o['namen'].get('name', ''))) if hat_hangul(o['namen'].get('name:ko') or o['namen'].get('name', '')) else ''))
try:
    from positionen_geonames import geonames
    for g in geonames(CFG['iso']):
        art = {'P': 'place:gn', 'T': 'island:gn' if g['fcode'].startswith('ISL') else 'terrain:gn', 'H': 'water:gn', 'L': 'area:gn', 'S': 'spot:gn'}.get(g['fcl'])
        if art:
            OBJ.append(dict(art=art, lat=g['lat'], lon=g['lon'], v=set(g['namen']), sk={skelett(x) for x in g['namen']}, anzeige=g['name'], ko='', rr='', rrs=set()))
except Exception as e:
    print('GeoNames fehlt', e)

GATTUNG = CFG['gattung']
GENERISCH = {'bay', 'point', 'island', 'islands', 'isla', 'river', 'entrance', 'channel', 'strait', 'sound', 'gulf', 'city', 'north', 'south',
             'east', 'west', 'pier', 'wharf', 'cove', 'reef', 'islet', 'head', 'cape', 'punta', 'the', 'of', 'de', 'del', 'light', 'anchorage',
             'passage', 'lagoon', 'creek', 'mouth', 'inner', 'outer', 'approach', 'poblacion', 'puerto', 'port',
             # Indonesisch (15.10.2026): Pulau, Teluk, Tanjung, Selat, Pelabuhan, Muara, Sungai ...
             'pulau', 'teluk', 'tanjung', 'tg', 'selat', 'pelabuhan', 'muara', 'sungai', 'kepulauan', 'pantai'} | {'sinhang', 'naehang', 'oehang', 'bukhang', 'guhang', 'je1budu', 'dongbudu', 'bangpaje', 'bangjoje', 'daegyo', 'deungdae',
             'powerplant', 'power', 'plant', 'port', 'harbor', 'harbour', 'bridge', 'jejudo', 'busan'}

def treffer(tok, lat, lon, radius_km=40):
    t, tg = norm(tok), re.sub(GATTUNG, '', norm(tok))
    sk, skg = skelett(t), skelett(tg)
    out = []
    for o in OBJ:
        if abs(o['lat'] - lat) > radius_km / 111 or abs(o['lon'] - lon) > radius_km / 90: continue
        if t in o['v'] or (len(tg) >= 4 and any(x == tg or re.sub(GATTUNG, '', x) in (tg, t) for x in o['v'])) or any(re.sub(GATTUNG, '', x) == t for x in o['v'] | o.get('rrs', set())):
            q = 'exakt'
        elif sk in o['sk'] or (len(skg) >= 4 and any(re.sub(GATTUNG, '', x) == skg for x in o['sk'])):
            q = 'umschrift'
        else:
            continue
        out.append((m((lat, lon), (o['lat'], o['lon'])), q, o))
    out.sort(key=lambda x: x[0])
    return out

ORTSART = ('place:', 'island', 'harbour', 'ferry_terminal', 'power_plant', 'pier', 'marina')

def was_liegt_hier(lat, lon):
    k = []
    for o in OBJ:
        if abs(o['lat'] - lat) > 0.03 or abs(o['lon'] - lon) > 0.04: continue
        if not o['art'].startswith(ORTSART) or o['art'] in ('place:county', 'place:province', 'place:state', 'place:city', 'place:sea', 'place:ocean', 'place:region', 'place:gn'):
            continue
        k.append((m((lat, lon), (o['lat'], o['lon'])), o))
    k.sort(key=lambda x: x[0])
    return k[:4]

def teile(name):
    basis = name.split(',')[0]
    haupt = re.sub(r'\s*\(.*?\)', '', basis).strip()
    klammer = re.findall(r'\((.*?)\)', basis)
    return haupt, klammer

INFRA_ART = ('harbour', 'pier', 'breakwater', 'quay', 'ferry_terminal', 'marina', 'power_plant')

def ziel_vorschlag(lat, lon, toks):
    """Anleger/Hafen, dessen Name zum Satz passt (bis 3 km), sonst naechste Infrastruktur bis 1.5 km."""
    k = []
    for o in OBJ:
        if o['art'] not in INFRA_ART or abs(o['lat'] - lat) > 0.04 or abs(o['lon'] - lon) > 0.05: continue
        d0 = m((lat, lon), (o['lat'], o['lon']))
        passt = any(len(re.sub(GATTUNG, '', norm(t))) >= 3 and re.sub(GATTUNG, '', norm(t)) in ' '.join(o['v'] | {o['rr']}) for t in toks)
        k.append((0 if passt else 1, d0, o))
    k = [x for x in k if (x[0] == 0 and x[1] <= 3000) or x[1] <= 1500]
    if not k: return None
    k.sort(key=lambda x: (x[0], x[1]))
    p, d0, o = k[0]
    return '%s %s [%s] %.4f/%.4f %dm%s' % (o['anzeige'], o['ko'], o['art'], o['lat'], o['lon'], d0, ' (Name passt)' if p == 0 else '')

GRENZE = {'place:city': 6000, 'place:town': 4000}
LAND_M, MEER_M, MEER_INFRA_M = 100, 300, 500
HAND_GROB_M = 1000   # von Hand gesetzte Positionen nur noch bei groben Fehlern melden

def hand_positionen():
    """Saetze, deren Position von Hand geaendert wurde (positions_locked.csv, provenance manual).
    Oliver 15.10.2026: bereits korrigierte Positionen nicht noch einmal zur Pruefung vorlegen."""
    import csv as _csv
    try:
        return {r['name'] for r in _csv.DictReader(open(ROOT + '/harmonics/help/positions_locked.csv', encoding='utf-8'))
                if r.get('provenance') == 'manual' and (r.get('moved_m') or '').strip() not in ('', '0')}
    except OSError:
        return set()
HAND = set()
URSPRUNG = {}   # name -> (lat, lon) der ersten eingecheckten Fassung (meist der Buchwert)

def ursprung():
    import csv as _csv
    out = {}
    try:
        for r in _csv.DictReader(open(ROOT + '/harmonics/help/positions_locked.csv', encoding='utf-8')):
            if (r.get('orig_lat') or '').strip():
                out[r['name']] = (float(r['orig_lat']), float(r['orig_lon']))
    except (OSError, ValueError):
        pass
    return out

def pruefe(name, lat, lon):
    z = dict(satz=name, lat=lat, lon=lon, befunde=[], hinweise='')
    d, seite = kueste(lat, lon)
    gew = im_gewaesser(lat, lon) if seite == 'land' else None
    inf = infra_abstand(lat, lon)
    z.update(kueste_m=round(d), seite=seite, gewaesser=gew[0] if gew else '', infra_m=round(inf))
    haupt, klammer = teile(name)
    toks = [t for t in re.split(r'\s+', haupt) if norm(t) not in GENERISCH and len(norm(t)) >= 3]
    pos = None
    hand = name in HAND
    if hand and d <= HAND_GROB_M:
        pass
    elif seite == 'land' and not gew and d > LAND_M and inf > 50:
        pos = 'LAND %d m hinter der Kueste' % d
    # Weit draussen entwarnt eine Mole in der Naehe nur bei von Hand gesetzten Punkten (Pierende, Daesan);
    # Mittelpunkte langer Piers liegen weit vom Pierende, darum zaehlt dort die Handarbeit.
    elif seite == 'wasser' and d > MEER_M and (inf > MEER_INFRA_M or (d > 600 and __import__('health_check').auf_raster(lat, lon))):
        pos = 'MEER %d m vor der Kueste, naechste Hafenanlage %d m' % (d, inf)
    # Feinschliff nur fuer gerundete Buchpositionen; von Hand gesetzte Positionen gelten als geprueft
    from health_check import auf_raster
    if not pos and not hand and seite == 'wasser' and d > 100 and auf_raster(lat, lon):
        v = ziel_vorschlag(lat, lon, toks)
        if v and re.search(r'\[(ferry_terminal|harbour|pier|quay|marina)\]', v) and int(re.search(r'(\d+)m', v.split(']')[1]).group(1)) <= 1000:
            z['befunde'].append('ANLEGER in der Naehe (Punkt %d m vor der Kueste); Vorschlag %s' % (d, v))
    if pos:
        v = ziel_vorschlag(lat, lon, toks)   # Klammer ist nur Kontext, kein Ziel (Oliver 15.10.2026)
        z['befunde'].append(pos + ('; Vorschlag ' + v if v else '; kein Hafen in der Naehe'))
    # Name: mindestens ein Teil (ganzer Name, Klammer, einzelne Woerter) muss nah liegen
    teile_ = [haupt] + klammer + toks
    naechste = {}
    for t in dict.fromkeys(teile_):
        tr = treffer(t, lat, lon)
        naechste[t] = tr[0] if tr else None
    def grenze(t, o):
        if o['art'] in ('water:gn', 'natural:bay', 'natural:strait'):
            return 12000   # Bucht/Kanal/Bank: GeoNames/OSM setzen den Mittelpunkt, der Pegel liegt am Rand (Philippinen 15.10.2026)
        if 'island' in o['art'] or re.search(r'(do|seom|to)$', norm(t)):
            return 10000   # Inseln: Abstand zur Inselmitte, Station liegt an der Kueste
        if norm(t) in {norm(x) for x in toks[:1]} and any(norm(w) in GENERISCH for w in haupt.split()):
            return 15000   # "Gunsan Naehang/Oehang": Stadt als Vorsatz vor einer Hafenbezeichnung (Aussenhafen liegt weit draussen)
        return GRENZE.get(o['art'], 2500)
    nah = [t for t, x in naechste.items() if x and x[0] <= grenze(t, x[2])]
    if not nah:
        # Klammerinhalt (Bucht, Insel als Kontext) begruendet keinen Befund "passt nicht" (Camayan (Subic Bay))
        gefunden = [(t, x) for t, x in naechste.items() if x and t not in klammer]
        if gefunden:
            t, (d0, q, o) = min(gefunden, key=lambda tx: tx[1][0])
            txt = 'NAME passt nicht zur Position: "%s" liegt %.1f km entfernt (%s %s)' % (t, d0 / 1000, o['art'], o['anzeige'])
            # Buchwerte sind auf Minuten gerundet (+-1 km): liegt das gleichnamige Objekt nahe der urspruenglichen
            # Position, ist es gemeint (Lugmayan Point 15.10.2026: 1.4 km vom Buchwert, Pegel war 7 km verschoben)
            u = URSPRUNG.get(name)
            if u:
                du = m(u, (o['lat'], o['lon']))
                if du <= 2500:
                    txt += '; liegt %.1f km von der urspruenglichen Position %.4f/%.4f -> Vorschlag %.4f/%.4f' % (du / 1000, u[0], u[1], o['lat'], o['lon'])
            z['befunde'].append(txt)
        else:
            spez = haupt   # gesucht wird der Name vor der Klammer
            nahobj = [o for o in OBJ if abs(o['lat'] - lat) < 0.05 and abs(o['lon'] - lon) < 0.06 and m((lat, lon), (o['lat'], o['lon'])) < 5000]
            cand = difflib.get_close_matches(norm(spez), [x for o in nahobj for x in o['v'] | {o['rr']}], n=1, cutoff=0.75)
            hint = ''
            if cand:
                o = next(o for o in nahobj if cand[0] in o['v'] | {o['rr']})
                hint = ' (aehnlich: %s %s)' % (o['anzeige'], o['ko'])
            z['befunde'].append('NAME nicht gefunden: "%s"%s' % (spez, hint))
    else:
        # Vorangestellter Ort weit weg (z. B. "Gunsan Yeondo"): nur Hinweis
        if len(toks) >= 2 and naechste.get(toks[0]) and naechste[toks[0]][0] > 6000:
            z['hinweise'] = 'Vorsatz "%s" %.1f km entfernt' % (toks[0], naechste[toks[0]][0] / 1000)
        # Umschrift: Namensteile gegen die RR-Form passender OSM-Objekte in Landesschrift.
        # Gleich, wenn Stamm gleich und die Endung eine RR-Endung ist (do, ri, hang ...; nicht to, ni, kang).
        hier = was_liegt_hier(lat, lon)
        for t in (nah if CFG['koreanisch'] else []):   # OSM fuehrt auch name:ko fuer Orte im Ausland (Bacolod = 바콜로드)
            nt = norm(t)
            if any(w.lower() in ('power', 'plant', 'port', 'bridge') for w in t.split()):
                continue
            kand = [o for d0, q, o in treffer(t, lat, lon)[:6] if o['rrs'] and d0 <= 3000 and o['art'] not in INFRA_ART]
            kand += [o for d0, o in hier if o['rrs'] and o['art'] not in INFRA_ART and max(difflib.SequenceMatcher(None, nt, r).ratio() for r in o['rrs']) >= 0.7]
            if not kand:
                continue
            endung = re.search(GATTUNG, nt)
            rr_endung = not endung or endung.group(1) in ('hang', 'gang', 'do', 'ri', 'dong', 'man', 'sudo', 'haehyeop', 'hae', 'po', 'seom', 'gundo', 'yeolto', 'budu', 'eup', 'myeon', 'gun', 'si')
            def gleich(o):
                return any(nt == r or r.startswith(nt) or nt.startswith(r) or
                           (rr_endung and re.sub(GATTUNG, '', nt) == re.sub(GATTUNG, '', r)) for r in o['rrs'])
            if not any(gleich(o) for o in kand):
                o = kand[0]
                z['befunde'].append('UMSCHRIFT "%s" -- %s = %s' % (t, o['ko'], sorted(o['rrs'], key=len)[-1]))
                break
        # Nur Stadt-/Kreisname, kein Ortsteil (z. B. "Incheon" -> "Incheon (Wolmido)")
        if CFG['koreanisch'] and not klammer and len(toks) == 1 and toks[0] == haupt and not re.search(GATTUNG, norm(haupt)):
            stadt = [o for d0, q, o in treffer(toks[0], lat, lon) if o['art'] in ('place:city', 'place:town', 'place:county') and q == 'exakt']
            if stadt:
                z['befunde'].append('NAME nur Stadt/Kreis "%s" (%s) -- Ortsteil ergaenzen? hier: %s' % (haupt, stadt[0]['anzeige'], '; '.join('%s %s' % (o['anzeige'], o['ko']) for _, o in hier[:2])))
    if re.search(r'(-sudo|haehyeop)$', haupt) and not klammer:
        z['befunde'].append('GEWAESSERNAME "%s" (Insel/Ort vorschlagen)' % haupt)
    z['hier'] = '; '.join('%s %s [%s] %dm' % (o['anzeige'], o['ko'], o['art'], d0) for d0, o in was_liegt_hier(lat, lon))
    return z

def html(zeilen, land, pfad):
    import html as H
    GRUPPEN = [('KOPIE', 'Identische Tafel (Kopie)'), ('AEHNLICH', 'Aehnlicher Satz am selben Ort/Namen (andere Quelle) -- Qualitaet vergleichen'),
               ('PRUEFEN', 'Gleicher Ort/Name, Kurven widersprechen sich'),
               ('ZEIT', 'Tidenzeiten gegen die Landesquelle verschoben (FES erklaert es nicht)'),('LAND', 'Position an Land'), ('MEER', 'Position auf dem Meer'), ('NAME passt', 'Name passt nicht zur Position'),
               ('NAME nicht', 'Name nicht gefunden'), ('NAME nur', 'Nur Stadt-/Kreisname, Ortsteil fehlt'), ('UMSCHRIFT', 'Umschrift weicht von RR ab'),
               ('GEWAESSER', 'Gewaessername statt Insel/Ort'), ('ANLEGER', 'Anleger in der Naehe (Feinschliff, niedrige Prioritaet)')]
    osm = lambda la, lo: 'https://www.openstreetmap.org/?mlat=%.5f&mlon=%.5f#map=16/%.5f/%.5f' % (la, lo, la, lo)
    out = ['<!doctype html><meta charset="utf-8"><title>Pruefliste %s</title><style>body{font:14px sans-serif;margin:16px;max-width:1100px}'
           'td{padding:3px 6px;border-bottom:1px solid #ddd;vertical-align:top}h2{margin-top:28px}</style>' % H.escape(land),
           '<h1>Pruefliste %s</h1><p>%d Saetze, %d mit Befund. Links: OSM an der Station / am Vorschlag.</p>' % (H.escape(land), len(zeilen), sum(1 for z in zeilen if z['befunde']))]
    for k, titel in GRUPPEN:
        rows = [(z, b) for z in zeilen for b in z['befunde'] if b.startswith(k)]
        if not rows: continue
        out.append('<h2>%s (%d)</h2><table>' % (titel, len(rows)))
        for z, b in rows:
            v = re.search(r'(-?\d+\.\d{4})/(-?\d+\.\d{4})', b.split('Vorschlag', 1)[1]) if 'Vorschlag' in b else None
            out.append('<tr><td><a href="%s">%s</a></td><td>%s%s</td><td style="color:#666">%s</td></tr>' % (
                osm(z['lat'], z['lon']), H.escape(z['satz']), H.escape(b),
                ' &rarr; <a href="%s">Vorschlag</a>' % osm(float(v.group(1)), float(v.group(2))) if v else '', H.escape(z['hier'][:160])))
        out.append('</table>')
    open(pfad, 'w', encoding='utf-8').write('\n'.join(out))

if __name__ == '__main__':
    # python3 py/pruefe_namen_positionen.py "South Korea"   (OSM_AUSZUG=... fuer andere Laender)
    from health_check import load_records
    from datetime import date
    land = sys.argv[1]
    import subprocess
    subprocess.run([sys.executable, os.path.join(ROOT, 'py/positions_lock.py')], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    HAND = hand_positionen()
    URSPRUNG = ursprung()
    rs = [r for r in load_records() if r['name'].endswith(', ' + land) and not r['current'] and r['lat'] is not None]
    zeilen = [pruefe(r['name'], r['lat'], r['lon']) for r in sorted(rs, key=lambda r: r['name'])]
    for z, r in zip(zeilen, sorted(rs, key=lambda r: r['name'])):
        z['datei'] = r['file']
    # Duplikate ueber Ort/Name und Tidenkurve
    # Nur Inselname, obwohl auf der Insel ein weiterer Pegel steht (Jindo -> Uisin-myeon (Jindo))
    def kennwort(n_):
        return {re.sub(GATTUNG, '', norm(w_)) for w_ in re.split(r"[\s(),/]+", n_.rsplit(',', 1)[0]) if len(norm(w_)) >= 3}
    for z in zeilen:
        haupt_, klammer_ = teile(z['satz'])
        if not CFG['koreanisch'] or klammer_ or ' ' in haupt_ or not re.search(r'(do|seom)$', norm(haupt_)):
            continue
        w_ = re.sub(GATTUNG, '', norm(haupt_))
        andere = [y['satz'] for y in zeilen if y is not z and w_ in kennwort(y['satz'])
                  and math.hypot(y['lat'] - z['lat'], (y['lon'] - z['lon']) * 0.82) < 0.2]   # ~20 km: Kreisname (Wando Sadong) zaehlt nicht
        if len(andere) >= 1:   # schon ein weiterer Pegel auf der Insel (Fehmarn / Westermarkelsdorf (Fehmarn))
            z['befunde'].append('NAME nur Insel "%s", aber %d weitere Pegel dort (%s) -- Ort vor die Klammer, Insel in die Klammer' % (
                haupt_, len(andere), '; '.join(a_.replace(', ' + land, '') for a_ in andere[:4])))
    import dubletten_kurven as D
    S = D.saetze(land, sorted({r['file'] for r in rs}))
    proz = {(z['satz'], z['datei']): z for z in zeilen}   # gleicher Name in mehreren Dateien (Jayapura BIG/Pushidrosal/BMKG)
    for i, a in enumerate(S):
        for b in S[i + 1:]:
            art_ = D.kandidat(a, b)
            if art_ and (a['name'], a['file']) in proz:
                quelle = lambda s_: os.path.basename(s_['file']).replace('harmonics_', '').replace('.txt', '')
                proz[(a['name'], a['file'])]['befunde'].append('%s mit "%s" (%s): %.1f km, Kurvenabweichung %.0f %% [%s]; %s gegen %s' % (
                    art_, b['name'], quelle(b), D.km(a, b), 100 * D.abw(a, b), D.detail(a, b), quelle(a), quelle(b)))
    # Zeitversatz von Uebertragungssaetzen gegen Pegel der Landesquelle (py/zeit_pruefung.py)
    import zeit_pruefung as Z
    for k_, txt_ in Z.pruefe(land, sorted({r['file'] for r in rs})).items():
        if k_ in proz:
            proz[k_]['befunde'].append(txt_)
    # Von Oliver bestaetigte Befunde nicht mehr melden (harmonics/help/pruefliste_bestaetigt.csv: satz;befund;notiz)
    bpfad = os.path.join(ROOT, 'harmonics/help/pruefliste_bestaetigt.csv')
    if os.path.exists(bpfad):
        import csv as _csv
        best = [(r_['satz'], r_['befund']) for r_ in _csv.DictReader(open(bpfad, encoding='utf-8'), delimiter=';')]
        for z in zeilen:
            z['befunde'] = [b for b in z['befunde'] if not any(z['satz'] == s_ and b.startswith(p_) for s_, p_ in best)]
    stem = 'harmonics/help/pruefliste_%s_%s' % (re.sub(r'\W+', '_', land.lower()), date.today().strftime('%Y%m%d'))
    json.dump(zeilen, open(os.path.join(ROOT, stem + '.json'), 'w'), ensure_ascii=False, indent=0)
    html(zeilen, land, os.path.join(ROOT, stem + '.html'))
    import collections
    print(len(zeilen), 'Saetze,', sum(1 for z in zeilen if z['befunde']), 'mit Befund:',
          dict(collections.Counter(' '.join(b.split()[:2]) if b.startswith('NAME') else b.split()[0] for z in zeilen for b in z['befunde'])))
    print(stem + '.html')
