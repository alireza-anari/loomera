export default function initAppointmentsManagement() {
  const pageState = {
    controller: null,
  };

  const MOBILE_ACCORDION_SHELL_CLASS =
    "rounded-[28px] border border-loomera-borderSoft bg-white/95 p-4 shadow-lm-card";

  const MOBILE_ACCORDION_TOGGLE_CLASS =
    "flex w-full items-center justify-between rounded-[20px] border border-loomera-borderSoft bg-loomera-bgSubtle px-4 py-3 text-right text-sm font-black text-loomera-textPrimary lg:hidden";

  const MOBILE_ACCORDION_BODY_CLASS = "mt-4";

  const initJalaliDatePicker = () => {
    const dateInputs = document.querySelectorAll("[data-jalali-date]");
    if (!dateInputs.length || typeof jalaliDatepicker === "undefined") return;

    try {
      jalaliDatepicker.startWatch({
        selector: "[data-jalali-date]",
        autoHide: true,
        minDate: "attr",
        maxDate: "attr",
      });
    } catch (error) {
      console.warn("[appointments] jalaliDatepicker initialization failed");
    }
  };

  const isMobileViewport = () => window.innerWidth < 1024;

  const initFilterModal = (root = document) => {
    const modal = root.querySelector("[data-appointments-filter-modal]");
    const openButtons = Array.from(root.querySelectorAll("[data-appointments-filter-open]"));
    const closeButtons = modal ? Array.from(modal.querySelectorAll("[data-appointments-filter-close]")) : [];

    if (!modal || !openButtons.length) return;

    const openModal = () => {
      modal.classList.remove("hidden");
      modal.setAttribute("aria-hidden", "false");
      document.body.classList.add("overflow-hidden");
      window.setTimeout(() => {
        modal.querySelector("input, select, button")?.focus?.();
      }, 40);
    };

    const closeModal = () => {
      modal.classList.add("hidden");
      modal.setAttribute("aria-hidden", "true");
      document.body.classList.remove("overflow-hidden");
    };

    openButtons.forEach((button) => {
      if (button.dataset.filterModalBound === "true") return;
      button.dataset.filterModalBound = "true";
      button.addEventListener("click", openModal);
    });

    closeButtons.forEach((button) => {
      if (button.dataset.filterModalBound === "true") return;
      button.dataset.filterModalBound = "true";
      button.addEventListener("click", closeModal);
    });

    if (modal.dataset.escapeBound !== "true") {
      modal.dataset.escapeBound = "true";
      document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && !modal.classList.contains("hidden")) {
          closeModal();
        }
      });
    }
  };

  const forceCloseFilterModal = (root = document) => {
    const scope = root instanceof Element ? root : document;
    const modals = Array.from(scope.querySelectorAll("[data-appointments-filter-modal]"));

    if (scope.matches?.("[data-appointments-filter-modal]")) {
      modals.push(scope);
    }

    modals.forEach((modal) => {
      modal.classList.add("hidden");
      modal.setAttribute("aria-hidden", "true");
    });

    document.body.classList.remove("overflow-hidden");
  };

  const initBulkSelection = (root = document) => {
    const checkboxes = Array.from(root.querySelectorAll("[data-appointment-checkbox]"));
    const selectAllToggles = Array.from(root.querySelectorAll("[data-select-all]"));
    const bulkBar = root.querySelector("[data-bulk-bar]");
    const countTarget = root.querySelector("[data-selected-count]");

    if (!checkboxes.length || !bulkBar || !countTarget) return;

    const selectedCount = () => checkboxes.filter((checkbox) => checkbox.checked).length;

    const syncSelectAllState = () => {
      const count = selectedCount();
      const allChecked = count > 0 && count === checkboxes.length;

      selectAllToggles.forEach((toggle) => {
        toggle.checked = allChecked;
        toggle.indeterminate = count > 0 && count < checkboxes.length;
      });

      if (count > 0) {
        bulkBar.classList.remove("hidden");
        bulkBar.classList.add("flex");
      } else {
        bulkBar.classList.remove("flex");
        bulkBar.classList.add("hidden");
      }

      countTarget.textContent = String(count);
    };

    selectAllToggles.forEach((toggle) => {
      if (toggle.dataset.bound === "true") return;
      toggle.dataset.bound = "true";

      toggle.addEventListener("change", (event) => {
        const checked = event.target.checked;
        checkboxes.forEach((checkbox) => {
          checkbox.checked = checked;
        });
        syncSelectAllState();
      });
    });

    checkboxes.forEach((checkbox) => {
      if (checkbox.dataset.bound === "true") return;
      checkbox.dataset.bound = "true";
      checkbox.addEventListener("change", syncSelectAllState);
    });

    syncSelectAllState();
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

  const initAccordions = (root = document) => {
    const isMobile = isMobileViewport();
    const sections = Array.from(root.querySelectorAll("[data-mobile-accordion]"));

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

        const hasExplicitState = section.hasAttribute("data-mobile-accordion-open");
        const defaultExpanded = hasExplicitState
          ? section.dataset.mobileAccordionOpen === "true"
          : index === 0;

        section.dataset.expanded = defaultExpanded ? "true" : "false";
        section.dataset.accordionReady = "true";

        toggle.addEventListener("click", () => {
          const expanded = section.dataset.expanded === "true";
          setAccordionState(section, !expanded, true);
        });
      }

      setAccordionState(section, section.dataset.expanded === "true", isMobile);
    });
  };

  const refreshDashboardWorkspace = (root = document) => {
    if (window.LoomeraDashboardWorkspace?.refresh) {
      window.LoomeraDashboardWorkspace.refresh(root);
      return;
    }

    document.dispatchEvent(
      new CustomEvent("loomera:workspace-refresh", {
        bubbles: true,
        detail: { source: "appointments-management" },
      })
    );
  };

  const getWorkspace = () => document.querySelector("[data-appointments-workspace]");

  const cleanQueryParams = (params) => {
    const next = new URLSearchParams();
    params.forEach((value, key) => {
      if (value !== null && value !== undefined && String(value).trim() !== "") {
        next.append(key, value);
      }
    });
    return next;
  };

  const swapWorkspace = (html) => {
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, "text/html");
    const nextWorkspace = doc.querySelector("[data-appointments-workspace]");
    const currentWorkspace = getWorkspace();

    if (!nextWorkspace || !currentWorkspace) return null;

    currentWorkspace.replaceWith(nextWorkspace);
    return nextWorkspace;
  };

  const fetchWorkspace = async (url, { pushState = true } = {}) => {
    const currentWorkspace = getWorkspace();
    if (!currentWorkspace) {
      window.location.href = url;
      return;
    }

    forceCloseFilterModal(document);

    const currentScroll = window.scrollY;
    currentWorkspace.classList.add("is-loading");

    if (pageState.controller) {
      pageState.controller.abort();
    }

    pageState.controller = new AbortController();

    try {
      const response = await fetch(url, {
        headers: {
          "X-Requested-With": "XMLHttpRequest",
        },
        signal: pageState.controller.signal,
      });

      if (!response.ok) {
        throw new Error(`Request failed with status ${response.status}`);
      }

      const html = await response.text();
      const nextWorkspace = swapWorkspace(html);

      if (!nextWorkspace) {
        window.location.href = url;
        return;
      }

      if (pushState) {
        window.history.pushState({ appointmentWorkspace: true }, "", url);
      }

      forceCloseFilterModal(document);
      window.scrollTo({ top: currentScroll, behavior: "auto" });
      bindWorkspace(nextWorkspace);
    } catch (error) {
      if (error.name === "AbortError") return;
      console.error("[appointments] ajax navigation failed");
      window.location.href = url;
    } finally {
      pageState.controller = null;
      document.body.classList.remove("overflow-hidden");
      getWorkspace()?.classList.remove("is-loading");
    }
  };

  const bindAjaxLinks = (root = document) => {
    const links = root.querySelectorAll("[data-appointments-ajax-link]");

    links.forEach((link) => {
      if (link.dataset.ajaxBound === "true") return;
      link.dataset.ajaxBound = "true";

      link.addEventListener("click", (event) => {
        if (
          event.defaultPrevented ||
          event.metaKey ||
          event.ctrlKey ||
          event.shiftKey ||
          event.altKey
        ) {
          return;
        }

        const href = link.getAttribute("href");
        if (!href || href.startsWith("#")) return;

        event.preventDefault();
        forceCloseFilterModal(document);
        fetchWorkspace(href);
      });
    });
  };

  const bindFilterForm = (root = document) => {
    const forms = Array.from(root.querySelectorAll("[data-appointments-filter-form]"));

    forms.forEach((form) => {
      if (form.dataset.ajaxBound === "true") return;

      form.dataset.ajaxBound = "true";
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        const params = cleanQueryParams(new URLSearchParams(new FormData(form)));
        const queryString = params.toString();
        const url = queryString ? `${form.action}?${queryString}` : form.action;
        forceCloseFilterModal(document);
        fetchWorkspace(url);
      });
    });
  };

  const bindWorkspace = (root = document) => {
    initJalaliDatePicker();
    initFilterModal(root);
    initBulkSelection(root);
    initAccordions(root);
    bindAjaxLinks(root);
    bindFilterForm(root);
    refreshDashboardWorkspace(root);
  };

  bindWorkspace(getWorkspace() || document);

  if (!window.__appointmentsManagementPopstateBound) {
    window.__appointmentsManagementPopstateBound = true;
    window.addEventListener("popstate", () => {
      if (!getWorkspace()) return;
      fetchWorkspace(window.location.href, { pushState: false });
    });
  }

  if (!window.__appointmentsManagementResizeBound) {
    window.__appointmentsManagementResizeBound = true;
    window.addEventListener(
      "resize",
      () => {
        const workspace = getWorkspace();
        if (!workspace) return;
        initAccordions(workspace);
        refreshDashboardWorkspace(workspace);
      },
      { passive: true }
    );
  }

  if (!window.__appointmentsManagementOrientationBound) {
    window.__appointmentsManagementOrientationBound = true;
    window.addEventListener("orientationchange", () => {
      const workspace = getWorkspace();
      if (!workspace) return;
      window.setTimeout(() => {
        initAccordions(workspace);
        refreshDashboardWorkspace(workspace);
      }, 160);
    });
  }
}
