#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DHN Peru (Dirección de Hidrografía y Navegación) Tide-Table-Downloader.

Der DHN-Webdienst https://www.dhn.mil.pe/portal/pdf-tabla-marea/<HAFEN>
generiert pro Aufruf eine PDF-Tafel des LAUFENDEN Monats (HW/LW, lokale Zeit
UTC-5). Es gibt KEINEN Monats-/Jahresparameter — um Juli/August zu bekommen,
muss dieses Skript im Juli bzw. August laufen (siehe Cron unten).

Speichert nach ~/tide_tables/peru/<YYYY-MM>/Tabla de mareas <hafen>.pdf,
so dass sich Monate akkumulieren (für spätere UTide-TC-Fits über mehrere Monate).
Idempotent: bereits valide vorhandene Dateien werden übersprungen.

Cron (2. jedes Monats, nachdem der Server umgestellt hat):
  0 7 2 * * /usr/bin/python3 /home/oliver/py/download_dhn_peru.py \
      >> /home/oliver/tide_tables/peru/download.log 2>&1
"""
import os, re, sys, time, zlib
from datetime import datetime
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

BASE = "https://www.dhn.mil.pe/portal/pdf-tabla-marea/"
OUTROOT = os.path.expanduser("~/tide_tables/peru")
UA = "Mozilla/5.0 (X11; Linux x86_64) tide-harvester/1.0"

# Alle DHN-Häfen (Klarnamen wie auf der Karte; URL = Großbuchstaben, URL-kodiert)
PORTS = [
    "Ancon", "Atico", "Bayovar", "Cabo Blanco", "Caleta Grau", "Callao",
    "Cerro Azul", "Chala", "Chancay", "Chimbote", "Eten", "Huacho", "Huarmey",
    "Ilo", "Lobitos", "Lobos de Afuera", "Malabrigo", "Matarani", "Melchorita",
    "Paita", "Pisco", "Salaverry", "San Juan", "Supe", "Talara", "Zorritos",
]

MES = {1: "ENE", 2: "FEB", 3: "MAR", 4: "ABR", 5: "MAY", 6: "JUN",
       7: "JUL", 8: "AGO", 9: "SEP", 10: "OCT", 11: "NOV", 12: "DIC"}


def pdf_month(data):
    """(mon_str, year) des ersten Datums in der PDF, oder None.

    Streams werden exakt über /Length extrahiert — NICHT per find('endstream'),
    da der komprimierte Inhalt zufaellig die Bytes 'endstream' enthalten kann
    (z. B. Salaverry) und sonst zu frueh abgeschnitten wuerde.
    """
    out = []
    for m in re.finditer(rb"/Length\s+(\d+)\s*>>\s*stream\r?\n", data):
        ln = int(m.group(1)); s = m.end()
        try:
            out.append(zlib.decompress(data[s:s + ln]))
        except zlib.error:
            e = data.find(b"endstream", s)
            try:
                out.append(zlib.decompress(data[s:e].rstrip(b"\r\n")))
            except zlib.error:
                pass
    c = b"".join(out).decode("latin-1", "replace")
    m = re.search(r"(\d{2})\s+([A-Z]{3})\.?\s+(\d{4})", c)
    return (m.group(2), int(m.group(3))) if m else None


def valid_pdf(path, expect_mon, expect_year):
    try:
        data = open(path, "rb").read()
    except OSError:
        return False
    if not data.startswith(b"%PDF") or len(data) < 1500:
        return False
    pm = pdf_month(data)
    return pm == (MES[expect_mon], expect_year)


def fetch(port, retries=3):
    url = BASE + quote(port.upper())
    for i in range(retries):
        try:
            req = Request(url, headers={"User-Agent": UA})
            with urlopen(req, timeout=60) as r:
                return r.read()
        except (URLError, HTTPError) as ex:
            if i == retries - 1:
                raise
            time.sleep(3 * (i + 1))


def main():
    now = datetime.now()
    outdir = os.path.join(OUTROOT, f"{now.year}-{now.month:02d}")
    os.makedirs(outdir, exist_ok=True)
    print(f"=== DHN Peru download {now:%Y-%m-%d %H:%M} -> {outdir} ===")
    ok = skip = fail = 0
    for port in PORTS:
        dest = os.path.join(outdir, f"Tabla de mareas {port.lower()}.pdf")
        if valid_pdf(dest, now.month, now.year):
            print(f"  skip  {port} (bereits valide)"); skip += 1
            continue
        try:
            data = fetch(port)
        except Exception as ex:
            print(f"  FAIL  {port}: {ex}"); fail += 1
            continue
        if not data.startswith(b"%PDF") or len(data) < 1500:
            print(f"  FAIL  {port}: kein PDF ({len(data)} B)"); fail += 1
            continue
        pm = pdf_month(data)
        if pm != (MES[now.month], now.year):
            print(f"  WARN  {port}: Monat {pm} != erwartet "
                  f"{(MES[now.month], now.year)} — trotzdem gespeichert")
        with open(dest, "wb") as f:
            f.write(data)
        print(f"  ok    {port} ({len(data)} B, {pm})"); ok += 1
        time.sleep(1)
    print(f"=== fertig: {ok} neu, {skip} übersprungen, {fail} fehlgeschlagen ===")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
