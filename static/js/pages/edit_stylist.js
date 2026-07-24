export default function initEditStylist() {
  const serviceCheckboxes = Array.from(document.querySelectorAll("[data-service-checkbox]"));
  const selectedCountTargets = Array.from(document.querySelectorAll("[data-selected-services-count]"));
  const selectedGroupsTargets = Array.from(document.querySelectorAll("[data-selected-groups-count]"));
  const serviceGroups = Array.from(document.querySelectorAll("[data-service-group]"));

  const nameInput = document.getElementById("id_name");
  const familyInput = document.getElementById("id_family");
  const mobileInput =
    document.getElementById("id_mobile_number") ||
    document.getElementById("id_mobile") ||
    document.querySelector("input[name='mobile_number'], input[name='mobile']");
  const expertInput = document.getElementById("id_expert");
  const descriptionInput =
    document.getElementById("id_description") || document.querySelector("textarea[name='description']");
  const profileImageInput = document.getElementById("id_profile_image");

  const previewName = document.querySelector("[data-stylist-preview-name]");
  const previewSubtitle = document.querySelector("[data-stylist-preview-subtitle]");
  const previewMobile = document.querySelector("[data-stylist-preview-mobile]");
  const previewInitials = document.querySelector("[data-stylist-preview-initials]");
  const previewImage = document.querySelector("[data-stylist-preview-image]");
  const readinessTitle = document.querySelector("[data-edit-stylist-readiness-title]");
  const readinessDescription = document.querySelector("[data-edit-stylist-readiness-description]");
  const readinessScoreTargets = Array.from(document.querySelectorAll("[data-readiness-score]"));
  const readinessPill = document.querySelector("[data-edit-stylist-readiness-pill]");
  const readinessSteps = Array.from(document.querySelectorAll("[data-readiness-step]"));
  let previewObjectUrl = "";

  if (typeof jalaliDatepicker !== "undefined" && document.querySelector(".datepicker")) {
    try {
      jalaliDatepicker.startWatch({
        selector: ".datepicker",
        autoHide: true,
      });
    } catch (error) {
      console.warn("[edit-stylist] jalaliDatepicker initialization failed");
    }
  }

  const toPersianDigits = (value) =>
    String(value).replace(/\d/g, (digit) => "۰۱۲۳۴۵۶۷۸۹"[Number(digit)]);

  const getSelectedServicesCount = () =>
    serviceCheckboxes.filter((checkbox) => checkbox.checked).length;

  const getSelectedGroupsCount = () => {
    let selectedGroups = 0;

    serviceGroups.forEach((group) => {
      const groupChecked = group.querySelectorAll("[data-service-checkbox]:checked").length;
      if (groupChecked > 0) selectedGroups += 1;
    });

    return selectedGroups;
  };

  const setServiceCardState = (checkbox) => {
    const option = checkbox.closest("[data-service-option]");
    const card = option?.querySelector("[data-service-card]");
    const icon = option?.querySelector("[data-service-check-icon]");
    const selectedLabel = option?.querySelector("[data-service-selected-label]");
    const isChecked = checkbox.checked;

    if (!card) return;

    card.classList.toggle("border-loomera-primary/40", isChecked);
    card.classList.toggle("bg-loomera-primarySoft", isChecked);
    card.classList.toggle("text-loomera-primaryText", isChecked);
    card.classList.toggle("shadow-lm-soft", isChecked);

    card.classList.toggle("border-loomera-borderSoft", !isChecked);
    card.classList.toggle("bg-white", !isChecked);
    card.classList.toggle("text-loomera-textSecondary", !isChecked);

    if (icon) {
      icon.classList.toggle("scale-100", isChecked);
      icon.classList.toggle("scale-90", !isChecked);
      icon.classList.toggle("border-loomera-primary", isChecked);
      icon.classList.toggle("bg-loomera-primary", isChecked);
      icon.classList.toggle("text-white", isChecked);
      icon.classList.toggle("opacity-100", isChecked);

      icon.classList.toggle("border-loomera-borderSoft", !isChecked);
      icon.classList.toggle("bg-white", !isChecked);
      icon.classList.toggle("text-transparent", !isChecked);
      icon.classList.toggle("opacity-60", !isChecked);
    }

    if (selectedLabel) {
      selectedLabel.classList.toggle("hidden", !isChecked);
    }

    checkbox.setAttribute("aria-checked", isChecked ? "true" : "false");
  };


const syncServiceCards = () => {
  serviceCheckboxes.forEach(setServiceCardState);
};

  const refreshWorkspace = () => {
    if (window.LoomeraDashboardWorkspace?.refreshAll) {
      window.requestAnimationFrame(() => window.LoomeraDashboardWorkspace.refreshAll());
    }
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

    syncServiceCards();
    syncReadiness();
    refreshWorkspace();
  };

  const syncPreviewText = () => {
    const firstName = (nameInput?.value || "").trim();
    const lastName = (familyInput?.value || "").trim();
    const expert = (expertInput?.value || "").trim();
    const mobile = (mobileInput?.value || "").trim();

    const fullName = `${firstName} ${lastName}`.trim();
    if (previewName) {
      previewName.textContent = fullName || "عضو تیم";
    }

    if (previewSubtitle) {
      previewSubtitle.textContent = expert || "بدون تخصص ثبت‌شده";
    }

    if (previewMobile) {
      previewMobile.textContent = mobile || "شماره تماس ثبت نشده";
    }

    if (previewInitials && previewImage?.classList.contains("hidden")) {
      const initials = `${firstName.slice(0, 1)}${lastName.slice(0, 1)}`.trim();
      previewInitials.textContent = initials || "عضو";
    }

    syncReadiness();
  };

  const syncPreviewImage = () => {
    const file = profileImageInput?.files?.[0];
    if (!previewImage || !previewInitials) return;

    if (previewObjectUrl) {
      URL.revokeObjectURL(previewObjectUrl);
      previewObjectUrl = "";
    }

    if (!file) {
      if (previewImage.dataset.originalSrc) {
        previewImage.src = previewImage.dataset.originalSrc;
        previewImage.classList.remove("hidden");
        previewInitials.classList.add("hidden");
      } else if (!previewImage.getAttribute("src")) {
        previewImage.src = "";
        previewImage.classList.add("hidden");
        previewInitials.classList.remove("hidden");
      }
      syncPreviewText();
      return;
    }

    previewObjectUrl = URL.createObjectURL(file);
    previewImage.src = previewObjectUrl;
    previewImage.classList.remove("hidden");
    previewInitials.classList.add("hidden");
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
          ? "پروفایل عضو آماده و پایدار است"
          : score === 2
            ? "پروفایل تقریباً کامل است"
            : "نیازمند بازبینی اطلاعات";
    }

    if (readinessDescription) {
      readinessDescription.textContent =
        score === 3
          ? "اطلاعات ضروری، پروفایل کاری و پوشش خدمات کامل هستند. می‌توانی تغییرات را با اطمینان ذخیره کنی."
          : score === 2
            ? "بخش‌های اصلی تقریباً کامل هستند. مورد باقی‌مانده را اصلاح کن تا عضو در رزروها و برنامه‌ریزی پایدارتر باشد."
            : "اطلاعات ضروری، پروفایل کاری و حداقل یک خدمت را بررسی کن تا این عضو بدون اختلال در رزروها فعال بماند.";
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
          ? '<i class="fa-solid fa-check text-[10px]" aria-hidden="true"></i><span>آماده ذخیره</span>'
          : '<i class="fa-solid fa-circle-info text-[10px]" aria-hidden="true"></i><span>در حال تکمیل</span>';
    }
  }

  if (previewImage?.getAttribute("src")) {
    previewImage.dataset.originalSrc = previewImage.getAttribute("src");
  }

  serviceGroups.forEach((group) => {
    const selectAllButton = group.querySelector("[data-select-group]");
    const clearButton = group.querySelector("[data-clear-group]");
    const checkboxes = Array.from(group.querySelectorAll("[data-service-checkbox]"));

    selectAllButton?.addEventListener("click", () => {
      checkboxes.forEach((checkbox) => {
        checkbox.checked = true;
      });
      syncServiceSummary();
    });

    clearButton?.addEventListener("click", () => {
      checkboxes.forEach((checkbox) => {
        checkbox.checked = false;
      });
      syncServiceSummary();
    });
  });

  serviceCheckboxes.forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      setServiceCardState(checkbox);
      syncServiceSummary();
    });
  });

  nameInput?.addEventListener("input", syncPreviewText);
  familyInput?.addEventListener("input", syncPreviewText);
  mobileInput?.addEventListener("input", syncPreviewText);
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
