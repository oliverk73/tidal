#!/usr/bin/env bash
# Deploy der NP203-Strömungs-TCD + Marker-Rebuild.
# Der sudo-cp-Schritt ist der EINZIGE, der Root braucht (neue Datei in
# /usr/share/xtide anlegen). Danach laeuft alles ohne sudo.
#
#   bash ~/py/deploy_np203_currents.sh
#
set -euo pipefail
cd "$HOME"

SRC="$HOME/harmonics/binary/harmonics_att_np203_currents.tcd"
DST="/usr/share/xtide/harmonics_att_np203_currents.tcd"

echo "== 1/3  TCD nach /usr/share/xtide deployen (sudo) =="
sudo cp "$SRC" "$DST"
sudo chown "$USER:$USER" "$DST"   # damit die App sie spaeter ohne sudo aktualisieren kann
ls -la "$DST"

echo "== 2/3  Verifikation: 65 Strömungsstationen in der deployten TCD =="
HFILE_PATH="$DST" tide -m l 2>/dev/null | grep -c 'Current' || true

echo "== 3/3  Marker neu bauen (Gruppen 'Admiralty NP203' + 'NP203 Strömung') =="
python3 "$HOME/py/build_tide_station_markers.py"

echo
echo "FERTIG. Bitte leaflet_markers* pruefen und committen:"
echo "  git add static/js/leaflet_markers*.js static/js/leaflet_markers_data.json"
echo "  git commit -m 'NP203 Strömungen + Tide: Marker-Gruppen aktiviert'"
