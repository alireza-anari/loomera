const ROOT_SELECTOR = "[data-help-assistant]";
const CONVERSATION_STORAGE_KEY = "loomera.help-assistant.conversation.v3";
const ACTION_STORAGE_KEY = "loomera.help-assistant.action-state.v1";

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

function positionKey() {
  return `loomera.help-assistant.position.${matchMedia("(max-width:767px)").matches ? "mobile" : "desktop"}`;
}

function applyPosition(root) {
  if (matchMedia("(max-width:767px)").matches) {
    root.style.left = "";
    root.style.top = "";
    root.style.right = "";
    root.style.bottom = "";
    return;
  }

  let saved = null;
  try { saved = JSON.parse(localStorage.getItem(positionKey()) || "null"); } catch (_) {}
  if (!saved) return;

  const size = root.offsetWidth || 60;
  const left = saved.side === "right" ? window.innerWidth - size - 20 : 20;
  const minY = 72;
  const maxY = Math.max(minY, window.innerHeight - size - 20);
  const top = minY + Math.max(0, Math.min(1, Number(saved.ratio) || 0)) * (maxY - minY);

  root.style.left = `${left}px`;
  root.style.top = `${top}px`;
  root.style.right = "auto";
  root.style.bottom = "auto";
}

function savePosition(root) {
  if (matchMedia("(max-width:767px)").matches) return;
  const rect = root.getBoundingClientRect();
  const side = rect.left + rect.width / 2 < window.innerWidth / 2 ? "left" : "right";
  const minY = 72;
  const maxY = Math.max(minY + 1, window.innerHeight - rect.height - 20);
  const ratio = (Math.max(minY, Math.min(maxY, rect.top)) - minY) / Math.max(1, maxY - minY);
  try { localStorage.setItem(positionKey(), JSON.stringify({ side, ratio })); } catch (_) {}
}

function bindDrag(root, fab) {
  if (matchMedia("(max-width:767px)").matches) return;

  let pointer = null;
  let startX = 0, startY = 0, startLeft = 0, startTop = 0;
  let dragging = false, suppress = false;

  fab.addEventListener("pointerdown", (event) => {
    if (event.button !== undefined && event.button !== 0) return;
    pointer = event.pointerId;
    const rect = root.getBoundingClientRect();
    startX = event.clientX;
    startY = event.clientY;
    startLeft = rect.left;
    startTop = rect.top;
    dragging = false;
    try { fab.setPointerCapture(pointer); } catch (_) {}
  });

  fab.addEventListener("pointermove", (event) => {
    if (pointer === null || event.pointerId !== pointer) return;
    const dx = event.clientX - startX;
    const dy = event.clientY - startY;
    if (!dragging && Math.hypot(dx, dy) < 7) return;
    dragging = true;

    const size = root.offsetWidth || 60;
    root.style.left = `${Math.max(10, Math.min(window.innerWidth - size - 10, startLeft + dx))}px`;
    root.style.top = `${Math.max(70, Math.min(window.innerHeight - size - 10, startTop + dy))}px`;
    root.style.bottom = "auto";
    root.style.right = "auto";
  });

  const finish = (event) => {
    if (pointer === null || event.pointerId !== pointer) return;
    if (dragging) {
      const rect = root.getBoundingClientRect();
      const right = rect.left + rect.width / 2 >= window.innerWidth / 2;
      const size = root.offsetWidth || 60;
      root.style.left = `${right ? window.innerWidth - size - 20 : 20}px`;
      savePosition(root);
      suppress = true;
      setTimeout(() => { suppress = false; }, 120);
    }
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
    if (source?.url) {
      const citation = document.createElement("a");
      citation.className = "lm-help-assistant__citation";
      citation.href = source.url;
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

    const heading = document.createElement(step.url ? "a" : "strong");
    heading.className = "lm-help-assistant__flow-title";
    heading.textContent = step.title || `مرحله ${index + 1}`;
    if (step.url) heading.href = step.url;
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

    if (step.url && step.link_label) {
      const action = document.createElement("a");
      action.href = step.url;
      action.className = "lm-help-assistant__flow-action";
      action.innerHTML = `<span>${step.link_label}</span><i class="fa-solid fa-arrow-up-left-from-square" aria-hidden="true"></i>`;
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
  row.appendChild(label);

  [
    ["helpful", "fa-regular fa-thumbs-up", "بله، مفید بود"],
    ["not_helpful", "fa-regular fa-thumbs-down", "نه، مفید نبود"],
  ].forEach(([rating, icon, aria]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.rating = rating;
    button.setAttribute("aria-label", aria);
    button.innerHTML = `<i class="${icon}" aria-hidden="true"></i>`;
    row.appendChild(button);
  });

  row.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", async () => {
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

        row.querySelectorAll("button").forEach((item) => item.classList.remove("is-selected"));
        button.classList.add("is-selected");
        label.textContent = "ثبت شد";

        const handoff = root.querySelector("[data-help-handoff-box]");
        if (handoff) {
          handoff.hidden = button.dataset.rating !== "not_helpful";
        }
      } catch (_) {
        label.textContent = "ثبت بازخورد انجام نشد";
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
    const link = document.createElement("a");
    link.href = source.url;
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

      if (result.image_url) {
        const image = document.createElement("img");
        image.className = "lm-help-assistant__discovery-image";
        image.src = result.image_url;
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
        price.innerHTML = `<i class="fa-solid fa-wallet" aria-hidden="true"></i> از ${formatToman(result.price)}`;
        meta.appendChild(price);
      }
      if (result.distance_km !== null && result.distance_km !== undefined) {
        const distance = document.createElement("span");
        distance.innerHTML = `<i class="fa-solid fa-location-dot" aria-hidden="true"></i> ${result.distance_km} کیلومتر`;
        meta.appendChild(distance);
      }
      if (Number(result.rating) > 0) {
        const rating = document.createElement("span");
        rating.innerHTML = `<i class="fa-solid fa-star" aria-hidden="true"></i> ${result.rating}`;
        meta.appendChild(rating);
      }
      if (result.availability) {
        const availability = document.createElement("span");
        availability.className = "lm-help-assistant__discovery-availability";
        availability.innerHTML = `<i class="fa-regular fa-clock" aria-hidden="true"></i> ${result.availability}`;
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
      if (result.url) {
        const detail = document.createElement("a");
        detail.className = "lm-help-assistant__discovery-result-detail";
        detail.href = result.url;
        detail.textContent = "مشاهده صفحه مجموعه";
        item.appendChild(detail);
      }
      list.appendChild(item);
    });
    card.appendChild(list);
  }

  if (payload.search_url) {
    const all = document.createElement("a");
    all.className = "lm-help-assistant__discovery-all";
    all.href = payload.search_url;
    all.innerHTML = `<span>${payload.search_label || "مشاهده همه نتایج"}</span><i class="fa-solid fa-arrow-up-left-from-square" aria-hidden="true"></i>`;
    card.appendChild(all);
  }

  return card.childElementCount ? card : null;
}


function bookingCard(payload = {}) {
  if (!payload?.handled || !String(payload.kind || "").startsWith("booking_")) return null;

  const card = document.createElement("section");
  card.className = "lm-help-assistant__booking";
  card.setAttribute("aria-label", "رزرو با لومی");

  if (payload.kind === "booking_auth_required" && payload.login_url) {
    const login = document.createElement("a");
    login.className = "lm-help-assistant__booking-primary";
    login.href = payload.login_url;
    login.innerHTML = '<span>ورود به حساب مشتری</span><i class="fa-solid fa-arrow-left-to-bracket" aria-hidden="true"></i>';
    card.appendChild(login);
    return card;
  }

  if (payload.kind === "booking_stylists" && Array.isArray(payload.providers)) {
    const header = document.createElement("div");
    header.className = "lm-help-assistant__booking-context";
    header.innerHTML = `<strong>${payload.service?.name || "خدمت"}</strong><span>${payload.salon?.name || ""}</span>`;
    card.appendChild(header);

    const list = document.createElement("div");
    list.className = "lm-help-assistant__booking-providers";
    payload.providers.forEach((provider) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "lm-help-assistant__booking-provider";
      button.dataset.lumiBookStylist = String(provider.id || "");
      const avatar = provider.image_url
        ? `<img src="${provider.image_url}" alt="" loading="lazy">`
        : '<span class="lm-help-assistant__booking-provider-avatar"><i class="fa-solid fa-user"></i></span>';
      const when = provider.next_date_label && provider.next_time
        ? `نزدیک‌ترین وقت: ${provider.next_date_label} · ${provider.next_time}`
        : "وقت قابل رزرو";
      button.innerHTML = `
        ${avatar}
        <span class="lm-help-assistant__booking-provider-copy">
          <strong>${provider.name || "متخصص"}</strong>
          <small>${when}</small>
          ${Number(provider.price) > 0 ? `<em>${formatToman(provider.price)}</em>` : ""}
        </span>
        <i class="fa-solid fa-chevron-left" aria-hidden="true"></i>
      `;
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
      button.innerHTML = `<span>${label}</span><i class="fa-solid fa-check" aria-hidden="true"></i>`;
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

function addMessage(container, role, text, options = {}) {
  const row = document.createElement("div");
  row.className = `lm-help-assistant__message lm-help-assistant__message--${role}`;
  if (options.temporary) row.dataset.temporary = "1";

  if (role === "assistant" && !options.temporary) {
    const avatar = document.createElement("span");
    avatar.className = "lm-help-assistant__message-avatar";
    avatar.setAttribute("aria-hidden", "true");
    avatar.innerHTML = '<i class="fa-solid fa-sparkles"></i>';
    row.appendChild(avatar);
  }

  const stack = document.createElement("div");
  stack.className = "lm-help-assistant__message-stack";

  const bubble = document.createElement("div");
  bubble.className = "lm-help-assistant__bubble";

  if (options.temporary) {
    const typing = document.createElement("div");
    typing.className = "lm-help-assistant__typing-wrap";
    typing.setAttribute("aria-label", "در حال آماده‌سازی پاسخ");
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

  if (role === "assistant" && !options.temporary) {
    const guide = guideCard(guideFromOptions(options));
    if (guide) stack.appendChild(guide);

    const discovery = discoveryCard(options.discovery || null);
    if (discovery) stack.appendChild(discovery);

    const booking = bookingCard(options.booking || null);
    if (booking) stack.appendChild(booking);

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

  const response = await fetch(root.dataset.customerDiscoveryUrl, {
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
  if (!response.ok) throw new Error(payload.error || "discovery");
  return payload;
}


async function sendCustomerBooking(root, action, actionState, extra = {}) {
  if (!root.dataset.customerBookingUrl) throw new Error("مسیر رزرو لومی در دسترس نیست.");
  const response = await fetch(root.dataset.customerBookingUrl, {
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
  if (!response.ok) throw new Error(payload.error || "رزرو انجام نشد.");
  return payload;
}

function submitExistingCheckout(root, url, paymentMethod) {
  if (!url || !paymentMethod) throw new Error("اطلاعات تأیید رزرو ناقص است.");
  const form = document.createElement("form");
  form.method = "post";
  form.action = url;
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
  const response = await fetch(root.dataset.chatUrl, {
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
  if (!response.ok) throw new Error(payload.error || "chat");
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

  let contextLoaded = false;
  let conversationHydrated = false;
  let history = [];
  let context = null;
  let conversationId = getStoredConversationId();
  let actionState = getStoredActionState();
  let actionCoordinates = null;

  applyPosition(root);
  bindDrag(root, fab);

  function resetConversationUi() {
    history = [];
    conversationId = null;
    setStoredConversationId(null);
    actionState = null;
    actionCoordinates = null;
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
    }
  }

  async function openPanel() {
    panel.hidden = false;
    if (matchMedia("(max-width:767px)").matches) {
      document.body.classList.add("lm-help-assistant-open");
    }
    fab.setAttribute("aria-expanded", "true");
    await Promise.all([loadContext(), hydrateConversation()]);

    if (context?.page_key) {
      localStorage.setItem(`loomera.help-assistant.seen.${context.page_key}.v3`, "1");
      dot.hidden = true;
    }

    setTimeout(() => input.focus(), 80);
  }

  function closePanel() {
    panel.hidden = true;
    fab.setAttribute("aria-expanded", "false");
    document.body.classList.remove("lm-help-assistant-open");
  }

  fab.addEventListener("click", () => panel.hidden ? openPanel() : closePanel());
  close?.addEventListener("click", closePanel);

  newChat?.addEventListener("click", () => {
    if (history.length && !window.confirm("گفتگوی جدید شروع بشه؟ گفتگوی فعلی در سوابق پشتیبانی باقی می‌مونه.")) {
      return;
    }
    resetConversationUi();
    input.focus();
  });

  input.addEventListener("input", () => autoGrow(input));
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  root.addEventListener("click", async (event) => {
    const messageButton = event.target.closest("[data-lumi-message]");
    if (messageButton && root.contains(messageButton)) {
      input.value = messageButton.dataset.lumiMessage || "";
      autoGrow(input);
      form.requestSubmit();
      return;
    }

    const salonButton = event.target.closest("[data-lumi-book-salon]");
    if (salonButton && root.contains(salonButton) && !send.disabled) {
      salonButton.disabled = true;
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
        addMessage(messages, "assistant", payload.answer || "متخصص‌ها آماده‌اند.", { root, booking: payload });
        history.push({ role: "assistant", content: payload.answer || "متخصص‌ها آماده‌اند." });
      } catch (error) {
        typing.remove();
        addMessage(messages, "assistant", error.message || "نتونستم متخصص‌ها رو دریافت کنم.", { root });
      } finally {
        salonButton.disabled = false;
      }
      return;
    }

    const stylistButton = event.target.closest("[data-lumi-book-stylist]");
    if (stylistButton && root.contains(stylistButton) && !send.disabled) {
      stylistButton.disabled = true;
      const typing = addMessage(messages, "assistant", "", { temporary: true });
      try {
        const payload = await sendCustomerBooking(root, "select_stylist", actionState, {
          stylist_id: stylistButton.dataset.lumiBookStylist,
        });
        typing.remove();
        if (Object.prototype.hasOwnProperty.call(payload, "action_state")) actionState = payload.action_state;
        setStoredActionState(actionState);
        addMessage(messages, "assistant", payload.answer || "زمان‌های آزاد آماده‌اند.", { root, booking: payload });
        history.push({ role: "assistant", content: payload.answer || "زمان‌های آزاد آماده‌اند." });
      } catch (error) {
        typing.remove();
        addMessage(messages, "assistant", error.message || "نتونستم زمان‌های آزاد رو دریافت کنم.", { root });
      } finally {
        stylistButton.disabled = false;
      }
      return;
    }

    const slotButton = event.target.closest("[data-lumi-book-slot]");
    if (slotButton && root.contains(slotButton) && !send.disabled) {
      slotButton.disabled = true;
      const typing = addMessage(messages, "assistant", "", { temporary: true });
      try {
        const payload = await sendCustomerBooking(root, "select_slot", actionState, {
          date: slotButton.dataset.date,
          time: slotButton.dataset.time,
        });
        typing.remove();
        if (Object.prototype.hasOwnProperty.call(payload, "action_state")) actionState = payload.action_state;
        setStoredActionState(actionState);
        addMessage(messages, "assistant", payload.answer || "جزئیات رزرو آماده است.", { root, booking: payload });
        history.push({ role: "assistant", content: payload.answer || "جزئیات رزرو آماده است." });
      } catch (error) {
        typing.remove();
        addMessage(messages, "assistant", error.message || "این زمان دیگه قابل رزرو نیست.", { root });
      } finally {
        slotButton.disabled = false;
      }
      return;
    }

    const relaxButton = event.target.closest("[data-lumi-relax-slots]");
    if (relaxButton && root.contains(relaxButton) && !send.disabled) {
      relaxButton.disabled = true;
      const typing = addMessage(messages, "assistant", "", { temporary: true });
      try {
        const payload = await sendCustomerBooking(root, "relax_slots", actionState, {});
        typing.remove();
        if (Object.prototype.hasOwnProperty.call(payload, "action_state")) actionState = payload.action_state;
        setStoredActionState(actionState);
        addMessage(messages, "assistant", payload.answer || "نزدیک‌ترین زمان‌ها رو پیدا کردم.", { root, booking: payload });
      } catch (error) {
        typing.remove();
        addMessage(messages, "assistant", error.message || "زمان دیگری پیدا نشد.", { root });
      } finally {
        relaxButton.disabled = false;
      }
      return;
    }

    const backButton = event.target.closest("[data-lumi-booking-back]");
    if (backButton && root.contains(backButton) && !send.disabled) {
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
        addMessage(messages, "assistant", "متخصص دیگه‌ای انتخاب کن.", { root, booking: payload });
      } catch (error) {
        typing.remove();
        addMessage(messages, "assistant", error.message || "نتونستم فهرست متخصص‌ها رو تازه کنم.", { root });
      }
      return;
    }

    const cancelBookingButton = event.target.closest("[data-lumi-booking-cancel]");
    if (cancelBookingButton && root.contains(cancelBookingButton) && !send.disabled) {
      try {
        const payload = await sendCustomerBooking(root, "cancel", actionState, {});
        actionState = null;
        setStoredActionState(null);
        addMessage(messages, "assistant", payload.answer || "رزرو لغو شد.", { root });
      } catch (error) {
        addMessage(messages, "assistant", error.message || "نتونستم فرایند رو پاک کنم.", { root });
      }
      return;
    }

    const checkoutButton = event.target.closest("[data-lumi-checkout]");
    if (checkoutButton && root.contains(checkoutButton) && !send.disabled) {
      checkoutButton.disabled = true;
      checkoutButton.innerHTML = '<span>در حال بررسی نهایی…</span><i class="fa-solid fa-spinner fa-spin" aria-hidden="true"></i>';
      submitExistingCheckout(root, checkoutButton.dataset.checkoutUrl, checkoutButton.dataset.lumiCheckout);
      return;
    }

    const locationButton = event.target.closest("[data-lumi-location]");
    if (!locationButton || !root.contains(locationButton) || send.disabled) return;

    locationButton.disabled = true;
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
      addMessage(messages, "assistant", error.message || "نتونستم موقعیت رو دریافت کنم. نام محله رو بنویس.", { root });
    } finally {
      locationButton.disabled = false;
      locationButton.innerHTML = original;
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = input.value.trim();
    if (!text || send.disabled) return;

    welcome.hidden = true;
    addMessage(messages, "user", text);
    history.push({ role: "user", content: text });

    input.value = "";
    autoGrow(input);
    send.disabled = true;
    const typing = addMessage(messages, "assistant", "", { temporary: true });

    try {
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
          addMessage(messages, "assistant", bookingAnswer, { root, booking: bookingPayload });
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
      addMessage(
        messages,
        "assistant",
        error.message && error.message !== "chat"
          ? error.message
          : "الان نتونستم پاسخ رو دریافت کنم. یک‌بار دیگه امتحان کن؛ اگر ادامه داشت، همین گفتگو رو برای پشتیبانی بفرست.",
        { root }
      );
      handoffBox.hidden = false;
    } finally {
      send.disabled = false;
      input.focus();
    }
  });

  escalate?.addEventListener("click", async () => {
    if (!conversationId) {
      window.location.href = root.dataset.supportUrl;
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

      if (response.ok && payload.ticket_url) {
        addMessage(
          messages,
          "assistant",
          "برای پشتیبانی ارسال شد؛ صفحه پیگیری باز می‌شود.",
          { root }
        );
        setTimeout(() => { window.location.href = payload.ticket_url; }, 650);
        return;
      }

      if (payload.support_url) {
        addMessage(
          messages,
          "assistant",
          payload.error || "برای ادامه، فرم پشتیبانی رو باز می‌کنم.",
          { root }
        );
        setTimeout(() => { window.location.href = payload.support_url; }, 850);
        return;
      }

      throw new Error(payload.error || "ارجاع گفتگو انجام نشد.");
    } catch (error) {
      addMessage(messages, "assistant", error.message || "ارجاع گفتگو انجام نشد.", { root });
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
    input.focus();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !panel.hidden) closePanel();
  });

  window.addEventListener("resize", () => {
    applyPosition(root);
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
