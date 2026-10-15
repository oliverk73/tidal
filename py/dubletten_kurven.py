"""Duplikatpruefung ueber Ort/Name und Tidenkurve (an den Suedkorea-Archivierungen geeicht, 36/47).

KOPIE    identische Tafel (Kurvenabweichung < 1 %) bis 10 km
DUPLIKAT gleicher Ort (<= 2 km) oder gleiches Kennwort im Namen, Kurven aehnlich (< 20 %)
PRUEFEN  gleicher Ort/Name, Kurven widersprechen sich -> einer ist falsch
Eigene Pegel derselben Quelle mit eigener Kennung werden nur als KOPIE gemeldet.
"""
import math, cmath, re, os

GATTUNG = r'(hang|gang|do|to|ri|ni|li|dong|man|wan|sudo|haehyeop|hae|po|seom|gundo|yeolto|budu|eup|myeon|gun|si)$'

def norm(s):
    return re.sub(r'[^a-z0-9]', '', s.lower())

def skelett(s):
    s = norm(s)
    for a, b in (('eo', 'o'), ('eu', 'u'), ('ae', 'e'), ('oe', 'e'), ('yeo', 'yo'), ('kk', 'k'), ('g', 'k'), ('b', 'p'), ('d', 't'), ('j', 'ch'), ('r', 'l'), ('chh', 'ch'), ('ss', 's')):
        s = s.replace(a, b)
    return s
ROOT = '/home/oliver/weather'
SP = {'M2': 28.984104, 'S2': 30.0, 'N2': 28.43973, 'K2': 30.082137, 'K1': 15.041069, 'O1': 13.943036, 'P1': 14.958931, 'Q1': 13.398661}
MER = re.compile(r'^[+-]\d\d:\d\d ')

def km(a, b):
    return math.hypot((a['lat'] - b['lat']) * 111.2, (a['lon'] - b['lon']) * 111.2 * math.cos(math.radians(a['lat'])))

def saetze(land, dateien):
    out = []
    for f in dateien:
        L = open(os.path.join(ROOT, f), encoding='latin-1').read().split('\n')
        for k, l in enumerate(L):
            if l.endswith(', ' + land) and not l.startswith('#') and k + 1 < len(L) and MER.match(L[k + 1]):
                kopf = []
                j = k - 1
                while j > 0 and L[j].startswith('#') and L[j] != '#':
                    kopf.append(L[j]); j -= 1
                h = '\n'.join(reversed(kopf))
                la = re.search(r'# !latitude: *(-?[\d.]+)', h); lo = re.search(r'# !longitude: *(-?[\d.]+)', h)
                if not la or not lo: continue
                kon = {}
                for x in L[k + 3:min(k + 200, len(L))]:
                    q = x.split()
                    if len(q) == 3 and q[0] in SP:
                        kon[q[0]] = (float(q[1]), float(q[2]))
                    elif q and q[0] != 'x' and len(q) != 3:
                        break
                mer = L[k + 1].split()[0]
                hh, mm = mer.lstrip('+-').split(':')
                e = L[k + 2].split()
                out.append(dict(name=l, file=f, lat=float(la.group(1)), lon=float(lo.group(1)), kopf=h, kon=kon,
                                meridian=(-1 if mer[0] == '-' else 1) * (int(hh) + int(mm) / 60),
                                fuss=len(e) > 1 and e[1].startswith('f')))
    return out

HAUPT = ('M2', 'S2', 'K1', 'O1')
def vek(s):
    f = 0.3048 if s.get('fuss') else 1.0
    return {c: cmath.rect(a * f, math.radians(g - SP[c] * s['meridian'])) for c, (a, g) in s['kon'].items() if c in SP}
def abw(a, b):
    """relative komplexe Abweichung der Hauptkonstituenten (0 = gleich)."""
    va, vb = vek(a), vek(b)
    cs = [c for c in HAUPT if c in va and c in vb]
    if len(cs) < 3: return None
    num = math.sqrt(sum(abs(va[c] - vb[c]) ** 2 for c in cs)); den = math.sqrt(sum(abs(vb[c]) ** 2 for c in cs))
    return num / den if den else None
def detail(a, b):
    va, vb = vek(a), vek(b); out = []
    for c in HAUPT:
        if c in va and c in vb and abs(vb[c]) > 0:
            out.append('%s %+.0f%% %+.0f°' % (c, 100 * (abs(va[c]) / abs(vb[c]) - 1), (math.degrees(cmath.phase(va[c] / vb[c])) + 180) % 360 - 180))
    return ', '.join(out)
STOP = {'pusan', 'chechu', 'chechuto', 'south', 'korea', 'island', 'harbor', 'breakwater', 'new', 'old', 'wharf', 'east', 'power', 'plant',
        'sinhang', 'naehang', 'oehang', 'pukhang', 'kuhang', 'inner', 'outer', 'nolth', 'pritke', 'pritge', 'lighthouse',
        # Gattungswoerter (Philippinen 15.10.2026: "Gallo Malo Channel" und "Tandungan Channel" sind kein gleicher Name)
        'channel', 'chanel', 'bay', 'pel', 'point', 'river', 'liver', 'entrance', 'pass', 'reef', 'anchorage', 'ankolake',
        'port', 'polt', 'harbour', 'halpol', 'sound', 'strait', 'cove', 'islands', 'islet', 'north', 'sowth', 'south', 'sout', 'east', 'west', 'city',
        'pulau', 'teluk', 'tanjung', 'selat', 'pelabuhan', 'muara', 'sungai', 'kepulauan'}
_STOP_SK = None  # Skelettformen der STOP-Woerter, beim ersten Aufruf gebaut

def woerter(n):
    global _STOP_SK
    if _STOP_SK is None:
        _STOP_SK = {re.sub(GATTUNG, '', skelett(w)) for w in STOP} | {skelett(w) for w in STOP}
    t = n.split(',')[0]
    k = [re.sub(GATTUNG, '', skelett(x)) for x in re.split(r"[\s()/]+", t) if len(norm(x)) >= 3]
    return [x for x in k if x and x not in STOP and x not in _STOP_SK]
def amt_id(s):
    m = re.search(r'# (khoa_code|cwa_code|station_id_context|ioc_code): *(\S+)', s['kopf'])
    return (s['file'], m.group(2)) if m else None
def kandidat(a, b):
    """-> None | KOPIE (identische Tafel) | AEHNLICH (gleicher Ort/Name, andere Quelle, aehnliche Kurve) | PRUEFEN (Kurven widersprechen sich)."""
    d = km(a, b)
    if d > 10: return None
    e = abw(a, b)
    if e is None: return None
    if e < 0.01: return 'KOPIE'
    wa, wb = woerter(a['name']), woerter(b['name'])
    gemeinsam = set(wa) & set(wb)
    ia, ib = amt_id(a), amt_id(b)
    eigene = ia and ib and ia[0] == ib[0] and ia[1] != ib[1]
    nur_stadt = gemeinsam and (set(wa[1:]) != set(wb[1:])) and gemeinsam <= {wa[0], wb[0]}
    if eigene:
        return None   # eigene Pegel derselben Quelle (andere Namen/Koordinaten) bleiben (Oliver, 14.10.2026)
    if d <= 2 or gemeinsam:
        return 'AEHNLICH' if e < 0.2 else 'PRUEFEN'
    return None
