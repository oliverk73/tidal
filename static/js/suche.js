document.addEventListener("DOMContentLoaded", function () {
  var trigger = document.getElementById("search-trigger");
  var modal = document.getElementById("search-modal");
  var input = document.getElementById("search-modal-input");
  var closeBtn = document.getElementById("search-modal-close");
  var resultsEl = document.getElementById("search-modal-results");

  if (!trigger || !modal || !input) return;

  var names = (typeof stationNames !== 'undefined') ? stationNames : [];

  // --- Open / Close ---
  function openModal() {
    modal.classList.add("open");
    input.value = "";
    resultsEl.innerHTML = "";
    // Small delay so the CSS transition starts before focus
    setTimeout(function () { input.focus(); }, 50);
  }

  function closeModal() {
    modal.classList.remove("open");
    input.value = "";
    resultsEl.innerHTML = "";
  }

  trigger.addEventListener("click", openModal);
  closeBtn.addEventListener("click", closeModal);

  // Close on backdrop click
  modal.addEventListener("click", function (e) {
    if (e.target === modal) closeModal();
  });

  // Close on Escape
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && modal.classList.contains("open")) closeModal();
  });

  // --- Accent-insensitive normalization ---
  function normalize(s) {
    return s.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  }

  // --- Filtering ---
  function filterStations(query) {
    var q = normalize(query);
    var startsWith = [];
    var contains = [];
    for (var i = 0; i < names.length; i++) {
      var lower = normalize(names[i]);
      if (lower.startsWith(q)) startsWith.push(names[i]);
      else if (lower.includes(q)) contains.push(names[i]);
    }
    return startsWith.concat(contains);
  }

  // --- Parse station name into name + location parts ---
  function parseName(full) {
    // e.g. "Crisfield, Little Annemessex River, Chesapeake Bay, Maryland"
    // → name: "Crisfield", detail: "Little Annemessex River, Chesapeake Bay, Maryland"
    var idx = full.indexOf(", ");
    if (idx > 0) {
      return { name: full.slice(0, idx), detail: full.slice(idx + 2) };
    }
    return { name: full, detail: "" };
  }

  // --- Type badges (match map-marker iconography) ---
  // Vertical double arrow ↕ for tide stations, horizontal double arrow ↔ for currents.
  var CURRENT_RE = /\s+Currents?(\s*\([^)]*\))?\s*$/;
  var TIDE_ICON_SVG =
    '<svg width="12" height="12" viewBox="0 0 18 18" aria-hidden="true">' +
    '<line x1="9" y1="2" x2="9" y2="16" stroke="currentColor" stroke-width="3" stroke-linecap="round"/>' +
    '<polyline points="5,5 9,2 13,5" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>' +
    '<polyline points="5,13 9,16 13,13" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>' +
    '</svg>';
  var CURRENT_ICON_SVG =
    '<svg width="12" height="12" viewBox="0 0 18 18" aria-hidden="true">' +
    '<line x1="2" y1="9" x2="16" y2="9" stroke="currentColor" stroke-width="3" stroke-linecap="round"/>' +
    '<polyline points="5,5 2,9 5,13" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>' +
    '<polyline points="13,5 16,9 13,13" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>' +
    '</svg>';
  function typeBadge(isCurrent) {
    return '<span class="search-modal-type-badge ' + (isCurrent ? 'type-current' : 'type-tide') + '">' +
      (isCurrent ? CURRENT_ICON_SVG + ' Current' : TIDE_ICON_SVG + ' Tide') +
      '</span>';
  }

  // --- Render results ---
  function renderResults(query) {
    var q = query.trim();
    if (q.length < 1) {
      resultsEl.innerHTML = '<div class="search-modal-hint">Type to search across ' +
        names.length + ' tide stations</div>';
      return;
    }

    var matches = filterStations(q);

    if (matches.length === 0) {
      resultsEl.innerHTML = '<div class="search-modal-empty">No stations found for "' +
        escapeHtml(q) + '"</div>';
      return;
    }

    // Limit displayed results for performance
    var showMax = 100;
    var limited = matches.slice(0, showMax);
    var html = '<div class="search-modal-count">' + matches.length + ' results</div>';

    var hasCoords = (typeof stationCoords !== 'undefined');

    limited.forEach(function (full) {
      var isCurrent = CURRENT_RE.test(full);
      // Strip trailing " Current[..]" for cleaner display; data-station keeps full name.
      var displayFull = isCurrent ? full.replace(CURRENT_RE, '') : full;
      var p = parseName(displayFull);
      var mapBtn = '';
      if (hasCoords && stationCoords[full]) {
        mapBtn = '<button class="search-modal-map-btn" data-station-map="' + escapeHtml(full) + '" title="Auf Karte zeigen">' +
          '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
          '<path d="M21 10c0 7-9 13-9 13S3 17 3 10a9 9 0 1 1 18 0z"/>' +
          '<circle cx="12" cy="10" r="3"/>' +
          '</svg></button>';
      }
      html += '<div class="search-modal-item" data-station="' + escapeHtml(full) + '">' +
        '<div class="search-modal-item-text">' +
        '<span class="search-modal-item-name">' + highlightMatch(p.name, q) + '</span>' +
        (p.detail ? '<span class="search-modal-item-detail">' + highlightMatch(p.detail, q) + '</span>' : '') +
        '</div>' +
        typeBadge(isCurrent) +
        mapBtn +
        '</div>';
    });

    if (matches.length > showMax) {
      html += '<div class="search-modal-more">... and ' +
        (matches.length - showMax) + ' more results</div>';
    }

    resultsEl.innerHTML = html;

    // Click handler: map button → zoom to station
    resultsEl.querySelectorAll(".search-modal-map-btn").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        var station = this.getAttribute("data-station-map");
        var coords = stationCoords[station];
        if (coords && window.map) {
          closeModal();
          window.map.setView(coords, 11);
          // Open the marker popup
          if (typeof markers !== 'undefined') {
            markers.eachLayer(function (layer) {
              var ll = layer.getLatLng();
              if (Math.abs(ll.lat - coords[0]) < 0.0001 && Math.abs(ll.lng - coords[1]) < 0.0001) {
                // Spiderfied clusters need a small delay
                setTimeout(function () { layer.openPopup(); }, 300);
              }
            });
          }
        }
      });
    });

    // Click handler: item text → generate prediction
    resultsEl.querySelectorAll(".search-modal-item").forEach(function (el) {
      el.addEventListener("click", function () {
        var station = this.getAttribute("data-station");
        generatePrediction(station);
      });
    });
  }

  // --- Debounced input ---
  var debounceTimer = null;
  input.addEventListener("input", function () {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(function () {
      renderResults(input.value);
    }, 120);
  });

  // Enter → pick first result or exact match
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter") {
      e.preventDefault();
      var q = input.value.trim();
      if (!q) return;

      // Exact match?
      var exact = names.find(function (n) {
        return normalize(n) === normalize(q);
      });
      if (exact) {
        generatePrediction(exact);
        return;
      }

      // Otherwise pick first result
      var first = resultsEl.querySelector(".search-modal-item");
      if (first) {
        generatePrediction(first.getAttribute("data-station"));
      }
    }
  });

  // --- Generate prediction ---
  function generatePrediction(station) {
    // Show loading state in modal
    resultsEl.innerHTML = '<div class="search-modal-loading">Generating prediction for ' +
      escapeHtml(station) + '...</div>';

    fetch('/generate/' + encodeURIComponent(station))
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (data) {
        window.location.href = data.url;
      })
      .catch(function (err) {
        resultsEl.innerHTML = '<div class="search-modal-empty">Error: ' +
          escapeHtml(err.message) + '</div>';
      });
  }

  // --- Helpers ---
  function escapeHtml(s) {
    var d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  function highlightMatch(text, query) {
    var nText = normalize(text);
    var nQuery = normalize(query);
    var idx = nText.indexOf(nQuery);
    if (idx < 0) return escapeHtml(text);
    var matchLen = nQuery.length;
    return escapeHtml(text.slice(0, idx)) +
      '<mark>' + escapeHtml(text.slice(idx, idx + matchLen)) + '</mark>' +
      escapeHtml(text.slice(idx + matchLen));
  }

  // Show hint on open
  renderResults("");
});
