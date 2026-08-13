let salonWorkingHoursBound = false;

function normalizeDigits(value) {
  const fa = "۰۱۲۳۴۵۶۷۸۹";
  const ar = "٠١٢٣٤٥٦٧٨٩";
  return String(value || "")
    .split("")
    .map((char) => {
      const faIndex = fa.indexOf(char);
      if (faIndex > -1) return String(faIndex);
      const arIndex = ar.indexOf(char);
      return arIndex > -1 ? String(arIndex) : char;
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
  const openMinutes = timeToMinutes(openValue);
  const closeMinutes = timeToMinutes(closeValue);

  let issue = "";
  if (active && (!openValue || !closeValue)) {
    issue = "برای روز فعال، ساعت شروع و پایان را کامل کن.";
  } else if (active && (!isValidTime(openValue) || !isValidTime(closeValue))) {
    issue = "ساعت واردشده معتبر نیست.";
  } else if (active && closeMinutes <= openMinutes) {
    issue = "ساعت پایان باید بعد از ساعت شروع باشد.";
  }

  return {
    active,
    openValue,
    closeValue,
    complete: active && !issue,
    invalid: Boolean(issue),
    issue,
  };
}

function syncDayRow(row) {
  const checkbox = row.querySelector('input[type="checkbox"]');
  const status = row.querySelector("[data-day-status]");
  const statusHelp = row.querySelector("[data-day-status-help]");
  const validation = row.querySelector("[data-day-validation]");
  const { openInput, closeInput } = getRowTimeInputs(row);
  const state = getRowState(row);

  [openInput, closeInput].forEach((input) => {
    if (!input) return;
    input.disabled = !state.active;
    input.classList.toggle("opacity-55", !state.active);
  });

  row.querySelectorAll("[data-time-trigger]").forEach((button) => {
    button.disabled = !state.active;
    button.classList.toggle("opacity-40", !state.active);
    button.classList.toggle("cursor-not-allowed", !state.active);
  });

  if (status) status.textContent = state.active ? "فعال" : "تعطیل";

  if (statusHelp) {
    if (!state.active) {
      statusHelp.textContent = "تعطیل";
    } else if (state.complete) {
      statusHelp.textContent = `${toPersianDigits(state.openValue)} تا ${toPersianDigits(state.closeValue)}`;
    } else {
      statusHelp.textContent = "ساعت این روز را کامل کن";
    }
  }

  row.classList.toggle("border-loomera-primary/25", state.complete);
  row.classList.toggle("border-loomera-danger/30", state.invalid);

  if (validation) {
    validation.textContent = state.issue;
    validation.classList.toggle("hidden", !state.invalid);
  }
}

function syncAllRows(rows) {
  rows.forEach(syncDayRow);
}

function dispatchValueChange(input) {
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

function setTimeValue(input, value) {
  if (!input) return;
  if (input._flatpickr) {
    input._flatpickr.setDate(value, true, "H:i");
  } else {
    input.value = value;
    dispatchValueChange(input);
  }
}

function initTimePicker(input) {
  if (!input) return;

  input.setAttribute("inputmode", "numeric");
  input.setAttribute("autocomplete", "off");

  if (typeof window.flatpickr === "function") {
    window.flatpickr(input, {
      enableTime: true,
      noCalendar: true,
      dateFormat: "H:i",
      time_24hr: true,
      minuteIncrement: 15,
      allowInput: true,
      disableMobile: true,
      defaultDate: isValidTime(input.value) ? input.value : null,
      onChange: () => dispatchValueChange(input),
      onClose: () => dispatchValueChange(input),
    });
    return;
  }

  // Fail-safe: if the library CDN is unavailable, keep the form usable.
  input.type = "time";
  input.step = "900";
}

function openPickerFor(targetId) {
  const input = document.getElementById(targetId);
  if (!input || input.disabled) return;
  if (input._flatpickr) {
    input._flatpickr.open();
  } else {
    input.showPicker?.();
    input.focus();
  }
}

function showBulkFeedback(message, type = "success") {
  const feedback = document.querySelector("[data-working-hours-apply-all-feedback]");
  if (!feedback) return;

  feedback.textContent = message;
  feedback.className = "mt-3 rounded-2xl border px-4 py-3 text-xs font-bold";
  feedback.classList.add(
    type === "error" ? "border-loomera-danger/20" : "border-loomera-primary/15",
    type === "error" ? "bg-loomera-dangerSoft" : "bg-white",
    type === "error" ? "text-loomera-danger" : "text-loomera-primaryText",
  );
}

function applySharedHours(rows, startInput, endInput) {
  const start = normalizeDigits(startInput?.value || "").trim();
  const end = normalizeDigits(endInput?.value || "").trim();

  if (!isValidTime(start) || !isValidTime(end)) {
    showBulkFeedback("ساعت شروع و پایان را انتخاب کن.", "error");
    return;
  }
  if (timeToMinutes(end) <= timeToMinutes(start)) {
    showBulkFeedback("ساعت پایان باید بعد از ساعت شروع باشد.", "error");
    return;
  }

  rows.forEach((row) => {
    const checkbox = row.querySelector('input[type="checkbox"]');
    const { openInput, closeInput } = getRowTimeInputs(row);
    if (!checkbox || !openInput || !closeInput) return;

    checkbox.checked = true;
    setTimeValue(openInput, start);
    setTimeValue(closeInput, end);
  });

  syncAllRows(rows);
  showBulkFeedback(`ساعت ${toPersianDigits(start)} تا ${toPersianDigits(end)} برای همه روزها ثبت شد. روزهای متفاوت را جدا ویرایش کن.`);
}

function enforceSingleOpenDay(rows, openedRow) {
  if (!openedRow.open) return;
  rows.forEach((row) => {
    if (row !== openedRow) row.open = false;
  });
}

export default function initSalonWorkingHoursStep() {
  if (salonWorkingHoursBound) return;
  salonWorkingHoursBound = true;

  const root = document.querySelector("[data-working-hours-step-page]");
  if (!root) return;

  const rows = Array.from(root.querySelectorAll("[data-working-day-row]"));
  const bulkStart = document.getElementById("working_hours_bulk_open");
  const bulkEnd = document.getElementById("working_hours_bulk_close");
  const applyAllButton = root.querySelector("[data-working-hours-apply-all]");

  const timeInputs = [
    bulkStart,
    bulkEnd,
    ...rows.flatMap((row) => {
      const { openInput, closeInput } = getRowTimeInputs(row);
      return [openInput, closeInput];
    }),
  ].filter(Boolean);

  timeInputs.forEach(initTimePicker);

  root.querySelectorAll("[data-time-trigger]").forEach((button) => {
    button.addEventListener("click", () => openPickerFor(button.dataset.targetInput));
  });

  rows.forEach((row) => {
    row.addEventListener("toggle", () => enforceSingleOpenDay(rows, row));

    const checkbox = row.querySelector('input[type="checkbox"]');
    checkbox?.addEventListener("change", () => {
      if (checkbox.checked) {
        row.open = true;
        enforceSingleOpenDay(rows, row);
      }
      syncDayRow(row);
    });

    const { openInput, closeInput } = getRowTimeInputs(row);
    [openInput, closeInput].forEach((input) => {
      input?.addEventListener("input", () => syncDayRow(row));
      input?.addEventListener("change", () => syncDayRow(row));
    });
  });

  const firstInvalid = rows.find((row) => getRowState(row).invalid);
  if (firstInvalid) {
    rows.forEach((row) => { row.open = row === firstInvalid; });
  }

  applyAllButton?.addEventListener("click", () => applySharedHours(rows, bulkStart, bulkEnd));
  syncAllRows(rows);
}

document.addEventListener("DOMContentLoaded", initSalonWorkingHoursStep);
