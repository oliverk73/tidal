/*!
 * Tide widget — free embeddable tide times.
 * Docs: /widgets/  (on the site this script is served from)
 *
 * Usage:
 *   <div class="tide-widget" data-station="cuxhaven-germany" data-days="3"></div>
 *   <script async src="https://YOUR-HOST/widget.js"></script>
 *
 * Attributes:
 *   data-station  station slug or full station name
 *   data-lat / data-lon  alternative: nearest station to coordinates
 *   data-days     1..3 (default 3)
 *   data-theme    light | dark | auto (default light)
 *   data-units    m | ft (default m)
 *   data-spd      kn | ms | kmh (default kn; current stations only)
 */
(function () {
  'use strict';

  // Base URL is derived from this script's own src, so the embed works on
  // any domain the site is served from.
  var script = document.currentScript;
  if (!script) {
    var scripts = document.getElementsByTagName('script');
    for (var i = scripts.length - 1; i >= 0; i--) {
      if (/\/widget\.js(\?|$)/.test(scripts[i].src)) { script = scripts[i]; break; }
    }
  }
  var BASE = '';
  if (script && script.src) {
    var a = document.createElement('a');
    a.href = script.src;
    BASE = a.protocol + '//' + a.host;
  }

  var CSS = '' +
    '.tide-widget{box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;' +
      'max-width:320px;border:1px solid #d8dee2;border-radius:8px;overflow:hidden;background:#fff;color:#223;font-size:14px;line-height:1.4}' +
    '.tide-widget *{box-sizing:border-box;margin:0;padding:0}' +
    '.tide-widget .tw-header{background:#169ca5;color:#fff;padding:8px 12px}' +
    '.tide-widget .tw-header a{color:#fff;text-decoration:none;font-weight:600;font-size:15px}' +
    '.tide-widget .tw-header a:hover{text-decoration:underline}' +
    '.tide-widget .tw-day{padding:6px 12px 8px}' +
    '.tide-widget .tw-day+.tw-day{border-top:1px solid #e8ecee}' +
    '.tide-widget .tw-date{font-weight:600;font-size:12.5px;color:#169ca5;text-transform:uppercase;letter-spacing:.03em;margin:2px 0 4px}' +
    '.tide-widget table.tw-table{width:100%;border-collapse:collapse}' +
    '.tide-widget .tw-table td{padding:2px 0;border:0;font-size:13.5px}' +
    '.tide-widget .tw-table th{padding:0 0 2px;border:0;font-size:10.5px;font-weight:600;' +
      'color:#8a99a3;text-transform:uppercase;letter-spacing:.05em;text-align:right}' +
    '.tide-widget .tw-icon{width:24px;text-align:center}' +
    '.tide-widget .tw-icon-high{color:#1a7fc4}' +
    '.tide-widget .tw-icon-low{color:#c47a1a}' +
    '.tide-widget .tw-type{color:#445}' +
    '.tide-widget .tw-time{font-variant-numeric:tabular-nums;font-weight:600;text-align:right;width:52px}' +
    '.tide-widget .tw-height{font-variant-numeric:tabular-nums;color:#667;text-align:right;width:72px}' +
    '.tide-widget .tw-footer{padding:6px 12px;background:#f4f7f8;border-top:1px solid #e8ecee;font-size:11px;color:#789}' +
    '.tide-widget .tw-footer a{color:#169ca5;text-decoration:none}' +
    '.tide-widget .tw-footer a:hover{text-decoration:underline}' +
    '.tide-widget .tw-msg{padding:14px 12px;color:#667;font-size:13px}' +
    /* dark theme */
    '.tide-widget.tw-dark{background:#1d2429;border-color:#39434b;color:#dde5ea}' +
    '.tide-widget.tw-dark .tw-header{background:#10747b}' +
    '.tide-widget.tw-dark .tw-day+.tw-day{border-top-color:#2c353c}' +
    '.tide-widget.tw-dark .tw-date{color:#4fc3cb}' +
    '.tide-widget.tw-dark .tw-type{color:#b9c4cb}' +
    '.tide-widget.tw-dark .tw-table th{color:#6e7f8a}' +
    '.tide-widget.tw-dark .tw-height{color:#8fa0aa}' +
    '.tide-widget.tw-dark .tw-icon-high{color:#5fb2e8}' +
    '.tide-widget.tw-dark .tw-icon-low{color:#e8b25f}' +
    '.tide-widget.tw-dark .tw-footer{background:#161c20;border-top-color:#2c353c;color:#7a8a94}' +
    '.tide-widget.tw-dark .tw-footer a{color:#4fc3cb}' +
    '.tide-widget.tw-dark .tw-msg{color:#9aa8b0}';

  function injectCss() {
    if (document.getElementById('tide-widget-css')) return;
    var style = document.createElement('style');
    style.id = 'tide-widget-css';
    style.textContent = CSS;
    (document.head || document.documentElement).appendChild(style);
  }

  var ICONS = { high: '▲', low: '▼', flood: '➡', ebb: '⬅', slack: '⏸' };
  var ICON_CLASS = { high: 'tw-icon-high', low: 'tw-icon-low', flood: 'tw-icon-high', ebb: 'tw-icon-low', slack: 'tw-type' };
  var LABELS = { 'High Tide': 'High', 'Low Tide': 'Low' };
  var UNIT_SHORT = { meters: 'm', feet: 'ft', knots: 'kn' };

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function formatDate(iso) {
    try {
      var p = iso.split('-');
      var d = new Date(Date.UTC(+p[0], +p[1] - 1, +p[2], 12));
      return d.toLocaleDateString(undefined,
        { weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC' });
    } catch (e) { return iso; }
  }

  function render(root, data) {
    root.textContent = '';

    var header = el('div', 'tw-header');
    var link = el('a', null, data.station);
    link.href = BASE + data.url;
    link.target = '_blank';
    link.rel = 'noopener';
    link.title = 'Full 7-day tide prediction for ' + data.station;
    header.appendChild(link);
    root.appendChild(header);

    if (!data.days || !data.days.length) {
      root.appendChild(el('div', 'tw-msg', 'No tide events available for this station.'));
    }

    (data.days || []).forEach(function (day) {
      var box = el('div', 'tw-day');
      box.appendChild(el('div', 'tw-date', formatDate(day.date)));
      var table = el('table', 'tw-table');
      var thead = document.createElement('thead');
      var hrow = document.createElement('tr');
      hrow.appendChild(el('th', null, ''));
      hrow.appendChild(el('th', null, ''));
      hrow.appendChild(el('th', null, 'time'));
      hrow.appendChild(el('th', null, data.is_current ? 'rate' : 'level'));
      thead.appendChild(hrow);
      table.appendChild(thead);
      var tbody = document.createElement('tbody');
      day.events.forEach(function (ev) {
        var tr = document.createElement('tr');
        var icon = el('td', 'tw-icon ' + (ICON_CLASS[ev.kind] || 'tw-type'), ICONS[ev.kind] || '');
        var type = el('td', 'tw-type', LABELS[ev.type] || ev.type);
        var time = el('td', 'tw-time', ev.time);
        var height = el('td', 'tw-height',
          ev.height != null ? ev.height.toFixed(2) + ' ' + (UNIT_SHORT[ev.unit] || ev.unit) : '');
        tr.appendChild(icon); tr.appendChild(type); tr.appendChild(time); tr.appendChild(height);
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
      box.appendChild(table);
      root.appendChild(box);
    });

    var footer = el('div', 'tw-footer');
    footer.appendChild(document.createTextNode('Tide times by '));
    var credit = el('a', null, (BASE || location.origin).replace(/^https?:\/\//, ''));
    credit.href = BASE + data.url;
    credit.target = '_blank';
    credit.rel = 'noopener';
    footer.appendChild(credit);
    if (data.datum) {
      footer.appendChild(document.createTextNode(' · heights: ' + data.datum));
    }
    root.appendChild(footer);
  }

  function renderMessage(root, msg) {
    root.textContent = '';
    root.appendChild(el('div', 'tw-msg', msg));
  }

  function fetchJson(url, cb, errCb) {
    var xhr = new XMLHttpRequest();
    xhr.open('GET', url, true);
    xhr.onreadystatechange = function () {
      if (xhr.readyState !== 4) return;
      if (xhr.status >= 200 && xhr.status < 300) {
        try { cb(JSON.parse(xhr.responseText)); }
        catch (e) { errCb('Invalid response'); }
      } else {
        var msg = 'Could not load tide data';
        try { msg = JSON.parse(xhr.responseText).error || msg; } catch (e) {}
        errCb(msg);
      }
    };
    xhr.send();
  }

  function initWidget(root) {
    if (root.getAttribute('data-tw-init')) return;
    root.setAttribute('data-tw-init', '1');

    var theme = (root.getAttribute('data-theme') || 'light').toLowerCase();
    if (theme === 'auto' && window.matchMedia &&
        window.matchMedia('(prefers-color-scheme: dark)').matches) {
      theme = 'dark';
    }
    root.classList.toggle('tw-dark', theme === 'dark');

    var days = parseInt(root.getAttribute('data-days') || '3', 10);
    if (!(days >= 1 && days <= 3)) days = 3;
    var units = (root.getAttribute('data-units') || 'm').toLowerCase();
    units = (units === 'ft' || units === 'feet') ? 'ft' : 'm';
    var spd = (root.getAttribute('data-spd') || 'kn').toLowerCase();
    spd = (spd === 'ms' || spd === 'kmh') ? spd : 'kn';

    renderMessage(root, 'Loading tide times…');

    var station = root.getAttribute('data-station');
    var lat = root.getAttribute('data-lat');
    var lon = root.getAttribute('data-lon');

    function load(stationQuery) {
      fetchJson(
        BASE + '/api/widget/tides?station=' + encodeURIComponent(stationQuery) + '&days=' + days + '&units=' + units + '&spd=' + spd,
        function (data) { render(root, data); },
        function (msg) { renderMessage(root, msg); }
      );
    }

    if (station) {
      load(station);
    } else if (lat && lon) {
      fetchJson(
        BASE + '/api/widget/nearest?lat=' + encodeURIComponent(lat) + '&lon=' + encodeURIComponent(lon),
        function (res) { load(res.slug); },
        function (msg) { renderMessage(root, msg); }
      );
    } else {
      renderMessage(root, 'Tide widget: set data-station or data-lat/data-lon.');
    }
  }

  function scan(container) {
    injectCss();
    var nodes = (container || document).querySelectorAll('.tide-widget');
    for (var i = 0; i < nodes.length; i++) initWidget(nodes[i]);
  }

  // Public API (used by the /widgets/ configurator for live previews)
  window.TideWidget = { scan: scan, render: initWidget };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { scan(); });
  } else {
    scan();
  }
})();
