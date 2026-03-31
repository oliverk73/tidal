document.addEventListener("DOMContentLoaded", function () {
  const input = document.getElementById("search") || document.getElementById("station-search");
  if (!input) return;

  const suggestionsContainer = document.createElement("div");
  suggestionsContainer.classList.add("autocomplete-suggestions");
  input.parentNode.appendChild(suggestionsContainer);

  input.addEventListener("input", function () {
    const val = this.value.toLowerCase();
    suggestionsContainer.innerHTML = "";
    if (!val) return;

    const matches = stationNames.filter(name => name.toLowerCase().includes(val)).slice(0, 50);
    matches.forEach(match => {
      const div = document.createElement("div");
      div.textContent = match;
      div.addEventListener("click", function () {
        input.value = match;
        suggestionsContainer.innerHTML = "";
      });
      suggestionsContainer.appendChild(div);
    });
  });
});