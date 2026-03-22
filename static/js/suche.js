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

  // --- Filtering ---
  function filterStations(query) {
    var q = query.toLowerCase();
    var startsWith = [];
    var contains = [];
    for (var i = 0; i < names.length; i++) {
      var lower = names[i].toLowerCase();
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

    limited.forEach(function (full) {
      var p = parseName(full);
      html += '<div class="search-modal-item" data-station="' + escapeHtml(full) + '">' +
        '<span class="search-modal-item-name">' + highlightMatch(p.name, q) + '</span>' +
        (p.detail ? '<span class="search-modal-item-detail">' + highlightMatch(p.detail, q) + '</span>' : '') +
        '</div>';
    });

    if (matches.length > showMax) {
      html += '<div class="search-modal-more">... and ' +
        (matches.length - showMax) + ' more results</div>';
    }

    resultsEl.innerHTML = html;

    // Click handlers
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
        return n.toLowerCase() === q.toLowerCase();
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
    var idx = text.toLowerCase().indexOf(query.toLowerCase());
    if (idx < 0) return escapeHtml(text);
    return escapeHtml(text.slice(0, idx)) +
      '<mark>' + escapeHtml(text.slice(idx, idx + query.length)) + '</mark>' +
      escapeHtml(text.slice(idx + query.length));
  }

  // Show hint on open
  renderResults("");
});
