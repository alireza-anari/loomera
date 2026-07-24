function getCsrfToken() {
  const cookie = document.cookie
    .split("; ")
    .find((row) => row.startsWith("csrftoken="));

  return cookie ? decodeURIComponent(cookie.split("=")[1]) : "";
}

function toPersianNumber(value) {
  return String(value ?? 0).replace(/\d/g, (digit) => "۰۱۲۳۴۵۶۷۸۹"[Number(digit)]);
}

function notifyHeaderUnreadChanged(count) {
  try {
    window.dispatchEvent(new CustomEvent("loomera:notifications-updated", {
      detail: { unread_count: Math.max(0, Number(count) || 0) },
    }));
  } catch (error) {
    // no-op: browsers without CustomEvent should still update the current page.
  }
}

function updateUnreadBadges(count) {
  const safeCount = Math.max(0, Number(count) || 0);

  document.querySelectorAll("[data-unread-count]").forEach((element) => {
    element.textContent = toPersianNumber(safeCount);
  });

  document.querySelectorAll("[data-notification-badge]").forEach((badge) => {
    badge.textContent = safeCount > 99 ? "+۹۹" : toPersianNumber(safeCount);
    badge.classList.toggle("hidden", safeCount === 0);
  });

  document.querySelectorAll("[data-mark-all-read]").forEach((button) => {
    button.disabled = safeCount === 0;
  });

  notifyHeaderUnreadChanged(safeCount);
}

async function postJson(url) {
  const response = await fetch(url, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "X-CSRFToken": getCsrfToken(),
      "X-Requested-With": "XMLHttpRequest",
    },
  });

  let payload = {};
  try {
    payload = await response.json();
  } catch (error) {
    payload = {};
  }

  if (!response.ok) {
    throw new Error(payload.error || "درخواست با خطا مواجه شد.");
  }

  return payload;
}

function markCardAsRead(card) {
  if (!card) return;

  card.classList.remove("border-loomera-primary/25", "bg-loomera-primarySoft/35");
  card.classList.add("border-loomera-borderSoft", "bg-white");
  card.querySelectorAll("[data-mark-read]").forEach((button) => button.remove());

  const iconWrap = card.querySelector(".bg-loomera-primary.text-white");
  if (iconWrap) {
    iconWrap.classList.remove("bg-loomera-primary", "text-white");
    iconWrap.classList.add("bg-loomera-bgSubtle", "text-loomera-textMuted");
  }

  card.querySelectorAll("span").forEach((span) => {
    if (span.textContent.trim() === "جدید") span.remove();
  });
}

function initSingleReadButtons() {
  document.querySelectorAll("[data-mark-read]").forEach((button) => {
    if (button.dataset.bound === "1") return;
    button.dataset.bound = "1";

    button.addEventListener("click", async () => {
      const card = button.closest("[data-notification-card]");
      const url = card?.dataset.readUrl;
      if (!card || !url || button.dataset.loading === "1") return;

      button.dataset.loading = "1";
      button.disabled = true;

      try {
        const payload = await postJson(url);
        markCardAsRead(card);
        updateUnreadBadges(payload.unread_count);
      } catch (error) {
        window.alert(error.message || "خوانده‌شدن اعلان ثبت نشد.");
        button.disabled = false;
      } finally {
        delete button.dataset.loading;
      }
    });
  });
}

function initNotificationActions() {
  document.querySelectorAll("[data-notification-action]").forEach((link) => {
    if (link.dataset.bound === "1") return;
    link.dataset.bound = "1";

    link.addEventListener("click", async (event) => {
      const card = link.closest("[data-notification-card]");
      const url = card?.dataset.readUrl;
      if (!card || !url || !card.querySelector("[data-mark-read]")) return;

      event.preventDefault();
      const targetUrl = link.getAttribute("href") || "/";

      try {
        const payload = await postJson(url);
        markCardAsRead(card);
        updateUnreadBadges(payload.unread_count);
      } catch (error) {
        // Navigation should still work even if marking as read fails.
      }

      window.location.href = targetUrl;
    });
  });
}

function initMarkAllRead() {
  document.querySelectorAll("[data-mark-all-read]").forEach((button) => {
    if (button.dataset.bound === "1") return;
    button.dataset.bound = "1";

    button.addEventListener("click", async () => {
      const url = button.dataset.readAllUrl;
      if (!url || button.dataset.loading === "1") return;

      button.dataset.loading = "1";
      button.disabled = true;

      try {
        const payload = await postJson(url);
        document.querySelectorAll("[data-notification-card]").forEach(markCardAsRead);
        updateUnreadBadges(payload.unread_count);
      } catch (error) {
        window.alert(error.message || "خواندن همه اعلان‌ها با خطا مواجه شد.");
        button.disabled = false;
      } finally {
        delete button.dataset.loading;
      }
    });
  });
}

function initCustomerNotificationsPage() {
  initSingleReadButtons();
  initNotificationActions();
  initMarkAllRead();
}

initCustomerNotificationsPage();
