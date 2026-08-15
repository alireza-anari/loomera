function normalizePickerLayer() {
  document
    .querySelectorAll(".jdp-popover, .jdp-container, .jalali-datepicker, [data-jdp-container]")
    .forEach((picker) => {
      picker.style.zIndex = "99999";
    });
}

export default function initLoomeraDatepickers(root = document) {
  const scope = root instanceof Element || root === document ? root : document;
  const selector = "[data-jdp], [data-jalali-date], input.datepicker";
  const inputs = Array.from(scope.querySelectorAll(selector));
  if (!inputs.length || typeof window.jalaliDatepicker === "undefined") return;

  inputs.forEach((input) => {
    if (!(input instanceof HTMLInputElement)) return;
    input.setAttribute("autocomplete", input.getAttribute("autocomplete") || "off");
    input.setAttribute("inputmode", input.getAttribute("inputmode") || "numeric");
    if (!input.getAttribute("placeholder")) {
      input.setAttribute("placeholder", "مثلاً ۱۴۰۵/۰۱/۰۱");
    }
  });

  try {
    window.jalaliDatepicker.startWatch({
      selector,
      autoHide: true,
      hideAfterChange: true,
    });
    setTimeout(normalizePickerLayer, 0);
  } catch (error) {
    console.warn("[loomera-datepickers] init warning", error);
  }

  inputs.forEach((input) => {
    if (input.dataset.loomeraDatepickerBound === "true") return;
    input.dataset.loomeraDatepickerBound = "true";
    ["focus", "click", "input"].forEach((eventName) => {
      input.addEventListener(eventName, () => setTimeout(normalizePickerLayer, 0), { passive: true });
    });
  });
}
