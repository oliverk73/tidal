"""Synoptic-Zeitreihen Wind Mai-Sep 2026 laden: quellen/thermik/synoptic/<stid>.json"""
import json, os, sys, time, requests
Q = os.path.dirname(os.path.abspath(__file__))
TOK = open(os.path.expanduser("~/.config/synoptic_token")).read().strip().strip('"')
os.makedirs(os.path.join(Q, "synoptic"), exist_ok=True)
for stid in sys.argv[1].split(","):
    pfad = os.path.join(Q, "synoptic", stid + ".json")
    if os.path.exists(pfad):
        continue
    teile = []
    for a, b in (("202605010000", "202606302359"), ("202607010000", "202608312359"), ("202609010000", "202610010100")):
        r = requests.get("https://api.synopticdata.com/v2/stations/timeseries", timeout=300, params=dict(
            token=TOK, stid=stid, start=a, end=b, vars="wind_speed,wind_direction", units="english,speed|kts",
            obtimezone="UTC")).json()
        if r["SUMMARY"]["RESPONSE_CODE"] != 1:
            print(stid, r["SUMMARY"]["RESPONSE_MESSAGE"]); continue
        teile.append(r["STATION"][0])
        time.sleep(0.5)
    if teile:
        json.dump(teile, open(pfad, "w"))
        n = sum(len(t["OBSERVATIONS"]["date_time"]) for t in teile)
        print(stid, teile[0]["NAME"], teile[0]["LATITUDE"], teile[0]["LONGITUDE"], n, flush=True)
