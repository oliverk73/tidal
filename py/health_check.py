#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gesundheitscheck ueber alle aktiven Harmonics-Dateien.

Prueft fuenf Dinge und meldet nur, was nicht in harmonics/help/geprueft.csv
als erklaert abgehakt ist:

  L  Sperrliste    hat sich eine Position oder ein Name gegen
                   positions_locked.csv veraendert?
  E  Bestand       ist ein gesperrter Datensatz verschwunden oder
                   doppelt vorhanden? (oft gewollt, nie stillschweigend)
  S  Struktur      fehlende Position, abweichende Slotzahl
  A  Nachbarn      unter 3 km, aber Kurven weichen stark ab
  B  Namensgleich  gleicher Name, gleiche Kurve, weit auseinander
                   -> mindestens eine Position ist falsch
  M  Konstituenten eine Nebenkonstituente ueberragt die Hauptkonstituenten

Ausnahmen werden ueber den Fingerabdruck des Konstituentenblocks
geschluesselt, ueberleben also Umbenennungen und Positionskorrekturen.

Usage: python3 py/health_check.py [--all] [--csv <verzeichnis>]
       --all  auch die abgehakten Faelle zeigen
"""
from __future__ import annotations

import cmath
import collections
import csv
import hashlib
import math
import os
import re
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCK = os.path.join(ROOT, 'harmonics/help/positions_locked.csv')
DONE = os.path.join(ROOT, 'harmonics/help/geprueft.csv')

SPEED = {'M2': 28.984104, 'S2': 30.0, 'K1': 15.041069,
         'O1': 13.943035, 'N2': 28.439730}
MAIN = list(SPEED)
MAJOR = {'M2', 'S2', 'N2', 'K2', 'K1', 'O1', 'P1', 'Q1',
         'M4', 'M6', 'MS4', 'MN4', 'SA', 'SSA', 'MM', 'MF', 'MSF'}
MERIDIAN = re.compile(r'^[+-]\d\d:\d\d')

NEAR_KM = 3.0        # Kanal A: als benachbart geltender Abstand
NEAR_TOL = 0.30      # Kanal A: relative Abweichung, ab der es ein Widerspruch ist
FAR_KM = 25.0        # Kanal B: ab hier gelten gleiche Namen als zu weit auseinander
FAR_TOL = 0.10       # Kanal B: bis hier gelten die Kurven als gleich
MINOR_FACTOR = 1.2   # Kanal M: ab diesem Vielfachen gilt eine Nebenkonstituente als dominant


def active_files():
    out = []
    for dirpath, _dirs, names in os.walk(os.path.join(ROOT, 'harmonics')):
        rel = os.path.relpath(dirpath, ROOT)
        if any(p in rel for p in ('backup', 'classic_original', 'template',
                                  'help', 'binary')):
            continue
        out += [os.path.relpath(os.path.join(dirpath, n), ROOT)
                for n in sorted(names) if n.endswith('.txt')]
    return sorted(out)


def namekey(s):
    s = unicodedata.normalize('NFKD', s.split(',')[0]).encode('ascii', 'ignore').decode().lower()
    # Klammerzusaetze weglassen -- aber nur solche ohne Ziffern. Sonst fallen
    # "Fundy (Offshore 1)" und "(Offshore 23)" auf denselben Schluessel.
    s = re.sub(r'\((?![^)]*\d)[^)]*\)', '', s)
    s = re.sub(r'\b(harbour|harbor|port|puerto|pier|jetty|island|isla|ile|ko|koh'
               r'|pulau|point|bay|roads|entrance|lighthouse|st|saint)\b', '', s)
    return re.sub(r'[^a-z0-9]', '', s)


def name_tokens(s):
    """Wortmenge des Namens ohne das Land -- zweite Sicherung fuer Kanal B.

    namekey() reduziert auf das Feld vor dem ersten Komma; bei Namen wie
    "Padre Island, Port Mansfield Channel, Texas" steht dort aber nicht die
    Provinz, sondern der unterscheidende Teil. Ohne diese Pruefung gelten
    zwei verschiedene Pegel als derselbe.
    """
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()
    parts = [p.strip() for p in s.split(',')]
    if len(parts) > 1:
        parts = parts[:-1]
    return {t for t in re.split(r'[^a-z0-9]+', ' '.join(parts)) if len(t) > 1}


def load_records():
    recs = []
    for path in active_files():
        lines = open(os.path.join(ROOT, path), encoding='iso-8859-1').read().split('\n')
        lat = lon = units = None
        for k, line in enumerate(lines):
            if line.startswith('# !latitude:'):
                lat = _num(line)
            elif line.startswith('# !longitude:'):
                lon = _num(line)
            elif line.startswith('# !units:'):
                units = line.split(':', 1)[1].strip()
            elif (line and not line.startswith('#') and k + 1 < len(lines)
                  and MERIDIAN.match(lines[k + 1])):
                mer = lines[k + 1].split()[0]
                hours = int(mer[1:3]) + int(mer[4:6]) / 60.0
                if mer[0] == '-':
                    hours = -hours
                amp, rows, j, c = {}, [], k + 3, 0
                while j < len(lines) and c < 175:
                    p = lines[j].split()
                    if not p or p[0].startswith('#'):
                        break
                    if p[0] != 'x':
                        rows.append(' '.join(p[:3]))
                        try:
                            amp[p[0]] = (float(p[1]), float(p[2]))
                        except ValueError:
                            pass
                    c += 1
                    j += 1
                current = (units or '').startswith('knot') or line.rstrip().endswith('Current')
                # Rund ein Viertel der Saetze steht in Fuss. Ohne Umrechnung
                # sieht ein Fuss-Satz gegen einen Meter-Satz aus wie ein
                # dreifach zu grosser Tidenhub.
                scale = 0.3048 if (units or '').startswith('f') else 1.0
                z = {x: cmath.rect(scale * amp.get(x, (0.0, 0.0))[0],
                                   -math.radians((amp.get(x, (0.0, 0.0))[1]
                                                  - SPEED[x] * hours) % 360))
                     for x in MAIN}
                recs.append(dict(
                    fp=hashlib.md5('|'.join(rows).encode()).hexdigest(),
                    file=path, name=line, key=namekey(line),
                    toks=name_tokens(line), lat=lat, lon=lon,
                    slots=c, current=current, amp=amp, z=z,
                    units=units or '', scale=scale,
                    tot=sum(abs(z[x]) for x in MAIN), line=k + 1))
                lat = lon = units = None
    return recs


def _num(line):
    try:
        return float(line.split(':', 1)[1])
    except ValueError:
        return None


def km(a, b):
    return 6371 * math.hypot(math.radians(a['lat'] - b['lat']),
                             math.radians(a['lon'] - b['lon'])
                             * math.cos(math.radians(a['lat'])))


def curve_diff(a, b):
    d = math.sqrt(sum(abs(a['z'][x] - b['z'][x]) ** 2 for x in MAIN) / 2)
    return d, d / max(0.15, (a['tot'] + b['tot']) / 2)


def load_done():
    done = set()
    if os.path.exists(DONE):
        with open(DONE, encoding='utf-8') as fh:
            for row in csv.DictReader(fh):
                done.add((row['check'].strip(), row['key'].strip()))
    return done


def main():
    show_all = '--all' in sys.argv
    recs = load_records()
    done = load_done()
    tide = [r for r in recs if not r['current'] and r['lat'] is not None
            and r['lon'] is not None]
    findings = collections.defaultdict(list)

    added = {}

    def add(check, key, text, sev=0.0):
        if not show_all and (check, key) in done:
            return
        prev = added.get((check, key))
        if prev is None or sev > prev[0]:
            added[(check, key)] = (sev, key, text)

    # ---- L: Sperrliste -------------------------------------------------
    locked = {}
    if os.path.exists(LOCK):
        with open(LOCK, encoding='utf-8') as fh:
            for row in csv.DictReader(fh):
                if row['provenance'] in ('manual', 'source'):
                    locked[row['fingerprint']] = row
    by_fp = collections.defaultdict(list)
    for r in recs:
        by_fp[r['fp']].append(r)
    for fp, row in locked.items():
        here = by_fp.get(fp, [])
        if not here:
            # Ein gesperrter Datensatz ist verschwunden. Das ist oft gewollt
            # -- aber es darf nie unbemerkt bleiben, sonst faellt Handarbeit
            # lautlos aus den Daten heraus.
            add('E', fp, f'{"entfernt":>13}  {row["name"][:44]:44} '
                         f'[{row["provenance"]}] {row["file"].split("/")[-1]}',
                2.0 if row['provenance'] == 'manual' else 1.0)
            continue
        if len(here) > 1:
            continue        # Mehrfachvorkommen unten, ueber alle Datensaetze
        r = here[0]
        moved = None
        if r['lat'] is not None and row['lat'] and row['lon']:
            moved = 6371000 * math.hypot(
                math.radians(r['lat'] - float(row['lat'])),
                math.radians(r['lon'] - float(row['lon']))
                * math.cos(math.radians(r['lat'])))
        if moved is not None and moved > 1.0:
            add('L', fp, f'{moved:8.0f} m verschoben  {row["name"][:40]:40} '
                         f'[{row["provenance"]}] {r["file"].split("/")[-1]}', moved)
        elif r['name'] != row['name']:
            add('L', fp, f'{"umbenannt":>13}  {row["name"][:40]:40} -> {r["name"][:40]} '
                         f'[{row["provenance"]}]', 1e9)

    # Mehrfachvorkommen ueber den gesamten Bestand, nicht nur ueber die
    # Sperrliste: dort steht pro Fingerabdruck nur eine Zeile, doppelte
    # Kurven waeren also gerade dort unsichtbar.
    for fp, here in by_fp.items():
        if len(here) < 2:
            continue
        d = 0.0
        pos = [x for x in here if x['lat'] is not None]
        for i in range(len(pos)):
            for j in range(i + 1, len(pos)):
                d = max(d, km(pos[i], pos[j]))
        add('E', fp, f'{len(here)}x dieselbe Kurve, max {d:6.1f} km  '
                     + ' | '.join(f'{x["name"][:26]} [{x["file"].split("/")[-1][:24]}]'
                                  for x in here)[:150],
            100.0 - d)

    # ---- S: Struktur ---------------------------------------------------
    modal = {}
    for path in {r['file'] for r in recs}:
        c = collections.Counter(r['slots'] for r in recs if r['file'] == path)
        if c:
            modal[path] = c.most_common(1)[0][0]
    for r in recs:
        if r['lat'] is None or r['lon'] is None:
            add('S', r['fp'], f'ohne Position   {r["name"][:45]:45} {r["file"]}:{r["line"]}')
        elif r['slots'] != modal.get(r['file']):
            add('S', r['fp'], f'{r["slots"]} statt {modal[r["file"]]} Slots  '
                              f'{r["name"][:40]:40} {r["file"]}:{r["line"]}')

    # ---- A und B -------------------------------------------------------
    grid = collections.defaultdict(list)
    for i, r in enumerate(tide):
        grid[(round(r['lat'] / 0.05), round(r['lon'] / 0.05))].append(i)
    seen = set()
    for (a, b), idx in grid.items():
        near = [x for da in (-1, 0, 1) for db in (-1, 0, 1)
                for x in grid.get((a + da, b + db), [])]
        for i in idx:
            for j in near:
                if j <= i or (i, j) in seen:
                    continue
                seen.add((i, j))
                r1, r2 = tide[i], tide[j]
                d = km(r1, r2)
                if d > NEAR_KM:
                    continue
                absd, rel = curve_diff(r1, r2)
                if rel > NEAR_TOL:
                    key = '|'.join(sorted((r1['fp'], r2['fp'])))
                    add('A', key, f'{d:4.1f} km  {rel*100:4.0f}% ({absd:.2f} m)  '
                                  f'{r1["name"][:34]:34} [{r1["file"].split("/")[-1][:24]:24}]  <->  '
                                  f'{r2["name"][:34]:34} [{r2["file"].split("/")[-1][:24]}]', rel)
    byname = collections.defaultdict(list)
    for i, r in enumerate(tide):
        if len(r['key']) >= 5:
            byname[r['key']].append(i)
    for _key, idx in byname.items():
        for a in range(len(idx)):
            for b in range(a + 1, len(idx)):
                r1, r2 = tide[idx[a]], tide[idx[b]]
                d = km(r1, r2)
                if d <= FAR_KM:
                    continue
                if not (r1['toks'] <= r2['toks'] or r2['toks'] <= r1['toks']):
                    continue
                _absd, rel = curve_diff(r1, r2)
                if rel > FAR_TOL:
                    continue
                key = '|'.join(sorted((r1['fp'], r2['fp'])))
                add('B', key, f'{d:7.0f} km auseinander, Kurven {rel*100:3.0f}%  '
                              f'{r1["name"][:30]:30} {r1["lat"]:8.3f} {r1["lon"]:9.3f} '
                              f'[{r1["file"].split("/")[-1][:22]:22}]  <->  '
                              f'{r2["name"][:30]:30} {r2["lat"]:8.3f} {r2["lon"]:9.3f} '
                              f'[{r2["file"].split("/")[-1][:22]}]', d)

    # ---- M: dominante Nebenkonstituente --------------------------------
    for r in tide:
        maj = max((r['amp'].get(x, (0.0, 0))[0] for x in MAJOR), default=0.0)
        minor = [(v[0], x) for x, v in r['amp'].items() if x not in MAJOR]
        if not minor or maj <= 0:
            continue
        v, x = max(minor)
        if v > MINOR_FACTOR * maj:
            add('M', r['fp'], f'{x:8} {v:6.2f} m gegen {maj:5.2f} m  '
                              f'{r["name"][:40]:40} {r["file"].split("/")[-1]}', v / maj)

    # ---- Bericht -------------------------------------------------------
    for (c, _k), row in added.items():
        findings[c].append(row)
    titles = {'L': 'Sperrliste verletzt',
              'E': 'gesperrter Datensatz entfernt oder mehrfach vorhanden',
              'S': 'Struktur',
              'A': f'Nachbarn unter {NEAR_KM:.0f} km, Kurven ueber {NEAR_TOL*100:.0f}% verschieden',
              'B': 'gleicher Name, gleiche Kurve, weit auseinander',
              'M': 'dominante Nebenkonstituente'}
    print(f'{len(recs)} Datensaetze, davon {len(tide)} Pegel mit Position')
    print(f'{len(done)} Faelle in geprueft.csv abgehakt\n')
    total = 0
    for c in 'LESBMA':
        rows = findings.get(c, [])
        total += len(rows)
        print(f'[{c}] {titles[c]}: {len(rows)} offen')
        for _sev, _key, text in sorted(rows, key=lambda t: -t[0])[:15]:
            print(f'      {text}')
        if len(rows) > 15:
            print(f'      ... und {len(rows)-15} weitere')
        print()
    print(f'Offen insgesamt: {total}')
    if '--csv' in sys.argv:
        d = sys.argv[sys.argv.index('--csv') + 1]
        os.makedirs(d, exist_ok=True)
        for c, rows in findings.items():
            with open(os.path.join(d, f'health_{c}.csv'), 'w', newline='',
                      encoding='utf-8') as fh:
                w = csv.writer(fh)
                w.writerow(['check', 'key', 'severity', 'text'])
                w.writerows([[c, k, f'{sv:.4f}', t]
                             for sv, k, t in sorted(rows, key=lambda t: -t[0])])
        print(f'CSV -> {d}')
    return 1 if findings.get('L') else 0


if __name__ == '__main__':
    sys.exit(main())
