#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Legt fehlende argentinische Saetze aus den SHN-Reihen an.

Anders als dhn_neufit und chs_neufit, die einen vorhandenen Satz
ersetzen, schreibt dieses Werkzeug neue: an acht der 66 SHN-Stationen
steht ueberhaupt kein uTide-Satz, an zweien davon (Mar de Ajo, Monte
Hermoso) im Umkreis von zwei Kilometern gar nichts. Das sind Luecken in
der Weltabdeckung, die diese Quelle schliessen kann.

Die Rechnung selbst kommt aus dhn_neufit; dort steht, worauf zu achten
ist -- die Epoche fuer utide, die monotone Interpolation, das ganze Jahr
statt eines Monats. Die stuendlichen Stationen gehen ohne Umweg in den
Ausgleich: ihre 8760 Werte sind besser als die daraus abgeleiteten
Scheitel.

Gemessen wird jeder neue Satz gegen den Juli, bevor er uebernommen
wird. Wer schlechter als --grenze Prozent des Tidenhubs bleibt, wird
verworfen -- lieber keine Station als eine falsche.

Die Position kommt aus der SHN-Datei und ist dort auf Bogenminuten
gerundet; das sind bis zu 900 m. Fuer die Vorhersage spielt das keine
Rolle, fuer die Nachbarschaftspruefung des health_check schon, deshalb
steht es als Kommentar im Satz.

Usage: python3 py/shn_neufit.py [--grenze 2] [--nur <code>]
       python3 py/shn_neufit.py --schreiben
"""
from __future__ import annotations

import datetime as dt
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import load_records, km, ROOT, MERIDIAN          # noqa: E402
from dhn_neufit import fitte, KON                                  # noqa: E402
from bom_qualitaet import vergleich, EREIGNIS                      # noqa: E402
from chs_qualitaet import xtide, TCD                               # noqa: E402
import shn_referenz as S                                           # noqa: E402

TXT = os.path.join(ROOT, 'harmonics/utide/harmonics_utide_tidetables.txt')
BACKUP = os.path.join(ROOT, 'harmonics/backup')
ARBEIT = '/tmp/shn_neufit'
VORLAGE = 'Bahía Thetis, Tierra del Fuego, Argentina'
GRENZE = 2.0        # so gut muss ein neuer Satz sein (Prozent des Hubs)
# Reichweite, in der ein vorhandener Satz als "deckt diese Station schon
# ab" gilt. Drei Kilometer, nicht zwei: die SHN-Position ist auf
# Bogenminuten gerundet, und in Mar de Ajo steht der vorhandene Satz
# 2.6 km daneben. Mit zwei Kilometern haette das Werkzeug ihn uebersehen
# und einen zweiten danebengesetzt -- eine Dublette statt einer Luecke.
NAH_KM = 3.0


def vorlage(zeilen):
    """Konstituentenzeilen eines vorhandenen Satzes als Geruest.

    Die Reihenfolge und der Satz der 175 Konstituenten muessen zu der
    Datei passen, in die geschrieben wird; abschreiben ist sicherer als
    sie neu aufzuzaehlen.
    """
    for k, z in enumerate(zeilen):
        if z.strip() == VORLAGE and k + 1 < len(zeilen) and MERIDIAN.match(zeilen[k + 1]):
            e = k + 3
            while e < len(zeilen) and zeilen[e].strip() and not zeilen[e].startswith('#'):
                e += 1
            return zeilen[k + 3:e]
    raise SystemExit(f'Vorlage "{VORLAGE}" nicht gefunden')


def block(st, con, z0, geruest, guete):
    """Vollstaendiger Satz fuer eine SHN-Station."""
    heute = f'{dt.date.today():%Y%m%d}'
    kopf = [
        '# Harmonic constants derived from SHN Argentina tide predictions',
        f'# using UTide, {"hourly heights" if S.stuendlich(st) else "HW/LW"}, '
        f'year {S.JAHR}',
        '#',
        f'# {st["name"]}',
        '# BEGIN HOT COMMENTS',
        '# country: Argentina',
        '# source: SHN Argentina tide tables × UTide',
        f'# station_id_context: SHN-{st["code"]}',
        f'# date_imported: {heute}',
        '# datum: Chart Datum',
        '# confidence: 7',
        f'# shn_code: {st["code"]}',
        f'# note: {heute} neu angelegt (py/shn_neufit.py); an dieser Station '
        f'stand bisher kein Satz aus der amtlichen Tafel. Gegen den Juli '
        f'{S.JAHR} gemessen {guete:.2f} % des Tidenhubs.',
        '# note: Position aus der SHN-Datei, dort auf Bogenminuten gerundet '
        '(bis zu 900 m).',
        '# !units: meters',
        f'# !longitude: {st["lon"]:.4f}',
        f'# !latitude: {st["lat"]:.4f}',
    ]
    zeilen = []
    for z in geruest:
        m = KON.match(z)
        if not m or m.group(1) == 'x':
            zeilen.append(z)
            continue
        c = m.group(1).upper()
        a, g = con.get(c, (0.0, 0.0))
        zeilen.append(f'{m.group(1):<16}{a:.4f}  {g:.2f}')
    # fitte() rechnet in UTC, die Phasen sind auf Greenwich bezogen --
    # der Meridian muss +00:00 sagen, sonst liegt der Satz um den
    # Zonenversatz daneben.
    return kopf + [_name(st), '+00:00 :UTC', f'{z0:.4f} meters'] + zeilen


# Wo der Bestand einen Ort schon anders benennt als der SHN, gilt der
# Bestand: die Namen sollen untereinander stimmen, und eine Quelle darf
# ihre Benennung nicht ueber die uebrigen legen. Puerto Argentino heisst
# im Bestand durchweg Stanley.
NAMEN = {
    'PARG': 'Stanley, Falkland Islands',
    'SSEB': 'Bahía San Sebastián, Tierra del Fuego, Argentina',
    'SUCE': 'Bahía Buen Suceso, Tierra del Fuego, Argentina',
    'USHU': 'Bahía Ushuaia, Tierra del Fuego, Argentina',
    'MHER': 'Monte Hermoso, Buenos Aires, Argentina',
    'MAJO': 'Mar de Ajó, Buenos Aires, Argentina',
    'PDES': 'Puerto Deseado, Santa Cruz, Argentina',
    'MADR': 'Puerto Madryn, Chubut, Argentina',
}


def _name(st):
    """Satzname im Stil des Bestands: Ort, Provinz, Land.

    Der SHN schreibt durchweg in Grossbuchstaben und ohne Provinz
    ("PUERTO DE BUENOS AIRES (Muelle de Pescadores)"), der Bestand
    gemischt und mit Provinz. Fuer die Stationen, um die es hier geht,
    steht der Name in NAMEN; alles andere waere Raten.
    """
    if st['code'] in NAMEN:
        return NAMEN[st['code']]
    n = st['name']
    if n.isupper():
        n = n.title()
    return f'{n}, {"Antarctica" if st["lat"] < -60 else "Argentina"}'


def deckung(st, recs, grenze, weite=60.0):
    """Trifft schon ein vorhandener Satz diese Tafel? -> (prozent, name, datei)

    Nach dem Abstand allein zu gehen reicht nicht. In Monte Hermoso steht
    der vorhandene Satz laut Datei 32 km von der SHN-Position entfernt --
    und trifft die Tafel trotzdem auf 0.17 Prozent des Tidenhubs. Es ist
    derselbe Pegel; eine der beiden Positionen ist falsch. Wer nur den
    Abstand prueft, legt hier einen zweiten Satz an und hat statt einer
    Luecke eine Dublette.

    Darum wird gemessen statt gemessen-geschaetzt: jeder Satz im weiten
    Umkreis wird gegen die Tafel gerechnet. Sobald einer sie trifft, ist
    die Station versorgt.
    """
    ref = S.vorhersage(st)
    if len(ref) < 40:
        return None
    hub = max(h for _z, h, _a in ref) - min(h for _z, h, _a in ref)
    if hub <= 0:
        return None
    von = f'{min(z for z, _h, _a in ref) - dt.timedelta(hours=6):%Y-%m-%d %H:%M}'
    bis = f'{max(z for z, _h, _a in ref) + dt.timedelta(hours=6):%Y-%m-%d %H:%M}'
    ziel = {'lat': st['lat'], 'lon': st['lon']}
    aus = None
    for r in sorted(recs, key=lambda q: km(ziel, q)):
        if km(ziel, r) > weite:
            break
        tcd = os.path.basename(r['file'])[:-4] + '.tcd'
        if not os.path.exists(os.path.join(TCD, tcd)):
            continue
        y = xtide(tcd, r['name'], von, bis)
        if not y:
            continue
        g = vergleich(ref, y)
        if not g:
            continue
        p = g['rms'] / hub * 100
        if aus is None or p < aus[0]:
            aus = (p, r['name'], os.path.basename(r['file']), km(ziel, r))
        if p <= grenze:
            break
    return aus


def messe(bl, ref):
    os.makedirs(ARBEIT, exist_ok=True)
    import build_noaa_cptt as b
    p = list(bl)
    for j, z in enumerate(p):
        if MERIDIAN.match(z) and j > 0:
            p[j - 1] = 'PROBE'
            break
    txt, tcd = os.path.join(ARBEIT, 'p.txt'), os.path.join(ARBEIT, 'p.tcd')
    open(txt, 'w', encoding='iso-8859-1', errors='replace').write(
        '\n'.join(list(b.HEADER) + p) + '\n')
    if os.path.exists(tcd):
        os.remove(tcd)
    if subprocess.run(['build_tide_db', tcd, txt], capture_output=True).returncode:
        return None
    von = f'{min(z for z, _h, _a in ref) - dt.timedelta(hours=6):%Y-%m-%d %H:%M}'
    bis = f'{max(z for z, _h, _a in ref) + dt.timedelta(hours=6):%Y-%m-%d %H:%M}'
    out = subprocess.run(['tide', '-l', 'PROBE', '-b', von, '-e', bis,
                          '-m', 'p', '-u', 'm', '-f', 'c', '-z'],
                         env=dict(os.environ, HFILE_PATH=tcd),
                         capture_output=True, encoding='iso-8859-1',
                         errors='replace').stdout
    y = []
    for z in out.split('\n'):
        m = EREIGNIS.match(z.strip())
        if not m:
            continue
        h = int(m.group(3)) % 12 + (12 if m.group(5) == 'P' else 0)
        y.append((dt.datetime.strptime(m.group(2), '%Y-%m-%d').replace(
            hour=h, minute=int(m.group(4))), float(m.group(6)), m.group(7)))
    return vergleich(ref, y) if y else None


def main(argv):
    grenze = float(argv[argv.index('--grenze') + 1]) if '--grenze' in argv else GRENZE
    nur = argv[argv.index('--nur') + 1] if '--nur' in argv else None
    schreiben = '--schreiben' in argv

    zeilen = open(TXT, encoding='iso-8859-1').read().split('\n')
    geruest = vorlage(zeilen)

    recs = [r for r in load_records() if r['lat'] is not None and not r['current']]
    ziel = []
    for s in S.stationen():
        if nur and nur.upper() != s['code']:
            continue
        vor = deckung(s, recs, grenze)
        if vor and vor[0] <= grenze:
            continue
        ziel.append((s, vor))
    print(f'{len(ziel)} SHN-Stationen ohne Satz, der die Tafel auf '
          f'{grenze} % des Hubs trifft\n')

    gebaut, verworfen = [], []
    for s, vor in ziel:
        jahr = S.jahresreihe(s)
        ref = S.vorhersage(s)
        if len(jahr) < 500 or len(ref) < 40:
            verworfen.append((s, f'nur {len(jahr)} Werte im Jahr'))
            continue
        hub = max(h for _z, h, _a in ref) - min(h for _z, h, _a in ref)
        try:
            con, z0 = fitte(jahr, 0.0, s['lat'])       # Reihe steht schon in UTC
        except Exception as ex:
            verworfen.append((s, type(ex).__name__))
            continue
        bl = block(s, con, z0, geruest, 0.0)
        g = messe(bl, ref)
        if not g:
            verworfen.append((s, 'nicht messbar'))
            continue
        p = g['rms'] / hub * 100
        if p > grenze:
            verworfen.append((s, f'{p:.2f} % des Hubs'))
            continue
        gebaut.append((s, block(s, con, z0, geruest, p), p, hub, g, vor))

    for s, _bl, p, hub, g, vor in sorted(gebaut, key=lambda x: x[2]):
        alt = (f'bisher bester {vor[0]:5.2f} % ({vor[2][:24]}, {vor[3]:.1f} km)'
               if vor else 'bisher nichts im Umkreis')
        print(f'  {p:5.2f} % ({g["rms"]*100:5.1f} cm bei {hub:5.2f} m Hub, '
              f'Versatz {g["versatz_min"]:+4.0f} min)  {_name(s)[:42]:42} {alt}')
    if verworfen:
        print('\nnicht uebernommen:')
        for s, warum in verworfen:
            print(f'   {s["code"]:5} {s["name"][:44]:44} {warum}')
    if not schreiben:
        print(f'\n{len(gebaut)} Saetze bereit (--schreiben, um sie anzulegen)')
        return 0

    shutil.copy2(TXT, os.path.join(
        BACKUP, os.path.basename(TXT) + f'.vor_shnneufit_{dt.datetime.now():%Y%m%d_%H%M}'))
    while zeilen and not zeilen[-1].strip():
        zeilen.pop()
    for s, bl, _p, _hub, _g, _vor in gebaut:
        zeilen += [''] + bl
    zeilen.append('')
    tmp = TXT + '.neu'
    open(tmp, 'w', encoding='iso-8859-1').write('\n'.join(zeilen))
    os.replace(tmp, TXT)
    print(f'\n{len(gebaut)} Saetze angelegt: {TXT}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
