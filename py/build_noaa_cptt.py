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
Writes harmonics/noaa/harmonics_noaa_cptt.txt (ISO-8859-1).  Region selectable via argv.
"""
import os, re, json, math, sys, glob, unicodedata
sys.path.insert(0, os.path.join(os.path.expanduser('~'), 'weather', 'py'))

HARM = os.path.expanduser('~/weather/harmonics')
OUT  = f'{HARM}/noaa/harmonics_noaa_cptt.txt'
# Persistenter Neuextrakt 2026-07-02 (py/parse_noaa_table2.py, cptt2018FullBook.pdf);
# der alte Session-Pfad ist tot. GAPS nur fuer den Nicht-ALL-Modus relevant.
FULL = f'{HARM}/help/cptt2018_table2_full.json'
GAPS = '/tmp/claude-1000/-home-oliver/99a597f4-8599-48bf-9982-0299f605aaa8/scratchpad/gaps.json'
FT = 0.3048
GAP_KM = 4.0
# cumulative: all regions built so far go into the one harmonics_noaa_cptt.txt
REGIONS = sys.argv[1].split(',') if len(sys.argv) > 1 else \
    ['SEAsia/PHL/IDN/MY', 'China/Korea', 'IndianOcean/Arabia/EAfrica', 'PacificIslands',
     'Okhotsk/Kamchatka/Kuril', 'Arctic/Siberia', 'Australia/NZ', 'Antarctica', 'Other']

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
         if 'noaa_cptt' not in f]
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
            z0 = None; con = {}; k = i + 1
            zm = _ZL.match(L[k]) if k < n else None
            if zm: z0 = float(zm.group(1)); k += 1
            while k < n:
                if _MER.match(L[k]) or L[k].startswith('#'): break
                cm = _CON.match(L[k])
                if cm and cm.group(1) != 'x': con[cm.group(1)] = (float(cm.group(2)), float(cm.group(3)))
                k += 1
            yield name, dict(con=con, z0=z0, mer=mer, tz=tz, src=os.path.basename(path)); i = k; continue
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
# Diese Namen werden per Teilzeichenkette aufgeloest, und find() nimmt den
# kuerzesten Treffer. Nach den Umbenennungen vom August 2026 faellt "Kure"
# damit auf "Akureyri, Iceland" und "Suva" auf "Suvali, Gujarat, India" --
# ein Neubau haette 33 japanische Stationen aus Island gerechnet, ohne dass
# irgendwo eine Meldung erschienen waere. Darum sind die Namen hier auf den
# vollen Stationsnamen festgenagelt.
REFMAP = {
 'Kure': 'Kure, Hiroshima, Japan', 'Naha': 'Naha, Okinawa, Japan',
 'Sasebo': 'Sasebo, Nagasaki, Japan', 'Moji': 'Moji, Fukuoka, Japan',
 'Kobe': 'Kobe, Hyogo, Japan',
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
 'Colombo': 'Colombo', 'Sagar': 'Sagar Island Lighthouse', 'Karachi': 'Karachi', 'Madras': 'Chennai',
 'Mina Jebel Ali': 'Jebel Ali', 'Mina Al Ahmadi': 'Mina Al Ahmadi', 'Mina Salman': 'Mina Salman',
 'Musay’id': 'Musay', 'Suez': 'Suez', 'Durban': 'Durban', 'Aden': 'Aden', 'Apia': 'Apia',
 # --- Pacific Islands ---
 'Honolulu': 'Honolulu', 'Kwajalein Atoll': 'Kwajalein', 'Suva': 'Suva Harbor', 'Pago Pago': 'Pago Pago',
 'Chuuk': 'Chuuk', 'Pohnpei Harbor': 'Pohnpei', 'Papeete': 'Papeete', 'Auckland': 'Auckland',
 'Dreger Harbor': 'Dreger', 'Townsville': 'Townsville',
 'Nawiliwili': 'Nawiliwili', 'Hilo': 'Hilo', 'Kahului': 'Kahului', 'Moku O Loe': 'Moku O Loe',
 # --- Russian Far East / Okhotsk / Kamchatka / Kuril ---
 'Moji': 'Moji', 'Yamato Wan': 'Ostrov Mamya', 'Paramushiru Island': 'Paramushir',
 # --- Australia / NZ / Mozambique / Guam (final batch) ---
 'Port Hedland': 'Port Hedland', 'Port Adelaide': 'Adelaide', 'Port Phillip': 'Port Phillip',
 'Port Lincoln': 'Port Lincoln', 'Beira': 'Beira', 'Guam': 'Guam',
 # Audit 2026-07-19: ohne Mapping loeste 'Sydney' auf 'Sydney, Nova Scotia, Canada' auf
 # (find() nimmt den kuerzesten Namen) -> Gruppe war +68min daneben. Fort Denison =
 # Sydney Harbour, der tatsaechliche Referenzpegel der NOAA-Tafel.
 'Sydney': 'Fort Denison',
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
    return {'French Polyneisa': 'French Polynesia', 'Moçambique': 'Mozambique'}.get(c, c)

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
    out = {}
    for c, (a, g) in con.items():
        if a <= 0: continue
        if c in ('S2', 'K2'): na = a * k * sS
        elif c in DIURN: na = a * k * sD
        elif c in LONGP: na = a
        else: na = a * k
        sp = SPEED.get(c)
        out[c] = (round(na, 4), round((g + (sp * dt if sp else 0)) % 360, 2))
    M2 = M2r * k; S2 = S2r * k * sS
    return dict(con=out, mer=rr['mer'], tz=rr['tz'], M2=M2, S2=S2, k=k, sD=sD, dt=dt, refF=refF)

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
    if OV is not None:
        import noaa_overrides as _NOV
        name = _NOV.resolve_name(OV, s['no'], name, EXISTING or {})
    tz = tz_lookup(s['lat'], s['lon'])            # authoritative zone for the station's location
    conf = conf_of(tr, s)
    z0 = s.get('mtl_ft')
    z0 = z0 * FT if z0 is not None else round(tr['M2'] + tr['S2'], 3)
    note = (f"NOAA Tide Tables (C&GS/NOS) Pacific+Indian 2018 Table 2 transfer from "
            f"{tr.get('refname','?')} (no.{s['no']}). M2={tr['M2']:.2f} S2={tr['S2']:.2f} "
            f"k={tr['k']:.2f} dt={tr['dt']*60:+.0f}min.")
    out = ['# BEGIN HOT COMMENTS',
           f"# country: {cty or '?'}",
           '# source: NOAA Tide Tables Pacific & Indian Ocean (NOS/C&GS), Table 2 transfer',
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
COORD_OVERRIDE = {
    219:  (47.05, 142.033),    # Port Kholmsk, Sakhalin: PDF prints 41°03' -> 47°03'N
    1751: (1.25, 102.1667),    # Siak River ent. (Riau): PDF prints 105°10' -> 102°10'E (nbrs ~102°)
}
# country fixes where neither reference nor nearest-neighbour resolve a contested border correctly
COUNTRY_OVERRIDE = {1205: 'China'}   # Zhaoshigou (Yalu mouth, Liaoning) — NOAA refs Nampo (NK)

# Audit 2026-07-19: 70 Stationen mit >=1h Vorhersagefehler entfernt (Phasen-Delta gegen
# Messnachbarn <=10km, siehe Memory noaa-eutt-tz-audit). Fehlerklassen: (a) Japan +-9h
# Frame-/Referenzfehler (~45), (b) absurde Fern-Referenzen (Antarktis von Kuril/Do Son,
# Golf von Tai O/Mamya), (c) Cross-Zone (Easter Island, Tuvalu, Provideniya, Pakistan).
# Alle haben Messstationen <=10km daneben; NICHT neu bauen.
DROP_NO = {83, 85, 147, 441, 443, 445, 569, 573, 587, 589, 591, 639, 643, 653, 655, 659,
           661, 665, 679, 699, 709, 717, 725, 743, 755, 829, 841, 907, 909, 929, 931, 933,
           939, 979, 1431, 1441, 1577, 1937, 1939, 1959, 2163, 2817, 2837, 2899, 3115, 3577, 3593, 3595,
           3623, 3665, 3951, 3973, 3975, 3977, 3983, 3985, 3987, 3989, 3991, 3995}

FORCE_INCLUDE = {1725: 'Banda Aceh (Ulee Lheue), Sumatra, Indonesia',
                 1869: 'Cirebon, Java, Indonesia',
                 1885: 'Pasuruan, Java, Indonesia',
                 3925: 'Mahajanga, Madagascar'}

def livenoaa_pts():
    """Live-CO-OPS-Stationen (censam/carib/pacif): Table-2 = dieselbe Quelle
    in alt -> dort nicht bauen (keine Quell-Duplikate, Oliver 2026-07-02)."""
    pts = []
    for base in ('censam', 'carib', 'pacif'):
        f = f'{HARM}/noaa/harmonics_noaa_{base}.txt'
        if not os.path.exists(f): continue
        t = open(f, encoding='iso-8859-1').read()
        for la, lo in zip(re.findall(r'# !latitude:\s*([\-\d.]+)', t),
                          re.findall(r'# !longitude:\s*([\-\d.]+)', t)):
            pts.append((float(la), float(lo)))
    return pts

def main():
    full = json.load(open(FULL))
    if REGIONS == ['ALL']:
        # Build-all (Oliver 2026-07-02): alle Nicht-Referenz-Zeilen, kein
        # Gap-Filter; globale Dedup spaeter ueber alle Quellen.
        gapno = {r['no'] for r in full if not r.get('daily')}
    else:
        gaps = json.load(open(GAPS))
        gapno = {g['no'] for g in gaps if g['region'] in REGIONS}
    gapno |= set(FORCE_INCLUDE)
    byno = {r['no']: r for r in full}
    PTS = refpts() if REGIONS != ['ALL'] else []
    LIVE = livenoaa_pts()
    import noaa_overrides as NOV
    raw_by_key = {}
    for r in full:
        clat, clon = COORD_OVERRIDE.get(r['no'], (r['lat'], r['lon']))
        raw_by_key[str(r['no'])] = (clat, clon, r.get('name', ''))
    EXISTING = NOV.parse_existing(OUT)
    OV = NOV.load('noaa_cptt')
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
    NOV.save('noaa_cptt', OV)
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
