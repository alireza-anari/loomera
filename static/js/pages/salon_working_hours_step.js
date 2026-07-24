let salonWorkingHoursBound = false;

const mobileDayAccordionQuery = window.matchMedia("(max-width: 1023px)");

function normalizeDigits(value) {
  const fa = "۰۱۲۳۴۵۶۷۸۹";
  const ar = "٠١٢٣٤٥٦٧٨٩";

  return String(value || "")
    .split("")
    .map((char) => {
      const faIndex = fa.indexOf(char);
      if (faIndex > -1) return String(faIndex);

      const arIndex = ar.indexOf(char);
      if (arIndex > -1) return String(arIndex);

      return char;
    })
    .join("");
}

function toPersianDigits(value) {
  const en = "0123456789";
  const fa = "۰۱۲۳۴۵۶۷۸۹";

  return String(value || "")
    .split("")
    .map((char) => {
      const index = en.indexOf(char);
      return index > -1 ? fa[index] : char;
    })
    .join("");
}

function isValidTime(value) {
  return /^([01]\d|2[0-3]):([0-5]\d)$/.test(normalizeDigits(value).trim());
}

function timeToMinutes(value) {
  const normalized = normalizeDigits(value).trim();
  if (!isValidTime(normalized)) return null;

  const [hours, minutes] = normalized.split(":").map((part) => Number.parseInt(part, 10));
  return hours * 60 + minutes;
}

function buildTimeOptions() {
  const options = [];

  for (let hour = 0; hour < 24; hour += 1) {
    for (let minute = 0; minute < 60; minute += 30) {
      options.push(`${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`);
    }
  }

  return options;
}

function getRowTimeInputs(row) {
  return {
    openInput: row.querySelector('input[id$="_open_time"]'),
    closeInput: row.querySelector('input[id$="_close_time"]'),
  };
}

function getRowState(row) {
  const checkbox = row.querySelector('input[type="checkbox"]');
  const { openInput, closeInput } = getRowTimeInputs(row);

  const active = Boolean(checkbox?.checked);
  const openValue = normalizeDigits(openInput?.value || "").trim();
  const closeValue = normalizeDigits(closeInput?.value || "").trim();

  const hasOpen = Boolean(openValue);
  const hasClose = Boolean(closeValue);
  const openValid = !hasOpen || isValidTime(openValue);
  const closeValid = !hasClose || isValidTime(closeValue);

  const openMinutes = timeToMinutes(openValue);
  const closeMinutes = timeToMinutes(closeValue);

  const complete =
    active &&
    hasOpen &&
    hasClose &&
    openValid &&
    closeValid &&
    closeMinutes !== null &&
    openMinutes !== null &&
    closeMinutes > openMinutes;

  let issue = "";

  if (active && (!hasOpen || !hasClose)) {
    issue = "برای روز فعال، ساعت شروع و پایان را کامل کن.";
  } else if (active && (!openValid || !closeValid)) {
    issue = "فرمت ساعت باید مثل 09:30 باشد.";
  } else if (active && hasOpen && hasClose && closeMinutes <= openMinutes) {
    issue = "ساعت پایان باید بعد از ساعت شروع باشد.";
  }

  return {
    active,
    complete,
    invalid: Boolean(issue),
    issue,
    openValue,
    closeValue,
  };
}

function getDayHeader(row) {
  return row.firstElementChild;
}

function getDayPanel(row) {
  return row.querySelector("[data-day-fields]");
}

function getDayValidation(row) {
  return row.querySelector("[data-day-validation]");
}

function isAccordionIgnoredTarget(target) {
  return Boolean(target.closest("input, select, textarea, button, a, label"));
}

function setDayState(row) {
  const checkbox = row.querySelector('input[type="checkbox"]');
  const status = row.querySelector("[data-day-status]");
  const statusHelp = row.querySelector("[data-day-status-help]");
  const validation = row.querySelector("[data-day-validation]");
  const triggers = row.querySelectorAll("[data-time-trigger]");
  const { openInput, closeInput } = getRowTimeInputs(row);
  const timeInputs = [openInput, closeInput].filter(Boolean);

  if (!checkbox) return getRowState(row);

  const state = getRowState(row);
  const isActive = state.active;

  timeInputs.forEach((field) => {
    field.disabled = !isActive;
    field.value = normalizeDigits(field.value || "").replace(/[^\d:]/g, "").slice(0, 5);

    field.classList.toggle("bg-loomera-bgSubtle", !isActive);
    field.classList.toggle("text-loomera-textMuted", !isActive);
    field.classList.toggle("bg-white", isActive);
    field.classList.toggle("border-loomera-danger/40", state.invalid && isActive);
    field.classList.toggle("ring-4", state.invalid && isActive);
    field.classList.toggle("ring-loomera-danger/10", state.invalid && isActive);
  });

  triggers.forEach((trigger) => {
    trigger.disabled = !isActive;
    trigger.classList.toggle("opacity-50", !isActive);
    trigger.classList.toggle("cursor-not-allowed", !isActive);
  });

  if (status) {
    status.textContent = isActive ? "روز فعال" : "روز تعطیل";
  }

  if (statusHelp) {
    if (!isActive) {
      statusHelp.textContent = "این روز در صفحه عمومی تعطیل نمایش داده می‌شود.";
    } else if (state.complete) {
      statusHelp.textContent = `فعال از ${toPersianDigits(state.openValue)} تا ${toPersianDigits(state.closeValue)}`;
    } else {
      statusHelp.textContent = "روز فعال است؛ بازه زمانی را کامل کن.";
    }
  }

  row.classList.toggle("opacity-70", !isActive);
  row.classList.toggle("border-loomera-danger/30", state.invalid);
  row.classList.toggle("bg-loomera-dangerSoft/30", state.invalid);
  row.classList.toggle("border-loomera-primary/25", state.complete);
  row.classList.toggle("bg-loomera-primarySoft/25", state.complete);

  if (validation) {
    validation.textContent = state.issue;
    validation.classList.toggle("hidden", !state.invalid);
  }

  return state;
}

function ensureDayAccordionControl(row, rows) {
  if (row.dataset.dayAccordionReady === "true") return;

  const header = getDayHeader(row);
  if (!header) return;

  const actionsHost = row.querySelector("[data-day-header-actions]");

  row.dataset.dayAccordionReady = "true";

  const toggleButton = document.createElement("button");
  toggleButton.type = "button";
  toggleButton.setAttribute("data-day-accordion-toggle", "");
  toggleButton.setAttribute("aria-label", "باز و بسته کردن روز");
  toggleButton.className =
    "inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border border-loomera-borderSoft bg-white text-loomera-textSecondary shadow-sm transition hover:border-loomera-primary/30 hover:bg-loomera-primarySoft hover:text-loomera-primaryText lg:hidden";
  toggleButton.innerHTML = '<i class="fa-solid fa-chevron-down text-xs transition-transform" aria-hidden="true"></i>';

  header.classList.add("cursor-pointer", "lg:cursor-default");
  (actionsHost || header).appendChild(toggleButton);

  const toggleRow = () => {
    if (!mobileDayAccordionQuery.matches) return;

    const shouldOpen = row.dataset.mobileDayExpanded !== "true";

    rows.forEach((item) => {
      item.dataset.mobileDayExpanded = "false";
    });

    row.dataset.mobileDayExpanded = shouldOpen ? "true" : "false";
    syncMobileDayAccordions(rows);
  };

  toggleButton.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    toggleRow();
  });

  header.addEventListener("click", (event) => {
    if (!mobileDayAccordionQuery.matches) return;
    if (isAccordionIgnoredTarget(event.target)) return;
    toggleRow();
  });

  header.addEventListener("keydown", (event) => {
    if (!mobileDayAccordionQuery.matches) return;
    if (event.key !== "Enter" && event.key !== " ") return;
    if (isAccordionIgnoredTarget(event.target)) return;

    event.preventDefault();
    toggleRow();
  });

  header.setAttribute("tabindex", "0");
}

function syncMobileDayAccordions(rows) {
  const isMobile = mobileDayAccordionQuery.matches;

  rows.forEach((row) => {
    const panel = getDayPanel(row);
    const validation = getDayValidation(row);
    const toggleButton = row.querySelector("[data-day-accordion-toggle]");
    const toggleIcon = toggleButton?.querySelector("i");
    const state = getRowState(row);

    if (!panel) return;

    if (!isMobile) {
      panel.classList.remove("hidden");
      row.dataset.mobileDayExpanded = "true";
      row.classList.remove("shadow-lm-card");
      toggleButton?.setAttribute("aria-expanded", "true");
      toggleIcon?.classList.add("rotate-180");

      if (validation) {
        validation.classList.toggle("hidden", !state.invalid);
      }

      return;
    }

    const expanded = row.dataset.mobileDayExpanded === "true";

    panel.classList.toggle("hidden", !expanded);
    row.classList.toggle("shadow-lm-card", expanded);
    row.classList.toggle("bg-white", expanded);

    toggleButton?.setAttribute("aria-expanded", expanded ? "true" : "false");
    toggleIcon?.classList.toggle("rotate-180", expanded);

    if (validation) {
      validation.classList.toggle("hidden", !expanded || !state.invalid);
    }
  });
}

function setupMobileDayAccordions(rows) {
  if (!rows.length) return;

  const firstActiveRow = rows.find((row) => row.querySelector('input[type="checkbox"]')?.checked);
  const defaultOpenRow = firstActiveRow || rows[0];

  rows.forEach((row) => {
    ensureDayAccordionControl(row, rows);
    row.dataset.mobileDayExpanded = row === defaultOpenRow ? "true" : "false";
  });

  syncMobileDayAccordions(rows);

  const handleAccordionResize = () => {
    if (!mobileDayAccordionQuery.matches) {
      rows.forEach((row) => {
        row.dataset.mobileDayExpanded = "true";
      });
    } else {
      const hasOpenRow = rows.some((row) => row.dataset.mobileDayExpanded === "true");
      if (!hasOpenRow && rows[0]) {
        rows[0].dataset.mobileDayExpanded = "true";
      }
    }

    syncMobileDayAccordions(rows);
    window.LoomeraDashboardWorkspace?.refresh?.(document.querySelector("[data-dashboard-workspace-root]"));
  };

  if (typeof mobileDayAccordionQuery.addEventListener === "function") {
    mobileDayAccordionQuery.addEventListener("change", handleAccordionResize);
  } else if (typeof mobileDayAccordionQuery.addListener === "function") {
    mobileDayAccordionQuery.addListener(handleAccordionResize);
  }

  window.addEventListener("resize", () => {
    window.setTimeout(handleAccordionResize, 120);
  });
}

function setText(selector, value) {
  const element = document.querySelector(selector);
  if (element) element.textContent = value;
}

function updateWorkingHoursSummary(rows) {
  const summaryList = document.querySelector("[data-working-hours-summary-list]");
  if (!summaryList) return;

  summaryList.innerHTML = "";

  rows.forEach((row) => {
    const state = getRowState(row);
    const dayName = row.dataset.dayName || row.querySelector("h3")?.textContent?.trim() || "روز";

    const item = document.createElement("div");
    item.className =
      "flex items-center justify-between gap-3 rounded-2xl border border-loomera-borderSoft bg-white px-3 py-3 text-xs leading-6";

    const title = document.createElement("span");
    title.className = "font-black text-loomera-textPrimary";
    title.textContent = dayName;

    const value = document.createElement("span");
    value.className = "shrink-0 rounded-full px-3 py-1 font-black";

    if (!state.active) {
      value.classList.add("bg-loomera-bgSubtle", "text-loomera-textMuted");
      value.textContent = "تعطیل";
    } else if (state.complete) {
      value.classList.add("bg-loomera-primarySoft", "text-loomera-primaryText");
      value.textContent = `${toPersianDigits(state.openValue)} تا ${toPersianDigits(state.closeValue)}`;
    } else {
      value.classList.add("bg-loomera-dangerSoft", "text-loomera-danger");
      value.textContent = "نیازمند اصلاح";
    }

    item.append(title, value);
    summaryList.appendChild(item);
  });
}

function updateReadiness(rows) {
  const states = rows.map((row) => setDayState(row));
  const activeCount = states.filter((state) => state.active).length;
  const completeCount = states.filter((state) => state.complete).length;
  const invalidCount = states.filter((state) => state.invalid).length;
  const closedCount = states.length - activeCount;

  let percent = 0;

  if (activeCount > 0) {
    percent = Math.round((completeCount / activeCount) * 80);
    if (invalidCount === 0 && completeCount === activeCount) percent = 100;
  }

  setText("[data-active-days-count]", toPersianDigits(activeCount));
  setText("[data-complete-days-count]", toPersianDigits(completeCount));
  setText("[data-closed-days-count]", toPersianDigits(closedCount));
  setText("[data-invalid-days-count]", toPersianDigits(invalidCount));
  setText("[data-working-hours-review-badge]", toPersianDigits(activeCount));
  setText("[data-working-hours-progress-label]", `${toPersianDigits(percent)}٪`);

  const progressBar = document.querySelector("[data-working-hours-progress-bar]");
  if (progressBar) progressBar.style.width = `${percent}%`;

  const statusLabel = document.querySelector("[data-working-hours-status-label]");
  const statusHelp = document.querySelector("[data-working-hours-status-help]");
  const readinessTitle = document.querySelector("[data-working-hours-readiness-title]");
  const readinessHelp = document.querySelector("[data-working-hours-readiness-help]");

  let title = "برنامه ناقص است";
  let help = "حداقل یک روز فعال با ساعت شروع و پایان معتبر لازم است.";

  if (activeCount === 0) {
    title = "هیچ روز فعالی ثبت نشده";
    help = "برای رزرو آنلاین باید حداقل یک روز فعال داشته باشی.";
  } else if (invalidCount > 0) {
    title = "نیازمند اصلاح ساعت‌ها";
    help = `${toPersianDigits(invalidCount)} روز بازه ناقص یا نامعتبر دارد.`;
  } else if (completeCount === activeCount) {
    title = "آماده ذخیره";
    help = `${toPersianDigits(activeCount)} روز فعال با ساعت معتبر تنظیم شده است.`;
  }

  if (statusLabel) statusLabel.textContent = title;
  if (statusHelp) statusHelp.textContent = help;
  if (readinessTitle) readinessTitle.textContent = title;
  if (readinessHelp) readinessHelp.textContent = help;

  updateWorkingHoursSummary(rows);
  syncMobileDayAccordions(rows);

  window.LoomeraDashboardWorkspace?.refresh?.(document.querySelector("[data-dashboard-workspace-root]"));
}

function applyPreset(name, rows) {
  rows.forEach((row) => {
    const day = Number.parseInt(row.dataset.day || "0", 10);
    const checkbox = row.querySelector('input[type="checkbox"]');
    const { openInput, closeInput } = getRowTimeInputs(row);

    if (!checkbox || !openInput || !closeInput) return;

    if (name === "clear") {
      checkbox.checked = false;
      openInput.value = "";
      closeInput.value = "";
      return;
    }

    if (name === "standard") {
      checkbox.checked = day >= 1 && day <= 6;
      openInput.value = checkbox.checked ? "10:00" : "";
      closeInput.value = checkbox.checked ? "20:00" : "";
      return;
    }

    if (name === "full-week") {
      checkbox.checked = true;
      openInput.value = "09:00";
      closeInput.value = "21:00";
    }
  });

  updateReadiness(rows);
}

export default function initSalonWorkingHoursStep() {
  if (salonWorkingHoursBound) return;
  salonWorkingHoursBound = true;

  const rows = Array.from(document.querySelectorAll("[data-working-day-row]"));
  const modal = document.getElementById("timePickerModal");
  const grid = document.getElementById("timePickerGrid");
  const title = document.getElementById("timePickerTitle");
  const closeBtn = document.getElementById("closeTimePickerBtn");
  const quickOptions = document.getElementById("timePickerQuickOptions");
  const presetButtons = Array.from(document.querySelectorAll("[data-working-hours-preset]"));

  if (!rows.length || !modal || !grid || !title || !closeBtn || !quickOptions) return;

  setupMobileDayAccordions(rows);

  const allTimes = buildTimeOptions();
  const quickTimes = ["09:00", "10:00", "11:00", "12:00", "18:00", "19:00", "20:00"];
  let activeInput = null;

  function closeModal() {
    modal.classList.add("hidden");
    modal.classList.remove("flex");
    activeInput = null;
  }

  function applyTime(value) {
    if (!activeInput) return;

    activeInput.value = value;
    activeInput.dispatchEvent(new Event("input", { bubbles: true }));
    activeInput.dispatchEvent(new Event("change", { bubbles: true }));
    closeModal();
  }

  function createTimeButton(value, compact = false) {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.timeValue = value;
    button.className = compact
      ? "rounded-full border border-loomera-borderSoft px-3 py-2 text-xs font-black text-loomera-textSecondary transition hover:border-loomera-primary/30 hover:bg-loomera-primarySoft hover:text-loomera-primaryText"
      : "rounded-2xl border border-loomera-borderSoft px-3 py-3 text-sm font-black text-loomera-textSecondary transition hover:border-loomera-primary/30 hover:bg-loomera-primarySoft hover:text-loomera-primaryText";
    button.textContent = toPersianDigits(value);
    button.addEventListener("click", () => applyTime(value));
    return button;
  }

  function renderOptions(selectedValue = "") {
    grid.innerHTML = "";
    quickOptions.innerHTML = "";

    quickTimes.forEach((time) => {
      const btn = createTimeButton(time, true);
      if (time === selectedValue) {
        btn.classList.add("border-loomera-primary", "bg-loomera-primarySoft", "text-loomera-primaryText");
      }
      quickOptions.appendChild(btn);
    });

    allTimes.forEach((time) => {
      const btn = createTimeButton(time, false);
      if (time === selectedValue) {
        btn.classList.add("border-loomera-primary", "bg-loomera-primarySoft", "text-loomera-primaryText");
      }
      grid.appendChild(btn);
    });
  }

  function openModal(input) {
    activeInput = input;

    const row = input.closest("[data-working-day-row]");
    const dayTitle = row?.dataset.dayName || row?.querySelector("h3")?.textContent?.trim() || "روز";
    const fieldLabel = input.id.includes("open") ? "ساعت شروع" : "ساعت پایان";

    title.textContent = `${fieldLabel} • ${dayTitle}`;
    renderOptions(normalizeDigits(input.value || ""));
    modal.classList.remove("hidden");
    modal.classList.add("flex");
  }

  rows.forEach((row) => {
    const checkbox = row.querySelector('input[type="checkbox"]');
    const { openInput, closeInput } = getRowTimeInputs(row);
    const inputs = [openInput, closeInput].filter(Boolean);
    const triggers = row.querySelectorAll("[data-time-trigger]");

    setDayState(row);

    checkbox?.addEventListener("change", () => updateReadiness(rows));

    inputs.forEach((input) => {
      input.setAttribute("inputmode", "numeric");
      input.setAttribute("autocomplete", "off");

      input.addEventListener("focus", () => {
        if (input.disabled) return;
        openModal(input);
      });

      input.addEventListener("click", () => {
        if (input.disabled) return;
        openModal(input);
      });

      input.addEventListener("input", () => {
        input.value = normalizeDigits(input.value).replace(/[^\d:]/g, "").slice(0, 5);
        updateReadiness(rows);
      });

      input.addEventListener("blur", () => {
        const value = normalizeDigits(input.value).trim();
        if (value && isValidTime(value)) input.value = value;
        updateReadiness(rows);
      });
    });

    triggers.forEach((trigger) => {
      trigger.addEventListener("click", () => {
        const targetId = trigger.dataset.targetInput;
        const target = document.getElementById(targetId);

        if (!target || target.disabled) return;
        openModal(target);
      });
    });
  });

  presetButtons.forEach((button) => {
    button.addEventListener("click", () => applyPreset(button.dataset.workingHoursPreset || "", rows));
  });

  closeBtn.addEventListener("click", closeModal);

  modal.addEventListener("click", (event) => {
    if (event.target === modal) closeModal();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeModal();
  });

  updateReadiness(rows);
}

document.addEventListener("DOMContentLoaded", initSalonWorkingHoursStep);
