document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-help-open-assistant]").forEach((button) => {
    button.addEventListener("click", () => {
      document.dispatchEvent(new CustomEvent("loomera:help:ask", {
        detail: { message: button.dataset.helpQuestion || "" },
      }));
    });
  });

  document.querySelector("[data-help-assistant-restore]")?.addEventListener("click", () => {
    localStorage.removeItem("loomera.help-assistant.hidden");
    document.dispatchEvent(new CustomEvent("loomera:help:ask", { detail: { message: "" } }));
  });
});
