export default function initAddService() {
  const root = document.querySelector("[data-dashboard-page-shell='add-service']");
  if (!root || root.dataset.addServiceBound === "true") return;
  root.dataset.addServiceBound = "true";

  const groupCheckboxes = Array.from(root.querySelectorAll("input[name='service_group']"));
  const stylistCheckboxes = Array.from(root.querySelectorAll("input[name='stylists']"));
  const priceRows = Array.from(root.querySelectorAll("[data-stylist-price-row]"));
  const selectAllStylistsButton = root.querySelector("[data-select-all-stylists]");
  const clearAllStylistsButton = root.querySelector("[data-clear-all-stylists]");

  const selectedGroupsTargets = Array.from(root.querySelectorAll("[data-selected-groups-count]"));
  const selectedStylistsTargets = Array.from(root.querySelectorAll("[data-selected-stylists-count]"));
  const readinessBadge = root.querySelector("[data-service-readiness-badge]");
  const readinessPercent = root.querySelector("[data-service-readiness-percent]");

  const serviceNameInput = root.querySelector("#id_service_name");
  const serviceSummaryInput = root.querySelector("#id_summery_description");
  const serviceDescriptionInput = root.querySelector("#id_description");
  const serviceDurationInput = root.querySelector("#id_duration_minutes");
  const serviceBasePriceInput = root.querySelector("#id_base_price");
  const serviceImageInput = root.querySelector("#id_service_image");

  const previewName = root.querySelector("[data-service-preview-name]");
  const previewSummary = root.querySelector("[data-service-preview-summary]");
  const previewInitials = root.querySelector("[data-service-preview-initials]");
  const previewImage = root.querySelector("[data-service-preview-image]");

  const toPersianDigits = (value) => String(value ?? "").replace(/\d/g, (digit) => "۰۱۲۳۴۵۶۷۸۹"[Number(digit)]);

  const hasText = (input) => Boolean((input?.value || "").trim());
  const hasPositiveNumber = (input) => {
    const value = Number(String(input?.value || "").replace(/,/g, ""));
    return Number.isFinite(value) && value > 0;
  };

  const getSelectedStylistIds = () => {
    return stylistCheckboxes
      .filter((checkbox) => checkbox.checked)
      .map((checkbox) => String(checkbox.value));
  };

  const refreshWorkspace = () => {
    window.LoomeraDashboardWorkspace?.refresh?.(root);
  };

  const setReadinessItem = (key, done, doneLabel, pendingLabel) => {
    const item = root.querySelector(`[data-readiness-item='${key}']`);
    if (!item) return;

    const iconWrapper = item.querySelector("[data-readiness-icon]");
    const icon = iconWrapper?.querySelector("i");
    const label = item.querySelector("[data-readiness-label]");

    item.classList.toggle("border-loomera-primary/20", done);
    item.classList.toggle("bg-loomera-primarySoft/45", done);

    if (iconWrapper) {
      iconWrapper.classList.toggle("bg-loomera-successSoft", done);
      iconWrapper.classList.toggle("text-loomera-success", done);
      iconWrapper.classList.toggle("bg-loomera-bgSubtle", !done);
      iconWrapper.classList.toggle("text-loomera-textMuted", !done);
    }

    if (icon) {
      icon.classList.toggle("fa-circle-check", done);
      icon.classList.toggle("fa-circle", !done);
    }

    if (label) {
      label.textContent = done ? doneLabel : pendingLabel;
    }
  };

  const syncCounts = () => {
    const selectedGroups = groupCheckboxes.filter((checkbox) => checkbox.checked).length;
    const selectedStylists = stylistCheckboxes.filter((checkbox) => checkbox.checked).length;

    selectedGroupsTargets.forEach((target) => {
      target.textContent = toPersianDigits(selectedGroups);
    });

    selectedStylistsTargets.forEach((target) => {
      target.textContent = toPersianDigits(selectedStylists);
    });
  };

  const syncCardsState = () => {
    const selectedStylistIds = new Set(getSelectedStylistIds());

    groupCheckboxes.forEach((checkbox) => {
      const card = checkbox.closest("[data-service-group-card]");
      if (!card) return;
      card.classList.toggle("border-loomera-primary/35", checkbox.checked);
      card.classList.toggle("bg-white", checkbox.checked);
      card.classList.toggle("shadow-lm-soft", checkbox.checked);
    });

    stylistCheckboxes.forEach((checkbox) => {
      const card = checkbox.closest("[data-stylist-card]");
      if (!card) return;
      card.classList.toggle("border-loomera-primary/35", checkbox.checked);
      card.classList.toggle("bg-white", checkbox.checked);
      card.classList.toggle("shadow-lm-soft", checkbox.checked);
    });

    priceRows.forEach((row) => {
      const stylistId = String(row.dataset.stylistPriceField || "");
      const active = selectedStylistIds.has(stylistId);
      const input = row.querySelector("input");

      row.classList.toggle("opacity-55", !active);
      row.classList.toggle("bg-loomera-primarySoft/25", active);

      if (input) {
        input.disabled = !active;
        input.required = active;
        input.classList.toggle("opacity-60", !active);
      }
    });
  };

  const syncPreviewText = () => {
    const name = (serviceNameInput?.value || "").trim();
    const summary = (serviceSummaryInput?.value || "").trim();

    if (previewName) previewName.textContent = name || "خدمت جدید";
    if (previewSummary) {
      previewSummary.textContent = summary || "بعد از ثبت، این توضیح کوتاه در مرور سریع خدمات دیده می‌شود.";
    }

    if (previewInitials && (!previewImage || previewImage.classList.contains("hidden"))) {
      previewInitials.textContent = name.slice(0, 1) || "خ";
    }
  };

  const syncPreviewImage = () => {
    const file = serviceImageInput?.files?.[0];
    if (!previewImage || !previewInitials) return;

    if (!file) {
      previewImage.src = "";
      previewImage.classList.add("hidden");
      previewInitials.classList.remove("hidden");
      syncPreviewText();
      return;
    }

    const imageUrl = URL.createObjectURL(file);
    previewImage.src = imageUrl;
    previewImage.classList.remove("hidden");
    previewInitials.classList.add("hidden");
  };

  const syncReadiness = () => {
    const basicsReady = hasText(serviceNameInput) && hasPositiveNumber(serviceDurationInput) && hasPositiveNumber(serviceBasePriceInput);
    const contentReady = hasText(serviceSummaryInput) || hasText(serviceDescriptionInput) || Boolean(serviceImageInput?.files?.length);
    const groupsReady = groupCheckboxes.some((checkbox) => checkbox.checked);
    const selectedStylistIds = new Set(getSelectedStylistIds());

    let allSelectedPricesReady = selectedStylistIds.size > 0;
    priceRows.forEach((row) => {
      const stylistId = String(row.dataset.stylistPriceField || "");
      if (!selectedStylistIds.has(stylistId)) return;
      const input = row.querySelector("input");
      if (!hasPositiveNumber(input)) allSelectedPricesReady = false;
    });

    const teamReady = selectedStylistIds.size > 0 && allSelectedPricesReady;
    const score = [basicsReady, contentReady, groupsReady, teamReady].filter(Boolean).length;
    const percent = Math.round((score / 4) * 100);
    const percentLabel = `${toPersianDigits(percent)}٪`;

    setReadinessItem("basics", basicsReady, "آماده ثبت", "در انتظار تکمیل");
    setReadinessItem("content", contentReady, "محتوا ثبت شده", "قابل بهبود");
    setReadinessItem("groups", groupsReady, "گروه انتخاب شده", "در انتظار انتخاب");
    setReadinessItem("team", teamReady, "تیم و قیمت آماده", "در انتظار انتخاب");

    if (readinessBadge) readinessBadge.textContent = percentLabel;
    if (readinessPercent) readinessPercent.textContent = percentLabel;
  };

  const syncAll = () => {
    syncCounts();
    syncCardsState();
    syncPreviewText();
    syncReadiness();
    refreshWorkspace();
  };

  groupCheckboxes.forEach((checkbox) => {
    checkbox.addEventListener("change", syncAll);
  });

  stylistCheckboxes.forEach((checkbox) => {
    checkbox.addEventListener("change", syncAll);
  });

  priceRows.forEach((row) => {
    row.querySelector("input")?.addEventListener("input", syncReadiness);
  });

  selectAllStylistsButton?.addEventListener("click", () => {
    stylistCheckboxes.forEach((checkbox) => {
      checkbox.checked = true;
    });
    syncAll();
  });

  clearAllStylistsButton?.addEventListener("click", () => {
    stylistCheckboxes.forEach((checkbox) => {
      checkbox.checked = false;
    });
    syncAll();
  });

  [serviceNameInput, serviceSummaryInput, serviceDescriptionInput, serviceDurationInput, serviceBasePriceInput].forEach((input) => {
    input?.addEventListener("input", syncAll);
  });

  serviceImageInput?.addEventListener("change", () => {
    syncPreviewImage();
    syncAll();
  });

  root.querySelector("[data-dashboard-workspace-tab-proxy]")?.addEventListener("click", (event) => {
    const target = root.querySelector("#add-service-section-basics");
    if (!target) return;
    event.preventDefault();
    target.open = true;
    window.LoomeraDashboardWorkspace?.scrollToPanel?.(target);
  });

  syncPreviewImage();
  syncAll();
}
