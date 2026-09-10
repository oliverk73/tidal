#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NP208 Secondary BATCH 3 (Med/Iberien, Seiten 276-281) — APPEND-only.

Die Bestandsdatei harmonics_att_np208_secondary.txt enthaelt manuelle
Nachkorrekturen (Akzente, Klammer-Namen) und darf NICHT regeneriert werden
(feedback_edit_not_regenerate). Dieses Skript baut nur die Batch-3-Seiten
(page_276.json..page_281.json, kuratiert nach der 3-km-Regel) und haengt
fehlende Stationen an die Bestandsdatei an. Idempotent (Skip wenn Name schon da).
"""
import importlib.util, os, json, glob, re

PY=os.path.dirname(os.path.abspath(__file__))
spec=importlib.util.spec_from_file_location('S',os.path.join(PY,'build_np208_secondary.py'))
S=importlib.util.module_from_spec(spec); spec.loader.exec_module(S)
B=S.B

HARM=S.HARM
SJ=f'{HARM}/help/np208_part2_json'
OUT=f'{HARM}/att/harmonics_att_np208_secondary.txt'
PAGES=['page_276','page_277','page_278','page_279','page_280','page_281']

def load_batch3():
    # Ueber S.load_sec(): dieselbe Zeit- und Zonenbehandlung wie im Hauptbuilder
    # (Zonenwechsel nach ATT-Konvention, 10.09.2026).
    return [s for s in S.load_sec() if s['seite'][:-5] in PAGES]

def main():
    txt=open(OUT,encoding='iso-8859-1').read()
    existing=set(re.findall(r'^# !latitude:[^\n]*\n([^\n]+)',txt,re.M))
    built=[]; skipped=[]; failed=[]
    for s in load_batch3():
        rn,rr=S.bezug(s['std'])
        if not rr: failed.append((s['name'],f"kein Bezug fuer {s['std']}")); continue
        tr=B.transfer(s,rr)
        if not tr or tr['M2n']<0.02:
            failed.append((s['name'],f'Transfer M2n={tr["M2n"] if tr else "-"}')); continue
        tr['refname']=rn
        b,nm,cf=S.block(s,tr)
        if nm in existing: skipped.append(nm); continue
        built.append((b,nm,cf,tr))
    if built:
        with open(OUT,'a',encoding='iso-8859-1') as f:
            f.write('\n'.join(l for blk,_,_,_ in built for l in blk)+'\n')
    print(f'angehaengt={len(built)} | schon vorhanden={len(skipped)} | nicht baubar={len(failed)}')
    for b,nm,cf,tr in sorted(built,key=lambda x:-x[3]['M2n']):
        print(f'  conf{cf} M2={tr["M2n"]:.2f} dt={tr["dt"]*60:+.0f}min  {nm}  <- {tr["refname"]}')
    if failed:
        print('NICHT BAUBAR:')
        for n,w in failed: print(f'  {n}: {w}')
    n_total=open(OUT,encoding='iso-8859-1').read().count('# !latitude')
    print(f'Stationen gesamt in Datei: {n_total}')

if __name__=='__main__':
    main()
