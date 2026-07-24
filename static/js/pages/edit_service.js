export default function initEditService() {
  const root = document.querySelector("[data-edit-service-page]");
  if (!root) return;

  const groupCheckboxes = Array.from(root.querySelectorAll("[data-service-group-checkbox]"));
  const stylistCheckboxes = Array.from(root.querySelectorAll("[data-stylist-checkbox]"));
  const selectedGroupsTargets = Array.from(root.querySelectorAll("[data-selected-groups-count]"));
  const selectedStylistsTargets = Array.from(root.querySelectorAll("[data-selected-stylists-count]"));
  const pricedStylistsTargets = Array.from(root.querySelectorAll("[data-priced-stylists-count]"));
  const readinessScoreTargets = Array.from(root.querySelectorAll("[data-readiness-score]"));
  const nameInput = root.querySelector("#id_service_name");
  const summaryInput = root.querySelector("#id_summery_description");
  const durationInput = root.querySelector("#id_duration_minutes");
  const basePriceInput = root.querySelector("#id_base_price");
  const imageInput = root.querySelector("#id_service_image");
  const previewNames = Array.from(root.querySelectorAll("[data-service-preview-name]"));
  const previewSummaries = Array.from(root.querySelectorAll("[data-service-preview-summary]"));
  const previewInitials = Array.from(root.querySelectorAll("[data-service-preview-initials]"));
  const previewImages = Array.from(root.querySelectorAll("[data-service-preview-image]"));
  const readinessItems = Array.from(root.querySelectorAll("[data-readiness-item]"));
  const groupOptions = Array.from(root.querySelectorAll("[data-group-option]"));
  let previewObjectUrl = "";

  previewImages.forEach((img) => { if (img.getAttribute("src")) img.dataset.originalSrc = img.getAttribute("src"); });

  const persianDigits = (value) => String(value).replace(/\d/g, (digit) => "۰۱۲۳۴۵۶۷۸۹"[Number(digit)]);
  const selectedGroups = () => groupCheckboxes.filter((checkbox) => checkbox.checked).length;
  const selectedStylists = () => stylistCheckboxes.filter((checkbox) => checkbox.checked).length;
  const selectedPricedStylists = () => stylistCheckboxes.filter((checkbox) => {
    const card = checkbox.closest("[data-stylist-card]");
    const price = card?.querySelector("[data-stylist-price]");
    return checkbox.checked && price && String(price.value || "").trim() !== "";
  }).length;

  function refreshWorkspace() {
    window.LoomeraDashboardWorkspace?.refresh(root);
  }

  function setReadinessItem(name, isReady) {
    const item = readinessItems.find((element) => element.dataset.readinessItem === name);
    if (!item) return;

    const icon = item.querySelector("[data-readiness-icon]");
    item.classList.toggle("bg-loomera-primarySoft/45", isReady);
    item.classList.toggle("border", isReady);
    item.classList.toggle("border-loomera-primary/20", isReady);

    if (icon) {
      icon.classList.toggle("bg-loomera-successSoft", isReady);
      icon.classList.toggle("text-loomera-success", isReady);
      icon.classList.toggle("bg-loomera-warningSoft", !isReady);
      icon.classList.toggle("text-loomera-warning", !isReady);
      icon.innerHTML = isReady
    ? '<i class="fa-solid fa-check text-[10px]" aria-hidden="true"></i>'
    : '<i class="fa-solid fa-circle-exclamation text-[10px]" aria-hidden="true"></i>';
    }
  }

  function syncGroupOptionsState() {
    groupOptions.forEach((option) => {
      const checkbox = option.querySelector("[data-service-group-checkbox]");
      const selected = Boolean(checkbox?.checked);
      option.classList.toggle("border-loomera-primary/30", selected);
      option.classList.toggle("bg-loomera-primarySoft", selected);
      option.classList.toggle("text-loomera-primaryText", selected);
      option.classList.toggle("border-loomera-borderSoft", !selected);
      option.classList.toggle("bg-white", !selected);
      option.classList.toggle("text-loomera-textSecondary", !selected);
    });
  }

  function syncStylistCardsState() {
    stylistCheckboxes.forEach((checkbox) => {
      const card = checkbox.closest("[data-stylist-card]");
      const priceField = card?.querySelector("[data-stylist-price]");
      if (!priceField) return;
      priceField.disabled = !checkbox.checked;
      priceField.classList.toggle("opacity-60", !checkbox.checked);
      if (checkbox.checked && !priceField.value && basePriceInput?.value) priceField.value = basePriceInput.value;
    });
  }

  function syncPreview() {
    const name = (nameInput?.value || "").trim();
    const summary = (summaryInput?.value || "").trim();
    previewNames.forEach((target) => { target.textContent = name || "خدمت"; });
    previewSummaries.forEach((target) => { target.textContent = summary || "بعد از ذخیره، این توضیح کوتاه در مرور سریع خدمات دیده می‌شود."; });
    previewInitials.forEach((target) => { target.textContent = name.slice(0, 1) || "خ"; });
  }

  function syncReadiness() {
    const hasInfo = Boolean((nameInput?.value || "").trim() && Number(durationInput?.value || 0) > 0 && Number(basePriceInput?.value || 0) >= 0 && String(basePriceInput?.value || "").trim() !== "");
    const hasGroups = selectedGroups() > 0;
    const hasStylists = selectedStylists() > 0;
    const hasPrices = selectedStylists() > 0 && selectedPricedStylists() === selectedStylists();
    const score = [hasInfo, hasGroups, hasStylists, hasPrices].filter(Boolean).length;
    readinessScoreTargets.forEach((target) => { target.textContent = `${persianDigits(score)}/۴`; });
    setReadinessItem("info", hasInfo);
    setReadinessItem("groups", hasGroups);
    setReadinessItem("team", hasStylists);
    setReadinessItem("prices", hasPrices);
  }

  function syncCounts() {
    const groups = selectedGroups();
    const stylists = selectedStylists();
    const priced = selectedPricedStylists();
    selectedGroupsTargets.forEach((target) => { target.textContent = persianDigits(groups); });
    selectedStylistsTargets.forEach((target) => { target.textContent = persianDigits(stylists); });
    pricedStylistsTargets.forEach((target) => { target.textContent = persianDigits(priced); });
    syncGroupOptionsState();
    syncReadiness();
    refreshWorkspace();
  }

  imageInput?.addEventListener("change", () => {
    const file = imageInput.files?.[0];
    if (previewObjectUrl) URL.revokeObjectURL(previewObjectUrl);
    if (!file) {
      previewImages.forEach((img) => {
    if (img.dataset.originalSrc) {
      img.src = img.dataset.originalSrc;
      img.classList.remove("hidden");
    } else {
      img.src = "";
      img.classList.add("hidden");
    }
      });
      previewInitials.forEach((item) => item.classList.toggle("hidden", previewImages.some((img) => !img.classList.contains("hidden"))));
      return;
    }
    previewObjectUrl = URL.createObjectURL(file);
    previewImages.forEach((img) => { img.src = previewObjectUrl; img.classList.remove("hidden"); });
    previewInitials.forEach((item) => item.classList.add("hidden"));
  });

  root.querySelector("[data-edit-service-focus-primary]")?.addEventListener("click", () => {
    document.getElementById("edit-service-section-info")?.scrollIntoView({ behavior: "smooth", block: "start" });
    nameInput?.focus({ preventScroll: true });
  });
  root.querySelector("[data-select-all-stylists]")?.addEventListener("click", () => { stylistCheckboxes.forEach((checkbox) => { checkbox.checked = true; }); syncStylistCardsState(); syncCounts(); });
  root.querySelector("[data-clear-all-stylists]")?.addEventListener("click", () => { stylistCheckboxes.forEach((checkbox) => { checkbox.checked = false; }); syncStylistCardsState(); syncCounts(); });
  root.querySelector("[data-copy-base-price]")?.addEventListener("click", () => { stylistCheckboxes.forEach((checkbox) => { if (!checkbox.checked) return; const price = checkbox.closest("[data-stylist-card]")?.querySelector("[data-stylist-price]"); if (price) price.value = basePriceInput?.value || ""; }); syncCounts(); });

  groupCheckboxes.forEach((checkbox) => checkbox.addEventListener("change", syncCounts));
  stylistCheckboxes.forEach((checkbox) => checkbox.addEventListener("change", () => { syncStylistCardsState(); syncCounts(); }));
  root.querySelectorAll("[data-stylist-price]").forEach((field) => field.addEventListener("input", syncCounts));
  [nameInput, summaryInput, durationInput, basePriceInput].forEach((field) => field?.addEventListener("input", () => { syncPreview(); syncStylistCardsState(); syncCounts(); }));
  window.addEventListener("beforeunload", () => { if (previewObjectUrl) URL.revokeObjectURL(previewObjectUrl); });

  syncStylistCardsState();
  syncPreview();
  syncCounts();

}
