"""Hangul -> Revised Romanization mit den wichtigsten Lautregeln (Bindung, Nasalierung, l/r)."""
INI = ['g', 'kk', 'n', 'd', 'tt', 'r', 'm', 'b', 'pp', 's', 'ss', '', 'j', 'jj', 'ch', 'k', 't', 'p', 'h']
MED = ['a', 'ae', 'ya', 'yae', 'eo', 'e', 'yeo', 'ye', 'o', 'wa', 'wae', 'oe', 'yo', 'u', 'wo', 'we', 'wi', 'yu', 'eu', 'ui', 'i']
# Auslaut-Index -> (Auslaut vor Konsonant, Anlaut bei Bindung vor ㅇ)
FIN = ['', 'k', 'k', 'k', 'n', 'n', 'n', 't', 'l', 'k', 'm', 'l', 'l', 'l', 'p', 'l', 'm', 'p', 'p', 't', 't', 'ng', 't', 't', 'k', 't', 'p', 't']
BIND = {1: 'g', 2: 'kk', 4: 'n', 7: 'd', 8: 'r', 16: 'm', 17: 'b', 19: 's', 20: 'ss', 22: 'j', 23: 'ch', 24: 'k', 25: 't', 26: 'p'}
def rr(s):
    sil = []
    for ch in s:
        c = ord(ch) - 0xAC00
        sil.append((c // 588, (c % 588) // 28, c % 28) if 0 <= c < 11172 else ch)
    out = []
    for k, x in enumerate(sil):
        if isinstance(x, str):
            out.append(x); continue
        i, mm, f = x
        prev = sil[k - 1] if k and not isinstance(sil[k - 1], str) else None
        nxt = sil[k + 1] if k + 1 < len(sil) and not isinstance(sil[k + 1], str) else None
        ini = INI[i]
        if prev:
            pf = prev[2]
            if i == 11 and pf in BIND: ini = ''               # Bindung: Auslaut wandert
            elif i == 5 and pf in (8,): ini = 'l'             # ㄹㄹ -> ll
            elif i == 5 and pf in (4,): ini = 'l'             # ㄴㄹ -> ll
            elif i == 5 and pf: ini = 'n'                     # ㄱㄹ, ㅁㄹ, ㅇㄹ -> n
        fin = FIN[f]
        if nxt:
            ni = nxt[0]
            if ni == 11 and f in BIND: fin = BIND[f] if f != 21 else 'ng'
            elif ni in (2, 6) or (ni == 5 and f not in (8, 4, 0)):   # vor ㄴ/ㅁ (und ㄹ) nasalieren
                fin = {'k': 'ng', 't': 'n', 'p': 'm'}.get(fin, fin)
            elif ni == 5 and f == 4: fin = 'l'
        out.append(ini + MED[mm] + fin)
    return ''.join(out)
def hat_hangul(s):
    return any(0xAC00 <= ord(c) < 0xAC00 + 11172 for c in s)
