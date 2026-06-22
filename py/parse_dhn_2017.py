#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Parser fuer DHN Peru TABLA DE MAREAS 2017 (HIDRONAV-5023, Jahres-Tafel).

Layout (verifiziert): Datenseiten ab PDF-Index 15. Pro Hafen 5 Seiten:
4 Datenseiten (je 3 Monate) + 1 kurze Zusatzseite. Jede Datenseite hat 6
Spaltenbloecke = 3 Monate x 2 Tageshaelften (1-15 / 16-31). Pro Block:
Dia (Tagnr) | Hora (HHMM) | cm. Dia steht auf y-Hoehe des ersten Tageseintrags.

Liefert parse_2017(pdf) -> dict port_lower -> list[(datetime_UTC, hoehe_m)].
Lokalzeit (Peru UTC-5) + 5h -> UTC. Hoehe cm/100.
"""
import fitz
import re
from datetime import datetime, timedelta

# Hafenreihenfolge = Contenido. PDF-Datenstart S15, je 5 Seiten/Hafen.
PORTS_ORDER = [
    'zorritos', 'cabo blanco', 'lobitos', 'talara', 'paita', 'bayovar',
    'lobos de afuera', 'eten', 'malabrigo', 'salaverry', 'chimbote', 'huarmey',
    'supe', 'huacho', 'chancay', 'ancon', 'callao', 'cerro azul', 'pisco',
    'san juan', 'atico', 'matarani', 'ilo',
]
PDF_START = 15
PAGES_PER_PORT = 5

# 6 Spaltenbloecke: (dia_x_center, hora_x_center, cm_x_center). Toleranz +/-12px.
# Bloecke: M0a M0b | M1a M1b | M2a M2b  (a=Tage1-15, b=16-31)
BLOCKS = [
    (50, 67, 91),    # Monat0 Haelfte a
    (112, 134, 157), # Monat0 Haelfte b
    (183, 200, 224), # Monat1 a
    (246, 267, 291), # Monat1 b
    (317, 334, 358), # Monat2 a
    (379, 400, 424), # Monat2 b
]
XTOL = 14


def _near(x, cx):
    return abs(x - cx) < XTOL


def parse_page(page, months):
    """months = (m_a, m_b, m_c) die 3 Monatsnummern dieser Seite.
    -> list[(month, day, hhmm, cm)]."""
    words = page.get_text("words")  # (x0,y0,x1,y1,text,...)
    toks = [(w[0], w[1], w[4]) for w in words if re.fullmatch(r'-?\d{1,4}', w[4])]
    out = []
    for bi, (dx, hx, cx) in enumerate(BLOCKS):
        month = months[bi // 2]
        if month is None:
            continue
        # Dia-Marker dieses Blocks: 1-31, x~dx
        dias = sorted([(y, int(t)) for x, y, t in toks
                       if _near(x, dx) and 1 <= int(t) <= 31], key=lambda a: a[0])
        # Hora-Tokens (4-stellig 0000-2359) x~hx
        horas = sorted([(y, t) for x, y, t in toks
                        if _near(x, hx) and re.fullmatch(r'\d{3,4}', t)
                        and int(t) < 2400 and int(t[-2:]) < 60], key=lambda a: a[0])
        # cm-Tokens x~cx
        cms = sorted([(y, int(t)) for x, y, t in toks
                      if _near(x, cx) and -50 <= int(t) <= 400], key=lambda a: a[0])
        if not dias or not horas:
            continue

        def day_for(y):
            d = None
            for dy, dval in dias:
                if dy <= y + 3:
                    d = dval
                else:
                    break
            return d
        # paare Hora mit naechstgelegenem cm (gleiche y-Zeile, |dy|<4)
        for hy, ht in horas:
            best = None
            for cy, cv in cms:
                if abs(cy - hy) < 4:
                    best = cv
                    break
            if best is None:
                continue
            day = day_for(hy)
            if day is None:
                continue
            hh = int(ht[:-2]) if len(ht) > 2 else 0
            mm = int(ht[-2:])
            if hh > 23 or mm > 59:
                continue
            out.append((month, day, hh, mm, best))
    return out


def parse_2017(pdf_path):
    doc = fitz.open(pdf_path)
    res = {}
    for pi, port in enumerate(PORTS_ORDER):
        base = PDF_START + pi * PAGES_PER_PORT
        ser = []
        for k in range(4):  # 4 Datenseiten = Monate (1-3),(4-6),(7-9),(10-12)
            pageno = base + k
            if pageno >= doc.page_count:
                break
            months = (k * 3 + 1, k * 3 + 2, k * 3 + 3)
            for month, day, hh, mm, cm in parse_page(doc[pageno], months):
                try:
                    loc = datetime(2017, month, day, hh, mm)
                except ValueError:
                    continue
                ser.append((loc + timedelta(hours=5), cm / 100.0))  # -> UTC
        # dedup + sort
        ser = sorted(set(ser))
        res[port] = ser
    doc.close()
    return res


if __name__ == '__main__':
    import sys
    pdf = sys.argv[1] if len(sys.argv) > 1 else \
        '/mnt/c/Users/Ihr Benutzerkonto/Downloads/389867163-Tabla-Mareas-2017.pdf'
    data = parse_2017(pdf)
    print(f"{'Hafen':18s} {'n':>5} {'Bereich':>22} {'h_min':>6}{'h_max':>6}")
    for p, s in data.items():
        if not s:
            print(f"{p:18s}  LEER"); continue
        hs = [h for _, h in s]
        print(f"{p:18s} {len(s):>5} {str(s[0][0])[:10]}..{str(s[-1][0])[:10]} "
              f"{min(hs):6.2f}{max(hs):6.2f}")
