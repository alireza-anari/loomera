export default function initAddTimeOff() {
  const form = document.querySelector("[data-time-off-form]");
  const allDayToggle = document.querySelector("[data-all-day-toggle]");
  const reasonSelect = document.getElementById("id_reason_choice");
  const startSelect = document.getElementById("id_start_time");
  const endSelect = document.getElementById("id_end_time");
  const startPicker = document.getElementById("time_off_start_picker");
  const endPicker = document.getElementById("time_off_end_picker");
  const hint = document.querySelector("[data-time-off-hint]");

  if (
    !form ||
    !allDayToggle ||
    !reasonSelect ||
    !startSelect ||
    !endSelect ||
    !startPicker ||
    !endPicker
  ) {
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

  reasonSelect.classList.add(
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
    "focus:ring-loomera-primary/10"
  );

  const toPersianDigits = (value) =>
    String(value).replace(/\d/g, (digit) => "۰۱۲۳۴۵۶۷۸۹"[Number(digit)]);

  const parseMinutes = (value) => {
    const match = /^(\d{1,2}):(\d{2})$/.exec(value || "");
    if (!match) return null;
    return Number(match[1]) * 60 + Number(match[2]);
  };

  const validOptions = (select) =>
    Array.from(select.options)
      .map((option) => option.value)
      .filter(Boolean);

  const startOptions = validOptions(startSelect);
  const endOptions = validOptions(endSelect);

  const pickerState = new Map();

  const dispatchSelectChange = (select) => {
    select.dispatchEvent(new Event("change", { bubbles: true }));
  };

  const syncProxyFromSelect = (select, input) => {
    input.value = select.value || "";
    const instance = pickerState.get(input);
    if (instance) {
      if (select.value) instance.setDate(select.value, false, "H:i");
      else instance.clear(false);
    }
  };

  const nearestAllowedValue = (values, value) => {
    if (!value || !values.length) return "";
    if (values.includes(value)) return value;

    const target = parseMinutes(value);
    if (target === null) return "";

    return values.reduce((nearest, candidate) => {
      if (!nearest) return candidate;
      const candidateMinutes = parseMinutes(candidate);
      const nearestMinutes = parseMinutes(nearest);
      if (candidateMinutes === null) return nearest;
      if (nearestMinutes === null) return candidate;
      return Math.abs(candidateMinutes - target) < Math.abs(nearestMinutes - target)
        ? candidate
        : nearest;
    }, "");
  };

  const setSelectFromPicker = (select, input, value) => {
    const values = validOptions(select);
    const nextValue = nearestAllowedValue(values, value);
    input.value = nextValue;
    if (select.value === nextValue) return;
    select.value = nextValue;
    dispatchSelectChange(select);
  };

  const initPicker = (input, select, options) => {
    input.value = select.value || "";

    const trigger = document.querySelector(
      `[data-time-off-picker-trigger][data-target-input="${input.id}"]`
    );

    if (typeof window.flatpickr === "function" && options.length) {
      const instance = window.flatpickr(input, {
        enableTime: true,
        noCalendar: true,
        dateFormat: "H:i",
        time_24hr: true,
        minuteIncrement: 30,
        allowInput: false,
        clickOpens: true,
        minTime: options[0],
        maxTime: options[options.length - 1],
        defaultDate: select.value || null,
        onChange: (_selectedDates, value) => {
          setSelectFromPicker(select, input, value);
        },
        onClose: (_selectedDates, value) => {
          if (value) setSelectFromPicker(select, input, value);
        },
      });
      pickerState.set(input, instance);
    }

    input.addEventListener("change", () => {
      setSelectFromPicker(select, input, input.value);
    });

    trigger?.addEventListener("click", () => {
      if (input.disabled) return;
      const instance = pickerState.get(input);
      if (instance) instance.open();
      else input.focus();
    });
  };

  initPicker(startPicker, startSelect, startOptions);
  initPicker(endPicker, endSelect, endOptions);

  const formatRange = () => {
    if (allDayToggle.checked) return "همه روز";
    if (startSelect.value && endSelect.value) {
      return `${toPersianDigits(startSelect.value)} تا ${toPersianDigits(endSelect.value)}`;
    }
    if (startSelect.value || endSelect.value) return "بازه ناقص";
    return "انتخاب نشده";
  };

  const refreshWorkspace = () => {
    window.requestAnimationFrame(() => {
      window.LoomeraDashboardWorkspace?.refresh?.(
        document.querySelector("[data-dashboard-workspace-root]")
      );
    });
  };

  const calculateReadiness = () => {
    const hasReason = Boolean(reasonSelect.value);
    const isAllDay = allDayToggle.checked;
    const startMinutes = parseMinutes(startSelect.value);
    const endMinutes = parseMinutes(endSelect.value);
    const hasBothTimes = startMinutes !== null && endMinutes !== null;
    const validRange = hasBothTimes && endMinutes > startMinutes;
    const invalidPartial =
      !isAllDay && Boolean(startSelect.value || endSelect.value) && !hasBothTimes;
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

  const setPickerDisabled = (input, disabled) => {
    input.disabled = disabled;
    const trigger = document.querySelector(
      `[data-time-off-picker-trigger][data-target-input="${input.id}"]`
    );
    if (trigger) trigger.disabled = disabled;
  };

  const syncState = () => {
    const state = calculateReadiness();
    const isAllDay = state.isAllDay;
    const noHourlySlots = startOptions.length === 0 || endOptions.length === 0;

    startSelect.disabled = isAllDay;
    endSelect.disabled = isAllDay;
    setPickerDisabled(startPicker, isAllDay || noHourlySlots);
    setPickerDisabled(endPicker, isAllDay || noHourlySlots);

    if (isAllDay) {
      startSelect.value = "";
      endSelect.value = "";
      syncProxyFromSelect(startSelect, startPicker);
      syncProxyFromSelect(endSelect, endPicker);
    }

    if (hint) {
      if (isAllDay) {
        hint.textContent =
          "مرخصی تمام‌روز ثبت می‌شود و همه شیفت‌های این روز تحت تأثیر قرار می‌گیرند.";
      } else if (noHourlySlots) {
        hint.textContent =
          "برای این روز ساعت کاری فعالی ثبت نشده است؛ مرخصی ساعتی قابل انتخاب نیست.";
      } else {
        hint.textContent =
          "مرخصی ساعتی ثبت می‌شود و فقط بازه‌های کاری هم‌پوشان با ساعت انتخاب‌شده تحت تأثیر قرار می‌گیرند.";
      }
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
        : "مرخصی ساعتی آماده ثبت است؛ فقط بازه‌های هم‌پوشان تحت تأثیر قرار می‌گیرند.";
    }

    if (readinessTitle) readinessTitle.textContent = title;
    if (readinessDesc) readinessDesc.textContent = desc;
    if (submitTitle) submitTitle.textContent = nextState.ready ? "آماده ثبت مرخصی" : title;
    if (submitDesc) submitDesc.textContent = desc;

    [startPicker, endPicker].forEach((field) => {
      field.classList.toggle(
        "border-loomera-danger/40",
        nextState.invalidPartial || nextState.invalidRange
      );
      field.classList.toggle(
        "focus:ring-loomera-danger/10",
        nextState.invalidPartial || nextState.invalidRange
      );
    });

    refreshWorkspace();
  };

  const maybeUnsetAllDay = () => {
    if (startSelect.value || endSelect.value) {
      allDayToggle.checked = false;
    }
    syncProxyFromSelect(startSelect, startPicker);
    syncProxyFromSelect(endSelect, endPicker);
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
