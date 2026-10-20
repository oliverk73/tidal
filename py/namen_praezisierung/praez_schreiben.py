import json, subprocess, os, collections
os.chdir('/home/oliver/weather')
ch = json.load(open('/home/oliver/weather/py/namen_praezisierung/praez_ch.json'))
OLIVER = {'harmonics/classic/harmonics-2004-06-14_mod.txt', 'harmonics/ticon/harmonics_ticon4_worldwide.txt', 'harmonics/utide/harmonics_utide_tidetables.txt'}
pro = collections.defaultdict(dict)
for f, a, b in ch:
    assert pro[f].get(a, b) == b; pro[f][a] = b
def wende(text, m):
    L = text.split('\n'); n = 0
    for k, l in enumerate(L):
        if l in m and k + 1 < len(L) and not l.startswith('#'):
            L[k] = m[l]; n += 1
    return '\n'.join(L), n
for f, m in sorted(pro.items()):
    for b in m.values(): b.encode('iso-8859-1')
    w, n = wende(open(f, encoding='iso-8859-1').read(), m)
    open(f, 'w', encoding='iso-8859-1', newline='').write(w)
    if f in OLIVER:
        h, nh = wende(subprocess.run(['git', 'show', 'HEAD:' + f], capture_output=True).stdout.decode('iso-8859-1'), m)
        blob = subprocess.run(['git', 'hash-object', '-w', '--stdin'], input=h.encode('iso-8859-1'), capture_output=True).stdout.decode().strip()
        subprocess.run(['git', 'update-index', '--cacheinfo', '100644,%s,%s' % (blob, f)], check=True)
    else:
        nh = n; subprocess.run(['git', 'add', f], check=True)
    print('%-60s %4d Namen, Arbeitskopie %d, gestaged %d' % (f, len(m), n, nh))
