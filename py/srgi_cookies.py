#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Uebernimmt die Anmeldung bei srgi.big.go.id aus Firefox fuer py/srgi_pegel.py.

Die SRGI-Anmeldung hat ein reCAPTCHA; sie geschieht deshalb im Browser. Dieses
Skript kopiert danach die Cookies von srgi.big.go.id -- und nur diese -- aus
dem Firefox-Profil nach ~/.srgi_cookies (Netscape-Format, nur fuer dich lesbar).
Ausgegeben werden nur die Namen der Cookies, keine Werte.

Firefox sperrt seine Datenbank, solange er laeuft; gelesen wird eine Kopie in
/tmp, die gleich wieder geloescht wird. Die Sitzung gilt eine Stunde.

Usage: python3 py/srgi_cookies.py
"""
import glob
import os
import shutil
import sqlite3
import tempfile

profile = sorted(glob.glob(os.path.expanduser('~/.mozilla/firefox/*/cookies.sqlite')), key=os.path.getmtime)
if not profile:
    raise SystemExit('Kein Firefox-Profil gefunden.')
quelle = profile[-1]
with tempfile.TemporaryDirectory() as tmp:
    kopie = os.path.join(tmp, 'c.sqlite')
    shutil.copy(quelle, kopie)
    if os.path.exists(quelle + '-wal'):
        shutil.copy(quelle + '-wal', kopie + '-wal')
    zeilen = sqlite3.connect(kopie).execute(
        "select host, path, isSecure, expiry, name, value from moz_cookies "
        "where host like '%srgi.big.go.id'").fetchall()
ziel = os.path.expanduser('~/.srgi_cookies')
with open(ziel, 'w') as fh:
    fh.write('# Netscape HTTP Cookie File\n')
    for host, pfad, sicher, ablauf, name, wert in zeilen:
        ablauf = int(ablauf / 1000) if ablauf > 1e12 else int(ablauf)
        fh.write(f"{host}\tTRUE\t{pfad}\t{'TRUE' if sicher else 'FALSE'}\t{ablauf}\t{name}\t{wert}\n")
os.chmod(ziel, 0o600)
print('ok, Cookies:', [z[4] for z in zeilen])
