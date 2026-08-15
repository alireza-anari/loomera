(function () {
  "use strict";

  function normalize(value) {
    return String(value || "").trim().toLocaleLowerCase("fa");
  }

  function initManagement(root) {
    const search = root.querySelector("[data-discount-search]");
    const buttons = Array.from(root.querySelectorAll("[data-discount-filter-button]"));
    const cards = Array.from(root.querySelectorAll("[data-discount-card]"));
    const filteredEmpty = root.querySelector("[data-discount-filter-empty]");
    if (!cards.length) return;

    let activeState = "all";

    const apply = () => {
      const query = normalize(search?.value);
      let visible = 0;
      cards.forEach((card) => {
        const stateMatch = activeState === "all" || card.dataset.discountState === activeState;
        const searchMatch = !query || normalize(card.textContent).includes(query);
        const show = stateMatch && searchMatch;
        card.hidden = !show;
        if (show) visible += 1;
      });
      if (filteredEmpty) filteredEmpty.hidden = visible !== 0;
    };

    buttons.forEach((button) => {
      button.addEventListener("click", () => {
        const next = button.dataset.filterValue || "all";
        activeState = activeState === next ? "all" : next;
        buttons.forEach((candidate) => {
          candidate.setAttribute("aria-pressed", candidate.dataset.filterValue === activeState ? "true" : "false");
        });
        apply();
      });
    });

    search?.addEventListener("input", apply);
    apply();
  }

  function initSelectionCounter(root) {
    const inputs = Array.from(root.querySelectorAll('input[type="checkbox"]'));
    const output = root.querySelector("[data-selection-count]");
    if (!inputs.length || !output) return;
    const update = () => {
      const count = inputs.filter((input) => input.checked).length;
      output.textContent = String(count);
    };
    inputs.forEach((input) => input.addEventListener("change", update));
    update();
  }

  document.addEventListener("DOMContentLoaded", () => {
    if (typeof window.jalaliDatepicker !== "undefined") {
      window.jalaliDatepicker.startWatch({ selector: "[data-jdp]" });
    }
    document.querySelectorAll("[data-discount-management]").forEach(initManagement);
    document.querySelectorAll("[data-discount-selection]").forEach(initSelectionCounter);
  });
})();
