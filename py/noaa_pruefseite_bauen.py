#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Baut aus dem Probelauf eine Pruefseite, auf der sich entscheiden laesst.

Oliver 16.09.2026: "Die Spalte begruendung ist kaum lesbar, weil ich immer
nach links und rechts scrollen muss." Eine CSV mit 1122 Zeilen und einem
Fliesstext je Zeile ist zum Archivieren gut und zum Arbeiten unbrauchbar.

Diese Seite zeigt links die Faelle, rechts den ganzen Nachweis zu einem
Fall, und die Entscheidung faellt mit einem Klick oder einer Taste. Die
Entscheidungen landen in der Artifact-Datenbank (Sammlung
"entscheidungen", ein Dokument je Fall); Claude liest sie von dort und
baut damit die Loeschliste (py/noaa_loeschliste_bauen.py).

Veroeffentlicht am 16.09.2026 als https://claude.ai/artifact/PkthD9CMHbFAAKrFB32ses

Gelesen werden:
  harmonics/help/noaa_guete_probelauf.csv        die Faelle
  harmonics/help/noaa_widerspruch_messreihen.csv die Messproben dazu

Usage: python3 py/noaa_pruefseite_bauen.py [--aus <datei.html>]
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import ROOT                                       # noqa: E402

HELP = os.path.join(ROOT, 'harmonics/help')
QUELLE = os.path.join(HELP, 'noaa_guete_probelauf.csv')
MESSUNG = os.path.join(HELP, 'noaa_widerspruch_messreihen.csv')
SCHWELLEN = os.path.join(HELP, 'noaa_guete_schwellen.json')
LISTEN = ['loeschen:schlecht', 'loeschen:neben_A', 'loeschen:widerspruch',
          'pruefen:stunde', 'bleibt:A_verdaechtig']
KURZ = {'loeschen:schlecht': 'Klar schlecht', 'loeschen:neben_A': 'Dublette neben A',
        'loeschen:widerspruch': 'Widerspruch', 'pruefen:stunde': 'Glatte Stunde',
        'bleibt:A_verdaechtig': 'A verdaechtig'}
VORGABE = {'loeschen:schlecht': 'loeschen', 'loeschen:neben_A': 'loeschen',
           'loeschen:widerspruch': 'loeschen', 'pruefen:stunde': '',
           'bleibt:A_verdaechtig': ''}
BAND = {'harmonics_noaa_eutt.txt': 'eutt', 'harmonics_noaa_amtt.txt': 'amtt',
        'harmonics_noaa_cptt.txt': 'cptt', 'harmonics_noaa_carib.txt': 'carib',
        'harmonics_noaa_censam.txt': 'censam', 'harmonics_noaa_pacif.txt': 'pacif'}


def kennung(z):
    """Stabile Dokumentkennung: erlaubt sind Buchstaben, Ziffern und _-.~:@+."""
    if z['uid']:
        return z['uid']
    roh = BAND.get(z['datei'], z['datei'][:6]) + '_' + z['name']
    return re.sub(r'[^A-Za-z0-9_.~:@+-]+', '_', roh)[:180]


def land(name):
    teile = [t.strip() for t in name.split(',') if t.strip()]
    return teile[-1] if len(teile) > 1 else '--'


def befund(z, tab):
    """Der Satz, der die Einstufung wirklich traegt -- mit den Zahlen, die sie trug.

    Die Spalten abw_pct/schwelle_pct sind Mediane ueber alle A-Orte und taugen
    nicht als Begruendung: Bei Acapulco standen 23.7 % gegen 34.7 %, was nach
    "in Ordnung" aussah, waehrend in Wahrheit der Schiedsrichter entschied
    (NOAA 24 % gegen die Zeugen, der A-Satz 1 %).
    """
    nah = sorted((t for t in tab if float(t['km']) <= 3.0), key=lambda t: float(t['pct']))
    n = nah[0] if nah else None
    if z['liste'] == 'loeschen:neben_A' and n:
        return (f"Dieselbe Tide wie \"{n['ort']}\" ({n['km']} km): {n['pct']} % Unterschied, "
                f"erlaubt sind dort {n['p90']} %. Beide Saetze sagen dasselbe, aber der A-Satz "
                f"hat gemessene Konstanten und die NOAA-Zeile nur Zeit- und Hubdifferenzen aus dem Buch.")
    if z['liste'] == 'loeschen:schlecht' and z['schieds_orte']:
        return (f"Unabhaengige Nachbarpegel entscheiden: {z['schieds_orte']}. Von denen weicht die "
                f"NOAA-Uebertragung um {z['schieds_noaa']} % ab, der Klasse-A-Satz nur um {z['schieds_a']} %. "
                f"Die Nachbarschaft sagt also dasselbe wie der A-Satz.")
    if z['liste'] == 'loeschen:schlecht':
        return (f"{z['a_orte']} Klasse-A-Orte bis 25 km sind sich einig und widersprechen dem Satz alle; "
                f"selbst im guenstigsten Vergleich ({z['e_ort']}, {z['e_km']} km) bleiben {z['e_pct']} % "
                f"gegen erlaubte {z['e_p90']} %.")
    if z['liste'] == 'loeschen:widerspruch' and n:
        stark = float(n['pct']) > float(n['p95'])
        kopf = (f"\"{n['ort']}\" liegt {n['km']} km entfernt und sagt deutlich etwas anderes: "
                if stark else f"\"{n['ort']}\" liegt {n['km']} km entfernt und weicht ab: ")
        schluss = ('Kein unabhaengiger Nachbarpegel in der Naehe, der einen der beiden stuetzen koennte'
                   + '; der Versatz ist keine glatte Stunde. Geloescht wird die Uebertragung, weil am '
                     'selben Ort gemessene Konstanten stehen.')
        return (kopf + f"{n['pct']} % Unterschied, normal waeren dort {n['p90']} %, "
                f"Ausreissergrenze {n['p95']} %. " + schluss)
    if z['liste'] == 'pruefen:stunde' and n:
        return (f"Zeitversatz {z['zeit_min']} min bei fast gleicher Amplitude (Faktor {z['massstab']}) "
                f"gegen \"{n['ort']}\" ({n['km']} km, {n['pct']} % Unterschied). Das ist das Bild eines "
                f"Zonenfehlers -- nur ist offen, welcher der beiden Saetze in der falschen Zone steht.")
    if z['liste'] == 'bleibt:A_verdaechtig':
        return (f"Hier steht der A-Satz in Frage: Von den unabhaengigen Nachbarpegeln ({z['schieds_orte']}) "
                f"weicht der NOAA-Satz nur um {z['schieds_noaa']} % ab, der A-Satz um {z['schieds_a']} %. "
                f"Der Satz, der die Uebertragung ersetzen wuerde, passt schlechter ins Umfeld als sie selbst.")
    return (f"Guenstigster Vergleich: {z['e_pct']} % gegen \"{z['e_ort']}\" ({z['e_km']} km), "
            f"erlaubt sind dort {z['e_p90']} %.")


def kurzbefund(z, t):
    """Ein Satz, der in eine Zeile passt -- die Kacheln tragen die Zahlen."""
    if z['liste'] == 'loeschen:neben_A':
        # Zwei Wege fuehren in diese Liste: klar innerhalb des Grundrauschens,
        # oder knapp darueber und von einem zweiten gemessenen Satz gestuetzt.
        # Der zweite Fall sah bisher aus wie der erste (Vollerwiek Plate:
        # 20 % gegen 18.9 % -- roter Balken, Text "sagt dasselbe").
        if t and float(t['pct']) > float(t['p90']):
            return (f"Etwas ueber der ueblichen Schwelle ({t['pct']} statt {t['p90']} %), aber unter der "
                    f"Ausreissergrenze -- und ein zweiter gemessener Satz stuetzt den Nachbarn.")
        return 'Sagt dasselbe wie der gemessene Satz nebenan.'
    if z['liste'] == 'loeschen:schlecht':
        return 'Die Nachbarschaft stuetzt den gemessenen Satz, nicht die Uebertragung.'
    if z['liste'] == 'loeschen:widerspruch':
        return 'Weicht vom gemessenen Satz am selben Ort ab; kein Zeuge klaert, wer recht hat.'
    if z['liste'] == 'pruefen:stunde':
        return f"Zeitversatz {z['zeit_min']} min bei gleicher Amplitude: Zonenfehler -- bei wem?"
    if z['liste'] == 'bleibt:A_verdaechtig':
        return 'Die Nachbarschaft stuetzt die Uebertragung, nicht den gemessenen Satz.'
    return ''


def faelle():
    mess = {}
    if os.path.exists(MESSUNG):
        for m in csv.DictReader(open(MESSUNG, encoding='utf-8')):
            mess.setdefault(m['noaa'], []).append(m)
    out = []
    for z in csv.DictReader(open(QUELLE, encoding='utf-8')):
        if z['liste'] not in LISTEN:
            continue
        f = dict(id=kennung(z), liste=z['liste'], datei=z['datei'], name=z['name'],
                 land=land(z['name']), lat=z['lat'], lon=z['lon'],
                 abw=z['abw_pct'], schwelle=z['schwelle_pct'],
                 e_ort=z['e_ort'], e_datei=z['e_datei'], e_km=z['e_km'], e_pct=z['e_pct'],
                 e_p90=z['e_p90'], e_p95=z['e_p95'],
                 tabelle=[dict(zip(('ort', 'km', 'pct', 'p90', 'p95', 'quelle', 'lat', 'lon'), t.split('|')))
                          for t in z['a_tabelle'].split(';') if t],
                 zeugen_tab=[dict(zip(('ort', 'km', 'pct_noaa', 'pct_a', 'quelle', 'lat', 'lon'), t.split('|')))
                             for t in z['schieds_tabelle'].split(';') if t],
                 karte=json.loads(z['karte']) if z['karte'] else None,
                 a_quelle=z['naechster_a_quelle'],
                 a_name=z['naechster_a'], a_datei=z['naechster_a_datei'],
                 a_km=z['naechster_a_km'], a_orte=z['a_orte'], a_einig=z['a_einig'],
                 zeit=z['zeit_min'], massstab=z['massstab'], zeugen=z['a_zeugen'],
                 schieds=z['schiedsrichter'], schieds_orte=z['schieds_orte'],
                 schieds_noaa=z['schieds_noaa'], schieds_a=z['schieds_a'], hinweis=z['name_hinweis'],
                 vorgabe=VORGABE[z['liste']])
        f['befund'] = befund(z, f['tabelle'])
        nah = sorted((t for t in f['tabelle'] if float(t['km']) <= 3.0), key=lambda t: float(t['pct']))
        t = nah[0] if nah else dict(ort=z['e_ort'], km=z['e_km'], pct=z['e_pct'],
                                    p90=z['e_p90'], p95=z['e_p95'])
        f.update(n_ort=t['ort'], n_km=t['km'], n_pct=t['pct'], n_p90=t['p90'], n_p95=t['p95'])
        f['kurz'] = kurzbefund(z, t)
        f['messung'] = [dict(reihe=m['reihe'], km=m['reihe_km'], jahr=m['jahr'],
                             rms_noaa=m['rms_noaa'], rms_a=m['rms_a'],
                             zeit_noaa=m['zeit_noaa'], zeit_a=m['zeit_a'],
                             urteil=m['urteil']) for m in mess.get(z['name'], [])]
        out.append(f)
    return out


SEITE = r'''<title>NOAA-Aufraeumliste</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Serif:wght@600&display=swap">
<style>
:root{
  --grund:#eef1f0; --flaeche:#ffffff; --flaeche2:#f6f8f7; --tinte:#14211f; --leise:#5b706c;
  --linie:#d3dcd9; --linie2:#e6ecea; --akzent:#1d5c7a; --akzent-w:#e3eef3;
  --weg:#a3402b; --weg-w:#f6e7e3; --bleibt:#2d6a4d; --bleibt-w:#e2efe8;
  --warn:#8a6216; --warn-w:#f7eeda; --schatten:0 1px 2px rgba(16,40,36,.09);
}
@media (prefers-color-scheme: dark){ :root:not([data-theme="light"]){
  --grund:#0e1518; --flaeche:#151d21; --flaeche2:#1a2328; --tinte:#e2eae8; --leise:#94a7a3;
  --linie:#28353a; --linie2:#1f2a2f; --akzent:#79b6d3; --akzent-w:#17323f;
  --weg:#e08a72; --weg-w:#3a211a; --bleibt:#7ec49d; --bleibt-w:#172c22;
  --warn:#d8ac54; --warn-w:#312611; --schatten:0 1px 2px rgba(0,0,0,.4);
} }
:root[data-theme="dark"]{
  --grund:#0e1518; --flaeche:#151d21; --flaeche2:#1a2328; --tinte:#e2eae8; --leise:#94a7a3;
  --linie:#28353a; --linie2:#1f2a2f; --akzent:#79b6d3; --akzent-w:#17323f;
  --weg:#e08a72; --weg-w:#3a211a; --bleibt:#7ec49d; --bleibt-w:#172c22;
  --warn:#d8ac54; --warn-w:#312611; --schatten:0 1px 2px rgba(0,0,0,.4);
}
*{box-sizing:border-box}
body{margin:0;background:var(--grund);color:var(--tinte);
  font:15px/1.5 "IBM Plex Sans",system-ui,sans-serif;-webkit-font-smoothing:antialiased}
h1,h2,h3{margin:0;text-wrap:balance}
button{font:inherit;color:inherit}
.rahmen{max-width:1480px;margin:0 auto;padding-inline:16px;padding-block:16px 26px}
header{display:flex;flex-wrap:wrap;gap:8px 20px;align-items:baseline;justify-content:space-between}
h1{font-family:"IBM Plex Serif",Georgia,serif;font-size:23px;font-weight:600}
header p{margin:0;color:var(--leise);font-size:13px}
.speicher{font:12px/1 "IBM Plex Mono",ui-monospace,monospace;color:var(--leise);
  border:1px solid var(--linie);border-radius:999px;padding:6px 11px;white-space:nowrap}
.speicher.an{color:var(--bleibt);border-color:var(--bleibt)}
.speicher.aus{color:var(--warn);border-color:var(--warn)}

.listen{display:flex;flex-wrap:wrap;gap:6px;margin-top:14px}
.karte{flex:1 1 150px;min-width:132px;text-align:left;background:var(--flaeche);border:1px solid var(--linie);
  border-left:3px solid var(--linie);border-radius:3px;padding:8px 11px;cursor:pointer}
.karte[aria-pressed="true"]{border-color:var(--akzent);border-left-color:var(--akzent);background:var(--akzent-w)}
.karte .n{font:600 19px/1.1 "IBM Plex Mono",ui-monospace,monospace;font-variant-numeric:tabular-nums}
.karte .t{font-size:12px;color:var(--leise);margin-top:2px}
.karte .rest{font-size:11px;color:var(--leise);margin-top:4px;font-variant-numeric:tabular-nums}
.karte.w{border-left-color:var(--weg)} .karte.p{border-left-color:var(--warn)}

.werkzeug{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:12px 0 10px}
input[type=search],select{font:inherit;font-size:14px;background:var(--flaeche);color:var(--tinte);
  border:1px solid var(--linie);border-radius:3px;padding:7px 9px;min-width:0}
input[type=search]{flex:1 1 200px}
.schalter{display:flex;align-items:center;gap:6px;font-size:13px;color:var(--leise)}
.sammelknopf{border:1px solid var(--linie);background:var(--flaeche);border-radius:3px;padding:7px 12px;
  font-size:13px;cursor:pointer}
.sammelknopf:hover{border-color:var(--weg);color:var(--weg)}
.fortschritt{flex:1 1 180px;display:flex;align-items:center;gap:8px;font-size:12px;color:var(--leise)}
.balken{flex:1;height:5px;background:var(--linie2);border-radius:999px;overflow:hidden}
.balken i{display:block;height:100%;background:var(--akzent)}

.werkbank{display:grid;grid-template-columns:minmax(0,340px) minmax(0,1fr);gap:12px;align-items:start}
@media (max-width:860px){.werkbank{grid-template-columns:1fr}}
.tafel{background:var(--flaeche);border:1px solid var(--linie);border-radius:4px;box-shadow:var(--schatten)}
.liste{max-height:min(72vh,780px);overflow-y:auto}
.zeile{display:grid;grid-template-columns:7px minmax(0,1fr) 92px;gap:8px;align-items:center;width:100%;
  text-align:left;background:none;border:0;border-bottom:1px solid var(--linie2);padding:7px 10px 7px 7px;cursor:pointer}
.zeile:hover{background:var(--flaeche2)}
.zeile[aria-current="true"]{background:var(--akzent-w)}
.punkt{width:7px;height:7px;border-radius:999px;background:var(--linie);justify-self:center}
.punkt.weg{background:var(--weg)} .punkt.bleibt{background:var(--bleibt)}
.zeile .nm{font-size:13.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:block}
.zeile .sub{font-size:11px;color:var(--leise);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:block}
.mini{display:flex;align-items:center;gap:6px;justify-content:flex-end}
.minibalken{width:40px;height:5px;border-radius:999px;background:var(--linie2);overflow:hidden}
.minibalken i{display:block;height:100%}
.zeile .pz{font:500 12.5px/1 "IBM Plex Mono",ui-monospace,monospace;font-variant-numeric:tabular-nums}

.detail{padding:16px 18px 18px}
.kopfzeile{display:flex;flex-wrap:wrap;gap:8px 12px;align-items:baseline;justify-content:space-between}
.detail h2{font-family:"IBM Plex Serif",Georgia,serif;font-size:21px;font-weight:600}
.ort{font:12px/1.5 "IBM Plex Mono",ui-monospace,monospace;color:var(--leise);margin-top:3px}
.ort a{color:var(--akzent)}
.marke{display:inline-block;font-size:11px;letter-spacing:.06em;text-transform:uppercase;
  border:1px solid var(--linie);border-radius:3px;padding:2px 7px;color:var(--leise);white-space:nowrap}
.marke.w{color:var(--weg);border-color:var(--weg);background:var(--weg-w)}
.marke.p{color:var(--warn);border-color:var(--warn);background:var(--warn-w)}
.kurz{margin:12px 0 0;font-size:15.5px;line-height:1.45;max-width:60ch}

.kacheln{display:grid;grid-template-columns:repeat(auto-fit,minmax(168px,1fr));gap:8px;margin-top:14px}
.kachel{border:1px solid var(--linie);border-radius:3px;padding:10px 12px;background:var(--flaeche2)}
.kachel .k{font-size:10.5px;text-transform:uppercase;letter-spacing:.07em;color:var(--leise)}
.kachel .v{font:600 20px/1.2 "IBM Plex Mono",ui-monospace,monospace;font-variant-numeric:tabular-nums;margin-top:5px}
.kachel .v.klein{font-size:15px;font-family:"IBM Plex Sans",sans-serif;font-weight:600}
.kachel .s{font-size:11.5px;color:var(--leise);margin-top:3px;font-variant-numeric:tabular-nums}
.kachel .c{font-size:11px;color:var(--leise);margin-top:7px;line-height:1.35;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.duellbox{margin-top:8px;display:grid;gap:4px}
.duell{display:grid;grid-template-columns:46px minmax(0,1fr) 54px;gap:7px;align-items:center;font-size:11.5px}
.duell .dl{color:var(--leise)}
.duell .dbalken{height:7px;border-radius:999px;background:var(--linie2);overflow:hidden}
.duell .dbalken i{display:block;height:100%}
.duell .dv{font:500 12px/1 "IBM Plex Mono",ui-monospace,monospace;font-variant-numeric:tabular-nums;text-align:right}
.kachel.rot{border-color:var(--weg);background:var(--weg-w)}
.kachel.gruen{border-color:var(--bleibt);background:var(--bleibt-w)}
.spur{height:6px;border-radius:999px;background:var(--linie2);overflow:hidden;margin-top:8px;position:relative}
.spur i{display:block;height:100%}
.spur b{position:absolute;top:-3px;width:2px;height:12px;background:var(--tinte);opacity:.65}
.rot-t{color:var(--weg)} .gruen-t{color:var(--bleibt)}

.entscheidung{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}
.knopf{border:1px solid var(--linie);background:var(--flaeche);border-radius:3px;padding:10px 16px;cursor:pointer;
  font-size:14.5px;display:inline-flex;gap:8px;align-items:center}
.knopf:hover{border-color:var(--akzent)}
.knopf kbd{font:11px/1 "IBM Plex Mono",monospace;border:1px solid var(--linie);border-radius:2px;padding:2px 4px;color:var(--leise)}
.knopf.weg[aria-pressed="true"]{background:var(--weg-w);border-color:var(--weg);color:var(--weg)}
.knopf.bleibt[aria-pressed="true"]{background:var(--bleibt-w);border-color:var(--bleibt);color:var(--bleibt)}
.vorgabe{font-size:12px;color:var(--leise);margin-top:8px}

details.mehr{margin-top:14px;border-top:1px solid var(--linie2);padding-top:10px;font-size:13.5px}
details.mehr summary{cursor:pointer;color:var(--akzent);font-size:13px}
dl{display:grid;grid-template-columns:auto minmax(0,1fr);gap:6px 14px;margin:10px 0 0;font-size:13.5px}
dt{color:var(--leise);white-space:nowrap} dd{margin:0;font-variant-numeric:tabular-nums}
.atab{width:100%;border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums;margin-top:10px}
.atab th{font-weight:500;color:var(--leise);text-align:right;padding:5px 9px;font-size:11px;
  text-transform:uppercase;letter-spacing:.05em;border-bottom:1px solid var(--linie2)}
.atab th:first-child,.atab td:first-child{text-align:left}
.atab td{padding:5px 9px;border-bottom:1px solid var(--linie2);text-align:right}
.atab tr:last-child td{border-bottom:0}
.atab td.q{color:var(--leise);font-size:12px;text-align:left}
.kartenbox{margin-top:14px;border:1px solid var(--linie);border-radius:3px;overflow:hidden;background:var(--flaeche2)}
.kartenbox canvas{display:block;width:100%;max-width:100%}
.kartenlegende{margin:0;padding:7px 11px;font-size:11.5px;color:var(--leise);border-top:1px solid var(--linie2)}
.pkt{display:inline-block;width:9px;height:9px;border-radius:999px;vertical-align:-1px}
.pkt.noaa{background:var(--weg)} .pkt.a{background:var(--bleibt)} .pkt.z{background:var(--leise)}
.notiz{width:100%;margin-top:10px;font:inherit;font-size:13.5px;background:var(--flaeche2);color:var(--tinte);
  border:1px solid var(--linie);border-radius:3px;padding:8px 9px;resize:vertical;min-height:46px}
.leer{padding:26px 18px;color:var(--leise);font-size:13.5px}
.hilfe{margin-top:12px;font-size:12px;color:var(--leise)}
.hilfe kbd{font:11px/1 "IBM Plex Mono",monospace;border:1px solid var(--linie);border-radius:2px;padding:2px 4px}
details.erklaerung{margin-top:14px;font-size:13px;color:var(--leise)}
details.erklaerung summary{cursor:pointer;color:var(--akzent)}
details.erklaerung table{border-collapse:collapse;margin-top:9px;font-variant-numeric:tabular-nums}
details.erklaerung th,details.erklaerung td{padding:4px 12px 4px 0;text-align:right;font-weight:400}
details.erklaerung th:first-child,details.erklaerung td:first-child{text-align:left}
:focus-visible{outline:2px solid var(--akzent);outline-offset:2px}
</style>

<div class="rahmen">
<header>
  <div>
    <h1>NOAA-Aufraeumliste</h1>
    <p>Uebertragungen aus den NOAA-Tafeln (Table 2) ausserhalb der USA, gemessen am gemessenen Satz nebenan.</p>
  </div>
  <div class="speicher" id="speicher">Speicher wird verbunden ...</div>
</header>

<div class="listen" id="listen"></div>

<div class="werkzeug">
  <input type="search" id="suche" placeholder="Name, Land oder Nachbarsatz" aria-label="Suchen">
  <select id="landwahl" aria-label="Land"></select>
  <label class="schalter"><input type="checkbox" id="nuroffen"> nur unentschiedene</label>
  <button class="sammelknopf" id="sammel">Alle sichtbaren loeschen</button>
  <div class="fortschritt"><span id="fortschrifttext">0 von 0</span>
    <span class="balken"><i id="balken" style="width:0%"></i></span></div>
</div>

<div class="werkbank">
  <div class="tafel"><div class="liste" id="liste"></div></div>
  <div class="tafel"><div class="detail" id="detail"></div></div>
</div>

<details class="erklaerung">
  <summary>Woher die Schwellen kommen</summary>
  <p>Zwei gute Saetze sind nie gleich: verschiedene Punkte, verschiedene Jahrzehnte, verschiedene Aemter.
     Wieviel das ausmacht, ist nicht geschaetzt, sondern an allen Paaren von Klasse-A-Saetzen im Bestand
     gemessen &mdash; getrennt nach Abstand.</p>
  __SCHWELLEN__
  <p>Klasse A heisst: gemessene Konstanten oder durchgehende amtliche Vorhersagen (eigene UTide-Fits auf
     Pegelreihen, TICON, die Harmonic-Constants-Teile der Admiralty Tide Tables, Puertos del Estado, die
     alten XTide-Bestaende). NOAA Table 2 gehoert nicht dazu: Zeit- und Hubdifferenzen auf einen
     Bezugshafen, keine eigene Messung.</p>
</details>

<p class="hilfe"><kbd>j</kbd>/<kbd>k</kbd> bewegen, <kbd>l</kbd> loeschen, <kbd>b</kbd> behalten,
  <kbd>u</kbd> zuruecknehmen. Alles wird sofort gespeichert.</p>
</div>

<script id="daten" type="application/json">__DATEN__</script>
<script>
const FAELLE = JSON.parse(document.getElementById('daten').textContent);
const KURZ = __KURZ__;
const ART = {'loeschen:schlecht':'w','loeschen:neben_A':'w','loeschen:widerspruch':'w',
             'pruefen:stunde':'p','bleibt:A_verdaechtig':'p'};
const stand = new Map();
let db = null, gewaehlt = null, filterListe = null;

function dz(v){ return String(v == null ? '' : v).replace('.', ','); }
function hesc(s){ return String(s == null ? '' : s).replace(/[&<>"]/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function lokal(){ try{ return JSON.parse(localStorage.getItem('noaa_entscheidungen')||'{}'); }catch(e){ return {}; } }
function lokalSchreiben(){
  try{ const o={}; stand.forEach((v,k)=>o[k]=v); localStorage.setItem('noaa_entscheidungen', JSON.stringify(o)); }catch(e){}
}
function status(text, art){
  const el = document.getElementById('speicher');
  el.textContent = text; el.className = 'speicher' + (art ? ' '+art : '');
}
async function speicherStarten(){
  try { db = await window.claude?.use?.('db'); } catch(e){ db = null; }
  if (!db){ status('nur in diesem Browser gespeichert', 'aus'); return; }
  try {
    const snap = await db.collection('entscheidungen').get();
    snap.docs.forEach(d => { const v = d.data(); if (v && v.entscheidung !== undefined)
      stand.set(d.id, {entscheidung: v.entscheidung, notiz: v.notiz || ''}); });
    status('gespeichert', 'an'); zeichnen();
  } catch(e){ status('Speicher nicht erreichbar', 'aus'); }
}
async function merken(id, wert){
  stand.set(id, wert); lokalSchreiben();
  if (!db) return;
  try { await db.collection('entscheidungen').doc(id).set(
    {entscheidung: wert.entscheidung, notiz: wert.notiz || '', zeit: new Date().toISOString()}); }
  catch(e){ status('nicht gespeichert: ' + ((e && e.code) || 'Fehler'), 'aus'); }
}

function gefiltert(){
  const q = document.getElementById('suche').value.trim().toLowerCase();
  const l = document.getElementById('landwahl').value;
  const offen = document.getElementById('nuroffen').checked;
  return FAELLE.filter(f => {
    if (filterListe && f.liste !== filterListe) return false;
    if (l && f.land !== l) return false;
    if (offen && stand.has(f.id)) return false;
    if (q && !(f.name + ' ' + f.land + ' ' + f.n_ort).toLowerCase().includes(q)) return false;
    return true;
  });
}
function entscheidungVon(f){ return (stand.get(f.id) || {}).entscheidung || ''; }
function ueber(f){ return (+f.n_pct) > (+f.n_p90); }

function karten(){
  const box = document.getElementById('listen'); box.innerHTML = '';
  [...new Set(FAELLE.map(f => f.liste))].forEach(l => {
    const alle = FAELLE.filter(f => f.liste === l);
    const off = alle.filter(f => !stand.has(f.id)).length;
    const b = document.createElement('button');
    b.className = 'karte ' + (ART[l] || '');
    b.setAttribute('aria-pressed', String(filterListe === l));
    b.innerHTML = '<div class="n">' + alle.length + '</div><div class="t">' + KURZ[l] +
      '</div><div class="rest">' + off + ' offen</div>';
    b.onclick = () => { filterListe = (filterListe === l ? null : l); zeichnen(); };
    box.appendChild(b);
  });
}

function zeilen(){
  const box = document.getElementById('liste'); const liste = gefiltert(); box.innerHTML = '';
  if (!liste.length){ box.innerHTML = '<p class="leer">Kein Fall passt zu diesen Filtern.</p>'; return; }
  const frag = document.createDocumentFragment();
  liste.forEach(f => {
    const e = entscheidungVon(f), rot = ueber(f);
    const breite = Math.max(4, Math.min(100, 100 * (+f.n_pct) / Math.max(1, 2 * (+f.n_p90))));
    const b = document.createElement('button');
    b.className = 'zeile'; b.setAttribute('aria-current', String(gewaehlt === f.id));
    b.innerHTML = '<span class="punkt ' + (e === 'loeschen' ? 'weg' : e === 'behalten' ? 'bleibt' : '') + '"></span>' +
      '<span><span class="nm">' + hesc(f.name) + '</span><span class="sub">' +
      dz(f.n_km) + ' km zu ' + hesc(f.n_ort) + '</span></span>' +
      '<span class="mini"><span class="minibalken"><i style="width:' + breite + '%;background:' +
      (rot ? 'var(--weg)' : 'var(--bleibt)') + '"></i></span>' +
      '<span class="pz">' + f.n_pct + '%</span></span>';
    b.onclick = () => { gewaehlt = f.id; zeichnen(); };
    frag.appendChild(b);
  });
  box.appendChild(frag);
  const aktiv = box.querySelector('[aria-current="true"]');
  if (aktiv) aktiv.scrollIntoView({block:'nearest'});
}

function quelleVon(f){
  const t = (f.tabelle || []).find(x => x.ort === f.n_ort);
  return (t && t.quelle) || f.a_quelle || '';
}

function messurteil(f){
  const m = (f.messung || []).filter(x => x.urteil !== 'blind (Satz aus dieser Reihe gefittet)');
  if (!m.length) return {kachel: kachel('Pegelreihe',
    (f.messung || []).length ? 'blind' : '--', '',
    (f.messung || []).length ? 'Satz stammt aus dieser Reihe' : 'keine Reihe in der Naehe', '', '', true)};
  const b = m[0];
  const art = b.urteil === 'A besser' ? 'rot' : b.urteil === 'NOAA besser' ? 'gruen' : '';
  return {kachel: kachel('Pegelreihe: Fehler gegen die Messung', b.urteil, '', hesc(b.reihe), art,
    duell('NOAA', b.rms_noaa, 'A-Satz', b.rms_a, ' m', true), true)};
}

// Zwei Werte als Balkenpaar -- das ist auf einen Blick zu sehen, der Satz
// "Von denen weicht die NOAA-Uebertragung um 40.2 % ab, der Klasse-A-Satz
// nur um 18.2 %" war es nicht (Oliver, 16.09.2026).
function duell(l1, v1, l2, v2, einheit, kleinerBesser){
  const a = Math.abs(+v1), b = Math.abs(+v2), max = Math.max(a, b, 0.0001);
  const zeile = (l, v, breit, schlecht) =>
    '<div class="duell"><span class="dl">' + l + '</span>' +
    '<span class="dbalken"><i style="width:' + Math.max(3, 100 * breit / max) + '%;background:' +
    (schlecht ? 'var(--weg)' : 'var(--bleibt)') + '"></i></span>' +
    '<span class="dv">' + v + einheit + '</span></div>';
  return '<div class="duellbox">' + zeile(l1, dz(v1), a, kleinerBesser ? a > b : a < b) +
         zeile(l2, dz(v2), b, kleinerBesser ? b > a : b < a) + '</div>';
}

function detail(){
  const box = document.getElementById('detail');
  const f = FAELLE.find(x => x.id === gewaehlt);
  if (!f){ box.innerHTML = '<p class="leer">Waehle links einen Fall.</p>'; return; }
  const e = entscheidungVon(f), st = stand.get(f.id) || {}, rot = ueber(f);
  const osm = 'https://www.openstreetmap.org/?mlat=' + f.lat + '&mlon=' + f.lon + '#map=13/' + f.lat + '/' + f.lon;
  const grenze = Math.max(1, 2 * (+f.n_p90));
  const breite = Math.max(3, Math.min(100, 100 * (+f.n_pct) / grenze));
  const marke = Math.min(100, 100 * (+f.n_p90) / grenze);
  const mu = messurteil(f);
  const nachbar = f.schieds_orte
    ? {kachel: kachel('Nachbarpegel: Unterschied zu ihnen',
        (+f.schieds_noaa) > (+f.schieds_a) ? 'stuetzen den A-Satz' : 'stuetzen NOAA', '',
        f.schieds_orte.split(';').map(x => hesc(x.trim())).join(' &middot; '),
        (+f.schieds_noaa) > (+f.schieds_a) ? 'rot' : 'gruen',
        duell('NOAA', f.schieds_noaa, 'A-Satz', f.schieds_a, ' %', true), true)}
    : {kachel: kachel('Nachbarpegel', 'kein Urteil', '',
        f.a_orte + ' Klasse-A-Ort(e), keine unabhaengigen Zeugen', '', '', true)};

  let html = '<div class="kopfzeile"><div><h2>' + hesc(f.name) + '</h2>' +
    '<div class="ort">' + f.lat + ', ' + f.lon + ' &middot; ' + hesc(f.datei) +
    ' &middot; <a href="' + osm + '" target="_blank" rel="noreferrer">Karte</a></div></div>' +
    '<span class="marke ' + (ART[f.liste]||'') + '">' + KURZ[f.liste] + '</span></div>' +
    '<p class="kurz">' + hesc(f.kurz) + '</p><div class="kacheln">' +
    kachel('Unterschied', dz(f.n_pct) + ' %', 'ueblich bis ' + dz(f.n_p90) + ' %, aeusserstenfalls ' + dz(f.n_p95) + ' %',
      hesc(f.n_ort), rot ? 'rot' : 'gruen',
      '<div class="spur"><i style="width:' + breite + '%;background:' + (rot ? 'var(--weg)' : 'var(--bleibt)') +
      '"></i><b style="left:' + marke + '%"></b></div>') +
    kachel('Gemessener Satz', (+f.n_km) < 0.05 ? 'gleicher Punkt' : dz(f.n_km) + ' km',
      hesc(quelleVon(f)), hesc(f.n_ort), '') +
    nachbar.kachel + mu.kachel +
    '</div>';

  html += '<div class="entscheidung">' +
    '<button class="knopf weg" id="kweg" aria-pressed="' + (e === 'loeschen') + '">Loeschen <kbd>l</kbd></button>' +
    '<button class="knopf bleibt" id="kbleibt" aria-pressed="' + (e === 'behalten') + '">Behalten <kbd>b</kbd></button>' +
    '<button class="knopf" id="kzurueck">Zuruecknehmen <kbd>u</kbd></button></div>' +
    '<div class="vorgabe">Ohne Entscheidung gilt: ' +
    (f.vorgabe === 'loeschen' ? 'loeschen (Vorschlag dieser Liste)' : 'behalten') + '</div>';

  if (f.karte){
    html += '<div class="kartenbox"><canvas id="karte" width="620" height="300"></canvas>' +
      '<p class="kartenlegende"><span class="pkt noaa"></span> NOAA-Satz &nbsp; ' +
      '<span class="pkt a"></span> gemessene Saetze &nbsp; <span class="pkt z"></span> Nachbarpegel ' +
      '&nbsp;&middot;&nbsp; Kueste aus der Landmaske (~1 km), keine Flussarme</p></div>';
  }
  html += '<details class="mehr"><summary>Alle Vergleiche und Einzelheiten</summary>' +
    '<p style="margin:10px 0 0;max-width:62ch">' + hesc(f.befund) + '</p>';
  if (f.tabelle && f.tabelle.length){
    html += '<table class="atab"><thead><tr><th>Klasse-A-Satz</th><th>Abstand</th><th>Unterschied</th>' +
      '<th>ueblich bis</th><th>aeusserstenfalls</th></tr></thead><tbody>';
    f.tabelle.forEach(t => { const r2 = (+t.pct) > (+t.p90);
      html += '<tr><td>' + hesc(t.ort) + '</td><td>' + t.km + ' km</td><td class="' + (r2 ? 'rot-t' : 'gruen-t') +
        '">' + dz(t.pct) + ' %</td><td>' + dz(t.p90) + ' %</td><td>' + dz(t.p95) + ' %</td></tr>'; });
    html += '</tbody></table>';
  }
  html += '<dl>';
  const z = (k, v) => { if (v) html += '<dt>' + k + '</dt><dd>' + v + '</dd>'; };
  z('Zeitversatz', f.zeit ? f.zeit + ' min' : '');
  z('Amplituden', f.massstab ? 'Faktor ' + f.massstab : '');
  z('Namenshinweis', hesc(f.hinweis));
  (f.messung || []).forEach(m => z('Reihe ' + hesc(m.reihe),
    m.km + ' km, ' + m.jahr + ': NOAA ' + m.rms_noaa + ' m (' + m.zeit_noaa + ' min), A ' + m.rms_a +
    ' m (' + m.zeit_a + ' min) &rarr; ' + hesc(m.urteil)));
  html += '</dl></details>' +
    '<textarea class="notiz" id="notiz" placeholder="Notiz zu diesem Fall">' + hesc(st.notiz || '') + '</textarea>';
  box.innerHTML = html;
  document.getElementById('kweg').onclick = () => setzen('loeschen');
  document.getElementById('kbleibt').onclick = () => setzen('behalten');
  document.getElementById('kzurueck').onclick = () => setzen('');
  if (f.karte) karteZeichnen(f);
  const n = document.getElementById('notiz');
  let stift = null;
  n.oninput = () => { clearTimeout(stift); stift = setTimeout(() => {
    const cur = stand.get(f.id) || {entscheidung: ''};
    merken(f.id, {entscheidung: cur.entscheidung || '', notiz: n.value}); zeichnen();
  }, 700); };
}

function karteZeichnen(f){
  const c = document.getElementById('karte'); if (!c) return;
  const k = f.karte, dpr = window.devicePixelRatio || 1;
  const breite = c.parentElement.clientWidth || 620, hoehe = 300;
  c.width = breite * dpr; c.height = hoehe * dpr; c.style.width = '100%'; c.style.height = hoehe + 'px';
  const g = c.getContext('2d'); g.scale(dpr, dpr);
  const stil = getComputedStyle(document.body);
  const wasser = stil.getPropertyValue('--akzent-w') || '#e3eef3';
  const land = stil.getPropertyValue('--linie') || '#d3dcd9';
  // Bitmaske auspacken (Norden oben, Zeile fuer Zeile)
  const roh = atob(k.b); const bytes = new Uint8Array(roh.length);
  for (let i = 0; i < roh.length; i++) bytes[i] = roh.charCodeAt(i);
  const N = k.n;
  const seite = Math.min(breite, hoehe);                 // quadratischer Ausschnitt, zentriert
  const x0 = (breite - seite) / 2, y0 = (hoehe - seite) / 2, zelle = seite / N;
  g.fillStyle = wasser; g.fillRect(0, 0, breite, hoehe);
  g.fillStyle = land;
  for (let i = 0; i < N; i++) for (let j = 0; j < N; j++){
    const bit = i * N + j;
    if (bytes[bit >> 3] & (128 >> (bit & 7)))
      g.fillRect(x0 + j * zelle, y0 + i * zelle, Math.ceil(zelle), Math.ceil(zelle));
  }
  const px = (lat, lon) => [x0 + seite * (((lon - k.lon) / (2 * k.dlo)) + 0.5),
                            y0 + seite * (0.5 - ((lat - k.lat) / (2 * k.dla)))];
  const punkt = (lat, lon, farbe, gross, ring) => {
    const [x, y] = px(+lat, +lon);
    if (x < x0 - 6 || x > x0 + seite + 6 || y < y0 - 6 || y > y0 + seite + 6) return;
    g.beginPath(); g.arc(x, y, gross, 0, 2 * Math.PI);
    g.fillStyle = farbe; g.fill();
    if (ring){ g.lineWidth = 2; g.strokeStyle = farbe; g.beginPath(); g.arc(x, y, gross + 4, 0, 2 * Math.PI); g.stroke(); }
  };
  const fWeg = stil.getPropertyValue('--weg') || '#a3402b';
  const fBleibt = stil.getPropertyValue('--bleibt') || '#2d6a4d';
  const fLeise = stil.getPropertyValue('--leise') || '#5b706c';
  (f.zeugen_tab || []).forEach(t => punkt(t.lat, t.lon, fLeise, 3));
  (f.tabelle || []).forEach(t => punkt(t.lat, t.lon, fBleibt, 4.5));
  punkt(f.lat, f.lon, fWeg, 4.5, true);
  // Massstab: 5 km
  const kmPix = seite / k.km, laenge = 5 * kmPix;
  g.strokeStyle = fLeise; g.lineWidth = 1.5;
  g.beginPath(); g.moveTo(x0 + 10, y0 + seite - 12); g.lineTo(x0 + 10 + laenge, y0 + seite - 12); g.stroke();
  g.beginPath(); g.moveTo(x0 + 10, y0 + seite - 16); g.lineTo(x0 + 10, y0 + seite - 8);
  g.moveTo(x0 + 10 + laenge, y0 + seite - 16); g.lineTo(x0 + 10 + laenge, y0 + seite - 8); g.stroke();
  g.fillStyle = fLeise; g.font = '11px "IBM Plex Mono", monospace';
  g.fillText('5 km', x0 + 16 + laenge, y0 + seite - 9);
}

function kachel(titel, wert, sub, unten, art, extra, klein){
  return '<div class="kachel ' + (art || '') + '"><div class="k">' + titel + '</div>' +
    '<div class="v' + (klein ? ' klein' : '') + '">' + wert + '</div>' +
    (extra || '') + (sub ? '<div class="s">' + sub + '</div>' : '') +
    (unten ? '<div class="c">' + unten + '</div>' : '') + '</div>';
}

function setzen(wert){
  const f = FAELLE.find(x => x.id === gewaehlt); if (!f) return;
  const alt = stand.get(f.id) || {};
  if (!wert){ stand.delete(f.id); lokalSchreiben(); zeichnen();
    if (db) db.collection('entscheidungen').doc(f.id).delete().catch(() => {}); return; }
  merken(f.id, {entscheidung: wert, notiz: alt.notiz || ''});
  const liste = gefiltert();
  const i = liste.findIndex(x => x.id === f.id);
  const next = liste[i + 1] || liste.find(x => !stand.has(x.id));
  if (next) gewaehlt = next.id;
  zeichnen();
}

async function sammelLoeschen(){
  const liste = gefiltert().filter(f => !stand.has(f.id));
  if (!liste.length) return;
  if (!confirm(liste.length + ' sichtbare Faelle als "loeschen" markieren?')) return;
  document.getElementById('sammel').disabled = true;
  for (const f of liste){ await merken(f.id, {entscheidung: 'loeschen', notiz: ''}); }
  document.getElementById('sammel').disabled = false;
  zeichnen();
}

function fortschritt(){
  const n = FAELLE.length, k = FAELLE.filter(f => stand.has(f.id)).length;
  document.getElementById('fortschrifttext').textContent = k + ' von ' + n + ' entschieden';
  document.getElementById('balken').style.width = (n ? (100 * k / n) : 0) + '%';
  const offen = gefiltert().filter(f => !stand.has(f.id)).length;
  const gefiltertAktiv = !!(filterListe || document.getElementById('landwahl').value ||
                            document.getElementById('suche').value.trim());
  const b = document.getElementById('sammel');
  b.textContent = gefiltertAktiv ? 'Alle ' + offen + ' sichtbaren loeschen' : 'Sammelaktion: erst filtern';
  b.disabled = !offen || !gefiltertAktiv;
  b.title = gefiltertAktiv ? '' : 'Erst eine Liste, ein Land oder eine Suche waehlen';
}

function laender(){
  const sel = document.getElementById('landwahl'), alt = sel.value, zahl = {};
  FAELLE.forEach(f => zahl[f.land] = (zahl[f.land] || 0) + 1);
  sel.innerHTML = '<option value="">alle Laender (' + FAELLE.length + ')</option>' +
    Object.keys(zahl).sort().map(l => '<option value="' + hesc(l) + '">' + hesc(l) + ' (' + zahl[l] + ')</option>').join('');
  sel.value = alt;
}

function zeichnen(){ karten(); zeilen(); detail(); fortschritt(); }

document.addEventListener('keydown', ev => {
  if (ev.target.matches('input, textarea, select')) return;
  const liste = gefiltert(), i = liste.findIndex(x => x.id === gewaehlt);
  if (ev.key === 'j' || ev.key === 'ArrowDown'){ ev.preventDefault(); gewaehlt = (liste[i + 1] || liste[0] || {}).id; zeichnen(); }
  else if (ev.key === 'k' || ev.key === 'ArrowUp'){ ev.preventDefault(); gewaehlt = (liste[i - 1] || liste[liste.length - 1] || {}).id; zeichnen(); }
  else if (ev.key === 'l'){ setzen('loeschen'); }
  else if (ev.key === 'b'){ setzen('behalten'); }
  else if (ev.key === 'u'){ setzen(''); }
});
['suche', 'landwahl', 'nuroffen'].forEach(id =>
  document.getElementById(id).addEventListener('input', () => zeichnen()));
document.getElementById('sammel').onclick = sammelLoeschen;

Object.entries(lokal()).forEach(([k, v]) => stand.set(k, v));
gewaehlt = (FAELLE.find(f => !stand.has(f.id)) || FAELLE[0] || {}).id;
laender(); zeichnen(); speicherStarten();
</script>
'''


def schwellentabelle():
    import json
    if not os.path.exists(SCHWELLEN):
        return ''
    zeilen = json.load(open(SCHWELLEN, encoding='utf-8'))
    tr = ''.join(f"<tr><td>{z['von']:.0f}&ndash;{z['bis']:.0f} km</td><td>{z['p50']} %</td>"
                 f"<td>{z['p90']} %</td><td>{z['p95']} %</td><td>{z['paare']}</td></tr>" for z in zeilen)
    return ('<table><thead><tr><th>Abstand</th><th>Mitte</th><th>ueblich bis</th>'
            '<th>aeusserstenfalls</th><th>Paare gemessen</th></tr></thead><tbody>' + tr + '</tbody></table>')


def main(argv):
    aus = argv[argv.index('--aus') + 1] if '--aus' in argv else os.path.join(
        os.environ.get('SCRATCH', '/tmp'), 'noaa_pruefseite.html')
    daten = faelle()
    html = SEITE.replace('__DATEN__', json.dumps(daten, ensure_ascii=False)) \
                .replace('__KURZ__', json.dumps(KURZ, ensure_ascii=False)) \
                .replace('__SCHWELLEN__', schwellentabelle())
    with open(aus, 'w', encoding='utf-8') as fh:
        fh.write(html)
    print(f'{len(daten)} Faelle -> {aus} ({len(html) / 1024:.0f} kB)')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
