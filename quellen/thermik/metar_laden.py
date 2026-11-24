"""IEM-ASOS/METAR-Archiv je Station fuer den ganzen Zeitraum: quellen/thermik/metar/<icao>.csv"""
import os, sys, time, requests
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "metar")
v, b = sys.argv[2], sys.argv[3]
for s in sys.argv[1].split(","):
    pfad = os.path.join(D, s + ".csv")
    if os.path.exists(pfad) and os.path.getsize(pfad) > 10000:
        continue
    for versuch in range(5):
        r = requests.get("https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py", timeout=300, params=dict(
            station=s, data=["sknt", "drct", "gust"], year1=v[:4], month1=int(v[5:7]), day1=int(v[8:]),
            year2=b[:4], month2=int(b[5:7]), day2=int(b[8:]), tz="Etc/UTC", format="onlycomma", latlon="yes",
            missing="empty", trace="empty", report_type=[3, 4]))
        if r.status_code == 200 and r.text.count("\n") > 100:
            open(pfad, "w").write(r.text)
            break
        time.sleep(30)
    print(s, r.status_code, r.text.count("\n"), flush=True)
    time.sleep(5)
