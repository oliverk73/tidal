#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vorschlagsseite fuer die NMDIS-Namen und -Positionen.

Grundlage ist harmonics/help/nmdis_namen_vorschlag.json
(py/nmdis_namen_vorschlag.py). Je Satz zeigt die Seite den chinesischen
Originalnamen, den heutigen Namen aus der Portalumschrift, die
GeoNames-Treffer zum chinesischen Namen und die Hafenanlagen aus
OpenStreetMap -- dazu eine Karte mit allen Punkten.

Entschieden wird je Satz durch Anklicken eines Vorschlags (Name und/oder
Position) oder durch eigenen Text. Die Entscheidungen stehen in der
Artifact-Datenbank, Sammlung "nmdis", ein Dokument je Stationscode.

Usage: python3 py/nmdis_seite_bauen.py [--aus <datei.html>] [--nur-offen]
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_check import ROOT                                       # noqa: E402

QUELLE = os.path.join(ROOT, 'harmonics/help/nmdis_namen_vorschlag.json')

SEITE = r'''<title>NMDIS-Namenswerkstatt</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Serif:wght@600&family=Noto+Sans+SC:wght@400;500&display=swap">
<style>
:root{
  --grund:#f0efec; --flaeche:#ffffff; --flaeche2:#f7f6f3; --tinte:#1c1a16; --leise:#6b665c;
  --linie:#dcd8d0; --linie2:#ebe8e2; --akzent:#8a5a2b; --akzent-w:#f4ece2;
  --gut:#3c6b4a; --gut-w:#e6efe7; --weg:#a3402b; --schatten:0 1px 2px rgba(40,34,24,.09);
}
@media (prefers-color-scheme: dark){ :root:not([data-theme="light"]){
  --grund:#15130f; --flaeche:#1d1a15; --flaeche2:#232019; --tinte:#ece7dd; --leise:#a09a8c;
  --linie:#332e26; --linie2:#282419; --akzent:#d9a166; --akzent-w:#332617;
  --gut:#86bd95; --gut-w:#1b2b20; --weg:#e08a72; --schatten:0 1px 2px rgba(0,0,0,.45);
} }
:root[data-theme="dark"]{
  --grund:#15130f; --flaeche:#1d1a15; --flaeche2:#232019; --tinte:#ece7dd; --leise:#a09a8c;
  --linie:#332e26; --linie2:#282419; --akzent:#d9a166; --akzent-w:#332617;
  --gut:#86bd95; --gut-w:#1b2b20; --weg:#e08a72; --schatten:0 1px 2px rgba(0,0,0,.45);
}
*{box-sizing:border-box}
body{margin:0;background:var(--grund);color:var(--tinte);
  font:15px/1.5 "IBM Plex Sans",system-ui,sans-serif}
h1,h2{margin:0;text-wrap:balance}
button{font:inherit;color:inherit}
.rahmen{max-width:1420px;margin:0 auto;padding-inline:16px;padding-block:16px 26px}
header{display:flex;flex-wrap:wrap;gap:8px 20px;align-items:baseline;justify-content:space-between}
h1{font-family:"IBM Plex Serif",Georgia,serif;font-size:23px}
header p{margin:0;color:var(--leise);font-size:13px;max-width:70ch}
.speicher{font:12px/1 "IBM Plex Mono",monospace;color:var(--leise);border:1px solid var(--linie);
  border-radius:999px;padding:6px 11px;white-space:nowrap}
.speicher.an{color:var(--gut);border-color:var(--gut)}
.werkzeug{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:14px 0 10px}
input[type=search]{flex:1 1 200px;font:inherit;font-size:14px;background:var(--flaeche);color:var(--tinte);
  border:1px solid var(--linie);border-radius:3px;padding:7px 9px}
.schalter{display:flex;align-items:center;gap:6px;font-size:13px;color:var(--leise)}
.fortschritt{flex:1 1 180px;display:flex;align-items:center;gap:8px;font-size:12px;color:var(--leise)}
.balken{flex:1;height:5px;background:var(--linie2);border-radius:999px;overflow:hidden}
.balken i{display:block;height:100%;background:var(--akzent)}
.werkbank{display:grid;grid-template-columns:minmax(0,300px) minmax(0,1fr);gap:12px;align-items:start}
@media (max-width:860px){.werkbank{grid-template-columns:1fr}}
.tafel{background:var(--flaeche);border:1px solid var(--linie);border-radius:4px;box-shadow:var(--schatten)}
.liste{max-height:min(74vh,800px);overflow-y:auto}
.zeile{display:grid;grid-template-columns:7px minmax(0,1fr) auto;gap:8px;align-items:center;width:100%;
  text-align:left;background:none;border:0;border-bottom:1px solid var(--linie2);padding:7px 10px 7px 7px;cursor:pointer}
.zeile:hover{background:var(--flaeche2)}
.zeile[aria-current="true"]{background:var(--akzent-w)}
.punkt{width:7px;height:7px;border-radius:999px;background:var(--linie);justify-self:center}
.punkt.fertig{background:var(--gut)}
.zeile .nm{font-size:13.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:block}
.zeile .zh{font-family:"Noto Sans SC","IBM Plex Sans",sans-serif;font-size:12px;color:var(--leise);display:block}
.zeile .tag{font:11px/1 "IBM Plex Mono",monospace;color:var(--leise)}
.detail{padding:16px 18px 20px}
.zh-gross{font-family:"Noto Sans SC","IBM Plex Sans",sans-serif;font-size:27px;font-weight:500;line-height:1.2}
.detail h2{font-family:"IBM Plex Serif",Georgia,serif;font-size:19px;margin-top:4px}
.meta{font:12px/1.6 "IBM Plex Mono",monospace;color:var(--leise);margin-top:4px}
.meta a{color:var(--akzent)}
.spalten{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin-top:14px}
.block h3{font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--leise);margin:0 0 7px;font-weight:600}
.vorschlag{display:block;width:100%;text-align:left;background:var(--flaeche2);border:1px solid var(--linie);
  border-radius:3px;padding:8px 10px;margin-bottom:6px;cursor:pointer}
.vorschlag:hover{border-color:var(--akzent)}
.vorschlag[aria-pressed="true"]{border-color:var(--gut);background:var(--gut-w)}
.vorschlag .v1{font-size:14px}
.vorschlag .v2{font:11.5px/1.4 "IBM Plex Mono",monospace;color:var(--leise);margin-top:2px}
.kartenbox{margin-top:14px;border:1px solid var(--linie);border-radius:3px;overflow:hidden;background:var(--flaeche2)}
.kartenbox canvas{display:block;width:100%}
.legende{margin:0;padding:7px 11px;font-size:11.5px;color:var(--leise);border-top:1px solid var(--linie2)}
.pkt{display:inline-block;width:9px;height:9px;border-radius:999px;vertical-align:-1px}
.pkt.jetzt{background:var(--weg)} .pkt.geo{background:var(--akzent)} .pkt.osm{background:var(--gut)}
.eingabe{display:grid;grid-template-columns:minmax(0,2fr) minmax(0,1fr) auto auto;gap:8px;margin-top:14px}
.eingabe input{font:inherit;font-size:14px;background:var(--flaeche2);color:var(--tinte);
  border:1px solid var(--linie);border-radius:3px;padding:8px 9px;min-width:0}
.knopf{border:1px solid var(--linie);background:var(--flaeche);border-radius:3px;padding:9px 14px;cursor:pointer;font-size:14px}
.knopf.haupt{border-color:var(--gut);color:var(--gut)}
.knopf:hover{border-color:var(--akzent)}
.auswahl{font:inherit;font-size:14px;background:var(--flaeche);color:var(--tinte);
  border:1px solid var(--linie);border-radius:3px;padding:7px 9px}
.koord{font:15px/1.4 "IBM Plex Mono",monospace;margin-top:4px;user-select:all;cursor:text}
.punkt.eingetragen{background:var(--leise)}
.leer{padding:26px 18px;color:var(--leise);font-size:13.5px}
.hilfe{margin-top:12px;font-size:12px;color:var(--leise)}
.hilfe kbd{font:11px/1 "IBM Plex Mono",monospace;border:1px solid var(--linie);border-radius:2px;padding:2px 4px}
:focus-visible{outline:2px solid var(--akzent);outline-offset:2px}
</style>

<div class="rahmen">
<header>
  <div>
    <h1>NMDIS-Namenswerkstatt</h1>
    <p>Chinesische NMDIS-Pegel, die noch niemand bearbeitet hat. Vorschlaege kommen
       aus GeoNames (ueber den chinesischen Namen) und aus OpenStreetMap (Hafenanlagen bis 5 km).</p>
  </div>
  <div class="speicher" id="speicher">Speicher wird verbunden ...</div>
</header>

<div class="werkzeug">
  <input type="search" id="suche" placeholder="Name, Pinyin oder Stationscode" aria-label="Suchen">
  <select id="filter" aria-label="Auswahl" class="auswahl">
    <option value="alle">alle Pegel</option>
    <option value="offen">noch nicht angefasst</option>
    <option value="neu">neu entschieden, noch nicht eingetragen</option>
  </select>
  <label class="schalter"><input type="checkbox" id="nurgeo"> nur mit GeoNames-Treffer</label>
  <div class="fortschritt"><span id="ftext">0 von 0</span>
    <span class="balken"><i id="fbalken" style="width:0%"></i></span></div>
</div>

<div class="werkbank">
  <div class="tafel"><div class="liste" id="liste"></div></div>
  <div class="tafel"><div class="detail" id="detail"></div></div>
</div>

<p class="hilfe"><kbd>j</kbd>/<kbd>k</kbd> bewegen, <kbd>1</kbd>–<kbd>6</kbd> Vorschlag waehlen,
  <kbd>Enter</kbd> uebernehmen, <kbd>u</kbd> zuruecknehmen. Alles wird sofort gespeichert;
  Claude traegt die Entscheidungen danach in die Harmonics-Dateien ein.</p>
</div>

<script id="daten" type="application/json">__DATEN__</script>
<script>
const FAELLE = JSON.parse(document.getElementById('daten').textContent);
const stand = new Map();
let db = null, gewaehlt = null, auswahl = null;

function hesc(s){ return String(s == null ? '' : s).replace(/[&<>"]/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function dz(v){ return String(v == null ? '' : v).replace('.', ','); }
function status(t, a){ const e = document.getElementById('speicher');
  e.textContent = t; e.className = 'speicher' + (a ? ' ' + a : ''); }
function lokal(){ try{ return JSON.parse(localStorage.getItem('nmdis_namen')||'{}'); }catch(e){ return {}; } }
function lokalSchreiben(){ try{ const o={}; stand.forEach((v,k)=>o[k]=v);
  localStorage.setItem('nmdis_namen', JSON.stringify(o)); }catch(e){} }

async function speicherStarten(){
  try { db = await window.claude?.use?.('db'); } catch(e){ db = null; }
  if (!db){ status('nur in diesem Browser', 'aus'); return; }
  try {
    const snap = await db.collection('nmdis').get();
    snap.docs.forEach(d => { const v = d.data(); if (v) stand.set(d.id, v); });
    status('gespeichert', 'an'); zeichnen();
  } catch(e){ status('Speicher nicht erreichbar', 'aus'); }
}
async function merken(code, wert){
  wert = Object.assign({zeit: new Date().toISOString()}, wert);
  stand.set(code, wert); lokalSchreiben(); zeichnen();
  if (!db) return;
  try { await db.collection('nmdis').doc(code).set(wert); }
  catch(e){ status('nicht gespeichert', 'aus'); }
}

// Zustand je Pegel: 'offen' (nie entschieden), 'eingetragen' (Entscheidung steht schon in
// den Harmonics-Dateien) oder 'neu' (hier entschieden, noch nicht eingetragen).
function zustand(f){
  const e = stand.get(f.code);
  if (!e) return 'offen';
  if (f.eingetragen && (!e.zeit || e.zeit <= f.eingetragen)) return 'eingetragen';
  return 'neu';
}
function k4(v){ return (+v).toFixed(4); }

function gefiltert(){
  const q = document.getElementById('suche').value.trim().toLowerCase();
  const wahl = document.getElementById('filter').value;
  const geo = document.getElementById('nurgeo').checked;
  return FAELLE.filter(f => {
    if (wahl !== 'alle' && zustand(f) !== wahl) return false;
    if (geo && !(f.geonames || []).length) return false;
    if (q && !(f.name + ' ' + f.zh + ' ' + f.code + ' ' + f.portal).toLowerCase().includes(q)) return false;
    return true;
  });
}

function zeilen(){
  const box = document.getElementById('liste'), liste = gefiltert();
  box.innerHTML = '';
  if (!liste.length){ box.innerHTML = '<p class="leer">Nichts mehr offen.</p>'; return; }
  const frag = document.createDocumentFragment();
  liste.forEach(f => {
    const e = stand.get(f.code), z = zustand(f);
    const b = document.createElement('button');
    b.className = 'zeile'; b.setAttribute('aria-current', String(gewaehlt === f.code));
    b.innerHTML = '<span class="punkt ' + (z === 'neu' ? 'fertig' : z) + '"></span>' +
      '<span><span class="nm">' + hesc(z === 'neu' ? (e.name || f.name) : f.name.split(',')[0]) + '</span>' +
      '<span class="zh">' + hesc(f.zh) + '</span></span>' +
      '<span class="tag">' + (f.geonames.length ? f.geonames.length + '&nbsp;GN' : '&mdash;') + '</span>';
    b.onclick = () => { gewaehlt = f.code; auswahl = null; zeichnen(); };
    frag.appendChild(b);
  });
  box.appendChild(frag);
  const a = box.querySelector('[aria-current="true"]');
  if (a) a.scrollIntoView({block:'nearest'});
}

function detail(){
  const box = document.getElementById('detail');
  const f = FAELLE.find(x => x.code === gewaehlt);
  if (!f){ box.innerHTML = '<p class="leer">Waehle links einen Pegel.</p>'; return; }
  const z = zustand(f), e = z === 'neu' ? stand.get(f.code) : {};
  const osm = 'https://www.openstreetmap.org/?mlat=' + f.lat + '&mlon=' + f.lon + '#map=14/' + f.lat + '/' + f.lon;
  let html = '<div class="zh-gross">' + hesc(f.zh) + '</div>' +
    '<h2>' + hesc(f.name) + '</h2>' +
    '<div class="koord">' + k4(f.lat) + ', ' + k4(f.lon) + '</div>' +
    '<div class="meta">' + f.code + ' &middot; Portal "' + hesc(f.portal) + '"' +
    (f.raster ? ' &middot; Position auf ganzer Bogenminute' : '') + ' &middot; ' +
    ({offen: 'noch nicht angefasst', eingetragen: 'schon bearbeitet', neu: 'neu entschieden'})[z] + ' &middot; ' +
    '<a href="' + osm + '" target="_blank" rel="noreferrer">Karte</a></div>';

  html += '<div class="spalten"><div class="block"><h3>GeoNames zum chinesischen Namen</h3>';
  if (!f.geonames.length) html += '<p class="leer" style="padding:8px 0">Kein Treffer bis 15 km.</p>';
  f.geonames.forEach((g, i) => {
    html += '<button class="vorschlag" data-art="geo" data-i="' + i + '" aria-pressed="' +
      (auswahl && auswahl.art === 'geo' && auswahl.i === i) + '">' +
      '<div class="v1">' + (i + 1) + '. ' + hesc(g.name) + '</div>' +
      '<div class="v2">' + hesc(g.teil) + ' &middot; ' + g.code + ' &middot; ' + dz(g.km) + ' km &middot; ' +
      k4(g.lat) + ', ' + k4(g.lon) + '</div></button>';
  });
  html += '</div><div class="block"><h3>Hafenanlagen aus OpenStreetMap</h3>';
  if (!(f.osm || []).length) html += '<p class="leer" style="padding:8px 0">Nichts kartiert bis 5 km.</p>';
  (f.osm || []).forEach((o, i) => {
    html += '<button class="vorschlag" data-art="osm" data-i="' + i + '" aria-pressed="' +
      (auswahl && auswahl.art === 'osm' && auswahl.i === i) + '">' +
      '<div class="v1">' + hesc(o.name || '(ohne Namen)') + '</div>' +
      '<div class="v2">' + hesc(o.art) + ' &middot; ' + dz(o.km) + ' km &middot; ' +
      k4(o.lat) + ', ' + k4(o.lon) + '</div></button>';
  });
  html += '</div></div>';

  html += '<div class="kartenbox"><canvas id="karte" width="640" height="300"></canvas>' +
    '<p class="legende"><span class="pkt jetzt"></span> heutige Position &nbsp;' +
    '<span class="pkt geo"></span> GeoNames &nbsp;<span class="pkt osm"></span> OSM-Hafenanlagen ' +
    '&middot; Kueste aus der Landmaske (~1 km)</p></div>';

  const vName = e.name || (f.name.split(',')[0]);
  const vPos = e.lat ? (e.lat + ', ' + e.lon) : '';
  html += '<div class="eingabe">' +
    '<input id="fname" value="' + hesc(vName) + '" placeholder="Name ohne Land/Provinz" aria-label="Name">' +
    '<input id="fpos" value="' + hesc(vPos) + '" placeholder="lat, lon (leer = unveraendert)" aria-label="Position">' +
    '<button class="knopf haupt" id="ok">Uebernehmen</button>' +
    '<button class="knopf" id="weg">Zuruecknehmen</button></div>' +
    '<div class="meta" style="margin-top:8px">Voller Name wird: <b id="vorschau"></b></div>';
  box.innerHTML = html;

  box.querySelectorAll('.vorschlag').forEach(b => b.onclick = () => {
    const art = b.dataset.art, i = +b.dataset.i;
    auswahl = {art, i};
    const q = art === 'geo' ? f.geonames[i] : f.osm[i];
    const nf = document.getElementById('fname'), pf = document.getElementById('fpos');
    if (art === 'geo') nf.value = q.name;
    else if (q.name) nf.value = q.name;
    pf.value = q.lat + ', ' + q.lon;
    vorschau(); detailKnoepfe(f);
  });
  document.getElementById('ok').onclick = () => uebernehmen(f);
  document.getElementById('weg').onclick = () => { stand.delete(f.code); lokalSchreiben();
    if (db) db.collection('nmdis').doc(f.code).delete().catch(()=>{}); zeichnen(); };
  document.getElementById('fname').oninput = vorschau;
  vorschau();
  if (f.karte) karteZeichnen(f);
}

function detailKnoepfe(f){
  document.querySelectorAll('.vorschlag').forEach(b => b.setAttribute('aria-pressed',
    String(auswahl && auswahl.art === b.dataset.art && auswahl.i === +b.dataset.i)));
}

function vorschau(){
  const f = FAELLE.find(x => x.code === gewaehlt); if (!f) return;
  const teile = f.name.split(',').map(s => s.trim());
  const rest = teile.slice(1).join(', ');
  const n = (document.getElementById('fname') || {}).value || teile[0];
  const el = document.getElementById('vorschau');
  if (el) el.textContent = n + (rest ? ', ' + rest : '');
}

function uebernehmen(f){
  const n = document.getElementById('fname').value.trim();
  const p = document.getElementById('fpos').value.trim();
  const teile = f.name.split(',').map(s => s.trim());
  const voll = n + (teile.length > 1 ? ', ' + teile.slice(1).join(', ') : '');
  const wert = {name: n, voller_name: voll};
  if (p){
    const m = p.match(/(-?\d+[.,]?\d*)\s*,\s*(-?\d+[.,]?\d*)/);
    if (m){ wert.lat = parseFloat(m[1].replace(',', '.')); wert.lon = parseFloat(m[2].replace(',', '.')); }
  }
  merken(f.code, wert);
  const liste = gefiltert();
  const i = liste.findIndex(x => x.code === f.code);
  const naechst = i >= 0 ? liste[i + 1] : liste.find(x => zustand(x) !== 'neu');
  if (naechst){ gewaehlt = naechst.code; auswahl = null; }
  zeichnen();
}

function karteZeichnen(f){
  const c = document.getElementById('karte'); if (!c) return;
  const k = f.karte, dpr = window.devicePixelRatio || 1;
  const breite = c.parentElement.clientWidth || 640, hoehe = 300;
  c.width = breite * dpr; c.height = hoehe * dpr; c.style.height = hoehe + 'px';
  const g = c.getContext('2d'); g.scale(dpr, dpr);
  const stil = getComputedStyle(document.body);
  g.fillStyle = stil.getPropertyValue('--akzent-w') || '#eef3f6'; g.fillRect(0, 0, breite, hoehe);
  const roh = atob(k.b), bytes = new Uint8Array(roh.length);
  for (let i = 0; i < roh.length; i++) bytes[i] = roh.charCodeAt(i);
  const N = k.n, seite = Math.min(breite, hoehe);
  const x0 = (breite - seite) / 2, y0 = (hoehe - seite) / 2, zelle = seite / N;
  g.fillStyle = stil.getPropertyValue('--linie') || '#d8d3ca';
  for (let i = 0; i < N; i++) for (let j = 0; j < N; j++){
    const bit = i * N + j;
    if (bytes[bit >> 3] & (128 >> (bit & 7)))
      g.fillRect(x0 + j * zelle, y0 + i * zelle, Math.ceil(zelle), Math.ceil(zelle));
  }
  const px = (lat, lon) => [x0 + seite * (((lon - k.lon) / (2 * k.dlo)) + 0.5),
                            y0 + seite * (0.5 - ((lat - k.lat) / (2 * k.dla)))];
  const punkt = (lat, lon, farbe, r, ring) => {
    const [x, y] = px(+lat, +lon);
    if (x < x0 - 8 || x > x0 + seite + 8 || y < y0 - 8 || y > y0 + seite + 8) return;
    g.beginPath(); g.arc(x, y, r, 0, 2 * Math.PI); g.fillStyle = farbe; g.fill();
    if (ring){ g.strokeStyle = farbe; g.lineWidth = 2; g.beginPath(); g.arc(x, y, r + 4, 0, 2 * Math.PI); g.stroke(); }
  };
  (f.osm || []).forEach(o => punkt(o.lat, o.lon, stil.getPropertyValue('--gut') || '#3c6b4a', 3.5));
  (f.geonames || []).forEach(q => punkt(q.lat, q.lon, stil.getPropertyValue('--akzent') || '#8a5a2b', 4));
  punkt(f.lat, f.lon, stil.getPropertyValue('--weg') || '#a3402b', 4.5, true);
  const kmPix = seite / k.km, laenge = 5 * kmPix;
  g.strokeStyle = stil.getPropertyValue('--leise') || '#6b665c'; g.lineWidth = 1.5;
  g.beginPath(); g.moveTo(x0 + 10, y0 + seite - 12); g.lineTo(x0 + 10 + laenge, y0 + seite - 12); g.stroke();
  g.fillStyle = stil.getPropertyValue('--leise') || '#6b665c';
  g.font = '11px "IBM Plex Mono", monospace'; g.fillText('5 km', x0 + 16 + laenge, y0 + seite - 9);
}

function fortschritt(){
  const n = FAELLE.length, zahl = {offen: 0, eingetragen: 0, neu: 0};
  FAELLE.forEach(f => zahl[zustand(f)]++);
  const k = n - zahl.offen;
  document.getElementById('ftext').textContent = n + ' Pegel: ' + zahl.neu + ' neu entschieden, ' +
    zahl.eingetragen + ' schon bearbeitet, ' + zahl.offen + ' nicht angefasst';
  document.getElementById('fbalken').style.width = (n ? 100 * k / n : 0) + '%';
}

function zeichnen(){ zeilen(); detail(); fortschritt(); }

document.addEventListener('keydown', ev => {
  if (ev.target.matches('input, textarea, select')){
    if (ev.key === 'Enter'){ const f = FAELLE.find(x => x.code === gewaehlt); if (f) uebernehmen(f); }
    return;
  }
  const liste = gefiltert(), i = liste.findIndex(x => x.code === gewaehlt);
  if (ev.key === 'j' || ev.key === 'ArrowDown'){ ev.preventDefault(); gewaehlt = (liste[i+1] || liste[0] || {}).code; auswahl = null; zeichnen(); }
  else if (ev.key === 'k' || ev.key === 'ArrowUp'){ ev.preventDefault(); gewaehlt = (liste[i-1] || liste[liste.length-1] || {}).code; auswahl = null; zeichnen(); }
  else if (ev.key >= '1' && ev.key <= '6'){
    const b = document.querySelectorAll('.vorschlag')[+ev.key - 1]; if (b) b.click();
  }
  else if (ev.key === 'Enter'){ const f = FAELLE.find(x => x.code === gewaehlt); if (f) uebernehmen(f); }
  else if (ev.key === 'u'){ const f = FAELLE.find(x => x.code === gewaehlt);
    if (f){ stand.delete(f.code); lokalSchreiben(); if (db) db.collection('nmdis').doc(f.code).delete().catch(()=>{}); zeichnen(); } }
});
['suche', 'filter', 'nurgeo'].forEach(id =>
  ['input', 'change'].forEach(ev => document.getElementById(id).addEventListener(ev, () => zeichnen())));

Object.entries(lokal()).forEach(([k, v]) => stand.set(k, v));
gewaehlt = (FAELLE.find(f => zustand(f) === 'offen') || FAELLE[0] || {}).code;
zeichnen(); speicherStarten();
</script>
'''


def main(argv):
    aus = argv[argv.index('--aus') + 1] if '--aus' in argv else '/tmp/nmdis_seite.html'
    faelle = json.load(open(QUELLE, encoding='utf-8'))
    if '--nur-offen' in argv:
        # Oliver 17.09.2026: nur Stationen, die weder von Hand noch ueber die Werkstatt
        # bearbeitet sind (Name noch Portalumschrift, Position auf der Bogenminute)
        faelle = [f for f in faelle if not f.get('bearbeitet') and not f.get('eingetragen')]
    faelle.sort(key=lambda f: f['name'])
    html = SEITE.replace('__DATEN__', json.dumps(faelle, ensure_ascii=False))
    open(aus, 'w', encoding='utf-8').write(html)
    print(f'{len(faelle)} Pegel -> {aus} ({len(html) / 1024:.0f} kB)')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
