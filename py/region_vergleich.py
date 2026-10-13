#!/usr/bin/env python3
"""Regionsvergleich: Dubletten, Plausibilitaet, Positionen und Namen.

Automatisiert die schrittweise Pruefung, die im Oktober 2026 fuer die
chinesische Kueste von Hand gemacht wurde:

  1. Dublette: ein Satz geringerer Guete liegt hoechstens DUP_KM von einem
     besseren Satz entfernt -> archivieren.
  2. Plausibilitaet der uebrigen Saetze gegen die besten Nachbarn
     (bis NACHBAR_KM, nach Entfernung gewichtet): M2-Hub und -Phase,
     S2/M2, Tagestiden. Nur Hub-Fehler -> korrigieren; Zeitfehler -> pruefen.
  3. Position: Rasterposition (Buchwert auf Bogenminuten), Nominatim
     (Land/Wasser, Ortsname).
  4. Name: Wade-Giles-Schreibweise, angehaengtes "dao".

Es wird nichts geschrieben ausser der Vorschlagstabelle
harmonics/help/region_<name>_<datum>.csv.

    python3 py/region_vergleich.py Taiwan [--ohne-nominatim] [--ohne-ioc]

Bei Dubletten zweier Messsaetze (Rang 1-3) entscheidet, wenn ein IOC-Pegel
bis 1.5 km daneben liegt, die Messung der letzten 60 Tage statt des Rangs.
"""
import csv
import json
import math
import cmath
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, km, auf_raster, ROOT  # noqa: E402

DUP_KM = 5.0
NACHBAR_KM = 60.0
# Rang der Quellen: kleiner = besser. Gemessene bzw. aus amtlichen
# Vorhersagen gefittete Saetze vor Originalanalysen vor Buchuebertragungen.
RANG = [('harmonics/utide/', 1), ('harmonics/ticon/', 2), ('harmonics/classic/', 3),
        ('harmonics/att/', 4), ('harmonics/noaa/', 5)]
UA = 'tidal-harmonics-check/1.0 (oliver.k73@gmail.com)'


def rang(r):
    return next((v for k, v in RANG if r['file'].startswith(k)), 9)


def kurz(f):
    return os.path.basename(f).replace('harmonics_', '').replace('.txt', '')


def amp(r, c):
    return abs(r['z'][c])


def phase(r, c):
    # z = A * exp(-i g)  (health_check)  ->  g = -arg(z)
    return (-math.degrees(cmath.phase(r['z'][c]))) % 360


def dphi(a, b):
    return (a - b + 180) % 360 - 180


def interpol(ref, r):
    """Komplexe, nach 1/d gewichtete Mittelung der Nachbarn."""
    w = sum(1 / max(d, 0.5) for d, _ in ref)
    return {c: sum(n['z'][c] / max(d, 0.5) for d, n in ref) / w for c in r['z']}


def nominatim(lat, lon):
    url = ('https://nominatim.openstreetmap.org/reverse?' + urllib.parse.urlencode(
        dict(lat=lat, lon=lon, format='jsonv2', zoom=17, **{'accept-language': 'en'})))
    try:
        req = urllib.request.Request(url, headers={'User-Agent': UA})
        j = json.load(urllib.request.urlopen(req, timeout=25))
    except Exception as e:  # noqa: BLE001
        return 'Fehler', str(e)[:40]
    time.sleep(1.1)
    if 'lat' not in j:
        return 'Wasser', ''
    d = km(dict(lat=lat, lon=lon), dict(lat=float(j['lat']), lon=float(j['lon'])))
    art = j.get('category', '')
    name = j.get('name') or ''
    ort = j.get('display_name', '')[:60]
    if art == 'boundary' or d > 1.0:
        return 'Wasser', 'naechste Zuordnung %.1f km: %s' % (d, ort)
    return 'Land', '%s/%s %s | %s' % (art, j.get('type', ''), name, ort)


IOC = 'https://www.ioc-sealevelmonitoring.org/service.php'
_IOC_LISTE = None


def ioc_station(lat, lon, max_km=1.5):
    """Naechster IOC-Pegel bis max_km -> Code oder None."""
    global _IOC_LISTE
    if _IOC_LISTE is None:
        try:
            _IOC_LISTE = json.load(urllib.request.urlopen(IOC + '?query=stationlist&showall=all', timeout=60))
        except Exception:  # noqa: BLE001
            _IOC_LISTE = []
    best = None
    for s in _IOC_LISTE:
        try:
            d = km(dict(lat=lat, lon=lon), dict(lat=float(s['Lat']), lon=float(s['Lon'])))
        except (TypeError, ValueError, KeyError):
            continue
        if d <= max_km and (best is None or d < best[0]):
            best = (d, s['Code'])
    return best[1] if best else None


def ioc_reihe(code, tage=60):
    """Stundenwerte der letzten `tage` Tage -> (t, h) als numpy-Arrays."""
    import numpy as np
    from datetime import datetime, timedelta, timezone
    ende = datetime.now(timezone.utc).date()
    t, h = [], []
    for k in range(0, tage, 30):
        a, b = ende - timedelta(days=tage - k), ende - timedelta(days=max(0, tage - k - 30))
        url = IOC + '?' + urllib.parse.urlencode(dict(query='data', code=code, timestart=a, timestop=b, format='json'))
        try:
            for r in json.load(urllib.request.urlopen(url, timeout=90)):
                if r.get('slevel') is not None:
                    t.append(datetime.strptime(r['stime'], '%Y-%m-%d %H:%M:%S')
                             .replace(tzinfo=timezone.utc).timestamp())
                    h.append(float(r['slevel']))
        except Exception:  # noqa: BLE001
            pass
    t, h = np.array(t), np.array(h)
    if len(t) < 24 * 14:
        return None
    o = np.argsort(t)
    t, h = t[o], h[o]
    m = np.abs(h - np.median(h)) < 5
    return t[m], h[m]


def gegen_messung(r, reihe):
    """RMS und Hubfaktor (Messung/Satz) eines Satzes gegen die Messreihe."""
    import numpy as np
    import xtide_modell as X
    pfad = os.path.join(ROOT, r['file'])
    namen, speeds, arg, fak = X.kopf_lesen(pfad)
    _z0, werte, einheit, mer = X.satz_lesen(pfad, r['name'])
    werte = {k: (a, X.greenwich(g, speeds[k], mer)) for k, (a, g) in werte.items() if k in speeds}
    t, h = reihe
    p = X.kurve(t, 0.0, werte, namen, speeds, arg, fak, 0.3048 if einheit.startswith('f') else 1.0)
    res = (h - h.mean()) - (p - p.mean())
    return float(np.sqrt(np.mean(res ** 2))), float(np.polyfit(p - p.mean(), h - h.mean(), 1)[0])


WADE = re.compile(r"[A-Za-z]+-[a-z]+|'|\b(Kang|Po-ti|Tao|Yu|Hsu)\b")


def namenhinweis(n):
    h = []
    teil = n.split(',')[0]
    if WADE.search(teil):
        h.append('Wade-Giles')
    if re.search(r'[a-z]dao\b', teil) and not re.search(r'Qingdao|Qinhuangdao|Huludao|Shidao', teil):
        h.append('dao angehaengt')
    return ';'.join(h)


def main(argv):
    region = argv[1] if len(argv) > 1 else 'Taiwan'
    mit_nom = '--ohne-nominatim' not in argv
    mit_ioc = '--ohne-ioc' not in argv
    alle = [r for r in load_records() if not r['current'] and r['lat'] is not None]
    rs = [r for r in alle if r['name'].endswith(region)]
    rs.sort(key=lambda r: (r['lat'], r['lon']))
    zeilen = []
    dubl = set()
    for r in rs:
        rg = rang(r)
        for n in rs:
            if n is r or (rang(n), n['file'], n['line']) >= (rg, r['file'], r['line']):
                continue
            d = km(r, n)
            if (rang(n) < rg and d <= DUP_KM) or (rang(n) == rg and d <= 0.5):
                dubl.add(id(r))
    for r in rs:
        rg = rang(r)
        besser = sorted(((km(r, n), n) for n in rs if n is not r and
                         (rang(n), n['file'], n['line']) < (rg, r['file'], r['line'])),
                        key=lambda t: t[0])
        # Gleichrangige Messstationen sind nur bei praktisch gleicher Position
        # Dubletten (Danhai/Tamsui liegen 2 km auseinander und sind zwei Pegel).
        dup = [(d, n) for d, n in besser
               if (rang(n) < rg and d <= DUP_KM) or (rang(n) == rg and d <= 0.5)]
        # Gleichrangige gleiche Position: der zweite (Dateiname) gilt als Dublette
        z = dict(satz=r['name'], datei=kurz(r['file']), rang=rg,
                 lat=r['lat'], lon=r['lon'], raster='ja' if auf_raster(r['lat'], r['lon']) else '',
                 m2='%.3f/%.0f' % (amp(r, 'M2'), phase(r, 'M2')),
                 s2m2='%.2f' % (amp(r, 'S2') / max(amp(r, 'M2'), 1e-3)),
                 k1='%.3f/%.0f' % (amp(r, 'K1'), phase(r, 'K1')),
                 o1='%.3f/%.0f' % (amp(r, 'O1'), phase(r, 'O1')),
                 p1q1='fehlt' if 'P1' not in r['amp'] and 'K1' in r['amp'] else '',
                 name_hinweis=namenhinweis(r['name']))
        befund, vorschlag = [], ''
        if dup:
            d, n = dup[0]
            a = amp(r, 'M2') / max(amp(n, 'M2'), 1e-3) - 1
            p = dphi(phase(r, 'M2'), phase(n, 'M2'))
            befund.append('Dublette zu %s [%s] %.1f km: M2 %+.0f %%, %+.0f Grad'
                          % (n['name'], kurz(n['file']), d, 100 * a, p))
            vorschlag = 'archivieren (nach Rang)'
            # Handarbeit nicht verlieren: weicht der zu archivierende Satz in Name
            # oder Position vom behaltenen ab, wird das als Uebernahme vorgeschlagen.
            if km(r, n) > 0.05:
                befund.append('UEBERNEHMEN? Position %.4f/%.4f statt %.4f/%.4f' % (r['lat'], r['lon'], n['lat'], n['lon']))
            if r['name'] != n['name']:
                befund.append('UEBERNEHMEN? Name "%s" statt "%s"' % (r['name'], n['name']))
            if 'P1' in r['amp'] and 'P1' not in n['amp']:
                befund.append('behaltener Satz ohne P1/Q1 -> inferieren')
            # Schiedsrichter: zwei Saetze aus Messung/Analyse und ein IOC-Pegel daneben
            code = ioc_station(n['lat'], n['lon']) if mit_ioc and rg <= 3 else None
            reihe = ioc_reihe(code) if code else None
            if reihe is not None:
                ra, fa = gegen_messung(r, reihe)
                rb, fb = gegen_messung(n, reihe)
                befund.append('IOC %s %d h: dieser RMS %.3f m Hub %.2f, %s RMS %.3f m Hub %.2f'
                              % (code, len(reihe[0]), ra, fa, kurz(n['file']), rb, fb))
                vorschlag = ('archivieren (Messung bestaetigt)' if rb <= ra
                             else 'TAUSCHEN: besser als %s (Messung)' % kurz(n['file']))
        else:
            ref = [(d, n) for d, n in besser
                   if d <= NACHBAR_KM and rang(n) <= 3 and id(n) not in dubl][:2]
            if rg >= 4 and ref:
                iz = interpol(ref, r)
                ia = {c: abs(iz[c]) for c in iz}
                ip = {c: (-math.degrees(cmath.phase(iz[c]))) % 360 for c in iz}
                fm2 = amp(r, 'M2') / ia['M2'] - 1
                pm2 = dphi(phase(r, 'M2'), ip['M2'])
                fs2 = (amp(r, 'S2') / amp(r, 'M2')) / (ia['S2'] / ia['M2']) - 1
                fk1 = amp(r, 'K1') / ia['K1'] - 1
                fo1 = amp(r, 'O1') / ia['O1'] - 1
                pk1 = dphi(phase(r, 'K1'), ip['K1'])
                nb = ', '.join('%s %.0f km' % (n['name'].split(',')[0], d) for d, n in ref)
                befund.append('gegen %s: M2 %+.0f %% %+.0f Grad, S2/M2 %+.0f %%, K1 %+.0f %% %+.0f Grad, O1 %+.0f %%'
                              % (nb, 100 * fm2, pm2, 100 * fs2, 100 * fk1, pk1, 100 * fo1))
                zeit = abs(pm2) > 20 or abs(pk1) > 25
                m2hub = abs(fm2) > 0.25
                hub = abs(fs2) > 0.25 or abs(fk1) > 0.3 or abs(fo1) > 0.3
                vorschlag = ('Zeit pruefen' if zeit else 'M2-Hub pruefen' if m2hub
                             else 'Hube korrigieren' if hub else 'behalten')
            else:
                vorschlag = 'behalten' if rg <= 3 else 'behalten (kein Nachbar)'
        if z['p1q1'] and vorschlag.startswith(('behalten', 'Hube')):
            vorschlag += ' + P1/Q1'
        if mit_nom and not vorschlag.startswith(('archivieren', 'TAUSCHEN')):
            art, txt = nominatim(r['lat'], r['lon'])
            z['lage'] = art
            z['lage_detail'] = txt
        z['befund'] = ' | '.join(befund)
        z['vorschlag'] = vorschlag
        zeilen.append(z)
        print('%-48s %-22s %-28s %s' % (r['name'][:48], z['datei'][:22], vorschlag,
                                       z.get('lage', '')), flush=True)
    aus = os.path.join(ROOT, 'harmonics/help/region_%s_%s.csv'
                       % (re.sub(r'\W+', '_', region.lower()), date.today().strftime('%Y%m%d')))
    felder = ['satz', 'datei', 'rang', 'lat', 'lon', 'raster', 'lage', 'lage_detail', 'm2', 's2m2',
              'k1', 'o1', 'p1q1', 'name_hinweis', 'befund', 'vorschlag']
    with open(aus, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=felder, extrasaction='ignore')
        w.writeheader()
        w.writerows(zeilen)
    print('\n%d Saetze, Tabelle: %s' % (len(zeilen), os.path.relpath(aus, ROOT)))


if __name__ == '__main__':
    main(sys.argv)
