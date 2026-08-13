// static/js/pages/orders.js
import { initBookAgainButtons } from "../components/bookAgain.js";

function openDirectionsIntent(lat, lng, label = "سالن") {
  const safeLabel = encodeURIComponent(label);
  const androidUrl = `geo:0,0?q=${lat},${lng}(${safeLabel})`;
  const iosUrl = `maps://?daddr=${lat},${lng}&dirflg=d`;
  const webUrl = `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(`${lat},${lng}`)}`;

  const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
  const isAndroid = /Android/i.test(navigator.userAgent);

  if (isAndroid) {
    window.location.href = androidUrl;
    return;
  }

  if (isIOS) {
    window.location.href = iosUrl;
    return;
  }

  window.open(webUrl, "_blank", "noopener");
}

function initDirectionsButtons() {
  document.querySelectorAll('[data-action="open-directions"]').forEach((button) => {
    if (button.dataset.bound === "1") return;
    button.dataset.bound = "1";

    button.addEventListener("click", (event) => {
      event.preventDefault();
      const lat = Number(button.dataset.lat);
      const lng = Number(button.dataset.lng);
      const label = button.dataset.label || "سالن";
      if (Number.isNaN(lat) || Number.isNaN(lng)) {
        const fallbackHref = button.getAttribute("href");
        if (fallbackHref) window.open(fallbackHref, "_blank", "noopener");
        return;
      }
      openDirectionsIntent(lat, lng, label);
    });
  });
}

export default function initOrdersPage() {
  initBookAgainButtons();
  initDirectionsButtons();
}
