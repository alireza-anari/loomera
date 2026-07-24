let salonDescriptionStepBound = false;

function toPersianDigits(value) {
  const fa = "۰۱۲۳۴۵۶۷۸۹";
  return String(value).replace(/\d/g, (digit) => fa[digit]);
}

function setTextContent(elements, value) {
  elements.forEach((element) => {
    element.textContent = value;
  });
}

function refreshWorkspace() {
  window.LoomeraDashboardWorkspace?.refresh?.(document);
}

export default function initSalonDescriptionStep() {
  if (salonDescriptionStepBound) return;
  salonDescriptionStepBound = true;

  const textarea = document.getElementById("id_description");
  const preview = document.getElementById("descriptionPreviewText");
  const count = document.getElementById("descriptionCurrentCount");
  const lengthLabels = Array.from(document.querySelectorAll("[data-description-length-label]"));
  const progressBars = Array.from(document.querySelectorAll("[data-description-progress-bar]"));
  const progressText = document.querySelector("[data-description-progress-text]");
  const hintBox = document.getElementById("descriptionHintBox");
  const statusTitle = document.querySelector("[data-description-status-title]");
  const statusText = document.querySelector("[data-description-status-text]");
  const submitButtons = Array.from(
    document.querySelectorAll("#submitDescriptionBtn, #submitDescriptionHeroBtn")
  );
  const chipButtons = Array.from(document.querySelectorAll("[data-description-chip]"));

  if (!textarea || !preview || !hintBox) {
    console.warn("[salon_description_step] required DOM not found");
    return;
  }

  const minLength = 200;
  const maxLength = 600;

  function setHint(tone, message) {
    const baseClasses = ["mt-4", "rounded-2xl", "border", "px-4", "py-3", "text-xs", "font-black", "leading-6"];
    const toneClasses = {
      warning: ["border-loomera-warning/20", "bg-loomera-warningSoft", "text-loomera-warning"],
      success: ["border-loomera-success/20", "bg-loomera-successSoft", "text-loomera-success"],
      danger: ["border-loomera-danger/20", "bg-loomera-dangerSoft", "text-loomera-danger"],
      primary: ["border-loomera-primary/15", "bg-loomera-primarySoft", "text-loomera-primaryText"],
    };

    hintBox.className = [...baseClasses, ...(toneClasses[tone] || toneClasses.primary)].join(" ");
    hintBox.textContent = message;
  }

  function updateState() {
    const value = textarea.value || "";
    const length = value.length;
    const lengthLabel = toPersianDigits(length);
    const percent = Math.min(Math.round((length / maxLength) * 100), 100);

    if (count) count.textContent = lengthLabel;
    setTextContent(lengthLabels, lengthLabel);
    preview.textContent = value.trim() || "هنوز متنی وارد نشده است.";

    progressBars.forEach((bar) => {
      bar.style.width = `${percent}%`;
    });
    if (progressText) progressText.textContent = `${toPersianDigits(percent)}٪`;

    submitButtons.forEach((button) => {
      button.classList.toggle("opacity-70", length > maxLength);
      button.classList.toggle("cursor-not-allowed", length > maxLength);
      button.disabled = length > maxLength;
    });

    if (length === 0) {
      if (statusTitle) statusTitle.textContent = "متن معرفی را کامل کن";
      if (statusText) statusText.textContent = "برای ادامه، متن معرفی باید حداقل ۲۰۰ کاراکتر داشته باشد.";
      setHint("warning", "برای ادامه، توضیحات باید حداقل ۲۰۰ کاراکتر داشته باشد.");
      refreshWorkspace();
      return;
    }

    if (length < minLength) {
      const remaining = toPersianDigits(minLength - length);
      if (statusTitle) statusTitle.textContent = "متن هنوز کوتاه است";
      if (statusText) statusText.textContent = `هنوز ${remaining} کاراکتر دیگر لازم است تا متن به حداقل برسد.`;
      setHint("warning", `هنوز ${remaining} کاراکتر دیگر لازم داری تا متن به حداقل برسد.`);
      refreshWorkspace();
      return;
    }

    if (length <= maxLength) {
      if (statusTitle) statusTitle.textContent = "متن آماده ذخیره است";
      if (statusText) statusText.textContent = "متن از نظر تعداد کاراکتر در وضعیت مناسبی قرار دارد. یک بار آن را از نگاه مشتری مرور کن.";
      setHint("success", "متن از نظر تعداد کاراکتر در وضعیت مناسبی قرار دارد.");
      refreshWorkspace();
      return;
    }

    const extra = toPersianDigits(length - maxLength);
    if (statusTitle) statusTitle.textContent = "متن بیش از حد بلند است";
    if (statusText) statusText.textContent = `متن از سقف مجاز عبور کرده است. ${extra} کاراکتر کم کن.`;
    setHint("danger", `متن از حداکثر مجاز عبور کرده است. ${extra} کاراکتر کم کن.`);
    refreshWorkspace();
  }

  function appendChipText(text) {
    const snippet = (text || "").trim();
    if (!snippet) return;

    const current = textarea.value.trim();
    textarea.value = current ? `${textarea.value}${current.endsWith(" ") ? "" : " "}${snippet}` : snippet;
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
    textarea.focus();
    textarea.setSelectionRange(textarea.value.length, textarea.value.length);
  }

  textarea.addEventListener("input", updateState);

  chipButtons.forEach((button) => {
    button.addEventListener("click", () => appendChipText(button.dataset.descriptionChip || ""));
  });

  updateState();
  window.setTimeout(refreshWorkspace, 120);
}