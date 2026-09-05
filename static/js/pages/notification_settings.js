// static/js/pages/notification_settings.js

const SWITCH_ON_CLASSES = ["border-loomera-primary", "bg-loomera-primary"];
const SWITCH_OFF_CLASSES = ["border-loomera-primary/25", "bg-loomera-primarySoft/70"];
const KNOB_ON_CLASSES = ["translate-x-6", "border-white/80", "bg-loomera-accent"];
const KNOB_OFF_CLASSES = ["translate-x-0", "border-loomera-primary", "bg-loomera-primary"];

function getCookie(name) {
  let cookieValue = null;
  if (!document.cookie) return cookieValue;

  const cookies = document.cookie.split(";");
  for (const cookie of cookies) {
    const trimmed = cookie.trim();
    if (trimmed.substring(0, name.length + 1) === `${name}=`) {
      cookieValue = decodeURIComponent(trimmed.substring(name.length + 1));
      break;
    }
  }

  return cookieValue;
}

function getCsrfToken() {
  return document.querySelector("[name=csrfmiddlewaretoken]")?.value || getCookie("csrftoken") || "";
}

function getToggleParts(toggle) {
  const label = toggle.nextElementSibling;
  const knob = label?.querySelector(".notification-switch-knob");
  return { label, knob };
}

function toggleClasses(element, classNames, enabled) {
  if (!element) return;
  classNames.forEach((className) => element.classList.toggle(className, enabled));
}

function setToggleVisualState(toggle, isChecked) {
  const { label, knob } = getToggleParts(toggle);
  if (!label || !knob) return;

  label.classList.toggle("opacity-60", toggle.disabled);
  label.classList.toggle("cursor-not-allowed", toggle.disabled);
  label.classList.toggle("cursor-pointer", !toggle.disabled);

  toggleClasses(label, SWITCH_ON_CLASSES, isChecked);
  toggleClasses(label, SWITCH_OFF_CLASSES, !isChecked);
  toggleClasses(knob, KNOB_ON_CLASSES, isChecked);
  toggleClasses(knob, KNOB_OFF_CLASSES, !isChecked);
}

function setStatus(message, type = "success") {
  const feedback = window.LoomeraFeedback;
  if (!feedback) return;
  if (type === "error") feedback.error(message);
  else feedback.success(message);
}

async function saveNotificationSetting(fieldName, isChecked) {
  const response = await fetch("/accounts/api/update-notification-settings/", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCsrfToken(),
      "X-Requested-With": "XMLHttpRequest",
    },
    body: JSON.stringify({ [fieldName]: isChecked }),
  });

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  return response.json().catch(() => ({}));
}

export default function initNotificationSettings() {
  const toggles = Array.from(document.querySelectorAll(".notification-toggle"));

  toggles.forEach((toggle) => {
    setToggleVisualState(toggle, toggle.checked);

    if (toggle.dataset.bound === "1") return;
    toggle.dataset.bound = "1";

    toggle.addEventListener("change", async function handleNotificationToggleChange() {
      const fieldName = this.getAttribute("data-field");
      const nextChecked = this.checked;
      const previousChecked = !nextChecked;

      if (!fieldName || this.dataset.loading === "1") return;

      this.dataset.loading = "1";
      this.disabled = true;
      setToggleVisualState(this, nextChecked);

      try {
        await saveNotificationSetting(fieldName, nextChecked);
        setStatus("تنظیمات اعلان ذخیره شد.");
      } catch (error) {
        console.error("[notification_settings] save failed", error);

        this.checked = previousChecked;
        setToggleVisualState(this, previousChecked);
        setStatus("خطا در ذخیره تنظیمات. لطفاً دوباره تلاش کنید.", "error");
      } finally {
        delete this.dataset.loading;
        this.disabled = false;
        setToggleVisualState(this, this.checked);
      }
    });
  });
}
