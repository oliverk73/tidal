"""Namens-Sonderfaelle (Oliver 21.10.2026): Doppelklammern, falsche Endungen, (n)/(expired)-Endungen.

Usage: venv/bin/python py/namen_praezisierung/sonderfaelle.py [--schreiben]
Olivers Dateien mit offenen Aenderungen werden auf HEAD-Basis gestaged (nur diese Namenszeilen).
"""
import os, re, sys, subprocess, collections
sys.path.insert(0, '/home/oliver/weather/py')
os.chdir('/home/oliver/weather')
import health_check as hc

OLIVER = {'harmonics/classic/harmonics-2004-06-14_mod.txt', 'harmonics/ticon/harmonics_ticon4_worldwide.txt',
          'harmonics/utide/harmonics_utide_tidetables.txt'}
HAND = {
    'Red Sea, West off Mokha Current': 'Mokha (west off, Red Sea), Yemen Current',
    'Al Ghallan / Al Tok Island Current': 'Al Ghallan / Al Tok Island, United Arab Emirates Current',
    'Sajin (Chongjin), North Kore': 'Sajin (Chongjin), North Korea',
    'Calshot Harbour (Edinburgh of the Seven Seas), Tristan da Cunha Island': 'Calshot Harbour (Edinburgh of the Seven Seas), Tristan da Cunha',
    'Pointe-Noire, Congo': 'Pointe-Noire, Republic of the Congo',
    "M'Bour Senegal": "M'Bour, Senegal",
    'Inikoi Island (Akwayafe River,) Cameroon': 'Inikoi Island (Akwayafe River), Cameroon',
    'Mururoa Atoll, Tuamotu Archipelago': 'Mururoa Atoll (Tuamotu), French Polynesia',
    'Makemo Atoll, Tuamotu Archipelago': 'Makemo Atoll (Tuamotu), French Polynesia',
    'Baha Honda Harbor (Bridge) Florida Current': 'Bahia Honda Harbor (Bridge), Florida Current',
    'Kaunakakai, Molokai (Hawaii)': 'Kaunakakai (Molokai), Hawaii',
    'Kihei, Maui (Hawaii)': 'Kihei (Maui), Hawaii',
    'Lower Hell Gate (Knubble Bay, Maine) Current': 'Lower Hell Gate (Knubble Bay), Maine Current',
    'Upper Hell Gate (Sasanoa River, Maine) Current': 'Upper Hell Gate (Sasanoa River), Maine Current',
    'Salisbury, Maryland (2 miles below) Current': 'Salisbury (2 miles below), Maryland Current',
    'Tanapag Harbor, Saipan Island, Marianas': 'Tanapag Harbor (Saipan), Northern Mariana Islands',
    'Chuuk (Moen Island, E. Caroline Islands), FSM': 'Chuuk (Moen Island), Micronesia',
    'Moen Island (Truk Islands), FSM': 'Moen Island (Chuuk), Micronesia',
    'Pohnpei C (Caroline Islands), Confederated States of Micronesia': 'Pohnpei C, Micronesia',
    'Washington (Potomac River), DC': 'Washington (Potomac River), District of Columbia',
    'Nieuwe Waterweg, Netherlands, Current': 'Nieuwe Waterweg, Netherlands Current',
    'Vlissingen, Netherlands, Current': 'Vlissingen, Netherlands Current',
    'Apia, Samoa Islands': 'Apia, Samoa',
    'Baie de Matavai, Tahiti': 'Baie de Matavai (Tahiti), French Polynesia',
    'Rikitea (Mangareva), Gambier Islands': 'Rikitea (Mangareva), French Polynesia',
    'La Peniche du Mascaret, Dordogne, France (bore arrival)': 'La Peniche du Mascaret (Dordogne, bore arrival), France',
    'Leava, Île Futuna': 'Leava (Futuna), Wallis and Futuna',
    'Mata Utu, Wallis': 'Mata Utu (Wallis), Wallis and Futuna',
    'Gustavia, Saint Barthelemy': 'Gustavia, Saint Barthélemy',
    'Active Pass (British Columbia) Current': 'Active Pass, British Columbia, Canada Current',
    'Burrard Inlet (First Narrows) Current': 'Burrard Inlet (First Narrows), British Columbia, Canada Current',
    'Seymour Narrows (Discovery Passage) Current': 'Seymour Narrows (Discovery Passage), British Columbia, Canada Current',
    'Changjiang Entrance Current': 'Changjiang Entrance, Shanghai, China Current',
    'Wusong Kou (Huangpu Entrance) Current': 'Wusong Kou (Huangpu Entrance), Shanghai, China Current',
}
SUF = re.compile(r'^(.*?)\s*\((\d+|expired[^)]*|use with caution)\)((?:\s*\((?:expired[^)]*)\))?)\s*$')


def doppel(name):
    """Aufeinanderfolgende Klammern im Teil vor dem ersten Komma zusammenlegen."""
    kopf, sep, rest = name.partition(', ')
    neu = kopf
    while re.search(r'\(([^()]*)\)\s*\(([^()]*)\)', neu):
        neu = re.sub(r'\(([^()]*)\)\s*\(([^()]*)\)', r'(\1, \2)', neu, count=1)
    return neu + sep + rest


def plan():
    R = hc.load_records()
    alle = collections.Counter(r['name'] for r in R)
    m, notiz, offen = {}, {}, []
    for r in R:
        n = r['name']
        neu = HAND.get(n, n)
        s = SUF.match(neu)
        if s:
            ohne = s.group(1)
            if re.search(r'\(\d+\)$', ohne):
                ohne = re.sub(r'\s*\(\d+\)$', '', ohne)
            zus = re.findall(r'\((expired[^)]*|use with caution)\)', neu)
            if alle.get(ohne, 0) and ohne != n:
                offen.append((n, r['file']))
            else:
                neu = ohne
                if zus:
                    notiz[(r['file'], n)] = '# note: 20261021 NOAA marked these predictions "%s" (formerly in the name)' % zus[0]
        neu = doppel(neu)
        if neu != n:
            m[(r['file'], n)] = neu
    neue = collections.Counter((f, b) for (f, a), b in m.items())
    for (f, a), b in m.items():
        assert neue[(f, b)] == 1 and not any(r['name'] == b and r['file'] == f for r in R if r['name'] != a), (f, b)
        assert len(b) <= 88, b
    return m, notiz, offen


def wende(text, datei, m, notiz):
    L = text.split('\n'); n = 0
    for k in range(len(L) - 1, -1, -1):
        l = L[k]
        if (datei, l) in m and k + 1 < len(L) and hc.MERIDIAN.match(L[k + 1]):
            if (datei, l) in notiz:
                L.insert(k, notiz[(datei, l)])
                k += 1
            L[k] = m[(datei, l)]; n += 1
    return '\n'.join(L), n


def main(argv):
    m, notiz, offen = plan()
    pro = collections.defaultdict(dict)
    for (f, a), b in m.items():
        pro[f][(f, a)] = b
    for (f, a), b in sorted(m.items()):
        print('%-28s %s  ->  %s' % (f.split('/')[-1][:28], a, b))
    for n, f in offen:
        print('OFFEN (Zwilling vorhanden):', n, f)
    print(len(m), 'Namen')
    if '--schreiben' not in argv:
        return
    for f, mm in pro.items():
        w, n = wende(open(f, encoding='iso-8859-1').read(), f, mm, notiz)
        for b in mm.values():
            b.encode('iso-8859-1')
        open(f, 'w', encoding='iso-8859-1', newline='').write(w)
        if f in OLIVER:
            h, nh = wende(subprocess.run(['git', 'show', 'HEAD:' + f], capture_output=True).stdout.decode('iso-8859-1'), f, mm, notiz)
            blob = subprocess.run(['git', 'hash-object', '-w', '--stdin'], input=h.encode('iso-8859-1'), capture_output=True).stdout.decode().strip()
            subprocess.run(['git', 'update-index', '--cacheinfo', '100644,%s,%s' % (blob, f)], check=True)
        else:
            nh = n; subprocess.run(['git', 'add', f], check=True)
        print(f, n, 'geschrieben,', nh, 'gestaged')
    with open('/tmp/claude-1000/-home-oliver/5927e01d-bfab-4a06-9761-a582fa5c417c/scratchpad/sonder_namen.txt', 'w', encoding='utf-8') as fh:
        for (f, a), b in m.items():
            fh.write(a + '\n' + b + '\n')


if __name__ == '__main__':
    main(sys.argv[1:])
