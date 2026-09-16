// static/js/pages/profile.js

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
  icon.classList.toggle("text-gray-500", !isFavorite);
}

function updateFavoriteCounts(count) {
  document.querySelectorAll("[data-favorite-count]").forEach((element) => {
    element.textContent = Number(count || 0).toLocaleString("fa-IR");
  });
}

function syncFavoritesEmptyState() {
  const grid = document.querySelector("[data-favorites-grid]");
  const listSection = document.querySelector("[data-favorites-list-section]");
  const emptySection = document.querySelector("[data-favorites-empty-section]");
  const remainingCount = grid?.querySelectorAll("[data-favorite-card]").length || 0;

  updateFavoriteCounts(remainingCount);
  listSection?.classList.toggle("hidden", remainingCount === 0);
  emptySection?.classList.toggle("hidden", remainingCount > 0);
}

function initFavoriteButtons() {
  document.querySelectorAll(".like-button[data-salon-id]").forEach((button) => {
    if (button.dataset.bound === "1") return;
    button.dataset.bound = "1";

    button.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopPropagation();

      const salonId = button.dataset.salonId;
      const endpoint = button.dataset.favoriteUrl || "/csf/add_favorite/";
      if (!salonId || button.dataset.loading === "1") return;

      button.dataset.loading = "1";
      button.classList.add("opacity-70", "pointer-events-none");

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
          window.LoomeraFeedback?.error?.(payload?.message || raw || "ثبت علاقه‌مندی با خطا مواجه شد.");
          return;
        }

        const isFavorite = typeof payload?.is_favorite === "boolean"
          ? payload.is_favorite
          : raw.includes("اضافه");

        syncFavoriteButtonState(button, isFavorite);

        if (!isFavorite) {
          const card = button.closest("[data-favorite-card]");
          card?.classList.add("opacity-0", "scale-[0.98]");
          window.setTimeout(() => {
            card?.remove();
            syncFavoritesEmptyState();
          }, 180);
        }
      } catch (error) {
        console.error("[profile] favorite toggle failed", error);
        window.LoomeraFeedback?.error?.("در ثبت علاقه‌مندی مشکلی پیش آمد.");
      } finally {
        delete button.dataset.loading;
        button.classList.remove("opacity-70", "pointer-events-none");
      }
    });
  });
}

export default function initProfilePage() {
  const searchButtons = document.querySelectorAll("[data-action='start-search']");
  searchButtons.forEach((btn) => {
    if (btn.dataset.bound === "1") return;
    btn.dataset.bound = "1";

    btn.addEventListener("click", () => {
      const url = btn.dataset.url || "/search/search/";
      window.location.href = url;
    });
  });

  initFavoriteButtons();
  syncFavoritesEmptyState();
}
