#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extrahiert Table-2-Zeilen (Subordinate-STROMstationen) aus den NOAA Tidal
Current Tables 2020 (acct/pcct). Zustandsmaschine: Sektions-Header (GROSS),
Referenz ('on <Name>, p.N'), Zeitmeridian. Zeilenformat:
  No Name... [depth d] lat° min' lon° min'  dtMinFlood dtFlood dtMinEbb dtEbb
  fRatio eRatio  [minF spd dir] maxF spd dir [minE spd dir] maxE spd dir
'do.'-Folgezeilen (weitere Messtiefen) werden uebersprungen.
Ausgabe: JSON-Liste mit Rohfeldern.
"""
import pypdf, re, json, sys

PDF, OUT = sys.argv[1], sys.argv[2]
PAGES = [int(x) for x in sys.argv[3].split('-')]   # pdf-Seiten from-to (1-basiert)

COORD = re.compile(r"(\d{1,2})\s*°\s*([\d.]+)[’']\s+(\d{1,3})\s*°\s*([\d.]+)[’']")
TD = re.compile(r"([+−-])(\d)\s+(\d{2})")          # +0 45 / −1 20
RATIO = re.compile(r"\b(\d\.\d)\b")
REF = re.compile(r"on\s+([A-Za-z][A-Za-z .,’'()\-&]+?),\s*p\.?\s*\d+")
MER = re.compile(r"Time meridian,?\s*(\d+)\s*°\s*([EW])")

def parse():
    r = pypdf.PdfReader(PDF)
    out = []; sec = None; ref = None; mer = None
    for i in range(PAGES[0]-1, PAGES[1]):
        try: t = r.pages[i].extract_text() or ''
        except Exception: continue
        if 'TABLE 2' not in t[:80]: continue
        for L in t.split('\n'):
            Ls = L.strip()
            m = REF.search(Ls)
            if m: ref = m.group(1).strip()
            m = MER.search(Ls)
            if m: mer = (int(m.group(1)), m.group(2))
            if re.match(r'^[A-Z][A-Z ,.’\'\-&]{4,50}$', Ls) and 'TABLE' not in Ls:
                sec = Ls.split(' on ')[0].strip()
            c = COORD.search(L)
            if not c or 'Daily predictions' in L: continue
            if Ls.startswith(('. . . do', '. . do', 'do.')): continue
            la = int(c.group(1)) + float(c.group(2))/60
            lo = int(c.group(3)) + float(c.group(4))/60
            if mer and mer[1] == 'W': lo = -lo
            pre = L[:c.start()]
            nm = re.sub(r'^\s*(\d{1,4})\s+', '', pre)
            no = re.match(r'^\s*(\d{1,4})\s', pre)
            nm = re.sub(r'[.\s]+$', '', nm).strip()
            nm = re.sub(r'\s+\d+d$', '', nm)          # Messtiefe '15d' am Namensende
            post = L[c.end():]
            tds = [f"{s}{h}:{mnt}" for s, h, mnt in TD.findall(post)]
            # Zeitdiffs in Minuten (bis zu 4: minF, F, minE, E)
            tmin = []
            for td in tds[:4]:
                sign = -1 if td[0] in '−-' else 1
                hh, mm = td[1:].split(':')
                tmin.append(sign*(int(hh)*60+int(mm)))
            rest = post
            for s, h, mnt in TD.findall(post):
                rest = rest.replace(f'{s}{h} {mnt}', ' ', 1)
            ratios = [float(x) for x in RATIO.findall(rest)]
            # maxF/maxE Speed+Richtung: 'spd DDD °'
            sd = re.findall(r'(\d{1,2}\.\d)\s+(\d{3})\s*°', post)
            out.append(dict(no=int(no.group(1)) if no else None, name=nm,
                            lat=round(la,4), lon=round(lo,4), sec=sec, ref=ref,
                            mer=mer, tdiffs=tmin, ratios=ratios[:2],
                            speeds=[(float(a),int(b)) for a,b in sd][:2],
                            pdfpage=i+1))
    return out

if __name__ == '__main__':
    rows = parse()
    json.dump(rows, open(OUT,'w'), ensure_ascii=False, indent=0)
    print(f'{len(rows)} Zeilen -> {OUT}')
    from collections import Counter
    for k,v in Counter(r['sec'] for r in rows).items(): print(f'  {v:4d} {k} (ref {next(x["ref"] for x in rows if x["sec"]==k)})')
