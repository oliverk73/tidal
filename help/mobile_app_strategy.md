# Mobile-App-Strategie für die Tide-Vorhersage-Website

Stand: 2026-05-11

## Ausgangslage

Die bestehende Flask-Webanwendung liefert eine Leaflet-Karte mit
~11 000 Stationen, Detail-Vorhersageseiten und mehreren Overlays
(Wellen, Niederschlag, Radar, SST, Strömungen).

`/static/manifest.webmanifest` ist bereits vorbildlich konfiguriert:
- `display: standalone`
- alle Icon-Größen (192, 512, 512-maskable)
- `theme_color`, `background_color`, `categories`, `scope`, `start_url`

Es fehlt nur ein Service Worker — dann ist die App zu ~95 % eine PWA.

## Die drei realistischen Pfade

### 1. PWA (Progressive Web App) — empfohlen für den Start

- **Was**: Service Worker hinzufügen → User können „Zum Startbildschirm
  hinzufügen", die App startet im Vollbild ohne Browser-Chrome,
  funktioniert offline (Karte gecachte Tiles, letzte Vorhersagen).
- **Aufwand**: **1–2 Tage**. ~150 Zeilen JS für den Service Worker,
  optional via Workbox-Library.
- **Pro**: Null Codeduplizierung, instant auf iOS und Android, Updates
  via Push-Refresh ohne Store-Release, kostenlos.
- **Con**: Kein App-Store-Eintrag (auf iOS schwerer entdeckbar), keine
  Push-Notifications vor iOS 16.4 (jetzt OK), Apple verbietet PWAs
  nicht aktiv, fördert sie aber auch nicht.

### 2. Capacitor obendrauf — wenn App-Store wichtig ist

- **Was**: Ionic Capacitor verpackt die bestehende Web-App in eine
  native Hülle (WebView). Distribution über Apple/Google Stores.
  Erbe von Cordova, modern gewartet.
- **Aufwand**: **1–2 Wochen** zusätzlich zur PWA. Plus laufend:
  Apple Developer 99 €/Jahr, Google Play 25 € einmalig,
  Store-Reviews bei jedem Update.
- **Pro**: Echter App-Store-Eintrag, Zugriff auf native APIs
  (GPS-Background, Push, lokale Benachrichtigungen für nächstes
  HW/LW).
- **Con**: Du betreibst plötzlich 3 Distributionen statt 1.
  Apple Review-Zyklen, Updates dauern Tage statt Sekunden.

### 3. Native (React Native / Flutter) — nicht zu empfehlen

- **Aufwand**: **Monate**. Komplette UI neu (Leaflet → MapLibre Native
  oder Mapbox SDK), Server-Endpoints anpassen.
- Lohnt sich nur, wenn man wirklich native Performance bei einer
  Komponente braucht — bei einer Karte+Charts-App nicht der Fall.

### Was kein Mobile-Pfad ist

**Docker** ist hier off-topic — Container sind ein
Server-Deployment-Tool, kein Mobile-Pfad.

## Empfehlung

1. **Jetzt**: PWA komplett machen (Service Worker, Offline-Cache,
   install-prompt). Das holt man in 1–2 Tagen ab.
2. **Wenn nach 3 Monaten** klar wird, dass Nutzer App Stores erwarten
   oder Push-Notifications für HW/LW gewünscht sind: Capacitor
   obendrauf packen — die ganze Web-App wird ohne Anpassung
   mitgenommen.

## Offene Fragen vor Schritt 1

- Was soll **offline** funktionieren — nur die zuletzt besuchte
  Station, oder soll man alle gerade gecachten Stationen offline
  durchblättern können?
- Soll's später **Push-Notifications** geben („Niedrigwasser in 2 h
  an deinem Lieblingsstrand")?
