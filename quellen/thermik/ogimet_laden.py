"""OGIMET-SYNOP-Archiv (getsynop, Rohtext AAXX) je Monat -> quellen/thermik/ogimet/<wmo>.csv (zeit_utc, kn, grad).
Fuer Stationen, die im IEM-Archiv Luecken haben (Essaouira 60220: IEM nur bis 11.06.2026). Hoeflich: 1 Abruf je Monat, 20 s Pause.
    python3 ogimet_laden.py 60220 2026-05 2026-09"""
import calendar, os, re, sys, time, requests
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ogimet")
os.makedirs(D, exist_ok=True)
stn, von, bis = sys.argv[1], sys.argv[2], sys.argv[3]
j, m = map(int, von.split("-"))
j1, m1 = map(int, bis.split("-"))
zeilen = {}
while (j, m) <= (j1, m1):
    tage = calendar.monthrange(j, m)[1]
    url = ("https://www.ogimet.com/cgi-bin/getsynop?block=%s&begin=%04d%02d010000&end=%04d%02d%02d2359"
           % (stn, j, m, j, m, tage))
    txt = requests.get(url, timeout=120).text
    n = 0
    for z in txt.splitlines():
        f = z.split(",")
        if len(f) < 7 or f[0] != stn:
            continue
        t = "%s-%s-%sT%s:%s:00Z" % tuple(f[1:6])
        g = f[6].split()
        try:
            k = g.index(stn)
        except ValueError:
            continue
        iw = g[1][4] if len(g) > 1 and len(g[1]) == 5 else "/"
        nddff = g[k + 2] if len(g) > k + 2 else ""
        if not re.fullmatch(r"[0-9/]{5}", nddff) or "/" in nddff[1:]:
            continue
        dd, ff = int(nddff[1:3]), int(nddff[3:5])
        if ff == 99 and len(g) > k + 3 and g[k + 3].startswith("00"):
            ff = int(g[k + 3][2:5])
        if iw in "01":                       # m/s -> kn
            ff = ff * 1.943844
        elif iw not in "34":
            continue
        grad = "" if dd in (0, 99) else dd * 10
        zeilen[t] = (round(ff, 2), grad)
        n += 1
    print(stn, "%04d-%02d" % (j, m), n, "Meldungen", flush=True)
    m += 1
    if m == 13:
        j, m = j + 1, 1
    time.sleep(20)
with open(os.path.join(D, stn + ".csv"), "w") as fh:
    fh.write("zeit_utc,kn,grad\n")
    for t in sorted(zeilen):
        fh.write("%s,%s,%s\n" % (t, *zeilen[t]))
print("->", os.path.join(D, stn + ".csv"), len(zeilen))
