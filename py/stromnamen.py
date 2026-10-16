#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Einheitliche Schreibweise fuer Stroemungsnamen (Klammer-Regel).

Oliver 16.10.2026: Die NOAA-Namen mischen "0.3 n.mi. east of", "2.35nm NNE of", "0.5 mi. S of"
und Abkuerzungen wie "Ft. Sumter" oder "Fire I. Inlet", die bei Google Maps schlecht zu finden
sind. Hier: Entfernungen immer "mi" (die NOAA-Stromtafeln rechnen in Seemeilen), Richtungen vor
"of" als Kompasskuerzel, Ortsabkuerzungen ausgeschrieben, Kontext in die Klammer.

  klammer("Pond Point, 7.6 miles SSE of") -> "Pond Point (7.6 mi SSE of)"
"""
import re

RICHTUNG = {'north': 'N', 'south': 'S', 'east': 'E', 'west': 'W', 'northeast': 'NE', 'northwest': 'NW',
            'southeast': 'SE', 'southwest': 'SW'}
ZAHL = r'(?:\d+|One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|Eleven|Twelve|Thirteen|Fourteen|Fifteen|Sixteen|Eighteen|Twenty)'
ABK = [(r'\bEaster Ch\.', 'Eastern Channel'), (r'\b(%s) Ft\.' % ZAHL, r'\1 Foot'),
       (r'\b([NSEW])\.(?=\s+of\b)', r'\1'), (r'\bN\.(?=\s[A-Z])', 'North'), (r'\bS\.(?=\s[A-Z])', 'South'),
       (r'\bPt\b\.?', 'Point'), (r'\bPts\.', 'Points'), (r'\bFt\.', 'Fort'), (r'\bIs?\.(?=[\s,)\-]|$)', 'Island'),
       (r'\bLt\.', 'Light'), (r'\bMt\.', 'Mount'), (r'\bHbr\.', 'Harbor'), (r'\b[Ee]ntr?\.', 'Entrance'),
       (r'\b[Cc]h(?:an)?\.', 'Channel'), (r'\bBr\.', 'Bridge'), (r'\bBkwtr\.', 'Breakwater'), (r'\bJct\.', 'Junction'),
       (r'\bR\.(?=\s[A-Z])', 'River'), (r'\bR\.?(?=\)|,|$)', 'River'), (r'\bRiv\.', 'River'), (r'\bCr\.', 'Creek'),
       (r'\b[Hh]wy\.', 'Highway'), (r'\bRR\.', 'Railroad'), (r'\bAve\.', 'Avenue'), (r'\bDel\. City', 'Delaware City'),
       (r'\bExt\.', 'Extension'), (r'\b(\d+) (?:yds?\.?|yards?)(?=[\s,)]|$)', r'\1 yd')]


def kurz(t):
    """Entfernungen, Richtungen und Abkuerzungen vereinheitlichen."""
    t = re.sub(r'(\d[\d.]*)\s*(?:nautical miles?|n\.\s?mi\.?|nmi\.?|nm\.?|miles?\.?|mi\.?)(?=[\s,)]|$)',
               lambda m: m.group(1).rstrip('.') + ' mi', t)
    t = re.sub(r'\b(north|south|east|west|northeast|northwest|southeast|southwest)\b(?=\s+of\b)',
               lambda m: RICHTUNG[m.group(1).lower()], t, flags=re.I)
    for a, b in ABK:
        t = re.sub(a, b, t)
    return re.sub(r'\s+', ' ', t).strip()


def klammer(n, zusatz=None):
    """"Pond Point, 7.6 miles SSE of" -> "Pond Point (7.6 mi SSE of)"; vorhandene Klammer bleibt Kontext."""
    teile = [kurz(t) for t in re.sub(r'\s+', ' ', n).split(',')]
    vorn, ctx = teile[0], [t for t in teile[1:] if t]
    m = re.match(r'^(.*?)\s*\((.*)\)$', vorn)
    if m and ctx:
        vorn, ctx = m.group(1), [m.group(2)] + ctx
    if zusatz:
        ctx.append(zusatz)
    return '%s (%s)' % (vorn, ', '.join(ctx)) if ctx else vorn
