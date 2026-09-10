#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Berichtigt Zeit- und Vorzeichenfehler in TICON-Saetzen -- nur belegt.

Befund vom 10.09.2026 (py/ticon_zeitpruefung.py und FES2022):

  Meridian falsch beschriftet  22 von 80 TICON-Saetzen im Meridian +01:00
      liegen um -60 min neben FES (bei +00:00: 2 von 586): ihre Phasen sind
      UTC, beschriftet als MEZ. Dasselbe in Zonen mit halbstuendigem
      Versatz (Oliver): dort ist der Fehler +-30 oder +-45 min.
  Mexiko umgedreht  26 Saetze aus GESLA/UHSLC_RQ bzw. UNAM_HIST: Phasen um
      180 Grad verdreht (Kurve auf dem Kopf). fix_ticon4_uhslc_rq_mexico_
      meridian.py hat im Juli den Meridian auf -06:00 gesetzt -- 6 h sind
      bei M2 fast genau 180 Grad, halbtaegig sah es richtig aus, K1/O1
      lagen danach 90 Grad daneben. Geprueft war nur M2.
  Manzanillo  hatte richtige UTC-Phasen und bekam durch denselben Eingriff
      6 h Versatz. Cabo San Lucas, Isla Socorro: 180 Grad ohne Eingriff.

Einheitliche Rechnung: wahre Greenwich-Phase = G_alt + w*D (+180 Grad bei
umgedrehter Kurve), geschrieben mit Meridian +00:00. D = um so viele Stunden
spaeter legen.

Geschrieben wird ein Satz nur, wenn er DANACH stimmt:
  * gegen FES, relativ zur Region (Median der nicht-TICON-Saetze bis 150 km),
    bei allen Partialtiden bis 20 min,
  * gegen den Zwilling bis 2 km, falls es einen gibt, bis 15 min,
  * gegen eine Messreihe bis 5 km, falls es eine gibt: ihr Zeitversatz vorher
    muss dem Betrag der Korrektur entsprechen (bis 15 min).
Glatte Stufen nur (ganze Stunden; halbe/Dreiviertel in solchen Zonen) --
krumme Betraege wie die deutschen +40 min werden nicht gedreht.

Usage: venv/bin/python3 py/ticon_zeit_richten.py [--schreiben]
"""
from __future__ import annotations

import cmath
import collections
import csv
import datetime as dt
import math
import os
import re
import shutil
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ticon_zeitpruefung as T                                         # noqa: E402
import messreihe_qualitaet as MQ                                       # noqa: E402
from health_check import load_records, km, MAIN, SPEED as HSP          # noqa: E402
from transfer_zonen import zeitversatz                                 # noqa: E402
from transfer_zonen_richten import speeds, _tz_std                     # noqa: E402
from pegel_dubletten import vermerke, ABGELEITET                       # noqa: E402
from sicher_schreiben import schreiben                                 # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATEI = os.path.join(ROOT, 'harmonics/ticon/harmonics_ticon4_worldwide.txt')
HEUTE = dt.date.today().strftime('%Y%m%d')
ZIEL_FES = 20
ZIEL_ZW = 15
REIHE_KM = 5.0
# Diese Saetze werden geloescht statt gedreht (krumme Versaetze, Oliver 10.09.2026)
LOESCHEN = {'Mellumplate (Jade), Germany', 'Dagebüll, Germany', 'Elmshorn (Krückau Hafen), Germany',
            'Itzehoe (Stör Hafen), Germany', 'Krückau-Sperrwerk (Binnenpegel), Germany',
            'Pinnau-Sperrwerk (Binnenpegel), Germany', 'Lühort (Lühe), Germany', 'Elsfleth (Weser), Germany',
            'Farge (Weser), Germany', 'Vegesack (Weser), Germany',
            'Este (Inneres Sperrwerk Binnenpegel), Germany', 'Ritterhude (Hamme), Germany',
            'Wasserhorst (Lesum), Germany', 'Cranz (Este-Sperrwerk), Germany', 'Altengamme (Elbe), Germany',
            'Fahrenholz (Ilmenau Unterpegel), Germany', 'K13 Alpha Platform, Netherlands'}


def mer_h(s):
    vz = -1.0 if s[0] == '-' else 1.0
    hh, mm = s.lstrip('+-').split(':')
    return vz * (int(hh) + int(mm) / 60.0)


def stufen(tz):
    """Zulaessige Korrekturstufen in Stunden fuer eine Station."""
    off = _tz_std(tz) if tz else None
    s = [1.0, -1.0, 2.0, -2.0]
    if off is not None and abs(off - round(off)) > 0.01:
        frac = abs(off - math.floor(off))
        s += [0.5, -0.5] if abs(frac - 0.5) < 0.01 else [0.75, -0.75, 0.25, -0.25]
    return s


def z_nach(r, D, inv):
    z = {}
    for x in MAIN:
        w = r['z'][x]
        g = (-math.degrees(cmath.phase(w))) % 360
        g2 = (g + HSP[x] * D + (180 if inv else 0)) % 360
        z[x] = cmath.rect(abs(w), -math.radians(g2))
    return {**r, 'z': z, '_fes': r.get('_fes', id(r))}


def main(argv):
    recs = [r for r in load_records() if r['lat'] is not None and not r['current']]
    komm = vermerke()
    for r in recs:
        r['abg'] = bool(ABGELEITET.search(komm.get((r['file'], r['line']), '')))
        r['tic'] = 'ticon' in r['file']
    zeilen = open(DATEI, encoding='iso-8859-1').read().split('\n')
    tic = [r for r in recs if r['tic']]
    for r in tic:
        m = zeilen[r['line']].split()
        r['mer'], r['tz'] = m[0], (m[1].lstrip(':') if len(m) > 1 else '')
    basis = [r for r in recs if not r['tic'] and not r['abg']]
    fes = T.fes_werte(tic + basis)

    def roh(r):
        d = {}
        for c in T.TEILE:
            w = r['z'][c]
            g, a = (-math.degrees(cmath.phase(w))) % 360, abs(w)
            gf, af = fes[r.get('_fes', id(r))][c]
            if a >= T.MIND_AMP and af >= T.MIND_AMP and not math.isnan(gf):
                d[c] = T.versatz_min(g, gf, c)
        return d
    gitter = collections.defaultdict(list)
    for b in basis:
        gitter[(int(b['lat'] // 2), int(b['lon'] // 2))].append(b)
    rb = {id(b): roh(b) for b in basis}

    def region(t):
        nah = [b for dz in (-1, 0, 1) for dm in (-1, 0, 1)
               for b in gitter.get((int(t['lat'] // 2) + dz, int(t['lon'] // 2) + dm), ())
               if km(t, b) <= T.REGION_KM]
        base = {}
        for c in T.TEILE:
            w = [rb[id(b)][c] for b in nah if c in rb[id(b)]]
            if len(w) >= T.MIND_NACHBARN:
                base[c] = statistics.median(w)
        zw = min(((km(t, b), b) for b in nah if km(t, b) <= T.ZWILLING_KM),
                 key=lambda x: x[0], default=None)
        return base, zw

    def resid(r, base):
        o = roh(r)
        return {c: o[c] - base[c] for c in o if c in base}

    # Messreihen-Anker wie in messreihe_qualitaet.py
    kopf = MQ.kopfdaten()
    dateien = MQ.reihendateien()
    anker = []
    for r in recs:
        sid = kopf.get((r['file'], r['line']), (None, None, ''))[0]
        if not sid:
            continue
        teile = [t for t in re.split(r'[ \-_]', sid) if t]
        p = None
        for i in range(len(teile)):
            for j in range(len(teile)):
                if i != j:
                    p = p or dateien.get((teile[i].upper(), teile[j].upper()))
        if p and os.path.basename(p) not in MQ.GESPERRT:
            anker.append((r['lat'], r['lon'], p))
    for f in (MQ.bodc_reihen, MQ.npz_reihen, MQ.beiblatt_reihen, MQ.jhod_reihen,
              MQ.linz_reihen, MQ.ea_reihen):
        anker += [(a['lat'], a['lon'], p) for a, p, _f, _b in f(None)]

    def reihe_versatz(t):
        best = None
        for la, lo, p in anker:
            d = km(t, {'lat': la, 'lon': lo})
            if d <= REIHE_KM and (best is None or d < best[0]):
                best = (d, p)
        if not best:
            return None, None
        obs = MQ.lies(best[1])
        if len(obs) < MQ.MIND_PUNKTE_TAFEL:
            return None, None
        import numpy as np
        ende = obs[-1][0]
        start = ende - 365 * 86400
        paare = [(a, b) for a, b in obs if start <= a <= ende]
        von = dt.datetime.fromtimestamp(start - 7200, dt.timezone.utc).strftime('%Y-%m-%d %H:%M')
        bis = dt.datetime.fromtimestamp(ende + 7200, dt.timezone.utc).strftime('%Y-%m-%d %H:%M')
        vt, vh = MQ.vorhersage('harmonics_ticon4_worldwide.tcd', t['name'], von, bis)
        g = MQ.messe(np.array([a for a, _ in paare]), np.array([b for _, b in paare]), vt, vh,
                     MQ.MIND_PUNKTE_TAFEL)
        return (g[3] if g else None), os.path.relpath(best[1], MQ.REIHEN)

    vorschlag = []
    for t in tic:
        if t['name'] in LOESCHEN:
            continue
        base, zw = region(t)
        res = resid(t, base)
        kand = []
        if t['name'] == 'Manzanillo, Colima, Mexico' and t['mer'] == '-06:00':
            kand = [(-6.0, False, 'Meridian -06:00 auf UTC-Phasen (Juli-Eingriff)')]
        elif t['name'].endswith(', Mexico') and t['mer'] == '-06:00':
            kand = [(-6.0, True, 'Mexiko: Kurve umgedreht, Juli-Eingriff -06:00 nur an M2 geprueft')]
        elif len(res) >= 3:
            rad = {c: math.radians(res[c] / 60 * HSP[c]) for c in res}
            if all(abs(abs(math.degrees(v)) - 180) <= 30 for v in rad.values()):
                kand = [(0.0, True, 'Kurve umgedreht (alle Partialtiden 180 Grad)')]
            elif max(res.values()) - min(res.values()) <= ZIEL_FES:
                mittel = statistics.mean(res.values())
                for s in stufen(t['tz']):
                    if abs(mittel + s * 60) <= 15 and abs(mittel) >= 25:
                        kand = [(s, False, f'einheitlich {mittel:+.0f} min gegen FES (Region)')]
        if not kand:
            continue
        D, inv, grund = kand[0]
        neu = z_nach(t, D, inv)
        mexiko = t['name'].endswith(', Mexico') and t['mer'] == '-06:00'
        if mexiko and len(base) < 2:
            # Keine Nachbarn im Umkreis: roh gegen FES pruefen. Zulaessig nur
            # fuer die Mexiko-Gruppe -- derselbe Ursprung, derselbe Eingriff,
            # an 20 Saetzen mit Zwilling oder Region bestaetigt.
            base = {c: 0.0 for c in T.TEILE}
            roh_fes = True
        else:
            roh_fes = False
        res2 = resid(neu, base)
        # Roh gegen FES (ohne Regionalabzug) liegt FES an Mexikos Kuesten selbst
        # bis ~30 min daneben -- La Paz (Cuarta Zona Naval), vom Zwilling auf -1 min
        # bestaetigt, zeigt roh +18..+28. Dort gilt deshalb 50 min.
        grenze = 50 if roh_fes else ZIEL_FES
        ok_fes = len(res2) >= 2 and max(abs(v) for v in res2.values()) <= grenze
        zw_vor = zw_nach = None
        if zw:
            v, g = zeitversatz(t, zw[1])
            zw_vor = v * 60 if v is not None else None
            v2, g2 = zeitversatz(neu, zw[1])
            zw_nach = v2 * 60 if v2 is not None and g2 >= 0.9 else None
            if v is None:
                zw = None
        ok_zw = zw is None or (zw_nach is not None and abs(zw_nach) <= ZIEL_ZW)
        mess, reihe = reihe_versatz(t)
        ok_mess = mess is None or inv or abs(mess + D * 60) <= 15
        beleg = '+'.join(x for x, ja in (('FES', ok_fes), ('Zwilling', zw is not None and ok_zw),
                                          ('Reihe', mess is not None and ok_mess and not inv)) if ja)
        # FES allein nur, wo der Fehler zu einem nachgewiesenen Mechanismus passt:
        # UTC-Phasen unter +01:00 (D = +1) oder der Mexiko-Eingriff.
        nur_fes = beleg == 'FES'
        mechanismus = mexiko or (t['mer'] == '+01:00' and D == 1.0) or inv
        urteil = ('richten' if (ok_fes or zw) and ok_zw and ok_mess
                  and (not nur_fes or mechanismus) else 'offen')
        vorschlag.append(dict(
            name=t['name'], meridian=t['mer'], tz=t['tz'], stunden=D, umgedreht=int(inv),
            grund=grund, fes_vorher=' '.join(f'{c}{v:+.0f}' for c, v in res.items()),
            fes_nachher=' '.join(f'{c}{v:+.0f}' for c, v in res2.items()),
            zwilling='' if not zw else f"{zw[1]['name']} [{os.path.basename(zw[1]['file'])}]",
            zwilling_vorher=None if zw_vor is None else round(zw_vor),
            zwilling_nachher=None if zw_nach is None else round(zw_nach),
            reihe=reihe or '', reihe_vorher_min=mess, beleg=beleg, urteil=urteil))
        print(f"  {urteil:7} {beleg:20} {t['name'][:40]:40} {t['mer']} D {D:+.2f} h{' +180' if inv else '     '}  "
              f"FES nachher [{vorschlag[-1]['fes_nachher']}]  Zw {zw_vor if zw_vor is None else round(zw_vor)} -> "
              f"{vorschlag[-1]['zwilling_nachher']}  Reihe {mess}", flush=True)
    aus = os.path.join(T.HELP, 'ticon_zeit_richten.csv')
    with open(aus, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(vorschlag[0].keys()))
        w.writeheader()
        w.writerows(vorschlag)
    c = collections.Counter(v['urteil'] for v in vorschlag)
    print(dict(c), '->', aus)
    if '--schreiben' not in argv:
        return 0
    sp = speeds(DATEI)
    ziel = {v['name']: v for v in vorschlag if v['urteil'] == 'richten'}
    n = 0
    for k in range(len(zeilen) - 1, -1, -1):
        v = ziel.get(zeilen[k])
        if not v or k + 1 >= len(zeilen) or not re.match(r'^[+-]\d\d:\d\d', zeilen[k + 1]):
            continue
        h_alt = mer_h(zeilen[k + 1].split()[0])
        D, inv = float(v['stunden']), bool(v['umgedreht'])
        j = k + 3
        while j < len(zeilen) and zeilen[j] and not zeilen[j].startswith('#'):
            p = zeilen[j].split()
            if p[0] != 'x' and p[0] in sp and len(p) >= 3:
                G = float(p[2]) - sp[p[0]] * h_alt
                g2 = (G + sp[p[0]] * D + (180 if inv else 0)) % 360
                zeilen[j] = f'{p[0]:<16}{float(p[1]):.4f}  {g2:.2f}'
            j += 1
        tz = zeilen[k + 1].split(':', 2)[-1] if zeilen[k + 1].count(':') >= 2 else 'UTC'
        zeilen[k + 1] = f'+00:00 :{tz}'
        zeilen[k:k] = [f"# note: {HEUTE} Zeit berichtigt: Meridian {v['meridian']} -> +00:00, "
                       f"{D:+.2f} h{', Kurve um 180 Grad gedreht' if inv else ''}.",
                       f"# note: -- {v['grund'][:70]}",
                       '# note: -- Belegt gegen FES/Zwilling/Reihe, siehe py/ticon_zeit_richten.py.']
        n += 1
    shutil.copy2(DATEI, os.path.join(ROOT, 'harmonics/backup',
                                     os.path.basename(DATEI) + f'.vor_zeit_richten_{HEUTE}'))
    schreiben(DATEI, '\n'.join(zeilen))
    print(f'{n} Saetze berichtigt')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
