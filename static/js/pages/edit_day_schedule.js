const persianDigits = new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 0 });

function toPersianNumber(value) {
  const number = Number(value) || 0;
  return persianDigits.format(number);
}

function timeToMinutes(value) {
  if (!value || !/^\d{2}:\d{2}$/.test(value)) return null;

  const [hours, minutes] = value.split(":").map(Number);
  if (!Number.isFinite(hours) || !Number.isFinite(minutes)) return null;

  return hours * 60 + minutes;
}

function setText(targets, value) {
  targets.forEach((target) => {
    if (target) target.textContent = value;
  });
}

function refreshWorkspaceLayout() {
  window.LoomeraDashboardWorkspace?.refresh?.();
}

function applyPersianDateLabels() {
  const root = document.querySelector("[data-edit-day-page]");
  const dateIso = root?.dataset.dateIso;
  const targets = Array.from(document.querySelectorAll("[data-jalali-date-label]"));

  if (!dateIso || !targets.length) return;

  try {
    const gregorianDate = new Date(`${dateIso}T12:00:00`);
    if (Number.isNaN(gregorianDate.getTime())) return;

    const formatter = new Intl.DateTimeFormat("fa-IR-u-ca-persian", {
      weekday: "long",
      day: "numeric",
      month: "long",
    });
    const label = formatter.format(gregorianDate).replace(/،/g, "، ");
    targets.forEach((target) => {
      target.textContent = label;
      target.setAttribute("dir", "rtl");
      target.setAttribute("lang", "fa");
    });
  } catch (error) {
    console.warn("[edit-day-schedule] Persian date formatting failed", error);
  }
}

export default function initEditDaySchedule() {
  applyPersianDateLabels();

  const form = document.querySelector("[data-edit-day-form]");
  const rowsContainer = document.querySelector("[data-shift-rows]");
  const template = document.querySelector("[data-shift-template]");
  const addButton = document.querySelector("[data-add-shift-row]");
  const emptyState = document.getElementById("emptyShiftState");

  if (!form || !rowsContainer || !template || !addButton) return;

  const canSchedule = form.dataset.canSchedule !== "false";
  const countTargets = Array.from(document.querySelectorAll("[data-shift-count]"));
  const completeTargets = Array.from(document.querySelectorAll("[data-complete-count]"));
  const incompleteTargets = Array.from(document.querySelectorAll("[data-incomplete-count]"));
  const invalidTargets = Array.from(document.querySelectorAll("[data-invalid-count]"));
  const readinessPercentTargets = Array.from(document.querySelectorAll("[data-readiness-percent]"));
  const readinessBadgeTargets = Array.from(document.querySelectorAll("[data-readiness-tab-badge]"));
  const readinessBar = document.querySelector("[data-readiness-bar]");
  const readinessTitle = document.querySelector("[data-readiness-title]");
  const readinessDescription = document.querySelector("[data-readiness-description]");
  const reviewMessage = document.querySelector("[data-review-message]");

  let rowIndex = rowsContainer.querySelectorAll("[data-shift-row]").length;

  const getRows = () => Array.from(rowsContainer.querySelectorAll("[data-shift-row]"));

  const getRowState = (row) => {
    const startInput = row.querySelector("[data-shift-start]");
    const endInput = row.querySelector("[data-shift-end]");
    const serviceInput = row.querySelector("[data-shift-service]");

    const start = startInput?.value || "";
    const end = endInput?.value || "";
    const service = serviceInput?.value || "";
    const hasAnyValue = Boolean(start || end || service);
    const hasAllValues = Boolean(start && end);
    const startMinutes = timeToMinutes(start);
    const endMinutes = timeToMinutes(end);
    const hasInvalidTime = Boolean(start && end && startMinutes !== null && endMinutes !== null && endMinutes <= startMinutes);

    return {
      startInput,
      endInput,
      serviceInput,
      hasAnyValue,
      hasAllValues,
      hasInvalidTime,
      isComplete: hasAllValues && !hasInvalidTime,
      isIncomplete: hasAnyValue && !hasAllValues,
    };
  };

  const markRow = (row, state) => {
    const rowStatus = row.querySelector("[data-row-status]");
    const inputs = [state.startInput, state.endInput, state.serviceInput].filter(Boolean);

    row.classList.toggle("border-loomera-warning/35", state.isIncomplete);
    row.classList.toggle("bg-loomera-warningSoft/40", state.isIncomplete);
    row.classList.toggle("border-loomera-danger/30", state.hasInvalidTime);
    row.classList.toggle("bg-loomera-dangerSoft/30", state.hasInvalidTime);
    row.classList.toggle("border-loomera-success/25", state.isComplete);

    inputs.forEach((input) => {
      const shouldWarn = state.hasAnyValue && !input.value;
      const shouldError = state.hasInvalidTime && (input === state.startInput || input === state.endInput);

      input.classList.toggle("border-loomera-warning/45", shouldWarn);
      input.classList.toggle("ring-4", shouldWarn || shouldError);
      input.classList.toggle("ring-loomera-warning/10", shouldWarn);
      input.classList.toggle("border-loomera-danger/45", shouldError);
      input.classList.toggle("ring-loomera-danger/10", shouldError);
    });

    if (!rowStatus) return;

    if (state.hasInvalidTime) {
      rowStatus.textContent = "پایان بازه باید بعد از شروع باشد.";
      rowStatus.className = "mt-1 text-xs leading-5 text-loomera-danger";
    } else if (state.isIncomplete) {
      rowStatus.textContent = "این ردیف نیمه‌کاره است؛ زمان شروع و پایان را کامل کن. انتخاب خدمت اختیاری است.";
      rowStatus.className = "mt-1 text-xs leading-5 text-loomera-warning";
    } else if (state.isComplete) {
      rowStatus.textContent = "این ردیف برای ذخیره آماده است.";
      rowStatus.className = "mt-1 text-xs leading-5 text-loomera-success";
    } else {
      rowStatus.textContent = "زمان شروع و پایان را برای این بازه مشخص کن. انتخاب خدمت اختیاری است.";
      rowStatus.className = "mt-1 text-xs leading-5 text-loomera-textMuted";
    }
  };

  const updateUIState = () => {
    const rows = getRows();
    let completeCount = 0;
    let incompleteCount = 0;
    let invalidCount = 0;

    rows.forEach((row) => {
      const state = getRowState(row);
      markRow(row, state);

      if (state.isComplete) completeCount += 1;
      if (state.isIncomplete) incompleteCount += 1;
      if (state.hasInvalidTime) invalidCount += 1;
    });

    const needsAttention = incompleteCount + invalidCount;
    let readiness = 0;
    let title = "برنامه نیازمند بررسی است";
    let description = "ردیف‌های ناقص یا بازه‌های زمانی نامعتبر را قبل از ذخیره اصلاح کن.";

    if (!canSchedule) {
      readiness = 0;
      title = "سالن در این روز فعال نیست";
      description = "این روز برای سالن تعطیل است یا ساعت کاری فعالی ندارد؛ ثبت شیفت کاری ممکن نیست.";
    } else if (rows.length === 0) {
      readiness = 65;
      title = "روز بدون شیفت ثبت می‌شود";
      description = "اگر می‌خواهی این روز بدون برنامه بماند، فرم خالی قابل ذخیره است.";
    } else if (needsAttention === 0) {
      readiness = 100;
      title = "آماده ذخیره برنامه روز";
      description = "همه ردیف‌های برنامه زمان معتبر دارند.";
    } else {
      readiness = Math.max(35, Math.round((completeCount / rows.length) * 85));
    }

    setText(countTargets, toPersianNumber(rows.length));
    setText(completeTargets, toPersianNumber(completeCount));
    setText(incompleteTargets, toPersianNumber(needsAttention));
    setText(invalidTargets, toPersianNumber(invalidCount));
    setText(readinessPercentTargets, `${toPersianNumber(readiness)}٪`);
    setText(readinessBadgeTargets, `${toPersianNumber(readiness)}٪`);

    if (readinessBar) readinessBar.style.width = `${readiness}%`;
    if (readinessTitle) readinessTitle.textContent = title;
    if (readinessDescription) readinessDescription.textContent = description;

    if (reviewMessage) {
      if (!canSchedule) {
        reviewMessage.textContent = "سالن در این روز تعطیل است یا ساعت کاری فعالی ندارد؛ امکان ثبت برنامه کاری وجود ندارد.";
      } else if (rows.length === 0) {
        reviewMessage.textContent = "فرم بدون ردیف ذخیره می‌شود و این روز برای عضو بدون شیفت باقی می‌ماند.";
      } else if (needsAttention > 0) {
        reviewMessage.textContent = `${toPersianNumber(needsAttention)} ردیف نیازمند اصلاح است. قبل از ذخیره، موارد مشخص‌شده را کامل کن.`;
      } else {
        reviewMessage.textContent = "برنامه روز آماده ذخیره است و همه ردیف‌ها زمان معتبر دارند.";
      }
    }

    emptyState?.classList.toggle("hidden", rows.length > 0);
    refreshWorkspaceLayout();
  };

  const removeRow = (row) => {
    if (!row) return;
    row.remove();
    updateUIState();
  };

  addButton.addEventListener("click", () => {
    if (addButton.disabled) return;

    const html = template.innerHTML.replaceAll("__index__", String(rowIndex));
    rowIndex += 1;

    const wrapper = document.createElement("div");
    wrapper.innerHTML = html.trim();
    const newRow = wrapper.firstElementChild;

    if (!newRow) return;

    rowsContainer.appendChild(newRow);
    updateUIState();
    newRow.scrollIntoView({ behavior: "smooth", block: "nearest" });
  });

  rowsContainer.addEventListener("click", (event) => {
    const removeButton = event.target.closest("[data-remove-shift-row]");
    if (!removeButton) return;

    const row = removeButton.closest("[data-shift-row]");
    removeRow(row);
  });

  rowsContainer.addEventListener("input", updateUIState);
  rowsContainer.addEventListener("change", updateUIState);

  updateUIState();
}
