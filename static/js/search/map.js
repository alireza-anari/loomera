function showMapFallback(message) {
  const fallback = document.getElementById("mapFallback");
  if (!fallback) return;
  const text = fallback.querySelector("p.text-xs");
  if (text && message) text.textContent = message;
  fallback.classList.remove("hidden");
}

function hideMapFallback() {
  document.getElementById("mapFallback")?.classList.add("hidden");
}

function buildTileTemplate(rawTemplate) {
  if (!rawTemplate) return "/search/map-tiles/{z}/{x}/{y}/";
  return rawTemplate.replace(/0\/0\/0\/?$/, "{z}/{x}/{y}/").replace(/0\/0\/0$/, "{z}/{x}/{y}");
}

function escapeHtml(value = "") {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatPrice(value) {
  const number = Number(value || 0);
  if (!number) return "";
  try {
    return `${number.toLocaleString("fa-IR")} تومان`;
  } catch (error) {
    return `${number} تومان`;
  }
}

function buildPopupContent(salon = {}) {
  const salonId = salon.id || "";
  const name = escapeHtml(salon.salon_name || salon.name || "سالن زیبایی");
  const location = escapeHtml(salon.neighborhood || salon.address || salon.search_location_label || "");
  const available = escapeHtml(salon.available_label || salon.search_available_label || "");
  const rating = salon.rating || salon.avg_score || salon.score || "";
  const reviews = salon.reviews || salon.total_reviews || salon.num_scores || "";
  const price = formatPrice(salon.price || salon.search_primary_price);
  const detailUrl = escapeHtml(salon.detail_url || salon.url || "#");
  const imageUrl = escapeHtml(salon.image_url || salon.banner_image || salon.banner_image_url || salon.cover_image_url || "");

  return `
    <article dir="rtl" class="overflow-hidden text-right">
      ${imageUrl ? `
        <a href="${detailUrl}" class="block h-28 overflow-hidden bg-loomera-bgSubtle" aria-label="مشاهده ${name}">
          <img src="${imageUrl}" alt="${name}" class="h-full w-full object-cover" loading="lazy">
        </a>
      ` : ""}
      <div class="bg-gradient-to-l from-loomera-primarySoft via-white to-white px-4 pb-3 pt-4">
        <div class="flex items-start gap-3">
          <span class="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-white text-loomera-primary shadow-lm-soft">
            <i class="fa-solid fa-location-dot" aria-hidden="true"></i>
          </span>
          <div class="min-w-0 flex-1 pl-7">
            <h3 class="line-clamp-2 text-sm font-black leading-6 text-loomera-textPrimary">${name}</h3>
            ${location ? `<p class="mt-1 line-clamp-2 text-xs leading-5 text-loomera-textMuted">${location}</p>` : ""}
          </div>
        </div>
      </div>

      <div class="space-y-3 px-4 py-3">
        <div class="flex flex-wrap items-center gap-2 text-[11px]">
          ${rating ? `<span class="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2.5 py-1 font-black text-amber-700"><i class="fa-solid fa-star text-[10px]" aria-hidden="true"></i>${escapeHtml(rating)}</span>` : ""}
          ${reviews ? `<span class="rounded-full bg-loomera-bgSubtle px-2.5 py-1 font-bold text-loomera-textMuted">${escapeHtml(reviews)} نظر</span>` : ""}
          ${price ? `<span class="rounded-full bg-loomera-primarySoft px-2.5 py-1 font-black text-loomera-primary">از ${escapeHtml(price)}</span>` : ""}
        </div>

        ${available ? `<p class="rounded-2xl border border-emerald-100 bg-emerald-50 px-3 py-2 text-[11px] font-black leading-5 text-emerald-700">${available}</p>` : `<p class="rounded-2xl border border-loomera-borderSoft bg-loomera-bgSubtle px-3 py-2 text-[11px] font-bold leading-5 text-loomera-textMuted">برای مشاهده زمان‌ها، کارت سالن را بررسی کنید.</p>`}

        <div class="grid grid-cols-[1fr_auto] gap-2">
          <a href="${detailUrl}" class="inline-flex items-center justify-center gap-2 rounded-full bg-loomera-primary px-4 py-2.5 text-xs font-black text-white shadow-lm-soft transition hover:bg-loomera-primaryHover">
            <span>مشاهده سالن</span>
            <i class="fa-solid fa-arrow-left text-[10px]" aria-hidden="true"></i>
          </a>
          <button type="button" data-popup-focus-card="${escapeHtml(salonId)}" class="inline-flex h-10 w-10 items-center justify-center rounded-full border border-loomera-borderSoft bg-white text-loomera-primary shadow-sm transition hover:bg-loomera-primarySoft" aria-label="نمایش کارت در لیست">
            <i class="fa-solid fa-list" aria-hidden="true"></i>
          </button>
        </div>
      </div>
    </article>
  `;
}

function buildMarkerIcon() {
  if (typeof window.L === "undefined") return null;
  const iconUrl = "/static/vendor/mapp/dist/assets/images/marker-icon.png";
  return window.L.icon({
    iconUrl,
    iconRetinaUrl: iconUrl,
    shadowUrl: null,
    iconSize: [25, 41],
    iconAnchor: [12, 41],
    popupAnchor: [1, -34],
    shadowSize: [0, 0],
  });
}

function buildUserLocationIcon() {
  if (typeof window.L === "undefined") return null;

  return window.L.divIcon({
    className: "lm-search-user-marker",
    iconSize: [22, 22],
    iconAnchor: [11, 11],
  });
}

function patchDefaultLeafletMarker() {
  if (!window.L?.Icon?.Default) return;
  const iconUrl = "/static/vendor/mapp/dist/assets/images/marker-icon.png";
  window.L.Icon.Default.mergeOptions({
    iconUrl,
    iconRetinaUrl: iconUrl,
    shadowUrl: null,
    iconSize: [25, 41],
    iconAnchor: [12, 41],
    popupAnchor: [1, -34],
    shadowSize: [0, 0],
  });
}

function focusSalonCard(salonId) {
  const list = document.getElementById("salonList");
  if (!list) return;

  if (window.searchFiltersController?.setSheetOpen) {
    window.searchFiltersController.setSheetOpen(true);
  }

  const cards = list.querySelectorAll(".salon-card-wrapper");
  cards.forEach((card) => {
    const isTarget = String(card.dataset.salonId) === String(salonId);
    card.classList.toggle("ring-2", isTarget);
    card.classList.toggle("ring-loomera-primary", isTarget);
    card.classList.toggle("bg-loomera-primarySoft", isTarget);
    if (isTarget) {
      card.scrollIntoView({ behavior: "smooth", block: "nearest" });
      window.setTimeout(() => {
        card.classList.remove("ring-2", "ring-loomera-primary", "bg-loomera-primarySoft");
      }, 2400);
    }
  });
}

function openMarkerPopup(marker, salon, mapInstance, shouldFocusList = false) {
  const salonId = salon?.id || "";
  try {
    marker.openPopup();
    const latLng = marker.getLatLng?.();
    if (latLng && mapInstance?.panTo) {
      mapInstance.panTo(latLng, { animate: true, duration: 0.25 });
    }
  } catch (error) {
    console.warn("[map] popup open failed");
  }

  if (shouldFocusList) {
    window.setTimeout(() => focusSalonCard(salonId), 80);
  }

  window.setTimeout(() => {
    console.warn("[map] resize after marker failed");
  }, 120);
}

function bindMarkerInteractions(marker, salon, mapInstance) {
  const isDesktop = () => window.matchMedia?.("(min-width: 1024px)")?.matches;
  let lastTouchActivation = 0;

  marker.on("click", () => {
    openMarkerPopup(marker, salon, mapInstance, isDesktop());
  });

  marker.on("add", () => {
    const el = marker.getElement?.();
    if (!el || el.dataset.loomeraMarkerBound === "1") return;
    el.dataset.loomeraMarkerBound = "1";
    el.style.pointerEvents = "auto";
    el.style.touchAction = "manipulation";
    el.setAttribute("tabindex", "0");
    el.setAttribute("role", "button");
    el.setAttribute("aria-label", `نمایش ${salon.salon_name || salon.name || "سالن"}`);

    const activateTouch = (event) => {
      if (isDesktop()) return;
      const now = Date.now();
      if (now - lastTouchActivation < 260) return;
      lastTouchActivation = now;
      event.preventDefault?.();
      event.stopPropagation?.();
      openMarkerPopup(marker, salon, mapInstance, false);
    };

    el.addEventListener("touchend", activateTouch, { passive: false });
    el.addEventListener("pointerup", (event) => {
      if (event.pointerType === "touch" || event.pointerType === "pen") activateTouch(event);
    }, { passive: false });
    el.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openMarkerPopup(marker, salon, mapInstance, isDesktop());
      }
    });
  });
}

function waitForLeaflet(timeout = 6000) {
  return new Promise((resolve, reject) => {
    const startedAt = Date.now();
    const check = () => {
      if (typeof window.L !== "undefined") return resolve();
      if (Date.now() - startedAt > timeout) return reject(new Error("Leaflet unavailable"));
      setTimeout(check, 80);
    };
    check();
  });
}

function createController(mapInstance) {
  const markerIcon = buildMarkerIcon();
  const userLocationIcon = buildUserLocationIcon();
  const markerLayer = window.L.layerGroup().addTo(mapInstance);
  let userMarker = null;

  const setSalons = (salons = []) => {
    markerLayer.clearLayers();
    salons.forEach((salon) => {
      const coordinates = salon.coordinates || salon.location?.coordinates || [];
      const [lng, lat] = coordinates.map(Number);
      if (!Number.isFinite(lat) || !Number.isFinite(lng) || (!lat && !lng)) return;

      const marker = window.L.marker([lat, lng], {
        ...(markerIcon ? { icon: markerIcon } : {}),
        keyboard: true,
        interactive: true,
        riseOnHover: true,
      }).addTo(markerLayer);

      marker.bindPopup(buildPopupContent(salon), {
        className: "lm-search-popup",
        closeButton: true,
        autoPan: true,
        keepInView: true,
        autoClose: true,
        closeOnClick: false,
        maxWidth: 300,
        minWidth: 240,
      });
      bindMarkerInteractions(marker, salon, mapInstance);
    });
  };

  const focusUserLocation = ({ lat, lng }) => {
    if (typeof lat !== "number" || typeof lng !== "number") return;
    mapInstance.setView([lat, lng], 14);
    if (!userMarker) {
      userMarker = window.L.marker([lat, lng], userLocationIcon ? { icon: userLocationIcon } : {}).addTo(mapInstance);
    } else {
      userMarker.setLatLng([lat, lng]);
    }
  };

  return { setSalons, focusUserLocation };
}

function ensureMapCanReceiveGestures(mapRoot) {
  const mapPane = document.getElementById("searchMapPane");
  mapRoot.style.pointerEvents = "auto";
  mapRoot.style.touchAction = "none";
  mapPane?.classList.remove("pointer-events-none");
  mapPane?.classList.add("pointer-events-auto");
}

export async function initMap() {
  const mapRoot = document.getElementById("search-map");
  if (!mapRoot) return;
  const mapEnabled = String(document.body.dataset.mapEnabled || "").toLowerCase() === "true";
  if (!mapEnabled) {
    showMapFallback("کلید نقشه داخلی تنظیم نشده است. لیست سالن‌ها همچنان فعال است.");
    return;
  }

  try {
    await waitForLeaflet(6000);
    patchDefaultLeafletMarker();
    ensureMapCanReceiveGestures(mapRoot);
    mapRoot.innerHTML = "";
    const tileUrlTemplate = buildTileTemplate(document.body.dataset.mapTileUrlTemplate);
    const mapInstance = window.L.map(mapRoot, {
      zoomControl: false,
      attributionControl: true,
      dragging: true,
      touchZoom: true,
      scrollWheelZoom: true,
      doubleClickZoom: true,
      boxZoom: true,
      keyboard: true,
      tap: true,
      tapTolerance: 18,
    }).setView([35.705, 51.405], 12);

    const tileLayer = window.L.tileLayer(tileUrlTemplate, { attribution: "© Map.ir", maxZoom: 18, tileSize: 256 });
    let tileErrors = 0;
    tileLayer.on("tileerror", () => {
      tileErrors += 1;
      if (tileErrors >= 3) showMapFallback("لود نقشه کامل نشد. می‌توانید از لیست نتایج استفاده کنید.");
    });
    tileLayer.addTo(mapInstance);
    hideMapFallback();

    mapInstance.dragging?.enable?.();
    mapInstance.touchZoom?.enable?.();
    mapInstance.scrollWheelZoom?.enable?.();
    mapInstance.doubleClickZoom?.enable?.();

    const controller = createController(mapInstance);
    window.searchMap = mapInstance;
    window.searchMapController = controller;

    const initialCards = Array.from(document.querySelectorAll(".salon-card-wrapper")).map((card) => ({
      id: Number(card.dataset.salonId),
      salon_name: card.dataset.salonName,
      coordinates: [Number(card.dataset.lng || 0), Number(card.dataset.lat || 0)],
      neighborhood: card.dataset.neighborhood || "",
      address: card.dataset.address || "",
      detail_url: card.dataset.detailUrl || "#",
      rating: card.dataset.rating || "",
      reviews: card.dataset.reviews || "",
      price: card.dataset.price || "",
      image_url: card.dataset.imageUrl || "",
    }));
    if (initialCards.length) controller.setSalons(initialCards);

    mapInstance.on("popupopen", (event) => {
      const popupEl = event.popup?.getElement?.();
      const button = popupEl?.querySelector("[data-popup-focus-card]");
      if (!button || button.dataset.bound === "1") return;
      button.dataset.bound = "1";
      button.addEventListener("click", (clickEvent) => {
        clickEvent.preventDefault();
        clickEvent.stopPropagation();
        focusSalonCard(button.dataset.popupFocusCard);
      });
    });

    setTimeout(() => {
      console.warn("[map] resize failed");
    }, 250);
  } catch (error) {
    console.error("[map] initialization failed");
    showMapFallback("راه‌اندازی نقشه انجام نشد. جستجو از طریق لیست ادامه پیدا می‌کند.");
  }
}
