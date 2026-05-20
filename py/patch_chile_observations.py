#!/usr/bin/env python3
"""Replace Chile-IOC station blocks in harmonics_utide_observations.txt
with freshly-fitted ones from a generated harmonics file
(after 2026-05-19 hourly-bin-bug patch).

Blocks are delimited by `# BEGIN HOT COMMENTS`. Each block starts at the
first contiguous comment/blank line preceding that marker and runs up to
the next block's start (or EOF). Each block contains exactly one
`# station_id_context:` line used to match new and old blocks.

Usage:
  python3 patch_chile_observations.py \
      --new ~/harmonics/help/chile_utide_v3_2026-05-19.txt \
      --observations ~/harmonics/utide/harmonics_utide_observations.txt \
      [--remove IOC-corr-chl-shoa[,IOC-other,...]]
"""

import argparse
import re
import shutil
from datetime import datetime


def parse_blocks(path, encoding='latin-1'):
    """Return (file_header_text, [block_dict, ...]).

    block_dict = {'ctx': str|None, 'text': str (newline-terminated)}.
    """
    with open(path, encoding=encoding) as f:
        text = f.read()
    lines = text.split('\n')
    boundary_indices = [i for i, ln in enumerate(lines)
                        if ln.startswith('# BEGIN HOT COMMENTS')]

    def find_block_start(b_idx):
        k = b_idx - 1
        while k >= 0 and (lines[k] == '' or lines[k].startswith('#')):
            k -= 1
        return k + 1

    block_starts = [find_block_start(b) for b in boundary_indices]
    if not block_starts:
        return text, []

    # File header = everything before the first block's start
    header_lines = lines[:block_starts[0]]
    header = '\n'.join(header_lines)
    if header_lines:
        header += '\n'

    blocks = []
    ctx_re = re.compile(r'^# station_id_context:\s*(.+?)\s*$')
    for i, start in enumerate(block_starts):
        end = block_starts[i + 1] if i + 1 < len(block_starts) else len(lines)
        block_lines = lines[start:end]
        block_text = '\n'.join(block_lines)
        # Ensure block ends with newline if there is more content after
        if end < len(lines):
            block_text += '\n'
        ctx = None
        for ln in block_lines:
            m = ctx_re.match(ln)
            if m:
                ctx = m.group(1)
                break
        blocks.append({'ctx': ctx, 'text': block_text})
    return header, blocks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--new', required=True,
                    help='Newly generated chile harmonics file')
    ap.add_argument('--observations', required=True)
    ap.add_argument('--remove', default='',
                    help='Comma-separated station_id_context values to drop')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    remove_set = {s.strip() for s in args.remove.split(',') if s.strip()}

    obs_header, obs_blocks = parse_blocks(args.observations)
    new_header, new_blocks = parse_blocks(args.new)

    new_by_ctx = {b['ctx']: b for b in new_blocks if b['ctx']}

    print(f'observations.txt: {len(obs_blocks)} blocks total')
    print(f'new file:         {len(new_blocks)} blocks total '
          f'({len(new_by_ctx)} unique ctx)')

    # Identify Chile-IOC stations (and DART) in observations
    def is_chile_ioc(ctx):
        if not ctx:
            return False
        return ctx.endswith('-chl-shoa') or ctx.endswith('-dart')

    obs_ctxs = {b['ctx'] for b in obs_blocks if b['ctx']}
    chile_obs_ctxs = {c for c in obs_ctxs if is_chile_ioc(c)}
    print(f'observations.txt: {len(chile_obs_ctxs)} Chile-IOC/DART blocks')
    print(f'new file:         {len(new_by_ctx)} replacement blocks')

    # Sanity: every new ctx must already exist in observations
    missing_in_obs = sorted(set(new_by_ctx) - obs_ctxs)
    if missing_in_obs:
        print('\nWARN: new file has ctx not present in observations '
              '(would be appended):')
        for c in missing_in_obs:
            print(f'  {c}')

    # Apply replacements
    out_blocks = []
    replaced_ctxs = set()
    removed_ctxs = set()
    kept_old_chile = []
    for b in obs_blocks:
        ctx = b['ctx']
        if ctx and ctx in remove_set:
            removed_ctxs.add(ctx)
            continue
        if ctx and ctx in new_by_ctx:
            replacement = new_by_ctx[ctx]
            # Preserve trailing newline behavior of original slot
            out_blocks.append({'ctx': ctx, 'text': replacement['text']})
            replaced_ctxs.add(ctx)
            continue
        if is_chile_ioc(ctx) and ctx not in new_by_ctx:
            # Stale Chile block we have no replacement for —
            # keep it but warn (unless explicitly removed above).
            kept_old_chile.append(ctx)
        out_blocks.append(b)

    # Append any new ctxs that weren't in observations
    appended_ctxs = set()
    for ctx in missing_in_obs:
        out_blocks.append(new_by_ctx[ctx])
        appended_ctxs.add(ctx)

    print(f'\nReplaced:  {len(replaced_ctxs)} blocks')
    print(f'Removed:   {len(removed_ctxs)} blocks ({sorted(removed_ctxs)})')
    print(f'Appended:  {len(appended_ctxs)} blocks')
    if kept_old_chile:
        print(f'Kept old Chile (no replacement): {len(kept_old_chile)}: '
              f'{kept_old_chile}')
    print(f'Total out: {len(out_blocks)} blocks '
          f'(was {len(obs_blocks)}; '
          f'expected {len(obs_blocks) - len(removed_ctxs) + len(appended_ctxs)})')

    expected = len(obs_blocks) - len(removed_ctxs) + len(appended_ctxs)
    assert len(out_blocks) == expected, (
        f'Block count mismatch: got {len(out_blocks)}, expected {expected}')

    if args.dry_run:
        print('\nDry-run only, no file written.')
        return

    # Write atomically: backup, then write to tmp, then move
    backup = (args.observations
              + f'.bak-chilefix-{datetime.now():%Y%m%d-%H%M%S}')
    shutil.copy(args.observations, backup)
    print(f'\nBackup: {backup}')

    tmp_path = args.observations + '.tmp'
    with open(tmp_path, 'w', encoding='latin-1', newline='') as f:
        f.write(obs_header)
        for b in out_blocks:
            f.write(b['text'])
    shutil.move(tmp_path, args.observations)

    # Verify
    with open(args.observations, encoding='latin-1') as f:
        verify_text = f.read()
    verify_ctx_count = verify_text.count('\n# station_id_context:') + (
        1 if verify_text.startswith('# station_id_context:') else 0)
    verify_begin_count = verify_text.count('\n# BEGIN HOT COMMENTS') + (
        1 if verify_text.startswith('# BEGIN HOT COMMENTS') else 0)
    print(f'\nVerification:')
    print(f'  station_id_context lines: {verify_ctx_count} '
          f'(expected {expected})')
    print(f'  BEGIN HOT COMMENTS lines: {verify_begin_count} '
          f'(expected {expected})')
    if verify_ctx_count != expected or verify_begin_count != expected:
        print('  ✗ MISMATCH — restore from backup!')
    else:
        print('  ✓ block counts match')


if __name__ == '__main__':
    main()
