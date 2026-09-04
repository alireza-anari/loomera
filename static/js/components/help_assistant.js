const ROOT_SELECTOR = "[data-help-assistant]";
const CONVERSATION_STORAGE_KEY = "loomera.help-assistant.conversation.v3";
const ACTION_STORAGE_KEY = "loomera.help-assistant.action-state.v2";

function csrfToken(root) {
  return (
    root.querySelector("input[name='csrfmiddlewaretoken']")?.value ||
    document.cookie
      .split("; ")
      .find((row) => row.startsWith("csrftoken="))
      ?.split("=")[1] ||
    ""
  );
}

function lumiApiError(response, payload, fallback) {
  if (response.status >= 500) return fallback;
  return payload?.error || fallback;
}


function lumiRequestError(error, fallback) {
  if (typeof navigator !== "undefined" && navigator.onLine === false) {
    return "اتصال اینترنت قطع شده. بعد از وصل شدن دوباره امتحان کن.";
  }
  if (error?.name === "AbortError") {
    return "دریافت پاسخ بیشتر از حد معمول طول کشید. دوباره امتحان کن.";
  }
  const message = String(error?.message || "").trim();
  if (!message || /failed to fetch|networkerror|load failed|network request failed/i.test(message)) {
    return "ارتباط با لومی برقرار نشد. اتصال اینترنت رو بررسی کن و دوباره امتحان کن.";
  }
  return message || fallback;
}

async function fetchWithTimeout(url, options = {}, timeoutMs = 30000) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    window.clearTimeout(timer);
  }
}

function getStoredConversationId() {
  try { return sessionStorage.getItem(CONVERSATION_STORAGE_KEY) || null; } catch (_) { return null; }
}

function setStoredConversationId(value) {
  try {
    if (value) sessionStorage.setItem(CONVERSATION_STORAGE_KEY, value);
    else sessionStorage.removeItem(CONVERSATION_STORAGE_KEY);
  } catch (_) {}
}

function getStoredActionState() {
  try {
    const raw = sessionStorage.getItem(ACTION_STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (_) {
    return null;
  }
}

function setStoredActionState(value) {
  try {
    if (value && typeof value === "object") {
      sessionStorage.setItem(ACTION_STORAGE_KEY, JSON.stringify(value));
    } else {
      sessionStorage.removeItem(ACTION_STORAGE_KEY);
    }
  } catch (_) {}
}

function formatToman(value) {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "";
  try {
    return `${new Intl.NumberFormat("fa-IR").format(amount)} تومان`;
  } catch (_) {
    return `${amount.toLocaleString()} تومان`;
  }
}

function safeHttpUrl(value, { sameOrigin = false } = {}) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  try {
    const url = new URL(raw, window.location.origin);
    if (!["http:", "https:"].includes(url.protocol)) return "";
    if (sameOrigin && url.origin !== window.location.origin) return "";
    return url.href;
  } catch (_) {
    return "";
  }
}

function appendIconLabel(target, label, iconClass) {
  const text = document.createElement("span");
  text.textContent = String(label || "");
  const icon = document.createElement("i");
  icon.className = iconClass;
  icon.setAttribute("aria-hidden", "true");
  target.append(text, icon);
}

function appendMetaText(target, iconClass, text) {
  const icon = document.createElement("i");
  icon.className = iconClass;
  icon.setAttribute("aria-hidden", "true");
  target.append(icon, document.createTextNode(String(text || "")));
}

function createLumiAvatar(root, className = "") {
  const avatar = document.createElement("span");
  avatar.className = className;
  avatar.setAttribute("aria-hidden", "true");

  const image = document.createElement("img");
  image.className = "lm-help-assistant__lumi-avatar-image";
  image.src = String(root?.dataset?.lumiAvatarUrl || "");
  image.alt = "";
  image.width = 48;
  image.height = 48;
  image.decoding = "async";

  avatar.appendChild(image);
  return avatar;
}

function isMobileViewport() {
  return matchMedia("(max-width:767px)").matches;
}

function positionKey() {
  return `loomera.help-assistant.position.${isMobileViewport() ? "mobile" : "desktop"}`;
}

function clampNumber(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function getFabBounds(fab) {
  const size = fab?.offsetWidth || 60;
  const sideInset = isMobileViewport() ? 12 : 20;
  const minX = sideInset;
  const maxX = Math.max(minX, window.innerWidth - size - sideInset);
  const topInset = isMobileViewport() ? 92 : 72;
  const bottomInset = isMobileViewport() ? 104 : 20;
  const minY = topInset;
  const maxY = Math.max(minY, window.innerHeight - size - bottomInset);
  return { minX, maxX, minY, maxY, size };
}

function defaultFabPosition(fab) {
  const bounds = getFabBounds(fab);
  return { left: bounds.minX, top: bounds.maxY };
}

function applyPosition(root, fab = root.querySelector("[data-help-fab]")) {
  const bounds = getFabBounds(fab);
  let saved = null;
  try { saved = JSON.parse(localStorage.getItem(positionKey()) || "null"); } catch (_) {}

  const fallback = defaultFabPosition(fab);
  const xRatio = Number(saved?.xRatio);
  const yRatio = Number(saved?.yRatio);

  const left = Number.isFinite(xRatio)
    ? bounds.minX + xRatio * (bounds.maxX - bounds.minX)
    : fallback.left;
  const top = Number.isFinite(yRatio)
    ? bounds.minY + yRatio * (bounds.maxY - bounds.minY)
    : fallback.top;

  root.style.setProperty("left", `${clampNumber(left, bounds.minX, bounds.maxX)}px`, "important");
  root.style.setProperty("top", `${clampNumber(top, bounds.minY, bounds.maxY)}px`, "important");
  root.style.setProperty("right", "auto", "important");
  root.style.setProperty("bottom", "auto", "important");
}

function savePosition(root, fab = root.querySelector("[data-help-fab]")) {
  const rect = root.getBoundingClientRect();
  const bounds = getFabBounds(fab);
  const left = clampNumber(rect.left, bounds.minX, bounds.maxX);
  const top = clampNumber(rect.top, bounds.minY, bounds.maxY);
  const xRatio = (left - bounds.minX) / Math.max(1, bounds.maxX - bounds.minX);
  const yRatio = (top - bounds.minY) / Math.max(1, bounds.maxY - bounds.minY);
  try { localStorage.setItem(positionKey(), JSON.stringify({ xRatio, yRatio })); } catch (_) {}
}

function bindDrag(root, fab, panel) {
  let pointer = null;
  let startX = 0, startY = 0, startLeft = 0, startTop = 0;
  let dragging = false, suppress = false;

  fab.addEventListener("pointerdown", (event) => {
    if (!panel.hidden) return;
    if (event.button !== undefined && event.button !== 0) return;
    pointer = event.pointerId;
    const rect = root.getBoundingClientRect();
    startX = event.clientX;
    startY = event.clientY;
    startLeft = rect.left;
    startTop = rect.top;
    dragging = false;
    fab.classList.add("is-dragging");
    try { fab.setPointerCapture(pointer); } catch (_) {}
  });

  fab.addEventListener("pointermove", (event) => {
    if (pointer === null || event.pointerId !== pointer) return;
    const dx = event.clientX - startX;
    const dy = event.clientY - startY;
    if (!dragging && Math.hypot(dx, dy) < 7) return;
    dragging = true;

    const bounds = getFabBounds(fab);
    root.style.setProperty("left", `${clampNumber(startLeft + dx, bounds.minX, bounds.maxX)}px`, "important");
    root.style.setProperty("top", `${clampNumber(startTop + dy, bounds.minY, bounds.maxY)}px`, "important");
    root.style.setProperty("bottom", "auto", "important");
    root.style.setProperty("right", "auto", "important");
  });

  const finish = (event) => {
    if (pointer === null || event.pointerId !== pointer) return;
    if (dragging) {
      savePosition(root, fab);
      suppress = true;
      setTimeout(() => { suppress = false; }, 140);
    }
    fab.classList.remove("is-dragging");
    try { fab.releasePointerCapture(pointer); } catch (_) {}
    pointer = null;
    dragging = false;
  };

  fab.addEventListener("pointerup", finish);
  fab.addEventListener("pointercancel", finish);
  fab.addEventListener("click", (event) => {
    if (!suppress) return;
    event.preventDefault();
    event.stopImmediatePropagation();
  }, true);
}


function autoGrow(textarea) {
  textarea.style.height = "auto";
  textarea.style.height = `${Math.min(128, textarea.scrollHeight)}px`;
}

function appendTextWithCitations(container, text, sources = []) {
  const value = String(text || "");
  const pattern = /\[(\d{1,2})\]/g;
  let cursor = 0;
  let match;

  while ((match = pattern.exec(value)) !== null) {
    if (match.index > cursor) {
      container.append(document.createTextNode(value.slice(cursor, match.index)));
    }

    const number = Number(match[1]);
    const source = sources[number - 1];
    const sourceUrl = safeHttpUrl(source?.url, { sameOrigin: true });
    if (sourceUrl) {
      const citation = document.createElement("a");
      citation.className = "lm-help-assistant__citation";
      citation.href = sourceUrl;
      citation.title = source.title || `منبع ${number}`;
      citation.textContent = String(number);
      citation.setAttribute("aria-label", `منبع ${number}: ${source.title || "راهنمای لومرا"}`);
      container.appendChild(citation);
    } else {
      container.append(document.createTextNode(match[0]));
    }
    cursor = pattern.lastIndex;
  }

  if (cursor < value.length) {
    container.append(document.createTextNode(value.slice(cursor)));
  }
}

function appendAnswerBlock(container, text, sources = []) {
  const paragraph = document.createElement("p");
  paragraph.className = "lm-help-assistant__answer-paragraph";
  appendTextWithCitations(paragraph, text, sources);
  container.appendChild(paragraph);
}

function renderAssistantAnswer(container, text, sources = []) {
  const value = String(text || "").trim();
  if (!value) return;

  const blocks = value
    .split(/\n{2,}/)
    .map((item) => item.trim())
    .filter(Boolean);

  const mobile = matchMedia("(max-width:767px)").matches;
  const collapsible = mobile && value.length > 720 && blocks.length >= 3;
  const visibleCount = collapsible ? 2 : blocks.length;

  blocks.slice(0, visibleCount).forEach((block) => {
    appendAnswerBlock(container, block, sources);
  });

  if (!collapsible) return;

  const details = document.createElement("details");
  details.className = "lm-help-assistant__answer-more";

  const summary = document.createElement("summary");
  summary.innerHTML = `
    <span>ادامه پاسخ</span>
    <i class="fa-solid fa-chevron-down" aria-hidden="true"></i>
  `;
  details.appendChild(summary);

  const body = document.createElement("div");
  body.className = "lm-help-assistant__answer-more-body";
  blocks.slice(visibleCount).forEach((block) => {
    appendAnswerBlock(body, block, sources);
  });

  details.appendChild(body);
  container.appendChild(details);
}

function guideFromOptions(options = {}) {
  return options.guide || options.sources?.find((source) => source?.guide)?.guide || null;
}

function guideCard(guide) {
  if (!guide?.steps?.length) return null;

  const card = document.createElement("section");
  card.className = "lm-help-assistant__guide";
  card.setAttribute("aria-label", guide.title || "مسیر انجام کار");

  const header = document.createElement("div");
  header.className = "lm-help-assistant__guide-header";
  const title = document.createElement("strong");
  title.textContent = guide.title || "مسیر انجام کار";
  header.appendChild(title);

  if (guide.required_role_label && guide.required_role !== "all") {
    const role = document.createElement("span");
    role.className = "lm-help-assistant__guide-role";
    role.textContent = guide.role_matches
      ? `برای ${guide.required_role_label}`
      : `نیازمند نقش ${guide.required_role_label}`;
    header.appendChild(role);
  }
  card.appendChild(header);

  if (guide.required_role !== "all" && guide.role_matches === false) {
    const note = document.createElement("p");
    note.className = "lm-help-assistant__guide-role-note";
    note.textContent = `این مسیر برای ${guide.required_role_label} است؛ لینک‌های عملیاتی برای نقش فعلی باز نمی‌شوند.`;
    card.appendChild(note);
  }

  const flow = document.createElement("ol");
  flow.className = "lm-help-assistant__flow";

  guide.steps.forEach((step, index) => {
    const item = document.createElement("li");
    item.className = "lm-help-assistant__flow-step";
    if (step.current_page) {
      item.classList.add("lm-help-assistant__flow-step--current");
    }

    const marker = document.createElement("span");
    marker.className = "lm-help-assistant__flow-marker";
    marker.textContent = String(step.number || index + 1);

    const copy = document.createElement("div");
    copy.className = "lm-help-assistant__flow-copy";

    const headingRow = document.createElement("div");
    headingRow.className = "lm-help-assistant__flow-heading-row";

    const stepUrl = safeHttpUrl(step.url, { sameOrigin: true });
    const heading = document.createElement(stepUrl ? "a" : "strong");
    heading.className = "lm-help-assistant__flow-title";
    heading.textContent = step.title || `مرحله ${index + 1}`;
    if (stepUrl) heading.href = stepUrl;
    headingRow.appendChild(heading);

    if (step.contextual) {
      const direct = document.createElement("span");
      direct.className = "lm-help-assistant__flow-direct";
      if (step.current_page) {
        direct.classList.add("lm-help-assistant__flow-direct--current");
      }
      direct.textContent = step.badge_label || (step.current_page ? "صفحه فعلی" : "همین مورد");
      direct.title = step.current_page
        ? "این مرحله همان صفحه‌ای است که الان باز کرده‌ای"
        : "این اقدام از اطلاعات واقعی صفحه فعلی ساخته شده";
      headingRow.appendChild(direct);
    }

    copy.appendChild(headingRow);

    if (step.body) {
      const body = document.createElement("p");
      body.textContent = step.body;
      copy.appendChild(body);
    }

    if (stepUrl && step.link_label) {
      const action = document.createElement("a");
      action.href = stepUrl;
      action.className = "lm-help-assistant__flow-action";
      appendIconLabel(action, step.link_label, "fa-solid fa-arrow-up-left-from-square");
      copy.appendChild(action);
    }

    item.append(marker, copy);
    flow.appendChild(item);
  });

  card.appendChild(flow);
  return card;
}

function feedbackRow(root, messageId) {
  if (!messageId) return null;

  const row = document.createElement("div");
  row.className = "lm-help-assistant__feedback";

  const label = document.createElement("span");
  label.textContent = "مفید بود؟";
  label.setAttribute("aria-live", "polite");
  row.appendChild(label);

  [
    ["helpful", "fa-regular fa-thumbs-up", "بله، مفید بود"],
    ["not_helpful", "fa-regular fa-thumbs-down", "نه، مفید نبود"],
  ].forEach(([rating, icon, aria]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.rating = rating;
    button.setAttribute("aria-label", aria);
    button.setAttribute("aria-pressed", "false");
    button.innerHTML = `<i class="${icon}" aria-hidden="true"></i>`;
    row.appendChild(button);
  });

  row.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", async () => {
      const buttons = [...row.querySelectorAll("button")];
      buttons.forEach((item) => { item.disabled = true; });
      try {
        const response = await fetch(root.dataset.feedbackUrl, {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrfToken(root),
            "X-Requested-With": "XMLHttpRequest",
          },
          body: JSON.stringify({
            message_id: messageId,
            rating: button.dataset.rating,
          }),
        });
        if (!response.ok) throw new Error("feedback");

        buttons.forEach((item) => {
          item.classList.remove("is-selected");
          item.setAttribute("aria-pressed", "false");
        });
        button.classList.add("is-selected");
        button.setAttribute("aria-pressed", "true");
        label.textContent = "ثبت شد";

        const handoff = root.querySelector("[data-help-handoff-box]");
        if (handoff) {
          handoff.hidden = button.dataset.rating !== "not_helpful";
        }
      } catch (_) {
        label.textContent = "ثبت بازخورد انجام نشد";
      } finally {
        buttons.forEach((item) => { item.disabled = false; });
      }
    });
  });

  return row;
}

function sourceDetails(sources = []) {
  if (!sources.length) return null;

  const details = document.createElement("details");
  details.className = "lm-help-assistant__message-sources";

  const summary = document.createElement("summary");
  summary.innerHTML = `
    <span><i class="fa-regular fa-book-open" aria-hidden="true"></i> منابع</span>
    <span class="lm-help-assistant__source-count">${sources.length}</span>
  `;
  details.appendChild(summary);

  const list = document.createElement("div");
  list.className = "lm-help-assistant__source-list";

  sources.forEach((source, index) => {
    const sourceUrl = safeHttpUrl(source.url, { sameOrigin: true });
    if (!sourceUrl) return;
    const link = document.createElement("a");
    link.href = sourceUrl;
    link.className = "lm-help-assistant__source-link";

    const number = document.createElement("span");
    number.className = "lm-help-assistant__source-number";
    number.textContent = String(index + 1);

    const copy = document.createElement("span");
    copy.className = "lm-help-assistant__source-copy";

    const title = document.createElement("strong");
    title.textContent = source.title || "راهنمای لومرا";
    copy.appendChild(title);

    if (source.heading && source.heading !== source.title) {
      const heading = document.createElement("small");
      heading.textContent = source.heading;
      copy.appendChild(heading);
    }

    const arrow = document.createElement("i");
    arrow.className = "fa-solid fa-chevron-left";
    arrow.setAttribute("aria-hidden", "true");

    link.append(number, copy, arrow);
    list.appendChild(link);
  });

  details.appendChild(list);
  return details;
}

function discoveryCard(payload = {}) {
  if (!payload?.handled) return null;

  const card = document.createElement("section");
  card.className = "lm-help-assistant__discovery";
  card.setAttribute("aria-label", "نتایج جستجوی لومی");

  if (Array.isArray(payload.filters) && payload.filters.length) {
    const filters = document.createElement("div");
    filters.className = "lm-help-assistant__discovery-filters";
    payload.filters.forEach((item) => {
      const chip = document.createElement("span");
      chip.className = "lm-help-assistant__discovery-chip";
      const icon = document.createElement("i");
      icon.className = `fa-solid fa-${item.icon || "check"}`;
      icon.setAttribute("aria-hidden", "true");
      const label = document.createElement("span");
      label.textContent = item.label || "";
      chip.append(icon, label);
      filters.appendChild(chip);
    });
    card.appendChild(filters);
  }

  if (payload.request_location) {
    const location = document.createElement("button");
    location.type = "button";
    location.className = "lm-help-assistant__discovery-location";
    location.dataset.lumiLocation = "1";
    location.innerHTML = `
      <span><i class="fa-solid fa-location-crosshairs" aria-hidden="true"></i> استفاده از موقعیت من</span>
      <i class="fa-solid fa-chevron-left" aria-hidden="true"></i>
    `;
    card.appendChild(location);
  }

  if (Array.isArray(payload.suggestions) && payload.suggestions.length) {
    const suggestions = document.createElement("div");
    suggestions.className = "lm-help-assistant__discovery-suggestions";
    payload.suggestions.forEach((item) => {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.lumiMessage = item.message || item.label || "";
      button.textContent = item.label || item.message || "";
      suggestions.appendChild(button);
    });
    card.appendChild(suggestions);
  }

  if (Array.isArray(payload.results) && payload.results.length) {
    const list = document.createElement("div");
    list.className = "lm-help-assistant__discovery-results";

    payload.results.forEach((result, index) => {
      const item = document.createElement("article");
      item.className = "lm-help-assistant__discovery-result";

      const top = document.createElement("div");
      top.className = "lm-help-assistant__discovery-result-top";

      const imageUrl = safeHttpUrl(result.image_url);
      if (imageUrl) {
        const image = document.createElement("img");
        image.className = "lm-help-assistant__discovery-image";
        image.src = imageUrl;
        image.alt = "";
        image.loading = "lazy";
        top.appendChild(image);
      } else {
        const placeholder = document.createElement("span");
        placeholder.className = "lm-help-assistant__discovery-image lm-help-assistant__discovery-image--placeholder";
        placeholder.innerHTML = '<i class="fa-solid fa-store" aria-hidden="true"></i>';
        top.appendChild(placeholder);
      }

      const copy = document.createElement("div");
      copy.className = "lm-help-assistant__discovery-result-copy";
      const rank = document.createElement("span");
      rank.className = "lm-help-assistant__discovery-rank";
      rank.textContent = String(index + 1);
      const title = document.createElement("strong");
      title.textContent = result.name || "مجموعه";
      const location = document.createElement("small");
      location.textContent = result.location || "";
      copy.append(title);
      if (result.location) copy.append(location);
      top.append(rank, copy);
      item.appendChild(top);

      const meta = document.createElement("div");
      meta.className = "lm-help-assistant__discovery-meta";
      if (result.price !== null && result.price !== undefined) {
        const price = document.createElement("span");
        appendMetaText(price, "fa-solid fa-wallet", `از ${formatToman(result.price)}`);
        meta.appendChild(price);
      }
      if (result.distance_km !== null && result.distance_km !== undefined) {
        const distance = document.createElement("span");
        appendMetaText(distance, "fa-solid fa-location-dot", `${result.distance_km} کیلومتر`);
        meta.appendChild(distance);
      }
      if (Number(result.rating) > 0) {
        const rating = document.createElement("span");
        appendMetaText(rating, "fa-solid fa-star", result.rating);
        meta.appendChild(rating);
      }
      if (result.availability) {
        const availability = document.createElement("span");
        availability.className = "lm-help-assistant__discovery-availability";
        appendMetaText(availability, "fa-regular fa-clock", result.availability);
        meta.appendChild(availability);
      }
      if (meta.childElementCount) item.appendChild(meta);

      if (result.catalog_service_id) {
        const action = document.createElement("button");
        action.type = "button";
        action.className = "lm-help-assistant__discovery-result-action";
        action.dataset.lumiBookSalon = String(result.id || "");
        action.dataset.lumiCatalogService = String(result.catalog_service_id || "");
        action.innerHTML = '<span>انتخاب این مجموعه</span><i class="fa-solid fa-chevron-left" aria-hidden="true"></i>';
        item.appendChild(action);
      }
      const resultUrl = safeHttpUrl(result.url, { sameOrigin: true });
      if (resultUrl) {
        const detail = document.createElement("a");
        detail.className = "lm-help-assistant__discovery-result-detail";
        detail.href = resultUrl;
        detail.textContent = "مشاهده صفحه مجموعه";
        item.appendChild(detail);
      }
      list.appendChild(item);
    });
    card.appendChild(list);
  }

  const searchUrl = safeHttpUrl(payload.search_url, { sameOrigin: true });
  if (searchUrl) {
    const all = document.createElement("a");
    all.className = "lm-help-assistant__discovery-all";
    all.href = searchUrl;
    appendIconLabel(all, payload.search_label || "مشاهده همه نتایج", "fa-solid fa-arrow-up-left-from-square");
    card.appendChild(all);
  }

  return card.childElementCount ? card : null;
}


function appendBookingSelectionContext(card, payload = {}) {
  if (!["booking_slots", "booking_slots_empty"].includes(payload.kind)) return;

  const context = payload.ui_context || {};
  const items = [
    ["خدمت", context.service],
    ["مجموعه", context.salon],
    ["متخصص", context.stylist],
  ].filter(([, value]) => String(value || "").trim());

  if (!items.length) return;

  const box = document.createElement("div");
  box.className = "lm-help-assistant__booking-selection-context";
  box.setAttribute("aria-label", "انتخاب فعلی رزرو");

  items.forEach(([label, value]) => {
    const item = document.createElement("span");
    const key = document.createElement("small");
    const data = document.createElement("strong");
    key.textContent = label;
    data.textContent = String(value || "").trim();
    item.append(key, data);
    box.appendChild(item);
  });

  card.appendChild(box);
}

function bookingCard(payload = {}) {
  if (!payload?.handled || !String(payload.kind || "").startsWith("booking_")) return null;

  const card = document.createElement("section");
  card.className = "lm-help-assistant__booking";
  card.setAttribute("aria-label", "رزرو با لومی");

  const loginUrl = safeHttpUrl(payload.login_url, { sameOrigin: true });
  if (payload.kind === "booking_auth_required" && loginUrl) {
    const login = document.createElement("a");
    login.className = "lm-help-assistant__booking-primary";
    login.href = loginUrl;
    appendIconLabel(login, "ورود به حساب مشتری", "fa-solid fa-arrow-left-to-bracket");
    card.appendChild(login);
    return card;
  }

  appendBookingSelectionContext(card, payload);

  if (payload.kind === "booking_stylists" && Array.isArray(payload.providers)) {
    const header = document.createElement("div");
    header.className = "lm-help-assistant__booking-context";
    const serviceName = document.createElement("strong");
    serviceName.textContent = payload.service?.name || "خدمت";
    const salonName = document.createElement("span");
    salonName.textContent = payload.salon?.name || "";
    header.append(serviceName, salonName);
    card.appendChild(header);

    const list = document.createElement("div");
    list.className = "lm-help-assistant__booking-providers";
    payload.providers.forEach((provider) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "lm-help-assistant__booking-provider";
      button.dataset.lumiBookStylist = String(provider.id || "");

      const providerImageUrl = safeHttpUrl(provider.image_url);
      if (providerImageUrl) {
        const image = document.createElement("img");
        image.src = providerImageUrl;
        image.alt = "";
        image.loading = "lazy";
        button.appendChild(image);
      } else {
        const avatar = document.createElement("span");
        avatar.className = "lm-help-assistant__booking-provider-avatar";
        const avatarIcon = document.createElement("i");
        avatarIcon.className = "fa-solid fa-user";
        avatarIcon.setAttribute("aria-hidden", "true");
        avatar.appendChild(avatarIcon);
        button.appendChild(avatar);
      }

      const copy = document.createElement("span");
      copy.className = "lm-help-assistant__booking-provider-copy";
      const name = document.createElement("strong");
      name.textContent = provider.name || "متخصص";
      const when = document.createElement("small");
      when.textContent = provider.next_date_label && provider.next_time
        ? `نزدیک‌ترین وقت: ${provider.next_date_label} · ${provider.next_time}`
        : "وقت قابل رزرو";
      copy.append(name, when);

      if (Number(provider.price) > 0) {
        const price = document.createElement("em");
        price.textContent = formatToman(provider.price);
        copy.appendChild(price);
      }

      const arrow = document.createElement("i");
      arrow.className = "fa-solid fa-chevron-left";
      arrow.setAttribute("aria-hidden", "true");
      button.append(copy, arrow);
      list.appendChild(button);
    });
    card.appendChild(list);
  }

  if (payload.kind === "booking_slots" && Array.isArray(payload.slots)) {
    const grouped = new Map();
    payload.slots.forEach((slot) => {
      const key = slot.date || "";
      if (!grouped.has(key)) grouped.set(key, { label: slot.date_label || key, items: [] });
      grouped.get(key).items.push(slot);
    });
    grouped.forEach((group) => {
      const day = document.createElement("div");
      day.className = "lm-help-assistant__booking-day";
      const label = document.createElement("strong");
      label.textContent = group.label;
      const slots = document.createElement("div");
      slots.className = "lm-help-assistant__booking-slots";
      group.items.forEach((slot) => {
        const button = document.createElement("button");
        button.type = "button";
        button.dataset.lumiBookSlot = "1";
        button.dataset.date = slot.date || "";
        button.dataset.time = slot.time || "";
        button.textContent = slot.time || "";
        slots.appendChild(button);
      });
      day.append(label, slots);
      card.appendChild(day);
    });
    const change = document.createElement("button");
    change.type = "button";
    change.className = "lm-help-assistant__booking-link";
    change.dataset.lumiBookingBack = "stylists";
    change.textContent = "تغییر متخصص";
    card.appendChild(change);
  }

  if (payload.kind === "booking_slots_empty") {
    if (payload.relax_available) {
      const relax = document.createElement("button");
      relax.type = "button";
      relax.className = "lm-help-assistant__booking-primary lm-help-assistant__booking-primary--soft";
      relax.dataset.lumiRelaxSlots = "1";
      relax.innerHTML = '<span>دیدن نزدیک‌ترین زمان‌های آزاد</span><i class="fa-regular fa-clock" aria-hidden="true"></i>';
      card.appendChild(relax);
    }
    const change = document.createElement("button");
    change.type = "button";
    change.className = "lm-help-assistant__booking-link";
    change.dataset.lumiBookingBack = "stylists";
    change.textContent = "انتخاب متخصص دیگر";
    card.appendChild(change);
  }

  if (payload.kind === "booking_preview" && payload.preview) {
    const preview = payload.preview;
    const title = document.createElement("div");
    title.className = "lm-help-assistant__booking-preview-title";
    title.innerHTML = '<i class="fa-solid fa-shield-check" aria-hidden="true"></i><strong>بررسی نهایی رزرو</strong>';
    card.appendChild(title);

    const rows = [
      ["خدمت", preview.service],
      ["مجموعه", preview.salon],
      ["متخصص", preview.stylist],
      ["زمان", `${preview.date_label || preview.date} · ${preview.time}`],
      ["مبلغ نهایی", formatToman(preview.total_amount)],
    ];
    const table = document.createElement("dl");
    table.className = "lm-help-assistant__booking-preview";
    rows.forEach(([label, value]) => {
      const dt = document.createElement("dt"); dt.textContent = label;
      const dd = document.createElement("dd"); dd.textContent = value || "—";
      table.append(dt, dd);
    });
    card.appendChild(table);

    if (Number(preview.discount_amount) > 0) {
      const discount = document.createElement("p");
      discount.className = "lm-help-assistant__booking-discount";
      discount.textContent = `${formatToman(preview.discount_amount)} تخفیف روی رزرو اعمال شده.`;
      card.appendChild(discount);
    }

    const confirm = document.createElement("div");
    confirm.className = "lm-help-assistant__booking-confirm";
    (payload.payment_methods || []).forEach((method) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "lm-help-assistant__booking-primary";
      button.dataset.lumiCheckout = method.value || "";
      button.dataset.checkoutUrl = payload.checkout_url || "";
      let label = method.label || "تأیید و رزرو";
      if (method.value === "pay_in_salon") label = "تأیید و رزرو";
      else if (method.value === "wallet") label = "پرداخت از کیف پول و رزرو";
      else if (method.value === "online") label = "ادامه و پرداخت آنلاین";
      appendIconLabel(button, label, "fa-solid fa-check");
      confirm.appendChild(button);
    });
    card.appendChild(confirm);

    const note = document.createElement("small");
    note.className = "lm-help-assistant__booking-safe-note";
    note.textContent = "با تأیید، قیمت و آزادبودن زمان دوباره بررسی می‌شود.";
    card.appendChild(note);
  }

  if (["booking_stylists", "booking_slots", "booking_slots_empty", "booking_preview"].includes(payload.kind)) {
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "lm-help-assistant__booking-cancel";
    cancel.dataset.lumiBookingCancel = "1";
    cancel.textContent = "انصراف از رزرو";
    card.appendChild(cancel);
  }

  return card.childElementCount ? card : null;
}

function operationalCard(payload = {}) {
  if (!payload?.handled) return null;

  const card = document.createElement("section");
  card.className = "lm-help-assistant__operation";
  card.setAttribute("aria-label", "عملیات لومی");

  const addSuggestions = (items = []) => {
    if (!Array.isArray(items) || !items.length) return;
    const wrap = document.createElement("div");
    wrap.className = "lm-help-assistant__operation-suggestions";
    items.forEach((value) => {
      const text = typeof value === "string" ? value : (value?.label || value?.message || "");
      if (!text) return;
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.lumiMessage = typeof value === "string" ? value : (value?.message || text);
      button.textContent = text;
      wrap.appendChild(button);
    });
    if (wrap.childElementCount) card.appendChild(wrap);
  };

  if (payload.kind === "action_collect") {
    addSuggestions(payload.suggestions || []);
  }

  if (payload.kind === "action_preview" && payload.preview) {
    const preview = payload.preview;
    const header = document.createElement("div");
    header.className = "lm-help-assistant__operation-header";
    const icon = document.createElement("span");
    icon.className = "lm-help-assistant__operation-icon";
    const iconName = String(preview.icon || "check").replace(/[^a-z0-9-]/gi, "");
    icon.innerHTML = `<i class="fa-solid fa-${iconName || "check"}" aria-hidden="true"></i>`;
    const title = document.createElement("strong");
    title.textContent = preview.title || "بررسی و تأیید";
    header.append(icon, title);
    card.appendChild(header);

    const rows = document.createElement("dl");
    rows.className = "lm-help-assistant__operation-preview";
    (preview.rows || []).forEach((row) => {
      const dt = document.createElement("dt");
      const dd = document.createElement("dd");
      dt.textContent = row?.label || "";
      dd.textContent = row?.value || "—";
      rows.append(dt, dd);
    });
    if (rows.childElementCount) card.appendChild(rows);

    if (preview.notice) {
      const notice = document.createElement("p");
      notice.className = "lm-help-assistant__operation-notice";
      notice.textContent = preview.notice;
      card.appendChild(notice);
    }

    const actions = document.createElement("div");
    actions.className = "lm-help-assistant__operation-actions";
    if (payload.confirmation_token) {
      const confirm = document.createElement("button");
      confirm.type = "button";
      confirm.className = "lm-help-assistant__operation-primary";
      if (preview.danger) confirm.classList.add("lm-help-assistant__operation-primary--danger");
      confirm.dataset.lumiConfirm = payload.confirmation_token;
      confirm.textContent = payload.confirm_label || "تأیید و انجام";
      actions.appendChild(confirm);
    }
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "lm-help-assistant__operation-secondary";
    cancel.dataset.lumiActionCancel = "1";
    cancel.textContent = payload.cancel_label || "انصراف";
    actions.appendChild(cancel);
    card.appendChild(actions);
  }

  if (payload.kind === "action_choice_list" && payload.choice_list) {
    const title = document.createElement("strong");
    title.className = "lm-help-assistant__operation-section-title";
    title.textContent = payload.choice_list.title || "یک مورد رو انتخاب کن";
    card.appendChild(title);

    const list = document.createElement("div");
    list.className = "lm-help-assistant__operation-choice-list";
    (payload.choice_list.items || []).forEach((item) => {
      if (!item?.choice_token) return;
      const row = document.createElement("article");
      row.className = "lm-help-assistant__operation-choice-item";
      const copy = document.createElement("div");
      copy.className = "lm-help-assistant__operation-review-copy";
      const strong = document.createElement("strong");
      strong.textContent = item.title || "نوبت";
      const small = document.createElement("small");
      small.textContent = item.subtitle || "";
      copy.append(strong, small);
      if (item.detail) {
        const detail = document.createElement("p");
        detail.textContent = item.detail;
        copy.appendChild(detail);
      }
      const choose = document.createElement("button");
      choose.type = "button";
      choose.className = "lm-help-assistant__operation-choice-button";
      choose.dataset.lumiChoice = item.choice_token;
      choose.textContent = item.choice_label || "انتخاب";
      row.append(copy, choose);
      list.appendChild(row);
    });
    if (list.childElementCount) card.appendChild(list);
  }

  if (payload.kind === "action_review_list" && payload.review_list) {
    const title = document.createElement("strong");
    title.className = "lm-help-assistant__operation-section-title";
    title.textContent = payload.review_list.title || "درخواست‌های در انتظار";
    card.appendChild(title);

    const list = document.createElement("div");
    list.className = "lm-help-assistant__operation-review-list";
    (payload.review_list.items || []).forEach((item) => {
      const row = document.createElement("article");
      row.className = "lm-help-assistant__operation-review-item";
      const copy = document.createElement("div");
      copy.className = "lm-help-assistant__operation-review-copy";
      const strong = document.createElement("strong");
      strong.textContent = item.title || "درخواست";
      const small = document.createElement("small");
      small.textContent = item.subtitle || "";
      copy.append(strong, small);
      if (item.detail) {
        const detail = document.createElement("p");
        detail.textContent = item.detail;
        copy.appendChild(detail);
      }
      row.appendChild(copy);
      const actions = document.createElement("div");
      actions.className = "lm-help-assistant__operation-review-actions";
      if (item.approve_token) {
        const approve = document.createElement("button");
        approve.type = "button";
        approve.className = "is-approve";
        approve.dataset.lumiConfirm = item.approve_token;
        approve.textContent = "تأیید";
        actions.appendChild(approve);
      }
      if (item.reject_token) {
        const reject = document.createElement("button");
        reject.type = "button";
        reject.className = "is-reject";
        reject.dataset.lumiConfirm = item.reject_token;
        reject.textContent = "رد";
        actions.appendChild(reject);
      }
      row.appendChild(actions);
      list.appendChild(row);
    });
    if (list.childElementCount) card.appendChild(list);

    const manageUrl = safeHttpUrl(payload.review_list.manage_url, { sameOrigin: true });
    if (manageUrl) {
      const link = document.createElement("a");
      link.className = "lm-help-assistant__operation-link";
      link.href = manageUrl;
      link.textContent = "مشاهده همه در داشبورد";
      card.appendChild(link);
    }
  }

  const actionLinkUrl = safeHttpUrl(payload.link?.url, { sameOrigin: true });
  if (payload.kind === "action_link" && actionLinkUrl) {
    const link = document.createElement("a");
    link.className = "lm-help-assistant__operation-primary lm-help-assistant__operation-primary--link";
    link.href = actionLinkUrl;
    const iconName = String(payload.link.icon || "arrow-up-left-from-square").replace(/[^a-z0-9-]/gi, "");
    const label = document.createElement("span");
    label.textContent = payload.link.label || "باز کردن";
    const icon = document.createElement("i");
    icon.className = `fa-solid fa-${iconName || "arrow-up-left-from-square"}`;
    icon.setAttribute("aria-hidden", "true");
    link.append(label, icon);
    card.appendChild(link);
  }

  if (payload.kind === "action_success" && payload.success) {
    const success = document.createElement("div");
    success.className = "lm-help-assistant__operation-success";
    const icon = document.createElement("span");
    icon.innerHTML = '<i class="fa-solid fa-check" aria-hidden="true"></i>';
    const copy = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = payload.success.title || "انجام شد";
    copy.appendChild(title);
    if (payload.success.detail) {
      const small = document.createElement("small");
      small.textContent = payload.success.detail;
      copy.appendChild(small);
    }
    success.append(icon, copy);
    card.appendChild(success);
    const successUrl = safeHttpUrl(payload.success.url, { sameOrigin: true });
    if (successUrl) {
      const link = document.createElement("a");
      link.className = "lm-help-assistant__operation-link";
      link.href = successUrl;
      link.textContent = payload.success.url_label || "مشاهده";
      card.appendChild(link);
    }
  }

  if (payload.kind === "action_capabilities" && Array.isArray(payload.capabilities)) {
    payload.capabilities.forEach((group) => {
      const section = document.createElement("div");
      section.className = "lm-help-assistant__capability-group";
      const title = document.createElement("strong");
      title.textContent = group.title || "قابلیت‌ها";
      section.appendChild(title);
      const list = document.createElement("ul");
      (group.items || []).forEach((item) => {
        const li = document.createElement("li");
        li.textContent = item;
        list.appendChild(li);
      });
      if (list.childElementCount) section.appendChild(list);
      const prompts = document.createElement("div");
      prompts.className = "lm-help-assistant__operation-suggestions";
      (group.prompts || []).forEach((prompt) => {
        const button = document.createElement("button");
        button.type = "button";
        button.dataset.lumiMessage = prompt;
        button.textContent = prompt;
        prompts.appendChild(button);
      });
      if (prompts.childElementCount) section.appendChild(prompts);
      card.appendChild(section);
    });
  }

  return card.childElementCount ? card : null;
}

function addMessage(container, role, text, options = {}) {
  const row = document.createElement("div");
  row.className = `lm-help-assistant__message lm-help-assistant__message--${role}`;
  if (options.error) row.classList.add("lm-help-assistant__message--error");
  if (options.temporary) row.dataset.temporary = "1";

  if (role === "assistant" && !options.temporary) {
    row.appendChild(createLumiAvatar(options.root, "lm-help-assistant__message-avatar"));
  }

  const stack = document.createElement("div");
  stack.className = "lm-help-assistant__message-stack";

  const bubble = document.createElement("div");
  bubble.className = "lm-help-assistant__bubble";

  if (options.temporary) {
    const typing = document.createElement("div");
    typing.className = "lm-help-assistant__typing-wrap";
    typing.setAttribute("role", "status");
    typing.setAttribute("aria-live", "polite");
    typing.setAttribute("aria-label", "لومی در حال آماده‌سازی پاسخ است");
    typing.innerHTML = `
      <span class="lm-help-assistant__typing" aria-hidden="true"><span></span><span></span><span></span></span>
    `;
    bubble.appendChild(typing);
  } else if (role === "assistant") {
    renderAssistantAnswer(bubble, text, options.sources || []);
  } else {
    bubble.textContent = text;
  }

  stack.appendChild(bubble);

  if (role === "assistant" && !options.temporary && options.retryMessage) {
    const retry = document.createElement("button");
    retry.type = "button";
    retry.className = "lm-help-assistant__retry";
    retry.dataset.lumiRetryMessage = String(options.retryMessage);
    retry.innerHTML = '<i class="fa-solid fa-rotate-right" aria-hidden="true"></i><span>دوباره امتحان</span>';
    stack.appendChild(retry);
  }

  if (role === "assistant" && !options.temporary) {
    const guide = guideCard(guideFromOptions(options));
    if (guide) stack.appendChild(guide);

    const discovery = discoveryCard(options.discovery || null);
    if (discovery) stack.appendChild(discovery);

    const booking = bookingCard(options.booking || null);
    if (booking) stack.appendChild(booking);

    const operational = operationalCard(options.operational || null);
    if (operational) stack.appendChild(operational);

    const details = sourceDetails(options.sources || []);
    if (details) stack.appendChild(details);

    const feedback = feedbackRow(options.root, options.messageId);
    if (feedback) stack.appendChild(feedback);
  }

  row.appendChild(stack);
  container.appendChild(row);
  container.scrollTop = container.scrollHeight;
  return row;
}

async function getContext(root) {
  const url = new URL(root.dataset.contextUrl, window.location.origin);
  url.searchParams.set("path", root.dataset.currentPath || window.location.pathname);
  url.searchParams.set("route", root.dataset.currentRoute || "");

  const response = await fetch(url, {
    credentials: "same-origin",
    headers: { "X-Requested-With": "XMLHttpRequest" },
  });
  if (!response.ok) throw new Error("context");
  return response.json();
}

async function getConversation(root, conversationId) {
  if (!conversationId) return null;
  const url = new URL(root.dataset.conversationUrl, window.location.origin);
  url.searchParams.set("conversation_id", conversationId);

  const response = await fetch(url, {
    credentials: "same-origin",
    headers: { "X-Requested-With": "XMLHttpRequest" },
  });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error("conversation");
  return response.json();
}

async function sendAssistantAction(root, { message = "", actionState = null, command = "message", confirmationToken = "", choiceToken = "" } = {}) {
  if (!root.dataset.assistantActionUrl) return { handled: false };
  const requestOptions = {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken(root),
      "X-Requested-With": "XMLHttpRequest",
    },
    body: JSON.stringify({
      message,
      action_state: actionState || null,
      current_path: root.dataset.currentPath || window.location.pathname,
      command,
      confirmation_token: confirmationToken || "",
      choice_token: choiceToken || "",
    }),
  };
  const response = command === "execute"
    ? await fetch(root.dataset.assistantActionUrl, requestOptions)
    : await fetchWithTimeout(root.dataset.assistantActionUrl, requestOptions);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(lumiApiError(response, payload, "الان نتونستم این کار رو انجام بدم. دوباره امتحان کن."));
  return payload;
}

function submitOperationalForm(root, payload) {
  const spec = payload?.form_submit;
  const actionUrl = safeHttpUrl(spec?.url, { sameOrigin: true });
  if (!actionUrl) throw new Error("مسیر اجرای عملیات در دسترس نیست.");
  const form = document.createElement("form");
  form.method = "post";
  form.action = actionUrl;
  form.hidden = true;
  const fields = { csrfmiddlewaretoken: csrfToken(root), ...(spec.fields || {}) };
  Object.entries(fields).forEach(([name, value]) => {
    const input = document.createElement("input");
    input.type = "hidden";
    input.name = name;
    input.value = value == null ? "" : String(value);
    form.appendChild(input);
  });
  document.body.appendChild(form);
  setStoredActionState(null);
  form.submit();
}

async function postOperationalEndpoint(root, payload) {
  const spec = payload?.remote_post;
  const actionUrl = safeHttpUrl(spec?.url, { sameOrigin: true });
  if (!actionUrl) throw new Error("مسیر اجرای عملیات در دسترس نیست.");
  const response = await fetch(actionUrl, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "X-CSRFToken": csrfToken(root),
      "X-Requested-With": "XMLHttpRequest",
    },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok || body.success === false) {
    const fallback = response.status >= 500
      ? "نتونستم نتیجه این عملیات رو با اطمینان تأیید کنم. قبل از تکرار، وضعیت فعلی رو بررسی کن."
      : "عملیات انجام نشد.";
    throw new Error(lumiApiError(response, body, fallback));
  }
  return {
    handled: true,
    kind: "action_success",
    answer: body.message || "عملیات با موفقیت انجام شد.",
    action_state: null,
    success: {
      title: "انجام شد",
      detail: body.refund_amount ? `${formatToman(body.refund_amount)} به کیف پول برگشت.` : "",
      url: spec.success_url || "",
      url_label: spec.success_label || "مشاهده",
    },
  };
}

async function sendCustomerDiscovery(root, message, actionState, coordinates = null) {
  if (!root.dataset.customerDiscoveryUrl) return { handled: false };
  const body = {
    message,
    action_state: actionState || null,
  };
  if (coordinates) {
    body.latitude = coordinates.latitude;
    body.longitude = coordinates.longitude;
  }

  const response = await fetchWithTimeout(root.dataset.customerDiscoveryUrl, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken(root),
      "X-Requested-With": "XMLHttpRequest",
    },
    body: JSON.stringify(body),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(lumiApiError(response, payload, "الان نتونستم جستجو رو انجام بدم. دوباره امتحان کن."));
  return payload;
}

async function sendCustomerBooking(root, action, actionState, extra = {}) {
  if (!root.dataset.customerBookingUrl) throw new Error("مسیر رزرو لومی در دسترس نیست.");
  const response = await fetchWithTimeout(root.dataset.customerBookingUrl, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken(root),
      "X-Requested-With": "XMLHttpRequest",
    },
    body: JSON.stringify({
      action,
      action_state: actionState || null,
      ...extra,
    }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(lumiApiError(response, payload, "الان نتونستم اطلاعات رزرو رو دریافت کنم. دوباره امتحان کن."));
  return payload;
}

function submitExistingCheckout(root, url, paymentMethod) {
  const checkoutUrl = safeHttpUrl(url, { sameOrigin: true });
  if (!checkoutUrl || !paymentMethod) throw new Error("اطلاعات تأیید رزرو ناقص است.");
  const form = document.createElement("form");
  form.method = "post";
  form.action = checkoutUrl;
  form.hidden = true;
  const fields = {
    csrfmiddlewaretoken: csrfToken(root),
    form_action: "confirm_checkout",
    coupon_code: "",
    payment_method: paymentMethod,
  };
  Object.entries(fields).forEach(([name, value]) => {
    const input = document.createElement("input");
    input.type = "hidden";
    input.name = name;
    input.value = value;
    form.appendChild(input);
  });
  document.body.appendChild(form);
  setStoredActionState(null);
  form.submit();
}

function requestBrowserLocation() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error("مرورگرت دسترسی به موقعیت مکانی رو پشتیبانی نمی‌کنه. نام محله رو بنویس."));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => resolve({
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
      }),
      () => reject(new Error("دسترسی موقعیت داده نشد. نام محله یا محدوده رو بنویس.")),
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 }
    );
  });
}

async function sendChat(root, message, history, conversationId) {
  const response = await fetchWithTimeout(root.dataset.chatUrl, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken(root),
      "X-Requested-With": "XMLHttpRequest",
    },
    body: JSON.stringify({
      message,
      path: root.dataset.currentPath || window.location.pathname,
      route_name: root.dataset.currentRoute || "",
      history: history.slice(-6),
      conversation_id: conversationId,
    }),
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(lumiApiError(response, payload, "الان نتونستم پاسخ بدم. دوباره امتحان کن."));
  return payload;
}

function init() {
  const root = document.querySelector(ROOT_SELECTOR);
  if (!root || root.dataset.bound === "1") return;
  root.dataset.bound = "1";

  // The widget must be a direct child of <body>. A transformed/contained page
  // ancestor can otherwise make position:fixed relative to that ancestor,
  // which is especially visible on mobile responsive layouts.
  if (root.parentElement !== document.body) {
    document.body.appendChild(root);
  }

  // Legacy versions allowed permanently hiding the assistant. The control no
  // longer exists, so clear the old preference to avoid leaving Lومي invisible.
  try { localStorage.removeItem("loomera.help-assistant.hidden"); } catch (_) {}

  const fab = root.querySelector("[data-help-fab]");
  const panel = root.querySelector("[data-help-panel]");
  const close = root.querySelector("[data-help-close]");
  const newChat = root.querySelector("[data-help-new-chat]");
  const form = root.querySelector("[data-help-form]");
  const input = root.querySelector("[data-help-input]");
  const send = root.querySelector("[data-help-send]");
  const messages = root.querySelector("[data-help-messages]");
  const welcome = root.querySelector("[data-help-welcome]");
  const prompts = root.querySelector("[data-help-prompts]");
  const summary = root.querySelector("[data-help-context-summary]");
  const pageLabel = root.querySelector("[data-help-page-label]");
  const dot = root.querySelector("[data-help-new-dot]");
  const handoffBox = root.querySelector("[data-help-handoff-box]");
  const escalate = root.querySelector("[data-help-escalate]");
  const newChatConfirm = root.querySelector("[data-help-new-chat-confirm]");
  const confirmNewChat = root.querySelector("[data-help-confirm-new-chat]");
  const cancelNewChat = root.querySelector("[data-help-cancel-new-chat]");

  let contextLoaded = false;
  let conversationHydrated = false;
  let history = [];
  let context = null;
  let conversationId = getStoredConversationId();
  let actionState = getStoredActionState();
  let actionCoordinates = null;
  let interactionBusy = false;
  let lastFocusBeforeOpen = null;
  let confirmReturnFocus = null;
  let bookingContext = { salon: "", service: "", stylist: "" };

  const isMobileViewport = () => matchMedia("(max-width:767px)").matches;
  const focusInputWhenAppropriate = ({ delay = 0 } = {}) => {
    // Mobile UX: opening or updating Lumi must not summon the software keyboard.
    // On phones the textarea gets focus only from a direct user tap.
    if (isMobileViewport()) return;
    if (delay > 0) {
      window.setTimeout(() => input.focus(), delay);
      return;
    }
    input.focus();
  };

  function setInteractionBusy(value) {
    interactionBusy = Boolean(value);
    send.disabled = interactionBusy;
    if (newChat) newChat.disabled = interactionBusy;
    root.classList.toggle("lm-help-assistant--busy", interactionBusy);
    if (interactionBusy) {
      form.setAttribute("aria-busy", "true");
    } else {
      form.removeAttribute("aria-busy");
    }
  }

  function panelFocusableElements() {
    return [...panel.querySelectorAll(
      'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), summary, [tabindex]:not([tabindex="-1"])'
    )].filter((element) => !element.hidden && element.getClientRects().length > 0);
  }

  function updateDialogMode() {
    if (matchMedia("(max-width:767px)").matches && !panel.hidden) {
      panel.setAttribute("aria-modal", "true");
    } else {
      panel.removeAttribute("aria-modal");
    }
  }

  function confirmFocusableElements() {
    if (!newChatConfirm || newChatConfirm.hidden) return [];
    return [...newChatConfirm.querySelectorAll('button:not([disabled]), [tabindex]:not([tabindex="-1"])')]
      .filter((element) => !element.hidden && element.getClientRects().length > 0);
  }

  function openNewChatConfirm() {
    if (!newChatConfirm || interactionBusy) return;
    confirmReturnFocus = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : newChat;
    newChatConfirm.hidden = false;
    root.classList.add("lm-help-assistant--confirming");
    requestAnimationFrame(() => cancelNewChat?.focus());
  }

  function closeNewChatConfirm({ restoreFocus = true } = {}) {
    if (!newChatConfirm) return;
    newChatConfirm.hidden = true;
    root.classList.remove("lm-help-assistant--confirming");
    if (restoreFocus) {
      const target = confirmReturnFocus?.isConnected ? confirmReturnFocus : newChat;
      requestAnimationFrame(() => target?.focus?.());
    }
    confirmReturnFocus = null;
  }

  function updateBookingContext(payload = {}, overrides = {}) {
    const salon = String(overrides.salon || payload?.salon?.name || payload?.preview?.salon || "").trim();
    const service = String(overrides.service || payload?.service?.name || payload?.preview?.service || "").trim();
    const stylist = String(overrides.stylist || payload?.stylist?.name || payload?.preview?.stylist || "").trim();

    if (salon) bookingContext.salon = salon;
    if (service) bookingContext.service = service;
    if (stylist) bookingContext.stylist = stylist;

    return {
      ...(payload || {}),
      ui_context: { ...bookingContext },
    };
  }

  applyPosition(root, fab);
  bindDrag(root, fab, panel);

  function resetConversationUi() {
    history = [];
    conversationId = null;
    setStoredConversationId(null);
    actionState = null;
    actionCoordinates = null;
    bookingContext = { salon: "", service: "", stylist: "" };
    closeNewChatConfirm({ restoreFocus: false });
    setStoredActionState(null);
    conversationHydrated = true;

    messages.querySelectorAll(".lm-help-assistant__message").forEach((item) => item.remove());
    welcome.hidden = false;
    handoffBox.hidden = true;
    input.value = "";
    autoGrow(input);
  }

  async function loadContext() {
    if (contextLoaded) return;
    contextLoaded = true;

    try {
      context = await getContext(root);
      // Header identity stays stable. Page context is used only for suggested
      // prompts and retrieval, not as extra visual copy in the header.
      if (pageLabel) {
        pageLabel.innerHTML = "";
        const online = document.createElement("span");
        online.className = "lm-help-assistant__online-dot";
        pageLabel.appendChild(online);
        pageLabel.append(document.createTextNode("دستیار راهنمای لومرا"));
      }
      if (summary) summary.textContent = "چه کاری می‌خوای انجام بدی؟";

      prompts.innerHTML = "";
      (context.quick_prompts || []).slice(0, 3).forEach((text) => {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = text;
        button.addEventListener("click", () => {
          if (interactionBusy) return;
          input.value = text;
          autoGrow(input);
          form.requestSubmit();
        });
        prompts.appendChild(button);
      });

      const seenKey = `loomera.help-assistant.seen.${context.page_key || "general"}.v3`;
      dot.hidden = localStorage.getItem(seenKey) === "1";
    } catch (_) {
      if (pageLabel) {
        pageLabel.innerHTML = '<span class="lm-help-assistant__online-dot"></span> دستیار راهنمای لومرا';
      }
    }
  }

  async function hydrateConversation() {
    if (conversationHydrated) return;
    conversationHydrated = true;
    if (!conversationId) return;

    const previousLive = messages.getAttribute("aria-live") || "polite";
    let liveMuted = false;
    try {
      const payload = await getConversation(root, conversationId);
      if (!payload?.messages?.length) {
        if (!payload) {
          conversationId = null;
          setStoredConversationId(null);
        }
        return;
      }

      welcome.hidden = true;
      history = [];
      messages.setAttribute("aria-live", "off");
      liveMuted = true;

      payload.messages.forEach((item) => {
        addMessage(messages, item.role, item.content, {
          root,
          messageId: item.message_id,
          sources: item.sources || [],
        });
        history.push({ role: item.role, content: item.content });
      });

      handoffBox.hidden = true;
    } catch (_) {
      conversationId = null;
      setStoredConversationId(null);
    } finally {
      if (liveMuted) {
        requestAnimationFrame(() => {
          messages.setAttribute("aria-live", previousLive);
        });
      }
    }
  }

  async function openPanel() {
    if (panel.hidden) {
      lastFocusBeforeOpen = document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    }
    panel.hidden = false;
    if (matchMedia("(max-width:767px)").matches) {
      document.body.classList.add("lm-help-assistant-open");
    }
    fab.setAttribute("aria-expanded", "true");
    updateDialogMode();
    await Promise.all([loadContext(), hydrateConversation()]);

    if (context?.page_key) {
      localStorage.setItem(`loomera.help-assistant.seen.${context.page_key}.v3`, "1");
      dot.hidden = true;
    }

    focusInputWhenAppropriate({ delay: 80 });
  }

  function closePanel({ restoreFocus = true } = {}) {
    closeNewChatConfirm({ restoreFocus: false });
    panel.hidden = true;
    fab.setAttribute("aria-expanded", "false");
    document.body.classList.remove("lm-help-assistant-open");
    updateDialogMode();

    if (restoreFocus) {
      const target = lastFocusBeforeOpen?.isConnected ? lastFocusBeforeOpen : fab;
      requestAnimationFrame(() => target?.focus?.());
    }
  }

  fab.addEventListener("click", () => panel.hidden ? openPanel() : closePanel());
  close?.addEventListener("click", closePanel);

  newChat?.addEventListener("click", () => {
    if (interactionBusy) return;
    if (history.length) {
      openNewChatConfirm();
      return;
    }
    resetConversationUi();
    focusInputWhenAppropriate();
  });

  cancelNewChat?.addEventListener("click", () => closeNewChatConfirm());

  confirmNewChat?.addEventListener("click", () => {
    closeNewChatConfirm({ restoreFocus: false });
    resetConversationUi();
    focusInputWhenAppropriate();
  });

  input.addEventListener("input", () => autoGrow(input));
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (!interactionBusy) form.requestSubmit();
    }
  });

  root.addEventListener("click", async (event) => {
    const retryButton = event.target.closest("[data-lumi-retry-message]");
    if (retryButton && root.contains(retryButton) && !interactionBusy) {
      const retryMessage = String(retryButton.dataset.lumiRetryMessage || "").trim();
      if (!retryMessage) return;
      retryButton.disabled = true;
      retryButton.closest(".lm-help-assistant__message")?.remove();
      form.dataset.lumiRetryMessage = retryMessage;
      input.value = retryMessage;
      autoGrow(input);
      form.requestSubmit();
      return;
    }
    const messageButton = event.target.closest("[data-lumi-message]");
    if (messageButton && root.contains(messageButton) && !interactionBusy) {
      input.value = messageButton.dataset.lumiMessage || "";
      autoGrow(input);
      form.requestSubmit();
      return;
    }

    const choiceButton = event.target.closest("[data-lumi-choice]");
    if (choiceButton && root.contains(choiceButton) && !interactionBusy) {
      choiceButton.disabled = true;
      setInteractionBusy(true);
      const typing = addMessage(messages, "assistant", "", { temporary: true });
      try {
        const payload = await sendAssistantAction(root, {
          command: "choose",
          choiceToken: choiceButton.dataset.lumiChoice || "",
          actionState,
        });
        typing.remove();
        if (Object.prototype.hasOwnProperty.call(payload, "action_state")) actionState = payload.action_state;
        setStoredActionState(actionState);
        const answer = payload.answer || "مورد انتخاب شد.";
        addMessage(messages, "assistant", answer, { root, operational: payload });
        history.push({ role: "assistant", content: answer });
      } catch (error) {
        typing.remove();
        addMessage(messages, "assistant", lumiRequestError(error, "انتخاب انجام نشد. دوباره تلاش کن."), { root, error: true });
      } finally {
        choiceButton.disabled = false;
        setInteractionBusy(false);
      }
      return;
    }

    const confirmActionButton = event.target.closest("[data-lumi-confirm]");
    if (confirmActionButton && root.contains(confirmActionButton) && !interactionBusy) {
      confirmActionButton.disabled = true;
      setInteractionBusy(true);
      const typing = addMessage(messages, "assistant", "", { temporary: true });
      try {
        let payload = await sendAssistantAction(root, {
          command: "execute",
          confirmationToken: confirmActionButton.dataset.lumiConfirm || "",
          actionState,
        });
        typing.remove();
        if (Object.prototype.hasOwnProperty.call(payload, "action_state")) actionState = payload.action_state;
        setStoredActionState(actionState);

        if (payload.kind === "action_form_submit") {
          submitOperationalForm(root, payload);
          return;
        }
        if (payload.kind === "action_remote_post") {
          const progress = addMessage(messages, "assistant", "", { temporary: true });
          try {
            payload = await postOperationalEndpoint(root, payload);
          } finally {
            progress.remove();
          }
          actionState = null;
          setStoredActionState(null);
        }

        const answer = payload.answer || "عملیات انجام شد.";
        addMessage(messages, "assistant", answer, { root, operational: payload });
        history.push({ role: "assistant", content: answer });
        handoffBox.hidden = true;
      } catch (error) {
        typing.remove();
        addMessage(messages, "assistant", lumiRequestError(error, "عملیات انجام نشد. دوباره تلاش کن."), { root, error: true });
      } finally {
        confirmActionButton.disabled = false;
        setInteractionBusy(false);
      }
      return;
    }

    const cancelActionButton = event.target.closest("[data-lumi-action-cancel]");
    if (cancelActionButton && root.contains(cancelActionButton)) {
      actionState = null;
      setStoredActionState(null);
      const card = cancelActionButton.closest(".lm-help-assistant__operation");
      if (card) card.remove();
      addMessage(messages, "assistant", "باشه، این عملیات رو انجام نمی‌دم.", { root });
      return;
    }

    const salonButton = event.target.closest("[data-lumi-book-salon]");
    if (salonButton && root.contains(salonButton) && !interactionBusy) {
      salonButton.disabled = true;
      setInteractionBusy(true);
      bookingContext.stylist = "";
      const selectedSalonName = salonButton.closest(".lm-help-assistant__discovery-result")
        ?.querySelector(".lm-help-assistant__discovery-result-copy strong")?.textContent?.trim() || "";
      if (selectedSalonName) bookingContext.salon = selectedSalonName;
      const typing = addMessage(messages, "assistant", "", { temporary: true });
      try {
        const payload = await sendCustomerBooking(root, "select_salon", actionState, {
          salon_id: salonButton.dataset.lumiBookSalon,
          catalog_service_id: salonButton.dataset.lumiCatalogService,
          discovery_state: actionState || null,
        });
        typing.remove();
        if (Object.prototype.hasOwnProperty.call(payload, "action_state")) actionState = payload.action_state;
        setStoredActionState(actionState);
        const bookingPayload = updateBookingContext(payload, { salon: selectedSalonName });
        addMessage(messages, "assistant", payload.answer || "متخصص‌ها آماده‌اند.", { root, booking: bookingPayload });
        history.push({ role: "assistant", content: payload.answer || "متخصص‌ها آماده‌اند." });
      } catch (error) {
        typing.remove();
        addMessage(messages, "assistant", lumiRequestError(error, "نتونستم متخصص‌ها رو دریافت کنم."), { root, error: true });
      } finally {
        salonButton.disabled = false;
        setInteractionBusy(false);
      }
      return;
    }

    const stylistButton = event.target.closest("[data-lumi-book-stylist]");
    if (stylistButton && root.contains(stylistButton) && !interactionBusy) {
      stylistButton.disabled = true;
      setInteractionBusy(true);
      const selectedStylistName = stylistButton
        .querySelector(".lm-help-assistant__booking-provider-copy strong")?.textContent?.trim() || "";
      if (selectedStylistName) bookingContext.stylist = selectedStylistName;
      const typing = addMessage(messages, "assistant", "", { temporary: true });
      try {
        const payload = await sendCustomerBooking(root, "select_stylist", actionState, {
          stylist_id: stylistButton.dataset.lumiBookStylist,
        });
        typing.remove();
        if (Object.prototype.hasOwnProperty.call(payload, "action_state")) actionState = payload.action_state;
        setStoredActionState(actionState);
        const bookingPayload = updateBookingContext(payload, { stylist: selectedStylistName });
        addMessage(messages, "assistant", payload.answer || "زمان‌های آزاد آماده‌اند.", { root, booking: bookingPayload });
        history.push({ role: "assistant", content: payload.answer || "زمان‌های آزاد آماده‌اند." });
      } catch (error) {
        typing.remove();
        addMessage(messages, "assistant", lumiRequestError(error, "نتونستم زمان‌های آزاد رو دریافت کنم."), { root, error: true });
      } finally {
        stylistButton.disabled = false;
        setInteractionBusy(false);
      }
      return;
    }

    const slotButton = event.target.closest("[data-lumi-book-slot]");
    if (slotButton && root.contains(slotButton) && !interactionBusy) {
      slotButton.disabled = true;
      setInteractionBusy(true);
      const typing = addMessage(messages, "assistant", "", { temporary: true });
      try {
        const payload = await sendCustomerBooking(root, "select_slot", actionState, {
          date: slotButton.dataset.date,
          time: slotButton.dataset.time,
        });
        typing.remove();
        if (Object.prototype.hasOwnProperty.call(payload, "action_state")) actionState = payload.action_state;
        setStoredActionState(actionState);
        const bookingPayload = updateBookingContext(payload);
        addMessage(messages, "assistant", payload.answer || "جزئیات رزرو آماده است.", { root, booking: bookingPayload });
        history.push({ role: "assistant", content: payload.answer || "جزئیات رزرو آماده است." });
      } catch (error) {
        typing.remove();
        addMessage(messages, "assistant", lumiRequestError(error, "این زمان دیگه قابل رزرو نیست."), { root, error: true });
      } finally {
        slotButton.disabled = false;
        setInteractionBusy(false);
      }
      return;
    }

    const relaxButton = event.target.closest("[data-lumi-relax-slots]");
    if (relaxButton && root.contains(relaxButton) && !interactionBusy) {
      relaxButton.disabled = true;
      setInteractionBusy(true);
      const typing = addMessage(messages, "assistant", "", { temporary: true });
      try {
        const payload = await sendCustomerBooking(root, "relax_slots", actionState, {});
        typing.remove();
        if (Object.prototype.hasOwnProperty.call(payload, "action_state")) actionState = payload.action_state;
        setStoredActionState(actionState);
        const bookingPayload = updateBookingContext(payload);
        addMessage(messages, "assistant", payload.answer || "نزدیک‌ترین زمان‌ها رو پیدا کردم.", { root, booking: bookingPayload });
      } catch (error) {
        typing.remove();
        addMessage(messages, "assistant", lumiRequestError(error, "زمان دیگری پیدا نشد."), { root, error: true });
      } finally {
        relaxButton.disabled = false;
        setInteractionBusy(false);
      }
      return;
    }

    const backButton = event.target.closest("[data-lumi-booking-back]");
    if (backButton && root.contains(backButton) && !interactionBusy) {
      setInteractionBusy(true);
      bookingContext.stylist = "";
      const typing = addMessage(messages, "assistant", "", { temporary: true });
      try {
        const payload = await sendCustomerBooking(root, "select_salon", actionState, {
          salon_id: actionState?.salon_id,
          catalog_service_id: actionState?.catalog_service_id,
          discovery_state: actionState || null,
        });
        typing.remove();
        if (Object.prototype.hasOwnProperty.call(payload, "action_state")) actionState = payload.action_state;
        setStoredActionState(actionState);
        const bookingPayload = updateBookingContext(payload);
        addMessage(messages, "assistant", "متخصص دیگه‌ای انتخاب کن.", { root, booking: bookingPayload });
      } catch (error) {
        typing.remove();
        addMessage(messages, "assistant", lumiRequestError(error, "نتونستم فهرست متخصص‌ها رو تازه کنم."), { root, error: true });
      } finally {
        setInteractionBusy(false);
      }
      return;
    }

    const cancelBookingButton = event.target.closest("[data-lumi-booking-cancel]");
    if (cancelBookingButton && root.contains(cancelBookingButton) && !interactionBusy) {
      setInteractionBusy(true);
      try {
        const payload = await sendCustomerBooking(root, "cancel", actionState, {});
        actionState = null;
        bookingContext = { salon: "", service: "", stylist: "" };
        setStoredActionState(null);
        addMessage(messages, "assistant", payload.answer || "رزرو لغو شد.", { root });
      } catch (error) {
        addMessage(messages, "assistant", lumiRequestError(error, "نتونستم فرایند رو پاک کنم."), { root, error: true });
      } finally {
        setInteractionBusy(false);
      }
      return;
    }

    const checkoutButton = event.target.closest("[data-lumi-checkout]");
    if (checkoutButton && root.contains(checkoutButton) && !interactionBusy) {
      checkoutButton.disabled = true;
      setInteractionBusy(true);
      const originalCheckout = checkoutButton.innerHTML;
      checkoutButton.innerHTML = '<span>در حال بررسی نهایی…</span><i class="fa-solid fa-spinner fa-spin" aria-hidden="true"></i>';
      try {
        submitExistingCheckout(root, checkoutButton.dataset.checkoutUrl, checkoutButton.dataset.lumiCheckout);
      } catch (error) {
        checkoutButton.disabled = false;
        checkoutButton.innerHTML = originalCheckout;
        setInteractionBusy(false);
        addMessage(messages, "assistant", lumiRequestError(error, "نتونستم رزرو رو برای پرداخت ادامه بدم."), { root, error: true });
      }
      return;
    }

    const locationButton = event.target.closest("[data-lumi-location]");
    if (!locationButton || !root.contains(locationButton) || interactionBusy) return;

    locationButton.disabled = true;
    setInteractionBusy(true);
    const original = locationButton.innerHTML;
    locationButton.innerHTML = '<span><i class="fa-solid fa-spinner fa-spin"></i> دریافت موقعیت…</span>';
    try {
      const coordinates = await requestBrowserLocation();
      actionCoordinates = coordinates;
      const typing = addMessage(messages, "assistant", "", { temporary: true });
      const payload = await sendCustomerDiscovery(
        root,
        "از موقعیت من استفاده کن",
        actionState,
        coordinates
      );
      typing.remove();
      if (!payload.handled) throw new Error("discovery");
      if (Object.prototype.hasOwnProperty.call(payload, "action_state")) {
        actionState = payload.action_state;
      }
      setStoredActionState(actionState);
      addMessage(messages, "assistant", payload.answer || "نتیجه جستجو آماده است.", {
        root,
        discovery: payload,
      });
      history.push({ role: "assistant", content: payload.answer || "نتیجه جستجو آماده است." });
      handoffBox.hidden = true;
    } catch (error) {
      addMessage(messages, "assistant", lumiRequestError(error, "نتونستم موقعیت رو دریافت کنم. نام محله رو بنویس."), { root, error: true });
    } finally {
      locationButton.disabled = false;
      locationButton.innerHTML = original;
      setInteractionBusy(false);
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = input.value.trim();
    if (!text || interactionBusy) return;

    const retryMessage = String(form.dataset.lumiRetryMessage || "").trim();
    const isRetry = Boolean(retryMessage && retryMessage === text);
    delete form.dataset.lumiRetryMessage;

    welcome.hidden = true;
    if (!isRetry) {
      addMessage(messages, "user", text);
      history.push({ role: "user", content: text });
    }

    input.value = "";
    autoGrow(input);
    setInteractionBusy(true);
    const typing = addMessage(messages, "assistant", "", { temporary: true });

    try {
      const operationalPayload = await sendAssistantAction(root, {
        message: text,
        actionState,
        command: "message",
      });
      if (operationalPayload?.handled) {
        typing.remove();
        if (Object.prototype.hasOwnProperty.call(operationalPayload, "action_state")) {
          actionState = operationalPayload.action_state;
        }
        setStoredActionState(actionState);
        const operationalAnswer = operationalPayload.answer || "آماده است.";
        addMessage(messages, "assistant", operationalAnswer, {
          root,
          operational: operationalPayload,
        });
        history.push({ role: "assistant", content: operationalAnswer });
        handoffBox.hidden = true;
        return;
      }

      const actionPayload = await sendCustomerDiscovery(root, text, actionState, actionCoordinates);
      if (actionPayload?.handled) {
        typing.remove();
        if (Object.prototype.hasOwnProperty.call(actionPayload, "action_state")) {
          actionState = actionPayload.action_state;
        }
        setStoredActionState(actionState);
        const actionAnswer = actionPayload.answer || "نتیجه جستجو آماده است.";

        if (actionPayload.booking_request) {
          const bookingPayload = await sendCustomerBooking(root, "select_salon", actionState, {
            salon_id: actionPayload.booking_request.salon_id,
            catalog_service_id: actionPayload.booking_request.catalog_service_id,
            discovery_state: actionState || null,
          });
          if (Object.prototype.hasOwnProperty.call(bookingPayload, "action_state")) actionState = bookingPayload.action_state;
          setStoredActionState(actionState);
          const bookingAnswer = bookingPayload.answer || actionAnswer;
          const bookingView = updateBookingContext(bookingPayload);
          addMessage(messages, "assistant", bookingAnswer, { root, booking: bookingView });
          history.push({ role: "assistant", content: bookingAnswer });
          handoffBox.hidden = true;
          return;
        }

        addMessage(messages, "assistant", actionAnswer, {
          root,
          discovery: actionPayload,
        });
        history.push({ role: "assistant", content: actionAnswer });
        handoffBox.hidden = true;
        return;
      }

      const payload = await sendChat(root, text, history, conversationId);
      typing.remove();

      conversationId = payload.conversation_id || conversationId;
      setStoredConversationId(conversationId);

      const answer = payload.answer || "الان جواب قابل اتکایی پیدا نکردم.";
      addMessage(messages, "assistant", answer, {
        root,
        messageId: payload.assistant_message_id,
        sources: payload.sources || [],
        guide: payload.guide || null,
      });
      history.push({ role: "assistant", content: answer });
      const hasGroundedHelp = Boolean((payload.sources || []).length || payload.guide);
      handoffBox.hidden = hasGroundedHelp;
    } catch (error) {
      typing.remove();
      const fallback = "الان نتونستم پاسخ رو دریافت کنم. دوباره امتحان کن؛ اگر ادامه داشت، همین گفتگو رو برای پشتیبانی بفرست.";
      const message = error?.message === "chat"
        ? fallback
        : lumiRequestError(error, fallback);
      addMessage(
        messages,
        "assistant",
        message,
        { root, error: true, retryMessage: text }
      );
      handoffBox.hidden = false;
    } finally {
      setInteractionBusy(false);
      focusInputWhenAppropriate();
    }
  });

  escalate?.addEventListener("click", async () => {
    if (interactionBusy) return;
    if (!conversationId) {
      const supportUrl = safeHttpUrl(root.dataset.supportUrl, { sameOrigin: true });
      if (supportUrl) window.location.href = supportUrl;
      return;
    }

    escalate.disabled = true;
    const original = escalate.innerHTML;
    escalate.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> در حال ارجاع…';

    try {
      const response = await fetch(root.dataset.handoffUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken(root),
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({ conversation_id: conversationId }),
      });
      const payload = await response.json().catch(() => ({}));

      const ticketUrl = safeHttpUrl(payload.ticket_url, { sameOrigin: true });
      if (response.ok && ticketUrl) {
        addMessage(
          messages,
          "assistant",
          "برای پشتیبانی ارسال شد؛ صفحه پیگیری باز می‌شود.",
          { root }
        );
        setTimeout(() => { window.location.href = ticketUrl; }, 650);
        return;
      }

      const supportUrl = safeHttpUrl(payload.support_url, { sameOrigin: true });
      if (supportUrl) {
        addMessage(
          messages,
          "assistant",
          payload.error || "برای ادامه، فرم پشتیبانی رو باز می‌کنم.",
          { root }
        );
        setTimeout(() => { window.location.href = supportUrl; }, 850);
        return;
      }

      throw new Error(payload.error || "ارجاع گفتگو انجام نشد.");
    } catch (error) {
      addMessage(messages, "assistant", lumiRequestError(error, "ارجاع گفتگو انجام نشد."), { root, error: true });
    } finally {
      escalate.disabled = false;
      escalate.innerHTML = original;
    }
  });

  document.addEventListener("loomera:help:ask", async (event) => {
    localStorage.removeItem("loomera.help-assistant.hidden");
    root.hidden = false;
    await openPanel();
    const question = String(event.detail?.message || "").trim();
    if (question) {
      input.value = question;
      autoGrow(input);
    }
    focusInputWhenAppropriate();
  });

  document.addEventListener("keydown", (event) => {
    if (panel.hidden) return;

    if (newChatConfirm && !newChatConfirm.hidden) {
      if (event.key === "Escape") {
        event.preventDefault();
        closeNewChatConfirm();
        return;
      }
      if (event.key === "Tab") {
        const focusable = confirmFocusableElements();
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        const active = document.activeElement;
        if (event.shiftKey && (active === first || !newChatConfirm.contains(active))) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && active === last) {
          event.preventDefault();
          first.focus();
        }
        return;
      }
    }

    if (event.key === "Escape") {
      event.preventDefault();
      closePanel();
      return;
    }

    if (event.key === "Tab" && matchMedia("(max-width:767px)").matches) {
      const focusable = panelFocusableElements();
      if (!focusable.length) {
        event.preventDefault();
        (close || newChat || fab)?.focus?.();
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;

      if (event.shiftKey && (active === first || !panel.contains(active))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    }
  });

  window.addEventListener("resize", () => {
    applyPosition(root, fab);
    updateDialogMode();
    if (!matchMedia("(max-width:767px)").matches) {
      document.body.classList.remove("lm-help-assistant-open");
    } else if (!panel.hidden) {
      document.body.classList.add("lm-help-assistant-open");
    }
  });
  loadContext();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init, { once: true });
} else {
  init();
}
