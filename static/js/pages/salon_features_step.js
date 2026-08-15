let salonFeaturesStepBound = false;

const toFaNumber = (value) => {
  try {
    return new Intl.NumberFormat("fa-IR").format(Number(value) || 0);
  } catch (_) {
    return String(value || 0);
  }
};

function normalizeTitle(value) {
  return String(value || "")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\|/g, "")
    .replace(/::/g, "")
    .slice(0, 50);
}

function normalizeDescription(value) {
  return String(value || "")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\|/g, "")
    .replace(/::/g, "")
    .slice(0, 180);
}

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function getForm() {
  return document.getElementById("salonFeaturesForm");
}

function getSelectedCount() {
  const form = getForm();
  if (!form) return 0;
  return form.querySelectorAll('input[name="selected_items"]:checked').length;
}

function getCustomCount() {
  return document.querySelectorAll("[data-custom-feature-item]").length;
}

function updateSelectedCount() {
  const countTarget = document.getElementById("selectedFeaturesCount");
  const selectedLabels = document.querySelectorAll("[data-selected-features-label]");
  const count = getSelectedCount();
  const formatted = toFaNumber(count);

  if (countTarget) countTarget.textContent = formatted;
  selectedLabels.forEach((label) => {
    label.textContent = formatted;
  });
}

function updateCustomCount() {
  const labels = document.querySelectorAll("[data-custom-features-label]");
  const formatted = toFaNumber(getCustomCount());
  labels.forEach((label) => {
    label.textContent = formatted;
  });
}

function updateReadiness() {
  const selectedCount = getSelectedCount();
  const customCount = getCustomCount();
  const progress = Math.min(100, Math.max(0, selectedCount * 34));
  const progressBar = document.querySelector("[data-features-progress-bar]");
  const progressText = document.querySelector("[data-features-progress-text]");
  const statusTitle = document.querySelector("[data-features-status-title]");
  const statusText = document.querySelector("[data-features-status-text]");
  const reviewStatus = document.querySelector("[data-features-review-status]");

  if (progressBar) progressBar.style.width = `${progress}%`;
  if (progressText) progressText.textContent = `${toFaNumber(progress)}٪`;

  let title = "ویژگی‌ها را کامل کن";
  let text = "برای ادامه بهتر است حداقل یک ویژگی یا امکان واقعی انتخاب شود.";
  let review = "نیازمند بررسی";

  if (selectedCount >= 3) {
    title = "مرحله آماده ادامه است";
    text = customCount
      ? "چند ویژگی آماده و سفارشی انتخاب شده و معرفی سالن کامل‌تر شده است."
      : "ویژگی‌های اصلی انتخاب شده‌اند. در صورت نیاز می‌توانی مزیت سفارشی هم اضافه کنی.";
    review = "آماده ثبت";
  } else if (selectedCount > 0) {
    title = "شروع خوبی است";
    text = "حداقل یک ویژگی انتخاب شده؛ برای معرفی کامل‌تر سالن، چند مورد واقعی دیگر را هم بررسی کن.";
    review = "قابل ذخیره";
  }

  if (statusTitle) statusTitle.textContent = title;
  if (statusText) statusText.textContent = text;
  if (reviewStatus) reviewStatus.textContent = review;
}

function refreshWorkspace() {
  window.LoomeraDashboardWorkspace?.refresh?.(document);
}

function syncAll() {
  updateSelectedCount();
  updateCustomCount();
  updateReadiness();
  refreshWorkspace();
}

function toggleEmptyState() {
  const list = document.getElementById("customFeaturesList");
  const emptyState = document.getElementById("customFeaturesEmptyState");
  if (!list || !emptyState) return;

  const itemCount = list.querySelectorAll("[data-custom-feature-item]").length;
  emptyState.classList.toggle("hidden", itemCount > 0);
}

function showInlineError(message) {
  const errorBox = document.getElementById("customFeatureInlineError");
  if (!errorBox) return;
  errorBox.textContent = message;
  errorBox.classList.remove("hidden");
}

function hideInlineError() {
  const errorBox = document.getElementById("customFeatureInlineError");
  if (!errorBox) return;
  errorBox.textContent = "";
  errorBox.classList.add("hidden");
}

function getSelectedIconClass() {
  const selectedInput = document.getElementById("selectedCustomIconInput");
  return selectedInput?.value || "fa-solid fa-sparkles";
}

function syncSelectedIconUI() {
  const selectedIcon = getSelectedIconClass();
  const buttons = document.querySelectorAll("[data-custom-icon-choice]");

  buttons.forEach((button) => {
    const isSelected = button.dataset.iconClass === selectedIcon;
    button.classList.toggle("is-selected", isSelected);
    button.classList.toggle("border-loomera-primary", isSelected);
    button.classList.toggle("bg-loomera-primarySoft", isSelected);
    button.classList.toggle("text-loomera-primaryText", isSelected);
    button.classList.toggle("ring-2", isSelected);
    button.classList.toggle("ring-loomera-primary/15", isSelected);
  });
}

function buildCustomFeatureItem(title, iconClass, description) {
  const wrapper = document.createElement("label");
  const safeTitle = escapeHtml(title);
  const safeIconClass = escapeHtml(iconClass);
  const safeDescription = escapeHtml(description);
  const safeValue = escapeHtml(`custom::${title}|${iconClass}|${description}`);

  wrapper.className =
    "flex items-start gap-3 rounded-[22px] border border-loomera-borderSoft bg-loomera-bgSubtle/70 px-4 py-4 transition hover:border-loomera-primary/20 hover:bg-white";
  wrapper.setAttribute("data-custom-feature-item", "");
  wrapper.setAttribute("data-custom-title", title);

  wrapper.innerHTML = `
    <input
      type="checkbox"
      name="selected_items"
      value="${safeValue}"
      class="mt-1 h-5 w-5 rounded border-loomera-borderSoft text-loomera-primary focus:ring-loomera-primary/20"
      checked
    >
    <span class="flex-1">
      <span class="block text-sm font-black text-loomera-textPrimary">
        <i class="${safeIconClass} ml-2 text-loomera-primaryText" aria-hidden="true"></i>${safeTitle}
      </span>
      <span class="mt-1 block text-xs leading-6 text-loomera-textMuted">${safeDescription}</span>
    </span>

    <button
      type="button"
      class="inline-flex h-9 w-9 items-center justify-center rounded-full border border-loomera-borderSoft bg-white text-loomera-textMuted transition hover:bg-loomera-dangerSoft hover:text-loomera-danger"
      data-remove-custom-feature
      title="حذف از لیست موقت">
      <i class="fa-solid fa-xmark text-xs" aria-hidden="true"></i>
    </button>
  `;

  return wrapper;
}

function attachRemoveHandlers(root) {
  const removeButtons = root.querySelectorAll("[data-remove-custom-feature]");
  removeButtons.forEach((button) => {
    if (button.dataset.bound === "true") return;
    button.dataset.bound = "true";

    button.addEventListener("click", () => {
      const item = button.closest("[data-custom-feature-item]");
      if (item) item.remove();
      toggleEmptyState();
      syncAll();
    });
  });
}

function setupFeatureSearch() {
  const searchInput = document.querySelector("[data-feature-search]");
  const cards = Array.from(document.querySelectorAll("[data-feature-card]"));
  const categories = Array.from(document.querySelectorAll("[data-feature-category]"));
  const emptyState = document.querySelector("[data-feature-empty]");

  if (!searchInput || !cards.length) return;

  const applySearch = () => {
    const query = searchInput.value.trim().toLowerCase();
    let visibleCount = 0;

    cards.forEach((card) => {
      const value = (card.dataset.featureSearchValue || card.textContent || "").toLowerCase();
      const visible = !query || value.includes(query);
      card.classList.toggle("hidden", !visible);
      if (visible) visibleCount += 1;
    });

    categories.forEach((category) => {
      const hasVisibleCard = Boolean(category.querySelector("[data-feature-card]:not(.hidden)"));
      category.classList.toggle("hidden", !hasVisibleCard);
    });

    emptyState?.classList.toggle("hidden", visibleCount !== 0);
    refreshWorkspace();
  };

  searchInput.addEventListener("input", applySearch);
  applySearch();
}

export default function initSalonFeaturesStep() {
  if (salonFeaturesStepBound) return;
  salonFeaturesStepBound = true;

  const form = getForm();
  const input = document.getElementById("customFeatureInput");
  const descriptionInput = document.getElementById("customFeatureDescriptionInput");
  const addBtn = document.getElementById("addCustomFeatureBtn");
  const list = document.getElementById("customFeaturesList");
  const selectedIconInput = document.getElementById("selectedCustomIconInput");
  const iconButtons = document.querySelectorAll("[data-custom-icon-choice]");

  if (!form || !input || !descriptionInput || !addBtn || !list || !selectedIconInput) {
    console.warn("[salon_features_step] required DOM not found");
    return;
  }

  function addCustomFeature() {
    hideInlineError();

    const normalized = normalizeTitle(input.value);
    const description = normalizeDescription(descriptionInput.value);
    const selectedIconClass = getSelectedIconClass();

    if (!normalized) {
      showInlineError("عنوان ویژگی سفارشی را وارد کن.");
      return;
    }

    if (!description) {
      showInlineError("توضیح ویژگی سفارشی را وارد کن.");
      return;
    }

    const existingTitles = Array.from(
      document.querySelectorAll("[data-custom-title]")
    ).map((el) => normalizeTitle(el.getAttribute("data-custom-title")).toLowerCase());

    const builtinTitles = Array.from(
      document.querySelectorAll('input[name="selected_items"][value^="builtin::"]')
    ).map((el) => {
      const raw = el.value.replace("builtin::", "");
      const title = raw.split("|", 1)[0];
      return normalizeTitle(title).toLowerCase();
    });

    const titleKey = normalized.toLowerCase();

    if (existingTitles.includes(titleKey) || builtinTitles.includes(titleKey)) {
      showInlineError("این ویژگی قبلاً در لیست وجود دارد.");
      return;
    }

    const item = buildCustomFeatureItem(normalized, selectedIconClass, description);
    list.appendChild(item);
    attachRemoveHandlers(item);

    input.value = "";
    descriptionInput.value = "";
    toggleEmptyState();
    syncAll();
  }

  addBtn.addEventListener("click", addCustomFeature);

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      addCustomFeature();
    }
  });

  iconButtons.forEach((button) => {
    button.addEventListener("click", () => {
      selectedIconInput.value = button.dataset.iconClass || "fa-solid fa-sparkles";
      syncSelectedIconUI();
    });
  });

  form.addEventListener("change", (event) => {
    if (event.target.matches('input[name="selected_items"]')) {
      syncAll();
    }
  });

  attachRemoveHandlers(document);
  setupFeatureSearch();
  toggleEmptyState();
  syncSelectedIconUI();
  syncAll();

}