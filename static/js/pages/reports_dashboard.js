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
      console.warn("[reports] jalaliDatepicker init error", error);
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

  const initFilterDialog = () => {
    const modal = document.querySelector("[data-reports-filter-modal]");
    const taskTabs = document.querySelector('[data-lm-task-tabs-generated="reports"]');
    if (!modal || !taskTabs) return;

    const dialog = modal.querySelector('[role="dialog"]');
    const firstFocusable = modal.querySelector('input:not([type="hidden"]), select, button, a[href]');
    const count = Number.parseInt(document.body.dataset.reportsFilterCount || "0", 10) || 0;
    let lastFocused = null;

    let trigger = document.querySelector("[data-reports-filter-open]");
    if (!trigger) {
      trigger = document.createElement("button");
      trigger.type = "button";
      trigger.className = "lm-task-tab lm-reports-filter-tab";
      trigger.dataset.reportsFilterOpen = "";
      trigger.setAttribute("aria-haspopup", "dialog");
      trigger.setAttribute("aria-controls", modal.id || "reportsFilterModal");
      trigger.setAttribute("aria-label", count ? `فیلتر گزارش‌ها، ${count} فیلتر فعال` : "فیلتر گزارش‌ها");
      trigger.innerHTML = `
        <svg viewBox="0 0 24 24" class="h-4 w-4 shrink-0" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M4 6h16M7 12h10M10 18h4"/>
        </svg>
        <span>فیلتر</span>
        ${count ? `<span class="lm-reports-filter-count" aria-hidden="true">${count}</span>` : ""}
      `;

      const anchor = taskTabs.closest(".lm-task-tabs-anchor");
      if (anchor) {
        const shell = document.createElement("div");
        shell.className = "lm-reports-tabs-shell";
        shell.dataset.reportsTabsShell = "";
        anchor.replaceChildren(shell);
        shell.append(trigger, taskTabs);
      } else {
        taskTabs.parentNode?.insertBefore(trigger, taskTabs);
      }
    }

    const openModal = () => {
      lastFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      modal.classList.remove("hidden");
      modal.classList.add("flex");
      modal.setAttribute("aria-hidden", "false");
      document.documentElement.classList.add("overflow-hidden");
      window.requestAnimationFrame(() => firstFocusable?.focus({ preventScroll: true }));
    };

    const closeModal = () => {
      modal.classList.add("hidden");
      modal.classList.remove("flex");
      modal.setAttribute("aria-hidden", "true");
      document.documentElement.classList.remove("overflow-hidden");
      lastFocused?.focus?.({ preventScroll: true });
    };

    trigger?.addEventListener("click", openModal);
    modal.querySelectorAll("[data-reports-filter-close]").forEach((button) => {
      button.addEventListener("click", closeModal);
    });

    modal.addEventListener("click", (event) => {
      if (event.target === modal) closeModal();
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && modal.getAttribute("aria-hidden") === "false") {
        event.preventDefault();
        closeModal();
        return;
      }

      if (event.key !== "Tab" || modal.getAttribute("aria-hidden") !== "false" || !dialog) return;
      const focusable = Array.from(
        dialog.querySelectorAll('a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')
      ).filter((node) => node instanceof HTMLElement && !node.hidden && node.offsetParent !== null);
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });
  };

  initJalaliDatePicker();
  initAccordions();
  initFilterDialog();

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
