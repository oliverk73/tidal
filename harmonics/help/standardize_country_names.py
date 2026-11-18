#!/usr/bin/env python3
"""
Standardize country names in harmonics TXT files to English.
Replaces non-English country names, ISO codes, and other non-standard
designations with proper English country names.

Uses binary mode to preserve ISO-8859-1 encoding.
"""

import os
import sys
import tempfile

# Files to process (only active files, not backups)
FILES = [
    "/home/oliver/harmonics/classic/harmonics-1997-05-25_mod.txt",
    "/home/oliver/harmonics/ticon/harmonics_ticon4_worldwide.txt",
]

# Replacements: (old_bytes, new_bytes)
# Order matters: specific/longer patterns first, then generic ones
REPLACEMENTS = [
    # Special cases (must come before generic replacements)
    (b"Kralendijk, Bonaire, Caribisch Nederland, Nederland",
     b"Kralendijk, Bonaire, Caribbean Netherlands"),
    (b"\xcele-d'Aix, Frankreich, France",  # Î = \xce in ISO-8859-1
     b"\xcele-d'Aix, France"),
    (b"Cote D'Ivoire", b"Ivory Coast"),
    (b"C\xf4te d'Ivoire", b"Ivory Coast"),   # akzentuiert (ô=0xF4 in ISO-8859-1)

    # ISO 3-letter codes → full English names
    # These are always at end of station name line, so match ", CODE\n"
    (b", SLV\n", b", El Salvador\n"),
    (b", CUW\n", b", Cura\xe7ao\n"),      # Curaçao (ç = \xe7)
    (b", MDV\n", b", Maldives\n"),
    (b", MRT\n", b", Mauritania\n"),
    (b", SYC\n", b", Seychelles\n"),

    # Non-English country names → English
    (b", Brasil\n", b", Brazil\n"),
    (b", Norge\n", b", Norway\n"),
    (b", Pilipinas\n", b", Philippines\n"),
    (b", Viet Nam\n", b", Vietnam\n"),
    (b", Hrvatska\n", b", Croatia\n"),
    (b", Cameroun\n", b", Cameroon\n"),
    (b", Slovenija\n", b", Slovenia\n"),
]


def process_file(filepath, dry_run=True):
    """Process a single file. Returns list of changes made."""
    with open(filepath, "rb") as f:
        data = f.read()

    original = data
    changes = []

    for old, new in REPLACEMENTS:
        count = data.count(old)
        if count > 0:
            # Only replace in station name lines, not in comment lines.
            # For line-ending patterns (ending with \n), split and check each line.
            if old.endswith(b"\n"):
                lines = data.split(b"\n")
                new_lines = []
                line_count = 0
                for line in lines:
                    # Station name lines don't start with #
                    if not line.startswith(b"#") and line.endswith(old[:-1]):
                        line = line[: -len(old[:-1])] + new[:-1]
                        line_count += 1
                    new_lines.append(line)
                data = b"\n".join(new_lines)
                if line_count > 0:
                    changes.append((old.strip(), new.strip(), line_count))
            else:
                # For non-line-ending patterns, replace everywhere
                # (these are specific enough to be safe)
                data = data.replace(old, new)
                changes.append((old, new, count))

    if not dry_run and data != original:
        # Atomic write
        fd, tmp = tempfile.mkstemp(
            dir=os.path.dirname(filepath), suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp, filepath)
        except:
            os.unlink(tmp)
            raise

    return changes


def main():
    dry_run = "--apply" not in sys.argv

    if dry_run:
        print("=== DRY RUN (use --apply to execute) ===\n")
    else:
        print("=== APPLYING CHANGES ===\n")

    total = 0
    for filepath in FILES:
        basename = os.path.basename(filepath)
        print(f"--- {basename} ---")

        if not os.path.exists(filepath):
            print(f"  ÜBERSPRUNGEN (Datei nicht gefunden)")
            continue

        changes = process_file(filepath, dry_run=dry_run)

        if not changes:
            print("  Keine Änderungen nötig.")
        else:
            for old, new, count in changes:
                old_str = old.decode("iso-8859-1")
                new_str = new.decode("iso-8859-1")
                print(f"  {old_str!r} → {new_str!r}  ({count}×)")
                total += count

        print()

    print(f"Gesamt: {total} Ersetzungen" +
          (" (Vorschau)" if dry_run else " (durchgeführt)"))


if __name__ == "__main__":
    main()
