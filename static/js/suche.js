document.addEventListener("DOMContentLoaded", function () {
  var searchInput = document.getElementById("search") || document.getElementById("station-search");
  var searchButton = document.querySelector("button[type='submit']");

  if (!searchInput || !searchButton) return;

  // stationNames is set as global var by the template (from Flask)
  var names = (typeof stationNames !== 'undefined') ? stationNames : [];

  // Autocomplete
  var suggestionsContainer = document.createElement("div");
  suggestionsContainer.classList.add("autocomplete-suggestions");
  searchInput.parentNode.style.position = "relative";
  searchInput.parentNode.appendChild(suggestionsContainer);

  searchInput.addEventListener("input", function () {
    var val = this.value.trim().toLowerCase();
    suggestionsContainer.innerHTML = "";
    if (!val || val.length < 2) return;

    var matches = names.filter(function (n) {
      return n.toLowerCase().includes(val);
    }).slice(0, 50);

    matches.forEach(function (match) {
      var div = document.createElement("div");
      div.textContent = match;
      div.addEventListener("click", function () {
        searchInput.value = match;
        suggestionsContainer.innerHTML = "";
        doSearch(match);
      });
      suggestionsContainer.appendChild(div);
    });
  });

  document.addEventListener("click", function (e) {
    if (!searchInput.contains(e.target) && !suggestionsContainer.contains(e.target)) {
      suggestionsContainer.innerHTML = "";
    }
  });

  function doSearch(query) {
    if (!query) return;
    searchButton.disabled = true;
    searchButton.textContent = "...";

    fetch('/generate/' + encodeURIComponent(query))
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (data) {
        window.location.href = data.url;
      })
      .catch(function (err) {
        alert("Fehler beim Erzeugen der Vorhersage: " + err.message);
      })
      .finally(function () {
        searchButton.disabled = false;
        searchButton.textContent = "Search";
      });
  }

  searchButton.addEventListener("click", function (e) {
    e.preventDefault();
    doSearch(searchInput.value.trim());
  });

  searchInput.addEventListener("keydown", function (e) {
    if (e.key === "Enter") {
      e.preventDefault();
      suggestionsContainer.innerHTML = "";
      doSearch(searchInput.value.trim());
    }
  });
});
