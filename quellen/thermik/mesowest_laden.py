"""MesoWest-Download-Formular (oeffentlich, 24 h je Abruf), Wind je Station: quellen/thermik/mesowest/<stn>.csv
Spalten: zeit_utc, sknt, drct. Langsam (2 s je Abruf)."""
import datetime as dt, os, re, sys, time, requests
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mesowest")
t0, t1 = dt.date.fromisoformat(sys.argv[2]), dt.date.fromisoformat(sys.argv[3])
for stn in sys.argv[1].split(","):
    pfad = os.path.join(D, stn + ".csv")
    fertig = set()
    if os.path.exists(pfad):
        fertig = {z[:10] for z in open(pfad) if z[:4].isdigit()}
    fh = open(pfad, "a")
    t = t0
    while t <= t1:
        if t.isoformat() not in fertig:
            try:
                r = requests.get("https://mesowest.utah.edu/cgi-bin/droman/station_dl_output.cgi", timeout=90, params=dict(
                    stn=stn, unit=0, time="GMT", day1=t.day, month1="%02d" % t.month, year1=t.year, hour1=23,
                    product="", output="csv"))
                txt = r.text
                if "high number of recent download attempts" in txt:   # MesoWest sperrt: abbrechen, Tag nicht abhaken
                    sys.exit("MesoWest-Formular gesperrt (zu viele Abrufe) bei %s %s" % (stn, t))
                if "PARM =" not in txt:
                    raise ValueError("keine Daten-Antwort")
                m = re.search(r"PARM = ([^\n]+)", txt)
                if m:
                    cols = [c.strip() for c in m.group(1).split(",")]
                    for z in txt[m.end():].splitlines():
                        f = [x.strip() for x in z.split(",")]
                        if len(f) != len(cols) or not f[0].isdigit():
                            continue
                        x = dict(zip(cols, f))
                        ts = dt.datetime(int(x["YEAR"]), int(x["MON"]), int(x["DAY"]), int(x["HR"]) % 24, int(x["MIN"]))
                        if int(x["HR"]) == 24:
                            ts += dt.timedelta(days=1)
                        fh.write("%s,%s,%s\n" % (ts.isoformat(), x.get("SKNT", ""), x.get("DRCT", "")))
                fh.write("%s,#tag\n" % t.isoformat())   # nur nach echter Antwort
                fh.flush()
            except Exception as e:
                print(stn, t, e, flush=True)
            time.sleep(2)
        t += dt.timedelta(days=1)
    print(stn, "fertig", flush=True)
