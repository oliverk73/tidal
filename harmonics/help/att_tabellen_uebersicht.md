# Welche ATT-Tabellen wir brauchen — und wofür

Stand 2026-07-28. Gilt für alle Bände der ADMIRALTY Tide Tables (NP201–NP208).

## Faustregel

**Zahlen je Hafen brauchen wir. Rechenschritte und Jahreswerte nicht.**

XTide führt die harmonische Synthese selbst aus und berechnet Knotenfaktoren und
Gleichgewichtsargumente für jedes beliebige Jahr. Alles, was im Buch der
Handrechnung dient, ist für uns wertlos — und teils sogar schädlich, weil es nur
für das Druckjahr gilt.

## Gebraucht

| Tabelle | Inhalt | Wofür |
|---|---|---|
| **Part II** (Secondary Ports) | Zeit- und Höhendifferenzen, **Koordinaten**, ML | Positionen aller Stationen; Konstanten nur dort, wo Part III nichts hat |
| **Part III** (Harmonic Constants) | ML/Z0, M2, S2, K1, O1 mit Phase und Amplitude, S.W.-Korrekturen f4/F4, f6/F6 | die eigentliche Datenquelle für die Konstituenten |
| **Table V Part 1** | LAT, MLWS, MLWN, MSL, MHWN, MHWS, HAT je **Standardhafen** | Bezugsgrößen für den Part-II-Transfer; Datumskontrolle |
| **Table V Part 2** | HAT je **Sekundärhafen** | unabhängige Qualitätsprüfung jeder Station |
| **Table VI** | Fortnightly Shallow Water Correction (ML je Tag vor/nach Springs) | MSf-Konstituente für die wenigen Häfen mit starkem Flachwassereffekt |

Part II ist auch dann unverzichtbar, wenn Part III vollständig ist: **Die
Koordinaten stehen nur dort.**

## Nicht gebraucht

| Tabelle | Warum nicht |
|---|---|
| Table I | Erläuterung der Methode |
| Table II — Multiplication Table | Rechenhilfe zum Multiplizieren von Hand |
| Table VII — Tidal Angles and Factors | tägliche A/F-Werte für M2/S2/K1/O1, **nur für das Druckjahr**; XTide rechnet das selbst |
| Table VIII — Orbital Elements | wöchentliche Bahnelemente, dito |
| Part I (Tagesvorhersagen der Standardhäfen) | fertige Vorhersagen, keine Konstanten |

## Warum Table V Part 1 gebraucht wird

Der Part-II-Transfer skaliert den Bezugshafen mit den Höhendifferenzen des
Sekundärhafens:

```
SR_sek = SR_bezug + (dMHWS - dMLWS)      fS = SR_sek / SR_bezug
```

`SR_bezug` muss der **publizierte** Springhub des Standardhafens sein, nicht der
aus seinem Konstantensatz gerechnete. Beispiel Mina Salman: Konstantensatz 1.57 m,
Buch 2.4 − 0.6 = 1.80 m. Bei einer Differenz von −1.2 m bleiben im ersten Fall
0.37 m Hub übrig, im zweiten 0.60 m — Faktor 1.6. Am Bahrain Yacht Club führte
das zu M2 = 0.064 m statt der gemessenen 0.16 m, und S2 wurde größer als M2.

Diese publizierten Werte stehen in Table V Part 1 (und im Kopf jedes Part-II-Blocks).

## Warum Table V Part 2 gebraucht wird

HAT ist der höchste astronomisch mögliche Wasserstand. Der über ein Jahr
vorhergesagte Maximalwert muss knapp darunter liegen. Das ist ein Test, der aus
derselben Quelle stammt wie die Daten und keine Modellannahmen braucht:

```
tide -l STATION -b 2026-01-01 -e 2027-01-01 -m s   ->  "Maximum was ..."
```

Die HAT-Werte aller NP203-Sekundärhäfen stehen transkribiert in
`harmonics/help/np203_table5_part2_hat.json`; `py/hat_test_np203.py` prüft damit
die ganze Datei auf einen Rutsch (Toleranz +0.30 m nach oben, −1.00 m nach unten).

Stand 2026-07-29 über 441 Stationen: 38 auffällig, davon 36 noch aus dem
Part-II-Transfer. Vor dem Part-III-Import derselben Datei waren es 69 — der
Import hat 31 Stationen geradegerückt.

**Nicht** geeignet ist die Summe aller Amplituden plus Z0: Sie ist eine obere
Schranke, die nie erreicht wird, und meldet Fehlalarme (Suhar schien 0.5 m zu
hoch, liegt tatsächlich 0.3 m unter HAT).

## Warum Table VI gebraucht wird

Bei zwölf Häfen mit starkem Flachwassereinfluss schwankt das Mittelwasser im
Vierzehntagerhythmus. Das Buch gibt korrigierte ML-Werte für den Springtag und
für jeden Tag davor/danach. In XTide ist das die Konstituente **MSf**
(1.0158958 °/h), die in unserem 175-Slot-Layout einen eigenen, bisher leeren
Platz hat. Amplitude ≈ halbe Spanne, Phasenlage so, dass das Maximum auf den
Springtag fällt.

Betroffen und bei uns vorhanden (NP203):

| att | Station | ML Springs | ML +7 Tage | Spanne |
|---|---|---:|---:|---:|
| 4326 | Lakhpat, Gujarat | 2.70 | 2.36 | 0.34 |
| 4327 | Godia Creek, Gujarat | 2.00 | 1.80 | 0.20 |
| 4349 | Dahej Bandar, Gujarat | 5.20 | 4.60 | 0.60 |
| 4350 | Ambetha, Gujarat | 4.38 | 4.06 | 0.32 |
| 4362 | Nava (Karanja), Maharashtra | 2.68 | 2.50 | 0.18 |
| 4472 | Kushabhadra River, Odisha | 1.24 | 1.08 | 0.16 |
| 4476 | Chandbali, Odisha | 1.88 | 1.66 | 0.22 |
| 4484 | Diamond Harbour, West Bengal | 3.47 | 3.13 | 0.34 |
| 4488 | Kolkata (Garden Reach) | 3.46 | 2.92 | 0.54 |

Nicht in der Sammlung: 4346, 4354, 4475a.

## Scans

Ablage: `weather/tide_tables/att/`, Namensschema `np<Band>_<Edition>_<teil>_p<Seiten>.pdf`.

Stand NP203 — vollständig:

```
np203_2015_secondary_ports_p222-238.pdf   Part II    S.222-238, lückenlos
np203_2015_standard_ports_p240-253.pdf    Part III   S.240-249, 252, 253
                                          (250/251 sind Leer- bzw. Überschriftseiten)
np203_2015_table5_pxxx-xxxvii.pdf         Table V    Part 1 (S.xxx-xxxii) + Part 2 (S.xxxiii-xxxvii)
np203_2015_table6_pxxxviii.pdf            Table VI   S.xxxviii
```

Für die anderen Bände fehlen Table V und VI bisher komplett. Ob dort überhaupt
Part III eingelesen wurde, ist noch zu prüfen.

## Werkzeuge

```
py/build_np203.py               Part III -> Standardhäfen (107 Stationen, 2026-06)
py/build_np203_tablev.py        Part III -> Sekundärhäfen, ersetzt Part-II-Transfers
py/build_np203_secondary.py     Part-II-Transfer (Fallback ohne Part III)
py/rebuild_np203_page231.py     Part II Seite 231 komplett aus dem Scan
py/add_np203_tablev_new.py      legt Stationen an, die es bei uns noch nicht gibt
py/fix_np203_numbers_2.py       att-Nummern gegen den Scan geradeziehen
py/hat_test_np203.py            HAT-Test gegen Table V Part 2
```

`build_np203_tablev.py` gleicht **über die att-Nummer** ab und prüft zusätzlich den
Namen: Weicht der Buchname zu stark vom Namen in der Datei ab, wird die Zeile
übersprungen statt überschrieben. Das hat den Buchstabenversatz 4210a/b/c
aufgedeckt — über die Nummer allein wären drei Stationen mit fremden Konstanten
befüllt worden. Umbenennungen (Zekreet/Zikrit, Dibba/Mina Diba) passieren die
Prüfung, ein anderer Ort nicht.

Der Nummernversatz ist kein Einzelfall: Am 2026-07-29 fand dieselbe Prüfung
13 weitere falsche Nummern (Rotes Meer und Golf von Oman, u. a. eine Kette von
fünf aufeinanderfolgenden Stationen von Dibab bis Bandar Jissah). Erkennbar
waren sie nur daran, dass der Buchname zur Nummer nicht zum Namen in der Datei
passte. **Vor jedem Wertübernehmen die Nummernfolge gegen den Scan prüfen.**
Verifizierte Abweichungen (El Tor/At Tur, Rodrigues/Port Mathurin) stehen als
`NAME_OK` mit Begründung im Skript, damit sie nicht jedes Mal neu auffallen.

## Reihenfolge beim Einlesen eines Bandes

1. **Part II** — Nummern, Namen, Koordinaten, Differenzen. Nummernfolge gegen den
   Scan prüfen, bevor Werte übernommen werden.
2. **Part III** — wo vorhanden, ersetzt es den Transfer vollständig. Meridian auf
   die im Seitenkopf angegebene Zone setzen, N2/K2 inferieren, M4/M6 aus f4/f6.
3. **Table V Part 1** — Bezugswerte für die Stationen, die weiter aus Part II kommen.
4. **Table V Part 2** — HAT-Test über alle Stationen des Bandes.
5. **Table VI** — MSf für die dort gelisteten Häfen.
