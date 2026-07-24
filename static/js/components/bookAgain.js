// static/js/components/bookAgain.js

export function initBookAgainButtons() {
  document.addEventListener("click", (e) => {
    const btn = e.target.closest(".btn-book-again");
    if (!btn) return;

    const rebookUrl =
      btn.dataset.rebookUrl ||
      btn.getAttribute("href") ||
      (btn.dataset.orderId ? `/orders/rebook/${btn.dataset.orderId}/` : "");

    if (!rebookUrl) return;

    if (btn.tagName === "A" && btn.getAttribute("href") === rebookUrl) {
      return;
    }

    window.location.href = rebookUrl;
  });
}
