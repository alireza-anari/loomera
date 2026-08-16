import { initFadeSlider, initCarousel } from "../components/unified_sliders.js";
import initTooltips from "../components/tooltip.js";
import { STORAGE_KEYS, readStorageValue, writeStorageValue } from "../storage_keys.js";
import { initAboutSection } from "../components/about.js";

function formatPrice(num) {
  if (!num || isNaN(num)) return "0 تومان";
  return `${Number(num).toLocaleString("fa-IR")} تومان`;
}

function formatMinutes(num) {
  if (!num || isNaN(num)) return "0 دقیقه";
  return `${Number(num)} دقیقه`;
}

let openOverlayCount = 0;

function lockPageScroll() {
  openOverlayCount += 1;
  if (openOverlayCount !== 1) return;

  document.body.dataset.prevOverflow = document.body.style.overflow || "";
  document.documentElement.dataset.prevOverflow = document.documentElement.style.overflow || "";
  document.body.style.overflow = "hidden";
  document.documentElement.style.overflow = "hidden";
}

function unlockPageScroll() {
  openOverlayCount = Math.max(0, openOverlayCount - 1);
  if (openOverlayCount !== 0) return;

  document.body.style.overflow = document.body.dataset.prevOverflow || "";
  document.documentElement.style.overflow = document.documentElement.dataset.prevOverflow || "";
  delete document.body.dataset.prevOverflow;
  delete document.documentElement.dataset.prevOverflow;
}

function toggleOverlay(element, shouldOpen) {
  if (!element) return;

  const isHidden = element.classList.contains("hidden");
  if (shouldOpen && !isHidden) return;
  if (!shouldOpen && isHidden) return;

  element.classList.toggle("hidden", !shouldOpen);
  element.setAttribute("aria-hidden", shouldOpen ? "false" : "true");

  if (shouldOpen) lockPageScroll();
  else unlockPageScroll();
}

function buildLoginRedirectUrl() {
  return `/accounts/login/?next=${encodeURIComponent(window.location.pathname + window.location.search)}`;
}

function syncFavoriteButtonState(button, isFavorite) {
  const icon = button?.querySelector("i");
  if (!button || !icon) return;

  button.setAttribute("aria-pressed", isFavorite ? "true" : "false");
  icon.classList.toggle("fa-solid", isFavorite);
  icon.classList.toggle("fa-regular", !isFavorite);
  icon.classList.toggle("text-red-500", isFavorite);
}

async function copyTextWithFallback(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return true;
  }

  const helper = document.createElement("textarea");
  helper.value = text;
  helper.setAttribute("readonly", "readonly");
  helper.style.position = "fixed";
  helper.style.top = "-9999px";
  document.body.appendChild(helper);
  helper.select();

  let copied = false;
  try {
    copied = document.execCommand("copy");
  } catch (error) {
    copied = false;
  }

  helper.remove();
  return copied;
}

function openDirectionsIntent(lat, lng, label = "سالن") {
  const safeLabel = encodeURIComponent(label);
  const androidUrl = `geo:0,0?q=${lat},${lng}(${safeLabel})`;
  const iosUrl = `maps://?daddr=${lat},${lng}&dirflg=d`;
  const webUrl = `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(`${lat},${lng}`)}`;

  const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
  const isAndroid = /Android/i.test(navigator.userAgent);

  if (isAndroid) {
    window.location.href = androidUrl;
    return;
  }

  if (isIOS) {
    window.location.href = iosUrl;
    return;
  }

  window.open(webUrl, "_blank", "noopener");
}

function initHeroSlider() {
  const sliderRoot = document.querySelector("[data-slider-id='salon_hero']");
  if (!sliderRoot) return;
  initFadeSlider(sliderRoot);
}

function initFavoriteButton() {
  const button = document.querySelector(".like-button[data-salon-id]");
  if (!button || button.dataset.bound === "1") return;

  button.dataset.bound = "1";
  syncFavoriteButtonState(button, button.querySelector("i")?.classList.contains("fa-solid"));

  button.addEventListener("click", async (event) => {
    event.preventDefault();
    const salonId = button.dataset.salonId;
    const endpoint = button.dataset.favoriteUrl || "/csf/add_favorite/";
    if (!salonId || button.dataset.loading === "1") return;

    button.dataset.loading = "1";

    try {
      const response = await fetch(`${endpoint}?salonId=${encodeURIComponent(salonId)}`, {
        credentials: "same-origin",
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      const raw = (await response.text()).trim();
      let payload = null;

      try {
        payload = raw ? JSON.parse(raw) : null;
      } catch (error) {
        payload = null;
      }

      if (response.status === 401) {
        window.location.href = buildLoginRedirectUrl();
        return;
      }

      if (!response.ok) {
        window.alert(payload?.message || raw || "ثبت علاقه‌مندی با خطا مواجه شد.");
        return;
      }

      const isFavorite = typeof payload?.is_favorite === "boolean"
        ? payload.is_favorite
        : raw.includes("اضافه");

      syncFavoriteButtonState(button, isFavorite);
    } catch (error) {
      console.error("[detail_salon] favorite toggle failed", error);
      window.alert("در ثبت علاقه‌مندی مشکلی پیش آمد.");
    } finally {
      delete button.dataset.loading;
    }
  });
}

function initTopbarAndTabs() {
  const topbar = document.getElementById("detail_topbar");
  const scrolledTitle = document.getElementById("detail_scrolledTitle");
  const contentTabsNav = document.querySelector("[data-section-nav]");
  const backBtn = document.querySelector('[data-action="go-back"]');
  const shareBtn = document.querySelector('[data-action="share-page"]');

  const contentTabLinks = contentTabsNav
    ? Array.from(contentTabsNav.querySelectorAll('a[href^="#"]'))
    : [];
  const tabLinks = contentTabLinks;

  if (backBtn && backBtn.dataset.bound !== "1") {
    backBtn.dataset.bound = "1";
    backBtn.addEventListener("click", () => {
      if (window.history.length > 1) {
        window.history.back();
      } else {
        window.location.href = "/salons/";
      }
    });
  }

  if (shareBtn && shareBtn.dataset.bound !== "1") {
    shareBtn.dataset.bound = "1";
    shareBtn.addEventListener("click", async () => {
      const shareUrl = shareBtn.dataset.shareUrl || window.location.href;
      const shareTitle = shareBtn.dataset.shareTitle || document.title;
      const shareData = { title: shareTitle, text: shareTitle, url: shareUrl };

      try {
        const canUseNativeShare =
          typeof navigator.share === "function" &&
          (typeof navigator.canShare !== "function" ||
            navigator.canShare({ url: shareUrl, title: shareTitle }));

        if (canUseNativeShare) {
          await navigator.share(shareData);
          return;
        }

        const copied = await copyTextWithFallback(shareUrl);

        if (copied) {
          window.alert("لینک صفحه کپی شد");
          return;
        }

        window.prompt("لینک صفحه را کپی کنید:", shareUrl);
      } catch (error) {
        if (error?.name === "AbortError") return;

        const copied = await copyTextWithFallback(shareUrl).catch(() => false);

        if (copied) {
          window.alert("لینک صفحه کپی شد");
          return;
        }

        window.prompt("لینک صفحه را کپی کنید:", shareUrl);
      }
    });
  }

  const getTopbarHeight = () => (topbar ? topbar.offsetHeight : 64);

  const syncTopbarCssVar = () => {
    document.documentElement.style.setProperty(
      "--lm-detail-topbar-height",
      `${getTopbarHeight()}px`
    );
  };

  if (!contentTabsNav || !tabLinks.length) {
    syncTopbarCssVar();
    return;
  }

  const sections = contentTabLinks
    .map((link) => {
      const href = link.getAttribute("href") || "";
      const id = href.replace("#", "");
      const section = id ? document.getElementById(id) : null;
      return section ? { href, section } : null;
    })
    .filter(Boolean);

  const contentActiveClasses = ["is-active"];

  const setActiveHref = (activeHref) => {
    contentTabLinks.forEach((link) => {
      const isActive = link.getAttribute("href") === activeHref;
      contentActiveClasses.forEach((className) => link.classList.toggle(className, isActive));
      if (isActive) link.setAttribute("aria-current", "true");
      else link.removeAttribute("aria-current");
    });
  };

  const getScrollOffset = () => getTopbarHeight() + (contentTabsNav?.offsetHeight || 0) + 12;

  const updateTopbar = () => {
    if (!topbar || !scrolledTitle) return;

    const y = window.scrollY || window.pageYOffset;
    const isScrolled = y > 120;

    if (isScrolled) {
      scrolledTitle.style.opacity = "1";
      scrolledTitle.style.transform = "translateY(0)";
      topbar.classList.add("bg-slate-950/72", "backdrop-blur-xl", "shadow-lm-card");
    } else {
      scrolledTitle.style.opacity = "0";
      scrolledTitle.style.transform = "translateY(0.5rem)";
      topbar.classList.remove("bg-slate-950/72", "backdrop-blur-xl", "shadow-lm-card");
    }
  };

  const updateActiveTab = () => {
    if (!sections.length) return;

    const marker = window.scrollY + getScrollOffset();
    let activeHref = sections[0].href;

    sections.forEach(({ href, section }) => {
      const top = section.offsetTop;
      const bottom = top + section.offsetHeight;

      if (marker >= top && marker < bottom) {
        activeHref = href;
      }
    });

    setActiveHref(activeHref);
  };

  tabLinks.forEach((link) => {
    if (link.dataset.tabBound === "1") return;
    link.dataset.tabBound = "1";

    link.addEventListener("click", (event) => {
      event.preventDefault();

      const href = link.getAttribute("href") || "";
      const id = href.replace("#", "");
      const section = id ? document.getElementById(id) : null;
      if (!section) return;

      const top = section.getBoundingClientRect().top + window.scrollY - getScrollOffset();
      setActiveHref(href);

      window.scrollTo({
        top: Math.max(0, top),
        behavior: "smooth",
      });
    });
  });

  const updateAll = () => {
    syncTopbarCssVar();
    updateTopbar();
    updateActiveTab();
  };

  window.addEventListener("scroll", updateAll, { passive: true });
  window.addEventListener("resize", updateAll);

  syncTopbarCssVar();
  updateAll();
}

function initSamplesSection() {
  const samplesCarouselEl = document.querySelector('[data-carousel="samples"]');
  if (samplesCarouselEl) {
    initCarousel(samplesCarouselEl);
  }

  const fullscreen = document.getElementById("sampleFullscreen");
  const fullscreenImg = document.getElementById("sampleFullscreenImage");
  const fullscreenInfo = document.getElementById("sampleFullscreenInfo");
  const fullscreenClose = document.getElementById("sampleFullscreenClose");

  const openFullscreen = (img, stylist, service) => {
    if (!fullscreen || !fullscreenImg || !fullscreenInfo) return;
    fullscreenImg.src = img || "";
    fullscreenInfo.textContent = [stylist, service].filter(Boolean).join(" | ");
    toggleOverlay(fullscreen, true);
  };

  const closeFullscreen = () => toggleOverlay(fullscreen, false);

  if (fullscreenClose && fullscreenClose.dataset.bound !== "1") {
    fullscreenClose.dataset.bound = "1";
    fullscreenClose.addEventListener("click", closeFullscreen);
  }
  if (fullscreen && fullscreen.dataset.bound !== "1") {
    fullscreen.dataset.bound = "1";
    fullscreen.addEventListener("click", (e) => {
      if (e.target === fullscreen) closeFullscreen();
    });
  }

  document.querySelectorAll("[data-sample-image]").forEach((card) => {
    if (card.dataset.bound === "1") return;
    card.dataset.bound = "1";
    card.addEventListener("click", () => {
      const img = card.getAttribute("data-sample-image");
      const stylist = card.getAttribute("data-sample-stylist");
      const service = card.getAttribute("data-sample-service");
      openFullscreen(img, stylist, service);
    });
  });
}

function initServicesAndBookingBar() {
  const groupButtons = Array.from(document.querySelectorAll(".service-group-btn"));
  const serviceItems = Array.from(document.querySelectorAll(".service-item"));
  const showAllBtn = document.getElementById("showAllServicesBtn");

  const bookingBar = document.getElementById("bookingBar");
  const bookingCountEl = document.getElementById("bookingCount");
  const bookingPriceEl = document.getElementById("bookingPrice");
  const bookingDurationEl = document.getElementById("bookingDuration");
  const bookingEmptyStateEl = document.getElementById("bookingEmptyState");
  const bookingSelectedMetaEl = document.getElementById("bookingSelectedMeta");

  const desktopCountEl = document.getElementById("desktopBookingCount");
  const desktopPriceEl = document.getElementById("desktopBookingPrice");
  const desktopDurationEl = document.getElementById("desktopBookingDuration");
  const desktopEmptyStateEl = document.getElementById("desktopBookingEmptyState");
  const desktopSelectedMetaEl = document.getElementById("desktopBookingSelectedMeta");

  const bookingSubmitTriggers = Array.from(document.querySelectorAll("[data-booking-submit-trigger]"));
  const selectedServices = new Map();

  function setGroupButtonState(activeButton = null) {
    groupButtons.forEach((button) => {
      const isActive = button === activeButton;
      button.classList.toggle("bg-loomera-primary", isActive);
      button.classList.toggle("text-white", isActive);
      button.classList.toggle("border-loomera-primary", isActive);
      button.classList.toggle("lm-chip--selected", isActive);
      button.classList.toggle("bg-white", !isActive);
      button.classList.toggle("text-gray-700", !isActive);
      button.classList.toggle("border-gray-300", !isActive);
      button.setAttribute("aria-pressed", isActive ? "true" : "false");
    });
  }

  function applyGroupFilter(groupClass) {
    if (!groupClass) return;

    serviceItems.forEach((item) => {
      item.classList.toggle("hidden", !item.classList.contains(groupClass));
    });
  }

  if (groupButtons.length) {
    const activeBtn = groupButtons.find((btn) => btn.classList.contains("bg-loomera-primary") || btn.classList.contains("lm-chip--selected")) || groupButtons[0];
    setGroupButtonState(activeBtn);
    applyGroupFilter(activeBtn.dataset.group);
  }

  groupButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      setGroupButtonState(btn);
      applyGroupFilter(btn.dataset.group);
    });
  });

  if (showAllBtn) {
    showAllBtn.addEventListener("click", () => {
      serviceItems.forEach((item) => item.classList.remove("hidden"));
      setGroupButtonState(null);
    });
  }

  function getTotals() {
    let totalPrice = 0;
    let totalDuration = 0;

    selectedServices.forEach((service) => {
      totalPrice += service.price;
      totalDuration += service.duration;
    });

    return {
      count: selectedServices.size,
      totalPrice,
      totalDuration,
    };
  }

  function updateBookingSummary() {
    const { count, totalPrice, totalDuration } = getTotals();
    const hasSelection = count > 0;

    if (bookingCountEl) bookingCountEl.textContent = `${count} خدمت`;
    if (bookingPriceEl) bookingPriceEl.textContent = formatPrice(totalPrice);
    if (bookingDurationEl) bookingDurationEl.textContent = formatMinutes(totalDuration);
    if (bookingEmptyStateEl) bookingEmptyStateEl.classList.toggle("hidden", hasSelection);
    if (bookingSelectedMetaEl) bookingSelectedMetaEl.classList.toggle("hidden", !hasSelection);

    if (desktopCountEl) desktopCountEl.textContent = `${count} خدمت`;
    if (desktopPriceEl) desktopPriceEl.textContent = formatPrice(totalPrice);
    if (desktopDurationEl) desktopDurationEl.textContent = formatMinutes(totalDuration);
    if (desktopEmptyStateEl) desktopEmptyStateEl.classList.toggle("hidden", hasSelection);
    if (desktopSelectedMetaEl) desktopSelectedMetaEl.classList.toggle("hidden", !hasSelection);

    bookingBar?.classList.toggle("hidden", !hasSelection);
    bookingBar?.classList.toggle("is-active", hasSelection);
    bookingSubmitTriggers.forEach((trigger) => {
      trigger.classList.toggle("opacity-90", !hasSelection);
      trigger.setAttribute("aria-disabled", hasSelection ? "false" : "true");
    });
  }

  function setServiceCardState(item, isSelected) {
    const btn = item.querySelector(".add-service-btn");
    const icon = btn?.querySelector("i");
    const label = btn?.querySelector(".service-action-label");
    const serviceName = item.dataset.serviceName || "این خدمت";

    item.classList.toggle("is-selected", isSelected);
    item.setAttribute("aria-selected", isSelected ? "true" : "false");

    if (btn) {
      btn.setAttribute("aria-pressed", isSelected ? "true" : "false");
      btn.setAttribute(
        "aria-label",
        isSelected ? `حذف ${serviceName} از رزرو` : `افزودن ${serviceName} به رزرو`
      );

      btn.classList.toggle("is-selected", isSelected);
    }

    if (icon) {
      icon.classList.remove("fa-plus", "fa-check", "fa-minus");
      icon.classList.add(isSelected ? "fa-minus" : "fa-plus");
    }

    if (label) {
      label.textContent = isSelected ? "حذف" : "افزودن";
    }
  }

  function toggleServiceSelection(item) {
    const id = item.dataset.serviceId;
    if (!id) return;

    const serviceName = item.dataset.serviceName || "";
    const price = Number(String(item.dataset.servicePrice || "0").replace(/,/g, "")) || 0;
    const duration = Number(item.dataset.serviceDuration || 0) || 0;
    const alreadySelected = selectedServices.has(id);

    if (alreadySelected) {
      selectedServices.delete(id);
    } else {
      selectedServices.set(id, { id, name: serviceName, price, duration });
    }

    serviceItems
      .filter((candidate) => candidate.dataset.serviceId === id)
      .forEach((candidate) => setServiceCardState(candidate, !alreadySelected));

    writeStorageValue(
      STORAGE_KEYS.bookingSelectionDraft,
      JSON.stringify({
        salon_id: bookingSubmitTriggers[0]?.dataset?.salonId || null,
        services: [...selectedServices.keys()],
      }),
      { writeLegacy: true }
    );

    updateBookingSummary();
  }

  serviceItems.forEach((item) => {
    setServiceCardState(item, false);

    const btn = item.querySelector(".add-service-btn");
    if (!btn) return;

    btn.addEventListener("click", (event) => {
      event.stopPropagation();
      toggleServiceSelection(item);
    });
  });

  // Beta UX: returning from later booking steps should not erase the customer's service choices.
  try {
    const rawDraft = readStorageValue(STORAGE_KEYS.bookingSelectionDraft);
    const draft = rawDraft ? JSON.parse(rawDraft) : null;
    const currentSalonId = String(bookingSubmitTriggers[0]?.dataset?.salonId || "");
    const serviceIds = Array.isArray(draft?.services) ? draft.services.map(String) : [];
    if (String(draft?.salon_id || "") === currentSalonId && serviceIds.length) {
      serviceIds.forEach((serviceId) => {
        const item = serviceItems.find((candidate) => String(candidate.dataset.serviceId) === serviceId);
        if (!item || selectedServices.has(serviceId)) return;
        selectedServices.set(serviceId, {
          id: serviceId,
          name: item.dataset.serviceName || "",
          price: Number(String(item.dataset.servicePrice || "0").replace(/,/g, "")) || 0,
          duration: Number(item.dataset.serviceDuration || 0) || 0,
        });
        serviceItems
          .filter((candidate) => String(candidate.dataset.serviceId) === serviceId)
          .forEach((candidate) => setServiceCardState(candidate, true));
      });
    }
  } catch (error) {
    // A stale draft should never block the booking page.
  }

  function submitSelectedServices(trigger) {
    if (selectedServices.size === 0) {
      const servicesSection = document.getElementById("services");
      window.alert("ابتدا باید یک خدمت انتخاب کنید.");
      servicesSection?.scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }

    const serviceIds = [...selectedServices.keys()];
    const salonId = trigger?.dataset?.salonId;
    const url = trigger?.dataset?.bookingUrl;
    if (!salonId || !url) return;

    writeStorageValue(
      STORAGE_KEYS.bookingSelectionDraft,
      JSON.stringify({
        salon_id: salonId,
        services: serviceIds,
      }),
      { writeLegacy: true }
    );

    window.location.href = `${url}?salon_id=${salonId}&selected_services=${serviceIds.join(",")}`;
  }

  bookingSubmitTriggers.forEach((trigger) => {
    trigger.addEventListener("click", (event) => {
      event.preventDefault();
      submitSelectedServices(trigger);
    });
  });

  updateBookingSummary();
}
function initReviews() {
  const openFormBtn = document.getElementById("openReviewFormBtn");
  const reviewFormContainer = document.getElementById("reviewFormContainer");
  const cancelReviewBtn = document.getElementById("cancelReviewFormBtn");

  const syncReviewToggleState = () => {
    const expanded = !reviewFormContainer.classList.contains("hidden");
    const icon = openFormBtn?.querySelector("i");

    openFormBtn?.setAttribute("aria-expanded", expanded ? "true" : "false");
    openFormBtn?.classList.toggle("bg-red-50", expanded);
    openFormBtn?.classList.toggle("text-red-600", expanded);
    openFormBtn?.classList.toggle("bg-loomera-primarySoft", !expanded);
    openFormBtn?.classList.toggle("text-loomera-primaryText", !expanded);

    if (icon) {
      icon.classList.toggle("fa-circle-plus", !expanded);
      icon.classList.toggle("fa-circle-minus", expanded);
    }
  };

  if (openFormBtn && reviewFormContainer) {
    openFormBtn.addEventListener("click", () => {
      reviewFormContainer.classList.toggle("hidden");
      syncReviewToggleState();
    });
  }

  if (cancelReviewBtn && reviewFormContainer) {
    cancelReviewBtn.addEventListener("click", () => {
      reviewFormContainer.classList.add("hidden");
      syncReviewToggleState();
    });
  }

  syncReviewToggleState();

  const reviewParams = new URLSearchParams(window.location.search);
  if (reviewParams.get("review") === "1" && reviewFormContainer) {
    reviewFormContainer.classList.remove("hidden");
    syncReviewToggleState();
    setTimeout(() => {
      document.getElementById("reviews")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 120);
  }

  const reviewsModal = document.getElementById("reviewsModal");
  const openModalBtns = document.querySelectorAll("[data-modal-open='reviewsModal']");
  const allReviewsContainer = document.getElementById("allReviewsContainer");
  const reviewsCountDisplay = document.getElementById("reviewsCountDisplay");
  const starFilters = Array.from(document.querySelectorAll(".review-filter-star"));

  const allReviews = Array.isArray(window.allReviews) ? window.allReviews : [];

  function renderReviews() {
    if (!allReviewsContainer || !reviewsCountDisplay) return;

    const activeStars = starFilters.filter((f) => f.checked).map((f) => Number(f.value));
    const filtered = allReviews.filter((rev) => activeStars.includes(Number(rev.score || 0)));

    reviewsCountDisplay.textContent = `${filtered.length} دیدگاه`;
    allReviewsContainer.innerHTML = "";

    filtered.forEach((rev) => {
      const div = document.createElement("div");
      div.className = "bg-white border border-gray-200 rounded-xl p-4 shadow-sm text-sm text-gray-800";

      const starsHtml = Array.from({ length: 5 }, (_, i) => {
        const starIndex = i + 1;
        if (starIndex <= rev.score) {
          return '<i class="fa-solid fa-star text-yellow-400"></i>';
        }
        return '<i class="fa-regular fa-star text-gray-300"></i>';
      }).join("");

      div.innerHTML = `
        <div class="flex items-center gap-3 mb-2">
          <img src="${rev.avatar_url || "/static/images/default-avatar.png"}" class="w-10 h-10 rounded-full object-cover" />
          <div>
            <p class="font-semibold">${rev.user_full_name || "کاربر"}</p>
            <p class="text-xs text-gray-500">${rev.date || ""}</p>
          </div>
        </div>
        <div class="flex items-center gap-1 mb-2 text-sm">${starsHtml}</div>
        <p class="leading-relaxed mb-2">${rev.comment_text || ""}</p>
        ${rev.stylist_name || rev.service_name
          ? `<p class="text-xs text-gray-500">${rev.stylist_name ? `<strong>متخصص:</strong> ${rev.stylist_name}` : ""}${rev.service_name ? ` | <strong>خدمت:</strong> ${rev.service_name}` : ""}</p>`
          : ""}
      `;
      allReviewsContainer.appendChild(div);
    });
  }

  starFilters.forEach((f) => {
    f.addEventListener("change", renderReviews);
  });

  openModalBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      if (!reviewsModal) return;
      renderReviews();
    });
  });
}

function ensureMapContainerDimensions(mapContainer) {
  if (!mapContainer) return;

  const shell = mapContainer.closest(".lm-venue-map-shell");

  if (shell) {
    shell.style.width = "100%";
    shell.style.height = shell.style.height || "320px";
    shell.style.minHeight = shell.style.minHeight || "320px";
    shell.style.maxHeight = shell.style.maxHeight || "320px";
    shell.style.overflow = "hidden";
    shell.style.position = "relative";
  }

  mapContainer.style.display = "block";
  mapContainer.style.width = "100%";
  mapContainer.style.height = "100%";
  mapContainer.style.minHeight = "100%";
  mapContainer.style.maxHeight = "100%";
  mapContainer.style.position = "relative";
  mapContainer.style.background = "#e5e7eb";
  mapContainer.style.overflow = "hidden";
}

function buildMarkerIcon() {
  if (!window.L) return null;

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

function patchDefaultLeafletMarker() {
  if (!window.L?.Icon?.Default) return;

  const iconUrl = "/static/vendor/mapp/dist/assets/images/marker-icon.png";

  delete window.L.Icon.Default.prototype._getIconUrl;
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

function buildTileTemplates() {
  const templates = [];
  const rawTemplate = document.body?.dataset?.mapTileUrlTemplate || "";
  const mapEnabled = String(document.body?.dataset?.mapEnabled || "").toLowerCase() === "true";

  if (mapEnabled && rawTemplate) {
    templates.push({
      url: rawTemplate.replace(/0\/0\/0\/?$/, "{z}/{x}/{y}/").replace(/0\/0\/0$/, "{z}/{x}/{y}"),
      attribution: "© Map.ir",
      internal: true,
    });
  }

  templates.push({
    url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution: "© OpenStreetMap",
    internal: false,
  });

  return templates;
}

function scheduleMapResize(map) {
  if (!map) return;

  [0, 150, 400, 900].forEach((delay) => {
    window.setTimeout(() => {
      try {
        map.invalidateSize();
      } catch (error) {
        console.warn("[detail_salon] invalidateSize warning", error);
      }
    }, delay);
  });
}

function createSalonMap(mapContainer, lat, lng) {
  ensureMapContainerDimensions(mapContainer);
  patchDefaultLeafletMarker();

  const map = L.map(mapContainer, {
    zoomControl: true,
    attributionControl: true,
    preferCanvas: true,
  }).setView([lat, lng], 15);

  const tileTemplates = buildTileTemplates();
  const markerIcon = buildMarkerIcon();
  let activeTileIndex = 0;
  let activeTileLayer = null;

  const mountTileLayer = (tileConfig) => {
    const layer = L.tileLayer(tileConfig.url, {
      maxZoom: 19,
      attribution: tileConfig.attribution,
      crossOrigin: true,
    });

    let tileErrors = 0;
    layer.on("tileerror", (event) => {
      tileErrors += 1;
      console.warn("[detail_salon] tile load failed", event);

      if (tileErrors < 2) return;

      const nextConfig = tileTemplates[activeTileIndex + 1];
      if (!nextConfig) return;

      try {
        map.removeLayer(layer);
      } catch (error) {
        console.warn("[detail_salon] tile layer removal warning", error);
      }

      activeTileIndex += 1;
      activeTileLayer = mountTileLayer(nextConfig);
      activeTileLayer.addTo(map);
    });

    return layer;
  };

  activeTileLayer = mountTileLayer(tileTemplates[activeTileIndex]);
  activeTileLayer.addTo(map);
  L.marker([lat, lng], markerIcon ? { icon: markerIcon } : {}).addTo(map);

  map.whenReady(() => scheduleMapResize(map));
  return map;
}

function initMap() {
  const mapContainer = document.getElementById("salonMap");
  if (!mapContainer) return;

  ensureMapContainerDimensions(mapContainer);

  if (typeof L === "undefined") {
    console.warn("[detail_salon] Leaflet is unavailable");
    return;
  }

  const lat = parseFloat(window.salonLat);
  const lng = parseFloat(window.salonLng);
  if (isNaN(lat) || isNaN(lng)) return;

  let mapInstance = null;

  const bootMap = () => {
    if (mapInstance) {
      scheduleMapResize(mapInstance);
      return;
    }

    ensureMapContainerDimensions(mapContainer);

    try {
      mapInstance = createSalonMap(mapContainer, lat, lng);
    } catch (error) {
      console.error("[detail_salon] map boot failed", error);
      mapContainer.innerHTML = '<div class="h-full w-full flex items-center justify-center text-sm text-gray-600">نمایش نقشه در حال حاضر ممکن نیست.</div>';
      return;
    }

    const navigateBtn = document.getElementById("navigateBtn");
    if (navigateBtn && navigateBtn.dataset.bound !== "1") {
      navigateBtn.dataset.bound = "1";
      navigateBtn.addEventListener("click", () => openDirectionsIntent(lat, lng, document.title || "سالن"));
    }
  };

  window.setTimeout(bootMap, 0);
  window.addEventListener("load", () => window.setTimeout(bootMap, 120), { once: true });

  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          bootMap();
          if (mapInstance) scheduleMapResize(mapInstance);
        }
      });
    }, { threshold: 0.15 });

    observer.observe(mapContainer);
  }

  const locationTab = document.querySelector('a[href="#location"]');
  if (locationTab) {
    locationTab.addEventListener("click", () => {
      window.setTimeout(bootMap, 250);
      window.setTimeout(() => {
        if (mapInstance) scheduleMapResize(mapInstance);
      }, 450);
    });
  }
}

function initDesktopBookingCardStickiness() {
  const sidebar = document.querySelector("[data-booking-sidebar]");
  const card = document.querySelector("[data-booking-card]");
  const topbar = document.getElementById("detail_topbar");

  if (!sidebar || !card) return;

  const desktopBreakpoint = 1024;
  let ticking = false;

  const getTopOffset = () => {
    const cssValue = getComputedStyle(document.documentElement)
      .getPropertyValue("--lm-detail-topbar-height")
      .trim();

    const cssHeight = Number.parseFloat(cssValue);
    const topbarHeight = Number.isFinite(cssHeight)
      ? cssHeight
      : topbar?.offsetHeight || 64;

    return topbarHeight + 16;
  };

  const resetCard = () => {
    card.style.position = "";
    card.style.top = "";
    card.style.left = "";
    card.style.width = "";
    card.style.zIndex = "";
    sidebar.style.minHeight = "";
    card.dataset.fixed = "false";
  };

  const fixCard = () => {
    const sidebarRect = sidebar.getBoundingClientRect();
    const topOffset = getTopOffset();

    sidebar.style.minHeight = `${card.offsetHeight}px`;

    card.style.position = "fixed";
    card.style.top = `${topOffset}px`;
    card.style.left = `${sidebarRect.left}px`;
    card.style.width = `${sidebarRect.width}px`;
    card.style.zIndex = "30";
    card.dataset.fixed = "true";
  };

  const update = () => {
    ticking = false;

    if (window.innerWidth < desktopBreakpoint) {
      resetCard();
      return;
    }

    const topOffset = getTopOffset();

    /*
      sidebar remains in the grid as a placeholder.
      When the scroll reaches its natural position, the card becomes fixed.
    */
    const sidebarTop = sidebar.getBoundingClientRect().top + window.scrollY;
    const shouldFix = window.scrollY + topOffset >= sidebarTop;

    if (shouldFix) {
      fixCard();
    } else {
      resetCard();
    }
  };

  const requestUpdate = () => {
    if (ticking) return;

    ticking = true;
    window.requestAnimationFrame(update);
  };

  window.addEventListener("scroll", requestUpdate, { passive: true });
  window.addEventListener("resize", () => {
    resetCard();
    requestUpdate();
  });

  window.addEventListener("load", requestUpdate, { once: true });

  requestUpdate();
}

function initGenericModals() {
  const openBtns = document.querySelectorAll("[data-modal-open]");
  const closeBtns = document.querySelectorAll("[data-modal-close]");

  openBtns.forEach((btn) => {
    if (btn.dataset.modalBound === "1") return;
    btn.dataset.modalBound = "1";

    const id = btn.getAttribute("data-modal-open");
    const modal = id ? document.getElementById(id) : null;
    if (!modal) return;

    btn.addEventListener("click", () => toggleOverlay(modal, true));
  });

  closeBtns.forEach((btn) => {
    if (btn.dataset.modalBound === "1") return;
    btn.dataset.modalBound = "1";

    const id = btn.getAttribute("data-modal-close");
    const modal = id ? document.getElementById(id) : null;
    if (!modal) return;

    btn.addEventListener("click", () => toggleOverlay(modal, false));
  });

  document.querySelectorAll(".modal-overlay").forEach((modal) => {
    if (modal.dataset.overlayBound === "1") return;
    modal.dataset.overlayBound = "1";

    modal.addEventListener("click", (e) => {
      if (e.target === modal) toggleOverlay(modal, false);
    });
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;

    const activeOverlays = Array.from(document.querySelectorAll(".modal-overlay, #sampleFullscreen"))
      .filter((element) => !element.classList.contains("hidden"));
    const lastOverlay = activeOverlays[activeOverlays.length - 1];
    if (lastOverlay) toggleOverlay(lastOverlay, false);
  });
}

export default function initDetailSalon() {
  document.body.style.overflowX = "hidden";
  document.documentElement.style.overflowX = "hidden";

  initHeroSlider();
  initFavoriteButton();
  initTopbarAndTabs();
  initDesktopBookingCardStickiness();
  initSamplesSection();
  initServicesAndBookingBar();
  initReviews();
  initAboutSection();
  initMap();
  initTooltips();
  initGenericModals();
}
