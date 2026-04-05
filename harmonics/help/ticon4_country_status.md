# TICON4-Stationen: Prüfstatus nach Land

Stand: 2026-04-05 | Gesamt: 1.210 Stationen, 96 Länder

## Legende
- **Korrigiert**: Fehler gefunden und behoben (Meridian, Phasen, Koordinaten, Namen)
- **Geprüft**: Gegen Referenzdaten validiert, ggf. kleinere Korrekturen
- **Nicht geprüft**: Noch keine systematische Prüfung
- Validierung: OK / Akzeptabel / Verdächtig / FEHLER / Keine Referenz

## Korrigierte Länder (20)

| Land | Anz | Validierung | Korrekturen |
|------|-----|-------------|-------------|
| Japan | 192 | 2/0/1/39/148 | Meridian → +00:00 (172 JODC-Stationen), verifiziert vs Classic |
| Canada | 144 | 7/1/1/105/20 | Meridian → +00:00 (136 MEDS-Stationen), Koordinaten (CHS API), Namen |
| France | 57 | 1/0/6/8/41 | REFMAR Meridian → +00:00 (43 Stationen), verifiziert vs Kartverket |
| Mexico | 32 | 0/0/0/1/28 | 180°-Phaseninversion (31 Stationen), Koordinaten, Namen, Meridian -06:00 |
| Norway | 25 | 6/0/1/15/0 | NHS/CMEMS Meridian → +00:00 (19 Stationen), verifiziert vs Kartverket (Bergen 7 min) |
| Peru | 7 | 0/0/0/0/7 | Meridian → +00:00, Koordinaten |
| Argentina | 6 | 2/0/0/0/4 | Koordinaten, Namen |
| Chile | 12 | 0/0/0/0/11 | Koordinaten (5 Stationen) |
| Brazil | 13 | 0/0/0/1/12 | Koordinaten |
| Colombia | 5 | 0/0/0/0/5 | Koordinaten |
| Ecuador | 5 | 0/0/0/0/5 | Koordinaten |
| Venezuela | 1 | 0/0/0/0/1 | Koordinaten |
| Costa Rica | 4 | 1/0/0/0/3 | Koordinaten |
| Cuba | 2 | 0/0/0/0/2 | Koordinaten |
| Dominican Republic | 3 | 0/0/0/0/3 | Koordinaten |
| El Salvador | 2 | 0/0/0/0/2 | Koordinaten |
| Guatemala | 3 | 0/0/0/0/3 | Koordinaten |
| Honduras | 2 | 0/0/0/0/2 | Koordinaten |
| Jamaica | 1 | 0/0/0/0/1 | Koordinaten |
| Kiribati | 5 | 0/0/0/1/4 | Koordinaten |
| Panama | 5 | 0/0/0/0/5 | Koordinaten |
| Trinidad and Tobago | 2 | 0/0/0/0/2 | Koordinaten |

## Geprüfte Länder (10)

| Land | Anz | Validierung | Anmerkungen |
|------|-----|-------------|-------------|
| United Kingdom | 62 | 32/0/0/0/28 | Severn Bridge Koordinaten |
| Germany | 86 | 2/7/35/5/37 | WSV: CET-Offset in Phasen, +01:00 korrekt |
| Netherlands | 72 | 2/3/14/10/40 | RWS: CET-Offset in Phasen, +01:00 korrekt |
| Australia | 76 | 4/0/0/7/65 | BOM: lokaler Offset in Phasen, lokaler Meridian korrekt. FEHLER = Datenqualität |
| Denmark | 55 | 3/0/0/0/52 | DMI: CET-Offset, +01:00 korrekt |
| Belgium | 4 | 3/0/0/0/1 | CMEMS: CET-Offset, +01:00 korrekt |
| New Zealand | 28 | 1/0/0/0/27 | TTW: +12:00 verifiziert (Phasenanalyse vs Bluff/UHSLC). Bluff OK vs LINZ (1.9 min) |
| Sweden | 32 | 0/0/0/0/32 | Stationen umbenannt, Göteborg Koordinaten |
| Ireland | 14 | 1/0/2/0/11 | Dublin (River Tolka) entfernt |
| Italy | 37 | 0/0/0/0/37 | Ländername korrigiert (Italia → Italy) |

## Meridian-Konvention nach Datenquelle

| Quelle | Meridian | Verifiziert | Länder |
|--------|----------|-------------|--------|
| UHSLC (uhslc_rq/fd) | +00:00 | Ja | weltweit (195+140 Stationen) |
| MEDS | +00:00 | Ja (CHS) | Kanada (136) |
| JODC (jma/pahb/jcg/giaj) | +00:00 | Ja (Classic) | Japan (172) |
| REFMAR | +00:00 | Ja (Kartverket) | Frankreich (43) |
| NHS | +00:00 | Ja (Kartverket) | Norwegen (11) |
| CMEMS Norwegen | +00:00 | Ja | Norwegen (8) |
| BODC/CCO | +00:00 | Ja | UK (37) |
| WSV/BFG | +01:00 (CET) | Ja (BSH) | Deutschland (80) |
| RWS/RWS_hist | +01:00 (CET) | Ja | Niederlande (66) |
| DMI | +01:00 (CET) | Ja | Dänemark (3) |
| CMEMS Belgien | +01:00 (CET) | Ja | Belgien (4) |
| BOM | lokal | Ja | Australien, Pazifik (78) |
| TTW | +12:00 | Ja (Phasenanalyse) | Neuseeland (13) |
| UNAM_hist | -06:00 | Ja | Mexiko (13) |
| SMHI/ISPRA/IEO/CMEMS (andere) | lokal | Angenommen | diverse (144) |

## Nicht geprüfte Länder (65)

Keine Referenzdaten verfügbar. Meridian basiert auf angenommener Konvention der Datenquelle.

Angola(2), Antarctica(3), Bahamas(1), Bahrain(1), Bangladesh(7), Bulgaria(4),
Cape Verde(1), China(13), Cook Islands(2), Croatia(1), Curaçao(1), Djibouti(1),
Egypt(1), Estonia(8), Fiji(2), Finland(3), Ghana(2), Greece(5), Grenada(1),
Haiti(1), Hong Kong(1), Iceland(1), India(3), Indonesia(18), Iran(2),
Ivory Coast(1), Kenya(2), Madagascar(1), Malaysia(18), Maldives(4),
Mauritania(2), Mauritius(2), Mozambique(3), Myanmar(2), Namibia(1), Nauru(1),
Nigeria(2), Niue(1), Oman(3), Pakistan(1), Papua New Guinea(10),
Philippines(9), Poland(4), Portugal(12), Rep. du Congo(1), Russia(3),
Samoa(1), Senegal(1), Seychelles(2), Singapore(1), Solomon Islands(1),
South Africa(14), Spain(12), Sri Lanka(1), St. Helena(1), Taiwan(1),
Tanzania(2), Thailand(2), Tonga(1), Turkey(2), Tuvalu(1), Vanuatu(1),
Vietnam(3), Yemen(1)
