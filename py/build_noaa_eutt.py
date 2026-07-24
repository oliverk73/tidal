#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NOAA 'Tide Tables Central & Western Pacific + Indian Ocean' (2018) Table 2
   subordinate stations -> XTide harmonics (C&GS/NOS difference transfer).

Method (range-based, datum-robust):
  NOAA Table 2 tabulates the SUBORDINATE station's resulting ranges directly:
    Mean range Mr, Spring range Sr, [Diurnal range Dr], Mean Tide Level MTL  (feet).
  Semidiurnal:  M2_sub = Mr/2 ;  S2_sub = (Sr - Mr)/2     (Sr=2(M2+S2), Mr=2*M2)
  Diurnal:      Dr = 2*(K1+O1)  ->  fD = Dr_sub / Dr_ref
  Reference constituent SHAPE (N2,K1,O1,shallow,...) scaled:
    semidiurnal x rM=M2_sub/M2_ref ; K2 x rS=S2_sub/S2_ref ; diurnal x fD ; shallow x rM^2
  Phase:  g' = g_ref + speed * mean(dtHW,dtLW)   (local-time offset, ref meridian inherited)
  Z0   :  MTL (mean tide level above chart datum), else M2_sub+S2_sub.

Only true gaps (>GAP_KM from existing DB). Reference rows (daily predictions) skipped.
Writes harmonics/noaa/harmonics_noaa_eutt.txt (ISO-8859-1).  Region selectable via argv.
"""
import os, re, json, math, sys, glob, unicodedata
sys.path.insert(0, os.path.join(os.path.expanduser('~'), 'weather', 'py'))

HARM = os.path.expanduser('~/weather/harmonics')
OUT  = f'{HARM}/noaa/harmonics_noaa_eutt.txt'
FULL = f'{HARM}/help/eutt2020_table2_full.json'
GAPS = f'{HARM}/help/eutt2020_gaps.json'
FT = 0.3048
GAP_KM = 4.0
# cumulative: all regions built so far go into the one harmonics_noaa_cptt.txt
REGIONS = sys.argv[1].split(',') if len(sys.argv) > 1 else \
    ['WestAfrica']

# ---------- header (congen block) from an existing harmonics file ----------
def read_header(path):
    lines = open(path, encoding='iso-8859-1').read().splitlines()
    end = max(i for i, l in enumerate(lines) if 'End congen output' in l)
    header = lines[:end + 1]
    order = []; speed = {}; in_s = False
    for l in lines:
        if l.startswith('# Constituent speeds'): in_s = True; continue
        if in_s:
            if l.startswith('# Starting year') or l.startswith('*END*'): break
            m = re.match(r'^(\S+)\s+([\d.]+)\s*$', l.strip())
            if m: order.append(m.group(1)); speed[m.group(1)] = float(m.group(2))
    return header, order, speed
HEADER, ORDER, SPEED = read_header(f'{HARM}/att/harmonics_att_np203.txt')

# ---------- reference resolver over live DB ----------
FILES = [f for f in (glob.glob(f'{HARM}/classic/*.txt') + glob.glob(f'{HARM}/ticon/*.txt')
                     + glob.glob(f'{HARM}/att/*.txt') + glob.glob(f'{HARM}/utide/*.txt'))
         if 'noaa_cptt' not in f and 'noaa_eutt' not in f]
_MER = re.compile(r'^([+-]\d{2}:\d{2})\s*:(\S+)')
_CON = re.compile(r'^([A-Za-z][A-Za-z0-9]*)\s+([\-\d.]+)\s+([\-\d.]+)\s*$')
_ZL  = re.compile(r'^([\-\d.]+)\s+meters')
def _blocks(path):
    try: L = open(path, encoding='iso-8859-1').read().split('\n')
    except Exception: return
    i = 0; n = len(L)
    while i < n:
        m = _MER.match(L[i])
        if m and i > 0:
            name = L[i - 1].strip(); mer, tz = m.group(1), m.group(2)
            rlat = rlon = None; b = i - 2
            while b >= 0 and L[b].startswith('#'):
                if L[b].startswith('# !latitude:'):
                    try: rlat = float(L[b].split(':', 1)[1])
                    except ValueError: pass
                elif L[b].startswith('# !longitude:'):
                    try: rlon = float(L[b].split(':', 1)[1])
                    except ValueError: pass
                b -= 1
            z0 = None; con = {}; k = i + 1
            zm = _ZL.match(L[k]) if k < n else None
            if zm: z0 = float(zm.group(1)); k += 1
            while k < n:
                if _MER.match(L[k]) or L[k].startswith('#'): break
                cm = _CON.match(L[k])
                if cm and cm.group(1) != 'x': con[cm.group(1)] = (float(cm.group(2)), float(cm.group(3)))
                k += 1
            yield name, dict(con=con, z0=z0, mer=mer, tz=tz, lat=rlat, lon=rlon,
                             src=os.path.basename(path)); i = k; continue
        i += 1
_IDX = None
def index():
    global _IDX
    if _IDX is None:
        _IDX = {}
        for f in FILES:
            for n, r in _blocks(f):
                if r['con'].get('M2', (0, 0))[0] > 0: _IDX.setdefault(n, []).append(r)
    return _IDX
def find(q):
    idx = index(); ql = q.lower()
    cand = [(n, r) for n, rs in idx.items() for r in rs if ql in n.lower()]
    if not cand:
        cand = [(n, r) for n, rs in idx.items() for r in rs if all(w in n.lower() for w in ql.split())]
    cand.sort(key=lambda x: len(x[0]))
    return cand[0] if cand else (None, None)

# NOAA Table-1 reference name -> resolver query (prefer measured sources)
REFMAP = {
 'Cebu': 'Cebu, Phil', 'Legaspi Port': 'Legaspi', 'Davao': 'Davao, Phil', 'Manila': 'Manila, Phil',
 'Jolo': 'Jolo, Phil', 'San Fernando Harbor': 'San Fernando, Phil',
 'Kutei River Ent.': 'Kutei', 'Belawan Channel': 'Belawan', 'Musi River': 'Air Musi',
 'Surabaja Strait': 'Surabaya', 'Barito River': 'Barito', 'Djakarta': 'Jakarta, Java',
 'Mergui': 'Mergui', 'Mui Vung Tau': 'Vung Tau', 'Do Son': 'Do Son', 'Bangkok Bar': 'Bangkok',
 'Singapore': 'Sembawang', 'Hong Kong': 'Hong Kong', 'Shantou': 'Shantou', 'Huangpu': 'Huangpu',
 'Beihai': 'Beihai', 'Haikou': 'Haikou', 'PengHu (Ma-Kung Kang)': 'Magong', 'Kamaisi': 'Kamaisi',
 'Naha': 'Naha', 'Yokohama': 'Yokohama', 'Paramushiru Island': 'Paramushir', 'Darwin': 'Darwin',
 'Dar Es Salaam': 'Dar Es Salaam', 'Bombay': 'Mumbai', 'Ch’ang Chiang Approach': 'Chang Jiang',
 'Shatt Al Arab': 'Khowr-e Musa',
 # --- China/Korea Yellow Sea + boundary ---
 'Dalian': 'Dalian, China', 'Tanggu': 'Tanggu, Tianjin', 'Inch’on': 'Incheon, South',
 'Wusong': 'Wusong', 'Namp’O-Hang': 'Nampo, North', 'Pusan': 'Busan New Port',
 'Lianyun Gang': 'Lianyungang (Port)', 'Yantai': 'Yantai, Shandong', 'Qingdao': 'Qingdao, China',
 'Qinhuangdao': 'Qinhuangdao, Hebei', 'Otomari': 'Korsakov',
 # --- Indian Ocean / Arabia / East Africa ---
 'Colombo': 'Colombo', 'Sagar': 'Sagar Roads', 'Karachi': 'Karachi', 'Madras': 'Chennai',
 'Mina Jebel Ali': 'Jebel Ali', 'Mina Al Ahmadi': 'Mina Al Ahmadi', 'Mina Salman': 'Mina Salman',
 'Musay’id': 'Musay', 'Suez': 'Suez', 'Durban': 'Durban', 'Aden': 'Aden', 'Apia': 'Apia',
 # --- Pacific Islands ---
 'Honolulu': 'Honolulu', 'Kwajalein Atoll': 'Kwajalein', 'Suva': 'Suva', 'Pago Pago': 'Pago Pago',
 'Chuuk': 'Chuuk', 'Pohnpei Harbor': 'Pohnpei', 'Papeete': 'Papeete', 'Auckland': 'Auckland',
 'Dreger Harbor': 'Dreger', 'Townsville': 'Townsville',
 'Nawiliwili': 'Nawiliwili', 'Hilo': 'Hilo', 'Kahului': 'Kahului', 'Moku O Loe': 'Moku O Loe',
 # --- Russian Far East / Okhotsk / Kamchatka / Kuril ---
 'Moji': 'Moji', 'Yamato Wan': 'Ostrov Mamya', 'Paramushiru Island': 'Paramushir',
 # --- Australia / NZ / Mozambique / Guam (final batch) ---
 'Port Hedland': 'Port Hedland', 'Port Adelaide': 'Adelaide', 'Port Phillip': 'Port Phillip',
 'Port Lincoln': 'Port Lincoln', 'Beira': 'Beira', 'Guam': 'Guam',
 # --- Europe & W Africa volume (eutt2020) references ---
 'Lisbon': 'Lisboa (Alc',                    # Lisboa (Alcantara), Portugal
 'Liverpool': 'Liverpool (Gladstone Dock)',  # England (NICHT Nova Scotia)
 'Gibralter': 'Gibraltar,',                  # NOAA-Schreibweise; Komma gegen 'Sandy Bay, Gibraltar'
}
_refcache = {}
def resolve_ref(noaa_ref):
    if noaa_ref in _refcache: return _refcache[noaa_ref]
    q = REFMAP.get(noaa_ref, noaa_ref)
    rn, rr = find(q)
    if rr is not None: rr = {**rr, '_name': rn}
    _refcache[noaa_ref] = (rn, rr)
    return rn, rr

# ---------- country inference: reference-based override, then bbox ----------
CK_CHINA = {'Dalian', 'Tanggu', 'Qingdao', 'Yantai', 'Lianyun Gang', 'Wusong',
            'Ch’ang Chiang Approach', 'Qinhuangdao'}
def country(lat, lon, ref):
    if lat < -60: return 'Antarctica'   # below 60°S = Antarctica (nearest DB station is S.America)
    # Sabah (NE Borneo, Malaysia) sits between Indonesian Kalimantan and Philippine Tawi-Tawi,
    # so country_nn lands across a border (Lahad Datu/Kudat -> PHL/IDN); pin it geographically.
    if 4.3 <= lat <= 7.5 and 115.2 <= lon <= 119.3: return 'Malaysia'
    # --- China/Korea/Japan/Russia (Yellow Sea + boundary refs), keyed by reference ---
    # gated by latitude: these refs are also used as distant character-matches for
    # equatorial Indonesian ports, which must NOT inherit the reference's country.
    if ref in CK_CHINA and lat >= 18 and lon < 124: return 'China'   # lon<124 keeps Korea (Koje-do) out
    if ref in ('Yokohama', 'Kamaisi', 'Naha') and lat >= 23: return 'Japan'   # Honshu / Ryukyu
    # (Otomari/Korsakov is a character-ref for BOTH Sakhalin (RU) and NE Hokkaido (JP);
    #  let country_nn decide by nearest station — e.g. Koiseboi 44.0N -> Japan.)
    if ref in ('Inch’on', 'Pusan', 'Namp’O-Hang') and 32 <= lat <= 43 and lon <= 131.5:  # Korea N/S
        if (lon < 126.7 and lat >= 37.75) or (lon >= 127.3 and lat >= 38.6): return 'North Korea'
        return 'South Korea'
    # geography first (reference can be a distant character-match port, so don't trust it for country)
    if 21.8 <= lat <= 25.4 and 119.2 <= lon <= 122.1: return 'Taiwan'       # Taiwan + Penghu
    if 22.1 <= lat <= 22.62 and 113.82 <= lon <= 114.52: return 'Hong Kong'
    if 4.5 <= lat <= 21 and 116 <= lon <= 127: return 'Philippines'
    if 5 <= lat <= 19.5 and 95 <= lon <= 99.5 and ref == 'Mergui': return 'Myanmar'
    if 5.5 <= lat <= 21 and 99 <= lon <= 110 and ref in ('Mui Vung Tau', 'Do Son'): return 'Vietnam'
    if 6 <= lat <= 14 and 99 <= lon <= 105.5 and ref == 'Bangkok Bar': return 'Thailand'
    if 6.4 <= lat <= 13.8 and 99 <= lon <= 102.2: return 'Thailand'    # Gulf of Thailand
    if 7 <= lat <= 10.6 and 97.8 <= lon <= 99.0: return 'Thailand'     # Thai Andaman coast
    if -11 <= lat <= 7.5 and 95 <= lon <= 141.5: return 'Indonesia'
    if 0.8 <= lat <= 7.5 and 99.5 <= lon <= 104.5 and ref == 'Sembawang': return 'Malaysia'
    if 8 <= lat <= 24 and 102 <= lon <= 110: return 'Vietnam'
    if 18 <= lat <= 41 and 105 <= lon <= 122.5: return 'China'
    # Cote d'Ivoire: Nachbarn gemischt (att='Cote d'Ivoire', ticon4/utide='Ivory Coast')
    # -> geografisch pinnen (Liberia-Grenze -7.55, Ghana-Grenze -3.11). Projektstandard 'Ivory Coast'.
    if 4.0 <= lat <= 7.0 and -7.55 <= lon <= -3.11: return 'Ivory Coast'
    return country_nn(lat, lon)   # fallback: country of nearest existing DB station

# --- nearest-neighbour country index (for regions not covered by explicit rules) ---
_CPTS = None
def country_nn(lat, lon):
    global _CPTS
    if _CPTS is None:
        plat = []; plon = []; pc = []
        latp = re.compile(r'^# !latitude: ([\-\d.]+)'); lonp = re.compile(r'^# !longitude: ([\-\d.]+)')
        for f in FILES:
            if 'current' in f.lower(): continue          # skip tidal-current files
            L = open(f, encoding='iso-8859-1').read().splitlines(); lo = None
            for j, l in enumerate(L):
                m = lonp.match(l)
                if m: lo = float(m.group(1)); continue
                m = latp.match(l)
                if m and lo is not None:
                    la = float(m.group(1)); nm = None
                    for k in range(j + 1, min(j + 6, len(L))):
                        if L[k].strip() and not L[k].startswith('#'): nm = L[k].strip(); break
                    if nm and ',' in nm and not nm.rstrip().endswith(('Current', 'Tide')):
                        c = nm.split(',')[-1].strip()
                        if 2 < len(c) < 40 and not any(ch.isdigit() for ch in c):
                            plat.append(la); plon.append(lo); pc.append(c)
                    lo = None
        _CPTS = (np.array(plat), np.array(plon), pc)
    plat, plon, pc = _CPTS
    if not len(plat): return None
    d = (plat - lat) ** 2 + ((plon - lon) * math.cos(math.radians(lat))) ** 2
    c = pc[int(np.argmin(d))]
    return {'French Polyneisa': 'French Polynesia', 'Moçambique': 'Mozambique', 'Novaya Zemlya': 'Russia'}.get(c, c)

from timezonefinder import TimezoneFinder
_TF = None
def tz_lookup(lat, lon):
    """Authoritative IANA timezone for the station's own location.  NOAA often uses a distant
    character-match reference (e.g. Russian Far East -> Jolo +8; Kiribati Line Is -> Honolulu
    -10, ~a day off across the date line), so the inherited reference tz is unreliable.
    Phases stay in the reference's meridian frame (dt is frame-independent); tz is display only."""
    global _TF
    if _TF is None: _TF = TimezoneFinder()
    lng = ((lon + 180) % 360) - 180                 # wrap to [-180,180] (Pacific lon>180)
    z = _TF.timezone_at(lat=lat, lng=lng)
    if z: return z
    off = round(lng / 15.0)                          # ocean fallback: fixed UTC offset
    return f"Etc/GMT{-off:+d}" if off else 'Etc/GMT'

# --- Zeitmeridian-Normalisierung der Table-2-Differenzen (Fix 2026-07-19) ---
# C&GS-Konvention: Table 2 gibt Zeitdifferenzen so an, dass Referenzzeit (im Zeitmeridian der
# Referenz) + dt = Stationszeit (im Zeitmeridian der STATION).  Liegt die Station in einer
# anderen Zone als die Referenz, steckt die Zonendifferenz mit im dt und muss heraus:
# dt_wahr = dt_tafel - (zone_station - zone_referenz).  Ohne diese Normalisierung waren alle
# 50 spanischen Lisboa-Transfers +60min zu spaet (validiert gegen IHM-Nachbarn, 15-Tage-Zyklus).
from zoneinfo import ZoneInfo
from datetime import datetime as _dt
# Epoche fuer die Zonenbestimmung: Die 2020-Baende reproduzieren alte C&GS-Datenbestaende;
# massgeblich ist die HISTORISCHE Zone der Tafel-Aera, nicht die heutige (Marokko ist seit
# 2018 UTC+1, die Tafel rechnet Casablanca aber mit UTC+0 -- empirisch validiert 2026-07-19:
# Casablanca->Madeira/W-Sahara +-0min, Lisboa->Spanien -60min noetig; 1980 liefert beides).
_TT_EPOCH = _dt(1980, 1, 15, 12)     # Winter = Standardzeit (kein DST)
def std_offset_h(tzname):
    try: return ZoneInfo(tzname).utcoffset(_TT_EPOCH).total_seconds() / 3600.0
    except Exception: return None
# Grenzfaelle, wo timezonefinder die Zone des Nachbarlands liefert, die Tafel aber die
# politische Zone der Station verwendet:
TABLE_TZ_OVERRIDE = {467: 'Europe/Madrid'}   # Ayamonte (spanisches Guadiana-Ufer)

# countries whose stations carry a province/state/island in the name ("Place, Province, Country")
PROVINCE_COUNTRIES = {'China', 'Indonesia', 'India', 'Australia', 'Japan', 'Philippines',
                      'New Zealand', 'South Korea', 'Thailand', 'Vietnam', 'Malaysia', 'Myanmar',
                      'Iran', 'Pakistan', 'Taiwan', 'Argentina', 'Russia'}
_PROV_BAD = ('strait', 'river', 'bay', 'island', 'islands', 'entrance', 'gulf', 'coast', 'arch',
             'channel', 'sound', 'shoal', 'reef', 'atoll', 'harbor', 'harbour', 'peninsula',
             'cape', 'lagoon', 'inlet', 'pulau', 'teluk', '(', ')', '<', '>', '[')
def is_real_province(p):
    """Accept administrative provinces/states/prefectures; reject geographic features and OCR
    artefacts that our DB sometimes stores in the same name slot."""
    if not (1 < len(p) < 32): return False
    pl = p.lower()
    return not any(w in pl for w in _PROV_BAD)

_PPTS = None
def province_lookup(cty, lat, lon):
    """Province/state/island for the station, taken from the nearest same-country DB station that
    carries one (3+ name segments). Distance-capped (250 km) so remote stations don't inherit a
    far, wrong province."""
    if cty not in PROVINCE_COUNTRIES: return None
    global _PPTS
    if _PPTS is None:
        _PPTS = {}
        latp = re.compile(r'^# !latitude: ([\-\d.]+)'); lonp = re.compile(r'^# !longitude: ([\-\d.]+)')
        for f in FILES:
            if 'current' in f.lower(): continue
            L = open(f, encoding='iso-8859-1').read().splitlines(); lo = None
            for j, l in enumerate(L):
                m = lonp.match(l)
                if m: lo = float(m.group(1)); continue
                m = latp.match(l)
                if m and lo is not None:
                    la = float(m.group(1)); nm = None
                    for k in range(j + 1, min(j + 6, len(L))):
                        if L[k].strip() and not L[k].startswith('#'): nm = L[k].strip(); break
                    if nm and nm.count(',') >= 2 and not nm.rstrip().endswith(('Current', 'Tide')):
                        segs = [x.strip() for x in nm.split(',')]
                        c, prov = segs[-1], segs[-2]
                        if c in PROVINCE_COUNTRIES and is_real_province(prov):
                            _PPTS.setdefault(c, ([], [], []))
                            _PPTS[c][0].append(la); _PPTS[c][1].append(lo); _PPTS[c][2].append(prov)
                    lo = None
        _PPTS = {c: (np.array(a), np.array(b), p) for c, (a, b, p) in _PPTS.items()}
    idx = _PPTS.get(cty)
    if not idx: return None
    la_a, lo_a, provs = idx
    d = (la_a - lat) ** 2 + ((lo_a - lon) * math.cos(math.radians(lat))) ** 2
    i = int(np.argmin(d))
    if math.sqrt(d[i]) * 111.0 > 250: return None          # ~km cap
    return provs[i]

def is_us_pacific(lat, lon, name):
    """US Pacific territories — excluded (NOAA's own DWF/US tide tables cover them better)."""
    n = name.lower()
    if any(x in n for x in ('howland', 'baker island', 'palmyra', 'jarvis', 'kingman',
                            'johnston', 'wake island', 'midway')):
        return True
    if 18.5 <= lat <= 28.7 and -178.6 <= lon <= -154.5: return True   # Hawaiian chain (incl. NW)
    if -14.7 <= lat <= -10.9 and -171.6 <= lon <= -168.0: return True  # American Samoa
    if 13 <= lat <= 21 and 144 <= lon <= 147: return True             # Guam + Northern Marianas
    return False

# ---------- helpers ----------
def lat1(s):
    out = []
    for ch in s:
        try: ch.encode('iso-8859-1'); out.append(ch)
        except UnicodeEncodeError:
            d = unicodedata.normalize('NFKD', ch)
            out.append(''.join(c for c in d if not unicodedata.combining(c)).encode('ascii', 'ignore').decode())
    return ''.join(out)
def cleanname(n):
    n = n.replace('}', '').replace('{', '').strip().strip('.,').strip()
    if n.isupper():
        sm = {'de','da','do','dos','das','del','di','du','e','y','of','the','and','la','le','les','el'}
        n = ' '.join((w.lower() if i and w.lower() in sm else w.capitalize()) for i, w in enumerate(n.split()))
    return lat1(n)

DIURN = {'K1','O1','P1','Q1','J1','M1','OO1','2Q1','SO1','RHO1','PHI1','PSI1','S1','SIG1','TAU1','CHI1','THE1','BET1','UPS1'}
SEMI  = {'N2','2N2','NU2','MU2','L2','T2','R2','LDA2','LAM2','EPS2','ETA2','GAM2','ALP2','BET2','DEL2','OQ2','MNS2','MSN2','SNK2'}
SHAL  = {'M4','MS4','M6','MN4','2MS6','MK3','2MK3','S4','S6','SK3','M8','3MK7','MK4','SK4','2SM6','MSN6','2MN6','M3','SO3','MO3','2MK5','2SK5','MK6','MSK6','3MN8','M10','M12','MNK6'}
LONGP = {'SA','SSA','MM','MF','MSF','MSQM','MTM','MSM','SM','MS0','MF1','NODE','Z0'}

def clamp(x, lo, hi): return max(lo, min(hi, x))

# --- nodal-free harmonic synthesis to measure tidal ranges (mean/spring/great-diurnal) ---
import numpy as np
_T = np.arange(0, 60 * 24, 0.5)            # 60 days, 30-min step (hours)
_DAY = (_T // 24).astype(int)
def measure(items):
    """items: list of (speed_deg_per_hr, amp, phase_deg). Return (mean,spring,great_diurnal) m."""
    h = np.zeros_like(_T)
    for sp, a, g in items:
        h += a * np.cos(math.radians(sp) * _T - math.radians(g))
    d = h[1:-1]
    hi = np.where((d >= h[:-2]) & (d > h[2:]))[0] + 1
    lo = np.where((d <= h[:-2]) & (d < h[2:]))[0] + 1
    if len(hi) < 5 or len(lo) < 5: return (0.0, 0.0, 0.0)
    HW, LW = h[hi], h[lo]
    mean_r = HW.mean() - LW.mean()
    spring_r = np.percentile(HW, 92) - np.percentile(LW, 8)
    dh = _DAY[hi]; dl = _DAY[lo]
    mhhw = [HW[dh == k].max() for k in range(60) if (dh == k).any()]
    mllw = [LW[dl == k].min() for k in range(60) if (dl == k).any()]
    gt = (np.mean(mhhw) - np.mean(mllw)) if mhhw and mllw else spring_r
    return (float(mean_r), float(spring_r), float(gt))
_REFR = {}
def ref_ranges(rn, con):
    """Measure the reference's (mean, spring, great-diurnal) ranges from the SAME
    constituent set that transfer() scales — a nodal-free synthesis.  This keeps the
    uniform scale k self-consistent: predicted range = k * synth(con) = NOAA range,
    regardless of any name collisions between our DB files and the system TCD.
    (Earlier a tide-based measurement of `rn` drifted from `con` for Pacific refs that
    resolve to a different 'Kwajalein' record, inflating M2 ~3x.)"""
    if rn not in _REFR:
        _REFR[rn] = measure([(SPEED[c], a, g) for c, (a, g) in con.items() if c in SPEED and a > 0])
    return _REFR[rn]

SEMI_SET = SEMI | {'M2', 'S2', 'K2'}

# Referenzen, deren Flachwasser-Obertiden aestuar-spezifisch sind und NICHT auf die
# Subordinates uebertragen werden duerfen (Fix 2026-07-19: Lisboa/Tejo-M4 war ~10x zu
# gross fuer iberische Aussenkuesten-Stationen; HW/NW-Asymmetrie +10/-11min -> -3/+1min
# nach Entfernen, validiert gegen IHM-Nachbarn). Bei Bedarf erweitern (z.B. nach Audit
# der Gibraltar-/Casablanca-Gruppen). Praefix-Match auf den aufgeloesten Referenznamen.
NO_SHALLOW_REFS = ('Lisboa (Alc',)

def transfer(s, rr):
    con = rr['con']
    M2r = con.get('M2', (0, 0))[0]; S2r = con.get('S2', (0, 0))[0]
    K1r = con.get('K1', (0, 0))[0]; O1r = con.get('O1', (0, 0))[0]
    if M2r <= 0: return None
    rn = rr.get('_name', '')
    Mn_ref, Sr_ref, Gt_ref = ref_ranges(rn, con)
    refF = (K1r + O1r) / (M2r + S2r + 1e-9)
    mean = s.get('mean_ft'); spring = s.get('spring_ft'); diu = s.get('diurnal_ft')
    trop = s.get('tropic_ft')
    if diu is not None and diu <= 0.05: diu = None        # OCR drop-out -> fall back
    ts = [t for t in (s.get('dtHW'), s.get('dtLW')) if t is not None]
    dt = (sum(ts) / len(ts) / 60.0) if ts else 0.0   # hours
    # Zonendifferenz Station-Referenz aus dem Tafel-dt herausrechnen (s. Kommentar oben)
    tzs = 0.0
    z_s = std_offset_h(TABLE_TZ_OVERRIDE.get(s.get('no')) or tz_lookup(s['lat'], s['lon']))
    z_r = std_offset_h(tz_lookup(rr['lat'], rr['lon'])) if rr.get('lat') is not None else None
    if z_s is not None and z_r is not None: tzs = z_s - z_r
    dt -= tzs
    # ---- step 1: uniform scale k matches the primary tabulated range exactly ----
    # (ranges scale linearly with a uniform amplitude scale, so this is one-shot exact)
    # CAL corrects the systematic ~10% gap between the nodal-free synth measure (used for
    # Mn_ref/Gt_ref) and XTide's actual HW/LW prediction, centring predicted ranges on 1.0.
    CAL = 1.10
    if mean is not None and Mn_ref > 0.02:
        k = clamp(CAL * mean * FT / Mn_ref, 0.05, 8.0)
    elif diu is not None and Gt_ref > 0.02:
        k = clamp(CAL * diu * FT / Gt_ref, 0.05, 8.0)
    elif trop is not None and Gt_ref > 0.02:                # DT row whose diurnal cell dropped
        k = clamp(CAL * 0.92 * trop * FT / Gt_ref, 0.05, 8.0)
    else:
        return None
    # ---- step 2: spring (MS) -> nudge S2 group ; great-diurnal (MD) -> nudge diurnal group ----
    sS = 1.0
    if spring is not None and mean is not None:
        cur_diff = k * (Sr_ref - Mn_ref); tgt_diff = (spring - mean) * FT
        if cur_diff > 0.02 and tgt_diff > 0:
            sS = clamp(tgt_diff / cur_diff, 0.1, 6.0)
    sD = 1.0
    if diu is not None and mean is not None and Gt_ref > Mn_ref:
        # great-diurnal range = semidiurnal baseline + diurnal contribution; scale only the
        # diurnal part: Gt = k*Mn_ref + sD*k*(Gt_ref-Mn_ref) -> solve sD for target diu.
        diur_contrib = k * (Gt_ref - Mn_ref)
        tgt_contrib = (diu - mean) * FT
        if diur_contrib > 0.02 and tgt_contrib > 0:
            sD = clamp(tgt_contrib / diur_contrib, 0.1, 6.0)
    drop_shal = any((rn or '').startswith(p) for p in NO_SHALLOW_REFS)
    out = {}
    for c, (a, g) in con.items():
        if a <= 0: continue
        if drop_shal and c in SHAL: continue
        if c in ('S2', 'K2'): na = a * k * sS
        elif c in DIURN: na = a * k * sD
        elif c in LONGP: na = a
        else: na = a * k
        sp = SPEED.get(c)
        out[c] = (round(na, 4), round((g + (sp * dt if sp else 0)) % 360, 2))
    M2 = M2r * k; S2 = S2r * k * sS
    return dict(con=out, mer=rr['mer'], tz=rr['tz'], M2=M2, S2=S2, k=k, sD=sD, dt=dt,
                tzs=tzs, ot=drop_shal, refF=refF)

# ---------- gap check ----------
def hav(a, b, c, d):
    R = 6371; p = math.pi / 180
    return 2 * R * math.asin(math.sqrt(math.sin((c-a)*p/2)**2 + math.cos(a*p)*math.cos(c*p)*math.sin((d-b)*p/2)**2))
def refpts():
    pts = []
    for f in FILES:
        t = open(f, encoding='iso-8859-1').read()
        for la, lo in zip(re.findall(r'# !latitude:\s*([\-\d.]+)', t), re.findall(r'# !longitude:\s*([\-\d.]+)', t)):
            pts.append((float(la), float(lo)))
    return pts

def conf_of(tr, s):
    c = 5
    if tr['k'] > 2.0 or tr['k'] < 0.4: c = 4
    if abs(tr['dt']) > 1.5: c = min(c, 4)
    if s.get('mtl_ft') is None: c = min(c, 4)
    if s.get('spring_ft') is None and s.get('diurnal_ft') is None: c = min(c, 4)
    if tr['M2'] < 0.30 and tr['refF'] < 1.0: c = min(c, 3)
    return c

def block(s, tr, cty, OV=None, EXISTING=None):
    if s.get('_name_override'):
        name = s['_name_override']
    else:
        place = cleanname(s['name'])
        prov = province_lookup(cty, s['lat'], s['lon'])
        name = ', '.join([place] + ([lat1(prov)] if prov else []) + ([cty] if cty else []))
    name = NAME_FIX_NO.get(s['no'], name)
    if OV is not None:
        import noaa_overrides as _NOV
        name = _NOV.resolve_name(OV, s['no'], name, EXISTING or {})
    tz = tz_lookup(s['lat'], s['lon'])            # authoritative zone for the station's location
    conf = conf_of(tr, s)
    z0 = s.get('mtl_ft')
    z0 = z0 * FT if z0 is not None else round(tr['M2'] + tr['S2'], 3)
    # Vermerke kurz halten: Zeilen ueber ~300 Zeichen sprengen den build_tide_db-Parser
    # (Ueberlauf wird als neuer Record gelesen, Stationen fallen lautlos aus dem TCD).
    tzs_txt = f" tzs={-tr['tzs']*60:+.0f}min" if tr.get('tzs') else ''
    ot_txt = ' OT-drop.' if tr.get('ot') else ''
    note = (f"NOAA Tide Tables (C&GS/NOS) Europe & W Coast of Africa 2020 Table 2 transfer from "
            f"{tr.get('refname','?')} (no.{s['no']}). M2={tr['M2']:.2f} S2={tr['S2']:.2f} "
            f"k={tr['k']:.2f} dt={tr['dt']*60:+.0f}min{tzs_txt}.{ot_txt}")
    out = ['# BEGIN HOT COMMENTS',
           f"# country: {cty or '?'}",
           '# source: NOAA Tide Tables Europe & West Coast of Africa (NOS/C&GS) 2020, Table 2 transfer',
           f"# noaa_number: {s['no']}", f"# note: {note}", '# date_imported: 20260630',
           '# datum: Chart Datum (Z0 = mean tide level above CD)', f"# confidence: {conf}",
           '# !units: meters', f"# !longitude: {s['lon']:.4f}", f"# !latitude: {s['lat']:.4f}",
           name, f"{tr['mer']} :{tz}", f"{float(z0):.4f} meters"]
    con = tr['con']
    for c in ORDER:
        if c in con: a, g = con[c]; out.append(f"{c:<16}{a:.4f}  {g:.2f}")
        else: out.append('x 0 0')
    return out, name, conf

# build these even though they are "covered" (explicit FES replacements requested by Oliver);
# value = display-name override (already carries its country suffix).
# coordinate corrections for NOAA misprints (verified against neighbouring-row ordering + geography)
COORD_OVERRIDE = {463: (37.3667, -6.0),   # Sevilla, Rio Guadalquivir: NOAA-Druckfehler 32 deg -> 37 deg N
                  283: (13.8805, -16.7565),  # Pointe de Sangomar: Oliver 2026-07-23 manuell an die Spitze gesetzt (ATT-Pendant liegt suedlich am Haken)
                  405: (45.647060, 13.759697),  # Trieste: Oliver 2026-07-23 an den Pegel Molo Sartorio gesetzt (Roh-Transfer stand grob auf 45.65/13.75)
                  195: (5.1378, -4.9915)}  # Grand-Lahou: Oliver 2026-07-24 an die Bandama-Reede (Roh-Transfer lag bei Braffedon ~5km ostlich)
# country fixes where neither reference nor nearest-neighbour resolve a contested border correctly
COUNTRY_OVERRIDE = {283: 'Senegal',                # Sangomar: NOAA sagt faelschlich Gambia
                    251: 'Guinea-Bissau',          # Cacine (country_nn-Fehler)
                    127: 'Cameroon', 111: 'Equatorial Guinea',  # FORCE_INCLUDE-Metadaten
                    181: 'Ghana', 183: 'Ghana', 101: 'Gabon'}


# Diakritika-/Namenskorrekturen per NOAA-Nr. (offizielle lokale Schreibweise; nur eindeutige
# Faelle, alles Latin-1). Volle Anzeigenamen. Kyrillisch (RU) bleibt ASCII (ISO-8859-1).
NAME_FIX_NO = {
 1163: 'Dún Laoghaire, Ireland',
 465: 'Huelva (Río Odiel), Spain',
 533: 'Corcubión, Spain',
 569: 'Suances, Spain',
 573: 'Santoña, Spain',
 593: 'Ría de Orio, Spain',
 595: 'San Sebastián, Spain',
 31:  'Ilhéu de Fora, Ilhas Selvagens, Portugal',
 511: 'Esposende (Rio Cávado), Portugal',
 113: 'Baía de Ana Chaves, São Tomé, São Tomé and Príncipe',
 249: 'João Vieira Island, Guinea-Bissau',
 243: 'Dubréka, Guinea',
 13:  'Fajã de Água (Brava), Cape Verde',
 321: 'Kénitra, Morocco',
 463: 'Sevilla, Río Guadalquivir, Spain',
 1495:'Sønderho, Fanø Island, Denmark',
 1467:'Südfall (Hever), Germany',
 1475:'Hooge, Süder Aue, Germany',
 407: 'Grado, Italy',
 411: 'Malamocco, Italy',
 413: 'Chioggia, Italy',
 # 2026-07-21 Diakritika-/Exonym-Sweep (alle 20 verbliebenen ASCII-Faelle)
 11:  'Porto da Praia, São Tiago Island, Cape Verde',
 15:  'Porto Grande, São Vicente Island, Cape Verde',   # NOAA-Tippfehler 'Vincente'
 73:  'Baía dos Tigres, Angola',
 79:  'Baía de Santa Marta, Angola',
 81:  'Baía dos Elefantes, Angola',
 445: 'Málaga, Spain',
 455: 'Cádiz, Spain',
 557: 'Avilés, Spain',
 561: 'Gijón, Spain',
 1293:'Tórshavn, Streymoy Island, Faroe Islands',
 1303:'Klaksvík, Borðoy Island, Faroe Islands',
 1335:'Antwerpen (Roads) Schelde River, Belgium',       # Exonym 'Antwerp'
 1447:'Büsum, Norderpiep, Germany',
 1463:'Tönning, Germany',
 1477:'Wyk, Föhr, Norder Aue, Germany',
 1483:'Hörnum Odde, Vortrapp Tief, Germany',
 1497:'Nordby, Fanø Island, Denmark',
 1545:'Bodø, Norway',
 1555:'Tromsø, Norway',
 1747:'Arkhangelsk, Solombala Island, Russia',          # Exonym 'Archangel'
 # 2026-07-22 Nachzuegler Norwegen (vom 21.07.-Sweep uebersehen)
 1535:'Florø, Norway',
 # 2026-07-23 Sangomar (Oliver manuell in txt, hier gespiegelt)
 283: 'Pointe de Sangomar (Saloum River), Senegal',
 405: 'Trieste, Italy',  # 2026-07-23 Oliver: Suffix '<5>' entfernt
 1549:'Kabelvåg, Norway',
 1541:'Rørvik, Norway',
 1521:'Oscarsborg, Norway',
 # 2026-07-22 Sweep 2 (systematischer Laender-Abgleich: FR/IS/FO/DK/DE/NL/NO/ES/PT)
 461: 'Sanlúcar, Río Guadalquivir, Spain',
 469: 'Vila Real de Santo António, Portugal',
 497: 'Nazaré (Baía de Pederneira), Portugal',
 507: 'Porto de Leixões (Matosinhos), Portugal',
 535: 'Camariñas, Spain',
 555: 'Ría de Pravia, Spain',
 601: 'St. Jean de Luz (Socoa), France',
 605: 'Cap Ferret, Bassin d\'Arcachon, France',
 615: 'La Maréchale, France',
 627: 'Île d\'Aix, France',
 633: 'St. Martin, Île de Ré, France',
 639: 'Port Joinville, Île d\'Yeu, France',
 657: 'Pénerf, France',
 665: 'La Trinité, Crac\'h River, France',
 667: 'Le Palais, Belle-Île, France',
 673: 'Île de Penfret, France',
 677: 'Bénodet, Odet River, France',
 681: 'Penmarc\'h, France',
 685: 'Île de Sein, France',
 695: 'Île de Molène, France',
 697: 'Île d\'Ouessant, France',
 699: 'L\'Aber Benoît entrance, France',
 701: 'L\'Aber Wrac\'h (Fort Cézon), France',
 707: 'Ploumanac\'h, France',
 709: 'Plougrescant, Tréguier River, France',
 711: 'Héaux-de-Bréhat, France',
 713: 'Île de Bréhat, France',
 715: 'Lézardrieux, France',
 721: 'Le Légué entrance, France',
 733: 'Diélette, France',
 735: 'Îles Chausey, France',
 769: 'Fécamp, France',
 775: 'Le Tréport, France',
 1279: 'Lopransfjørður, Suðuroy Island, Faroe Islands',
 1283: 'Trongisvágur, Suðuroy Island, Faroe Islands',
 1285: 'Suðuroyarfjørður, Faroe Islands',
 1287: 'Sandsvágur, Sandoy Island, Faroe Islands',
 1301: 'Leirvík, Eysturoy Island, Faroe Islands',
 1305: 'Svínoyarfjørður, Faroe Islands',
 1307: 'Fugloyarfjørður, Faroe Islands',
 1311: 'Keflavík Harbor, Iceland',
 1315: 'Hvammsvík, Iceland',
 1319: 'Hrútafjörður, Iceland',
 1321: 'Hrísey, Iceland',
 1355: 'IJmuiden (Ymuiden), Netherlands',
 1429: 'Scharhörn, Germany',
 1433: 'Brunsbüttelkoog, Germany',
 1435: 'Glückstadt, Germany',
 1439: 'Lühedeich, Germany',
 1479: 'Dagebüll, Norder Aue, Germany',
 1491: 'Højer Sluice, Denmark',
 1503: 'Blåvands Huk, Denmark',
 1543: 'Mo i Rana, Ranfjorden, Norway',
 1559: 'Vardøya, Norway',
 # 2026-07-22 Baskenland: baskische Namen = uebliche lokale Bezeichnung (Oliver-Regel)
 585: 'Lekeitio, Spain',
 589: 'Deba, Spain',
 591: 'Getaria, Spain',
 595: 'Donostia (San Sebastián), Spain',
 597: 'Pasaia, Spain',
}

# exakte Namensdubletten zu gemessenen Quellen (Puertos del Estado etc.) -> Messung gewinnt
DROP_NO = {581,   # Bilbao (= gemessener Puertos-Pegel 'Bilbao, Spain')
           177,   # Lome (= vorhandener DWF-1997 + UTide-TC 'Lomé, Togo', 6.2km)
           547,   # Ria de Viveiro (2026-07-19 manuell entfernt: Duplikat der publizierten
                  # ATT-1714-Position; Ria durch IHM 'Cillero' + ATT 'Viveiro (Landro)' abgedeckt)
           # 2026-07-20 Liberia-Dubletten: der NOAA-Cape-Town-Transfer ist ~3h falsch
           # (Monrovia: HW 11:53 statt echt 14:43; verifiziert gg. att-np208 + classic-1997,
           # die untereinander auf ±25min stimmen). Echte Admiralty-Harmonik in att_np208/_secondary
           # deckt diese 5 Positionen ab -> Messung/echte Analyse gewinnt.
           219,   # Monrovia (= att_np208 'Monrovia, Liberia', 0.0km)
           207,   # Bafu Bay (= att_np208_secondary, 0.0km)
           209,   # Cestos Bay (= att_np208_secondary, 0.0km)
           211,   # Upper Buchanan (= att_np208_secondary 'Buchanan, Liberia', 5.8km)
           221,   # Cape Mount Bay (= att_np208_secondary 'Cape Mount, Liberia', 0.0km)
           # 2026-07-20 Irland-Inversion: NOAA referenziert die Süd-/West-/Nordküsten-
           # Iren an 'Dublin' mit KLEINEM dtHW. Dublin (Irische See) liegt aber ~180° zur
           # Süd-/Westküste (Keltische See) — um die irische Amphidromie. Der uniforme
           # Phasen-Shift erbt Dublins Phase -> HW/NW um ~6h INVERTIERT (verifiziert:
           # Dunmore/Cork/Galway sagen HW, wenn real NW ist). Alle 28 haben bessere
           # unabhängige Daten <5km (Admiralty-tidetables/utide/ticon4/classic). Ostküste
           # Irland + Wales + NI-Ostseite (in Phase mit Dublin) bleiben korrekt/erhalten.
           1173,1175,1177,1179,1183,1185,1187,1191,1193,1195,1197,1199,1201,1203,1205,
           1207,1209,1211,1215,1219,1221,1233,1235,1237,1239,1241,1243,1245,
           # 2026-07-20 Ferntransfer-Dubletten (1-3.5h M2-Fehler, exakte Admiralty-/classic-
           # Dublette <=1km am selben Ort -> Original gewinnt; verifiziert: La Palma +1.4h,
           # Eiði/Faroe +3.5h & Amplitude 2x). Casablanca->Kanaren/Madeira/Guinea-Bissau,
           # Dakar->Gambia, Reykjavik->Faroe, Cape Town->Greenville(=att 'Sinoe Bay').
           # 2026-07-22 Moderate-Nachbarn-Audit (2-4km): redundant zu besserer unabh.
           # Quelle UND M2-phasenfalsch (dg gegen UTC-normierten Nachbar-Konsens):
           15,    # Porto Grande (= gemessenes Mindelo utide_obs/att/classic 0.8km; -118min)
           1447,  # Buesum Norderpiep (= Buesum Schleuse utide_obs conf8 1.4km; -45..-80min)
           459,   # Bajo Salmedina (= Chipiona utide conf8 3.7km; -37min Transfer-Rauschen)
           121,   # Bata Bay (= Bata att/classic 4.1km, die stimmen ueberein; eutt +83min)
           123,   # San Carlos Bay Fernando Poo (= Luba classic conf10 4.5km; eutt +79min)
           1291,  # Vestmanna (Amphidrom! eutt-k-Transfer 0.72m physikalisch falsch; att 0.9km)
           1303,  # Klaksvik (= classic Klaksvik conf10 2.3km; eutt -96min)
           1325,  # Vestdalseyri (= classic Seydisfjordur conf10 2.4km im selben Fjord; -178min)
           1853,  # Foki Bight (= att np202 3.7km; eutt -118min, Yekaterininskaya-Zonenverdacht)
           1855,  # Russkaya Harbor (= att np202 Zaliv Russkaya Gavan 3.8km; -113min)
           1845,  # Matochkin Strait east end (= att np202 Mys Byk 3.7km; -97min)
           291,   # Bale[sic] d'Arguin (2026-07-23: identische Position wie att_np208_secondary
                  # 'Ile d'Arguin'; NOAA-Zeiten = Pauschal-Offset von Port Etienne/Nouadhibou
                  # ohne Bank-Laufzeit -> ~80min zu frueh. ATT-Gradient Nouadhibou->Arguin->
                  # Cap Sainte-Anne physikalisch stimmig, Nouadhibou per SHOM bestaetigt)
           463,   # Sevilla Rio Guadalquivir (2026-07-23: historischer Stadthafen, liegt heute
                  # in der abgeschleusten Darsena (Schleuse 1926) -> dort kommt keine Tide mehr
                  # an; Puertos Esclusa/Sevilla-2 conf8 4-5.4km flussab decken die lebende Tide ab)
           17,19,21,27,31,35,37,39,205,249,259,261,275,279,281,1281,1299}  # 279=Balingho/Gambia (=att Balingo 0km, ~invertiert)

# 2026-07-20 Referenz-Override: {Station-no -> Referenz-Station-no}. NOAA referenziert diese
# 4 liberianischen Stationen an Cape Town (34 S, falsches Regime -> ~3h invertiert, verifiziert:
# Monrovia HW 11:53 statt real 14:43). Ersatz: von Monrovia (no.219, echte att_np208/classic-
# Harmonik) transferieren; dtHW/dtLW werden auf die Override-Referenz umgerechnet (beide sind
# Cape-Town-relativ, Differenz = Monrovia-relativ). Verifiziert per Vorhersage: Junk River
# entrance HW = Monrovia +/-3min (NOAA: -5min); Harper -48min; Harbel +132min (Aestuar).
REF_OVERRIDE_NO = {203: 219, 213: 219, 215: 219, 217: 219}

FORCE_INCLUDE = {127: 'Kribi, Cameroon',
                 125: 'Malabo (Santa Isabel), Equatorial Guinea',
                 111: 'Annobón, Equatorial Guinea',
                 181: 'Tema, Ghana',
                 183: 'Accra, Ghana',
                 101: 'Mayumba, Gabon',
                 97:  'Cabinda, Angola',
                 83:  'Benguela, Angola',
                 75:  'Tombua (Porto Alexandre), Angola'}

def livenoaa_pts():
    """Stationen der Live-CO-OPS-Dateien (censam/carib/pacif): dieselbe Quelle
    in AKTUELL -> Table-2-Version dort NICHT bauen (Oliver 2026-07-02,
    keine Quell-Duplikate)."""
    pts = []
    for f in glob.glob(f'{HARM}/noaa/harmonics_noaa_censam.txt') + \
             glob.glob(f'{HARM}/noaa/harmonics_noaa_carib.txt') + \
             glob.glob(f'{HARM}/noaa/harmonics_noaa_pacif.txt'):
        t = open(f, encoding='iso-8859-1').read()
        for la, lo in zip(re.findall(r'# !latitude:\s*([\-\d.]+)', t), re.findall(r'# !longitude:\s*([\-\d.]+)', t)):
            pts.append((float(la), float(lo)))
    return pts

def main():
    full = json.load(open(FULL))
    if REGIONS == ['ALL']:
        # Build-all (Oliver 2026-07-02): ALLE Nicht-Referenz-Zeilen des Bands,
        # kein Gap-Filter (grobe Tafel-Koordinaten machen ihn unzuverlaessig);
        # Dedup erfolgt spaeter global ueber alle Quellen.
        gapno = {r['no'] for r in full if not r.get('daily')}
    else:
        gaps = json.load(open(GAPS))
        gapno = {g['no'] for g in gaps if g['region'] in REGIONS}
    gapno |= set(FORCE_INCLUDE)
    byno = {r['no']: r for r in full}
    PTS = refpts() if REGIONS != ['ALL'] else []
    LIVE = livenoaa_pts()
    # --- persistenter Override-Layer: Frontend-Koordinaten-Korrekturen schuetzen ---
    import noaa_overrides as NOV
    raw_by_key = {}
    for r in full:
        clat, clon = COORD_OVERRIDE.get(r['no'], (r['lat'], r['lon']))
        raw_by_key[str(r['no'])] = (clat, clon, r.get('name', ''))
    EXISTING = NOV.parse_existing(OUT)
    OV = NOV.load('noaa_eutt')
    NOV.capture_coords(OV, EXISTING, raw_by_key)
    built = []; skipped = []
    for no in sorted(gapno):
        if no in DROP_NO: continue
        s = byno.get(no)
        if not s or s.get('daily'): continue
        if no in COORD_OVERRIDE:
            s = {**s, 'lat': COORD_OVERRIDE[no][0], 'lon': COORD_OVERRIDE[no][1]}
        _olat, _olon = NOV.apply_coord(OV, no, s['lat'], s['lon'])
        if (_olat, _olon) != (s['lat'], s['lon']):
            s = {**s, 'lat': _olat, 'lon': _olon}
        forced = no in FORCE_INCLUDE
        if not forced and is_us_pacific(s['lat'], s['lon'], s['name']):
            skipped.append((no, s['name'], 'us')); continue
        if PTS and not forced and min(hav(s['lat'], s['lon'], a, b) for a, b in PTS) <= GAP_KM:
            skipped.append((no, s['name'], 'not-gap')); continue
        if LIVE and min(hav(s['lat'], s['lon'], a, b) for a, b in LIVE) <= 3.0:
            skipped.append((no, s['name'], 'live-coops')); continue
        if no in REF_OVERRIDE_NO:
            _refst = byno.get(REF_OVERRIDE_NO[no])
            rn, rr = resolve_ref(_refst['name']) if _refst else (None, None)
            if _refst and s.get('dtHW') is not None and _refst.get('dtHW') is not None:
                s = {**s, 'dtHW': s['dtHW'] - _refst['dtHW'], 'dtLW': s['dtLW'] - _refst['dtLW']}
        else:
            rn, rr = resolve_ref(s['ref'])
        if not rr: skipped.append((no, s['name'], f"noref:{s['ref']}")); continue
        tr = transfer(s, rr)
        if not tr or tr['M2'] < 0.05 and s.get('diurnal_ft') is None:
            skipped.append((no, s['name'], 'tiny')); continue
        tr['refname'] = rn
        if forced:
            s = {**s, '_name_override': FORCE_INCLUDE[no]}
        cty = COUNTRY_OVERRIDE.get(no) or country(s['lat'], s['lon'], s['ref'])
        built.append((s, tr, cty))
    lines = list(HEADER); names = []
    for s, tr, cty in built:
        b, nm, cf = block(s, tr, cty, OV, EXISTING); lines += b; names.append((nm, cf, tr['M2'], s['no']))
    NOV.save('noaa_eutt', OV)
    open(OUT, 'w', encoding='iso-8859-1').write('\n'.join(lines) + '\n')
    print(f"BUILT {len(built)} stations -> {OUT}")
    print(f"skipped {len(skipped)}")
    from collections import Counter
    print('skip reasons:', dict(Counter(r.split(':')[0] for _, _, r in skipped)))
    for nm, cf, m2, no in sorted(names, key=lambda x: -x[2])[:15]:
        print(f"  conf{cf} M2={m2:.2f}  no{no} {nm}")
    return built, skipped

if __name__ == '__main__':
    main()
