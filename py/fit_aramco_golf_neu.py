#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rechnet die 12 Aramco-Golfsaetze (Tide Tables 2026) mit Jahrestide neu.

py/fit_aramco_gulf.py (Juni 2026) liess UTide die Partialtiden selbst waehlen;
bei knapp einem Jahr Stundenwerten faellt SA dabei unter die Rayleigh-Grenze,
der jahreszeitliche Wasserstand fehlte (Rest ~9 cm). Hier wird mit derselben
Fitfunktion wie py/fit_aramco_rotes_meer.py (SA/SSA erzwungen) neu gerechnet
und nur der Zahlenteil der bestehenden Saetze ersetzt -- Name, Position und
Kopfzeilen bleiben, dazu kommt ein Vermerk.

Usage: venv/bin/python3 py/fit_aramco_golf_neu.py [--schreiben]
"""
import datetime as dt
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fit_aramco_rotes_meer as A                                    # noqa: E402
from health_check import MERIDIAN                                    # noqa: E402

A.PDF = os.path.join(A.ROOT, 'tide_tables/saudi_arabia/968249708-Arabian-Gulf-Tide-Tables-2026.pdf')
A.JAHR = 2026
# (Buchtitel im PDF, station_id_context im Bestand, lat) -- Namen im Bestand sind inzwischen
# teils umbenannt ("Zuluf Oilfield"), deshalb wird ueber die Kennung gesucht.
STA = [
    ('Abu Ali Pier', 'abu_ali_pier', "27°18'01.6"), ("Abu Sa'fah GOSP", 'abu_safah_gosp', "26°55'49.6"),
    ('Arabiyah Island', 'arabiyah_island', "27°46'43.6"), ('Berri 119', 'berri', "27°15'28.5"),
    ("Ju'aymah", 'juaymah_pier', "26°51'34.2"), ('Manifa Causeway', 'manifa_causeway', "27°36'19.7"),
    ('Marjan GOSP 1', 'marjan_gosp_1', "28°27'46.6"), ('Ras Tanura North Pier', 'ras_tanura_north_pier', "26°38'54.2"),
    ('Safaniyah GOSP 4', 'safaniya_gosp_4', "28°22'37.1"), ('Safaniyah Pier', 'safaniya_pier', "28°00'19.8"),
    ('Tanajib Pier', 'tanajib_pier', "27°46'18.6"), ('Zuluf GOSP 2', 'zuluf_gosp_2', "28°23'21.2"),
]


def dms(s):
    d, m, sec = re.match(r"(\d+)°(\d+)'([\d.]+)", s).groups()
    return int(d) + int(m) / 60 + float(sec) / 3600


def main(argv):
    import dmi_tidevand as D
    import sicher_schreiben
    from add_uhslc_harmonics import CONSTITUENTS_175
    A.STATIONEN = {n: (n, None, None, None) for n, _k, _a in STA}
    reihen = A.reihen()
    text = open(A.ZIEL, encoding='iso-8859-1').read()
    zeilen = text.split('\n')
    heute = f'{dt.date.today():%Y%m%d}'
    geaendert = 0
    for name, kennung, la in STA:
        serie = reihen.get(name, {})
        tage = len({(mo, d) for mo, d, _h in serie})
        treffer = []
        for j, l in enumerate(zeilen):
            if l.strip() == f'# station_id_context: ARAMCO-{kennung}':
                k = j + 1
                while k < len(zeilen) and zeilen[k].startswith('#'):
                    k += 1
                if k + 1 < len(zeilen) and MERIDIAN.match(zeilen[k + 1]):
                    treffer.append(k)
        if tage < 350 or len(treffer) != 1:
            print(f'{name}: {tage} Tage, {len(treffer)} Saetze im Bestand -- uebersprungen')
            continue
        f = A.fit(serie, dms(la))
        w = D.werte_aus(f['coef'])
        k = treffer[0]
        ende = k + 3
        while ende < len(zeilen) and zeilen[ende].strip() and not zeilen[ende].startswith('#'):
            ende += 1
        alt_z0 = zeilen[k + 2]
        alt_m2 = next((l.split()[1:] for l in zeilen[k + 3:ende] if l.startswith('M2 ')), ['?', '?'])
        name_im_bestand = zeilen[k]
        neu = [f"{f['z0']:.4f} meters"] + [
            f'{cn:15s} {w[cn][0]:.4f}  {w[cn][1]:.2f}' if cn in w and w[cn][0] >= 0.00005 else 'x 0 0'
            for cn, _sp in CONSTITUENTS_175]
        if len(neu) != ende - (k + 2):
            print(f'{name}: Zeilenzahl passt nicht ({len(neu)} statt {ende - k - 2}) -- uebersprungen')
            continue
        zeilen[k + 2:ende] = neu
        einf = max(j for j in range(k - 30, k) if zeilen[j].startswith('# !units:'))
        zeilen.insert(einf, f"# note: {heute} neu gefittet mit Jahrestide SA/SSA (vorher fehlte SA); "
                            f"r2={f['r2']:.4f} rms={f['rms']:.4f}m, py/fit_aramco_golf_neu.py.")
        geaendert += 1
        print(f"{name_im_bestand[:34]:34} M2 {alt_m2[0]}/{alt_m2[1]} -> {w['M2'][0]:.4f}/{w['M2'][1]:.2f}  {tage} Tage  r2={f['r2']:.4f} rms={f['rms']:.3f} m  SA={w.get('SA-IOS', (0,))[0]:.3f}  "
              f"Z0 {alt_z0.split()[0]} -> {f['z0']:.4f}")
    if '--schreiben' in argv and geaendert:
        sicher_schreiben.schreiben(A.ZIEL, '\n'.join(zeilen))
        print(f'{geaendert} Saetze geschrieben')
    elif geaendert:
        print('(nur Probe; mit --schreiben eintragen)')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
