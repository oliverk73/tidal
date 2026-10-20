# MDE-Engstellen (Oliver 20.10.2026)

Einlese- und Eintragsskripte für die Crown-Estate-Strömungsmessungen (Marine Data Exchange) an
Engstellen: Pentland Firth, Orkney, Kyle Rhea, Islay, Fair Head, St David's Head, Skerries, East Anglia.

- Leser je Paket (`anglia.py`, `westray.py`, `brims*.py`, `fairhead.py`, `islay.py`, `inner.py`, `stdavids.py`,
  `costa.py`, `rdi.py` für RDI-PD0) schreiben Pickles nach `currents/UK_MDE/_arbeit/`
  (Stundenmittel mit `cmems_stroemung_nachholen.stundenmittel`, Druck für die Zeitprobe).
  Große Rohdaten (Brims-/Costa-Matlab, RDI `.000`) vorher aus den Zips nach `_arbeit/brims/` bzw. `_arbeit/rdi/`
  entpacken (mehrteilige Archive mit `7z x`).
- `probe.py PKL` / `pruef.py`: Fit und Zeitprobe (M2 des Gerätedrucks gegen die nächsten Pegel).
- `eintrag.py` + `liste1..3.py`, `anglia_eintragen.py`: Blöcke für harmonics_utide_current_observations.txt (`--schreiben`).
- `atlas_eichung.py`: SHOM-Atlas gegen gemessene Stationen; `delta.py`, `spion.py`: Stempelfehler der Stundenmittel messen.
