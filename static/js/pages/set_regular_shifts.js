export default function initSetRegularShifts() {
  const form = document.querySelector("[data-regular-shifts-form]");
  const template = document.getElementById("regularShiftRowTemplate");
  const dayCards = Array.from(document.querySelectorAll("[data-regular-day]"));
  const mobileDaysQuery = window.matchMedia("(max-width: 767px)");

  const startDateInput = document.querySelector("[data-regular-start-date]");
  const endDateInput = document.querySelector("[data-regular-end-date]");
  const readinessBar = document.querySelector("[data-regular-readiness-bar]");
  const readinessPercent = document.querySelector("[data-regular-readiness-percent]");
  const readinessBadge = document.querySelector("[data-regular-readiness-badge]");
  const readinessStatus = document.querySelector("[data-regular-readiness-status]");
  const readinessNote = document.querySelector("[data-regular-readiness-note]");
  const selectedDaysCount = document.querySelector("[data-regular-selected-days-count]");
  const selectedRangesCount = document.querySelector("[data-regular-selected-ranges-count]");
  const selectedRangesBadge = document.querySelector("[data-regular-selected-ranges-badge]");
  const reviewStart = document.querySelector("[data-regular-review-start]");
  const reviewEnd = document.querySelector("[data-regular-review-end]");
  const reviewDays = document.querySelector("[data-regular-review-days]");
  const reviewRanges = document.querySelector("[data-regular-review-ranges]");
  const openFirstDayButton = document.querySelector("[data-open-first-day]");
  const openAllDaysButton = document.querySelector("[data-open-all-days]");

  const toPersianDigits = (value) =>
    String(value ?? "").replace(/\d/g, (digit) => "۰۱۲۳۴۵۶۷۸۹"[Number(digit)]);

  const scheduleWorkspaceRefresh = () => {
    window.requestAnimationFrame(() => {
      if (window.LoomeraDashboardWorkspace?.refresh) {
        window.LoomeraDashboardWorkspace.refresh(document.querySelector("[data-regular-shifts-page]") || document);
      }
    });
  };

  if (typeof jalaliDatepicker !== "undefined") {
    try {
      jalaliDatepicker.startWatch({
        selector: "[data-jalali-date]",
        autoHide: true,
      });
    } catch (error) {
      console.warn("[set-regular-shifts] jalaliDatepicker initialization failed");
    }
  }

  if (!form || !template || !dayCards.length) return;

  const normalizeTime = (value) => {
    const parts = String(value || "").split(":");
    const hour = Number.parseInt(parts[0], 10);
    const minute = Number.parseInt(parts[1], 10);
    if (!Number.isFinite(hour) || !Number.isFinite(minute)) return "";
    return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
  };

  const timeToMinutes = (value) => {
    const normalized = normalizeTime(value);
    if (!normalized) return null;
    const [hour, minute] = normalized.split(":").map((part) => Number.parseInt(part, 10));
    return hour * 60 + minute;
  };

  const minutesToTime = (minutes) => {
    const hour = Math.floor(minutes / 60);
    const minute = minutes % 60;
    return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
  };

  const buildTimeOptions = (select, { openTime = "", closeTime = "", selectedValue = "", isEnd = false } = {}) => {
    if (!select) return;

    const startMinutes = timeToMinutes(openTime);
    const endMinutes = timeToMinutes(closeTime);
    const selected = normalizeTime(selectedValue);
    const placeholder = isEnd ? "انتخاب پایان" : "انتخاب شروع";
    const options = [`<option value="">${placeholder}</option>`];

    if (startMinutes !== null && endMinutes !== null && endMinutes > startMinutes) {
      for (let minute = startMinutes; minute <= endMinutes; minute += 30) {
        const value = minutesToTime(minute);
        options.push(`<option value="${value}"${value === selected ? " selected" : ""}>${toPersianDigits(value)}</option>`);
      }

      if ((endMinutes - startMinutes) % 30 !== 0) {
        const value = minutesToTime(endMinutes);
        options.push(`<option value="${value}"${value === selected ? " selected" : ""}>${toPersianDigits(value)}</option>`);
      }
    }

    select.innerHTML = options.join("");
    select.dataset.minTime = normalizeTime(openTime);
    select.dataset.maxTime = normalizeTime(closeTime);
  };

  const markRowInvalid = (row, invalid) => {
    row.classList.toggle("border-loomera-error/30", invalid);
    row.classList.toggle("bg-loomera-errorSoft/35", invalid);
  };

  const createRow = ({ openTime = "", closeTime = "", fillFull = false } = {}) => {
    const wrapper = document.createElement("div");
    wrapper.innerHTML = template.innerHTML.trim();
    const row = wrapper.firstElementChild;
    const startSelect = row.querySelector("[data-start-time]");
    const endSelect = row.querySelector("[data-end-time]");
    const normalizedOpen = normalizeTime(openTime);
    const normalizedClose = normalizeTime(closeTime);

    buildTimeOptions(startSelect, {
      openTime: normalizedOpen,
      closeTime: normalizedClose,
      selectedValue: fillFull ? normalizedOpen : "",
    });

    buildTimeOptions(endSelect, {
      openTime: normalizedOpen,
      closeTime: normalizedClose,
      selectedValue: fillFull ? normalizedClose : "",
      isEnd: true,
    });

    return row;
  };

  const getDayValues = (dayCard) => {
    const rows = Array.from(dayCard.querySelectorAll("[data-shift-row]"));
    const values = [];
    let invalidCount = 0;

    rows.forEach((row) => {
      const startInput = row.querySelector("[data-start-time]");
      const endInput = row.querySelector("[data-end-time]");
      const startValue = normalizeTime(startInput?.value || "");
      const endValue = normalizeTime(endInput?.value || "");
      const minTime = normalizeTime(startInput?.dataset.minTime || dayCard.dataset.openTime || "");
      const maxTime = normalizeTime(endInput?.dataset.maxTime || dayCard.dataset.closeTime || "");
      const incomplete = (startValue && !endValue) || (!startValue && endValue);
      const reversed = startValue && endValue && endValue <= startValue;
      const outsideOpen = minTime && startValue && startValue < minTime;
      const outsideClose = maxTime && endValue && endValue > maxTime;
      const invalid = incomplete || reversed || outsideOpen || outsideClose;

      markRowInvalid(row, invalid);
      if (invalid) invalidCount += 1;
      if (startValue && endValue && !reversed && !outsideOpen && !outsideClose) {
        values.push(`${startValue}-${endValue}`);
      }
    });

    return { rows, values, invalidCount };
  };

  const closeOtherDayCards = (activeCard) => {
    if (!mobileDaysQuery.matches || !activeCard?.open) return;
    dayCards.forEach((card) => {
      if (card !== activeCard) card.open = false;
    });
  };

  const openFirstAvailableDay = () => {
    const firstOpenDay = dayCards.find((card) => card.dataset.dayOpen === "1") || dayCards[0];
    if (!firstOpenDay) return;
    firstOpenDay.open = true;
    closeOtherDayCards(firstOpenDay);
    firstOpenDay.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  const updateSummary = () => {
    let daysWithPlan = 0;
    let rangesCount = 0;
    let invalidCount = 0;

    dayCards.forEach((dayCard) => {
      const { values, invalidCount: dayInvalidCount } = getDayValues(dayCard);
      if (values.length > 0) daysWithPlan += 1;
      rangesCount += values.length;
      invalidCount += dayInvalidCount;
    });

    const hasStart = Boolean((startDateInput?.value || "").trim());
    const hasEnd = Boolean((endDateInput?.value || "").trim());
    const hasDateRange = hasStart && hasEnd;
    const hasSchedule = rangesCount > 0;
    let progress = 0;

    if (hasStart) progress += 25;
    if (hasEnd) progress += 25;
    if (daysWithPlan > 0) progress += 25;
    if (rangesCount > 0 && invalidCount === 0) progress += 25;

    const progressLabel = `${toPersianDigits(progress)}٪`;
    if (readinessBar) readinessBar.style.width = `${progress}%`;
    if (readinessPercent) readinessPercent.textContent = progressLabel;
    if (readinessBadge) readinessBadge.textContent = progressLabel;

    if (readinessStatus && readinessNote) {
      if (progress >= 100) {
        readinessStatus.textContent = "آماده ثبت";
        readinessNote.textContent = "تاریخ‌ها و بازه‌های شیفت کامل هستند. حالا می‌توانی ثبت نهایی را انجام بدهی.";
      } else if (invalidCount > 0) {
        readinessStatus.textContent = "نیازمند اصلاح زمان‌ها";
        readinessNote.textContent = "بعضی بازه‌ها ناقص، خارج از ساعت کاری یا دارای پایان زودتر از شروع هستند.";
      } else if (!hasDateRange) {
        readinessStatus.textContent = "تاریخ‌ها کامل نیستند";
        readinessNote.textContent = "برای اعمال گروهی، تاریخ شروع و پایان را مشخص کن.";
      } else if (!hasSchedule) {
        readinessStatus.textContent = "الگوی هفته خالی است";
        readinessNote.textContent = "برای حداقل یک روز بازه کاری تعریف کن.";
      } else {
        readinessStatus.textContent = "در حال تکمیل";
        readinessNote.textContent = "اطلاعات اصلی تکمیل شده اما هنوز بهتر است بازبینی نهایی انجام شود.";
      }
    }

    const daysLabel = `${toPersianDigits(daysWithPlan)} روز برنامه‌دار`;
    const rangesLabel = `${toPersianDigits(rangesCount)} بازه`;
    if (selectedDaysCount) selectedDaysCount.textContent = daysLabel;
    if (selectedRangesCount) selectedRangesCount.textContent = rangesLabel;
    if (selectedRangesBadge) selectedRangesBadge.textContent = toPersianDigits(rangesCount);
    if (reviewDays) reviewDays.textContent = daysLabel;
    if (reviewRanges) reviewRanges.textContent = rangesLabel;
    if (reviewStart) reviewStart.textContent = startDateInput?.value || "—";
    if (reviewEnd) reviewEnd.textContent = endDateInput?.value || "—";
  };

  const updateDayState = (dayCard) => {
    const hiddenInput = dayCard.querySelector("[data-day-hidden]");
    const countTarget = dayCard.querySelector("[data-day-count]");
    const emptyState = dayCard.querySelector("[data-day-empty]");
    const { rows, values } = getDayValues(dayCard);

    if (hiddenInput) hiddenInput.value = values.join(",");
    if (countTarget) countTarget.textContent = toPersianDigits(values.length);
    emptyState?.classList.toggle("hidden", rows.length > 0);
    dayCard.classList.toggle("border-loomera-primary/30", values.length > 0);
    dayCard.classList.toggle("bg-loomera-primarySoft/10", values.length > 0);
    updateSummary();
  };

  dayCards.forEach((dayCard) => {
    const rowsContainer = dayCard.querySelector("[data-day-rows]");
    const addRowButton = dayCard.querySelector("[data-add-row]");
    const fillFullButton = dayCard.querySelector("[data-fill-full]");
    const isOpen = dayCard.dataset.dayOpen === "1";
    const openTime = dayCard.dataset.openTime || "";
    const closeTime = dayCard.dataset.closeTime || "";

    dayCard.addEventListener("toggle", () => {
      closeOtherDayCards(dayCard);
      scheduleWorkspaceRefresh();
    });

    addRowButton?.addEventListener("click", () => {
      if (!isOpen || !rowsContainer) return;
      dayCard.open = true;
      closeOtherDayCards(dayCard);
      rowsContainer.appendChild(createRow({ openTime, closeTime }));
      updateDayState(dayCard);
      scheduleWorkspaceRefresh();
    });

    fillFullButton?.addEventListener("click", () => {
      if (!isOpen || !rowsContainer) return;
      dayCard.open = true;
      closeOtherDayCards(dayCard);
      rowsContainer.appendChild(createRow({ openTime, closeTime, fillFull: true }));
      updateDayState(dayCard);
      scheduleWorkspaceRefresh();
    });

    rowsContainer?.addEventListener("click", (event) => {
      const removeButton = event.target.closest("[data-remove-row]");
      if (!removeButton) return;
      removeButton.closest("[data-shift-row]")?.remove();
      updateDayState(dayCard);
      scheduleWorkspaceRefresh();
    });

    ["input", "change"].forEach((eventName) => {
      rowsContainer?.addEventListener(eventName, () => updateDayState(dayCard));
    });

    updateDayState(dayCard);
  });

  openFirstDayButton?.addEventListener("click", openFirstAvailableDay);
  openAllDaysButton?.addEventListener("click", () => {
    dayCards.forEach((card) => {
      card.open = true;
    });
    scheduleWorkspaceRefresh();
  });

  [startDateInput, endDateInput].forEach((input) => {
    input?.addEventListener("input", updateSummary);
    input?.addEventListener("change", updateSummary);
  });

  form.addEventListener("submit", (event) => {
    let hasClientError = false;
    dayCards.forEach((dayCard) => {
      updateDayState(dayCard);
      if (getDayValues(dayCard).invalidCount > 0) {
        hasClientError = true;
        dayCard.open = true;
      }
    });

    updateSummary();
    if (hasClientError) {
      event.preventDefault();
      window.alert("بعضی از بازه‌ها ناقص، خارج از ساعت کاری یا دارای زمان پایان نامعتبر هستند. لطفاً قبل از ذخیره اصلاحشان کن.");
    }
  });

  window.addEventListener("resize", () => {
    if (mobileDaysQuery.matches) {
      closeOtherDayCards(dayCards.find((card) => card.open) || dayCards[0]);
    }
    scheduleWorkspaceRefresh();
  }, { passive: true });

  if (mobileDaysQuery.matches) openFirstAvailableDay();
  updateSummary();
  scheduleWorkspaceRefresh();
}
