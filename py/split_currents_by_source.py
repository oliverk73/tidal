#!/usr/bin/env python3
"""
Split harmonics_utide_currents.txt into two files based on each station's
`# source:` header:

  - harmonics_utide_current_observations.txt  (real ADCP/velocity measurements)
  - harmonics_utide_current_tables.txt        (provider predictions, e.g. CHS,
                                                BOM tidal stream predictions)

Classification rule:
  if "predictions" appears in the source line (case-insensitive) → tables (TC)
  else → observations (SL)
"""
import re
import sys
from pathlib import Path

SRC = Path('/home/oliver/harmonics/utide/harmonics_utide_currents.txt')
OUT_SL = Path('/home/oliver/harmonics/utide/harmonics_utide_current_observations.txt')
OUT_TC = Path('/home/oliver/harmonics/utide/harmonics_utide_current_tables.txt')


def main():
    text = SRC.read_text(encoding='latin-1')
    lines = text.split('\n')

    # Find master-header end: line "# detail_table:" (+ optional trailing "#" blank)
    master_end = next((i for i, l in enumerate(lines)
                       if l.startswith('# detail_table:')), None)
    if master_end is None:
        sys.exit("No master-header end marker '# detail_table:' found.")
    if master_end + 1 < len(lines) and lines[master_end + 1].strip() == '#':
        master_end += 1
    master = lines[:master_end + 1]

    # Find every station's "# BEGIN HOT COMMENTS" line
    begins = [i for i, l in enumerate(lines) if l.strip() == '# BEGIN HOT COMMENTS']
    if not begins:
        sys.exit("No '# BEGIN HOT COMMENTS' markers found.")

    # Walk back from each BEGIN to gather pre-comments belonging to that station
    def station_start(begin):
        k = begin - 1
        while k > master_end and lines[k].startswith('#'):
            k -= 1
        return k + 1

    starts = [station_start(b) for b in begins]
    # Make station block i = lines[starts[i] : starts[i+1]] (or end of file)
    starts.append(len(lines))

    sl_blocks = []
    tc_blocks = []
    src_re = re.compile(r'^#\s*source:\s*(.+)$', re.IGNORECASE)
    for i in range(len(begins)):
        block = lines[starts[i]:starts[i + 1]]
        src = None
        for bl in block:
            m = src_re.match(bl)
            if m:
                src = m.group(1).strip()
                break
        is_prediction = src and 'prediction' in src.lower()
        if is_prediction:
            tc_blocks.append(block)
        else:
            sl_blocks.append(block)

    def write(path, blocks, label):
        # Adjust master header counters where they exist
        new_master = list(master)
        for j, line in enumerate(new_master):
            if line.startswith('# total_stations:'):
                new_master[j] = f"# total_stations: {len(blocks)}"
            if line.strip() == '# UTide harmonic analysis -- aggregated statistics (currents)':
                new_master[j] = (
                    f"# UTide harmonic analysis -- aggregated statistics "
                    f"(currents, {label})"
                )
        body = '\n'.join(new_master) + '\n'
        for blk in blocks:
            body += '\n'.join(blk).rstrip('\n') + '\n'
        path.write_text(body, encoding='latin-1')
        print(f"  Wrote {path.name}  {len(blocks)} stations  "
              f"({path.stat().st_size / 1024:.0f} KB)")

    print(f"Source file: {SRC.name}  ({len(begins)} stations)")
    write(OUT_SL, sl_blocks, 'observations / SL')
    write(OUT_TC, tc_blocks, 'tables / TC')

    # Sanity report: source histograms
    def src_hist(blocks):
        from collections import Counter
        c = Counter()
        for blk in blocks:
            for bl in blk:
                m = src_re.match(bl)
                if m:
                    c[m.group(1).strip()] += 1
                    break
        for k, v in c.most_common():
            print(f"    {v:4d}  {k}")

    print(f"\n[observations] {len(sl_blocks)} stations by source:")
    src_hist(sl_blocks)
    print(f"\n[tables] {len(tc_blocks)} stations by source:")
    src_hist(tc_blocks)


if __name__ == '__main__':
    main()
