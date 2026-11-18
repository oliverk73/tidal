import fitz, subprocess, sys, os, tempfile
doc=fitz.open('/home/oliver/weather/tide_tables/att/np203_2002_vollband.pdf')
def ocr(pno, dpi=300):
    p=doc[pno]
    pix=p.get_pixmap(dpi=dpi)
    fn=f'/tmp/np_{pno}.png'; pix.save(fn)
    out=subprocess.run(['tesseract',fn,'-','--psm','6'],capture_output=True,text=True).stdout
    return out
if __name__=='__main__':
    for pno in [int(x) for x in sys.argv[1:]]:
        print(f'\n===== PAGE {pno} (0-idx) =====')
        print(ocr(pno)[:1800])
