export default function initAddTimeOff() {
  const form = document.querySelector("[data-time-off-form]");
  const allDayToggle = document.querySelector("[data-all-day-toggle]");
  const reasonSelect = document.getElementById("id_reason_choice");
  const startSelect = document.getElementById("id_start_time");
  const endSelect = document.getElementById("id_end_time");
  const hint = document.querySelector("[data-time-off-hint]");

  if (!form || !allDayToggle || !reasonSelect || !startSelect || !endSelect) {
    return;
  }

  const readinessTitle = document.querySelector("[data-time-off-readiness-title]");
  const readinessDesc = document.querySelector("[data-time-off-readiness-desc]");
  const readinessPercent = document.querySelector("[data-time-off-readiness-percent]");
  const readinessBar = document.querySelector("[data-time-off-readiness-bar]");
  const summaryMode = document.querySelector("[data-time-off-summary-mode]");
  const summaryRange = document.querySelector("[data-time-off-summary-range]");
  const submitTitle = document.querySelector("[data-time-off-submit-title]");
  const submitDesc = document.querySelector("[data-time-off-submit-desc]");

  const selectClasses = [
    "w-full",
    "rounded-2xl",
    "border",
    "border-loomera-borderSoft",
    "bg-white",
    "px-4",
    "py-3",
    "text-sm",
    "font-bold",
    "text-loomera-textPrimary",
    "outline-none",
    "transition",
    "focus:border-loomera-primary/40",
    "focus:ring-4",
    "focus:ring-loomera-primary/10",
    "disabled:cursor-not-allowed",
    "disabled:bg-loomera-bgSubtle",
    "disabled:text-loomera-textMuted",
  ];

  [reasonSelect, startSelect, endSelect].forEach((field) => {
    field.classList.add(...selectClasses);
  });

  const toPersianDigits = (value) =>
    String(value).replace(/\d/g, (digit) => "۰۱۲۳۴۵۶۷۸۹"[Number(digit)]);

  const parseMinutes = (value) => {
    const match = /^(\d{1,2}):(\d{2})$/.exec(value || "");
    if (!match) return null;
    return Number(match[1]) * 60 + Number(match[2]);
  };

  const formatRange = () => {
    if (allDayToggle.checked) return "همه روز";
    if (startSelect.value && endSelect.value) return `${toPersianDigits(startSelect.value)} تا ${toPersianDigits(endSelect.value)}`;
    if (startSelect.value || endSelect.value) return "بازه ناقص";
    return "انتخاب نشده";
  };

  const refreshWorkspace = () => {
    window.requestAnimationFrame(() => {
      window.LoomeraDashboardWorkspace?.refresh?.(document.querySelector("[data-dashboard-workspace-root]"));
    });
  };

  const calculateReadiness = () => {
    const hasReason = Boolean(reasonSelect.value);
    const isAllDay = allDayToggle.checked;
    const startMinutes = parseMinutes(startSelect.value);
    const endMinutes = parseMinutes(endSelect.value);
    const hasBothTimes = startMinutes !== null && endMinutes !== null;
    const validRange = hasBothTimes && endMinutes > startMinutes;
    const invalidPartial = !isAllDay && Boolean(startSelect.value || endSelect.value) && !hasBothTimes;
    const invalidRange = !isAllDay && hasBothTimes && !validRange;

    let score = 0;
    if (hasReason) score += 45;
    if (isAllDay) score += 55;
    if (!isAllDay && validRange) score += 55;

    const percent = Math.min(score, 100);
    const ready = hasReason && (isAllDay || validRange);

    return {
      hasReason,
      isAllDay,
      invalidPartial,
      invalidRange,
      percent,
      ready,
      validRange,
    };
  };

  const syncState = () => {
    const state = calculateReadiness();
    const isAllDay = state.isAllDay;

    startSelect.disabled = isAllDay;
    endSelect.disabled = isAllDay;

    if (isAllDay) {
      startSelect.value = "";
      endSelect.value = "";
    }

    if (hint) {
      hint.textContent = isAllDay
        ? "مرخصی تمام‌روز ثبت می‌شود و همه شیفت‌های این روز حذف خواهند شد."
        : "مرخصی ساعتی ثبت می‌شود و فقط شیفت‌های متداخل با این بازه حذف خواهند شد.";
    }

    const nextState = calculateReadiness();

    if (readinessPercent) readinessPercent.textContent = `${toPersianDigits(nextState.percent)}٪`;
    if (readinessBar) readinessBar.style.width = `${nextState.percent}%`;
    if (summaryMode) summaryMode.textContent = nextState.isAllDay ? "تمام‌روز" : "ساعتی";
    if (summaryRange) summaryRange.textContent = formatRange();

    let title = "آماده تکمیل اطلاعات";
    let desc = "نوع مرخصی و حالت تمام‌روز یا ساعتی را مشخص کن.";

    if (!nextState.hasReason) {
      title = "نوع مرخصی انتخاب نشده";
      desc = "برای ثبت نهایی ابتدا نوع مرخصی را مشخص کن.";
    } else if (nextState.invalidPartial) {
      title = "بازه ساعتی ناقص است";
      desc = "برای مرخصی ساعتی، ساعت شروع و پایان باید با هم انتخاب شوند.";
    } else if (nextState.invalidRange) {
      title = "بازه زمانی معتبر نیست";
      desc = "ساعت پایان باید بعد از ساعت شروع باشد.";
    } else if (nextState.ready) {
      title = "فرم آماده ثبت است";
      desc = nextState.isAllDay
        ? "مرخصی تمام‌روز آماده ثبت است؛ اثر آن روی شیفت‌های روز را مرور کن."
        : "مرخصی ساعتی آماده ثبت است؛ فقط شیفت‌های متداخل تحت تأثیر قرار می‌گیرند.";
    }

    if (readinessTitle) readinessTitle.textContent = title;
    if (readinessDesc) readinessDesc.textContent = desc;
    if (submitTitle) submitTitle.textContent = nextState.ready ? "آماده ثبت مرخصی" : title;
    if (submitDesc) submitDesc.textContent = desc;

    [startSelect, endSelect].forEach((field) => {
      field.classList.toggle("border-loomera-danger/40", nextState.invalidPartial || nextState.invalidRange);
      field.classList.toggle("focus:ring-loomera-danger/10", nextState.invalidPartial || nextState.invalidRange);
    });

    refreshWorkspace();
  };

  const maybeUnsetAllDay = () => {
    if (startSelect.value || endSelect.value) {
      allDayToggle.checked = false;
    }
    syncState();
  };

  allDayToggle.addEventListener("change", syncState);
  reasonSelect.addEventListener("change", syncState);
  startSelect.addEventListener("change", maybeUnsetAllDay);
  endSelect.addEventListener("change", maybeUnsetAllDay);

  if (!startSelect.value && !endSelect.value) {
    allDayToggle.checked = true;
  }

  syncState();
}
