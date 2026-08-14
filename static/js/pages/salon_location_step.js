let salonLocationStepBound = false;

function setMessageState(messageBox, type, text) {
  if (!messageBox) return;

  const baseClasses = "mt-3 rounded-2xl border px-4 py-3 text-xs font-bold";
  const typeClasses = {
    loading: "border-blue-200 bg-blue-50 text-blue-700",
    success: "border-emerald-200 bg-emerald-50 text-emerald-700",
    warning: "border-amber-200 bg-amber-50 text-amber-700",
  };

  messageBox.className = `${baseClasses} ${typeClasses[type] || typeClasses.warning}`;
  messageBox.classList.remove("hidden");
  messageBox.innerHTML = text;
}

function hideMessage(messageBox) {
  if (!messageBox) return;
  messageBox.className = "mt-3 hidden rounded-2xl border px-4 py-3 text-xs font-bold";
  messageBox.innerHTML = "";
}

function waitForLeaflet(timeout = 6000) {
  return new Promise((resolve, reject) => {
    const startedAt = Date.now();

    const check = () => {
      if (typeof window.L !== "undefined") {
        resolve();
        return;
      }

      if (Date.now() - startedAt > timeout) {
        reject(new Error("Leaflet unavailable"));
        return;
      }

      window.setTimeout(check, 80);
    };

    check();
  });
}

function patchLeafletMarkerIcon(markerIconUrl) {
  if (!window.L?.Icon?.Default || !markerIconUrl) return;

  delete window.L.Icon.Default.prototype._getIconUrl;
  window.L.Icon.Default.imagePath = "";

  window.L.Icon.Default.mergeOptions({
    iconUrl: markerIconUrl,
    iconRetinaUrl: markerIconUrl,
    shadowUrl: "",
    shadowRetinaUrl: "",
    iconSize: [25, 41],
    iconAnchor: [12, 41],
    popupAnchor: [1, -34],
    tooltipAnchor: [16, -28],
    shadowSize: [0, 0],
  });
}

function createMarkerIcon(markerIconUrl) {
  if (!window.L?.icon || !markerIconUrl) return null;

  return window.L.icon({
    iconUrl: markerIconUrl,
    iconRetinaUrl: markerIconUrl,
    shadowUrl: "",
    shadowRetinaUrl: "",
    iconSize: [25, 41],
    iconAnchor: [12, 41],
    popupAnchor: [1, -34],
    tooltipAnchor: [16, -28],
    shadowSize: [0, 0],
    className: "salon-location-marker",
  });
}

export default function initSalonLocationStep() {
  if (salonLocationStepBound) return;
  salonLocationStepBound = true;

  const body = document.body;
  const mapEnabled = String(body.dataset.mapEnabled || "").toLowerCase() === "true";
  const reverseGeocodeUrl = body.dataset.reverseGeocodeUrl || "";
  const mapTileUrlTemplate = body.dataset.mapTileUrlTemplate || "";
  const markerIconUrl = body.dataset.markerIconUrl || "";
  const markerIcon = createMarkerIcon(markerIconUrl);

  const mapRoot = document.getElementById("salon-location-map");
  const form = document.getElementById("salonLocationForm");
  const submitBtn = document.getElementById("submitStepBtn");
  const useCurrentLocationBtn = document.getElementById("useCurrentLocationBtn");
  const clearLocationBtn = document.getElementById("clearLocationBtn");
  const warningBox = document.getElementById("mapWarning");
  const addressMessageBox = document.getElementById("addressAutofillMessage");

  const latitudeInput = document.getElementById("id_latitude");
  const longitudeInput = document.getElementById("id_longitude");
  const zoneInput = document.getElementById("id_zone");
  const neighborhoodInput = document.getElementById("id_neighborhood");
  const neighborhoodNameInput = document.getElementById("id_neighborhood_name");
  const zoneLabelInput = document.getElementById("id_zone_label");
  const zoneDisplayInput = document.getElementById("id_zone_display");
  const neighborhoodDisplayInput = document.getElementById("id_neighborhood_display");
  const addressInput = document.getElementById("id_address");
  const plaqueInput = document.getElementById("id_address_plaque");
  const unitInput = document.getElementById("id_address_unit");

  if (!mapRoot || !form || !submitBtn || !latitudeInput || !longitudeInput || !addressInput || !plaqueInput || !unitInput) {
    return;
  }

  let mapInstance = null;
  let marker = null;
  let reverseLookupCounter = 0;

  const tileSeedUrl = body.dataset.mapTileSeedUrl || "/search/map-tiles/0/0/0/";
  const tileUrl = mapTileUrlTemplate
    ? mapTileUrlTemplate
        .replace("987654", "{z}")
        .replace("876543", "{x}")
        .replace("765432", "{y}")
    : tileSeedUrl.replace(/0\/0\/0\/?$/, "{z}/{x}/{y}/");

  function ensureMapDimensions() {
    if (!mapRoot) return;
    const computed = window.getComputedStyle(mapRoot);
    if (parseFloat(computed.height || "0") <= 0) {
      mapRoot.style.height = window.matchMedia("(min-width: 640px)").matches ? "400px" : "320px";
    }
  }

  function showMapWarning(message) {
    if (!warningBox) return;
    warningBox.textContent = message;
    warningBox.classList.remove("hidden");
  }

  function clearMapWarning() {
    if (!warningBox) return;
    warningBox.classList.add("hidden");
    warningBox.textContent = "";
  }

  function hasSelectedLocation() {
    return Boolean(latitudeInput.value && longitudeInput.value);
  }

  function syncSubmitState() {
    submitBtn.disabled = !(
      hasSelectedLocation() &&
      addressInput.value.trim() &&
      plaqueInput.value.trim() &&
      unitInput.value.trim()
    );
  }

  function normalizeText(value) {
    return String(value || "").trim();
  }

  function normalizeDigits(value) {
    const map = {"۰":"0","۱":"1","۲":"2","۳":"3","۴":"4","۵":"5","۶":"6","۷":"7","۸":"8","۹":"9","٠":"0","١":"1","٢":"2","٣":"3","٤":"4","٥":"5","٦":"6","٧":"7","٨":"8","٩":"9"};
    return String(value || "").replace(/[۰-۹٠-٩]/g, (digit) => map[digit] || digit);
  }

  function applyReverseArea(data = {}) {
    const zoneValue = normalizeDigits(data.zone || "").replace(/[^0-9]/g, "");
    const zoneLabel = normalizeText(data.zone_label) || (zoneValue ? `منطقه ${zoneValue}` : "");
    const neighborhood = normalizeText(data.neighborhood);

    if (zoneInput) zoneInput.value = zoneValue;
    if (zoneLabelInput) zoneLabelInput.value = zoneLabel;
    if (zoneDisplayInput) zoneDisplayInput.value = zoneLabel;

    if (neighborhoodInput) neighborhoodInput.value = "";
    if (neighborhoodNameInput) neighborhoodNameInput.value = neighborhood;
    if (neighborhoodDisplayInput) neighborhoodDisplayInput.value = neighborhood;
  }

  async function reverseGeocode(lat, lng) {
    if (!reverseGeocodeUrl) return;

    const requestId = ++reverseLookupCounter;
    setMessageState(
      addressMessageBox,
      "loading",
      '<i class="fa-solid fa-spinner fa-spin ml-1"></i> در حال دریافت آدرس از روی لوکیشن...'
    );

    try {
      const url = new URL(reverseGeocodeUrl, window.location.origin);
      url.searchParams.set("lat", lat);
      url.searchParams.set("lon", lng);

      const response = await fetch(url.toString(), {
        method: "GET",
        headers: {
          "X-Requested-With": "XMLHttpRequest",
        },
      });

      const data = await response.json();

      if (requestId !== reverseLookupCounter) return;

      if (response.ok && data.ok) {
        if (data.address) {
          addressInput.value = data.address;
        }
        if (data.plaque) {
          plaqueInput.value = data.plaque;
        }
        applyReverseArea(data);
        const missingArea = !normalizeText(data.neighborhood) || !normalizeText(data.zone);
        setMessageState(
            addressMessageBox,
            missingArea ? "warning" : "success",
            missingArea
              ? '<i class="fa-solid fa-triangle-exclamation ml-1"></i> آدرس دریافت شد، اما منطقه یا محله کامل نبود. پین را کمی جابه‌جا کن یا دوباره تلاش کن.'
              : '<i class="fa-solid fa-check ml-1"></i> آدرس، منطقه و محله بر اساس لوکیشن انتخاب شده وارد شدند. پلاک را بررسی کن و واحد را در فیلد جداگانه وارد کن.'
            );
        clearMapWarning();
      } else {
        setMessageState(
          addressMessageBox,
          "warning",
          '<i class="fa-solid fa-triangle-exclamation ml-1"></i> آدرس خودکار پیدا نشد؛ آدرس را دستی وارد کن.'
        );
      }
    } catch (error) {
      if (requestId !== reverseLookupCounter) return;

      setMessageState(
        addressMessageBox,
        "warning",
        '<i class="fa-solid fa-triangle-exclamation ml-1"></i> دریافت آدرس خودکار انجام نشد؛ آدرس را دستی وارد کن.'
      );
    }
  }

  function setLocation(lat, lng, recenter = false, shouldLookup = true) {
    latitudeInput.value = Number(lat).toFixed(6);
    longitudeInput.value = Number(lng).toFixed(6);

    if (!marker) {
      const markerOptions = { draggable: true };
      if (markerIcon) {
        markerOptions.icon = markerIcon;
      }

      marker = window.L.marker([lat, lng], markerOptions).addTo(mapInstance);
      marker.on("dragend", (event) => {
        const position = event.target.getLatLng();
        setLocation(position.lat, position.lng, false, true);
      });
    } else {
      marker.setLatLng([lat, lng]);
    }

    if (recenter && mapInstance) {
      mapInstance.setView([lat, lng], Math.max(mapInstance.getZoom(), 15));
    }

    syncSubmitState();

    if (shouldLookup) {
      reverseGeocode(lat, lng);
    }
  }

  function clearLocation() {
    latitudeInput.value = "";
    longitudeInput.value = "";

    if (marker && mapInstance) {
      mapInstance.removeLayer(marker);
      marker = null;
    }

    if (zoneInput) zoneInput.value = "";
    if (zoneLabelInput) zoneLabelInput.value = "";
    if (zoneDisplayInput) zoneDisplayInput.value = "";
    if (neighborhoodInput) neighborhoodInput.value = "";
    if (neighborhoodNameInput) neighborhoodNameInput.value = "";
    if (neighborhoodDisplayInput) neighborhoodDisplayInput.value = "";

    reverseLookupCounter += 1;
    hideMessage(addressMessageBox);
    syncSubmitState();
  }

  async function initMap() {
    if (!mapEnabled) {
      showMapWarning("سرویس نقشه داخلی هنوز فعال نشده است. می‌توانی فعلاً آدرس را دستی وارد کنی و بعداً لوکیشن را تکمیل کنی.");
      syncSubmitState();
      return;
    }

    try {
      await waitForLeaflet();
      patchLeafletMarkerIcon(markerIconUrl);
      ensureMapDimensions();

      mapInstance = window.L.map(mapRoot, {
        zoomControl: true,
        attributionControl: true,
        scrollWheelZoom: false,
      }).setView([35.699739, 51.338097], 12);

      const tileLayer = window.L.tileLayer(tileUrl, {
        attribution: "© Map.ir",
        maxZoom: 18,
        tileSize: 256,
      });

      let tileErrors = 0;

      tileLayer.on("tileerror", () => {
        tileErrors += 1;
        if (tileErrors >= 2) {
          showMapWarning("نمایش نقشه در حال حاضر با مشکل مواجه شده است. می‌توانی از موقعیت فعلی استفاده کنی یا چند لحظه بعد دوباره تلاش کنی.");
        }
      });

      tileLayer.addTo(mapInstance);
      clearMapWarning();

      mapInstance.on("click", (event) => {
        setLocation(event.latlng.lat, event.latlng.lng, false, true);
      });

      const initialLat = parseFloat(latitudeInput.value || "");
      const initialLng = parseFloat(longitudeInput.value || "");

      if (!Number.isNaN(initialLat) && !Number.isNaN(initialLng)) {
        setLocation(initialLat, initialLng, true, false);
        if (addressInput.value.trim()) {
          setMessageState(
            addressMessageBox,
            "success",
            '<i class="fa-solid fa-check ml-1"></i> آدرس ذخیره‌شده قبلی نمایش داده شده است.'
          );
        }
      }

      window.requestAnimationFrame(() => {
        try {
          ensureMapDimensions();
          mapInstance.invalidateSize();
        } catch (error) {}
      });
      window.setTimeout(() => {
        try {
          ensureMapDimensions();
          mapInstance.invalidateSize();
        } catch (error) {}
      }, 250);
    } catch (error) {
      showMapWarning("نمایش نقشه در حال حاضر در دسترس نیست. چند لحظه بعد دوباره تلاش کن یا از موقعیت فعلی استفاده کن.");
    }

    syncSubmitState();
  }

  useCurrentLocationBtn?.addEventListener("click", () => {
    if (!navigator.geolocation) {
      showMapWarning("مرورگر شما دسترسی به موقعیت فعلی را پشتیبانی نمی‌کند.");
      return;
    }

    navigator.geolocation.getCurrentPosition(
      (position) => {
        clearMapWarning();
        setLocation(position.coords.latitude, position.coords.longitude, true, true);
      },
      () => {
        showMapWarning("دسترسی به موقعیت فعلی انجام نشد. لطفاً روی نقشه محل سالن را انتخاب کن.");
      },
      {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 0,
      }
    );
  });

  clearLocationBtn?.addEventListener("click", () => {
    clearLocation();
  });

  [addressInput, plaqueInput, unitInput].forEach((input) => {
    input.addEventListener("input", syncSubmitState);
    input.addEventListener("change", syncSubmitState);
  });

  form.addEventListener("submit", (event) => {
    if (!hasSelectedLocation()) {
      event.preventDefault();
      showMapWarning("برای ادامه، باید موقعیت سالن را روی نقشه انتخاب کنی.");
      mapRoot.scrollIntoView({ behavior: "smooth", block: "center" });
      syncSubmitState();
      return;
    }

    if (!addressInput.value.trim()) {
      event.preventDefault();
      showMapWarning("آدرس مجموعه خالی است. لوکیشن را دوباره انتخاب کن یا آدرس را دستی وارد کن.");
      addressInput.focus();
      return;
    }

    if (!plaqueInput.value.trim()) {
      event.preventDefault();
      showMapWarning("وارد کردن پلاک الزامی است.");
      plaqueInput.focus();
      return;
    }

    if (!unitInput.value.trim()) {
      event.preventDefault();
      showMapWarning("وارد کردن واحد الزامی است.");
      unitInput.focus();
    }
  });

  initMap();
}
