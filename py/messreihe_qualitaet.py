#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Misst Saetze gegen die Pegelreihen, die schon im Haus liegen.

Die Guetepruefung gab es bisher nur je Quelle -- chs_qualitaet gegen die
kanadischen Tafeln, bom_qualitaet gegen die australischen, dazu SHN,
SHOA, SEMAR, CICESE, DHN, Hidronav, CPA. Zusammen decken sie rund 300
der 1119 Dublettengruppen ab. Fuer den Rest fehlte der Massstab, und
ohne Massstab wurde zuletzt nach Herkunft entschieden -- eine
Abkuerzung, die der Bestand nicht haben soll.

Der Massstab liegt aber da: in water_levels/ stehen 43 GB Pegelreihen,
darunter genau die grossen Loecher -- JMA_Japan mit 239 Stationen ueber
fuenfzehn Jahre, Norway_Kartverket, India_IOC, Portugal_IOC, die
UHSLC-Reihen fuer Bangladesch, Myanmar und Mosambik.

Zugeordnet wird ueber station_id_context: die Saetze, die wir selbst
aus einer Reihe gefittet haben, nennen deren Kennung ("JMA AS",
"UHSLC-878", "IOC-oran"), und damit ist auch die Position bekannt. Um
diesen Anker herum werden alle Saetze im Umkreis gegen dieselbe Reihe
gerechnet.

Zwei Dinge, ohne die die Zahl nichts wert waere:

  Der Satz, der AUS dieser Reihe stammt, ist gegen sie kein
  unabhaengiger Kandidat -- er hat auf ihr trainiert. Die Spalte
  "eigen" markiert ihn; ein Vergleich, in dem er gewinnt, beweist
  nichts. Wo die Reihe ueber sein Fitfenster hinausreicht, wird
  ausserhalb gemessen, und die Spalte "ausserhalb" sagt es.

  Die Reihe ist gemessen, nicht vorhergesagt: Wind und Luftdruck
  stehen mit drin. Der RMS liegt deshalb hoeher als gegen eine Tafel,
  meist um zehn bis zwanzig Zentimeter Sturmanteil. Fuer den Vergleich
  ZWEIER Saetze an derselben Reihe macht das nichts -- der Sturm ist
  fuer beide derselbe und faellt in der Differenz heraus. Absolut mit
  den Tafelwerten vergleichbar sind diese Zahlen aber nicht.

Usage: python3 py/messreihe_qualitaet.py [--km 3] [--tage 365]
                                         [--ordner JMA_Japan]
                                         > harmonics/help/messreihe_qualitaet.csv
"""
from __future__ import annotations

import collections
import csv
import datetime as dt
import glob
import json
import math
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, km, active_files, ROOT, MERIDIAN   # noqa: E402

TCD = '/usr/share/xtide'
REIHEN = os.path.join(ROOT, 'water_levels')
SCHRITT_MIN = 10             # Aufloesung der Vorhersage
SUCHE_MIN = 720              # Zeitversatz wird in diesem Rahmen gesucht
MIND_PUNKTE = 2000


def kopfdaten():
    """-> {(datei, zeile): (station_id_context, fitzeitraum, quelle)}."""
    out = {}
    for path in active_files():
        lines = open(os.path.join(ROOT, path), encoding='iso-8859-1').read().split('\n')
        sid = zeit = quelle = None
        for k, line in enumerate(lines):
            if line.startswith('# station_id_context:'):
                sid = line.split(':', 1)[1].strip()
            elif line.startswith('# source:'):
                quelle = line.split(':', 1)[1].strip()
            elif line.startswith('# utide:'):
                m = re.search(r'period=(\d{4}-\d\d-\d\d)\.\.(\d{4}-\d\d-\d\d)', line)
                if m:
                    zeit = (m.group(1), m.group(2))
            elif (line and not line.startswith('#') and k + 1 < len(lines)
                  and MERIDIAN.match(lines[k + 1])):
                out[(path, k + 1)] = (sid, zeit, quelle or '')
                sid = zeit = quelle = None
    return out


def reihendateien(nur=None):
    """-> {(anbieter, kennung): pfad} fuer alles, was wir lesen koennen."""
    out = {}
    for pfad in glob.glob(os.path.join(REIHEN, '**', '*'), recursive=True):
        if not os.path.isfile(pfad) or os.path.splitext(pfad)[1] not in ('.csv', '.txt'):
            continue
        rel = os.path.relpath(pfad, REIHEN)
        ordner = rel.split(os.sep)[0]
        if nur and nur != ordner:
            continue
        stamm = os.path.splitext(os.path.basename(pfad))[0]
        teile = [t for t in re.split(r'[_\-. ]', stamm) if t]
        for anbieter in re.split(r'[_\-]', ordner):
            for t in teile:
                out.setdefault((anbieter.upper(), t.upper()), pfad)
        # JMA legt die Kennung allein in den Dateinamen (A0.txt).
        out.setdefault((ordner.upper(), stamm.upper()), pfad)
    return out


def lies(pfad):
    """-> [(unixzeit, hoehe_m)], grob von Ausreissern befreit."""
    return _sauber(_lies(pfad))


def _sauber(reihe, spanne=20.0, mindest_m=3.0):
    """Wirft heraus, was weit ausserhalb der Streuung liegt.

    Die irischen Rohreihen enthalten Spitzen von dreissig Metern --
    Sensorfehler, die den RMS einer ganzen Station unbrauchbar machen.
    Gemessen wird an der mittleren absoluten Abweichung vom Median, die
    ein einzelner Ausreisser nicht verschiebt.
    """
    if len(reihe) < 100:
        return reihe
    werte = sorted(h for _t, h in reihe)
    med = werte[len(werte) // 2]
    mad = sorted(abs(h - med) for h in werte)[len(werte) // 2] or 0.01
    grenze = max(mindest_m, spanne * mad)
    return [(t, h) for t, h in reihe if abs(h - med) <= grenze]


def _lies(pfad):
    if os.path.basename(os.path.dirname(pfad)).upper().startswith('JMA'):
        return _lies_jma(pfad)
    if 'bodc' in pfad:
        return _lies_bodc(pfad)
    if pfad.endswith('.npz'):
        return _lies_npz(pfad)
    return _lies_csv(pfad)


def _lies_npz(pfad):
    """Die irischen Reihen liegen als numpy-Archiv mit allem drin."""
    import numpy as np
    d = np.load(pfad, allow_pickle=True)
    t = d['datetimes_utc'].astype('datetime64[s]').astype('int64')
    # Die irischen Reihen fuehren Meter, die deutschen Zentimeter.
    if 'levels_m' in d:
        h = d['levels_m'].astype(float)
    elif 'levels_cm' in d:
        h = d['levels_cm'].astype(float) / 100.0
    else:
        return []
    gut = np.isfinite(h)
    return sorted(zip(t[gut].tolist(), h[gut].tolist()))


BODC_ZEILE = re.compile(r'^\s*\d+\)\s+(\d{4})/(\d\d)/(\d\d)\s+(\d\d):(\d\d):(\d\d)'
                        r'\s+(-?[\d.]+)([A-Z]?)\s+(-?[\d.]+)([A-Z]?)')


def bodc_kopf(pfad):
    """-> (Site, lat, lon) aus dem Kopf einer BODC-Datei."""
    site = lat = lon = None
    with open(pfad, encoding='iso-8859-1', errors='replace') as fh:
        for _ in range(12):
            z = fh.readline()
            if z.startswith('Site:'):
                site = z.split(':', 1)[1].strip()
            elif z.startswith('Latitude:'):
                lat = float(z.split(':', 1)[1])
            elif z.startswith('Longitude:'):
                lon = float(z.split(':', 1)[1])
    return site, lat, lon


def _lies_bodc(pfad):
    """BODC-Pegelreihe. Gibt den GEZEITENANTEIL zurueck: Wert minus Residuum.

    Die Dateien fuehren neben dem Messwert das Residuum mit, also den
    nicht-astronomischen Anteil. Zieht man es ab, bleibt die Tide ohne
    Wind und Luftdruck -- damit misst diese Reihe wie eine Tafel und
    nicht wie eine Messung, der Sturmboden von zehn bis zwanzig
    Zentimetern faellt weg.

    Verworfen werden nur Zeilen mit dem Kennbuchstaben N (Luecke) und
    Werte unter -90.
    """
    out = []
    for zeile in open(pfad, encoding='iso-8859-1', errors='replace'):
        m = BODC_ZEILE.match(zeile)
        if not m:
            continue
        # Nur 'N' heisst fehlend ("gaps are filled in with null values,
        # marked with an 'N' flag"); 'M' steht an fast der Haelfte aller
        # Zeilen und markiert keine Luecke, sondern eine Nachbearbeitung.
        if 'N' in (m.group(8), m.group(10)):
            continue
        wert, rest = float(m.group(7)), float(m.group(9))
        if wert < -90 or rest < -90:
            continue
        t = dt.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                        int(m.group(4)), int(m.group(5)), int(m.group(6)),
                        tzinfo=dt.timezone.utc).timestamp()
        out.append((t, wert - rest))
    out.sort()
    return out


def _lies_csv(pfad):
    with open(pfad, encoding='utf-8', errors='replace') as fh:
        kopf = fh.readline().strip().split(',')
        kl = [c.strip().lower() for c in kopf]
        zi = next((i for i, c in enumerate(kl) if 'time' in c or 'date' in c), None)
        wi = next((i for i, c in enumerate(kl)
                   if 'level' in c or 'water' in c or 'height' in c or 'sea' in c), None)
        if zi is None or wi is None:
            return []
        # Manche UHSLC-Dateien setzen eine zweite Kopfzeile mit den
        # Einheiten darunter ("UTC,millimeters,"). Ohne sie werden
        # Millimeter als Meter gelesen, und der RMS kommt in
        # Hunderten von Metern heraus statt in Zentimetern.
        merker = fh.tell()
        zweite = fh.readline().split(',')
        einheit = kl[wi]
        if len(zweite) > wi:
            try:
                float(zweite[wi])
                fh.seek(merker)
            except ValueError:
                einheit = zweite[wi].strip().lower() or einheit
        faktor = 0.001 if einheit.startswith('milli') or einheit == 'mm' else (
            0.01 if 'cm' in einheit or einheit.startswith('centi') else 1.0)
        out = []
        for zeile in fh:
            f = zeile.rstrip('\n').split(',')
            if len(f) <= max(zi, wi):
                continue
            try:
                wert = float(f[wi]) * faktor
                # Die UHSLC-Reihen schreiben Luecken als "nan" -- float()
                # nimmt das an, und ein einziger davon macht den ganzen
                # RMS zu nan.
                if not math.isfinite(wert):
                    continue
                out.append((_zeit(f[zi]), wert))
            except (ValueError, TypeError):
                continue
    out.sort()
    return out


def _zeit(s):
    s = s.strip().replace('T', ' ').replace('Z', '')
    if '+' in s[10:]:
        s = s[:10] + s[10:].split('+')[0]
    s = s.strip()
    for muster in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d %H:%M:%S.%f'):
        try:
            return dt.datetime.strptime(s, muster).replace(tzinfo=dt.timezone.utc).timestamp()
        except ValueError:
            pass
    raise ValueError(s)


def _lies_jma(pfad):
    """JMA-Festbreite: 24 Stundenwerte in cm, dann JJMMTT und Stationskuerzel.

    9999 heisst fehlend. Die Zeiten stehen in japanischer Ortszeit
    (UTC+9); gerechnet wird durchweg in UTC.
    """
    out = []
    for zeile in open(pfad, encoding='iso-8859-1', errors='replace'):
        if len(zeile) < 78:
            continue
        try:
            werte = [int(zeile[3 * i:3 * i + 3]) for i in range(24)]
            jj, mm, tt = int(zeile[72:74]), int(zeile[74:76]), int(zeile[76:78])
        except ValueError:
            continue
        jahr = 2000 + jj if jj < 70 else 1900 + jj
        try:
            tag = dt.datetime(jahr, mm, tt, tzinfo=dt.timezone.utc)
        except ValueError:
            continue
        for stunde, w in enumerate(werte):
            if w >= 999:
                continue
            out.append((tag.timestamp() + (stunde - 9) * 3600, w / 100.0))
    out.sort()
    return out


def vorhersage(tcd, name, von, bis, schritt=SCHRITT_MIN):
    """-> (numpy-Zeiten, numpy-Hoehen) aus XTide im Rohmodus."""
    import numpy as np
    out = subprocess.run(
        ['tide', '-l', name, '-b', von, '-e', bis, '-m', 'r',
         '-s', f'{schritt // 60:02d}:{schritt % 60:02d}', '-u', 'm', '-z'],
        env=dict(os.environ, HFILE_PATH=os.path.join(TCD, tcd)),
        capture_output=True, encoding='iso-8859-1', errors='replace').stdout
    t, h = [], []
    for zeile in out.split('\n'):
        f = zeile.split()
        if len(f) == 2:
            try:
                t.append(float(f[0]))
                h.append(float(f[1]))
            except ValueError:
                pass
    return np.array(t), np.array(h)


def messe(obs_t, obs_h, vt, vh):
    """-> (n, rms, max, zeitversatz_min, hoehenversatz, hub) oder None."""
    import numpy as np
    if len(vt) < 100 or len(obs_t) < MIND_PUNKTE:
        return None
    schritt = vt[1] - vt[0]
    best = None
    for versatz in range(-SUCHE_MIN, SUCHE_MIN + 1, SCHRITT_MIN):
        i = np.round((obs_t + versatz * 60 - vt[0]) / schritt).astype(int)
        gut = (i >= 0) & (i < len(vh))
        if gut.sum() < MIND_PUNKTE:
            continue
        d = obs_h[gut] - vh[i[gut]]
        rms = float(np.sqrt(np.mean((d - d.mean()) ** 2)))
        if best is None or rms < best[0]:
            best = (rms, versatz, gut, d)
    if best is None:
        return None
    rms, versatz, gut, d = best
    return (int(gut.sum()), rms, float(np.max(np.abs(d - d.mean()))),
            versatz, float(d.mean()), float(vh.max() - vh.min()))


def bodc_reihen(nur=None):
    """BODC-Jahresdateien: sie bringen Name und Position selbst mit."""
    ordner = glob.glob(os.path.join(REIHEN, 'UK', 'bodc*', ''))
    if nur and nur != 'UK':
        return []
    neueste = {}
    for verzeichnis in ordner:
        for name in os.listdir(verzeichnis):
            m = re.match(r'^(\d{4})([A-Z]{3})\.txt$', name)
            if m and int(m.group(1)) >= neueste.get(m.group(2), (0, ''))[0]:
                neueste[m.group(2)] = (int(m.group(1)), os.path.join(verzeichnis, name))
    out = []
    for _code, (_jahr, pfad) in sorted(neueste.items()):
        site, lat, lon = bodc_kopf(pfad)
        if lat is None or lon is None:
            continue
        out.append((dict(lat=lat, lon=lon, name=site or os.path.basename(pfad),
                         file='(BODC)', line=0), pfad, None, 'BODC'))
    return out


def beiblatt_reihen(nur=None):
    """Reihen, die ein stationen.json neben sich haben.

    Der Hauptweg ist satzgetrieben: eine Reihe wird nur gelesen, wenn
    ein Satz sie in station_id_context nennt. Damit lagen 2694 von 4659
    Dateien brach -- allein die kanadischen Provinzordner fuehren 1007
    Reihen, von denen zehn ankamen. Wo ein Beiblatt Position und Name
    liefert, geht es auch ohne Namensnennung: gesucht wird dann wie bei
    den npz-Reihen ueber die Lage.
    """
    out = []
    for pfad in sorted(glob.glob(os.path.join(REIHEN, '*', 'stationen.json'))):
        ordner = os.path.relpath(pfad, REIHEN).split(os.sep)[0]
        if nur and nur != ordner:
            continue
        try:
            eintraege = json.load(open(pfad, encoding='utf-8'))
        except Exception:
            continue
        for datei, e in sorted(eintraege.items()):
            voll = os.path.join(REIHEN, ordner, datei)
            if not os.path.exists(voll):
                continue
            out.append((dict(lat=float(e['lat']), lon=float(e['lon']),
                             name=e.get('name', datei), file=f'({ordner})', line=0),
                        voll, None, ordner))
    return out


def npz_reihen(nur=None):
    """Reihen im numpy-Format.

    Die meisten bringen Name und Position selbst mit. Die deutschen
    PEGELONLINE-Reihen nicht: sie enthalten nur datetimes_utc und
    levels_cm, und damit fielen alle 99 aus jeder Guetepruefung heraus --
    genau der Bestand, in dem die TICON-Saetze 38 Minuten zu spaet
    liegen. Fuer solche Ordner liegt die Zuordnung als
    npz_stationen.json daneben, einmal von Hand geprueft, statt bei
    jedem Lauf neu geraten.
    """
    import numpy as np
    out = []
    beiblatt = {}
    for pfad in glob.glob(os.path.join(REIHEN, '*', 'npz_stationen.json')):
        ordner = os.path.relpath(pfad, REIHEN).split(os.sep)[0]
        try:
            beiblatt[ordner] = json.load(open(pfad, encoding='utf-8'))
        except Exception:
            pass
    for pfad in sorted(glob.glob(os.path.join(REIHEN, '**', '*.npz'), recursive=True)):
        ordner = os.path.relpath(pfad, REIHEN).split(os.sep)[0]
        if nur and nur != ordner:
            continue
        try:
            d = np.load(pfad, allow_pickle=True)
            lat, lon = float(d['latitude']), float(d['longitude'])
            name = str(d['name'])
        except Exception:
            e = beiblatt.get(ordner, {}).get(os.path.basename(pfad)[:-4])
            if not e:
                continue
            lat, lon, name = float(e['lat']), float(e['lon']), e['name']
        out.append((dict(lat=lat, lon=lon, name=name, file=f'({ordner})', line=0),
                    pfad, None, 'Marine Institute' if 'Ireland' in ordner else ordner))
    return out


def main(argv):
    import numpy as np
    umkreis = float(argv[argv.index('--km') + 1]) if '--km' in argv else 3.0
    tage = int(argv[argv.index('--tage') + 1]) if '--tage' in argv else 365
    nur = argv[argv.index('--ordner') + 1] if '--ordner' in argv else None

    kopf = kopfdaten()
    dateien = reihendateien(nur)
    recs = [r for r in load_records()
            if r['lat'] is not None and r['lon'] is not None and not r['current']]
    anker = []
    for r in recs:
        sid, fit, _q = kopf.get((r['file'], r['line']), (None, None, ''))
        if not sid:
            continue
        teile = [t for t in re.split(r'[ \-_]', sid) if t]
        pfad = None
        for i in range(len(teile)):
            for j in range(len(teile)):
                if i == j:
                    continue
                pfad = pfad or dateien.get((teile[i].upper(), teile[j].upper()))
        if pfad:
            anker.append((r, pfad, fit, None))
    anker += bodc_reihen(nur)
    anker += npz_reihen(nur)
    anker += beiblatt_reihen(nur)
    print(f'{len(anker)} Reihen zugeordnet, Umkreis {umkreis:.0f} km, '
          f'{tage} Tage Fenster', file=sys.stderr)

    w = csv.writer(sys.stdout)
    w.writerow(['station', 'lat', 'lon', 'jahr', 'satz', 'datei', 'abstand_m', 'n',
                'rms_m', 'max_m', 'zeit_min', 'hoehe_off_m', 'hub_m', 'reihe',
                'eigen', 'ausserhalb'])
    for nr, (a, pfad, fit, anbieter) in enumerate(anker, 1):
        obs = lies(pfad)
        if len(obs) < MIND_PUNKTE:
            print(f'  {os.path.basename(pfad)}: nur {len(obs)} Werte', file=sys.stderr)
            continue
        ende = obs[-1][0]
        start = ende - tage * 86400
        ausserhalb = 'nein'
        if fit:
            fit_von = dt.datetime.strptime(fit[0], '%Y-%m-%d').replace(
                tzinfo=dt.timezone.utc).timestamp()
            fit_bis = dt.datetime.strptime(fit[1], '%Y-%m-%d').replace(
                tzinfo=dt.timezone.utc).timestamp()
            if start > fit_bis or ende < fit_von:
                # Die Reihe liegt schon ganz ausserhalb -- etwa die
                # JMA-Tafel fuer 2026 gegen einen Fit bis 2025.
                ausserhalb = 'ja'
            elif obs[0][0] < fit_von - tage * 86400:
                # Sonst nach vorn ausweichen: vor dem Fitfenster ist die
                # Reihe fuer alle Kandidaten gleich neu.
                ende, start, ausserhalb = fit_von, fit_von - tage * 86400, 'ja'
        paare = [(t, h) for t, h in obs if start <= t <= ende]
        if len(paare) < MIND_PUNKTE:
            continue
        obs_t = np.array([p[0] for p in paare])
        obs_h = np.array([p[1] for p in paare])
        von = dt.datetime.fromtimestamp(start - 7200, dt.timezone.utc).strftime('%Y-%m-%d %H:%M')
        bis = dt.datetime.fromtimestamp(ende + 7200, dt.timezone.utc).strftime('%Y-%m-%d %H:%M')
        for x in sorted(recs, key=lambda q: km(a, q)):
            d = km(a, x)
            if d > umkreis:
                break
            tcd = os.path.basename(x['file'])[:-4] + '.tcd'
            if not os.path.exists(os.path.join(TCD, tcd)):
                continue
            vt, vh = vorhersage(tcd, x['name'], von, bis)
            g = messe(obs_t, obs_h, vt, vh)
            if not g:
                continue
            n, rms, gross, versatz, off, hub = g
            # "eigen" heisst: dieser Satz stammt aus eben dieser Quelle.
            # Bei den Ankern ueber station_id_context ist es derselbe
            # Satz, bei den BODC-Reihen erkennt man es am Quellenvermerk.
            eigen = 1 if x is a else 0
            if anbieter and anbieter.lower() in kopf.get(
                    (x['file'], x['line']), ('', None, ''))[2].lower():
                eigen = 1
            w.writerow([os.path.basename(pfad), f'{a["lat"]:.4f}', f'{a["lon"]:.4f}',
                        dt.datetime.fromtimestamp(ende, dt.timezone.utc).year,
                        x['name'], os.path.basename(x['file']), round(d * 1000), n,
                        round(rms, 4), round(gross, 3), versatz, round(off, 3),
                        round(hub, 3), os.path.relpath(pfad, REIHEN).split(os.sep)[0],
                        eigen, ausserhalb])
            sys.stdout.flush()
        if nr % 20 == 0:
            print(f'  {nr}/{len(anker)}', file=sys.stderr, flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
