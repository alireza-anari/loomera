function getCsrfToken() {
  const input = document.querySelector("input[name='csrfmiddlewaretoken']");
  if (input?.value) return input.value;

  const cookie = document.cookie
    .split("; ")
    .find((row) => row.startsWith("csrftoken="));

  return cookie ? decodeURIComponent(cookie.split("=")[1]) : "";
}

function buildLoginRedirectUrl() {
  return `/accounts/login/?next=${encodeURIComponent(window.location.pathname + window.location.search)}`;
}

function initHorizontalRails() {
  document.querySelectorAll("[data-scroll-section]").forEach((section) => {
    const rail = section.querySelector("[data-scroll-rail]");
    const prev = section.querySelector("[data-rail-prev]");
    const next = section.querySelector("[data-rail-next]");

    if (!rail) return;

    const getScrollAmount = () => Math.max(260, Math.floor(rail.clientWidth * 0.78));

    prev?.addEventListener("click", () => {
      rail.scrollBy({ left: getScrollAmount(), behavior: "smooth" });
    });

    next?.addEventListener("click", () => {
      rail.scrollBy({ left: -getScrollAmount(), behavior: "smooth" });
    });
  });
}

function syncFavoriteIcon(button, isFavorite) {
  const icon = button.querySelector("i");
  button.setAttribute("aria-pressed", isFavorite ? "true" : "false");

  if (!icon) return;

  icon.classList.toggle("fa-solid", isFavorite);
  icon.classList.toggle("fa-regular", !isFavorite);
  icon.classList.toggle("text-red-500", isFavorite);
  icon.classList.toggle("text-loomera-textMuted", !isFavorite);
}

function removeFavoriteCard(button) {
  const card = button.closest("[data-favorite-card]");
  const railItem = button.closest("[data-salon-rail-item]");

  if (railItem) {
    railItem.style.transition = "opacity .2s ease, transform .2s ease";
    railItem.style.opacity = "0";
    railItem.style.transform = "scale(.96)";
    window.setTimeout(() => railItem.remove(), 220);
    return;
  }

  if (card) {
    card.style.transition = "opacity .2s ease, transform .2s ease";
    card.style.opacity = "0";
    card.style.transform = "scale(.96)";
    window.setTimeout(() => card.remove(), 220);
  }
}

function initFavoriteButtons() {
  document.querySelectorAll("[data-favorite-button][data-salon-id]").forEach((button) => {
    if (button.dataset.bound === "1") return;
    button.dataset.bound = "1";

    const initialState = button.getAttribute("aria-pressed") === "true";
    syncFavoriteIcon(button, initialState);

    button.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopPropagation();

      if (button.dataset.loading === "1") return;

      const salonId = button.dataset.salonId;
      const endpoint = button.dataset.favoriteUrl || "/csf/add_favorite/";

      if (!salonId) return;

      button.dataset.loading = "1";
      button.classList.add("opacity-70", "pointer-events-none");

      try {
        const response = await fetch(`${endpoint}?salonId=${encodeURIComponent(salonId)}`, {
          credentials: "same-origin",
          headers: {
            "X-Requested-With": "XMLHttpRequest",
            "X-CSRFToken": getCsrfToken(),
          },
        });

        const raw = (await response.text()).trim();
        let payload = null;

        try {
          payload = raw ? JSON.parse(raw) : null;
        } catch (error) {
          payload = null;
        }

        if (response.status === 401 || response.redirected) {
          window.location.href = buildLoginRedirectUrl();
          return;
        }

        if (!response.ok) {
          window.alert(payload?.message || raw || "تغییر علاقه‌مندی با خطا مواجه شد.");
          return;
        }

        const isFavorite = typeof payload?.is_favorite === "boolean"
          ? payload.is_favorite
          : raw.includes("اضافه") || raw.includes("added") || raw.includes("true");

        syncFavoriteIcon(button, isFavorite);

        if (!isFavorite || raw.includes("حذف") || payload?.action === "removed") {
          removeFavoriteCard(button);
        }
      } catch (error) {
        console.error("[show_salons] favorite toggle failed", error);
        window.alert("در تغییر علاقه‌مندی مشکلی پیش آمد.");
      } finally {
        delete button.dataset.loading;
        button.classList.remove("opacity-70", "pointer-events-none");
      }
    });
  });
}

function initSearchForm() {
  const form = document.querySelector("[data-discovery-search-form]");
  if (!form) return;

  form.addEventListener("submit", () => {
    form.querySelectorAll("input").forEach((input) => {
      if (!input.value.trim()) {
        input.disabled = true;
      }
    });

    window.setTimeout(() => {
      form.querySelectorAll("input").forEach((input) => {
        input.disabled = false;
      });
    }, 0);
  });
}

function initCardKeyboardSafety() {
  document.querySelectorAll("[data-salon-card]").forEach((card) => {
    const link = card.querySelector("a[href]");
    if (!link) return;

    card.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      if (event.target.closest("button, a, input, select, textarea")) return;
      link.click();
    });
  });
}

export default function initShowSalons() {
  initHorizontalRails();
  initFavoriteButtons();
  initSearchForm();
  initCardKeyboardSafety();
}