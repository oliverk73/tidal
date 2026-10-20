"""Praezisierungen hinter dem ersten Komma in die Klammer vor dem ersten Komma ziehen (Oliver 20.10.2026)."""
import sys, re, collections, json, subprocess, os
sys.path.insert(0, '/home/oliver/weather/py')
os.chdir('/home/oliver/weather')
import health_check as hc

US = {'Alabama', 'Alaska', 'California', 'Connecticut', 'Delaware', 'Florida', 'Georgia', 'Hawaii', 'Louisiana', 'Maine',
      'Maryland', 'Massachusetts', 'Mississippi', 'New Hampshire', 'New Jersey', 'New York', 'North Carolina', 'Oregon',
      'Rhode Island', 'South Carolina', 'Texas', 'Virginia', 'Washington', 'District of Columbia', 'DC', 'Pennsylvania',
      'Maryland/Delaware', 'Puerto Rico'}
UK = {'England', 'Scotland', 'Wales', 'Northern Ireland'}
# haeufig an Verwaltungsstelle, aber Gewaesser/Insel
NICHT = {'Coral Sea', 'Waddenzee', 'New Britain', 'Torres Strait', 'Tasman Sea'}
AU = {'Queensland', 'Western Australia', 'Northern Territory', 'South Australia', 'Victoria', 'New South Wales', 'Tasmania', 'Australian Antarctic Territory'}
WEG = {'Fiji Islands', 'B.C.'}
# zweitletzter Teil: von Hand als Verwaltungseinheit bestaetigt (seltene Namen)
ADMIN = set(json.load(open(os.path.join(os.path.dirname(__file__), 'praez_admin.json')))) if os.path.exists(
    os.path.join(os.path.dirname(__file__), 'praez_admin.json')) else set()
TAIL = re.compile(r'^(.*?)( Current)?((?: \((?:\d+|expired[^)]*|use with caution)\))*)$')


def split(s):
    out, d, cur, i = [], 0, '', 0
    while i < len(s):
        c = s[i]
        d += (c == '(') - (c == ')')
        if d == 0 and s[i:i + 2] == ', ':
            out.append(cur); cur = ''; i += 2; continue
        cur += c; i += 1
    out.append(cur)
    return out


def flach(p):
    """'Hudson River (midchannel)' -> 'Hudson River, midchannel' (keine Klammer in der Klammer)."""
    return re.sub(r'\s*\(([^()]*)\)', r', \1', p).strip()


def zaehlen(R):
    adm = collections.Counter()
    for r in R:
        m = TAIL.match(r['name']); p = split(m.group(1))
        if len(p) >= 3 and p[-1] not in US:
            adm[(p[-1], p[-2])] += 1
    return adm


def neu(name, kom, adm, unsicher, lat=None, lon=None):
    m = TAIL.match(name)
    core, cur, tail = m.group(1), m.group(2) or '', m.group(3) or ''
    p = split(core)
    if len(p) < 3:
        return name
    last = p[-1]
    if last in US:
        prez, rest = p[1:-1], [last]
    else:
        a = p[-2]
        ist = a not in NICHT and (a in UK or a in kom or adm[(last, a)] >= 3 or a in ADMIN)
        if ist:
            prez, rest = p[1:-2], p[-2:]
        else:
            unsicher[(last, a)] += 1
            prez, rest = p[1:-1], [last]
    if last == 'Australia' and not AU & set(rest) and lat is not None:
        rest = [('Queensland' if lat > -29 and lon > 138 else 'New South Wales' if lon > 150 else '?')] + rest
    prez = [x for x in prez if x not in WEG]
    if not prez:
        neu_ = ', '.join([p[0]] + rest) + cur + tail
        return neu_
    inner = ', '.join(flach(x) for x in prez)
    head = p[0]
    head = head[:-1] + ', ' + inner + ')' if head.endswith(')') else head + ' (' + inner + ')'
    return ', '.join([head] + rest) + cur + tail
