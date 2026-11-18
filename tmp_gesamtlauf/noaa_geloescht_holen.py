"""Gelöschte NOAA-Übertragungen (eutt/amtt/cptt) aus der Git-Historie holen.

Schlüssel ist die NOAA-Nummer (noaa_uid bzw. noaa_number), damit Umbenennungen
nicht als Löschung zählen. Je Schlüssel gilt die jüngste Fassung vor dem
Verschwinden. Grund aus den Löschlisten harmonics/help/*loesch*.csv.
Schreibt tmp_gesamtlauf/noaa_geloescht/<datei> (Prüfdateien, nicht Bestand)
und tmp_gesamtlauf/noaa_geloescht.csv.
"""
import csv, glob, os, re, subprocess, sys, collections
sys.path.insert(0, 'py')
from health_check import MERIDIAN

DATEIEN = ('harmonics_noaa_eutt.txt', 'harmonics_noaa_amtt.txt', 'harmonics_noaa_cptt.txt')
AUSDIR = 'tmp_gesamtlauf/noaa_geloescht'
os.makedirs(AUSDIR, exist_ok=True)


def bloecke(text):
    """-> {schluessel: (name, blocktext)}; Block = Kommentare + Name + Meridian + Z0 + Konstituenten."""
    L = text.split('\n')
    out = {}
    for i in range(1, len(L) - 1):
        if L[i].startswith('#') or not MERIDIAN.match(L[i + 1]):
            continue
        j = i - 1
        while j >= 0 and L[j].startswith('#'):
            j -= 1
        kom = L[j + 1:i]
        # Kommentarblock beginnt beim letzten BEGIN HOT COMMENTS davor (Dateikopf ausschliessen)
        k = i + 3
        while k < len(L) and L[k] and not L[k].startswith('#') and not (k + 1 < len(L) and MERIDIAN.match(L[k + 1])):
            k += 1
        c = '\n'.join(kom)
        m = re.search(r'noaa_uid: (\S+)', c) or re.search(r'noaa_number: (\d+)', c)
        if not m or 'Table 2 transfer' not in c:
            continue
        out[m.group(1)] = (L[i], '\n'.join(kom + L[i:k]))
    return out


def gruende():
    g = {}
    for p in sorted(glob.glob('harmonics/help/*loesch*.csv')):
        try:
            for r in csv.DictReader(open(p, encoding='utf-8')):
                if 'noaa' in (r.get('datei') or ''):
                    g.setdefault((os.path.basename(r['datei']), r.get('name')),
                                 (os.path.basename(p), (r.get('begruendung') or '')))
        except (csv.Error, UnicodeDecodeError, KeyError):
            pass
    return g


G = gruende()
zeilen = []
for datei in DATEIEN:
    pfad = f'harmonics/noaa/{datei}'
    jetzt = bloecke(open(pfad, encoding='iso-8859-1').read())
    commits = subprocess.run(['git', 'log', '--format=%h %ad', '--date=short', '--', pfad],
                             capture_output=True, text=True).stdout.split('\n')
    letzte = {}
    for zeile in commits:
        if not zeile.strip():
            continue
        h, datum = zeile.split()
        roh = subprocess.run(['git', 'show', f'{h}:{pfad}'], capture_output=True).stdout.decode('iso-8859-1')
        for key, (name, block) in bloecke(roh).items():
            if key not in jetzt and key not in letzte:
                letzte[key] = (name, block, h, datum)
    bl = []
    for key, (name, block, h, datum) in letzte.items():
        quelle, grund = G.get((datei, name), ('', ''))
        art = ('Zeit/Referenz' if re.search(r'Zeitprobe|falscher Referenz|Referenz|Zeitfehler|zeitfalsch', grund)
               else 'Dublette/Guete' if grund else 'ohne Log')
        zeilen.append(dict(datei=datei, schluessel=key, name=name, letzter_commit=h, datum=datum,
                           liste=quelle, art=art, grund=grund[:200]))
        bl.append(block)
    # Kopf der aktuellen Datei + gelöschte Blöcke -> lesbare Prüfdatei
    txt = open(pfad, encoding='iso-8859-1').read().split('\n')
    kopf_ende = next(i for i in range(1, len(txt) - 1) if not txt[i].startswith('#') and MERIDIAN.match(txt[i + 1]))
    while kopf_ende > 0 and txt[kopf_ende - 1].startswith('#'):
        kopf_ende -= 1
    open(f'{AUSDIR}/{datei}', 'w', encoding='iso-8859-1').write('\n'.join(txt[:kopf_ende]) + '\n' + '\n'.join(bl) + '\n')
    print(datei, 'geloescht:', len(letzte), collections.Counter(z['art'] for z in zeilen if z['datei'] == datei))
with open('tmp_gesamtlauf/noaa_geloescht.csv', 'w', newline='', encoding='utf-8') as fh:
    w = csv.DictWriter(fh, fieldnames=list(zeilen[0].keys())); w.writeheader(); w.writerows(zeilen)
