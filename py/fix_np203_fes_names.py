#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Namens-Cleanup der per build_np203_fes_gaps.py geschriebenen FES-Bloecke.
Aendert nur Kommentar- + Stationsnamenszeile (Konstituenten unangetastet).
Voellig unlesbare OCR-Namen -> ganzen Block entfernen (att_no in DROP)."""
import re, os

TXT = os.path.expanduser('~/harmonics/utide/harmonics_fes2022.txt')

# unlesbar -> Block loeschen
DROP = {'4952', '4957', '4753', '4946', '6976', '6988', '6968', '4241'}
# kuratierte Korrekturen att_no -> Name
FIX = {
    '3959': 'Rodrigues', '4146a': 'Ras al Katib', '4171': 'Ras al Madrakah',
    '4189a': 'Al Khaburah', '4199': 'Khasab', '4201': "Ras al Khaymah",
    '4266': 'Warba Spit', '4266a': 'Umm al Aish', '4269': 'Al Faw',
    '4276a': 'Khowr-e Musa Outer Platform', '4309': 'Ras al Kuh',
    '4507a': 'Isa Ghat', '4563': 'Heinze Bok (Long Island)', '4589': 'Zar Det Aw',
    '4604': 'Cleugh Passage', '4689': 'One Fathom Bank', '4690': 'Pulau Jemur',
    '4736': 'Tanjung Ayam', '4746a': 'Pulau Sambu', '4966': 'Garcia Hernandez',
    '5012': 'Musa Bay', '5018': 'Diapitan Bay', '5035': 'Santa Rita Island',
    '5048': 'Maasin', '5081': 'Dassalan Island', '5107': 'Lahad Datu',
    '5139a': 'Kuala Lawas', '6994': 'Cua Ba Lat', '4182b': 'Makalla Wabar',
    '4261a': 'Jazirat Qaruh', '4260e': 'Jazirat Umm al Maradim',
    '4170a': 'Al Lakbi', '4198': 'Khawr al Quwayy',
}

def generic(n):
    # Wort-Normalisierung
    n = re.sub(r'\b(Isiand|Istand|lsland|Islnd|Isjand)\b', 'Island', n)
    n = re.sub(r'\bPlatiorm\b', 'Platform', n)
    n = re.sub(r'\bBayo\b', 'Bay', n)
    n = re.sub(r'\bAI\b', 'Al', n)
    # Praefix-Entmaschung: "AlLakbi" -> "Al Lakbi"
    n = re.sub(r'\b(Al|El|Ras|Umm|Jazirat|Jazireh|Bandar|Tanjung|Kuala|Pulau|Selat|Teluk|Khawr)([A-Z][a-z])', r'\1 \2', n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n

def main():
    lines = open(TXT, encoding='iso-8859-1').read().split('\n')
    # Bloecke finden: '#' Trenner-Zeile; Block geht von '#' bis vor naechstem '#'
    out = []
    i = 0
    n_fix = n_drop = 0
    while i < len(lines):
        l = lines[i]
        # Blockstart erkennen: Zeile '#' gefolgt von '# <name>' ... und enthaelt '# att_no:'
        if l.strip() == '#':
            j = i + 1
            while j < len(lines) and not (lines[j].strip() == '#' and j > i+1):
                # Blockende = naechste '#'-Only-Zeile ODER Dateiende
                if lines[j].strip() == '#' :
                    break
                j += 1
            block = lines[i:j]
            att = None
            for b in block:
                m = re.match(r'#\s*att_no:\s*(\S+)', b)
                if m: att = m.group(1)
            if att and att in DROP:
                n_drop += 1; i = j; continue
            if att:
                # name lines: '# <name>' (2. Zeile) und Stationsnamenszeile (nach !latitude)
                newname = FIX.get(att)
                # aktuellen Namen aus Zeile nach !latitude holen
                cur = None; idx_name = None
                for k,b in enumerate(block):
                    if b.startswith('# !latitude:') and k+1 < len(block):
                        cur = block[k+1]; idx_name = k+1; break
                if cur is not None:
                    nn = newname if newname else generic(cur)
                    if nn != cur:
                        n_fix += 1
                        block[idx_name] = nn
                        block[1] = f'# {nn}'   # Kommentar-Kopfzeile
                out.extend(block); i = j; continue
        out.append(l); i += 1
    open(TXT, 'w', encoding='iso-8859-1').write('\n'.join(out))
    cnt = sum(1 for l in out if l.startswith('# !latitude:'))
    print(f'fixes={n_fix} dropped={n_drop}  !latitude jetzt {cnt}')

if __name__ == '__main__':
    main()
