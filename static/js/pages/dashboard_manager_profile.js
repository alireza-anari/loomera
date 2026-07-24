let dashboardManagerProfileBound = false;

const PERSIAN_DIGITS = ["۰", "۱", "۲", "۳", "۴", "۵", "۶", "۷", "۸", "۹"];

const toPersianDigits = (value) =>
  String(value ?? "").replace(
    /\d/g,
    (digit) => PERSIAN_DIGITS[Number(digit)] || digit,
  );

const setText = (element, value) => {
  if (!element) return;
  element.textContent = value;
};

const setStatusBadge = (
  element,
  isReady,
  readyText = "تکمیل",
  missingText = "نیازمند تکمیل",
) => {
  if (!element) return;

  element.textContent = isReady ? readyText : missingText;
  element.classList.toggle("bg-loomera-successSoft", isReady);
  element.classList.toggle("text-loomera-success", isReady);
  element.classList.toggle("bg-loomera-warningSoft", !isReady);
  element.classList.toggle("text-loomera-warning", !isReady);
};

const refreshWorkspace = () => {
  window.LoomeraDashboardWorkspace?.refreshAll?.();
};

export default function initDashboardManagerProfile() {
  if (dashboardManagerProfileBound) return;
  dashboardManagerProfileBound = true;

  const form = document.querySelector("[data-manager-profile-form]");
  if (!form) return;

  const imageInput = document.getElementById("managerProfileImageInput");
  const avatarPreview = document.querySelector("[data-manager-avatar-preview]");

  const nameInput = form.querySelector('[name="name"]');
  const familyInput = form.querySelector('[name="family"]');
  const emailInput = form.querySelector('[name="email"]');
  const mobileInput = form.querySelector('[name="mobile_number"]');
  const salonPhoneInput = form.querySelector('[name="salon_number"]');
  const addressInput = form.querySelector('[name="address"]');

  const readinessPercent = document.querySelector(
    "[data-manager-readiness-percent]",
  );
  const readinessBar = document.querySelector("[data-manager-readiness-bar]");
  const readinessText = document.querySelector("[data-manager-readiness-text]");
  const reviewTitle = document.querySelector("[data-manager-review-title]");
  const reviewDescription = document.querySelector(
    "[data-manager-review-description]",
  );
  const imageStatus = document.querySelector("[data-manager-image-status]");

  const previewName = document.querySelector("[data-manager-preview-name]");
  const previewEmail = document.querySelector("[data-manager-preview-email]");
  const previewMobile = document.querySelector("[data-manager-preview-mobile]");
  const previewSalonPhone = document.querySelector(
    "[data-manager-preview-salon-phone]",
  );

  const statusName = document.querySelector("[data-manager-status-name]");
  const statusEmail = document.querySelector("[data-manager-status-email]");
  const statusSalonPhone = document.querySelector(
    "[data-manager-status-salon-phone]",
  );
  const statusImage = document.querySelector("[data-manager-status-image]");

  let hasImage = form.dataset.managerHasImage === "true";

  const getValue = (input) => (input?.value || "").trim();

  const getFullName = () => {
    const parts = [getValue(nameInput), getValue(familyInput)].filter(Boolean);
    return parts.join(" ") || "مدیر سالن";
  };

  const updatePreview = () => {
    setText(previewName, getFullName());
    setText(previewEmail, getValue(emailInput) || "ثبت نشده");
    setText(previewMobile, getValue(mobileInput) || "ثبت نشده");
    setText(previewSalonPhone, getValue(salonPhoneInput) || "ثبت نشده");
  };

  const updateReadiness = () => {
    const checks = [
      Boolean(getValue(nameInput) && getValue(familyInput)),
      Boolean(getValue(emailInput)),
      Boolean(getValue(salonPhoneInput)),
      hasImage,
    ];
    const readyCount = checks.filter(Boolean).length;
    const percent = Math.round((readyCount / checks.length) * 100);

    setText(readinessPercent, `${toPersianDigits(percent)}٪`);
    if (readinessBar) readinessBar.style.width = `${percent}%`;

    setStatusBadge(statusName, checks[0]);
    setStatusBadge(statusEmail, checks[1]);
    setStatusBadge(statusSalonPhone, checks[2]);
    setStatusBadge(statusImage, checks[3], "ثبت شده", "بدون تصویر");
    setText(imageStatus, checks[3] ? "ثبت شده" : "نیازمند آپلود");

    if (percent === 100) {
      setText(
        readinessText,
        "پروفایل مدیر کامل است و برای استفاده روزانه آماده است.",
      );
      setText(reviewTitle, "آماده ذخیره و استفاده");
      setText(
        reviewDescription,
        "همه اطلاعات کلیدی تکمیل شده‌اند. در صورت تغییر، ذخیره را بزن.",
      );
    } else if (percent >= 70) {
      setText(
        readinessText,
        "پروفایل تقریباً آماده است؛ فقط چند مورد تکمیلی باقی مانده.",
      );
      setText(reviewTitle, "تقریباً آماده");
      setText(
        reviewDescription,
        "قبل از ذخیره، موارد باقی‌مانده در چک‌لیست را بررسی کن.",
      );
    } else {
      setText(
        readinessText,
        "برای آماده شدن پروفایل، نام، ایمیل، شماره سالن و تصویر را تکمیل کن.",
      );
      setText(reviewTitle, "نیازمند تکمیل");
      setText(
        reviewDescription,
        "اطلاعات کلیدی هنوز کامل نیستند؛ بهتر است قبل از ذخیره آن‌ها را تکمیل کنی.",
      );
    }
  };

  const updateAll = () => {
    updatePreview();
    updateReadiness();
    refreshWorkspace();
  };

  imageInput?.addEventListener("change", function () {
    const file = this.files?.[0];
    if (!file || !avatarPreview) return;

    const reader = new FileReader();
    reader.onload = function (event) {
      const src = event.target?.result;
      if (!src) return;

      const previousPreview = avatarPreview.querySelector(
        "#managerProfileImagePreview",
      );
      previousPreview?.remove();

      const img = document.createElement("img");
      img.src = src;
      img.alt = "پیش‌نمایش تصویر پروفایل مدیر";
      img.className =
        "h-28 w-28 rounded-full border-4 border-white object-cover shadow-lm-card";
      img.id = "managerProfileImagePreview";
      avatarPreview.prepend(img);

      hasImage = true;
      form.dataset.managerHasImage = "true";
      updateAll();
    };

    reader.readAsDataURL(file);
  });

  [
    nameInput,
    familyInput,
    emailInput,
    mobileInput,
    salonPhoneInput,
    addressInput,
  ].forEach((input) => {
    input?.addEventListener("input", updateAll);
    input?.addEventListener("change", updateAll);
  });

  updateAll();
}

initDashboardManagerProfile();
