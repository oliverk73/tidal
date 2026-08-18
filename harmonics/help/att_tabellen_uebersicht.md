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

## „Stationseigen" gegen „übertragen"

Beides kommt als fertige Harmonics bei uns an — der Unterschied liegt darin,
**wessen Analyse dahintersteckt**:

- **Stationseigen (Part III).** Das UKHO hat an *diesem* Hafen einen
  Pegelschrieb harmonisch analysiert und druckt das Ergebnis. Die Zahlen
  gehören zum Ort. In den Stationsnotizen: `Stationseigene Konstanten`.
- **Übertragen (Part-II-Transfer).** Für diese Häfen druckt das Buch **gar
  keine** Konstanten, nur Zeit- und Höhendifferenzen zu einem Standardhafen.
  Den Konstantensatz bauen *wir*: die Kurve des Bezugshafens, mit den
  Höhendifferenzen gestreckt und mit der Zeitdifferenz verschoben. In den
  Notizen: `Sekundaerhafen-Transfer von …`.

Praktisch dreht sich die Sache dabei um:

| | Stationen | Konstituenten im Mittel |
|---|---:|---:|
| aus Part III übernommen | 309 | 6.3 (3–9) |
| aus Part II übertragen | 170 | 29.7 (6–68) |

Part III gibt nur M2, S2, K1, O1 her; N2/K2 und M4/M6 leiten wir daraus ab.
Der Transfer erbt dagegen das ganze Spektrum des Bezugshafens. Suvali (4353,
Part III, 7 Konstituenten) und Hazira (4353a, von Bhavnagar übertragen, 55)
liegen 9 km auseinander an derselben Flussmündung — die 48 zusätzlichen
Konstituenten beschreiben Bhavnagar, 60 km nördlich, nicht Hazira.

Part III bleibt trotzdem die bessere Quelle: Die vier dominanten Konstituenten
tragen den Löwenanteil, und beim Transfer hängt alles daran, dass Bezugshafen,
Pegel und Zone stimmen. **Stationseigen heißt aber nicht gut** — viele
Part-III-Zeilen tragen im Buch ein `a` („data approximate"), und die
zugrundeliegenden Aufzeichnungen sind teils kurz.

## Nicht gebraucht

| Tabelle | Warum nicht |
|---|---|
| Table I | Erläuterung der Methode |
| Table II — Multiplication Table | Rechenhilfe zum Multiplizieren von Hand |
| Table VII — Tidal Angles and Factors | tägliche A/F-Werte für M2/S2/K1/O1, **nur für das Druckjahr**; XTide rechnet das selbst |
| Table VIII — Orbital Elements | wöchentliche Bahnelemente, dito |
| Part I (Tagesvorhersagen der Standardhäfen) | fertige Vorhersagen, keine Konstanten |

## Table V Part 1 — erledigt für NP203 (2026-08-01)

Transkribiert in `harmonics/help/np203_table5_part1_levels.json`: 65 Standard-
häfen mit LAT, den vier Pegeln, MSL und HAT, jeder mit att-Nummer. Die Tabelle
hat zwei Teile — S.xxx die überwiegend halbtägigen Häfen (MHWS/MHWN/MLWN/MLWS),
S.xxxi die tagesungleichen (MHHW/MLHW/MHLW/MLLW), S.xxxii die Definitionen.

**Selbsttest:** Dieselben vier Pegel stehen auch in den Part-II-Gruppenköpfen.
29 von 29 Bezugshäfen stimmen exakt überein — beide Transkriptionen bestätigen
sich gegenseitig.

**Der eigentliche Gewinn** war der HAT-Test für `harmonics_att_np203.txt`
(107 Stationen), der bis dahin gar nicht existierte, weil Table V Part 2 nur
Sekundärhäfen abdeckt. Volle HAT-Abdeckung, und der Test fand sofort zwei
Fehler:

- **4146 und 4146a waren vertauscht.** Das Buch führt 4146 Ras al Katib
  (14° 55′ N) und 4146a Al Hudaydah (14° 50′ N); unsere Positionen belegen den
  Tausch eindeutig, die Namen standen an der falschen Nummer.
- **Vier Stationen trugen Z0 aus der Ausgabe 2002**, das der ML-Spalte von
  Part II (2015) widersprach: 4145 Kamaran 0.78 → 1.00, 4146 Ras al Katib
  1.09 → 0.46, 4146a Al Hudaydah 1.22 → 0.58, 4330 Kandla 3.68 → 3.88. Bei den
  beiden Jemen-Häfen waren die Konstituenten selbst richtig, nur das Datum lag
  0.63 m zu hoch. Von 84 Stationen, die in beiden Ausgaben vorliegen, weichen
  nur diese vier um mehr als 0.15 m ab.

Danach bleiben 2 von 107 auffällig: 4279 Bandar-e Mahshahr (+0.42 m) und
4325 Kori Creek Entrance (+0.91 m).

**Aufruf:** `python3 py/hat_test_np203.py <tcd> [<txt>]` — die Textquelle wird
aus dem TCD-Namen erraten, kann aber als zweites Argument gesetzt werden.

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
das zu M2 = 0.064 m statt der 0.16 m aus Part III, und S2 wurde größer als M2.

Diese publizierten Werte stehen in Table V Part 1 (und im Kopf jedes Part-II-Blocks).

## Welcher Standardhafen ist der Bezug?

**Der eingerahmte Standardhafen über einer Gruppe gilt bis zum nächsten
eingerahmten Kopf.** Ein Standardhafen, der *innerhalb* der Liste an seiner
geografischen Stelle steht (`STANDARD PORT … See Table V`), ist nur ein Eintrag
und **kein** neuer Bezug.

Der Import von 2026-06 hat das verwechselt und ab jedem solchen Eintrag den
Bezug gewechselt. Auf Seite 224 steht die ganze Madagaskar-Liste unter
Antsiranana — der alte Import hat ab Mahajanga (3881) und ab Toamasina (3932)
umgeschaltet und damit 28 Stationen falsch abgeleitet. Insgesamt betraf es
63 der 170 Transfer-Stationen.

ATT wählt den Bezug nach **Kurvenform, nicht nach Nähe**: Die Antarktis hängt an
Durban, Kerguelen an Sagar Roads, Mawson an Kochi, Chagos wieder an Durban.
Raten führt zwangsläufig in die Irre — der Kopf muss gelesen werden.

Die vollständige Zuordnung aller 59 Gruppen samt publizierter Pegel steht in
`harmonics/help/np203_part2_bezugshaefen.json`, geprüft wird sie mit
`py/check_np203_bezug.py`. Seit 2026-08-01 hängen alle 168 Transfer-Stationen
am richtigen Bezugshafen.

## Woher die Konstanten der Bezugshäfen kommen

**ATT druckt für Standardhäfen keine harmonischen Konstanten.** Part III listet
nur Häfen ohne Tagesvorhersage; die Standardhäfen bekommen Part I und Table V.
Seite 252/253 von NP203 ist Part **IIIa** — Gezeitenströme in Knoten, keine
Wasserstände.

Für den Transfer brauchen wir trotzdem einen Konstantensatz des Bezugshafens.
18 von ihnen kommen deshalb aus unseren anderen Sammlungen; welcher und warum,
steht in `harmonics/help/np203_bezugshafen_konstanten.json`. Ausgewählt wird
nach Spring- und Nipphub gegen die publizierten Pegel des Gruppenkopfs. Zwei
Kandidaten fielen dabei als fehlerhaft auf:

| Hafen | Quelle | Springhub | Buch |
|---|---|---:|---:|
| Mumbai (Colaba) | `utide_observations`, `master_2026-05-20` | 8.29 m | 3.60 m |
| Chennai | `utide_observations`, `master_2026-05-20` | 0.80 m | 1.00 m |

Bei Mumbai steht dort M2 = 3.05 m statt 1.23 m. Für beide nehmen wir Classic-1997.

Ebenfalls gefunden: **4539 „Bassein River Entrance"** ist nicht Pathein
flussaufwärts, sondern Thamihla Kyun (Diamond Island) an der Mündung — 1.94/0.71 m
gegen 2.00/0.70 m im Buch, Pathein träfe 1.88/0.94 m.

## Die Zeitdifferenz enthält den Zonensprung

Die Zeitdifferenzen in Part II werden auf die Zeit des Standardhafens **in dessen
Zone** addiert und ergeben die Zeit des Sekundärhafens **in dessen** Zone (die
Zwischenüberschrift `Zone -0xx00`). Sie enthalten den Zonenversatz also mit. Für
die Phasenverschiebung braucht man aber die Verzögerung in Weltzeit:

```
dt_UT = dt_Buch + (Zone_Bezug - Zone_Sekundär)
```

Bei Madagaskar fällt das weg (beides −0300), deshalb fiel es lange nicht auf.
Kerguelen unter Durban sind 3 h Unterschied — in M2 sind das 87° Phasenfehler.

Nachgeprüft an Stationen, die **beides** haben, stationseigene Part-III-Konstanten und
Part-II-Differenzen (Phasen dafür auf Weltzeit umrechnen, sonst vergleicht man
über verschiedene Meridiane):

| Gruppe | dz | Fehler g(M2) ohne Korrektur | mit Korrektur |
|---|---:|---:|---:|
| Ägypten unter Suez (Kontrolle) | 0 h | 0.1–1.6° | 0.1–1.6° |
| Saudi-Arabien unter Suez | −1 h | 27.6–29.0° | 0.0–1.4° |

Die Zone jedes Standardhafens steht als `ZONE_STD` in
`py/rebuild_np203_transfer.py`, die je Seite vorherrschende als `ZONE_SEITE`.

**Der Import von 2026-06 hat HHMM als Minutenzahl gelesen** — aus `−0540`
wurden −540 statt −340 Minuten. Das sind 200 Minuten und damit 96.6° in M2.
Die Umrechnung war dabei uneinheitlich (Port Beaufort `+0110` → +70 min, also
richtig), und im Roten Meer stammten einzelne Werte zusätzlich aus verschobenen
Zeilen. Mechanisch nachrechnen ließ sich das deshalb nicht; alle 167 Transfers
sind neu aus dem Scan abgeleitet.

## Wenn die Niedrigwasserspalten fehlen

Steht bei MLWN/MLWS ein ⊙, lässt sich der Hub nicht bilden. „Niedrigwasser wie
am Bezugshafen" anzunehmen sprengt den Faktor, sobald der Nipphub klein ist —
Cherbaniani Reef kam so auf fN = 4.5 und lag 0.85 m über HAT. Stattdessen wird
der Faktor gegen das **Mittelwasser** gebildet, das im Buch in der ML-Spalte
steht; der Bezugswert folgt aus dem Gruppenkopf als (MHWS + MLWS)/2:

```
fS = (MHWS_bezug + dMHWS - ML_sek) / (MHWS_bezug - ML_bezug)
```

Wo beide Spalten vorhanden sind, liefern beide Regeln dasselbe (Al Qusayr 0.40),
deshalb greift die ML-Regel nur in der Lücke.

## Wie gut trifft der Transfer?

Gemessen an sieben Stationen, die **beides** haben — stationseigene Part-III-Konstanten und
Part-II-Differenzen (Ägypten und Saudi-Arabien unter Suez, S.228):

| | mittlerer Fehler |
|---|---|
| Amplitude M2 | 0.021 m (bei 0.13–0.42 m Amplitude) |
| Phase M2 | 0.9° |

Das ist die Genauigkeitsgrenze des Verfahrens — der Part-II-Transfer ist damit
für Häfen ohne Part III eine tragfähige Quelle, solange Bezugshafen, Pegel und
Zone stimmen.

## Warum Table V Part 2 gebraucht wird

HAT ist der höchste astronomisch mögliche Wasserstand. Der über ein Jahr
vorhergesagte Maximalwert muss knapp darunter liegen. Das ist ein Test, der aus
derselben Quelle stammt wie die Daten und keine Modellannahmen braucht:

```
tide -l STATION -b 2026-01-01 -e 2027-01-01 -m s   ->  "Maximum was ..."
```

Die HAT-Werte aller NP203-Sekundärhäfen stehen transkribiert in
`harmonics/help/np203_table5_part2_hat.json`; `py/hat_test_np203.py` prüft damit
die ganze Datei auf einen Rutsch (Toleranz **+0.30 m plus die Amplituden der
abgeleiteten N2/K2** nach oben, −1.00 m nach unten).

Der Zuschlag für N2/K2 ist kein Aufweichen des Tests, sondern die Korrektur
eines Äpfel-mit-Birnen-Vergleichs: ATT rechnet HAT aus M2, S2, K1 und O1, wir
synthetisieren mit sechs. Jede zusätzliche Konstituente kann den Jahresgipfel
über den Buch-HAT heben, und zwar proportional zu ihrer Amplitude — bei kleinem
Hub um Zentimeter, beim größten Hafen des Bandes um vier Dezimeter. Der feste
Zuschlag benachteiligte deshalb systematisch die Großhub-Stationen.

Verlauf über dieselbe Datei: **69** auffällig vor dem Part-III-Import, **38**
danach, **22** nach der Neuableitung Madagaskars, **13** nach der Umstellung
auf den richtigen Bezugshafen, **12** seit alle 167 Transfers neu aus dem Scan
abgeleitet sind (445 geprüfte Stationen, Stand 2026-08-01).

Von den verbleibenden 12 sind mehrere **Widersprüche im Buch selbst**, keine
Fehler bei uns. Beispiele, jeweils gegen den Scan geprüft:

| att | Station | HAT im Buch | aus den Part-II-Differenzen |
|---|---|---:|---:|
| 3977 | Assomption Island | 4.6 m | MHWS 3.0 m → HAT ≈ 3.4 m |
| 4174 | Ghubbat Hashish | 4.0 m | MHWS 2.6 m, Nachbarn 2.9–3.1 m |
| 4178 | Ras Sheiblah | 4.0 m | dito |

Beide Oman-Zeilen tragen im Buch `dx` (Differenzen approximativ, ML abgeleitet).

**Achtung beim Aufruf:** `HFILE_PATH` allein genügt nicht — das Skript setzt die
Variable für `tide` selbst. Die zu prüfende TCD als Argument übergeben, sonst
wird stillschweigend die alte aus `binary/` getestet.

**Nicht** geeignet ist die Summe aller Amplituden plus Z0: Sie ist eine obere
Schranke, die nie erreicht wird, und meldet Fehlalarme (Suhar schien 0.5 m zu
hoch, liegt tatsächlich 0.3 m unter HAT).

## Part III der Standardhäfen — gegen den Scan geprüft (2026-08-02)

Anlass waren die beiden HAT-Ausreißer 4279 Bandar-e Mahshahr (+0.42 m) und
4325 Kori Creek Entrance (+0.91 m). Beide hatten verschiedene Ursachen, und
die zweite reichte weit über die eine Station hinaus.

**Kori Creek war falsch abgeschrieben.** Buch (2015 *und* 2002, Ziffer für
Ziffer identisch): M2 349/1.00, S2 030/0.32, K1 064/0.37. In der Datei stand
M2 100/1.00, S2 132/0.64, K1 037/0.74. Das Muster ist immer dasselbe — eine
Amplitude landet als Phase (`1.00` → 100), eine Phase als Amplitude
(`074` → 0.74). Der Import vom 20260615 hat also spaltenweise verrutscht.

Daraufhin **alle 107 Standardhäfen gegen die Scanseiten S.240–249 gelesen**,
zusätzlich gegen die OCR des 2002er Bandes gegengeprüft (beide Ausgaben
stimmen in Part III fast überall überein, siehe unten). Ergebnis: **32 der
107 Stationen** wichen in mindestens einer Zahl ab, meist in genau einer,
bei 4325/4334/4340 in drei bis vier. Richtigstellung in
`py/fix_np203_part3_gegen_2015.py`, die Buchwerte stehen dort als `BUCH`.

**Zweiter Fund: die N2-Inferenz lief über den Nullpunkt aus dem Ruder.**

```
g_N2 = g_M2 − 0.536 · (g_S2 − g_M2)
```

verlangt die *kleine* Phasendifferenz. Steht M2 bei 343° und S2 bei 51°, ist
die rohe Differenz −292° statt +68°, und die N2-Phase liegt **167° daneben**.
Das traf **25 der 102 Stationen mit Inferenz**. Die Differenz gehört auf
(−180, 180] normiert:

```python
d = (gs - gm + 180) % 360 - 180
```

**Mahshahr dagegen ist in Ordnung.** Die Konstanten stimmen exakt mit S.246
(Z0 3.24, M2 343/1.54, S2 051/0.53, K1 314/0.53, O1 270/0.31), S.W.-Spalten
leer. Der Überschuss kommt allein aus den zwei Konstituenten, die wir mehr
haben als das Buch: ohne N2/K2 liegt der Jahresgipfel bei 5.83 m (+0.13),
mit ihnen bei 6.13 m (+0.43). Mahshahr hat mit 2.91 m die größte
Amplitudensumme des Bandes, deshalb schlägt der Zuschlag dort am stärksten
durch — daraus die neue, amplitudenabhängige Toleranz des HAT-Tests.

Stand danach: **107 Stationen geprüft, 0 auffällig.**

## Table VI — erledigt für NP203 (2026-08-01)

Bei zwölf Häfen mit starkem Flachwassereinfluss schwankt das Mittelwasser im
Vierzehntagerhythmus. Das Buch gibt korrigierte ML-Werte für den Springtag und
für jeden Tag davor/danach; Part II schreibt bei diesen Häfen ein `w` in die
ML-Spalte. In XTide ist das die Konstituente **MSf** (1.0158958 °/h).

**Die Buchtabelle ist eine reine Kosinuskurve** mit der MSf-Periode
(14.765 Tage) — nachgerechnet weicht sie um höchstens 0.031 m ab. Damit ist die
Umsetzung eindeutig:

```
Amplitude = (ML_Springtag − ML_+7Tage) / 2
Z0        = Mittel beider  (steht als "Average ML" in der Tabelle)
```

Die Phase folgt daraus, dass das ML-Maximum auf den Springtag fällt. Springtide
heißt, M2 und S2 sind in Phase, also `σ_MSf·t + V_MSf = g_S2 − g_M2` (denn
S2 − M2 = MSf). Das MSf-Glied hat sein Maximum bei `σ_MSf·t + V_MSf = g_MSf`,
also:

```
g_MSf = g_S2 − g_M2
```

Das ist unabhängig von der Meridiankonvention, weil alle drei Phasen in
derselben stehen. Gegenprobe: Das Buch sagt, der Springtag liege x Tage nach
Neu- und Vollmond (x = 2 hier), also g_MSf = 2 · 24.38° = 48.8°. Bei den Häfen
mit stationseigenen Part-III-Konstanten kommt `g_S2 − g_M2` auf 1.93 bis 2.01 Tage —
der Befund des Buches wird bestätigt.

| att | Station | ML Springs | ML +7 Tage | MSf-Amplitude | g |
|---|---|---:|---:|---:|---:|
| 4326 | Lakhpat, Gujarat | 2.70 | 2.36 | 0.170 | 49.0° |
| 4327 | Godia Creek, Gujarat | 2.00 | 1.80 | 0.100 | 37.0° |
| 4349 | Dahej Bandar, Gujarat | 5.20 | 4.60 | 0.300 | 47.0° |
| 4350 | Ambetha, Gujarat | 4.38 | 4.06 | 0.160 | 41.0° |
| 4362 | Nava (Karanja), Maharashtra | 2.68 | 2.50 | 0.090 | 42.0° |
| 4472 | Kushabhadra River, Odisha | 1.24 | 1.08 | 0.080 | 43.0° |
| 4476 | Chandbali, Odisha | 1.88 | 1.66 | 0.110 | 47.0° |
| 4484 | Diamond Harbour, West Bengal | 3.47 | 3.13 | 0.170 | 48.0° |
| 4488 | Kolkata (Garden Reach) | 3.46 | 2.92 | 0.270 | 47.0° |

Werkzeug: `py/add_np203_table6_msf.py`.

Nachgeprüft an Kolkata über zwei Monate stündlicher Vorhersage: Das Tagesmittel
schwankt um 0.53 m (Buch 0.54 m), und sein Maximum fällt in jeder Periode auf
±1 Tag mit dem größten Tageshub zusammen — genau die Aussage des Buches.

Nicht in der Sammlung: **4346** Bhavnagar und **4354** Tapi River (Hazira) sind
Standardhäfen, für die ATT keine Konstanten druckt; **4475a** Dhamra fehlt uns
ganz. Ebenso fehlt 4353a Hazira aus Part II S.234.

## Part IIIa (Ströme) — erledigt für NP203 (2026-08-01)

S.252/253 sind **nicht** Teil von Part III, sondern Part IIIa: harmonische
Konstanten für **Gezeitenströme** in Knoten. Das Buch nennt dort keine
Ortsnamen, nur Nummer und Position, und je Station **zwei** Zeilen — eine für
die Nord-, eine für die Ostkomponente.

Unsere 68 Strömungsstationen in `harmonics_att_np203_currents.txt` stammen aus
der Ausgabe **2002** und waren nie gegen den 2015er Scan geprüft. Ergebnis des
Abgleichs: von den 30 Buchstationen im NP203-Gebiet lagen 28 bei uns, auf
**0.25 km** genau und mit übereinstimmenden Werten.

**Wie aus zwei Zeilen eine XTide-Station wird.** XTide kennt nur eine
eindimensionale Stromachse. Der Rechenweg der Ausgabe 2002 ließ sich aus der
Datei rekonstruieren und an 421a, 421b und 422b in allen vier Konstituenten
exakt nachrechnen:

```
1. Stromellipse aus M2:
     W+ = 0.5·(Ae·e^(−i·ge) + i·An·e^(−i·gn))
     W− = 0.5·(Ae·e^(+i·ge) + i·An·e^(+i·gn))
   Hauptachsenwinkel  θ = 0.5·(arg W+ + arg W−),  Peilung = (90 − θ°) mod 360
   Elliptizität       e = (|W+| − |W−|) / (|W+| + |W−|)

2. ALLE Konstituenten auf diese eine Achse projizieren:
     z = cos θ · Ae·e^(−i·ge) + sin θ · An·e^(−i·gn)
     Amplitude = |z|,  Phase = (−arg z) mod 360

3. N2 = 0.19·M2, K2 = 0.27·S2 (NP203 führt nur M2/S2/K1/O1).
   Z0 (Reststrom) wird ebenso projiziert.
```

Entscheidend ist Schritt 2: Die Achse kommt **allein aus M2**, alle übrigen
Konstituenten werden auf sie projiziert. Ein erster Versuch, jede Konstituente
über ihre eigene Ellipse zu drehen, traf nur M2. Bei `|e| > 0.25` bekommt die
Station ein `# rotary_caveat:` — die 1D-Darstellung unterschätzt dann die
Geschwindigkeit und zeigt Stillwasser, das es nicht gibt.

**Zwei Nummernbefunde:**

- **426c/426d** (beide vor Al-Khafji) fehlten in der Ausgabe 2002 und sind
  jetzt ergänzt: `py/add_np203_part3a_fehlende.py`.
- Unser „Khowr-e Musa, Iran Current" trug **426c**, liegt aber exakt auf der
  Buchposition von **426e** (29° 56.9′ N / 49° 07.6′ E) — 162 km nördlich des
  echten 426c. Nummer korrigiert.

**Die übrigen 40 Stationen** (Singapur, Riau, Bangka, Philippinen, Sulawesi,
Lombok, Irian Jaya, Nummern 470–551) sind korrekt gekennzeichnet — siehe den
nächsten Abschnitt.

## Der Band ist zwischen 2002 und 2015 geschrumpft

Die 40 fernöstlichen Strömungsstationen sahen zunächst falsch etikettiert aus.
Sie sind es nicht. Das Vorwort der Ausgabe 2002 sagt:

> VOLUME 3: **INDIAN OCEAN AND SOUTH CHINA SEA** (including Tidal Stream Tables)

Deren Part IIIa steht auf S.340–342 und läuft von 415 bis 551 — Rotes Meer,
Golf, Oman, dann Singapur, Malaysia, Philippinen, Borneo, Sulawesi, Indonesien,
Irian Jaya. Die Werte in unserer Datei stimmen Ziffer für Ziffer mit dieser
Seite überein (Stichprobe 496: 10° 41.0′ N / 122° 35.0′ E, M2 243°/1.54 kn).

Die Ausgabe **2015** ist auf den Indischen Ozean zurückgeschnitten:

| | 2002 | 2015 |
|---|---|---|
| Part IIIa | S.340–342, Nr. 415–551 | S.252–253, Nr. 415–429a |
| Part III | S.312–339, bis Irian Jaya | S.240–249, bis Myanmar |
| Sekundärhäfen | Part II bis weit über 4491 | endet bei 4491 Canning Town |
| Standardhäfen (Table V Part 1) | — | endet bei 4539 Bassein River |

Also: nichts zu reparieren. Die Quellenzeile nennt bereits die Ausgabe, und die
beiden Ausgaben stehen nebeneinander in derselben Datei.

**Der Band 2002 liegt vollständig vor** — `tide_tables/att/np203_2002_vollband.pdf`.
Darin steckt Material, das wir noch nirgends haben:

- **Part III für Südchinesisches Meer und Indonesien** (S.321–339, Nummern
  ~4500–5400+): stationseigene Konstanten für Malakkastraße, Sumatra, Java,
  Bali, Borneo, Philippinen. In keiner unserer Sammlungen.
- **Part II derselben Region** (S.264–311).
- **4311 Gugsar/Koksar** hat 2002 stationseigene Konstanten (S.319) — bei uns
  der letzte Part-II-Transfer dieses Küstenabschnitts.
- **4276A Abadan schließt der Band 2002 nicht**: dort trägt 4276a „Khowr-e Musa
  Outer Platform", Abadan fehlt. Die Lücke bleibt.

OCR von Part II und Part III liegt bereits vor: `tide_tables/yemen/ocr/part{2,3}_full.txt`.

## Die beiden letzten NP203-Lücken — geschlossen (2026-08-03)

**4322 Karachi (Entrance)** fehlte in der ATT-Sammlung komplett — ausgerechnet
der Bezugshafen der Gruppe 4322a bis 4322e. Übersehen worden war er, weil
„Karachi, Pakistan" in classic_original, TICON und UTide steht; die
Lückenprüfung nach att-Nummern hat ihn deshalb nicht als fehlend gemeldet.
Konstanten aus Part III S.247 (Z0 1.67, M2 305/0.80, S2 344/0.28, K1 058/0.40,
O1 045/0.21), Position aus Part II S.234. Gegenprobe auf GMT gerechnet:

| Quelle | M2 | Phase | K1 | O1 |
|---|---:|---:|---:|---:|
| ATT (Buch) | 0.80 | 160.1° | 0.40 | 0.21 |
| TICON-4 | 0.80 | 157.4° | 0.40 | 0.20 |
| UTide | 0.80 | 158.0° | 0.40 | 0.20 |
| classic 1997 | 0.79 | 163.1° | 0.40 | 0.20 |

**4276A Abadan** ist der Sonderfall: die Ausgabe 2015 führt ihn als
**Standardhafen** (Table V Part 1: 2.0 / 1.6 / 0.6 / 0.6, MSL 1.2, HAT 2.6),
druckt aber **keine harmonischen Konstanten** — Part III springt von 4271 Al
Basrah direkt zu 4276b Khowr-e Musa Approaches. Aus dem Band allein ist er
deshalb nicht zu bauen.

Die Ausgabe **2002** löst es: dort ist Abadan noch **Sekundärhafen Nr. 4270**
mit Differenzen auf 4268 Shatt al Arab Outer Bar — +0250 / +0345,
−1.0 −0.8 −0.7 +0.2, ML 1.22. Die Probe ist zwingend: auf die publizierten
Pegel des Bezugshafens angewendet (3.0 / 2.4 / 1.3 / 0.4) ergibt das
**2.0 / 1.6 / 0.6 / 0.6** — genau die Pegel, die die Ausgabe 2015 für Abadan
druckt. Beide Ausgaben sind sich einig, der Transfer reproduziert das Buch.
fS 0.538, fN 0.909, dt 198 min. `py/add_np203_karachi_abadan.py`.

HAT-Test danach: Karachi −0.18 m, Abadan −0.31 m. Stand jetzt
**108 Standardhäfen / 0 auffällig** und **480 Sekundärhäfen / 12 auffällig**.

## Südchinesisches Meer aus dem 2002er Band — erledigt (2026-08-02)

Die Ausgabe 2002 reicht bis Irian Jaya und Vietnam, die Ausgabe 2015 nur bis
Myanmar. Für den ganzen Bereich dahinter hatten wir **keine einzige Station**
(nur 4490 und 4491 existierten). Jetzt:
**`harmonics/att/harmonics_att_np203_scs.txt`, 791 Stationen.**

| Land | Stationen | | Land | Stationen |
|---|---:|---|---|---:|
| Indonesien | 356 | | Bangladesch | 16 |
| Philippinen | 140 | | Brunei | 9 |
| Malaysia | 117 | | Singapur | 8 |
| Myanmar | 44 | | Kambodscha | 3 |
| Vietnam | 42 | | Australien (Cocos, Christmas) | 2 |
| Thailand | 33 | | Spratly/Scarborough | 2 |
| Indien (Andamanen/Nikobaren) | 18 | | Paracel-Inseln | 1 |

**Die OCR war hier unbrauchbar** — von 849 Part-III-Zeilen ließen sich 101
parsen, und die kaputten sind nicht als kaputt erkennbar (`4982` statt `4282`,
`0339` statt `0.33`). Alles von den Scanseiten abgelesen, in zwei Dateien:

- `harmonics/help/np203_2002_part3_scs.tsv` — Konstanten, Buchseiten 322–338
- `harmonics/help/np203_2002_part2_scs_pos.tsv` — Position und ML, S. 281–309

Part III führt **keine Koordinaten**; die stehen nur in Part II, ebenso das ML
für die Häfen, bei denen in Part III `w` (Table VI) steht. Beide Teile decken
sich exakt: 791 Nummern, keine ohne Gegenstück.

**Trick für Part II:** nur die gebrauchten Spalten ausschneiden und
nebeneinandersetzen, dann passt eine ganze Buchseite lesbar in ein Bild statt
in drei:

```python
L=fitz.Rect(16,45,305,800)   # Nr, Ort, Lat, Long
R=fitz.Rect(498,45,578,800)  # Z0
pg.show_pdf_page(fitz.Rect(0,0,L.width,L.height), src, p, clip=L)
pg.show_pdf_page(fitz.Rect(L.width+10,0,L.width+10+R.width,L.height), src, p, clip=R)
```

**Prüfung ohne Table V.** Für dieses Gebiet gibt es keine Table V, der HAT-Test
entfällt. Stattdessen gegen die unabhängigen Sammlungen: 421 der neuen
Stationen liegen näher als 3 km an einer Station aus classic/ticon/utide/noaa.
Dabei muss man **auf denselben Meridian umrechnen** — die ATT-Stationen tragen
den Zonenmeridian (`+08:00 :Asia/Makassar`), die anderen Sammlungen GMT
(`+00:00 :Asia/Makassar`):

```
g_Zone = g_GMT + omega * Zonenstunden        omega(M2) = 28.9841 Grad/h
```

Danach: mittlere Abweichung **0.03 m** in der M2-Amplitude und **4.6°** in der
Phase. Bei classic, classic_original und TICON (71 Paare) weicht keine einzige
Phase um mehr als 60° ab. Die 35 Ausreißer stammen alle von NOAA-Table-2-
Transfers, und zwar dort, wo M2 winzig ist (Golf von Tonkin) und der Transfer
von einem weit entfernten Bezugshafen kommt — die Buchwerte sind dort die
besseren.

73 Stationsnamen kollidieren wörtlich mit anderen Sammlungen (Manila, Cebu,
Haiphong …). Das ist im Bestand schon so — „Cebu, Philippines" steht bereits
dreifach in classic_original, ticon und utide — und bleibt so.

## Part-II-Transfers desselben Gebiets — erledigt (2026-08-04)

Alle 29 Part-II-Seiten (PDF 117–145 = Buch 281–309) einzeln vom Scan gelesen.
Ergebnis: **71 Sekundärhäfen ohne eigene Konstanten**, davon **44 gerechnet** →
`harmonics/att/harmonics_att_np203_scs_secondary.txt`.
Transkription: `harmonics/help/np203_2002_part2_scs_transfer.tsv`,
Bauskript `py/build_np203_scs_transfer.py`.

**Die OCR taugt hier nur als Suchraster, nicht als Quelle.** Sie übersah 4703a
und 5156c, erfand 4708a, 5161, 5163b, 5044 und 5197 und meldete „5495" auf fünf
Seiten, auf denen die Nummer nicht steht. Nur seitenweises Lesen ist belastbar.

**Drei Differenztypen, aber nur zwei Rechenwege.** Neben semidiurn (MHWS…MLWS)
und diurn (MHHW…MLLW) druckt das Buch im Sungai-Sarawak- und im Mekong-Gebiet
eine **gemischte** Beschriftung „MHW / LLW" über den Spalten MHHW/MLHW/MHLW/MLLW
(bei 400 dpi geprüft; die Kopfzeile von PDF 133 trägt sie selbst). Das betrifft
aber nur die beiden *Zeit*spalten, und beide Zeitdifferenzen werden ohnehin zu
einer mittleren Verzögerung gemittelt — für die Rechnung zählt allein, welche
vier *Höhen* gemeint sind. Also: Regime S wie bisher, Regime D/M über die
Zerlegung `A = MHHW−MLLW = 2H+2D`, `B = MLHW−MHLW = 2H−2D`.

**Kreis ≠ Dreieck.** ⊙ heißt „No data" (Wert fehlt), △ heißt „Tide is usually
diurnal" (Größe dort nicht anwendbar, MHHW/MLLW sind gedruckt). Wer beides
gleich behandelt, verliert 4990, 5111, 7000 und 7002 grundlos.

**27 nicht rechenbar** — das Buch druckt dort keine Höhen- oder Zeitdifferenzen.
Fast alles Mekong-Delta: bis Pnom Penh und Kompon-Luom gibt es Zeitdifferenzen,
aber keine Höhen und kein ML. Von der ganzen Strecke bleiben nur 6934 Cua Soirap
und 6943 Ho Chi Minh City.

**Zwei tote Verweise in der Ausgabe 2002:** 6878 Hua Hin und 6979 Dong Hoi
tragen „p — use harmonic constants (see Part III)", stehen dort aber nicht
(Part III springt 6876→6880 bzw. 6976→6980). Buchfehler, keine
Transkriptionslücke.

**Prüfung** (`py/check_np203_scs_transfer.py`, `..._extern.py`): gegen die
unabhängigen Sammlungen im 10-km-Umkreis 9 Paare, mittlere Abweichung
**0.13 m** in der M2-Amplitude und **26°** in der Phase. Genau eine Station über
60°: **4911 Geting**, +92° gegen eine gemessene TICON4-Station 1.6 km entfernt.
Das Buch markiert Getings Zeitdifferenzen selbst mit „t" (approximate) und
druckt für Tumpat 8 km weiter +0026/+0013 statt +0350/+0340. Die Station steht
mit Warnvermerk und `confidence: 3` in der Datei; für Navigation unbrauchbar.

Beim Vergleich **beide Seiten auf GMT bringen**, `g_GMT = g_Zone − ω·Zonenstunden`.
Nur die externe Seite umzurechnen ergibt bei +08:00 einen Scheinversatz von
28.98°/h · 8 h = 232° ≡ −128°, der wie ein Datenfehler aussieht.

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
py/check_np203_bezug.py         Bezugshäfen gegen die Gruppenköpfe prüfen
py/rebuild_np203_transfer.py    Transfer neu ableiten (richtiger Bezug, publizierte Pegel)
py/add_np203_table6_msf.py      Table VI -> MSf (vierzehntägiges Mittelwasser)
py/add_np203_fehlende.py        fehlende Buchstationen anlegen (Part III oder Transfer)
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

## Vollständigkeit: Lückenprüfung gegen die Buchnummern

Am 2026-08-01 alle att-Nummern der Part-II-Seiten 222–230 und 233–237 gegen
unsere Dateien abgeglichen — **54 Lücken**, die sich sauber in drei Gruppen
teilen:

| | Anzahl | Ergebnis |
|---|---:|---|
| Standardhäfen | 27 | **nichts zu tun** — ATT druckt für sie keine Konstanten, und alle 27 liegen bereits in anderen Sammlungen (utide, ticon4, classic, noaa). Es fehlt nur die ATT-Nummer, nicht die Station. |
| Sekundärhäfen mit Part III | 18 | angelegt, stationseigene Konstanten |
| Sekundärhäfen ohne Part III | 9 | 3 angelegt (Transfer), 6 bewusst nicht |

Die sechs nicht angelegten geben im Buch **weder Höhendifferenzen noch ML**:
3828 Mchenga, 3840 Moma River Bar, 3883 Maravoai, 4371 Angria Bank,
4478 Burhabalang River Entrance, 4487 Akra Semaphore. Ohne ML gibt es kein
Datum — die Station wäre nur der um einen Zeitversatz verschobene Bezugshafen.
(Zwei Altfälle derselben Art stehen schon in der Datei: 3822 Pungue River Bar
und 3824 Mapanda. Sie bleiben, aber es kommen keine neuen dazu.)

Kontrolle der Zeilenzuordnung beim Anlegen: Bei allen 18 Part-III-Stationen
stimmt das ML aus Part II **exakt** mit dem aus Part III überein. Alle 21 neuen
Stationen bestehen den HAT-Test (schlechtester Wert −0.95 m bei Hazira, dessen
Zeitdifferenz das Buch nicht angibt).

Werkzeug: `py/add_np203_fehlende.py`.

**Nachtrag 2026-08-01, Seiten 231/232/238 — damit ist NP203 Part II vollständig
abgeglichen.** Seite 238 ist eine reine *Notes*-Seite ohne Stationen (sie löst
das `★` auf). Auf 231 und 232 stehen 92 Buchnummern, neun davon fehlen bei uns:

| att | | warum nicht angelegt |
|---|---|---|
| 4252 | Mina Salman | Standardhafen, liegt in classic/ticon4 |
| 4254 | Ras Tannurah | Standardhafen, liegt in utide |
| 4261 | Mina az Zawr | Standardhafen, liegt in classic |
| 4276A | **Abadan** | Standardhafen — **in keiner Sammlung vorhanden** |
| 4272–4276 | Qarmat Ali Bar, Nahr Umr, Shafi Creek, Odin Point, Qurna | Buch gibt weder Höhendifferenz noch ML (Shatt al Arab flussaufwärts) |

Abadan ist damit die einzige echte Lücke im ganzen Band, die sich nicht aus
den vorhandenen Quellen schließen lässt.

Die `★`-Notizen auf S.238 erklären nebenbei zwei hartnäckige HAT-Ausreißer:
Im **River Hugli** (4484–4488) läuft bei Springtiden eine **Flutwelle** auf, die
bei Kidderpore 1.2 m und bei Chinsura 1.5 m erreicht; in der **Cambay Channel /
Mahi River** (4348) ebenso. Eine Bore ist stark nichtlinear und von der
harmonischen Methode grundsätzlich nicht darstellbar — dass 4488 Kolkata
(−1.11 m) und 4352 Bharuch (−2.52 m) unter HAT bleiben, ist damit keine
Schwäche unserer Ableitung, sondern eine Grenze des Verfahrens.

## Reihenfolge beim Einlesen eines Bandes

1. **Part II** — Nummern, Namen, Koordinaten, Differenzen. Nummernfolge gegen den
   Scan prüfen, bevor Werte übernommen werden.
2. **Part III** — wo vorhanden, ersetzt es den Transfer vollständig. Meridian auf
   die im Seitenkopf angegebene Zone setzen, N2/K2 inferieren, M4/M6 aus f4/f6.
3. **Table V Part 1** — Bezugswerte für die Stationen, die weiter aus Part II kommen.
4. **Table V Part 2** — HAT-Test über alle Stationen des Bandes.
5. **Table VI** — MSf für die dort gelisteten Häfen.

## NP202 (Ausgabe 2015) — Table IV, V und VI aus `np202_iv_vi.pdf` (2026-08-04)

Der Scan hat 21 Seiten, davon 19 verschiedene: **S13 und S14 sind Doppelscans
von S11 und S12** (Kopf und Fuß zeilengleich). Aufbau: Table IV auf xxxvi/xxxvii,
Table V Part 1 auf drei Seiten, Table V Part 2 auf fünfzehn, Table VI auf einer.
Zwischen den Buchnummern **1694 und 2307** klafft eine Lücke im Scan (Iberien,
Mittelmeer, Westafrika, Südamerika); dort haben wir ebenfalls keine Stationen.

- **Table IV** ist neu — so eine Größe gab es in keinem anderen Band:
  *Height in metres of Chart Datum relative to the Land Levelling System*.
  162 Häfen von København bis Alexandria plus die Legende der 13 Höhensysteme,
  in `np202_2015_table4_chartdatum.tsv`. Umrechnung einer XTide-Vorhersage in
  Landeshöhe: `h_Land = h_Kartennull + height`. Im gesamten XTide-Bestand haben
  **98 der 162** ein Gegenstück (32 deutsche, 26 niederländische, 26 französische),
  verteilt über NOAA EUTT, TICON4, UTide, DWF und Pierre Lavergne — beim Suchen
  unbedingt das Land mitprüfen, sonst fängt man sich „Port Louis, British
  Columbia" und „Bath, Maine" ein.
- **Table V Part 2**: neun der fünfzehn Seiten transkribiert, nämlich die, auf
  denen unsere Stationen liegen (`np202_2015_table5_part2_hat.tsv`, 978 Zeilen).
  Die übrigen sechs enthalten keine.

**Die Zuordnung muss über den NAMEN laufen, nicht über die Nummer.** Unsere
NP202-Nummerierung weicht an 17 Stellen vom Buch ab, teils um eine Stelle
verschoben (unser 2547 Wide Opening = Buch 2546; unser 2548 Ship Channel =
Buch 2547; Seine ab 1588; Oslofjord 1295a–c). Alle Fälle stehen in
`py/hat_test_np202.py` unter `VERSATZ`, mehrere über die Koordinaten bestätigt.

**Der HAT-Test für NP202 legt einen Systemfehler in den Part-II-Transfers frei:**
415 geprüft, **90 auffällig** (NP203 zur Einordnung: 480/12).

> **Korrektur 2026-08-05.** Die hier ursprünglich notierte Ursache — „49 Transfers
> mit einem Bezugshafen weiter als 1500 km entfernt" — war **falsch**. In NP202
> sind die Höhenspalten **Differenzen in Metern** („HEIGHT DIFFERENCES (IN
> METRES)"), keine Faktoren. Die Entfernung zum Bezugshafen ist deshalb belanglos:
> das Buch nimmt bewusst Helgoland für die sibirische Arktis, Galveston für die
> Kleinen Antillen, Port of Spain für Nicaragua. Was wie ein Fehler aussah, ist
> die Systematik der Vorlage. Der wirkliche Befund steht unten.

## NP202 Part II neu abgeleitet (2026-08-05)

Aus `np202_2015_secondary_ports_p358-403.pdf` — 28 Seiten, das sind die
Buchseiten 358–383 sowie 400 und 401. Die Seiten 384–399 fehlen im Scan; dort
liegt keine unserer Stationen. Ergebnis zwei neue Hilfsdateien:

- `np202_part2_gruppenkoepfe.tsv` — welcher eingerahmte Bezugshafen für welchen
  Nummernbereich gilt, mit dessen publizierten Pegeln.
- `np202_part2_stationen.tsv` — 742 Stationszeilen mit Position, Zeit- und
  Höhendifferenzen und ML. Deckt alle 436 unserer Stationen ab.

**Drei Fehler des Imports von Juni 2026, alle behoben durch
`py/rebuild_np202_transfer.py --write`:**

1. **105 von 436 Stationen hingen am falschen Bezugshafen.** In ATT gilt der
   eingerahmte Standardhafen über einer Gruppe bis zum nächsten eingerahmten
   Kopf. Ein Standardhafen, der nur *innerhalb* der Liste an seiner
   geografischen Stelle steht („STANDARD PORT / See Table V"), ist ein Eintrag
   und kein neuer Bezug. Der Import hat ab jedem solchen Eintrag gewechselt:
   Färöer an Tórshavn statt Reykjavík, Weißes Meer an Archangelsk statt Port of
   Kem', Finnmark an Kirkenes statt Ostrow Jekaterininski, Troms an Tromsø statt
   Narvik, Vestland an Stavanger und Oslo statt Bergen. **Dieselbe Falle wie bei
   NP203 auf Seite 224.**
2. **Skalierung gegen den falschen Hub und fehlender Zonenversatz.** Die
   Zeitdifferenzen gelten zwischen den Ortszeiten beider Häfen; für die Phasen
   braucht es `dt_UT = dt_Buch + (Zone_Bezug − Zone_Sekundär)`. Bei der Finnmark
   unter Jekaterininski sind das 2 Stunden, bei Pitlekaj unter Helgoland 11.
3. **Die Galveston-Gruppe wurde in Fuß statt Meter gerechnet.** Die
   NOAA-Stationen in `harmonics-dwf-20251228-free.txt` tragen `# !units: feet`.
   Wer das übersieht, macht die ganze Gruppe um 3,28 zu groß — Kleine Antillen,
   Jungferninseln und der mexikanische Golf lagen dadurch über HAT. Als
   Gegenprobe taugt der im Gruppenkopf gedruckte Springhub: `2·(M2+S2)` sollte
   ihn auf wenige Prozent treffen. Zugleich wurde *Clear Lake* durch
   *Galveston Pier 21* ersetzt — den Pegel, den ATT als GALVESTON führt.

**Ergebnis: 415 geprüft, 4 auffällig** (vorher 90). Die Reste — 1689 Libourne
(Flusseinfluss in der Dordogne), 2360 Puerto El Roque, 2491 Oracabessa,
3432 Færingehavn — liegen alle knapp außerhalb der Toleranz.

Nebenbefund, erledigt: der alte Vermerk „(att NNNN)" nannte bei allen Stationen
die eigene Nummer statt der des Bezugshafens; die neuen Vermerke nennen die
richtige.

## Dublette 4475a Dhamra entfernt (2026-08-05)

`Dhamra, Odisha, India` (ATT 4475a, NP203 Part III S. 249) und
`Dhamra Port, Odisha, India` in `harmonics_utide_tidetables` sind **derselbe
Pegel** — UKHO-Station 4475A. Der Utide-Satz stammt aus den Gezeitentafeln des
Hafens, die genau diese Nummer nennen. Belege: M2 weicht um 2,6 %, S2 um 4,7 %,
K1 um 1,1 % ab, die Hochwasserzeiten um 3 bis 10 Minuten.

Die Buchposition 20° 48′ N / 86° 54′ E liegt 7,7 km westlich des Hafens und ist
ungenau — auf derselben Buchseite stimmen Shortt Island auf 0,0 km und Chandbali
auf 0,8 km. Der Nachweis führt über die Laufzeit: Chandbali liegt 24,7 km
flussaufwärts und hat Hochwasser 75 Minuten später, also rund 3 Minuten je
Kilometer. Läge der ATT-Pegel wirklich 7,7 km weiter oben, müsste sein
Hochwasser gut 20 Minuten *später* eintreten — gemessen sind es 9 Minuten
*früher*. Er kann also nicht oberhalb des Hafens liegen.

Der ATT-Datensatz wurde daher gelöscht (7 Konstituenten, zwei davon inferiert,
gegen 57 beim Utide-Satz). NP203 Part II hat damit eine Lücke bei 4475a; die
Begründung steht in der Notiz von `Dhamra Port`. Die Kurve des ATT-Satzes lag
rund 0,3 m tiefer, weil ihm MM und SSA (je 0,12 m) fehlten. Bestand danach:
479 statt 480 Stationen, HAT-Test unverändert 467/12.

## Dublette 4486 Moyapur entfernt, Mayapur neu verortet (2026-08-05)

`Moyapur, West Bengal, India` (ATT 4486, NP203 Part II S. 237) und
`Mayapur, West Bengal, India` in `harmonics_utide_tidetables` (Survey of India)
sind **derselbe Pegel** — eine Signalstation des Hugli-Lotsendienstes; das Buch
schreibt *Moyapur*, die Survey of India *Mayapur*.

Die UTide-Station stand auf **23,4122 N / 88,3804 E**, dem bekannten Mayapur in
Nadia, 112 km flussaufwärts. Das ist offensichtlich aus dem Namen geografisch
aufgelöst worden. Der Nachweis kommt ohne jeden ATT-Wert aus, allein aus den
Survey-of-India-Pegeln des Hugli (Hochwasserverzug nach Sagar Island Lighthouse):

| Station | Breite | HW-Verzug |
|---|---:|---:|
| Sagar Island Lighthouse | 21,66 | 0 min |
| Haldia Port Lighthouse | 21,95 | 33 min |
| Haldia | 22,03 | 63 min |
| Diamond Harbour | 22,18 | 97 min |
| Mayapur | eingetragen 23,41 | 184 min |
| Kolkata | 22,55 | 243 min |

Mayapur liegt zeitlich bei 60 % der Strecke Diamond Harbour → Kolkata, also bei
**22° 24′ N** — vier Kilometer neben der Buchangabe 22° 26′ N. Oberhalb von
Kolkata kann der Pegel nicht liegen: dort käme die Welle später an, nicht
59 Minuten früher. Auch die M2-Amplitude passt, 1,57 m liegt zwischen Diamond
Harbour (1,73) und Kolkata (1,39), nicht darüber.

Übernommen wurde die Buchposition 22,4333 / 88,1333; die ATT-Station wurde
gelöscht (6 Konstituenten aus einem Transfer gegen 57 gemessene). Bestand danach:
478 statt 479 Stationen.

**Merke:** Ortsnamen aus Tafelwerken nicht geografisch auflösen, ohne die Lage
gegen die Laufzeit der Tidewelle zu prüfen. Auf derselben Buchseite stehen mit
Gangra, Balari, Hugli Point und Akra vier weitere Semaphorstationen, die in
allgemeinen Karten nicht mehr auftauchen — dass ein Name dort nicht zu finden
ist, sagt nichts über die Richtigkeit der Position.

## Dublette Garden Reach: NOAA-Datensatz entfernt (2026-08-06)

Vier Datensätze für denselben Pegel im Hafen von Kolkata:

| Datensatz | Position | Z0 | Konstituenten | Herkunft |
|---|---|---|---|---|
| Calcutta (Garden Reach) Hooghly River, `noaa_cptt` | 22,5500 / 88,3000 | 3,1394 | 6 | NOAA Table-2-Transfer von Sagar Roads (+287 min) |
| Kolkata (Garden Reach), `att_np203_secondary` (att 4488) | 22,5500 / 88,3000 | 3,1900 | 9 | NP203 Part III |
| Kolkata (Garden Reach Khidderpore), `harmonics-1997-05-25_mod` | 22,5486 / 88,3201 | 3,2000 | 22 | ohne Quellzeile, Datum LAT |
| Kolkata (Garden Reach Khidderpore), `utide_tidetables` | 22,5486 / 88,3201 | 3,3999 | 57 | Survey of India, r²=0,9916 |

Die beiden Positionen liegen 2,1 km auseinander, nur im Längengrad. Die runden
Werte 22° 33′ N / 88° 18′ E sind eine auf volle Bogenminuten gerundete
Listenangabe, die NOAA und ATT gemeinsam geerbt haben.

**Beleg für denselben Pegel** ist der Flachwasser-Fingerabdruck. M4 entsteht erst
im Fluss, das Verhältnis M4/M2 wächst stromauf monoton:

| Station | M2 | M4 | M4/M2 | 2g(M2)−g(M4) |
|---|---|---|---|---|
| Haldia | 1,702 | 0,145 | 0,085 | 87,0° |
| Diamond Harbour | 1,731 | 0,210 | 0,121 | 89,3° |
| Mayapur | 1,572 | 0,238 | 0,151 | 90,0° |
| Garden Reach ATT | 1,260 | 0,229 | 0,181 | 78,0° |
| Garden Reach classic 1997 | 1,105 | 0,222 | 0,201 | 79,0° |
| Garden Reach utide | 1,385 | 0,237 | 0,171 | 90,9° |

Alle Garden-Reach-Sätze sitzen oberhalb von Mayapur in derselben Flussstrecke.
ATT und classic teilen `2g(M2)−g(M4)` auf 1° genau — gemeinsame
Admiralty-Abstammung, der Satz von 1997 stammt aus einer älteren Ausgabe
derselben Tafel. utide liegt bei 90,9° wie die übrigen modernen
Survey-of-India-Stationen (87–90°).

Trotzdem sind die Sätze nicht austauschbar: erstes Hochwasser am 14.09.2026
zwischen 02:50 und 03:58 (68 min Spanne), Maximum 5,27 bis 6,53 m.

**Gelöscht** wurde der NOAA-Satz `Calcutta (Garden Reach) Hooghly River` aus
`harmonics_noaa_cptt.txt` (189 Zeilen, Bestand 1593 → 1592). Er war der
schwächste der vier: ein Table-2-Transfer von Sagar Roads mit sechs
Konstituenten und ohne M4, also ohne jede Flachwasserinformation für einen Pegel
80 km flussaufwärts. Die übrigen drei behält Oliver und führt sie auf eine
gemeinsame Position und einen einheitlichen Namen zusammen.

**Zum Namen:** „Garden Reach" ist ein *Reach*, ein gerader Flussabschnitt in der
seemännischen Benennung, nach den Landhäusern mit ihren Gärten benannt, die die
Briten im 18. Jahrhundert an diesem Ufer bauten. Der Botanische Garten
(Shibpur/Howrah) liegt am anderen Ufer und flussabwärts — die Namensähnlichkeit
ist Zufall. Khidderpore Dock und Garden Reach sind zwei benachbarte Becken
derselben Hafenanlage; welches Ufer die einzelnen Positionsangaben treffen, ist
aus den Daten nicht zu entscheiden.
