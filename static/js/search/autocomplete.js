function debounce(fn, delay = 220) {
  let timer = null;

  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

function closeList(list) {
  if (!list) return;
  list.innerHTML = "";
  list.classList.add("hidden");
}

function renderSuggestionItem(item, onSelect) {
  const li = document.createElement("li");

  const name = item.value || item.name || "";
  const typeLabel = item.type_label || "نتیجه";
  const meta = item.meta || "";

  li.className = "lm-search-suggestion-item";
  li.innerHTML = `
    <div class="lm-search-suggestion-item__main">
      <strong>${name}</strong>
      <span>${typeLabel}</span>
    </div>
    ${meta ? `<small>${meta}</small>` : ""}
  `;

  li.addEventListener("click", () => onSelect(item));

  return li;
}

async function loadSuggestions(endpoint, query) {
  if (!endpoint || !query.trim()) return [];

  const response = await fetch(`${endpoint}?q=${encodeURIComponent(query.trim())}`, {
    headers: { "X-Requested-With": "XMLHttpRequest" },
  });

  if (!response.ok) return [];

  const payload = await response.json();
  return payload.results || [];
}

function setupQueryAutocomplete(form) {
  const input = form.querySelector("[data-lm-search-query]");
  const list = form.querySelector("[data-lm-search-query-list]");
  const qTypeInput = form.querySelector("[data-lm-q-type]");
  const qIdInput = form.querySelector("[data-lm-q-id]");
  const servicesInput = form.querySelector("[data-lm-services-hidden]");
  const endpoint = form.dataset.searchSuggestUrl;

  if (!input || !list || !endpoint) return;

  let selectedValue = input.value.trim();

  const run = debounce(async () => {
    const query = input.value.trim();

    if (!query) {
      selectedValue = "";
      closeList(list);
      return;
    }

    /*
      اگر کاربر یک گزینه را انتخاب کرده و مقدار input همان گزینه است،
      دیگر پیشنهادها را دوباره باز نکن.
    */
    if (selectedValue && query === selectedValue) {
      closeList(list);
      return;
    }

    const results = await loadSuggestions(endpoint, query);

    list.innerHTML = "";

    const filteredResults = results.filter((item) => {
      const itemValue = item.value || item.name || "";
      const itemType = item.type || "";
      const itemId = String(item.id || "");

      if (qTypeInput?.value && qIdInput?.value) {
        return !(itemType === qTypeInput.value && itemId === String(qIdInput.value));
      }

      return itemValue !== selectedValue;
    });

    if (!filteredResults.length) {
      closeList(list);
      return;
    }

    filteredResults.slice(0, 12).forEach((item) => {
      list.appendChild(
        renderSuggestionItem(item, (selected) => {
          const value = selected.value || selected.name || "";

          selectedValue = value;
          input.value = value;

          if (qTypeInput) qTypeInput.value = selected.type || "";
          if (qIdInput) qIdInput.value = selected.id || "";

          if (servicesInput) {
            servicesInput.value = selected.type === "service" ? selected.id || "" : "";
          }

          closeList(list);
          input.blur();
        })
      );
    });

    list.classList.remove("hidden");
  }, 220);

  input.addEventListener("input", () => {
    selectedValue = "";

    if (qTypeInput) qTypeInput.value = "";
    if (qIdInput) qIdInput.value = "";
    if (servicesInput) servicesInput.value = "";

    run();
  });

  input.addEventListener("focus", () => {
    const query = input.value.trim();

    if (!query) return;

    if (selectedValue && query === selectedValue) {
      closeList(list);
      return;
    }

    run();
  });
}

function setupLocationAutocomplete(form) {
  const input = form.querySelector("[data-lm-location-query]");
  const list = form.querySelector("[data-lm-location-list]");
  const endpoint = form.dataset.locationSuggestUrl;

  if (!input || !list || !endpoint) return;

  let selectedValue = input.value.trim();

  const run = debounce(async () => {
    const query = input.value.trim();

    if (selectedValue && query === selectedValue) {
      closeList(list);
      return;
    }

    const results = await loadSuggestions(endpoint, query);

    list.innerHTML = "";

    const filteredResults = results.filter((item) => {
      const itemValue = item.value || item.name || "";
      return itemValue !== selectedValue;
    });

    if (!filteredResults.length) {
      closeList(list);
      return;
    }

    filteredResults.slice(0, 10).forEach((item) => {
      list.appendChild(
        renderSuggestionItem(item, (selected) => {
          const value = selected.value || selected.name || "";

          selectedValue = value;
          input.value = value;

          closeList(list);
          input.blur();
        })
      );
    });

    list.classList.remove("hidden");
  }, 220);

  input.addEventListener("input", () => {
    selectedValue = "";
    run();
  });

  input.addEventListener("focus", () => {
    const query = input.value.trim();

    if (selectedValue && query === selectedValue) {
      closeList(list);
      return;
    }

    run();
  });
}

export function setupPublicSearchAutocomplete(root = document) {
  const forms = Array.from(root.querySelectorAll("[data-lm-search-autocomplete]"));

  forms.forEach((form) => {
    setupQueryAutocomplete(form);
    setupLocationAutocomplete(form);
  });

  document.addEventListener("click", (event) => {
    forms.forEach((form) => {
      if (form.contains(event.target)) return;

      closeList(form.querySelector("[data-lm-search-query-list]"));
      closeList(form.querySelector("[data-lm-location-list]"));
    });
  });
}