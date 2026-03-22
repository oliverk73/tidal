document.addEventListener("DOMContentLoaded", function () {
  var searchInput = document.getElementById("search") || document.getElementById("station-search");
  var searchButton = document.querySelector("button[type='submit']");
  var resultsContainer = document.getElementById("search-results");

  if (!searchInput || !searchButton) return;

  var names = (typeof stationNames !== 'undefined') ? stationNames : [];

  // --- Autocomplete dropdown (quick hints while typing) ---
  var acContainer = document.createElement("div");
  acContainer.classList.add("autocomplete-suggestions");
  searchInput.parentNode.style.position = "relative";
  searchInput.parentNode.appendChild(acContainer);

  searchInput.addEventListener("input", function () {
    var val = this.value.trim().toLowerCase();
    acContainer.innerHTML = "";
    if (!val || val.length < 2) return;

    var matches = filterStations(val).slice(0, 8);
    matches.forEach(function (m) {
      var div = document.createElement("div");
      div.textContent = m;
      div.addEventListener("click", function () {
        searchInput.value = m;
        acContainer.innerHTML = "";
        generatePrediction(m);
      });
      acContainer.appendChild(div);
    });
  });

  document.addEventListener("click", function (e) {
    if (!searchInput.contains(e.target) && !acContainer.contains(e.target)) {
      acContainer.innerHTML = "";
    }
  });

  // --- Search: filter and display results ---
  function filterStations(query) {
    var q = query.toLowerCase();
    // Exact start matches first, then contains
    var startsWith = [];
    var contains = [];
    for (var i = 0; i < names.length; i++) {
      var lower = names[i].toLowerCase();
      if (lower.startsWith(q)) startsWith.push(names[i]);
      else if (lower.includes(q)) contains.push(names[i]);
    }
    return startsWith.concat(contains);
  }

  function showResults(query) {
    if (!query) return;
    acContainer.innerHTML = "";

    // Exact match → go directly
    var exact = names.find(function (n) {
      return n.toLowerCase() === query.toLowerCase();
    });
    if (exact) {
      generatePrediction(exact);
      return;
    }

    var matches = filterStations(query);

    if (matches.length === 0) {
      resultsContainer.style.display = "block";
      resultsContainer.innerHTML =
        '<div class="search-results-header">No stations found for "' +
        escapeHtml(query) + '"</div>';
      return;
    }

    if (matches.length === 1) {
      generatePrediction(matches[0]);
      return;
    }

    // Show results list
    var html = '<div class="search-results-header">' +
      matches.length + ' stations matching "' + escapeHtml(query) + '"' +
      '<span class="search-results-close" title="Close">&times;</span></div>' +
      '<div class="search-results-list">';

    matches.forEach(function (name) {
      html += '<div class="search-result-item" data-station="' +
        escapeHtml(name) + '">' + highlightMatch(name, query) + '</div>';
    });
    html += '</div>';

    resultsContainer.innerHTML = html;
    resultsContainer.style.display = "block";

    // Close button
    resultsContainer.querySelector(".search-results-close").addEventListener("click", function () {
      resultsContainer.style.display = "none";
    });

    // Click on result → generate prediction
    resultsContainer.querySelectorAll(".search-result-item").forEach(function (el) {
      el.addEventListener("click", function () {
        var station = this.getAttribute("data-station");
        searchInput.value = station;
        generatePrediction(station);
      });
    });
  }

  function generatePrediction(station) {
    resultsContainer.style.display = "none";
    searchButton.disabled = true;
    searchButton.textContent = "...";

    fetch('/generate/' + encodeURIComponent(station))
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (data) {
        window.location.href = data.url;
      })
      .catch(function (err) {
        alert("Error generating prediction: " + err.message);
      })
      .finally(function () {
        searchButton.disabled = false;
        searchButton.textContent = "Search";
      });
  }

  function escapeHtml(s) {
    var d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  function highlightMatch(text, query) {
    var idx = text.toLowerCase().indexOf(query.toLowerCase());
    if (idx < 0) return escapeHtml(text);
    return escapeHtml(text.slice(0, idx)) +
      '<b>' + escapeHtml(text.slice(idx, idx + query.length)) + '</b>' +
      escapeHtml(text.slice(idx + query.length));
  }

  // --- Event handlers ---
  searchButton.addEventListener("click", function (e) {
    e.preventDefault();
    showResults(searchInput.value.trim());
  });

  searchInput.addEventListener("keydown", function (e) {
    if (e.key === "Enter") {
      e.preventDefault();
      showResults(searchInput.value.trim());
    }
  });
});
