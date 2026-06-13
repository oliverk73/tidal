"""Parse Payra Port Authority 'Rabnabad Channel Tide Table' PDF -> HW/LW series.

Layout (text layer): two stations side by side per page, each with TIME (HHMM)
and M (height) columns. Day-of-month numbers sit at the far left/right margins.
Even data pages (10,12,...) hold Charipara (left) + Kaurchar (right); odd pages
(11,13,...) hold Monopile-1 (left) + Monopile-2 (right). One month per page-row,
~8 days per page. Times are Bangladesh Standard Time (UTC+6, no DST).
"""
import re
import pdfplumber
from datetime import datetime

MONTHS = {'JANUARY': 1, 'FEBRUARY': 2, 'MARCH': 3, 'APRIL': 4, 'MAY': 5,
          'JUNE': 6, 'JULY': 7, 'AUGUST': 8, 'SEPTEMBER': 9, 'OCTOBER': 10,
          'NOVEMBER': 11, 'DECEMBER': 12}

# data pages start at 10; even->CK, odd->MM
PAGES = {
    'charipara':  ('left',  range(10, 106, 2)),
    'kaurchar':   ('right', range(10, 106, 2)),
    'monopile-1': ('left',  range(11, 106, 2)),
    'monopile-2': ('right', range(11, 106, 2)),
}


XMID = 132    # page is ~268 wide; left station < XMID, right station >= XMID


def _median(xs):
    s = sorted(xs)
    return s[len(s) // 2]


def parse_page(page, side, year):
    txt = page.extract_text() or ''
    mons = re.findall(r'\b(' + '|'.join(MONTHS) + r')\b', txt)
    if not mons:
        return []
    month = MONTHS[mons[0]]
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False)

    # restrict to the chosen station's half of the page
    half = [w for w in words if (w['x0'] < XMID) == (side == 'left')
            and w['top'] < 372]   # drop centred page-number at the foot

    times, heights, cand = [], [], []
    for w in half:
        x = w['x0']; top = w['top']; t = w['text'].strip()
        if re.fullmatch(r'\d{3,4}', t):
            times.append((top, x, t))
        elif re.fullmatch(r'-?\d+\.\d+', t):
            heights.append((top, float(t)))
        elif re.fullmatch(r'\d{1,2}', t) and 1 <= int(t) <= 31:
            cand.append((top, x, int(t)))
    if not times or not heights or not cand:
        return []

    # day-number column sits in the outer margin relative to the data columns
    tx = _median([x for _, x, _ in times])
    hx = _median([h_x for h_x in [w['x0'] for w in half
                  if re.fullmatch(r'-?\d+\.\d+', w['text'].strip())]])
    if side == 'left':
        anchors = [(top, d) for top, x, d in cand if x < tx - 4]
    else:
        anchors = [(top, d) for top, x, d in cand if x > hx + 4]
    times = [(top, t) for top, x, t in times]

    # pair time + height by matching vertical position
    events = []
    used = [False] * len(heights)
    for tt, tv in times:
        best, bj = 3.0, -1
        for j, (ht, hv) in enumerate(heights):
            if used[j]:
                continue
            d = abs(ht - tt)
            if d < best:
                best, bj = d, j
        if bj >= 0:
            used[bj] = True
            events.append((tt, tv, heights[bj][1]))

    if not anchors:
        return []
    anchors.sort()
    # day boundaries = midpoints between consecutive day-number tops
    bounds = []
    for i in range(len(anchors) - 1):
        bounds.append((anchors[i][0] + anchors[i + 1][0]) / 2.0)
    bounds.append(float('inf'))

    out = []
    for top, tv, hv in events:
        di = 0
        while di < len(bounds) and top >= bounds[di]:
            di += 1
        if di >= len(anchors):
            continue
        day = anchors[di][1]
        hh = tv.zfill(4)
        H, M = int(hh[:2]), int(hh[2:])
        if H > 23 or M > 59:
            continue
        try:
            out.append((datetime(year, month, day, H, M), hv))
        except ValueError:
            pass
    return out


def parse_station(pdf_path, code, year=2025):
    side, pages = PAGES[code]
    pdf = pdfplumber.open(pdf_path)
    allres = []
    for pi in pages:
        if pi < len(pdf.pages):
            allres += parse_page(pdf.pages[pi], side, year)
    seen, ded = set(), []
    for dt, h in sorted(allres):
        if dt not in seen:
            ded.append((dt, h)); seen.add(dt)
    return ded


if __name__ == '__main__':
    import calendar
    from datetime import date
    PDF = '/home/oliver/annual_predictions/bangladesh/payra/ppa_10.pdf'
    for code in PAGES:
        res = parse_station(PDF, code, 2025)
        hs = [h for _, h in res]
        days = sorted(set(dt.date() for dt, _ in res))
        miss = []
        for m in range(1, 13):
            for d in range(1, calendar.monthrange(2025, m)[1] + 1):
                if date(2025, m, d) not in days:
                    miss.append(f"{m}/{d}")
        print(f"{code:12} {len(res):4} HW/LW  {len(days)}/365 Tage  "
              f"{len(res)/max(len(days),1):.2f}/Tag  H={min(hs):.2f}..{max(hs):.2f}  "
              f"fehlt={miss[:8]}{'...' if len(miss)>8 else ''}")
