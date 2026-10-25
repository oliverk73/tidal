#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stroemungskonstanten aus den brasilianischen "Cartas de Correntes de Maré" (CHM/DHN, Oliver 25.10.2026).

Die Hefte (currents/brazil/ccm-*.pdf, von Oliver im Browser geladen) zeigen je Kartensatz 13
Stundenkarten von 6 h vor bis 6 h nach der Preamar eines Bezugshafens, mittlere Springtide,
Geschwindigkeit in Knoten. Die PDFs sind Vektorgrafik:
  - Pfeil = roter Strich (Schaft) + rote Flaeche (Spitze),
  - Geschwindigkeit = roter Text "0,8" neben dem Pfeil (nicht jeder Pfeil hat eine Zahl),
  - Gradnetz-Beschriftung schwarz am Kartenrand (Grad/Minuten, Sued/West).

Umrechnung wie bei den SHOM-Atlanten (shom_atlas_stroemung.py):
  1. Pfeile mit Zahl ueber die 13 Karten zu Punkten verbinden (Zuordnung nach Lage),
  2. Preamar/Baixa-mar des Bezugshafens fuer ein Jahr aus unserem Satz vorausrechnen,
  3. Strom zur Zeit t = Kartenwert zur Stunde (t - PM), mal Faktor aus dem Tidenhub der Tide
     (Tabelle bzw. Abakus des Hefts),
  4. die Jahresreihe wie eine Messreihe fitten (cmems_stroemung_nachholen.analyse).

Schreibt nur nach harmonics/help/ (Bestand bleibt unberuehrt):
  chm_ccm_<heft>_<datum>.csv / .txt
Usage: venv/bin/python py/chm_ccm_stroemung.py HEFT [--nur-punkte]
       HEFT = Kurzname aus HEFTE (z.B. sao-marcos)
"""
from __future__ import annotations

import csv
import datetime as dt
import math
import os
import re
import sys

import fitz
import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cmems_stroemung_nachholen as C                               # noqa: E402
import shom_atlas_stroemung as S                                    # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF = os.path.join(ROOT, 'currents/brazil')
HILFE = os.path.join(ROOT, 'harmonics/help')
MS_KN = C.MS_KN
SCHWARZ = 0x231f20      # Farbe der schwarzen Schrift; alles andere mit Zahl = Geschwindigkeit


def faktor_sao_marcos(hub):
    # Tabelle im Heft: Hub 2,0..6,5 m -> 0,5..1,4, also 0,2*Hub + 0,1 (exakt an allen 10 Stuetzstellen)
    return 0.2 * hub + 0.1


# Kurzname -> (PDF, Bezugshafen in unserer Datei, Faktor(Hub))
HEFTE = {
    'sao-marcos': ('ccm-baia-sao-marcos.pdf', (S.TAFELN, 'Sao Luis, Maranhão, Brazil'), faktor_sao_marcos),
}

# Vorgeschlagene Namen je Punkt (Satz.Nr wie im Lauf; Punkte ohne Namen werden nicht als Block geschrieben).
# Ortsnamen aus der Karte bzw. wie bei Google Maps (Portugiesisch).
NAMEN = {
    'sao-marcos': {
        '1.10': 'Baía de São Marcos (Farol Itacolomi)',
        '2.1': 'Baía de São Marcos (Banco da Cerca)',
        '2.2': 'Baía de São Marcos (Rota Aconselhada)',
        '2.3': 'Banco do Cotovelo (Baía de São Marcos)',
        '2.4': "Ponta d'Areia (Baía de São Marcos)",
        '2.5': 'Pedra do Severino (Baía de São Marcos)',
        '2.6': 'Ilha do Medo (Baía de São Marcos)',
        '2.7': 'Canal do Boqueirão (Baía de São Marcos)',
        '2.8': "Farol de Ponta d'Areia (São Luís)",
        '2.9': 'Banco da Minerva (São Luís)',
        '2.11': 'Rio Anil (São Luís)',
        '2.12': 'Cabeço Mearim (Baía de São Marcos)',
        '2.13': 'Porto do Itaqui',
    },
}
HEFT_TITEL = {'sao-marcos': 'DG 10-V-1 Proximidades da Baía de São Marcos / Portos de São Luís e Itaqui'}
REGION = {'sao-marcos': 'Maranh\u00e3o, Brazil'}


def block(kurz, pdfname, hafen, zeile, r, name):
    from cmems_stroemung_nachholen import CONSTITUENTS_175, utide
    L = ['# Harmonic constants derived from the CHM/DHN tidal stream charts "Cartas de Correntes de Mare"',
         '# %s (%s), point %s, surface layer ~5 m, mean spring values' % (HEFT_TITEL[kurz], pdfname, zeile['punkt']),
         '# Chart rule: hours from HW %s (13 charts HW-6..HW+6), speed factor from tidal range (booklet table),'
         % hafen[1].split(',')[0],
         '# one synthetic year 2026; no time correction; charts include the mean wind drift (NE trade)',
         '# Chart values (kn@deg, HW-6..HW+6): %s' % zeile['werte'],
         '# (UTide v%s, principal-axis projection)' % utide.__version__,
         '# %d 10-minute samples, surface' % r['n'],
         '# from %s to %s' % (r['t0'].strftime('%Y-%m-%d'), r['t1'].strftime('%Y-%m-%d')),
         '# R^2 = %.4f, RMS error = %.4f knots' % (r['r2'], r['rms']),
         '# Major axis: %.1f deg true' % r['achse'], '#',
         '# BEGIN HOT COMMENTS',
         '# country: Brazil',
         '# source: CHM/DHN Cartas de Correntes de Mare (charts), UTide analysis',
         '# station_id_context: CHM-CCM-%s-%s' % (kurz.upper(), zeile['punkt']),
         '# institution: Centro de Hidrografia da Marinha (DHN)',
         '# datum: n/a', '# station_type: current',
         '# major_axis_deg_true: %.1f' % r['achse'],
         '# confidence: 5',
         '# chm_ccm: %s point %s' % (pdfname, zeile['punkt']),
         '# time_correction_min: 0',
         '# utide: period=%s..%s const=%d' % (r['t0'].strftime('%Y-%m-%d'), r['t1'].strftime('%Y-%m-%d'), len(r['konst'])),
         '# !units: knots', '# !longitude: %.4f' % zeile['lon'], '# !latitude: %.4f' % zeile['lat'],
         '%s, %s Current' % (name, REGION[kurz]), '+00:00 :UTC', '%.4f knots' % r['mean']]
    for k, _sp in CONSTITUENTS_175:
        a = r['konst'].get(k)
        L.append('%-15s %.4f  %.2f' % (k, a[0], a[1]) if a and a[0] >= 0.00005 else 'x 0 0')
    return '\n'.join(L)


def _rot(c):
    return bool(c) and c[0] > 0.8 and c[1] < 0.4 and c[2] < 0.4


def _punkte(g):
    out = []
    for it in g['items']:
        out += [q for q in it[1:] if hasattr(q, 'x')]
    return out


def pfeile(p):
    """-> Liste dict(x, y = Pfeilfuss, mx, my = Pfeilmitte, dir) in PDF-Punkten; dir = wohin, Grad (Kartennord oben)."""
    schaefte, spitzen = [], []
    for g in p.get_drawings():
        if g['type'] == 's' and _rot(g.get('color')):
            schaefte.append(_punkte(g))
        elif g['type'] == 'f' and _rot(g.get('fill')):
            spitzen.append(_punkte(g))
    out = []
    frei = list(range(len(schaefte)))
    for h in spitzen:
        cx = sum(q.x for q in h) / len(h)
        cy = sum(q.y for q in h) / len(h)
        best = None
        for k in frei:
            s = schaefte[k]
            for a, b in ((s[0], s[-1]), (s[-1], s[0])):
                d = math.hypot(b.x - cx, b.y - cy)
                if best is None or d < best[0]:
                    best = (d, a, k)
        if best is None or best[0] > 15:
            continue
        _, fuss, k = best
        frei.remove(k)
        spitze = max(h, key=lambda q: math.hypot(q.x - fuss.x, q.y - fuss.y))
        rw = math.degrees(math.atan2(spitze.x - fuss.x, -(spitze.y - fuss.y))) % 360
        # Der Messpunkt ist der Fuss des Pfeils: der bleibt in allen 13 Karten liegen
        out.append(dict(x=fuss.x, y=fuss.y, mx=(fuss.x + spitze.x) / 2, my=(fuss.y + spitze.y) / 2, dir=rw))
    return out


def zahlen(p):
    out = []
    for b in p.get_text('dict')['blocks']:
        for l in b.get('lines', []):
            for s in l['spans']:
                t = s['text'].strip()
                if s['color'] != SCHWARZ and re.fullmatch(r'\d,\d', t):
                    x0, y0, x1, y1 = s['bbox']
                    out.append(dict(x=(x0 + x1) / 2, y=(y0 + y1) / 2, v=float(t.replace(',', '.'))))
    return out


def stunde(p):
    """'6 HORAS ANTES DA PREAMAR ...' -> -6, 'PREAMAR ...' -> 0; None wenn keine Stundenkarte."""
    for b in p.get_text('dict')['blocks']:
        for l in b.get('lines', []):
            t = ''.join(s['text'] for s in l['spans']).strip().upper()
            m = re.match(r'^(\d+) HORAS? (ANTES|DEPOIS) DA PREAMAR', t)
            if m:
                return int(m.group(1)) * (-1 if m.group(2) == 'ANTES' else 1)
            if re.match(r'^PREAMAR( (DE|EM|NO|NA) [^.]*)?$', t):
                return 0
    return None


_GRAD = re.compile(r"^(\d{1,3})\s*[º°]\s*(?:(\d{1,2})\s*['’])?$")
_MIN = re.compile(r"^(\d{1,2})\s*['’]$")


def gradnetz(p):
    """Lineare Abbildung PDF -> (lat, lon) aus der Randbeschriftung. Sued und West negativ."""
    W, H = p.rect.width, p.rect.height
    oben, links = [], []
    for b in p.get_text('dict')['blocks']:
        for l in b.get('lines', []):
            spans = [s for s in l['spans'] if s['color'] == SCHWARZ]
            t = ''.join(s['text'] for s in spans).strip()
            if not t or l['dir'] != (1.0, 0.0):
                continue
            x0, y0, x1, y1 = l['bbox']
            m = _GRAD.match(t)
            n = _MIN.match(t)
            if not (m or n):
                continue
            wert = (int(m.group(1)), int(m.group(2) or 0)) if m else (None, int(n.group(1)))
            if x1 < 0.13 * W:
                # Breitenspalte links vom Kartenrahmen (die Laengen-Eckmarke sitzt weiter rechts)
                links.append(((y0 + y1) / 2, wert))
            elif y1 < 0.2 * H:
                oben.append(((x0 + x1) / 2, wert))
    return _achse(links, False), _achse(oben, True)


def _achse(lab, lon):
    """Beschriftung entlang einer Achse -> (a, b) mit Grad = a + b*Position (Betrag)."""
    lab = sorted(lab)
    # Doppelte (Grad-Zeile + Minuten-Zeile eng beieinander) zusammenfassen
    merged = []
    for pos, (g, m) in lab:
        # "44º" und "20'" als getrennte Zeilen: zusammen "44º 20'", Linie in der Mitte
        if merged and g is None and pos - merged[-1][0] < 16 and merged[-1][1][0] is not None \
                and merged[-1][1][1] == 0:
            pg, (gg, _mm) = merged[-1]
            merged[-1] = ((pg + pos) / 2, (gg, m))
            continue
        merged.append((pos, (g, m)))
    # Eckbeschriftung der anderen Achse sitzt dicht neben der ersten/letzten Marke: weg damit
    while len(merged) > 3:
        gaps = np.diff([q for q, _ in merged])
        med = np.median(gaps)
        if gaps[0] < 0.5 * med:
            merged.pop(1 if merged[0][1][0] is not None and merged[1][1][0] is None else 0)
        elif gaps[-1] < 0.5 * med:
            merged.pop(-2 if merged[-1][1][0] is not None and merged[-2][1][0] is None else -1)
        else:
            break
    anker =[i for i, (_, (g, _m)) in enumerate(merged) if g is not None]
    if not anker:
        raise ValueError('keine Grad-Beschriftung')
    i0 = anker[0]
    werte = [None] * len(merged)
    werte[i0] = merged[i0][1][0] + merged[i0][1][1] / 60
    # Richtung aus zwei Ankern oder aus den Minuten-Nachbarn ableiten: von i0 aus abwickeln
    for rng in (range(i0 + 1, len(merged)), range(i0 - 1, -1, -1)):
        prev = i0
        for i in rng:
            g, m = merged[i][1]
            if g is not None:
                werte[i] = g + m / 60
            else:
                pm = round((werte[prev] % 1) * 60)
                d = (m - pm + 30) % 60 - 30
                if d == -30:
                    d = 30
                werte[i] = werte[prev] + d / 60
            prev = i
    pos = np.array([q for q, _ in merged])
    w = np.array(werte)
    b, a = np.polyfit(pos, w, 1)
    rest = w - (a + b * pos)
    if np.abs(rest).max() > 0.3 / 60 * max(1, np.ptp(w) * 2):
        raise ValueError('Gradnetz unstimmig: %s' % list(zip(pos.round(), (w * 60).round(1))))
    return a, b


def kartensaetze(pdf):
    """-> Liste von Saetzen; Satz = dict(stunde -> (page, pfeile_mit_v, (lat_ab, lon_ab)))."""
    d = fitz.open(pdf)
    saetze, aktuell = [], None
    for i in range(d.page_count):
        p = d[i]
        if len(p.get_drawings()) < 20:
            continue
        h = stunde(p)
        if h is None:
            continue
        if h == -6 or aktuell is None or h in aktuell:
            aktuell = {}
            saetze.append(aktuell)
        P, Z = pfeile(p), zahlen(p)
        # Zahl -> Pfeil (Abstand Textmitte - Pfeilmitte, hoechstens 22 pt)
        mit = []
        if P and Z:
            M = np.array([[math.hypot(a['mx'] - z['x'], a['my'] - z['y']) for z in Z] for a in P])
            r, c = linear_sum_assignment(M)
            for ri, ci in zip(r, c):
                if M[ri, ci] <= 22:
                    mit.append(dict(P[ri], v=Z[ci]['v']))
        lat_ab, lon_ab = gradnetz(p)
        aktuell[h] = (i + 1, mit, (lat_ab, lon_ab), len(P), len(Z))
    return saetze


def spuren(satz, max_pt=12):
    """Pfeile ueber die Stunden verbinden -> Liste von {stunde: pfeil}.

    Verglichen wird mit der zuletzt gesehenen Lage jeder Spur, damit eine Stunde ohne
    zugeordnete Zahl die Spur nicht zerreisst.
    """
    sp = []
    for h in sorted(satz):
        B = satz[h][1]
        if not B:
            continue
        genutzt = set()
        if sp:
            letzte = [s[max(s)] for s in sp]
            M = np.array([[math.hypot(a['x'] - b['x'], a['y'] - b['y']) for b in B] for a in letzte])
            r, c = linear_sum_assignment(M)
            for ri, ci in zip(r, c):
                if M[ri, ci] <= max_pt:
                    sp[ri][h] = B[ci]
                    genutzt.add(ci)
        for k, b in enumerate(B):
            if k not in genutzt:
                sp.append({h: b})
    return sp


def zyklus_aus(s):
    """Spur -> Array (13, 2) u, v in Knoten; einzelne fehlende Stunden linear (in u/v) aufgefuellt."""
    std = sorted(s)
    uv = np.array([[s[h]['v'] * math.sin(math.radians(s[h]['dir'])),
                    s[h]['v'] * math.cos(math.radians(s[h]['dir']))] for h in std])
    alle = np.arange(-6, 7)
    return np.column_stack([np.interp(alle, std, uv[:, 0]), np.interp(alle, std, uv[:, 1])])


def lage(satz, s):
    """Mittlere Position der Spur in Grad (S/W negativ)."""
    la, lo = [], []
    for h, a in s.items():
        (aa, ab), (oa, ob) = satz[h][2]
        la.append(-(aa + ab * a['y']))
        lo.append(-(oa + ob * a['x']))
    return float(np.mean(la)), float(np.mean(lo))


def reihe(hafen, faktor, zyklus, jahr=2026, schritt_min=10):
    """zyklus: Array (13, 2) u, v in Knoten fuer -6..+6 h -> DataFrame u, v in m/s."""
    pfad, name = hafen
    t0 = dt.datetime(jahr, 1, 1, tzinfo=dt.timezone.utc).timestamp()
    t = np.arange(t0 - 2 * 86400, t0 + 367 * 86400, 120.0)
    h = S.gezeit(pfad, name, t)
    tp, hp = S.scheitel(t, h, True)
    tl, hl = S.scheitel(t, h, False)
    hub = hp - np.interp(tp, tl, hl)
    fak = faktor(hub)
    ts = np.arange(t0, t0 + 365 * 86400, schritt_min * 60.0)
    k = np.clip(np.searchsorted(tp, ts), 1, len(tp) - 1)
    k -= (ts - tp[k - 1]) < (tp[k] - ts)
    tau = np.clip((ts - tp[k]) / 3600.0, -6, 6)
    knoten = np.arange(-6, 7)
    u = np.interp(tau, knoten, zyklus[:, 0]) * fak[k]
    v = np.interp(tau, knoten, zyklus[:, 1]) * fak[k]
    return pd.DataFrame({'u': u / MS_KN, 'v': v / MS_KN}, index=pd.to_datetime(ts, unit='s')), \
        float(np.mean(hub)), float(np.percentile(hub, 90))


def main(argv):
    kurz = argv[1]
    pdfname, hafen, faktor = HEFTE[kurz]
    saetze = kartensaetze(os.path.join(PDF, pdfname))
    heute = dt.date.today().strftime('%Y%m%d')
    zeilen, bloecke = [], []
    for si, satz in enumerate(saetze, 1):
        stunden = sorted(satz)
        print('Satz %d: Stunden %s, Seiten %s' % (si, stunden, [satz[h][0] for h in stunden]))
        for h in stunden:
            pg, mit, _, nP, nZ = satz[h]
            if len(mit) != nZ:
                print('  Seite %d: %d Zahlen, nur %d einem Pfeil zugeordnet' % (pg, nZ, len(mit)))
        for pi, s in enumerate(spuren(satz), 1):
            fehlt = [h for h in range(-6, 7) if h not in s]
            if len(fehlt) > 1 or -6 in fehlt or 6 in fehlt:
                print('  Punkt %d.%d unvollstaendig (%d Stunden) bei %s' % (si, pi, len(s), lage(satz, s)))
                continue
            lat, lon = lage(satz, s)
            z = zyklus_aus(s)
            # Plausibilitaet: groesster Richtungssprung zwischen Nachbarstunden bei kraeftigem Strom
            std = sorted(s)
            spr = 0.0
            for h0, h1 in zip(std, std[1:]):
                if min(s[h0]['v'], s[h1]['v']) >= 0.5:
                    d = abs((s[h1]['dir'] - s[h0]['dir'] + 180) % 360 - 180)
                    spr = max(spr, d)
            h0 = 0 if 0 in s else 1
            pos = 'seite %d x %.0f y %.0f' % (satz[h0][0], s[h0]['x'], s[h0]['y'])
            zeile = dict(punkt='%d.%d' % (si, pi), lat=round(lat, 4), lon=round(lon, 4),
                         vmax=max(s[h]['v'] for h in s), sprung=round(spr), fehlt=fehlt[0] if fehlt else '',
                         pdf=pos, werte=' '.join('%g@%03.0f' % (s[h]['v'], s[h]['dir']) if h in s else '-'
                                                 for h in range(-6, 7)))
            if '--nur-punkte' not in argv:
                df, hub_m, _ = reihe(hafen, faktor, z)
                r = C.analyse(df, lat, S.KONST)
                zeile.update(achse=round(r['achse'], 1), r2=round(r['r2'], 4), m2=round(r['m2'], 3),
                             s2=round(r['s2'], 3), m2_phase=round(r['konst'].get('M2', (0, 0))[1], 1),
                             mean=round(r['mean'], 3), hub_mittel=round(hub_m, 2))
                bloecke.append((zeile, r))
            zeilen.append(zeile)
            print('  %s' % {k: zeile[k] for k in zeile if k != 'werte'})
    os.makedirs(HILFE, exist_ok=True)
    out = os.path.join(HILFE, 'chm_ccm_%s_%s' % (kurz, heute))
    with open(out + '.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(zeilen[0].keys()) if zeilen else ['punkt'])
        w.writeheader()
        for z in zeilen:
            w.writerow(z)
    print('->', out + '.csv', len(zeilen), 'Punkte')
    namen = NAMEN.get(kurz, {})
    txt = [block(kurz, pdfname, hafen, z, r, namen[z['punkt']]) for z, r in bloecke if z['punkt'] in namen]
    if txt:
        with open(out + '.txt', 'w', encoding='iso-8859-1') as f:
            f.write('\n\n'.join(txt) + '\n')
        print('->', out + '.txt', len(txt), 'Bloecke')


if __name__ == '__main__':
    main(sys.argv)
