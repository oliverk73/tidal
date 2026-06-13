import fitz, pytesseract, re
from PIL import Image
import numpy as np

def passes(pdf):
    doc=fitz.open(pdf)
    for dpi in (4.0,5.0,6.0,3.5):
        for psm in ('6','4','11'):
            pix=doc[0].get_pixmap(matrix=fitz.Matrix(dpi,dpi)); pix.save('/tmp/_n.png')
            img=Image.open('/tmp/_n.png')
            yield img, pytesseract.image_to_data(img, config=f'--psm {psm}', output_type=pytesseract.Output.DICT), dpi

def geom(d):
    hours={}; days={}
    for i,t in enumerate(d['text']):
        cx=d['left'][i]+d['width'][i]/2; cy=d['top'][i]+d['height'][i]/2
        if re.fullmatch(r'(0[0-9]|1[0-9]|2[0-3])00',t): hours[int(t[:2])]=cx
        if hours and re.fullmatch(r'\d{1,2}',t) and 1<=int(t)<=31:
            fx=min(hours.values()); 
            if cx<fx-30: days[int(t)]=cy
    return hours,days

def ocr_grid(pdf, ndays):
    grid={}
    for img,d,dpi in passes(pdf):
        hours,days=geom(d)
        if len(hours)<20 or len(days)<10: continue
        A=np.polyfit(sorted(days),[days[k] for k in sorted(days)],1)
        hsort=sorted(hours); colx=[hours[h] for h in hsort]
        for i,t in enumerate(d['text']):
            if not re.fullmatch(r'\d\.\d\d',t): continue
            if int(d['conf'][i])<55: continue
            cx=d['left'][i]+d['width'][i]/2; cy=d['top'][i]+d['height'][i]/2
            h=int(np.argmin([abs(cx-x) for x in colx]))
            if abs(cx-colx[h])>0.35*(colx[1]-colx[0]): continue
            day=round((cy-A[1])/A[0])
            if not (1<=day<=ndays) or abs(A[0]*day+A[1]-cy)>0.45*abs(A[0]): continue
            key=(day,hsort[h]); v=float(t)
            grid.setdefault(key,[]).append(v)
    # Mehrheitswert je Zelle
    out={}
    for k,vs in grid.items():
        from collections import Counter
        out[k]=Counter(vs).most_common(1)[0][0]
    return out

if __name__=='__main__':
    g=ocr_grid('7A- TT HAJAMBRO CREEK HOURLY.pdf',30)
    print(f"Erkannt: {len(g)}/720 ({len(g)/720*100:.0f}%)")
    exp=[1.98,1.51,0.98,0.54,0.28,0.28,0.55,1.01,1.54,2.06,2.50,2.78,2.82,2.64,2.31,1.95,1.66,1.51,1.54,1.72,1.94,2.15,2.30,2.31]
    got=[g.get((1,h)) for h in range(24)]
    print("Tag1:",got)
    ok=sum(1 for a,b in zip(got,exp) if a==b); bad=[(h,got[h],exp[h]) for h in range(24) if got[h] is not None and got[h]!=exp[h]]
    print(f"Tag1 korrekt: {ok}/24, falsch: {bad}")
