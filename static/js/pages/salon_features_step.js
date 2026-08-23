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

  const values = new Set(
    Array.from(form.querySelectorAll('input[name="selected_items"]:checked'))
      .map((input) => input.value)
      .filter(Boolean)
  );

  return values.size;
}

function getCustomCount() {
  return document.querySelectorAll("[data-custom-feature-item]").length;
}

function syncFeatureCardStates() {
  document.querySelectorAll(".lm-feature-card").forEach((card) => {
    const input = card.querySelector('input[name="selected_items"]');
    card.classList.toggle("is-selected", Boolean(input?.checked));
  });
}

function updateSelectedCount() {
  const countTarget = document.getElementById("selectedFeaturesCount");
  const selectedLabels = document.querySelectorAll(
    "[data-selected-features-label]"
  );
  const formatted = toFaNumber(getSelectedCount());

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

function updateCategoryCounts() {
  document
    .querySelectorAll("[data-feature-category-panel]")
    .forEach((panel) => {
      const key = panel.dataset.featureCategoryPanel;

      const count = panel.querySelectorAll(
        'input[name="selected_items"]:checked'
      ).length;

      const target = document.querySelector(
        `[data-feature-category-count="${key}"]`
      );

      if (target) {
        target.textContent = toFaNumber(count);
      }
    });
}

function updateReadiness() {
  const selectedCount = getSelectedCount();
  const customCount = getCustomCount();

  const progress = Math.min(
    100,
    Math.max(0, selectedCount * 34)
  );

  const progressBar = document.querySelector(
    "[data-features-progress-bar]"
  );

  const progressText = document.querySelector(
    "[data-features-progress-text]"
  );

  const statusTitle = document.querySelector(
    "[data-features-status-title]"
  );

  const statusText = document.querySelector(
    "[data-features-status-text]"
  );

  const reviewStatus = document.querySelector(
    "[data-features-review-status]"
  );

  if (progressBar) {
    progressBar.style.width = `${progress}%`;
  }

  if (progressText) {
    progressText.textContent = `${toFaNumber(progress)}٪`;
  }

  let title = "ویژگی‌ها را کامل کن";
  let text =
    "برای ادامه بهتر است حداقل یک ویژگی یا امکان واقعی انتخاب شود.";
  let review = "نیازمند بررسی";

  if (selectedCount >= 3) {
    title = "مرحله آماده ادامه است";

    text = customCount
      ? "چند ویژگی آماده و سفارشی انتخاب شده و معرفی مجموعه کامل‌تر شده است."
      : "ویژگی‌های اصلی انتخاب شده‌اند. در صورت نیاز می‌توانی مزیت سفارشی هم اضافه کنی.";

    review = "آماده ثبت";
  } else if (selectedCount > 0) {
    title = "شروع خوبی است";

    text =
      "حداقل یک ویژگی انتخاب شده؛ برای معرفی کامل‌تر مجموعه، چند مورد واقعی دیگر را هم بررسی کن.";

    review = "قابل ذخیره";
  }

  if (statusTitle) {
    statusTitle.textContent = title;
  }

  if (statusText) {
    statusText.textContent = text;
  }

  if (reviewStatus) {
    reviewStatus.textContent = review;
  }
}

function refreshWorkspace() {
  window.LoomeraDashboardWorkspace?.refresh?.(document);
}

function syncAll() {
  syncFeatureCardStates();
  updateSelectedCount();
  updateCustomCount();
  updateCategoryCounts();
  updateReadiness();
  refreshWorkspace();
}

function toggleEmptyState() {
  const list = document.getElementById("customFeaturesList");
  const emptyState = document.getElementById(
    "customFeaturesEmptyState"
  );

  if (!list || !emptyState) {
    return;
  }

  const itemCount = list.querySelectorAll(
    "[data-custom-feature-item]"
  ).length;

  emptyState.classList.toggle("hidden", itemCount > 0);
}

function showInlineError(message) {
  const errorBox = document.getElementById(
    "customFeatureInlineError"
  );

  if (!errorBox) {
    return;
  }

  errorBox.textContent = message;
  errorBox.classList.remove("hidden");
}

function hideInlineError() {
  const errorBox = document.getElementById(
    "customFeatureInlineError"
  );

  if (!errorBox) {
    return;
  }

  errorBox.textContent = "";
  errorBox.classList.add("hidden");
}

function getSelectedIconClass() {
  const selectedInput = document.getElementById(
    "selectedCustomIconInput"
  );

  return selectedInput?.value || "fa-solid fa-sparkles";
}

function syncSelectedIconUI() {
  const selectedIcon = getSelectedIconClass();

  const buttons = document.querySelectorAll(
    "[data-custom-icon-choice]"
  );

  buttons.forEach((button) => {
    const isSelected =
      button.dataset.iconClass === selectedIcon;

    button.classList.toggle(
      "is-selected",
      isSelected
    );

    button.classList.toggle(
      "border-loomera-primary",
      isSelected
    );

    button.classList.toggle(
      "bg-loomera-primarySoft",
      isSelected
    );

    button.classList.toggle(
      "text-loomera-primaryText",
      isSelected
    );

    button.classList.toggle(
      "ring-2",
      isSelected
    );

    button.classList.toggle(
      "ring-loomera-primary/15",
      isSelected
    );
  });
}

function buildCustomFeatureItem(
  title,
  iconClass,
  description
) {
  const wrapper = document.createElement("label");

  const safeTitle = escapeHtml(title);
  const safeIconClass = escapeHtml(iconClass);
  const safeDescription = escapeHtml(description);

  const safeValue = escapeHtml(
    `custom::${title}|${iconClass}|${description}`
  );

  wrapper.className =
    "lm-feature-card relative flex items-start gap-3 rounded-[22px] border border-loomera-borderSoft bg-loomera-bgSubtle/70 px-4 py-4 transition";

  wrapper.setAttribute(
    "data-custom-feature-item",
    ""
  );

  wrapper.setAttribute(
    "data-custom-title",
    title
  );

  wrapper.innerHTML = `
    <input
      type="checkbox"
      name="selected_items"
      value="${safeValue}"
      class="lm-feature-checkbox sr-only"
      checked
    >

    <span
      class="lm-feature-check mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-xl border border-loomera-borderSoft bg-white text-white transition"
      aria-hidden="true"
    >
      <i class="fa-solid fa-check text-[10px]"></i>
    </span>

    <span class="min-w-0 flex-1">
      <span class="block text-sm font-black text-loomera-textPrimary">
        <i
          class="${safeIconClass} ml-2 text-loomera-primaryText"
          aria-hidden="true"
        ></i>

        ${safeTitle}
      </span>

      <span class="mt-1 block text-xs leading-6 text-loomera-textMuted">
        ${safeDescription}
      </span>
    </span>

    <button
      type="button"
      class="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-loomera-borderSoft bg-white text-loomera-textMuted transition hover:bg-loomera-dangerSoft hover:text-loomera-danger"
      data-remove-custom-feature
      title="حذف از لیست موقت"
    >
      <i
        class="fa-solid fa-xmark text-xs"
        aria-hidden="true"
      ></i>
    </button>
  `;

  return wrapper;
}

function attachRemoveHandlers(root) {
  const removeButtons = root.querySelectorAll(
    "[data-remove-custom-feature]"
  );

  removeButtons.forEach((button) => {
    if (button.dataset.bound === "true") {
      return;
    }

    button.dataset.bound = "true";

    button.addEventListener(
      "click",
      (event) => {
        event.preventDefault();
        event.stopPropagation();

        const item = button.closest(
          "[data-custom-feature-item]"
        );

        if (item) {
          item.remove();
        }

        toggleEmptyState();
        syncAll();
      }
    );
  });
}

function deduplicatePresetCustomItems() {
  const presetTitles = new Set(
    Array.from(
      document.querySelectorAll(
        "[data-feature-card][data-feature-title]"
      )
    )
      .map((card) =>
        normalizeTitle(
          card.dataset.featureTitle
        ).toLowerCase()
      )
      .filter(Boolean)
  );

  document
    .querySelectorAll("[data-custom-feature-item]")
    .forEach((item) => {
      const title = normalizeTitle(
        item.dataset.customTitle
      ).toLowerCase();

      if (
        title &&
        presetTitles.has(title)
      ) {
        item.remove();
      }
    });
}

function setupFeatureTabsAndSearch() {
  const tabs = Array.from(
    document.querySelectorAll(
      "[data-feature-category-tab]"
    )
  );

  const panels = Array.from(
    document.querySelectorAll(
      "[data-feature-category-panel]"
    )
  );

  const searchInput = document.querySelector(
    "[data-feature-search]"
  );

  const emptyState = document.querySelector(
    "[data-feature-empty]"
  );

  if (!tabs.length || !panels.length) {
    return;
  }

  let activeKey =
    tabs.find(
      (tab) =>
        tab.getAttribute("aria-selected") ===
        "true"
    )?.dataset.featureCategoryTab ||
    tabs[0].dataset.featureCategoryTab;

  const applySearch = () => {
    const activePanel = panels.find(
      (panel) =>
        panel.dataset.featureCategoryPanel ===
        activeKey
    );

    if (!activePanel) {
      return;
    }

    const query = (
      searchInput?.value || ""
    )
      .trim()
      .toLowerCase();

    let visibleCount = 0;

    activePanel
      .querySelectorAll("[data-feature-card]")
      .forEach((card) => {
        const value = (
          card.dataset.featureSearchValue ||
          card.textContent ||
          ""
        ).toLowerCase();

        const visible =
          !query ||
          value.includes(query);

        card.classList.toggle(
          "hidden",
          !visible
        );

        if (visible) {
          visibleCount += 1;
        }
      });

    emptyState?.classList.toggle(
      "hidden",
      visibleCount !== 0
    );
  };

  const activate = (key) => {
    activeKey = key;

    tabs.forEach((tab) => {
      const active =
        tab.dataset.featureCategoryTab === key;

      tab.setAttribute(
        "aria-selected",
        active ? "true" : "false"
      );

      tab.classList.toggle(
        "border-loomera-primary/20",
        active
      );

      tab.classList.toggle(
        "bg-loomera-primarySoft",
        active
      );

      tab.classList.toggle(
        "text-loomera-primaryText",
        active
      );

      tab.classList.toggle(
        "shadow-sm",
        active
      );

      tab.classList.toggle(
        "border-loomera-borderSoft",
        !active
      );

      tab.classList.toggle(
        "bg-white",
        !active
      );

      tab.classList.toggle(
        "text-loomera-textSecondary",
        !active
      );
    });

    panels.forEach((panel) => {
      const active =
        panel.dataset.featureCategoryPanel === key;

      panel.classList.toggle(
        "hidden",
        !active
      );

      if (active) {
        panel
          .querySelectorAll(
            "[data-feature-card]"
          )
          .forEach((card) => {
            card.classList.remove("hidden");
          });
      }
    });

    if (searchInput) {
      searchInput.value = "";
    }

    emptyState?.classList.add("hidden");

    applySearch();
    refreshWorkspace();
  };

  tabs.forEach((tab) => {
    tab.addEventListener(
      "click",
      () => {
        activate(
          tab.dataset.featureCategoryTab
        );
      }
    );
  });

  searchInput?.addEventListener(
    "input",
    applySearch
  );

  activate(activeKey);
}

export default function initSalonFeaturesStep() {
  if (salonFeaturesStepBound) {
    return;
  }

  salonFeaturesStepBound = true;

  const form = getForm();

  const input = document.getElementById(
    "customFeatureInput"
  );

  const descriptionInput =
    document.getElementById(
      "customFeatureDescriptionInput"
    );

  const addBtn = document.getElementById(
    "addCustomFeatureBtn"
  );

  const list = document.getElementById(
    "customFeaturesList"
  );

  const selectedIconInput =
    document.getElementById(
      "selectedCustomIconInput"
    );

  const iconButtons =
    document.querySelectorAll(
      "[data-custom-icon-choice]"
    );

  if (
    !form ||
    !input ||
    !descriptionInput ||
    !addBtn ||
    !list ||
    !selectedIconInput
  ) {
    console.warn(
      "[salon_features_step] required DOM not found"
    );

    return;
  }

  function addCustomFeature() {
    hideInlineError();

    const normalized = normalizeTitle(
      input.value
    );

    const description =
      normalizeDescription(
        descriptionInput.value
      );

    const selectedIconClass =
      getSelectedIconClass();

    if (!normalized) {
      showInlineError(
        "عنوان ویژگی سفارشی را وارد کن."
      );

      return;
    }

    if (!description) {
      showInlineError(
        "توضیح ویژگی سفارشی را وارد کن."
      );

      return;
    }

    const existingTitles = Array.from(
      document.querySelectorAll(
        "[data-custom-title]"
      )
    ).map((el) =>
      normalizeTitle(
        el.getAttribute("data-custom-title")
      ).toLowerCase()
    );

    const presetTitles = Array.from(
      document.querySelectorAll(
        "[data-feature-title]"
      )
    ).map((el) =>
      normalizeTitle(
        el.getAttribute("data-feature-title")
      ).toLowerCase()
    );

    const titleKey =
      normalized.toLowerCase();

    if (
      existingTitles.includes(titleKey) ||
      presetTitles.includes(titleKey)
    ) {
      showInlineError(
        "این ویژگی قبلاً در لیست وجود دارد."
      );

      return;
    }

    const item = buildCustomFeatureItem(
      normalized,
      selectedIconClass,
      description
    );

    list.appendChild(item);

    attachRemoveHandlers(item);

    input.value = "";
    descriptionInput.value = "";

    toggleEmptyState();
    syncAll();
  }

  addBtn.addEventListener(
    "click",
    addCustomFeature
  );

  input.addEventListener(
    "keydown",
    (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        addCustomFeature();
      }
    }
  );

  iconButtons.forEach((button) => {
    button.addEventListener(
      "click",
      () => {
        selectedIconInput.value =
          button.dataset.iconClass ||
          "fa-solid fa-sparkles";

        syncSelectedIconUI();
      }
    );
  });

  form.addEventListener(
    "change",
    (event) => {
      if (
        event.target.matches(
          'input[name="selected_items"]'
        )
      ) {
        syncAll();
      }
    }
  );

  deduplicatePresetCustomItems();
  attachRemoveHandlers(document);
  setupFeatureTabsAndSearch();
  toggleEmptyState();
  syncSelectedIconUI();
  syncAll();
}