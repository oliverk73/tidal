"""IEM-Archiv WMO-SYNOP (BUFR) je Tag laden: quellen/thermik/synop/<sid>.jsonl"""
import datetime as dt, json, os, sys, time, requests
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "synop")
STATIONEN = sys.argv[1].split(",")
t0, t1 = dt.date.fromisoformat(sys.argv[2]), dt.date.fromisoformat(sys.argv[3])
for sid in STATIONEN:
    pfad = os.path.join(D, sid + ".jsonl")
    fertig = set()
    if os.path.exists(pfad):
        fertig = {json.loads(z)["tag"] for z in open(pfad)}
    with open(pfad, "a") as fh:
        t = t0
        while t <= t1:
            if t.isoformat() not in fertig:
                for v in range(3):
                    try:
                        r = requests.get("https://mesonet.agron.iastate.edu/api/1/obhistory.json",
                                         params=dict(station=sid, network="WMO_BUFR_SRF", date=t.isoformat(), full=1), timeout=60)
                        d = r.json()["data"]
                        break
                    except Exception as e:
                        time.sleep(10); d = None
                if d is not None:
                    obs = [[x["utc_valid"], x.get("sknt"), x.get("drct"), x.get("gust")] for x in d]
                    fh.write(json.dumps(dict(tag=t.isoformat(), obs=obs)) + "\n"); fh.flush()
                time.sleep(0.3)
            t += dt.timedelta(days=1)
    print(sid, "fertig", flush=True)
