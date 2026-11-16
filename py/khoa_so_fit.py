#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Messfits aus den KHOA-Kurz-/Langzeitpegeln (장·단기 조석관측, Badanuri-Karte, SO_xxxx).

Oliver 16.11.2026: KHOA (jhlee22@korea.kr) verwies auf die Badanuri-Karte; Download py-frei per
scratch-Skript nach quellen/water_levels/Korea_KHOA_SO/<SO_xxxx>/{detail.html,reihe.csv}.
Regeln (Oliver 16.11.): > 10 km vom naechsten Nicht-FES-Satz -> neu; 3-10 km -> neu, wenn die Messung
merklich vom naechsten Satz abweicht (Kurvenabstand > 5 %); < 3 km -> nur Qualitaetskontrolle.
Mehrere Messungen am selben Ort (<= 1 km): laengste Reihe, bei Gleichstand die juengste.

Reihe: Stundenwerte in cm ueber Kartennull (기본수준면), Zeit KST -> UTC (-9 h). Fit wie py/qld_msq_fit.py.
Kurzreihen: K2/P1 koppelt danach py/pegel_kopplung_lauf.py.

Usage: venv/bin/python py/khoa_so_fit.py --probe SO_0326        Fit + Vergleich mit den amtlichen Konstanten
       venv/bin/python py/khoa_so_fit.py --liste                 alle fitten -> harmonics/help/khoa_so_fit.csv
       venv/bin/python py/khoa_so_fit.py --eintragen [--schreiben]  Saetze mit aktion=neu eintragen (+ neu_pruefen)
"""
import csv
import datetime as dt
import html
import json
import os
import re
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import health_check as H                                           # noqa: E402
import qld_msq_fit as Q                                            # noqa: E402
import scheitelfit as SF                                           # noqa: E402
import seine_haropa_fit as S                                       # noqa: E402
import xtide_modell as X                                           # noqa: E402

ROOT = S.ROOT
ZIEL = S.ZIEL
QUELLE = os.path.join(ROOT, 'quellen/water_levels/Korea_KHOA_SO')
ERGEBNIS = os.path.join(ROOT, 'harmonics/help/khoa_so_fit.csv')


# Positionsfehler der KHOA-Liste, an der Tide erkannt (Fit passt 1-4 % zu fernen Saetzen, 60 % zu den Nachbarn)
POS_KORREKTUR = {'SO_1238': (34.68389, 126.06444)}   # 신안옥도: Laenge 127.064 statt 126.064 (Anjwado, Sinan)


def liste():
    L = []
    for f in ('liste_long.json', 'liste_short.json'):
        L += json.load(open(os.path.join(QUELLE, f), encoding='utf-8'))
    for x in L:
        if x['obs_post_i'] in POS_KORREKTUR:
            x['obs_lat'], x['obs_lon'] = POS_KORREKTUR[x['obs_post_i']]
    return L


def detail(sid):
    p = os.path.join(QUELLE, sid, 'detail.html')
    return open(p, encoding='utf-8', errors='replace').read() if os.path.exists(p) else ''


def zeitraum(t):
    a = re.search(r'id="startDate">\s*(\d{4}-\d\d-\d\d)', t)
    b = re.search(r'id="endDate">\s*(\d{4}-\d\d-\d\d)', t)
    return (a.group(1) if a else '', b.group(1) if b else '')


def amtlich(t):
    """Amtliche Konstanten der Detailseite: {name: (amp_m, g_grad)}, Z0 in m."""
    txt = html.unescape(re.sub(r'<[^>]+>', ' ', t))
    k = {}
    for n, a, g in re.findall(r'\s([A-Z0-9][A-Z0-9()]{0,7})\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)', txt):
        if n not in k:
            k[n] = (float(a) / 100.0, float(g))
    return k


def reihe(sid):
    p = os.path.join(QUELLE, sid, 'reihe.csv')
    if not os.path.exists(p) or os.path.getsize(p) < 2000:
        return None
    d = pd.read_csv(p, encoding='utf-8-sig')
    d.columns = ['no', 'name', 'zeit', 'cm']
    s = pd.Series(d['cm'].values / 100.0, index=pd.to_datetime(d['zeit']) - pd.Timedelta(hours=9)).dropna()
    s = s[~s.index.duplicated()].sort_index()
    return s[s.index.minute == 0]


def fitte(s, kopf, voll):
    namen, speeds, arg, fak = kopf
    tage = max(1, (s.index[-1] - s.index[0]).days)
    nutz = Q.rayleigh(voll, speeds, namen, tage)
    s, t, z0, w, h, aus = Q.fit(s, nutz, kopf, speeds, arg, fak)
    rms = float(np.sqrt(np.mean((s.values - h) ** 2)))
    r2 = 1 - np.var(s.values - h) / np.var(s.values)
    tief = h <= np.quantile(h, 0.05)
    plateau = float(np.median(s.values[tief] - h[tief]))
    tg = np.arange(dt.datetime(2008, 1, 1).timestamp(), dt.datetime(2027, 1, 1).timestamp(), 1800.0)
    lat_kurve = -float(SF.hoehe_und_ableitungen(tg, 0.0, w, kopf)[0].min())
    return dict(s=s, t=t, z0=z0, w=w, h=h, aus=aus, rms=rms, r2=r2, plateau=plateau, tage=tage, nutz=nutz, lat_kurve=lat_kurve)


def kopf_und_liste():
    kopf = X.kopf_lesen(ZIEL)
    namen = kopf[0]
    voll = SF.konstituenten(namen, SF.CONSTIT_67) + [k for k in S.OBERTIDEN if k in namen]
    return kopf, voll


def probe(sid):
    kopf, voll = kopf_und_liste()
    speeds = kopf[1]
    t = detail(sid)
    a = amtlich(t)
    s = reihe(sid)
    print(sid, zeitraum(t), 'Werte', None if s is None else len(s))
    f = fitte(s, kopf, voll)
    print('Fit: %d d, %d Konst., R2 %.3f, RMS %.1f cm, Z0 %.3f (amtlich Z0 %s), Plateau %+.0f cm' % (
        f['tage'], len(f['nutz']), f['r2'], 100 * f['rms'], f['z0'], a.get('Z0'), 100 * f['plateau']))
    for c in ('M2', 'S2', 'K1', 'O1', 'N2', 'K2', 'P1', 'M4', 'MS4'):
        if c in f['w'] and c in a:
            g_utc = f['w'][c][1]
            g_kst = (g_utc + 9 * speeds[c]) % 360          # Phase im KST-Meridian
            print('  %-4s fit %.3f m  g_UTC %6.1f  g_KST %6.1f   amtlich %.3f m  g %6.1f' % (c, f['w'][c][0], g_utc, g_kst, *a[c]))



# ---------------------------------------------------------------- Hauptlauf
CACHE = os.path.join(ROOT, 'cache/khoa_so_fits.pkl')


def alle_fits():
    """Fit je Messung (gecacht); nur Reihen ab 25 Tagen."""
    import pickle
    alt = pickle.load(open(CACHE, 'rb')) if os.path.exists(CACHE) else {}
    kopf, voll = kopf_und_liste()
    neu = 0
    for x in liste():
        sid = x['obs_post_i']
        if sid in alt:
            continue
        s = reihe(sid)
        if s is None or len(s) < 24 * 25:
            alt[sid] = None
            continue
        try:
            f = fitte(s, kopf, voll)
        except Exception as e:                                   # noqa: BLE001
            print('  Fit scheitert', sid, e)
            alt[sid] = None
            continue
        alt[sid] = {k: f[k] for k in ('z0', 'w', 'aus', 'rms', 'r2', 'plateau', 'tage', 'nutz', 'lat_kurve')}
        alt[sid].update(von=str(f['s'].index[0].date()), bis=str(f['s'].index[-1].date()), pts=len(f['s']))
        neu += 1
        if neu % 25 == 0:
            print('  %d Fits ...' % neu, flush=True)
            pickle.dump(alt, open(CACHE, 'wb'))
    pickle.dump(alt, open(CACHE, 'wb'))
    return alt


def eigene_namen():
    """Namen der schon eingetragenen KHOA-SO-Saetze (damit ein neuer Lauf sie nicht als Bestand zaehlt)."""
    namen, offen = set(), False
    for z in open(ZIEL, encoding='iso-8859-1'):
        if z.startswith('# source: KHOA tide observation SO_'):
            offen = True
        elif offen and not z.startswith('#'):
            namen.add(z.rstrip('\n'))
            offen = False
        elif z.startswith('# BEGIN HOT'):
            offen = False
    return namen


def bestand():
    eigen = eigene_namen()
    return [r for r in H.load_records() if r['lat'] and 32 < r['lat'] < 39.5 and 124 < r['lon'] < 131.5 and not r['current']
            and 'fes' not in r['file'].split('/')[-1].lower() and r['name'] not in eigen]


def platzhalter(la, lo):
    """KHOA-Fuellwerte: Breite D°D'D\" (34.57611 = 34°34'34\"), Laenge xx°12'12\" (63 der 699 Eintraege)."""
    d = int(la)
    return abs(la - (d + d / 60 + d / 3600)) < 0.0002 or abs((lo - int(lo)) - (12 / 60 + 12 / 3600)) < 0.0002


def kartennull(w, a):
    """Koreanischer Kartennull (약최저저조면) = MSL - (M2+S2+K1+O1); amtlicher Z0 = MSL ueber Kartennull."""
    if a.get('Z0') and all(c in a for c in ('M2', 'S2', 'K1', 'O1')):
        return a['Z0'][0], 'KHOA Z0'
    return sum(w[c][0] for c in ('M2', 'S2', 'K1', 'O1') if c in w), 'M2+S2+K1+O1'


def auswerten():
    fits = alle_fits()
    B = bestand()
    L = {x['obs_post_i']: x for x in liste()}
    kandid = []
    for sid, f in fits.items():
        if not f:
            continue
        x = L[sid]
        a = amtlich(detail(sid))
        amt = ''
        if all(c in a for c in ('M2', 'S2', 'K1', 'O1')):
            sp = kopf_und_liste()[0][1]
            au = {c: (v[0], (v[1] - 9 * sp[c]) % 360) for c, v in a.items() if c in sp}   # amtliche Phasen in KST
            amt = '%.0f' % (100 * H.curve_diff(Q.rec(f['w']), Q.rec(au))[1])
        kandid.append(dict(sid=sid, f=f, x=x, a=a, amt=amt, lat=float(x['obs_lat']), lon=float(x['obs_lon']),
                           platzhalter=platzhalter(float(x['obs_lat']), float(x['obs_lon']))))
    # Gruppen <= 1 km: laengste Reihe, bei Gleichstand juengste
    kandid.sort(key=lambda k: (-k['f']['tage'], k['f']['bis']), reverse=False)
    kandid.sort(key=lambda k: (k['f']['tage'] >= 300, k['f']['tage'], k['f']['bis']), reverse=True)
    gruppen = []
    for k in kandid:
        if k['platzhalter']:                       # nicht mit echten Orten zusammenfassen
            gruppen.append([k])
            continue
        for g in gruppen:
            if g[0]['platzhalter']:
                continue
            if H.km(k, g[0]) <= 1.0:
                g.append(k)
                break
        else:
            gruppen.append([k])
    pool = [dict(lat=r['lat'], lon=r['lon'], name=r['name'], file=r['file'], z=r['z'], tot=r['tot'], neu=False) for r in B]
    zeilen = []
    for g in gruppen:
        k = g[0]
        f = k['f']
        rk = Q.rec(f['w'])
        nah = sorted(((H.km(k, r), r) for r in pool), key=lambda t: t[0])
        d0, r0 = nah[0]
        diff0 = 100 * H.curve_diff(rk, r0)[1]
        name, zus = ortsname(k['x']['obs_post_n'])
        gruende = []
        if f['r2'] < 0.9 and f['tage'] < 300:      # Ostkueste: Mikrotide unter Wetterrauschen, Jahresreihe trennt sie trotzdem
            gruende.append('R2 %.2f' % f['r2'])
        if f['plateau'] > 0.15:
            gruende.append('trockenfallend')
        if k['amt'] and float(k['amt']) > 3:
            gruende.append('weicht %s %% von KHOA-Konstanten ab' % k['amt'])
        if k['platzhalter']:
            aktion = 'position'
            gruende.append('Platzhalter-Koordinaten in der KHOA-Liste')
        elif gruende:
            aktion = 'weg'
        elif d0 > 10:
            aktion = 'neu'
        elif d0 >= 3:
            aktion = 'neu' if diff0 > 5 else 'gleich'
        else:
            aktion = 'kontrolle'
        if aktion == 'neu':
            pool.append(dict(lat=k['lat'], lon=k['lon'], name=name + ' [neu]', file='khoa_so', z=rk['z'], tot=rk['tot'], neu=True))
        zeilen.append(dict(sid=k['sid'], khoa_name=k['x']['obs_post_n'], name=name, kontext=zus, lat='%.5f' % k['lat'], lon='%.5f' % k['lon'],
                           von=f['von'], bis=f['bis'], tage=f['tage'], typ=k['x']['obs_type'], r2='%.3f' % f['r2'], rms_cm='%.1f' % (100 * f['rms']),
                           m2='%.3f' % f['w']['M2'][0], amtlich_diff=k['amt'], naechster=r0['name'], naechster_datei=r0['file'].split('/')[-1],
                           km='%.1f' % d0, diff_prozent='%.0f' % diff0, aktion=aktion, grund='; '.join(gruende),
                           weitere=' '.join(x['sid'] for x in g[1:])))
    with open(ERGEBNIS, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(zeilen[0]))
        w.writeheader()
        w.writerows(zeilen)
    import collections
    print(len(zeilen), 'Orte ->', os.path.relpath(ERGEBNIS, ROOT))
    print(collections.Counter(z['aktion'] for z in zeilen))
    return zeilen



# ---------------------------------------------------------------- Eintragen
ORTE = os.path.join(ROOT, 'cache/khoa_so_nominatim.json')
PROVINZ = {'Gyeonggi': 'Gyeonggi', 'Incheon': 'Incheon', 'Chungcheongnam': 'South Chungcheong', 'South Chungcheong': 'South Chungcheong',
           'Jeollabuk': 'North Jeolla', 'Jeonbuk': 'North Jeolla', 'North Jeolla': 'North Jeolla', 'Jeollanam': 'South Jeolla',
           'South Jeolla': 'South Jeolla', 'Jeonnam': 'South Jeolla', 'Gwangju': 'South Jeolla', 'Gyeongsangnam': 'South Gyeongsang',
           'South Gyeongsang': 'South Gyeongsang', 'Busan': 'Busan', 'Ulsan': 'Ulsan', 'Gyeongsangbuk': 'North Gyeongsang',
           'North Gyeongsang': 'North Gyeongsang', 'Gangwon': 'Gangwon', 'Jeju': 'Jeju'}


def ort_info(lat, lon):
    """Nominatim reverse (zoom 10, englisch): (Kreis, Provinz), gecacht."""
    import time
    import urllib.request
    c = json.load(open(ORTE, encoding='utf-8')) if os.path.exists(ORTE) else {}
    k = '%.4f,%.4f' % (lat, lon)
    if k not in c:
        url = 'https://nominatim.openstreetmap.org/reverse?format=jsonv2&zoom=10&accept-language=en&lat=%.5f&lon=%.5f' % (lat, lon)
        req = urllib.request.Request(url, headers={'User-Agent': 'weather-tides/1.0'})
        try:
            c[k] = json.load(urllib.request.urlopen(req, timeout=30)).get('address', {})
        except Exception as e:                                       # noqa: BLE001
            print('  Nominatim', k, e)
            c[k] = {}
        time.sleep(1.1)
        json.dump(c, open(ORTE, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    a = c[k]
    kreis = a.get('county') or a.get('city') or a.get('town') or ''
    kreis = re.sub(r'(-gun|-si|-gu| County| City)$', '', kreis).strip()
    st = a.get('state') or a.get('province') or a.get('city') or ''
    prov = next((v for n, v in PROVINZ.items() if n.lower() in st.lower()), '')
    return kreis, prov


def ortsteil(lat, lon):
    """Nominatim reverse zoom 14: Dorf/Insel/Ortsteil (fuer Namen ohne Ort und gleichnamige Saetze)."""
    import time
    import urllib.request
    p = ORTE.replace('.json', '_z14.json')
    c = json.load(open(p, encoding='utf-8')) if os.path.exists(p) else {}
    k = '%.4f,%.4f' % (lat, lon)
    if k not in c:
        url = 'https://nominatim.openstreetmap.org/reverse?format=jsonv2&zoom=14&accept-language=en&lat=%.5f&lon=%.5f' % (lat, lon)
        try:
            c[k] = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'weather-tides/1.0'}), timeout=30)).get('address', {})
        except Exception as e:                                       # noqa: BLE001
            print('  Nominatim', k, e)
            c[k] = {}
        time.sleep(1.1)
        json.dump(c, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    a = c[k]
    for f in ('island', 'islet', 'hamlet', 'village', 'quarter', 'suburb', 'town'):
        if a.get(f) and re.fullmatch(r"[A-Za-z' .-]+", a[f]):
            return a[f]
    return ''


def eintragen(schreib):
    from sicher_schreiben import schreiben
    kopf, voll = kopf_und_liste()
    namen = kopf[0]
    Lz = open(ZIEL, encoding='iso-8859-1').read().rstrip('\n').split('\n')
    vorhanden = {z for z in Lz if z and not z.startswith(('#', ' ')) and ', ' in z}
    fits = alle_fits()
    heute = dt.date.today().strftime('%Y%m%d')
    zeilen = [z for z in csv.DictReader(open(ERGEBNIS, encoding='utf-8')) if z['aktion'] == 'neu']
    pruef = []
    namen_neu = set()
    for z in zeilen:
        f = fits[z['sid']]
        la, lo = float(z['lat']), float(z['lon'])
        kreis, prov = ort_info(la, lo)
        basis = z['name']
        if not basis or basis.lower() == kreis.lower():           # "고흥부근(T-3)": nur der Kreis bekannt -> Ortsteil als Name
            basis = ortsteil(la, lo) or basis
        if not basis:
            print('  ohne Namen (Oliver fragen):', z['sid'], z['khoa_name'])
            continue
        kontext = z['kontext'] or (kreis if kreis and kreis.lower().replace('-', '') not in basis.lower().replace('-', '') else '')
        name = '%s%s, South Korea' % (basis, ' (%s)' % kontext if kontext else '')
        if name in vorhanden or name in namen_neu:                 # gleichnamig: Ortsteil statt Kennung (Namen ohne Codes)
            ot = ortsteil(la, lo)
            if ot and ot.lower() not in name.lower():
                name = '%s (%s), South Korea' % (basis, ', '.join(x for x in (ot, kontext) if x))
        if name in vorhanden or name in namen_neu:
            print('  gleichnamig, uebersprungen:', name, z['sid'])
            continue
        namen_neu.add(name)
        a = amtlich(detail(z['sid']))
        z0, bezug = kartennull(f['w'], a)
        lang = f['tage'] >= 300
        blk = ['#', '# ' + name, '# BEGIN HOT COMMENTS', '# country: South Korea',
               '# source: KHOA tide observation %s (Badanuri), least squares' % z['sid'],
               '# station_id_context: KHOA-%s' % z['sid'], '# date_imported: %s' % heute,
               '# datum: Korean chart datum (approx. lowest low water, Z0 = %s)' % bezug, '# confidence: %d' % (7 if lang else 6),
               '# utide: pts=%d period=%s..%s r2=%.4f rms=%.4fm const=%d' % (f['pts'], f['von'], f['bis'], f['r2'], f['rms'], len(f['nutz'])),
               '# note: %s Messfit aus der KHOA-%s (%s Tage, py/khoa_so_fit.py), Oliver.' % (
                   heute, 'Langzeitmessung' if z['typ'] == 'L' else 'Kurzzeitmessung', f['tage']),
               '# note: Naechster Satz %s %s km, Kurvenabstand %s %%.%s' % (z['naechster'].split(',')[0], z['km'], z['diff_prozent'],
                   (' KHOA-Konstanten %s %%.' % z['amtlich_diff']) if z['amtlich_diff'] else ''),
               '# !units: meters', '# !longitude: %.4f' % lo, '# !latitude: %.4f' % la]
        if prov:
            blk.append('# province: %s' % prov)
        blk += [name, '+00:00 :Asia/Seoul', '%.4f meters' % z0]
        blk += ['%-15s %.4f  %.2f' % (c, *f['w'][c]) if c in f['w'] and f['w'][c][0] >= 0.00005 else 'x 0 0' for c in namen]
        Lz += blk
        pruef.append(dict(datei=os.path.basename(ZIEL), name=name))
        print('  %-55s %s %s d  %s km %s %%' % (name, z['sid'], f['tage'], z['km'], z['diff_prozent']))
    print(len(pruef), 'neue Saetze')
    if schreib:
        schreiben(ZIEL, '\n'.join(Lz) + '\n')
        p = os.path.join(ROOT, 'harmonics/help/neu_pruefen_%s.csv' % heute)
        alt = list(csv.DictReader(open(p, encoding='utf-8'))) if os.path.exists(p) else []
        with open(p, 'w', newline='', encoding='utf-8') as fh:
            w = csv.DictWriter(fh, fieldnames=['datei', 'name'])
            w.writeheader()
            w.writerows(alt + pruef)
        print('->', os.path.relpath(ZIEL, ROOT), os.path.relpath(p, ROOT))


# ---------------------------------------------------------------- Namen (Revised Romanization, vereinfacht)
_ANL = ['g', 'kk', 'n', 'd', 'tt', 'r', 'm', 'b', 'pp', 's', 'ss', '', 'j', 'jj', 'ch', 'k', 't', 'p', 'h']
_VOK = ['a', 'ae', 'ya', 'yae', 'eo', 'e', 'yeo', 'ye', 'o', 'wa', 'wae', 'oe', 'yo', 'u', 'wo', 'we', 'wi', 'yu', 'eu', 'ui', 'i']
_AUS = ['', 'k', 'k', 'k', 'n', 'n', 'n', 't', 'l', 'k', 'm', 'l', 'l', 'l', 'p', 'l', 'm', 'p', 'p', 't', 't', 'ng', 't', 't', 'k', 't', 'p', 't']
# Auslaut vor Vokal (Bindung): Konsonant wandert als Anlaut weiter
_BIND = ['', 'g', 'kk', 'ks', 'n', 'nj', 'nh', 'd', 'r', 'lg', 'lm', 'lb', 'ls', 'lt', 'lp', 'lh', 'm', 'b', 'bs', 's', 'ss', 'ng', 'j', 'ch', 'k', 't', 'p', 'h']


def _silben(w):
    out = []
    for ch in w:
        c = ord(ch) - 0xAC00
        if 0 <= c < 11172:
            out.append((c // 588, (c % 588) // 28, c % 28))
        else:
            out.append(ch)
    return out


def roman(w):
    """Hangul-Wort -> Revised Romanization mit den haeufigsten Lautregeln (Bindung, Nasalierung, l-Angleichung)."""
    s = _silben(w)
    r = ''
    for i, x in enumerate(s):
        if isinstance(x, str):
            r += x
            continue
        a, v, e = x
        vor = s[i - 1] if i and not isinstance(s[i - 1], str) else None
        ini = _ANL[a]
        if vor:
            pe = vor[2]
            if a == 11 and pe and pe != 21:              # Bindung: Auslaut + ㅇ -> Anlaut (wurde beim Vorgaenger weggelassen)
                ini = _BIND[pe]
            elif a == 5:                                  # ㄹ-Anlaut: nach Vokal r, nach l/n l, sonst n
                ini = 'r' if not pe else ('l' if _AUS[pe] in ('l', 'n') else 'n')
            elif a == 2 and _AUS[pe] == 'l':
                ini = 'l'
        elif a == 5:
            ini = 'r'
        nach = s[i + 1] if i + 1 < len(s) and not isinstance(s[i + 1], str) else None
        aus = _AUS[e]
        if nach and e:
            na = nach[0]
            if na == 11 and e != 21:
                aus = ''                                  # wandert zur naechsten Silbe
            elif na in (2, 6) or (na == 5 and aus not in ('l', 'n')):   # Nasalierung vor ㄴ/ㅁ (und ㄹ->n)
                aus = {'k': 'ng', 't': 'n', 'p': 'm'}.get(aus, aus)
            elif na == 5 and aus == 'n':
                aus = 'l'
        r += ini + _VOK[v] + aus
    return r


_ENDUNG = [('항구', 'hanggu'), ('항', 'hang'), ('리', 'ri'), ('면', 'myeon'), ('동', 'dong'), ('읍', 'eup'), ('포구', 'pogu')]


def ortsname_roh(n):
    """KHOA-Bezeichnung saeubern: Jahres-/Typ-Zusaetze weg, nur der Ortsteil."""
    m = re.search(r'조석관측\((\S+?)\s*\d+일\)', n)
    if m:
        n = m.group(1)
    n = re.sub(r'^(A-)?\d{4}(-\d{2})?\s*년?[_ ]*', '', n)
    n = re.sub(r'^(장기관측|단기관측|장기조석관측)[_ ]*', '', n)
    n = re.sub(r'_?\d{4}년$|_\d+분.*$|\d*day$|\(\d+년\)$', '', n)
    n = re.sub(r'\s*(부근|인근)?\s*(관측|조석관측)?$', '', n)
    n = re.sub(r'(?<=[가-힣])\d+$', '', n).strip(' _')
    n = re.sub(r'(?<=[가-힣])([동서남북]측|부근|인근|앞|전면)$', '', n)
    return n


# Kuestenkreise/-staedte: steht einer davor (강화외포, 진도서망, 고흥금진항), wird er Klammerkontext
KREISE = ('강화 옹진 인천 김포 시흥 안산 화성 평택 당진 서산 태안 홍성 보령 서천 군산 김제 부안 고창 영광 함평 무안 목포 신안 '
          '진도 해남 완도 강진 장흥 보성 고흥 여수 순천 광양 남해 하동 사천 고성 통영 거제 창원 마산 진해 부산 울산 경주 포항 '
          '영덕 울진 삼척 동해 강릉 양양 속초 제주 서귀포 울릉 백령 연평').split()


def kreis_abtrennen(n):
    for k in KREISE:
        if n.startswith(k) and len(n) - len(k) >= 2 and not n[len(k):].startswith(('도', '항', '리')):
            return n[len(k):], k
    return n, ''


RICHTUNG = r'(?:[동서남북]{1,2}측?|북측|남측|동측|서측)'


def _wort(w):
    if not re.search(r'[가-힣]', w):
        return w
    if w.endswith('방파제') and len(w) > 4:
        return roman(w[:-3]).capitalize() + ' Breakwater'
    for k, rr in _ENDUNG:
        if w.endswith(k) and len(w) > len(k) + 1:
            return roman(w[:-len(k)]).capitalize() + '-' + rr
    return roman(w).capitalize()


# beschreibende Bezeichnungen (keine Ortsnamen): Uebersetzung, Kontext kommt aus Nominatim
BESCHREIBUNG = {'여수해만입구': 'Yeosu Bay Entrance', 'GSCaltex': 'GS Caltex Terminal', '해양박물관': 'Maritime Museum',
                '신안중공업': 'Sinan Shipyard'}


def ortsname(n):
    n = ortsname_roh(n)
    if n in BESCHREIBUNG:
        return BESCHREIBUNG[n], ''
    zus = ''
    m = re.match(r'^(.*?)\s*\((.*)\)$', n)
    if m:
        n, zus = m.group(1).strip(), m.group(2).strip()
    if re.fullmatch(r'Elipsoid|Ellipsoid|\d+|T-\d+', zus, re.I):        # Messtechnik/Jahr/Punktnummer: kein Ort
        zus = ''
    if zus and (n.endswith(('부근', '인근')) or re.search(r'\s*(등|일대)$|항로$', n)):   # "군산부근(외도)": Ort steht in der Klammer
        n, zus = zus, ('' if re.search(r'\s*(등|일대)$|항로$', n) else re.sub(r'(부근|인근)$', '', n))
    n = re.sub(r'(부근|인근)$', '', n)
    n = re.sub(r'항포구$', '항', n)
    n = re.sub(r'(?<=[도항리포])' + RICHTUNG + r'$', '', n)                  # 대부도남서, 상왕등도북서측
    n = ' '.join(w for w in n.split() if not re.fullmatch(RICHTUNG, w))      # 갈도 남측
    m = re.match(r'^([가-힣]{2,}도)([가-힣]{2,})$', n)                      # 비금도가산 -> Gasan (Bigeumdo)
    if m and not m.group(2).endswith('도') and not zus:
        n, zus = m.group(2), m.group(1)
    if re.search(r'항로$', n):                                               # Faehrroute ohne Ort: Name kommt aus Nominatim
        n = ''
    if ' ' not in n and '_' not in n:
        n, kr = kreis_abtrennen(n)
        zus = zus or kr
    name = ' '.join(_wort(w) for w in re.split(r'[\s_]+', n) if w)
    zus = re.sub(r'(부근|인근)$', '', zus)
    zus = ' '.join(_wort(w) for w in re.split(r'[\s_]+', zus) if w)
    return name, zus

if __name__ == '__main__':
    if '--probe' in sys.argv:
        for sid in sys.argv[sys.argv.index('--probe') + 1:]:
            probe(sid)
    elif '--liste' in sys.argv:
        auswerten()
    elif '--eintragen' in sys.argv:
        eintragen('--schreiben' in sys.argv)
