import sys, re, collections, json
sys.path.insert(0, '/home/oliver/weather/py/namen_praezisierung')
import praez as Z, health_check as hc
R = hc.load_records(); adm = Z.zaehlen(R); F = {}
def kom(r):
    if r['file'] not in F: F[r['file']] = open(r['file'], encoding='iso-8859-1').read().split('\n')
    L = F[r['file']]; k = r['line']; j = k
    while j > 0 and L[j - 1].startswith('#'): j -= 1
    return {mm.group(2).strip() for l in L[j:k] for mm in [re.match(r'# (state|region|province|admin1): (.+)', l)] if mm}
uns = collections.Counter(); ch = []
SPEZ = {'Goods Island, Torres Strait': 'Goods Island (Torres Strait), Queensland, Australia',
        'Turtle Head, Torres Strait': 'Turtle Head (Torres Strait), Queensland, Australia',
        'Rangiroa, Tuamoto Atoll, French Polyneisa': 'Rangiroa (Tuamotu), French Polynesia',
        'Rocas, Atol das, Brazil': 'Atol das Rocas, Rio Grande do Norte, Brazil',
        'Marore, , Indonesia': 'Marore, Sulawesi Utara, Indonesia',
        'Kaingaroa, Chatham, Island, New Zealand': 'Kaingaroa (Chatham Island), New Zealand',
        'Owenga, Chatham, Island, New Zealand': 'Owenga (Chatham Island), New Zealand'}
for r in R:
    n2 = SPEZ.get(r['name']) or Z.neu(r['name'], kom(r), adm, uns, r['lat'], r['lon'])
    if ' (Coral Sea), Queensland, Australia' in n2:
        n2 = n2.replace(' (Coral Sea), Queensland, Australia', ', Coral Sea Islands, Australia') if r['lon'] > 147.5 else n2.replace('(Coral Sea)', '(Torres Strait)')
    if n2 != r['name']: ch.append((r['file'], r['name'], n2))
print(len(ch), collections.Counter(f for f, _, _ in ch).most_common(8))
print('zu lang', [(b, len(b)) for _, _, b in ch if len(b) > 88][:20], sum(1 for _, _, b in ch if len(b) > 88))
alle = collections.Counter((r['file'], r['name']) for r in R)
neu = collections.Counter((f, b) for f, _, b in ch)
print('Kollision', [k for k in neu if neu[k] > 1 or alle.get(k)][:10])
print('unsicher', uns.most_common(200))
json.dump(ch, open('/home/oliver/weather/py/namen_praezisierung/praez_ch.json', 'w'), ensure_ascii=False)
