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
  const count = document.getElementById("descriptionCurrentCount");
  const lengthLabels = Array.from(document.querySelectorAll("[data-description-length-label]"));
  const hintBox = document.getElementById("descriptionHintBox");
  const submitButtons = Array.from(
    document.querySelectorAll("#submitDescriptionBtn, #submitDescriptionHeroBtn")
  );

  if (!textarea || !hintBox) {
    console.warn("[salon_description_step] required DOM not found");
    return;
  }

  const maxLength = 600;

  function setHint(tone, message) {
    const baseClasses = ["mt-4", "rounded-2xl", "border", "px-4", "py-3", "text-xs", "font-black", "leading-6"];
    const toneClasses = {
      warning: ["border-loomera-warning/20", "bg-loomera-warningSoft", "text-loomera-warning"],
      success: ["border-loomera-success/20", "bg-loomera-successSoft", "text-loomera-success"],
      danger: ["border-loomera-danger/20", "bg-loomera-dangerSoft", "text-loomera-danger"],
    };
    hintBox.className = [...baseClasses, ...(toneClasses[tone] || toneClasses.warning)].join(" ");
    hintBox.textContent = message;
  }

  function updateState() {
    const value = textarea.value || "";
    const length = value.length;
    const lengthLabel = toPersianDigits(length);

    if (count) count.textContent = lengthLabel;
    setTextContent(lengthLabels, lengthLabel);

    const invalid = length === 0 || length > maxLength;
    submitButtons.forEach((button) => {
      button.classList.toggle("opacity-70", invalid);
      button.classList.toggle("cursor-not-allowed", invalid);
      button.disabled = invalid;
    });

    if (length === 0) {
      setHint("warning", "توضیحات مجموعه را وارد کن؛ محدودیت حداقلی وجود ندارد.");
    } else if (length <= maxLength) {
      setHint("success", "متن آماده ذخیره است.");
    } else {
      const extra = toPersianDigits(length - maxLength);
      setHint("danger", `متن از حداکثر ۶۰۰ کاراکتر عبور کرده است. ${extra} کاراکتر کم کن.`);
    }

    refreshWorkspace();
  }

  textarea.addEventListener("input", updateState);
  updateState();
  window.setTimeout(refreshWorkspace, 120);
}
