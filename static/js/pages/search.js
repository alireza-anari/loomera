// static/js/pages/search.js
// ورودی صفحه جستجو (نقشه + فیلترها)

import { initMap } from "../search/map.js";
import { setupFiltersUI } from "../search/filters.js";
import { setupPublicSearchAutocomplete } from "../search/autocomplete.js";
export default function initSearchPage() {
  try {
    if (typeof jalaliDatepicker !== "undefined" && document.querySelector("[data-jdp]")) {
      jalaliDatepicker.startWatch({
        selector: "[data-jdp]",
        autoHide: true,
      });
    }
  } catch (e) {
    console.error("[search] jalaliDatepicker ERROR:", e);
  }

  try {
    initMap();
  } catch (e) {
    console.error("[search] initMap ERROR:", e);
  }

  try {
    setupPublicSearchAutocomplete();
    setupFiltersUI();
  } catch (e) {
    console.error("[search] setupFiltersUI ERROR:", e);
  }

}
