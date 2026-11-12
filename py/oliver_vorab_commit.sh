#!/bin/bash
# Vor jeder eigenen Aenderung: Olivers ungecommittete Karten-/Satzaenderungen als eigenen Commit sichern.
# (12.11.2026 zweimal seine Verschiebungen in meine Commits gemischt.) Aufruf: bash py/oliver_vorab_commit.sh
cd "$(dirname "$0")/.." || exit 1
# nur Satzdateien (Olivers Kartenedits), nicht harmonics/help (meine Listen); Markerdatei nur zusammen mit ihnen
dateien=$(git status --porcelain -- 'harmonics/*/*.txt' | awk '$1=="M"{print $2}' | grep -v '/help/')
[ -z "$dateien" ] && exit 0
git diff --quiet -- static/js/leaflet_markers_data.json || dateien="$dateien static/js/leaflet_markers_data.json"
namen=$(git diff -- $dateien | grep -a '^+[^#+ ].*,' | grep -av '^+[A-Za-z0-9-]* *[0-9.]* *[0-9.]*$' | sed 's/^+//' | head -5 | tr '\n' ';')
git add $dateien && git commit -q -m "Oliver: Kartenaenderungen ${namen:0:150}

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" && echo "Olivers Aenderungen vorab committet: $dateien"
