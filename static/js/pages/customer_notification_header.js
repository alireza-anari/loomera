function getCsrfToken() {
  const cookie = document.cookie
    .split("; ")
    .find((row) => row.startsWith("csrftoken="));

  return cookie ? decodeURIComponent(cookie.split("=")[1]) : "";
}

function toPersianNumber(value) {
  return String(value ?? 0).replace(/\d/g, (digit) => "۰۱۲۳۴۵۶۷۸۹"[Number(digit)]);
}

function buildReadUrl(template, id) {
  if (!template || !id) return "";
  return template.replace(/\/0\//, `/${id}/`).replace(/\/0$/, `/${id}`);
}

function parseBackendDate(dateString) {
  if (!dateString) return null;

  const value = String(dateString).trim();
  const match = value.match(
    /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?$/
  );

  if (!match) return null;

  const [, year, month, day, hour = "00", minute = "00", second = "00"] = match;

  return new Date(
    Number(year),
    Number(month) - 1,
    Number(day),
    Number(hour),
    Number(minute),
    Number(second)
  );
}

function formatJalaliDate(dateString) {
  const date = parseBackendDate(dateString);
  if (!date || Number.isNaN(date.getTime())) {
    return dateString || "";
  }

  try {
    return new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    })
      .format(date)
      .replace("،", " - ");
  } catch (error) {
    return dateString || "";
  }
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    credentials: "same-origin",
    headers: {
      "X-Requested-With": "XMLHttpRequest",
      ...(options.headers || {}),
    },
    ...options,
  });

  let payload = {};
  try {
    payload = await response.json();
  } catch (error) {
    payload = {};
  }

  if (!response.ok) {
    throw new Error(payload.error || "request_failed");
  }

  return payload;
}

async function postJson(url) {
  return fetchJson(url, {
    method: "POST",
    headers: {
      "X-CSRFToken": getCsrfToken(),
    },
  });
}

function openMenu(root) {
  const button = root.querySelector("[data-notification-toggle]");
  const menu = root.querySelector("[data-notification-menu]");
  if (!button || !menu) return;

  menu.classList.remove("invisible", "pointer-events-none", "opacity-0");
  menu.classList.add("visible", "pointer-events-auto", "opacity-100");
  button.setAttribute("aria-expanded", "true");
  root.dataset.menuOpen = "true";
}

function closeMenu(root) {
  const button = root.querySelector("[data-notification-toggle]");
  const menu = root.querySelector("[data-notification-menu]");
  if (!button || !menu) return;

  menu.classList.add("invisible", "pointer-events-none", "opacity-0");
  menu.classList.remove("visible", "pointer-events-auto", "opacity-100");
  button.setAttribute("aria-expanded", "false");
  root.dataset.menuOpen = "false";
}

function closeOtherMenus(currentRoot) {
  document.querySelectorAll("[data-customer-notification-root]").forEach((root) => {
    if (root !== currentRoot) closeMenu(root);
  });
}

function syncUnreadCount(count) {
  const safeCount = Math.max(0, Number(count) || 0);

  document.querySelectorAll("[data-notification-badge]").forEach((badge) => {
    badge.textContent = safeCount > 99 ? "+۹۹" : toPersianNumber(safeCount);
    badge.classList.toggle("hidden", safeCount === 0);
    badge.classList.toggle("inline-flex", safeCount > 0);
  });

  document.querySelectorAll("[data-notification-unread-text]").forEach((element) => {
    element.textContent = toPersianNumber(safeCount);
  });

  document.querySelectorAll("[data-notification-read-all]").forEach((button) => {
    button.disabled = safeCount === 0;
  });
}

function setRootState(root, state) {
  const loading = root.querySelector("[data-notification-loading]");
  const empty = root.querySelector("[data-notification-empty]");
  const error = root.querySelector("[data-notification-error]");

  if (loading) loading.classList.toggle("hidden", state !== "loading");
  if (empty) empty.classList.toggle("hidden", state !== "empty");
  if (error) error.classList.toggle("hidden", state !== "error");
}

function setActiveTab(root, tabValue) {
  const nextTab = tabValue || "all";
  root.dataset.activeTab = nextTab;

  root.querySelectorAll("[data-notification-tab]").forEach((button) => {
    const isActive = button.dataset.notificationTab === nextTab;

    button.classList.toggle("border-slate-900", isActive);
    button.classList.toggle("bg-slate-900", isActive);
    button.classList.toggle("text-white", isActive);

    button.classList.toggle("border-loomera-borderSoft", !isActive);
    button.classList.toggle("bg-white", !isActive);
    button.classList.toggle("text-loomera-textSecondary", !isActive);
  });
}

function filterNotifications(notifications, tabValue) {
  if (!Array.isArray(notifications)) return [];

  if (tabValue === "all") return notifications;
  if (tabValue === "unread") return notifications.filter((item) => !item.is_read);

  return notifications.filter((item) => item.category === tabValue);
}

function getCategoryTone(category, isUnread) {
  const tones = {
    booking: {
      unreadIcon: "bg-emerald-600 text-white",
      readIcon: "bg-emerald-50 text-emerald-700",
      chip: "bg-emerald-50 text-emerald-700",
    },
    payment: {
      unreadIcon: "bg-sky-600 text-white",
      readIcon: "bg-sky-50 text-sky-700",
      chip: "bg-sky-50 text-sky-700",
    },
    wallet: {
      unreadIcon: "bg-amber-500 text-white",
      readIcon: "bg-amber-50 text-amber-700",
      chip: "bg-amber-50 text-amber-700",
    },
    support: {
      unreadIcon: "bg-rose-500 text-white",
      readIcon: "bg-rose-50 text-rose-700",
      chip: "bg-rose-50 text-rose-700",
    },
    system: {
      unreadIcon: "bg-slate-800 text-white",
      readIcon: "bg-slate-100 text-slate-700",
      chip: "bg-slate-100 text-slate-700",
    },
    marketing: {
      unreadIcon: "bg-orange-500 text-white",
      readIcon: "bg-orange-50 text-orange-700",
      chip: "bg-orange-50 text-orange-700",
    },
  };

  const tone = tones[category] || tones.system;

  return {
    icon: isUnread ? tone.unreadIcon : tone.readIcon,
    chip: tone.chip,
  };
}

function createNotificationItem(root, notification) {
  const readTemplate = root.dataset.readUrlTemplate || "";
  const readUrl = buildReadUrl(readTemplate, notification.id);
  const actionUrl = notification.action_url || root.dataset.notificationsUrl || "#";
  const isUnread = !notification.is_read;


  const item = document.createElement("a");
  item.href = actionUrl;
  item.className = [
    "group flex gap-3 rounded-[1.35rem] border p-3.5 text-right transition hover:border-loomera-primary/30 hover:bg-loomera-primarySoft/40 lg:p-4",
    isUnread ? "border-loomera-primary/20 bg-loomera-primarySoft/30" : "border-loomera-borderSoft bg-white",
  ].join(" ");
  item.dataset.notificationItem = "true";
  item.dataset.notificationId = String(notification.id || "");
  item.dataset.readUrl = readUrl;
  item.dataset.isRead = notification.is_read ? "true" : "false";

  const tone = getCategoryTone(notification.category, isUnread);

  const iconWrap = document.createElement("span");
  iconWrap.className = [
    "mt-0.5 inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl text-sm transition",
    tone.icon,
  ].join(" ");

  const icon = document.createElement("i");
  icon.className = notification.icon || "fa-regular fa-bell";
  icon.setAttribute("aria-hidden", "true");
  iconWrap.appendChild(icon);

  const body = document.createElement("span");
  body.className = "min-w-0 flex-1";

  const topRow = document.createElement("span");
  topRow.className = "flex items-start justify-between gap-2";

  const titleBlock = document.createElement("span");
  titleBlock.className = "min-w-0";

  const title = document.createElement("strong");
  title.className = "line-clamp-1 block text-sm font-black text-loomera-textPrimary lg:text-[0.95rem]";
  title.textContent = notification.title || "اعلان";

  const bodyText = document.createElement("span");
  bodyText.className = "mt-1 line-clamp-2 block text-xs font-medium leading-6 text-loomera-textMuted lg:text-[0.82rem]";
  bodyText.textContent = notification.body || "";

  titleBlock.appendChild(title);
  titleBlock.appendChild(bodyText);

  const sideMeta = document.createElement("span");
  sideMeta.className = "shrink-0 text-left";

  if (isUnread) {
    const badge = document.createElement("span");
    badge.className = "mb-2 inline-flex rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-black text-slate-700 shadow-lm-soft";
    badge.textContent = "جدید";
    sideMeta.appendChild(badge);
  }

  const date = document.createElement("span");
  date.className = "block text-[11px] font-bold text-loomera-textMuted";
  date.dir = "rtl";
  date.textContent = formatJalaliDate(notification.created_at);
  sideMeta.appendChild(date);

  topRow.appendChild(titleBlock);
  topRow.appendChild(sideMeta);

  const bottomRow = document.createElement("span");
  bottomRow.className = "mt-3 flex items-center justify-between gap-2";

  const category = document.createElement("span");
  category.className = [
    "inline-flex rounded-full px-3 py-1 text-[11px] font-black",
    tone.chip,
  ].join(" ");
  category.textContent = notification.category_label || "اعلان";

  const actionText = document.createElement("span");
  actionText.className = "inline-flex items-center gap-1 text-[11px] font-black text-slate-700 group-hover:text-slate-900";
  actionText.innerHTML = 'مشاهده <i class="fa-solid fa-arrow-left text-[10px]" aria-hidden="true"></i>';

  bottomRow.appendChild(category);
  bottomRow.appendChild(actionText);

  body.appendChild(topRow);
  body.appendChild(bottomRow);

  item.appendChild(iconWrap);
  item.appendChild(body);

  item.addEventListener("click", async (event) => {
    if (item.dataset.isRead === "true" || !readUrl) return;

    event.preventDefault();
    const targetUrl = item.href;

    try {
      const payload = await postJson(readUrl);
      item.dataset.isRead = "true";
      syncUnreadCount(payload.unread_count);
    } catch (error) {
      // اگر mark as read خطا بدهد، ناوبری را متوقف نمی‌کنیم
    }

    window.location.href = targetUrl;
  });

  return item;
}

function renderNotifications(root) {
  const list = root.querySelector("[data-notification-list]");
  if (!list) return;

  const activeTab = root.dataset.activeTab || "all";
  const allNotifications = root._notifications || [];
  const filtered = filterNotifications(allNotifications, activeTab);

  list.innerHTML = "";

  if (!filtered.length) {
    setRootState(root, "empty");
    return;
  }

  setRootState(root, "ready");

  const fragment = document.createDocumentFragment();
  filtered.forEach((notification) => {
    fragment.appendChild(createNotificationItem(root, notification));
  });

  list.appendChild(fragment);
}

async function loadSummary(root) {
  const url = root.dataset.summaryUrl;
  if (!url) return;

  setRootState(root, "loading");

  try {
    const payload = await fetchJson(url);
    root._notifications = Array.isArray(payload.notifications) ? payload.notifications : [];
    syncUnreadCount(payload.unread_count);
    renderNotifications(root);
  } catch (error) {
    setRootState(root, "error");
  }
}

function bindTabs(root) {
  if (root.dataset.tabsBound === "1") return;
  root.dataset.tabsBound = "1";

  root.addEventListener("click", (event) => {
    const tabButton = event.target.closest("[data-notification-tab]");
    if (!tabButton || !root.contains(tabButton)) return;

    event.preventDefault();
    event.stopPropagation();

    const tabValue = tabButton.dataset.notificationTab || "all";

    setActiveTab(root, tabValue);
    renderNotifications(root);
  });
}

function bindRoot(root) {
  if (root.dataset.bound === "1") return;
  root.dataset.bound = "1";

  root._notifications = [];
  setActiveTab(root, "all");
  bindTabs(root);

  const toggle = root.querySelector("[data-notification-toggle]");
  const readAll = root.querySelector("[data-notification-read-all]");

  if (toggle) {
    toggle.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopPropagation();

      const isOpen = root.dataset.menuOpen === "true";
      closeOtherMenus(root);

      if (isOpen) {
        closeMenu(root);
        return;
      }

      openMenu(root);
      await loadSummary(root);
    });
  }

  if (readAll) {
    readAll.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopPropagation();

      const url = root.dataset.readAllUrl;
      if (!url || readAll.dataset.loading === "1") return;

      readAll.dataset.loading = "1";
      readAll.disabled = true;

      try {
        const payload = await postJson(url);
        syncUnreadCount(payload.unread_count);
        await loadSummary(root);
      } catch (error) {
        window.LoomeraFeedback?.error?.("خواندن همه اعلان‌ها با خطا مواجه شد");
      } finally {
        delete readAll.dataset.loading;
      }
    });
  }

  loadSummary(root);
}

let globalListenersBound = false;

function initCustomerNotificationHeader() {
  const roots = Array.from(document.querySelectorAll("[data-customer-notification-root]"));
  if (!roots.length) return;

  roots.forEach(bindRoot);

  if (globalListenersBound) return;
  globalListenersBound = true;

  document.addEventListener("click", (event) => {
    if (event.target.closest("[data-customer-notification-root]")) return;
    roots.forEach((root) => closeMenu(root));
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    roots.forEach((root) => closeMenu(root));
  });

  window.addEventListener("loomera:notifications-updated", (event) => {
    const unreadCount = event.detail?.unread_count;
    syncUnreadCount(unreadCount);
    roots.forEach((root) => {
      if (root.dataset.menuOpen === "true") loadSummary(root);
    });
  });

  window.setInterval(() => {
    roots.forEach((root) => {
      loadSummary(root);
    });
  }, 60000);
}

export default initCustomerNotificationHeader;

if (typeof window !== "undefined" && !window.__loomeraCustomerNotificationHeaderAutoBooted) {
  window.__loomeraCustomerNotificationHeaderAutoBooted = true;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      initCustomerNotificationHeader();
    });
  } else {
    initCustomerNotificationHeader();
  }
}