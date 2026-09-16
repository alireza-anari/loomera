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

  const REPORT_PRIMARY = "#735cbe";
  const REPORT_PRIMARY_SOFT = "#e9e3f7";
  const REPORT_GRID = "#eeeaf4";
  const REPORT_TEXT = "#5d566d";
  const REPORT_MUTED = "#8a8198";

  const prepareCanvas = (canvas, cssHeight) => {
    const rect = canvas.getBoundingClientRect();
    const width = Math.max(
      280,
      Math.round(rect.width || canvas.parentElement?.clientWidth || 320)
    );
    const height = cssHeight;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);

    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    canvas.style.height = `${height}px`;

    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.direction = "rtl";
    ctx.textBaseline = "middle";
    return { ctx, width, height };
  };

  const formatCompactNumber = (value) => {
    const number = Number(value || 0);
    if (number >= 1_000_000) {
      return `${(number / 1_000_000).toFixed(number >= 10_000_000 ? 0 : 1)}م`;
    }
    if (number >= 1_000) {
      return `${(number / 1_000).toFixed(number >= 100_000 ? 0 : 1)}ه`;
    }
    return String(Math.round(number));
  };

  const truncateCanvasLabel = (value, max = 10) => {
    const text = String(value || "");
    return text.length > max ? `${text.slice(0, max - 1)}…` : text;
  };

  const drawTrendChart = (root) => {
    if (!root || root.offsetParent === null) return;

    const canvas = root.querySelector("[data-reports-trend-canvas]");
    const points = Array.from(
      root.querySelectorAll("[data-report-trend-point]")
    ).map((node) => ({
      label: node.dataset.label || "",
      revenue: Number(node.dataset.revenue || 0),
      appointments: Number(node.dataset.appointments || 0),
    }));

    if (!canvas || !points.length) return;

    const { ctx, width, height } = prepareCanvas(canvas, 260);
    const pad = { top: 24, right: 14, bottom: 44, left: 14 };
    const plotW = width - pad.left - pad.right;
    const plotH = height - pad.top - pad.bottom;
    const maxRevenue = Math.max(...points.map((point) => point.revenue), 1);
    const maxAppointments = Math.max(
      ...points.map((point) => point.appointments),
      1
    );
    const count = points.length;
    const step = count > 1 ? plotW / (count - 1) : plotW;
    const labelStep = Math.max(1, Math.ceil(count / 6));

    ctx.clearRect(0, 0, width, height);

    ctx.strokeStyle = REPORT_GRID;
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i += 1) {
      const y = pad.top + (plotH / 4) * i;
      ctx.beginPath();
      ctx.moveTo(pad.left, y);
      ctx.lineTo(width - pad.right, y);
      ctx.stroke();
    }

    const barSlot = count > 1 ? plotW / count : plotW / 2;
    const barWidth = Math.max(5, Math.min(14, barSlot * 0.42));

    points.forEach((point, index) => {
      const x =
        count > 1 ? pad.left + step * index : pad.left + plotW / 2;
      const barHeight =
        (point.appointments / maxAppointments) * plotH * 0.68;

      ctx.fillStyle = REPORT_PRIMARY_SOFT;
      ctx.fillRect(
        x - barWidth / 2,
        pad.top + plotH - barHeight,
        barWidth,
        barHeight
      );
    });

    ctx.strokeStyle = REPORT_PRIMARY;
    ctx.lineWidth = 3;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.beginPath();

    points.forEach((point, index) => {
      const x =
        count > 1 ? pad.left + step * index : pad.left + plotW / 2;
      const y =
        pad.top + plotH - (point.revenue / maxRevenue) * plotH;

      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    points.forEach((point, index) => {
      const x =
        count > 1 ? pad.left + step * index : pad.left + plotW / 2;
      const y =
        pad.top + plotH - (point.revenue / maxRevenue) * plotH;

      ctx.fillStyle = "#ffffff";
      ctx.strokeStyle = REPORT_PRIMARY;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(x, y, 3.5, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();

      if (
        index % labelStep === 0 ||
        index === count - 1 ||
        count <= 6
      ) {
        ctx.fillStyle = REPORT_MUTED;
        ctx.font = "700 9px sans-serif";
        ctx.textAlign = "center";
        ctx.fillText(
          truncateCanvasLabel(point.label, 9),
          x,
          height - 24
        );
      }
    });

    ctx.fillStyle = REPORT_TEXT;
    ctx.font = "800 9px sans-serif";
    ctx.textAlign = "right";
    ctx.fillText(
      `بیشترین درآمد: ${formatCompactNumber(maxRevenue)}`,
      width - pad.right,
      10
    );
  };

  const drawStatusChart = (root) => {
    if (!root || root.offsetParent === null) return;

    const canvas = root.querySelector("[data-reports-status-canvas]");
    const points = Array.from(
      root.querySelectorAll("[data-report-status-point]")
    ).map((node) => ({
      count: Number(node.dataset.count || 0),
      color: node.dataset.color || REPORT_PRIMARY,
    }));

    if (!canvas || !points.length) return;

    const { ctx, width, height } = prepareCanvas(canvas, 220);
    const total = points.reduce((sum, point) => sum + point.count, 0);
    const cx = width / 2;
    const cy = height / 2;
    const radius = Math.min(width, height) * 0.31;
    const lineWidth = Math.max(18, radius * 0.3);
    let angle = -Math.PI / 2;

    ctx.clearRect(0, 0, width, height);

    ctx.strokeStyle = REPORT_GRID;
    ctx.lineWidth = lineWidth;
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, Math.PI * 2);
    ctx.stroke();

    points.forEach((point) => {
      if (!point.count || !total) return;

      const slice = (point.count / total) * Math.PI * 2;
      ctx.strokeStyle = point.color;
      ctx.lineWidth = lineWidth;
      ctx.lineCap = "butt";
      ctx.beginPath();
      ctx.arc(cx, cy, radius, angle, angle + slice);
      ctx.stroke();
      angle += slice;
    });

    ctx.fillStyle = "#2f283d";
    ctx.textAlign = "center";
    ctx.font = "900 24px sans-serif";
    ctx.fillText(String(total), cx, cy - 4);

    ctx.fillStyle = REPORT_MUTED;
    ctx.font = "700 10px sans-serif";
    ctx.fillText("کل رزروها", cx, cy + 20);
  };

  const drawRankingChart = (root) => {
    if (!root || root.offsetParent === null) return;

    const canvas = root.querySelector("[data-reports-ranking-canvas]");
    const points = Array.from(
      root.querySelectorAll("[data-report-ranking-point]")
    ).map((node) => ({
      label: node.dataset.label || "",
      meta: node.dataset.meta || "",
      value: Number(node.dataset.value || 0),
      valueLabel: node.dataset.valueLabel || "",
    }));

    if (!canvas || !points.length) return;

    const palette = [
      "#735cbe",  // بنفش Loomera
      "#0ea5e9",  // آبی
      "#10b981",  // سبز
      "#f59e0b",  // نارنجی
      "#f43f5e",  // قرمز/صورتی
    ];

    const { ctx, width, height } = prepareCanvas(canvas, 220);
    const total = points.reduce((sum, point) => sum + Math.max(point.value, 0), 0);
    const cx = width / 2;
    const cy = height / 2;
    const radius = Math.min(width, height) * 0.31;
    const lineWidth = Math.max(18, radius * 0.3);
    let angle = -Math.PI / 2;

    ctx.clearRect(0, 0, width, height);

    ctx.strokeStyle = REPORT_GRID;
    ctx.lineWidth = lineWidth;
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, Math.PI * 2);
    ctx.stroke();

    points.forEach((point, index) => {
      if (!point.value || !total) return;

      const slice = (point.value / total) * Math.PI * 2;
      ctx.strokeStyle = palette[index % palette.length];
      ctx.lineWidth = lineWidth;
      ctx.lineCap = "butt";
      ctx.beginPath();
      ctx.arc(cx, cy, radius, angle, angle + slice);
      ctx.stroke();
      angle += slice;
    });

    ctx.fillStyle = "#2f283d";
    ctx.textAlign = "center";
    ctx.font = "900 22px sans-serif";
    ctx.fillText(points.length.toLocaleString("fa-IR"), cx, cy - 4);

    ctx.fillStyle = REPORT_MUTED;
    ctx.font = "700 10px sans-serif";
    ctx.fillText("مورد برتر", cx, cy + 20);

    root
      .querySelectorAll("[data-report-ranking-legend-color]")
      .forEach((node, index) => {
        node.style.backgroundColor = palette[index % palette.length];
      });
  };

  const renderVisibleReportCharts = () => {
    document
      .querySelectorAll("[data-reports-trend-chart]")
      .forEach(drawTrendChart);
    document
      .querySelectorAll("[data-reports-status-chart]")
      .forEach(drawStatusChart);
    document
      .querySelectorAll("[data-reports-ranking-chart]")
      .forEach(drawRankingChart);
  };


  const initReportSectionTabs = () => {
    const tabs = Array.from(document.querySelectorAll("[data-reports-section-tab]"));
    const panels = Array.from(document.querySelectorAll("[data-reports-section-panel]"));
    const filterTrigger = document.querySelector("[data-reports-filter-open]");
    if (!tabs.length || !panels.length) return;

    const validKeys = new Set(tabs.map((tab) => tab.dataset.reportsSectionTab));
    const hashKey = window.location.hash.replace(/^#/, "").replace(/^reports-/, "");
    let activeKey = validKeys.has(hashKey) ? hashKey : "overview";

    const activate = (key, { updateHash = true, focus = false } = {}) => {
      if (!validKeys.has(key)) key = "overview";
      activeKey = key;

      tabs.forEach((tab) => {
        const active = tab.dataset.reportsSectionTab === key;
        tab.setAttribute("aria-selected", active ? "true" : "false");
        tab.setAttribute("tabindex", active ? "0" : "-1");
        if (active && focus) {
          tab.focus({ preventScroll: true });
        }
      });

      panels.forEach((panel) => {
        const active = panel.dataset.reportsSectionPanel === key;
        panel.hidden = !active;
        panel.setAttribute("aria-hidden", active ? "false" : "true");
      });

      if (filterTrigger) {
        const showFilter = key !== "overview";
        filterTrigger.classList.toggle("hidden", !showFilter);
        filterTrigger.setAttribute("aria-hidden", showFilter ? "false" : "true");
        filterTrigger.tabIndex = showFilter ? 0 : -1;
      }

      if (updateHash) {
        const url = new URL(window.location.href);
        url.hash = key === "overview" ? "" : `reports-${key}`;
        window.history.replaceState({}, "", url);
      }

      window.requestAnimationFrame(renderVisibleReportCharts);
    };

    tabs.forEach((tab, index) => {
      tab.addEventListener("click", () => {
        activate(tab.dataset.reportsSectionTab);
      });

      tab.addEventListener("keydown", (event) => {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
        event.preventDefault();

        let nextIndex = index;
        if (event.key === "Home") nextIndex = 0;
        else if (event.key === "End") nextIndex = tabs.length - 1;
        else if (event.key === "ArrowLeft") nextIndex = (index + 1) % tabs.length;
        else if (event.key === "ArrowRight") nextIndex = (index - 1 + tabs.length) % tabs.length;

        activate(tabs[nextIndex].dataset.reportsSectionTab, { focus: true });
      });
    });

    window.addEventListener("hashchange", () => {
      const nextKey = window.location.hash.replace(/^#/, "").replace(/^reports-/, "");
      activate(validKeys.has(nextKey) ? nextKey : "overview", { updateHash: false });
    });

    activate(activeKey, { updateHash: false });
  };


  const initFilterDialog = () => {
    const modal = document.querySelector("[data-reports-filter-modal]");
    const trigger = document.querySelector("[data-reports-filter-open]");
    if (!modal || !trigger) return;

    const dialog = modal.querySelector('[role="dialog"]');
    const firstFocusable = modal.querySelector('input:not([type="hidden"]), select, button, a[href]');
    let lastFocused = null;

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

    trigger.addEventListener("click", openModal);
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
  initReportSectionTabs();
  initFilterDialog();
  window.requestAnimationFrame(renderVisibleReportCharts);

  if (!window.__reportsDashboardResizeBound) {
    window.__reportsDashboardResizeBound = true;
    window.addEventListener(
      "resize",
      () => {
        initAccordions();
        window.requestAnimationFrame(renderVisibleReportCharts);
      },
      { passive: true }
    );
  }
}
