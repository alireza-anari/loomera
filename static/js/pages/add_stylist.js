export default function initAddStylist() {
  const root = document.querySelector("[data-add-stylist-form]") || document;
  const serviceCheckboxes = Array.from(root.querySelectorAll("[data-service-checkbox]"));
  const selectedCountTargets = Array.from(document.querySelectorAll("[data-selected-services-count]"));
  const selectedGroupsTargets = Array.from(document.querySelectorAll("[data-selected-groups-count]"));
  const serviceGroups = Array.from(root.querySelectorAll("[data-service-group]"));

  const nameInput = document.getElementById("id_name");
  const familyInput = document.getElementById("id_family");
  const mobileInput = document.getElementById("id_mobile_number");
  const expertInput = document.getElementById("id_expert");
  const descriptionInput = document.getElementById("id_description");
  const profileImageInput = document.getElementById("id_profile_image");

  const previewNames = Array.from(document.querySelectorAll("[data-stylist-preview-name]"));
  const previewSubtitles = Array.from(document.querySelectorAll("[data-stylist-preview-subtitle]"));
  const previewInitialsTargets = Array.from(document.querySelectorAll("[data-stylist-preview-initials]"));
  const previewImages = Array.from(document.querySelectorAll("[data-stylist-preview-image]"));
  const readinessTitle = document.querySelector("[data-add-stylist-readiness-title]");
  const readinessDescription = document.querySelector("[data-add-stylist-readiness-description]");
  const readinessScoreTargets = Array.from(document.querySelectorAll("[data-readiness-score]"));
  const readinessPill = document.querySelector("[data-add-stylist-readiness-pill]");
  const readinessSteps = Array.from(document.querySelectorAll("[data-readiness-step]"));
  let previewObjectUrl = "";

  if (typeof jalaliDatepicker !== "undefined" && document.querySelector(".datepicker")) {
    try {
      jalaliDatepicker.startWatch({
        selector: ".datepicker",
        autoHide: true,
      });
    } catch (error) {
      console.warn("[add-stylist] jalaliDatepicker initialization failed");
    }
  }

  const toPersianDigits = (value) =>
    String(value).replace(/\d/g, (digit) => "۰۱۲۳۴۵۶۷۸۹"[Number(digit)]);

  const getSelectedServicesCount = () =>
    serviceCheckboxes.filter((checkbox) => checkbox.checked).length;

  const getSelectedGroupsCount = () => {
    let selectedGroups = 0;
    serviceGroups.forEach((group) => {
      if (group.querySelectorAll("[data-service-checkbox]:checked").length > 0) {
        selectedGroups += 1;
      }
    });
    return selectedGroups;
  };

  const refreshWorkspace = () => {
    if (window.LoomeraDashboardWorkspace?.refreshAll) {
      window.requestAnimationFrame(() => window.LoomeraDashboardWorkspace.refreshAll());
    }
  };

  const setText = (targets, text) => {
    targets.forEach((target) => {
      target.textContent = text;
    });
  };

  const syncOptionState = (checkbox) => {
    const option = checkbox.closest("[data-service-option]");
    const shell = option?.querySelector("[data-service-option-shell]");
    const icon = option?.querySelector("[data-service-check-icon]");
    const checked = checkbox.checked;

    option?.classList.toggle("is-selected", checked);
    shell?.classList.toggle("border-loomera-primary/30", checked);
    shell?.classList.toggle("bg-loomera-primarySoft", checked);
    shell?.classList.toggle("text-loomera-primaryText", checked);
    shell?.classList.toggle("bg-white", !checked);
    shell?.classList.toggle("text-loomera-textSecondary", !checked);
    icon?.classList.toggle("opacity-100", checked);
    icon?.classList.toggle("opacity-0", !checked);
  };

  const syncAllOptionStates = () => {
    serviceCheckboxes.forEach(syncOptionState);
  };

  const setCheckboxChecked = (checkbox, checked) => {
    if (checkbox.checked === checked) {
      syncOptionState(checkbox);
      return;
    }

    checkbox.checked = checked;
    checkbox.dispatchEvent(new Event("change", { bubbles: true }));
  };

  const setStepState = (stepName, isReady) => {
    const step = readinessSteps.find((item) => item.dataset.readinessStep === stepName);
    if (!step) return;

    const icon = step.querySelector("[data-readiness-step-icon]");
    step.classList.toggle("border-loomera-primary/25", isReady);
    step.classList.toggle("bg-loomera-primarySoft/25", isReady);

    if (icon) {
      icon.classList.toggle("bg-loomera-successSoft", isReady);
      icon.classList.toggle("text-loomera-success", isReady);
      icon.classList.toggle("bg-loomera-warningSoft", !isReady);
      icon.classList.toggle("text-loomera-warning", !isReady);
      icon.innerHTML = isReady
        ? '<i class="fa-solid fa-check" aria-hidden="true"></i>'
        : '<i class="fa-solid fa-circle-exclamation" aria-hidden="true"></i>';
    }
  };

  const syncServiceSummary = () => {
    const selectedCount = getSelectedServicesCount();
    const selectedGroups = getSelectedGroupsCount();

    selectedCountTargets.forEach((target) => {
      target.textContent = toPersianDigits(selectedCount);
    });

    selectedGroupsTargets.forEach((target) => {
      target.textContent = toPersianDigits(selectedGroups);
    });

    syncAllOptionStates();
    syncReadiness();
    refreshWorkspace();
  };

  const syncPreviewText = () => {
    const firstName = (nameInput?.value || "").trim();
    const lastName = (familyInput?.value || "").trim();
    const expert = (expertInput?.value || "").trim();

    const fullName = `${firstName} ${lastName}`.trim();
    setText(previewNames, fullName || "عضو جدید تیم");
    setText(previewSubtitles, expert || "بعد از ثبت، عضو به‌صورت فعال وارد محیط کاری تیم می‌شود.");

    const initials = `${firstName.slice(0, 1)}${lastName.slice(0, 1)}`.trim() || "عضو";
    previewInitialsTargets.forEach((target, index) => {
      const relatedImage = previewImages[index];
      if (!relatedImage || relatedImage.classList.contains("hidden")) {
        target.textContent = initials;
      }
    });

    syncReadiness();
  };

  const syncPreviewImage = () => {
    const file = profileImageInput?.files?.[0];

    if (previewObjectUrl) {
      URL.revokeObjectURL(previewObjectUrl);
      previewObjectUrl = "";
    }

    if (!file) {
      previewImages.forEach((image) => {
        image.src = "";
        image.classList.add("hidden");
      });
      previewInitialsTargets.forEach((target) => target.classList.remove("hidden"));
      syncPreviewText();
      return;
    }

    previewObjectUrl = URL.createObjectURL(file);
    previewImages.forEach((image) => {
      image.src = previewObjectUrl;
      image.classList.remove("hidden");
    });
    previewInitialsTargets.forEach((target) => target.classList.add("hidden"));
  };

  function syncReadiness() {
    const hasIdentity = Boolean(
      (nameInput?.value || "").trim() &&
        (familyInput?.value || "").trim() &&
        (mobileInput?.value || "").trim()
    );
    const hasProfile = Boolean((expertInput?.value || "").trim() || (descriptionInput?.value || "").trim());
    const hasServices = getSelectedServicesCount() > 0;
    const score = [hasIdentity, hasProfile, hasServices].filter(Boolean).length;

    readinessScoreTargets.forEach((target) => {
      target.textContent = `${toPersianDigits(score)}/۳`;
    });

    setStepState("identity", hasIdentity);
    setStepState("profile", hasProfile);
    setStepState("services", hasServices);

    if (readinessTitle) {
      readinessTitle.textContent =
        score === 3
          ? "عضو برای ثبت آماده است"
          : score === 2
            ? "تقریباً آماده ثبت"
            : "نیازمند تکمیل اطلاعات";
    }

    if (readinessDescription) {
      readinessDescription.textContent =
        score === 3
          ? "اطلاعات ضروری، پروفایل کاری و پوشش خدمات تکمیل شده‌اند. حالا می‌توانی عضو را ثبت کنی."
          : score === 2
            ? "بخش‌های اصلی تقریباً کامل هستند. مورد باقی‌مانده را تکمیل کن تا عضو با اصطکاک کمتر وارد برنامه‌ریزی شود."
            : "نام، نام خانوادگی، شماره موبایل و حداقل یک خدمت را تکمیل کن تا عضو برای ورود به برنامه‌ریزی آماده‌تر باشد.";
    }

    if (readinessPill) {
      readinessPill.classList.toggle("border-loomera-primary/15", score < 3);
      readinessPill.classList.toggle("bg-white", score < 3);
      readinessPill.classList.toggle("text-loomera-primaryText", score < 3);
      readinessPill.classList.toggle("border-loomera-success/20", score === 3);
      readinessPill.classList.toggle("bg-loomera-successSoft", score === 3);
      readinessPill.classList.toggle("text-loomera-success", score === 3);
      readinessPill.innerHTML =
        score === 3
          ? '<i class="fa-solid fa-check text-[10px]" aria-hidden="true"></i><span>آماده ثبت</span>'
          : '<i class="fa-solid fa-circle-info text-[10px]" aria-hidden="true"></i><span>در حال تکمیل</span>';
    }
  }

  serviceGroups.forEach((group) => {
    const selectAllButton = group.querySelector("[data-select-group]");
    const clearButton = group.querySelector("[data-clear-group]");
    const checkboxes = Array.from(group.querySelectorAll("[data-service-checkbox]"));

    selectAllButton?.addEventListener("click", (event) => {
      event.preventDefault();
      checkboxes.forEach((checkbox) => setCheckboxChecked(checkbox, true));
      syncServiceSummary();
    });

    clearButton?.addEventListener("click", (event) => {
      event.preventDefault();
      checkboxes.forEach((checkbox) => setCheckboxChecked(checkbox, false));
      syncServiceSummary();
    });
  });

  serviceCheckboxes.forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      syncOptionState(checkbox);
      syncServiceSummary();
    });
  });

  nameInput?.addEventListener("input", syncPreviewText);
  familyInput?.addEventListener("input", syncPreviewText);
  mobileInput?.addEventListener("input", syncReadiness);
  expertInput?.addEventListener("input", syncPreviewText);
  descriptionInput?.addEventListener("input", syncReadiness);
  profileImageInput?.addEventListener("change", syncPreviewImage);

  window.addEventListener("beforeunload", () => {
    if (previewObjectUrl) URL.revokeObjectURL(previewObjectUrl);
  });

  syncServiceSummary();
  syncPreviewText();
  syncPreviewImage();
  refreshWorkspace();
}
