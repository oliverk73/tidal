#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Schreibt Bestandsdateien, ohne sie im Fehlerfall zu vernichten.

Zweimal an einem Tag ist dasselbe passiert: ein Werkzeug schrieb mit

    open(pfad, 'w', encoding='iso-8859-1').write(text)

und der Text enthielt ein Zeichen, das ISO-8859-1 nicht kennt -- einmal
das Makron in einem Natural-Earth-Namen, einmal das typografische
Apostroph in einem von Hand vergebenen Namen. open(...,'w') leert die
Datei SOFORT, die Ausnahme kam erst beim Schreiben, und zurueck blieben
null Bytes: harmonics_att_np203.txt, harmonics_noaa_eutt.txt und
harmonics_utide_observations.txt. Alle drei liessen sich aus der
Sicherung wiederherstellen, aber darauf soll sich niemand verlassen
muessen.

Hier wird deshalb erst in eine Nebendatei geschrieben und dann
umbenannt. os.replace ist auf demselben Dateisystem unteilbar: entweder
steht die neue Fassung da oder die alte, nie eine halbe.

Und Zeichen jenseits von ISO-8859-1 werden umgeschrieben statt zum
Abbruch zu fuehren -- "Manawatū" wird zu "Manawatu", das typografische
Apostroph zum geraden. Der Bestand ist ISO-8859-1, weil XTide das so
liest; das laesst sich nicht umgehen, nur sauber behandeln.
"""
from __future__ import annotations

import os
import unicodedata

ERSATZ = {'’': "'", '‘': "'", '“': '"', '”': '"',
          '–': '-', '—': '-', '…': '...', ' ': ' ',
          '′': "'", '″': '"', 'ʻ': "'", 'ʼ': "'"}


def latin1(s):
    """-> Fassung, die sich in ISO-8859-1 schreiben laesst."""
    try:
        s.encode('iso-8859-1')
        return s
    except (UnicodeEncodeError, AttributeError):
        pass
    for a, b in ERSATZ.items():
        s = s.replace(a, b)
    try:
        s.encode('iso-8859-1')
        return s
    except UnicodeEncodeError:
        ohne = ''.join(c for c in unicodedata.normalize('NFD', s)
                       if unicodedata.category(c) != 'Mn')
        gerade = unicodedata.normalize('NFC', ohne)
        try:
            gerade.encode('iso-8859-1')
            return gerade
        except UnicodeEncodeError:
            return gerade.encode('ascii', 'ignore').decode('ascii')


def schreiben(pfad, text, encoding='iso-8859-1'):
    """Schreibt text nach pfad -- erst daneben, dann umbenennen."""
    if encoding.lower() in ('iso-8859-1', 'latin-1', 'latin1'):
        text = latin1(text)
    neben = pfad + '.neu'
    with open(neben, 'w', encoding=encoding) as fh:
        fh.write(text)
    os.replace(neben, pfad)
