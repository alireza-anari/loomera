// static/js/pages/search.js
// ورودی صفحه جستجو (نقشه + فیلترها)

import { initMap } from "../search/map.js";
import { setupFiltersUI } from "../search/filters.js";
import { setupPublicSearchAutocomplete } from "../search/autocomplete.js";

export default function initSearchPage() {
  try {
    if (
      typeof jalaliDatepicker !== "undefined" &&
      document.querySelector("[data-jdp]")
    ) {
      jalaliDatepicker.startWatch({
        selector: "[data-jdp]",
        autoHide: true,
      });
    }
  } catch (error) {
    console.error("[search] jalaliDatepicker initialization failed");
  }

  try {
    initMap();
  } catch (error) {
    console.error("[search] map initialization failed");
  }

  try {
    setupPublicSearchAutocomplete();
    setupFiltersUI();
  } catch (error) {
    console.error("[search] filter initialization failed");
  }
}
