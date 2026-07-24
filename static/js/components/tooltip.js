export default function initTooltips(scope = document) {
  const wrappers = Array.from(scope.querySelectorAll("[data-tooltip-toggle='true']"));

  const closeTooltip = (wrapper) => {
    const button = wrapper.querySelector("button");
    const panel = wrapper.querySelector(".tooltip-panel");
    if (!button || !panel) return;

    panel.classList.add("opacity-0", "pointer-events-none");
    panel.classList.remove("opacity-100", "pointer-events-auto");
    button.setAttribute("aria-expanded", "false");
    wrapper.dataset.tooltipOpen = "0";
  };

  const openTooltip = (wrapper) => {
    const button = wrapper.querySelector("button");
    const panel = wrapper.querySelector(".tooltip-panel");
    if (!button || !panel) return;

    wrappers.forEach((item) => {
      if (item !== wrapper) closeTooltip(item);
    });

    panel.classList.remove("opacity-0", "pointer-events-none");
    panel.classList.add("opacity-100", "pointer-events-auto");
    button.setAttribute("aria-expanded", "true");
    wrapper.dataset.tooltipOpen = "1";
  };

  wrappers.forEach((wrapper) => {
    if (wrapper.dataset.tooltipBound === "1") return;
    wrapper.dataset.tooltipBound = "1";

    const button = wrapper.querySelector("button");
    const panel = wrapper.querySelector(".tooltip-panel");
    if (!button || !panel) return;

    wrapper.addEventListener("mouseenter", () => openTooltip(wrapper));
    wrapper.addEventListener("mouseleave", () => closeTooltip(wrapper));

    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();

      if (wrapper.dataset.tooltipOpen === "1") {
        closeTooltip(wrapper);
      } else {
        openTooltip(wrapper);
      }
    });

    button.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        closeTooltip(wrapper);
        button.focus();
      }
    });
  });

  if (document.body.dataset.tooltipDocumentBound !== "1") {
    document.body.dataset.tooltipDocumentBound = "1";

    document.addEventListener("click", (event) => {
      wrappers.forEach((wrapper) => {
        if (!wrapper.contains(event.target)) {
          closeTooltip(wrapper);
        }
      });
    });

    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      wrappers.forEach(closeTooltip);
    });
  }
}