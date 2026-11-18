import json, os, time, urllib.request, urllib.error
UA = {'User-Agent': 'weather-tides/1.0 (private tidal harmonics research)'}
ZIEL = 'tide_tables/germany_bsh'
BOX = 'https://filebox.bsh.de/index.php/s/SbJ3z5NBkpOZloY/download'
def hole(url, pfad):
    if os.path.exists(pfad) and os.path.getsize(pfad) > 1000:
        return 'da'
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
            daten = r.read()
    except urllib.error.HTTPError as e:
        return str(e.code)
    open(pfad, 'wb').write(daten)
    time.sleep(1.0)
    return 'neu'
orte = json.load(open(f'{ZIEL}/json/tides_overview.json'))
orte = orte if isinstance(orte, list) else next(v for v in orte.values() if isinstance(v, list))
kurven = 0
for o in orte:
    nr = o['bshnr']; name = nr.rjust(5, '_')
    s = hole(f'https://gezeiten.bsh.de/data/DE_{name}_tides.json', f'{ZIEL}/json/DE_{name}_tides.json')
    info = ''
    try:
        d = json.load(open(f'{ZIEL}/json/DE_{name}_tides.json'))
        for y in d.get('years', []):
            for jahr, v in y.items():
                if v.get('has_curve'):
                    k = hole(f'{BOX}?path=/vb_kurv/deu{jahr}&files=DE__{nr}{jahr}.txt', f'{ZIEL}/kurve/DE__{nr}{jahr}.txt')
                    info += f' Kurve{jahr}:{k}'; kurven += 1
    except Exception as e:
        info = f' JSON unlesbar ({e})'
    print(f"{nr:6} {o['station_name'][:34]:34} JSON:{s}{info}", flush=True)
print('FERTIG', len(orte), 'Orte,', kurven, 'Kurven')
