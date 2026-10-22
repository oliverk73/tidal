#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pegelreihen des Department of Transport Western Australia (DoT) einlesen.

Oliver 22.10.2026: nach Queensland (py/qld_msq_fit.py) die anderen Bundeslaender -> WA hat als einziges ein freies
Massenarchiv: oeffentlicher S3-Ordner s3-ap-southeast-2.amazonaws.com/transport.wa/Tide_Packet/<STATION>_Tides.zip
(Liste water_levels/Australia_WA/dot_zip/liste.txt). Je Zip Unterordner <STATION>_<Einsatz>/ mit Jahresdateien:
Kopf (#Location, #Lat/Long, #Time Zone, #Vertical Datum, #Unit, #Sampling Rate) und Saetze "Hoehe,JJJJMMTT.hhmm/".

Zeit: AWST (UTC+8) laut Kopf -> UTC. Einheit cm (laut Kopf) -> m. -9999 = Fehlwert. Ein Einsatz (_01, _02 ...) ist
eine eigene Reihe, weil Position, Sensor und Bezugshoehe wechseln koennen; Metadaten aus der juengsten Jahresdatei.
Zips werden nicht entpackt (zipfile liest direkt).

Usage: python3 py/wa_dot_einlesen.py -> water_levels/Australia_WA/dot/<EINSATZ>.csv (time_utc, waterlevel_m)
                                        + water_levels/Australia_WA/dot/einsaetze.csv
"""
import csv
import datetime as dt
import glob
import os
import re
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUELLE = os.path.join(ROOT, 'water_levels/Australia_WA/dot_zip')
ZIEL = os.path.join(ROOT, 'water_levels/Australia_WA/dot')
SATZ = re.compile(r'(-?\d+(?:\.\d+)?),(\d{8})\.(\d{4})')


def kopf(text):
    k = {}
    for z in text.split('\n')[:30]:
        if not z.startswith('#'):
            continue
        z = z[1:].strip()
        m = re.search(r'Lat:\s*(-?[\d.]+)\s+Long:\s*(-?[\d.]+)', z, re.I)
        if m:
            k['lat'], k['lon'] = float(m.group(1)), float(m.group(2))
        for feld, muster in (('ort', r'^LOCATION:\s*(.*)'), ('status', r'^Station Status:\s*(.*)'),
                             ('datum', r'^Vertical Datum:\s*(.*)'), ('zone', r'^Time Zone:\s*(.*)'),
                             ('ansi', r'^National Station ID:\s*(.*)')):
            m = re.search(muster, z, re.I)
            if m:
                k[feld] = re.sub(r'\s+', ' ', m.group(1)).strip()
        m = re.search(r'Unit of Height Observations:\s*(\w+)', z, re.I)
        if m:
            k['einheit'] = m.group(1).lower()
        m = re.search(r'Sampling Rate \(min\):\s*([\d.]+)', z, re.I)
        if m:
            k['takt'] = float(m.group(1))
    return k


def versatz(zone):
    m = re.search(r'UTC\s*([+-])\s*(\d+):(\d+)', zone or '')
    if m:
        return (1 if m.group(1) == '+' else -1) * (int(m.group(2)) + int(m.group(3)) / 60)
    if 'western' not in (zone or '').lower():
        print('   Zeitzone fehlt/unbekannt (%r) -> AWST laut DoT-Katalog' % zone)
    return 8.0


def main():
    os.makedirs(ZIEL, exist_ok=True)
    meta = []
    for zpfad in sorted(glob.glob(os.path.join(QUELLE, '*.zip'))):
        try:
            Z = zipfile.ZipFile(zpfad)
        except zipfile.BadZipFile:
            print('%s: kaputt' % os.path.basename(zpfad))
            continue
        einsaetze = {}
        for n in Z.namelist():
            if n.lower().endswith('.txt'):
                e = os.path.basename(os.path.dirname(n)) or re.sub(r'_\d{4}\w?\.txt$', '', os.path.basename(n))
                einsaetze.setdefault(e, []).append(n)
        for e, dateien in sorted(einsaetze.items()):
            werte, k, fehler = {}, {}, 0
            for n in sorted(dateien):
                try:
                    text = Z.read(n).decode('latin-1')
                except zipfile.BadZipFile as x:                     # AEEMU01_01_2018: CRC-Fehler schon im DoT-Paket
                    print('   %s: %s' % (n, x))
                    continue
                if 'readme' in n.lower() or 'WATER LEVEL' not in text[:400].upper():
                    print('   %s: %s' % (n, re.sub(r'\s+', ' ', text)[:200]))   # Hinweise wie "synthesised" (EXEXM01_02)
                    continue
                kk = kopf(text)
                k.update(kk)                                        # juengste Datei gewinnt
                h = versatz(kk.get('zone', k.get('zone')))
                faktor = {'cm': 0.01, 'mm': 0.001, 'm': 1.0}[kk.get('einheit', k.get('einheit', 'cm'))]
                for v, d, t in SATZ.findall(text.split('H(cm)', 1)[-1] if 'H(cm)' in text else text):
                    if float(v) <= -9990:
                        continue
                    try:
                        zeit = dt.datetime.strptime(d + t, '%Y%m%d%H%M') - dt.timedelta(hours=h)
                    except ValueError:
                        fehler += 1
                        continue
                    werte[zeit] = float(v) * faktor
            if not werte:
                continue
            with open(os.path.join(ZIEL, e + '.csv'), 'w', newline='') as f:
                w = csv.writer(f)
                w.writerow(['time_utc', 'waterlevel_m'])
                for t in sorted(werte):
                    w.writerow([t.strftime('%Y-%m-%d %H:%M'), '%.3f' % werte[t]])
            von, bis = min(werte), max(werte)
            tage = (bis - von).days + 1
            meta.append(dict(einsatz=e, ort=k.get('ort', ''), lat=k.get('lat', ''), lon=k.get('lon', ''), status=k.get('status', ''),
                             datum=k.get('datum', ''), takt=k.get('takt', ''), von=von.date(), bis=bis.date(), tage=tage,
                             werte=len(werte), abdeckung='%.2f' % (len(werte) * k.get('takt', 60) / 1440 / tage), ansi=k.get('ansi', '')))
            print('%-12s %-38s %s..%s %6d d  %s' % (e, k.get('ort', '')[:38], von.date(), bis.date(), tage, k.get('datum', '')[:40]))
    with open(os.path.join(ZIEL, 'einsaetze.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(meta[0]))
        w.writeheader()
        w.writerows(meta)


if __name__ == '__main__':
    main()
