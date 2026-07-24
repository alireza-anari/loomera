function parseInitialState() {
  const raw = document.body.dataset.initialSearchState || "{}";
  try {
    return JSON.parse(raw);
  } catch (error) {
    console.warn("[search] invalid initial state");
    return {};
  }
}

function debounce(fn, delay = 250) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

function truthyFilterValue(value) {
  return [true, "true", "1", "yes", "on", "checked"].includes(value);
}

function normalizePriceInput(value) {
  return String(value || "")
    .replace(/[۰-۹]/g, (digit) => "۰۱۲۳۴۵۶۷۸۹".indexOf(digit))
    .replace(/[٠-٩]/g, (digit) => "٠١٢٣٤٥٦٧٨٩".indexOf(digit))
    .replace(/[^0-9]/g, "");
}

function formatPriceLabel(value) {
  const normalized = normalizePriceInput(value);
  if (!normalized) return "";
  return Number(normalized).toLocaleString("fa-IR");
}

export function setupFiltersUI() {
  if (document.body.getAttribute("data-page") !== "search") return;

  const searchEndpoint = document.body.dataset.searchEndpoint || "/search/results/";
  const searchPageUrl = document.body.dataset.searchPageUrl || "/search/search/";
  const initialState = parseInitialState();

  const filtersSheet = document.getElementById("filtersSheet");
  const filtersHandle = document.getElementById("filtersHandle") || filtersSheet?.querySelector(".sheet-handle");
  const salonList = document.getElementById("salonList");
  const searchLoading = document.getElementById("searchLoading");
  const searchStatus = document.getElementById("searchStatus");
  const resultsCountEl = document.getElementById("resultsCount");
  const searchBarButton = document.getElementById("searchBarButton");
  const searchBarText = document.getElementById("searchBarText");
  const openFilterBtn = document.getElementById("openFilterBtn");
  const openFilterIcon = openFilterBtn?.querySelector("i");
  const mapPane = document.getElementById("searchMapPane");
  const contentPane = document.getElementById("searchContentPane");
  const desktopResultsToggleBtn = document.getElementById("desktopResultsToggleBtn");
  const desktopResultsToggleIcon = document.getElementById("desktopResultsToggleIcon");
  const desktopSearchPanel = document.getElementById("desktopSearchPanel");
  const desktopSearchField = document.getElementById("desktopSearchField");
  const filterScreen = document.getElementById("filterScreen");
  const filterBackBtn = document.getElementById("filterBackBtn");
  const filterApplyBtn = document.getElementById("filterApplyBtn");
  const clearFiltersFullBtn = document.getElementById("clearFiltersFullScreen");
  const clearFiltersSheetBtn = document.getElementById("clearFilters");
  const filterSheetOpenBtn = document.getElementById("filterSheetOpenBtn");
  const locationInput = document.getElementById("filterLocationInput");
  const locationSuggestions = document.getElementById("locationSuggestions");
  const useCurrentLocationBtn = document.getElementById("useCurrentLocationBtn");
  const dateInput = document.getElementById("filterDateInput");
  const timeInput = document.getElementById("filterTimeInput");
  const timeChips = Array.from(document.querySelectorAll(".time-chip"));
  const sortChips = Array.from(document.querySelectorAll(".sort-chip"));
  const serviceSearchInput = document.getElementById("serviceSearchInput");
  const serviceSearchSuggestions = document.getElementById("serviceSearchSuggestions");
  const selectedServicesList = document.getElementById("selectedServicesList");
  const serviceOptionChips = Array.from(document.querySelectorAll(".service-option-chip"));
  const selectedGroupTitle = document.querySelector("[data-selected-group-title]");
  const clearGroupLink = document.querySelector("[data-clear-group]");
  const categoryCards = Array.from(document.querySelectorAll("[data-search-group]"));
  const locateButtons = Array.from(document.querySelectorAll(".map-locate-btn, #mapLocateButton"));
  const filterValidationMessage = document.getElementById("filterValidationMessage");
  const activeFiltersBar = document.getElementById("activeFiltersBar");
  const activeFiltersBarScreen = document.getElementById("activeFiltersBarScreen");
  const activeFiltersChips = document.getElementById("activeFiltersChips");
  const activeFiltersChipsScreen = document.getElementById("activeFiltersChipsScreen");
  const clearActiveFilterButtons = Array.from(document.querySelectorAll("[data-clear-active-filters]"));
  const minPriceInput = document.getElementById("filterMinPriceInput");
  const maxPriceInput = document.getElementById("filterMaxPriceInput");
  const minRatingInput = document.getElementById("filterMinRatingInput");
  const filterToggleChips = Array.from(document.querySelectorAll("[data-filter-toggle]"));
  const availabilityChips = Array.from(document.querySelectorAll("[data-availability]"));

  if (!filtersSheet || !salonList) return;

  const state = {
    q: initialState.q || "",
    location: initialState.location || "",
    date: initialState.date || "",
    period: initialState.period || "",
    time: initialState.time || "",
    group: initialState.group || "",
    services: Array.isArray(initialState.services) ? initialState.services.map(String) : [],
    serviceNames: {},
    sort: initialState.sort || "recommended",
    lat: initialState.lat || "",
    lng: initialState.lng || "",
    min_price: normalizePriceInput(initialState.min_price || initialState.price_min || ""),
    max_price: normalizePriceInput(initialState.max_price || initialState.price_max || ""),
    min_rating: String(initialState.min_rating || initialState.rating_min || ""),
    discounted: truthyFilterValue(initialState.discounted) || truthyFilterValue(initialState.has_discount),
    verified: truthyFilterValue(initialState.verified) || truthyFilterValue(initialState.verified_only),
    availability: initialState.availability || (truthyFilterValue(initialState.available_today) ? "today" : truthyFilterValue(initialState.available_this_week) ? "this_week" : ""),
  };

  let isSheetOpen = false;
  let areDesktopResultsOpen = true;
  let isFetching = false;
  let suggestionsData = [];

  function syncMobileResultsIcon() {
    if (!openFilterBtn || !openFilterIcon) return;

    openFilterBtn.setAttribute("aria-expanded", String(isSheetOpen));
    openFilterBtn.setAttribute("aria-label", isSheetOpen ? "نمایش نقشه" : "نمایش نتایج");

    openFilterIcon.classList.remove("fa-map-location-dot", "fa-sliders", "fa-magnifying-glass");
    openFilterIcon.classList.add(isSheetOpen ? "fa-map-location-dot" : "fa-sliders");

    searchBarButton?.classList.remove("hidden");
    searchBarButton?.classList.add("inline-flex");
  }

  function syncDesktopResultsIcon() {
    if (!desktopResultsToggleBtn || !desktopResultsToggleIcon) return;

    desktopResultsToggleBtn.setAttribute("aria-label", "باز کردن فیلترها");
    desktopResultsToggleBtn.setAttribute("aria-controls", "filterScreen");
    desktopResultsToggleBtn.setAttribute("aria-haspopup", "dialog");
    desktopResultsToggleBtn.removeAttribute("aria-expanded");

    desktopResultsToggleIcon.classList.add("fa-sliders");
    desktopResultsToggleIcon.classList.remove("fa-map-location-dot", "fa-magnifying-glass");

    desktopSearchField?.classList.remove("hidden");
    desktopSearchField?.classList.add("flex-1");
    desktopSearchPanel?.classList.add("w-full", "p-2.5", "border-loomera-borderSoft", "bg-white/95", "shadow-lm-card", "backdrop-blur-xl");
    desktopSearchPanel?.classList.remove("w-auto", "p-0", "border-transparent", "bg-transparent", "shadow-none");
  }

  function setDesktopResultsOpen(open = true) {
    areDesktopResultsOpen = true;

    mapPane?.classList.add("lg:right-[440px]");
    mapPane?.classList.remove("lg:right-0");

    filtersSheet.classList.remove("lg:hidden");

    contentPane?.classList.add("lg:border-l", "lg:border-loomera-borderSoft", "lg:bg-loomera-surface/95", "lg:shadow-lm-elevated", "lg:backdrop-blur-xl");
    contentPane?.classList.remove("lg:border-transparent", "lg:bg-transparent", "lg:shadow-none", "lg:backdrop-blur-0");

    syncDesktopResultsIcon();
  }

  function setSheetOpen(open) {
    isSheetOpen = open;
    filtersSheet.classList.toggle("translate-y-[calc(100%-4.5rem)]", !open);
    filtersSheet.classList.toggle("translate-y-0", open);
    syncMobileResultsIcon();
    window.setTimeout(() => {
      console.warn("[search] map resize failed");
    }, open ? 320 : 180);
  }

  function openFilterScreen() {
    filterScreen?.classList.remove("hidden");
    window.setTimeout(ensureSearchDatePicker, 80);
  }

  function closeFilterScreen() {
    filterScreen?.classList.add("hidden");
  }

  function ensureSearchDatePicker() {
    if (!dateInput || typeof window.jalaliDatepicker === "undefined") return;

    try {
      window.jalaliDatepicker.startWatch({
        selector: "#filterDateInput",
        autoHide: true,
        hideAfterChange: true,
      });
    } catch (error) {
      console.warn("[search] datepicker initialization failed");
    }

    window.setTimeout(() => {
      document
        .querySelectorAll(".jdp-popover, .jdp-container, .jalali-datepicker, [data-jdp-container]")
        .forEach((picker) => {
          picker.style.zIndex = "99999";
        });
    }, 0);
  }

  function showLoading(show) {
    searchLoading?.classList.toggle("hidden", !show);
    salonList.classList.toggle("hidden", show);
  }

  function setStatus(message = "") {
    if (!searchStatus) return;
    searchStatus.textContent = message;
    searchStatus.classList.toggle("hidden", !message);
  }

  function setFilterValidation(message = "") {
    if (!filterValidationMessage) return;
    filterValidationMessage.textContent = message;
    filterValidationMessage.classList.toggle("hidden", !message);
  }

  function buildSummary(summary) {
    if (summary) return summary;
    const parts = [];
    if (state.services.length === 1) {
      const chip = serviceOptionChips.find((item) => item.dataset.serviceId === state.services[0]);
      parts.push(chip?.dataset.serviceName || serviceSearchInput?.value?.trim() || "");
    } else if (state.services.length > 1) {
      parts.push(`${state.services.length} خدمت`);
    } else if (state.q) {
      parts.push(state.q);
    }
    if (state.location) parts.push(state.location);
    if (state.date) parts.push(state.date);
    if (state.period) {
      const chip = timeChips.find((item) => item.dataset.period === state.period);
      parts.push(chip?.textContent?.trim() || state.period);
    }
    if (state.time) parts.push(state.time);
    if (state.min_price) parts.push(`از ${formatPriceLabel(state.min_price)} تومان`);
    if (state.max_price) parts.push(`تا ${formatPriceLabel(state.max_price)} تومان`);
    if (state.min_rating) parts.push(`امتیاز ${state.min_rating}+`);
    if (state.discounted) parts.push("تخفیف‌دار");
    if (state.verified) parts.push("تاییدشده");
    if (state.availability === "today") parts.push("وقت آزاد امروز");
    if (state.availability === "this_week") parts.push("وقت آزاد این هفته");
    return parts.filter(Boolean).join(" • ") || "جستجو سالن، خدمات یا منطقه...";
  }

  function updateUrl() {
    const params = new URLSearchParams();
    if (state.q) params.set("q", state.q);
    if (state.location) params.set("location", state.location);
    if (state.date) params.set("date", state.date);
    if (state.period) params.set("period", state.period);
    if (state.time) params.set("time", state.time);
    if (state.group) params.set("group", state.group);
    if (state.services.length) params.set("services", state.services.join(","));
    if (state.sort) params.set("sort", state.sort);
    if (state.lat) params.set("lat", state.lat);
    if (state.lng) params.set("lng", state.lng);
    if (state.min_price) params.set("min_price", state.min_price);
    if (state.max_price) params.set("max_price", state.max_price);
    if (state.min_rating) params.set("min_rating", state.min_rating);
    if (state.discounted) params.set("discounted", "1");
    if (state.verified) params.set("verified", "1");
    if (state.availability) params.set("availability", state.availability);
    const url = `${searchPageUrl}${params.toString() ? `?${params}` : ""}`;
    window.history.replaceState({}, "", url);
  }

  function activeFilterItems() {
    const items = [];
    if (state.q) items.push({ key: "q", label: "جستجو", value: state.q });
    if (state.location) items.push({ key: "location", label: "موقعیت", value: state.location });
    if (state.group) items.push({ key: "group", label: "دسته", value: selectedGroupTitle?.textContent?.trim() || "انتخاب‌شده" });
    state.services.forEach((serviceId) => {
      const chip = serviceOptionChips.find((item) => String(item.dataset.serviceId) === String(serviceId));
      items.push({ key: `service:${serviceId}`, label: "خدمت", value: chip?.dataset.serviceName || state.serviceNames[serviceId] || "خدمت" });
    });
    if (state.date) items.push({ key: "date", label: "تاریخ", value: state.date });
    if (state.period) {
      const chip = timeChips.find((item) => item.dataset.period === state.period);
      items.push({ key: "period", label: "بازه روز", value: chip?.textContent?.trim() || state.period });
    }
    if (state.time) items.push({ key: "time", label: "ساعت", value: state.time });
    if (state.sort && state.sort !== "recommended") {
      const chip = sortChips.find((item) => item.dataset.sort === state.sort);
      items.push({ key: "sort", label: "مرتب‌سازی", value: chip?.textContent?.trim() || state.sort });
    }
    if (state.min_price) items.push({ key: "min_price", label: "قیمت", value: `از ${formatPriceLabel(state.min_price)} تومان` });
    if (state.max_price) items.push({ key: "max_price", label: "قیمت", value: `تا ${formatPriceLabel(state.max_price)} تومان` });
    if (state.min_rating) items.push({ key: "min_rating", label: "امتیاز", value: `${state.min_rating}+` });
    if (state.discounted) items.push({ key: "discounted", label: "تخفیف", value: "فقط تخفیف‌دارها" });
    if (state.verified) items.push({ key: "verified", label: "تایید", value: "فقط سالن‌های تاییدشده" });
    if (state.availability === "today") items.push({ key: "availability", label: "وقت آزاد", value: "امروز" });
    if (state.availability === "this_week") items.push({ key: "availability", label: "وقت آزاد", value: "این هفته" });
    return items;
  }

  function removeActiveFilter(key) {
    if (key.startsWith("service:")) {
      const serviceId = key.split(":")[1];
      state.services = state.services.filter((value) => value !== serviceId);
    } else if (key === "group") {
      state.group = "";
      if (selectedGroupTitle) selectedGroupTitle.textContent = "";
    } else if (key === "q") {
      state.q = "";
      state.services = [];
      state.serviceNames = {};
    } else if (key === "location") {
      state.location = "";
      state.lat = "";
      state.lng = "";
    } else if (key === "sort") {
      state.sort = "recommended";
    } else if (key === "availability") {
      state.availability = "";
    } else if (Object.prototype.hasOwnProperty.call(state, key)) {
      state[key] = typeof state[key] === "boolean" ? false : "";
    }
    syncInputs();
    applySearch();
  }

  function renderActiveFilterChips() {
    const items = activeFilterItems();
    const containers = [activeFiltersChips, activeFiltersChipsScreen].filter(Boolean);
    [activeFiltersBar, activeFiltersBarScreen].forEach((bar) => bar?.classList.toggle("hidden", items.length === 0));
    containers.forEach((container) => {
      container.innerHTML = "";
      items.forEach((item) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "inline-flex items-center gap-2 rounded-full border border-loomera-primary/20 bg-loomera-primarySoft px-3 py-2 text-[11px] font-black text-loomera-primary transition hover:border-rose-200 hover:bg-rose-50 hover:text-rose-600";
        button.innerHTML = `<span class="opacity-70">${item.label}:</span><span>${item.value}</span><i class="fa-solid fa-xmark text-[10px]"></i>`;
        button.setAttribute("aria-label", `حذف فیلتر ${item.label}`);
        button.addEventListener("click", () => removeActiveFilter(item.key));
        container.appendChild(button);
      });
    });
  }

  function syncInputs() {
    if (serviceSearchInput && document.activeElement !== serviceSearchInput) {
      serviceSearchInput.value = state.q;
    }
    if (locationInput) locationInput.value = state.location;
    if (dateInput) dateInput.value = state.date;
    if (timeInput) timeInput.value = state.time;
    if (minPriceInput) minPriceInput.value = state.min_price;
    if (maxPriceInput) maxPriceInput.value = state.max_price;
    if (minRatingInput) minRatingInput.value = state.min_rating;

    filterToggleChips.forEach((chip) => {
      const key = chip.dataset.filterToggle;
      const active = key === "discounted" ? state.discounted : key === "verified" ? state.verified : false;
      chip.classList.toggle("bg-loomera-primary", active);
      chip.classList.toggle("text-white", active);
      chip.classList.toggle("border-loomera-primary", active);
      chip.classList.toggle("bg-white", !active);
      chip.classList.toggle("text-loomera-textSecondary", !active);
      chip.classList.toggle("border-loomera-borderSoft", !active);
    });

    availabilityChips.forEach((chip) => {
      const active = (chip.dataset.availability || "") === state.availability;
      chip.classList.toggle("bg-loomera-primary", active);
      chip.classList.toggle("text-white", active);
      chip.classList.toggle("border-loomera-primary", active);
      chip.classList.toggle("bg-white", !active);
      chip.classList.toggle("text-loomera-textSecondary", !active);
      chip.classList.toggle("border-loomera-borderSoft", !active);
    });

    timeChips.forEach((chip) => {
      const active = (chip.dataset.period || "") === state.period;
      chip.classList.toggle("bg-loomera-primary", active);
      chip.classList.toggle("text-white", active);
      chip.classList.toggle("border-loomera-primary", active);
      chip.classList.toggle("bg-white", !active);
      chip.classList.toggle("text-loomera-textSecondary", !active);
      chip.classList.toggle("border-loomera-borderSoft", !active);
    });

    sortChips.forEach((chip) => {
      const active = (chip.dataset.sort || "recommended") === state.sort;
      chip.classList.toggle("bg-loomera-primary", active);
      chip.classList.toggle("text-white", active);
      chip.classList.toggle("border-loomera-primary", active);
      chip.classList.toggle("bg-white", !active);
      chip.classList.toggle("text-loomera-textSecondary", !active);
      chip.classList.toggle("border-loomera-borderSoft", !active);
    });

    serviceOptionChips.forEach((chip) => {
      const active = state.services.includes(String(chip.dataset.serviceId));
      chip.classList.toggle("bg-loomera-primary", active);
      chip.classList.toggle("text-white", active);
      chip.classList.toggle("border-loomera-primary", active);
      chip.classList.toggle("bg-loomera-bgSubtle", !active);
      chip.classList.toggle("text-loomera-textSecondary", !active);
      chip.classList.toggle("border-loomera-borderSoft", !active);
    });

    if (selectedServicesList) {
      selectedServicesList.innerHTML = "";
      state.services.forEach((serviceId) => {
        const chip = serviceOptionChips.find((item) => String(item.dataset.serviceId) === String(serviceId));
        if (!chip) return;
        const button = document.createElement("button");
        button.type = "button";
        button.className = "inline-flex items-center gap-2 rounded-full border border-loomera-borderSoft bg-white px-3 py-1.5 text-[11px] font-bold text-loomera-textSecondary transition hover:bg-loomera-primarySoft hover:text-loomera-primary";
        button.innerHTML = `<span>${chip?.dataset.serviceName || state.serviceNames[serviceId] || "خدمت"}</span><i class="fa-solid fa-xmark text-[10px]"></i>`;
        button.addEventListener("click", () => {
          state.services = state.services.filter((value) => value !== String(serviceId));
          syncInputs();
          applySearch();
        });
        selectedServicesList.appendChild(button);
      });
    }
    renderActiveFilterChips();
  }

  function buildParams() {
    const params = new URLSearchParams();
    if (state.q) params.set("q", state.q);
    if (state.location) params.set("location", state.location);
    if (state.date) params.set("date", state.date);
    if (state.period) params.set("period", state.period);
    if (state.time) params.set("time", state.time);
    if (state.group) params.set("group", state.group);
    if (state.services.length) params.set("services", state.services.join(","));
    if (state.sort) params.set("sort", state.sort);
    if (state.lat) params.set("lat", state.lat);
    if (state.lng) params.set("lng", state.lng);
    if (state.min_price) params.set("min_price", state.min_price);
    if (state.max_price) params.set("max_price", state.max_price);
    if (state.min_rating) params.set("min_rating", state.min_rating);
    if (state.discounted) params.set("discounted", "1");
    if (state.verified) params.set("verified", "1");
    if (state.availability) params.set("availability", state.availability);
    return params;
  }

  async function applySearch() {
    if (isFetching) return;
    if ((state.period || state.time) && !state.date) {
      const validationMessage = "برای فیلتر زمان، ابتدا تاریخ را انتخاب کنید.";
      setStatus(validationMessage);
      setFilterValidation(validationMessage);
      dateInput?.focus();
      return;
    }
    setFilterValidation("");
    isFetching = true;
    showLoading(true);
    setStatus("در حال به‌روزرسانی نتایج...");

    try {
      const response = await fetch(`${searchEndpoint}?${buildParams().toString()}`, {
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      if (!response.ok) throw new Error(`status ${response.status}`);
      const payload = await response.json();
      salonList.innerHTML = payload.html || "";
      if (resultsCountEl) resultsCountEl.textContent = `${payload.count || 0} سالن`;
      if (searchBarText) searchBarText.textContent = buildSummary(payload.summary || "");
      setStatus(payload.count ? "" : "هیچ سالنی با این فیلترها پیدا نشد.");
      updateUrl();
      if (window.searchMapController?.setSalons) {
        window.searchMapController.setSalons(payload.salons || []);
      }
      setSheetOpen(true);
      setDesktopResultsOpen(true);
      closeFilterScreen();
      const clearButton = salonList.querySelector("[data-clear-search]");
      clearButton?.addEventListener("click", resetFilters);
    } catch (error) {
      console.error("[search] result update failed");
      setStatus("به‌روزرسانی نتایج انجام نشد. دوباره تلاش کنید.");
    } finally {
      showLoading(false);
      isFetching = false;
    }
  }

  function resetFilters() {
    state.q = "";
    state.location = "";
    state.date = "";
    state.period = "";
    state.time = "";
    state.group = "";
    state.services = [];
    state.sort = "recommended";
    state.lat = "";
    state.lng = "";
    state.min_price = "";
    state.max_price = "";
    state.min_rating = "";
    state.discounted = false;
    state.verified = false;
    state.availability = "";
    if (selectedGroupTitle) selectedGroupTitle.textContent = "";
    syncInputs();
    applySearch();
  }

  async function setActiveSort(sort) {
    const nextSort = sort || "recommended";

    if (nextSort === "nearest" && (!state.lat || !state.lng)) {
      const ok = await requestCurrentLocationForSearch({
        applyAfterSuccess: false,
        silent: false,
      });

      if (!ok) {
        state.sort = "recommended";
        syncInputs();
        setStatus("برای مرتب‌سازی نزدیک‌ترین، باید دسترسی موقعیت فعلی را فعال کنی.");
        return;
      }
    }

    state.sort = nextSort;
    syncInputs();
    applySearch();
  }

  function requestCurrentLocationForSearch(options = {}) {
    const { applyAfterSuccess = true, silent = false } = options;

    return new Promise((resolve) => {
      if (!navigator.geolocation) {
        if (!silent) setStatus("دسترسی به موقعیت فعلی در این دستگاه در دسترس نیست.");
        resolve(false);
        return;
      }

      if (!silent) setStatus("در حال دریافت موقعیت فعلی...");

      navigator.geolocation.getCurrentPosition(
        (position) => {
          state.lat = String(position.coords.latitude);
          state.lng = String(position.coords.longitude);
          state.location = "نزدیک من";

          syncInputs();

          window.searchMapController?.focusUserLocation?.({
            lat: position.coords.latitude,
            lng: position.coords.longitude,
          });

          if (applyAfterSuccess) {
            applySearch();
          } else if (!silent) {
            setStatus("موقعیت فعلی دریافت شد. نتایج بر اساس نزدیک‌ترین مرتب می‌شوند.");
          }

          resolve(true);
        },
        () => {
          if (!silent) setStatus("دسترسی به موقعیت فعلی انجام نشد.");
          resolve(false);
        },
        {
          enableHighAccuracy: true,
          timeout: 10000,
          maximumAge: 60000,
        }
      );
    });
  }

  async function loadLocationSuggestions(query = "") {
    const endpoint = document.body.dataset.locationSuggestUrl || document.body.dataset.salonLocationsUrl;
    if (!endpoint || !locationSuggestions) return;

    const normalized = (query || "").trim();

    try {
      const url = `${endpoint}?q=${encodeURIComponent(normalized)}`;
      const response = await fetch(url, {
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });

      if (!response.ok) throw new Error(`status ${response.status}`);

      const payload = await response.json();
      const items = Array.isArray(payload) ? payload : (payload.results || []);

      locationSuggestions.innerHTML = "";

      const nearMeRow = document.createElement("li");
      nearMeRow.className = "cursor-pointer px-3 py-2 transition hover:bg-loomera-primarySoft";
      nearMeRow.innerHTML = `
        <div class="flex items-center gap-2 font-black text-loomera-textPrimary">
          <i class="fa-solid fa-location-crosshairs text-loomera-primary" aria-hidden="true"></i>
          <span>نزدیک من</span>
        </div>
        <div class="mt-1 text-[10px] text-loomera-textMuted">استفاده از موقعیت فعلی دستگاه</div>
      `;
      nearMeRow.addEventListener("click", async () => {
        locationSuggestions.classList.add("hidden");
        await requestCurrentLocationForSearch({ applyAfterSuccess: false });
      });
      locationSuggestions.appendChild(nearMeRow);

      items.slice(0, 10).forEach((item) => {
        const value = item.value || item.name || "";
        if (!value) return;

        const row = document.createElement("li");
        row.className = "cursor-pointer px-3 py-2 transition hover:bg-loomera-primarySoft";
        row.innerHTML = `
          <div class="font-black text-loomera-textPrimary">${value}</div>
          <div class="mt-1 text-[10px] text-loomera-textMuted">${item.meta || item.type_label || "محله"}</div>
        `;

        row.addEventListener("click", () => {
          state.location = value;
          state.lat = "";
          state.lng = "";
          locationInput.value = state.location;
          locationSuggestions.classList.add("hidden");
          syncInputs();
        });

        locationSuggestions.appendChild(row);
      });

      locationSuggestions.classList.toggle("hidden", locationSuggestions.children.length === 0);
    } catch (error) {
      console.warn("[search] location suggestions unavailable");
      locationSuggestions.classList.add("hidden");
    }
  }

  async function loadServiceSuggestions(query = "") {
    if (!serviceSearchSuggestions) return;
    const endpoint = document.body.dataset.serviceSuggestUrl;
    if (!endpoint || !query.trim()) {
      serviceSearchSuggestions.classList.add("hidden");
      return;
    }
    try {
      const response = await fetch(`${endpoint}?q=${encodeURIComponent(query)}`, { headers: { "X-Requested-With": "XMLHttpRequest" } });
      if (!response.ok) throw new Error(`status ${response.status}`);
      const payload = await response.json();
      const services = payload.services || payload.results || [];
      serviceSearchSuggestions.innerHTML = "";
      const salons = payload.salons || [];
      const appendSectionTitle = (label) => {
        const section = document.createElement("li");
        section.className = "px-3 pt-2 pb-1 text-[10px] font-black text-loomera-textMuted";
        section.textContent = label;
        serviceSearchSuggestions.appendChild(section);
      };

      if (services.length) {
        appendSectionTitle("خدمات");
      }
      services.slice(0, 8).forEach((service) => {
        const item = document.createElement("li");
        const serviceId = String(service.id || service.pk || "");
        const serviceName = service.service_name || service.name || "خدمت";
        item.className = "cursor-pointer px-3 py-2 transition hover:bg-loomera-primarySoft";
        item.innerHTML = `<div class="font-black text-loomera-textPrimary">${serviceName}</div><div class="mt-1 text-[10px] text-loomera-textMuted">خدمت</div>`;
        item.addEventListener("click", () => {
          if (serviceId && !state.services.includes(serviceId)) {
            state.services.push(serviceId);
          }
          if (serviceId) {
            state.serviceNames[serviceId] = serviceName;
          }
          state.q = serviceName;
          serviceSearchInput.value = serviceName;
          serviceSearchSuggestions.classList.add("hidden");
          syncInputs();
        });
        serviceSearchSuggestions.appendChild(item);
      });

      if (salons.length) {
        appendSectionTitle("سالن‌ها");
      }
      salons.slice(0, 6).forEach((salon) => {
        const salonName = salon.salon_name || salon.name || "سالن";
        const salonMeta = [salon.neighborhood, salon.address].filter(Boolean).join(" • ");
        const item = document.createElement("li");
        item.className = "cursor-pointer px-3 py-2 transition hover:bg-loomera-primarySoft";
        item.innerHTML = `<div class="font-black text-loomera-textPrimary">${salonName}</div><div class="mt-1 text-[10px] text-loomera-textMuted">${salonMeta || "سالن"}</div>`;
        item.addEventListener("click", () => {
          state.q = salonName;
          serviceSearchInput.value = salonName;
          serviceSearchSuggestions.classList.add("hidden");
          syncInputs();
        });
        serviceSearchSuggestions.appendChild(item);
      });
      serviceSearchSuggestions.classList.toggle("hidden", serviceSearchSuggestions.children.length === 0);
    } catch (error) {
      console.warn("[search] service suggestions unavailable");
      serviceSearchSuggestions.classList.add("hidden");
    }
  }

  serviceOptionChips.forEach((chip) => {
    chip.addEventListener("click", () => {
      const serviceId = String(chip.dataset.serviceId || "");
      if (!serviceId) return;
      if (state.services.includes(serviceId)) {
        state.services = state.services.filter((value) => value !== serviceId);
      } else {
        state.services = [...state.services, serviceId];
      }
      syncInputs();
    });
  });

  categoryCards.forEach((card) => {
    card.addEventListener("click", (event) => {
      event.preventDefault();
      state.group = String(card.dataset.searchGroup || "");
      state.services = [];
      if (selectedGroupTitle) selectedGroupTitle.textContent = card.dataset.groupTitle || "";
      syncInputs();
      applySearch();
    });
  });

  clearGroupLink?.addEventListener("click", (event) => {
    event.preventDefault();
    state.group = "";
    syncInputs();
    applySearch();
  });

  timeChips.forEach((chip) => {
    chip.addEventListener("click", () => {
      state.period = chip.dataset.period || "";
      if (!state.period) state.time = "";
      syncInputs();
    });
  });

  sortChips.forEach((chip) => {
    chip.addEventListener("click", () => setActiveSort(chip.dataset.sort || "recommended"));
  });

  const debouncedLocationSuggestions = debounce(() => loadLocationSuggestions(locationInput?.value || ""), 150);
  const debouncedServiceSuggestions = debounce(() => loadServiceSuggestions(serviceSearchInput?.value || ""), 180);

  locationInput?.addEventListener("input", () => {
    state.location = locationInput.value.trim();
    if (state.location !== "نزدیک من") {
      state.lat = "";
      state.lng = "";
    }
    debouncedLocationSuggestions();
  });
  locationInput?.addEventListener("focus", () => loadLocationSuggestions(locationInput.value || ""));

  serviceSearchInput?.addEventListener("input", () => {
    state.q = serviceSearchInput.value.trim();
    debouncedServiceSuggestions();
  });
  serviceSearchInput?.addEventListener("focus", () => {
    if (serviceSearchInput.value.trim()) loadServiceSuggestions(serviceSearchInput.value.trim());
  });

  dateInput?.addEventListener("focus", ensureSearchDatePicker);
  dateInput?.addEventListener("click", ensureSearchDatePicker);
  document.querySelector("[data-open-search-date-picker]")?.addEventListener("click", () => {
    openFilterScreen();
    window.setTimeout(() => {
      ensureSearchDatePicker();
      dateInput?.focus();
      dateInput?.click();
    }, 120);
  });

  dateInput?.addEventListener("change", () => {
    state.date = dateInput.value.trim();
  });

  timeInput?.addEventListener("change", () => {
    state.time = timeInput.value;
  });

  minPriceInput?.addEventListener("input", () => {
    state.min_price = normalizePriceInput(minPriceInput.value);
    renderActiveFilterChips();
  });
  maxPriceInput?.addEventListener("input", () => {
    state.max_price = normalizePriceInput(maxPriceInput.value);
    renderActiveFilterChips();
  });
  minRatingInput?.addEventListener("change", () => {
    state.min_rating = minRatingInput.value;
    syncInputs();
  });

  filterToggleChips.forEach((chip) => {
    chip.addEventListener("click", () => {
      const key = chip.dataset.filterToggle;
      if (key === "discounted") state.discounted = !state.discounted;
      if (key === "verified") state.verified = !state.verified;
      syncInputs();
    });
  });

  availabilityChips.forEach((chip) => {
    chip.addEventListener("click", () => {
      const value = chip.dataset.availability || "";
      state.availability = state.availability === value ? "" : value;
      syncInputs();
    });
  });

  clearActiveFilterButtons.forEach((button) => {
    button.addEventListener("click", resetFilters);
  });

  useCurrentLocationBtn?.addEventListener("click", () => {
    requestCurrentLocationForSearch({ applyAfterSuccess: true });
  });

  locateButtons.forEach((button) => {
    button.addEventListener("click", () => useCurrentLocationBtn?.click());
  });

  searchBarButton?.addEventListener("click", openFilterScreen);
  openFilterBtn?.addEventListener("click", () => setSheetOpen(!isSheetOpen));
  desktopResultsToggleBtn?.addEventListener("click", openFilterScreen);
  filtersHandle?.addEventListener("click", () => setSheetOpen(!isSheetOpen));
  filterBackBtn?.addEventListener("click", closeFilterScreen);
  filterSheetOpenBtn?.addEventListener("click", openFilterScreen);
  filterApplyBtn?.addEventListener("click", applySearch);
  clearFiltersFullBtn?.addEventListener("click", resetFilters);
  clearFiltersSheetBtn?.addEventListener("click", resetFilters);

  document.addEventListener("click", (event) => {
    if (!locationSuggestions?.contains(event.target) && event.target !== locationInput) {
      locationSuggestions?.classList.add("hidden");
    }
    if (!serviceSearchSuggestions?.contains(event.target) && event.target !== serviceSearchInput) {
      serviceSearchSuggestions?.classList.add("hidden");
    }
  });

  setSheetOpen(false);
  setDesktopResultsOpen(true);
  ensureSearchDatePicker();
  syncInputs();
  updateUrl();
  salonList.querySelector("[data-clear-search]")?.addEventListener("click", resetFilters);
  window.searchFiltersController = { applySearch, resetFilters, setSheetOpen, openFilterScreen, state };
}
