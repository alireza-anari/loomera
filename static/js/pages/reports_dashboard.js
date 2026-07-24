export default function initReportsDashboard() {
  const MOBILE_ACCORDION_SHELL_CLASS =
    "rounded-[28px] border border-slate-200 bg-white p-4 shadow-sm";

  const MOBILE_ACCORDION_TOGGLE_CLASS =
    "flex w-full items-center justify-between rounded-[20px] border border-slate-200 bg-slate-50 px-4 py-3 text-right text-sm font-black text-slate-900 lg:hidden";

  const MOBILE_ACCORDION_BODY_CLASS = "mt-4";

  const initJalaliDatePicker = () => {
    const dateInputs = document.querySelectorAll("[data-jalali-date]");
    if (!dateInputs.length || typeof jalaliDatepicker === "undefined") {
      return;
    }

    try {
      jalaliDatepicker.startWatch({
        selector: "[data-jalali-date]",
        autoHide: true,
        minDate: "attr",
        maxDate: "attr",
      });
    } catch (error) {
      console.warn("[reports] jalaliDatepicker initialization failed");
    }
  };

  const setAccordionState = (section, expanded, isMobile) => {
    const toggle = section.querySelector("[data-accordion-toggle]");
    const body = section.querySelector("[data-accordion-body]");
    const icon = toggle?.querySelector("i");

    if (!toggle || !body) return;

    if (!section.dataset.originalClassNameCaptured) {
      section.dataset.originalClassName = section.className || "";
      section.dataset.originalClassNameCaptured = "true";
    }

    if (!isMobile) {
      section.className = section.dataset.originalClassName || "";
      toggle.classList.add("hidden");
      body.hidden = false;
      body.classList.remove(...MOBILE_ACCORDION_BODY_CLASS.split(" "));
      icon?.classList.remove("rotate-180");
      return;
    }

    section.className = MOBILE_ACCORDION_SHELL_CLASS;
    toggle.className = MOBILE_ACCORDION_TOGGLE_CLASS;
    body.classList.add(...MOBILE_ACCORDION_BODY_CLASS.split(" "));
    toggle.classList.remove("hidden");
    body.hidden = !expanded;
    icon?.classList.toggle("rotate-180", expanded);
    section.dataset.expanded = expanded ? "true" : "false";
  };

  const initAccordions = () => {
    const isMobile = window.innerWidth < 1024;
    const sections = Array.from(document.querySelectorAll("[data-mobile-accordion]"));

    sections.forEach((section, index) => {
      if (section.dataset.accordionReady !== "true") {
        const label = section.dataset.mobileAccordion || "بخش";
        const body = document.createElement("div");
        body.setAttribute("data-accordion-body", "");

        while (section.firstChild) {
          body.appendChild(section.firstChild);
        }

        const toggle = document.createElement("button");
        toggle.type = "button";
        toggle.setAttribute("data-accordion-toggle", "");
        toggle.className = MOBILE_ACCORDION_TOGGLE_CLASS;
        toggle.innerHTML = `
          <span>${label}</span>
          <i class="fa-solid fa-chevron-down text-xs transition-transform duration-200"></i>
        `;

        section.appendChild(toggle);
        section.appendChild(body);

        const defaultExpanded =
          section.dataset.mobileAccordionOpen === "true" || index === 0;

        section.dataset.expanded = defaultExpanded ? "true" : "false";
        section.dataset.accordionReady = "true";

        toggle.addEventListener("click", () => {
          const expanded = section.dataset.expanded === "true";
          setAccordionState(section, !expanded, true);
        });
      }

      setAccordionState(
        section,
        section.dataset.expanded === "true",
        isMobile
      );
    });
  };

  initJalaliDatePicker();
  initAccordions();

  if (!window.__reportsDashboardResizeBound) {
    window.__reportsDashboardResizeBound = true;
    window.addEventListener(
      "resize",
      () => {
        initAccordions();
      },
      { passive: true }
    );
  }
}