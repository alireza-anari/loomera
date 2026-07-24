const SLOT_STEP = 15;
const AVAILABILITY_MONTHS_TO_PRELOAD = 3;

function normalizeDigits(value) {
  return String(value || "")
    .replace(/[۰-۹]/g, (d) => "۰۱۲۳۴۵۶۷۸۹".indexOf(d))
    .replace(/[٠-٩]/g, (d) => "٠١٢٣٤٥٦٧٨٩".indexOf(d));
}

function toPersianDigits(value) {
  return String(value || "").replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[Number(d)]);
}

function parseIsoDate(dateStr) {
  const [y, m, d] = String(dateStr).split("-").map(Number);
  return new Date(y, (m || 1) - 1, d || 1);
}

function formatGregorianToJalali(dateStr, options = {}) {
  if (!dateStr) return "";
  const date = typeof dateStr === "string" ? parseIsoDate(dateStr) : dateStr;
  const [jy, jm, jd] = JalaliDate.gregorianToJalali(date.getFullYear(), date.getMonth() + 1, date.getDate());
  const months = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"];
  const weekdays = ["یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه", "شنبه"];
  const base = `${toPersianDigits(jd)} ${months[jm - 1]} ${toPersianDigits(jy)}`;
  return options.withWeekday ? `${weekdays[date.getDay()]} ${base}` : base;
}

function formatGregorianToJalaliNumeric(dateStr) {
  if (!dateStr) return "";
  const date = typeof dateStr === "string" ? parseIsoDate(dateStr) : dateStr;
  const [jy, jm, jd] = JalaliDate.gregorianToJalali(date.getFullYear(), date.getMonth() + 1, date.getDate());
  return `${toPersianDigits(jy)}/${toPersianDigits(String(jm).padStart(2, "0"))}/${toPersianDigits(String(jd).padStart(2, "0"))}`;
}

function jalaliInputToGregorian(jalaliValue) {
  const normalized = normalizeDigits(jalaliValue).replace(/\//g, "-").trim();
  const match = normalized.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
  if (!match) return null;
  const [gy, gm, gd] = JalaliDate.jalaliToGregorian(Number(match[1]), Number(match[2]), Number(match[3]));
  return `${gy}-${String(gm).padStart(2, "0")}-${String(gd).padStart(2, "0")}`;
}

function shiftJalaliMonth(year, month, delta) {
  let newYear = year;
  let newMonth = month + delta;
  while (newMonth > 12) { newMonth -= 12; newYear += 1; }
  while (newMonth < 1) { newMonth += 12; newYear -= 1; }
  return { year: newYear, month: newMonth };
}

function toMinutes(timeStr) {
  const [hour, minute] = String(timeStr).split(":").map(Number);
  return hour * 60 + minute;
}

function minutesToTime(minutes) {
  const hour = Math.floor(minutes / 60);
  const minute = minutes % 60;
  return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
}

function slotOverlaps(startA, endA, startB, endB) {
  return startA < endB && endA > startB;
}

export default function initManualBookingPage() {
  const source = document.getElementById("manualBookingData");
  if (!source) return;

  function readJsonScript(id) {
    const node = document.getElementById(id);
    if (!node) return [];
    try {
      return JSON.parse(node.textContent || "[]");
    } catch (error) {
      console.error("[manual-booking] invalid embedded data");
      return [];
    }
  }

  const state = {
    salonId: source.dataset.salonId,
    customers: readJsonScript("manualBookingCustomersData"),
    services: readJsonScript("manualBookingServicesData"),
    stylists: readJsonScript("manualBookingStylistsData"),
    schedules: {},
    bookedTimes: {},
    timeOffs: {},
    loadedMonths: new Set(),
    selectedDate: document.getElementById("id_appointment_date")?.value || "",
    selectedTime: document.getElementById("id_start_time")?.value || "",
    currentSlots: [],
  };

  const els = {
    customerInput: document.getElementById("customerAutocomplete"),
    customerHidden: document.getElementById("id_customer"),
    customerSuggestions: document.getElementById("customerSuggestions"),
    serviceInput: document.getElementById("serviceAutocomplete"),
    serviceHidden: document.getElementById("id_service"),
    serviceSuggestions: document.getElementById("serviceSuggestions"),
    stylistInput: document.getElementById("stylistAutocomplete"),
    stylistHidden: document.getElementById("id_stylist"),
    stylistSuggestions: document.getElementById("stylistSuggestions"),
    dateInput: document.getElementById("manualBookingDatePicker"),
    dateHidden: document.getElementById("id_appointment_date"),
    timeHidden: document.getElementById("id_start_time"),
    calendar: document.getElementById("manualBookingCalendar"),
    monthTitle: document.getElementById("manualBookingMonthTitle"),
    calendarHint: document.getElementById("manualBookingCalendarHint"),
    timeSlots: document.getElementById("manualBookingTimeSlots"),
    selectedDateLabel: document.getElementById("manualBookingSelectedDateLabel"),
    summaryCustomer: document.getElementById("manualBookingSummaryCustomer"),
    summaryService: document.getElementById("manualBookingSummaryService"),
    summaryStylist: document.getElementById("manualBookingSummaryStylist"),
    summaryDate: document.getElementById("manualBookingSummaryDate"),
    summaryTime: document.getElementById("manualBookingSummaryTime"),
    summaryStatus: document.getElementById("manualBookingSummaryStatus"),
    workspaceRoot: document.querySelector("[data-manual-booking-page]"),
  };

  function refreshWorkspaceLayout() {
    if (window.LoomeraDashboardWorkspace?.refresh && els.workspaceRoot) {
      window.LoomeraDashboardWorkspace.refresh(els.workspaceRoot);
    }
  }

  function findById(list, id) {
    return list.find((item) => String(item.id) === String(id));
  }

  function getSelectedCustomer() {
    return findById(state.customers, els.customerHidden.value);
  }

  function getSelectedService() {
    return findById(state.services, els.serviceHidden.value);
  }

  function getSelectedStylist() {
    return findById(state.stylists, els.stylistHidden.value);
  }
  function setText(element, value, fallback = "—") {
    if (!element) return;
    element.textContent = value || fallback;
  }

  function updateBookingSummary() {
    const customer = getSelectedCustomer();
    const service = getSelectedService();
    const stylist = getSelectedStylist();

    const customerLabel = customer?.label || els.customerInput?.value?.trim();
    const serviceLabel = service?.name || els.serviceInput?.value?.trim();
    const stylistLabel = stylist?.name || els.stylistInput?.value?.trim();

    const dateLabel = state.selectedDate
      ? formatGregorianToJalali(state.selectedDate, { withWeekday: true })
      : "";

    setText(els.summaryCustomer, customerLabel, "انتخاب نشده");
    setText(els.summaryService, serviceLabel, "انتخاب نشده");
    setText(els.summaryStylist, stylistLabel, "انتخاب نشده");
    setText(els.summaryDate, dateLabel, "—");
    setText(els.summaryTime, state.selectedTime, "—");

    if (els.summaryStatus) {
      const isReady = Boolean(
        els.customerHidden.value &&
        els.serviceHidden.value &&
        els.stylistHidden.value &&
        state.selectedDate &&
        state.selectedTime
      );

      els.summaryStatus.textContent = isReady
        ? "رزرو آماده ثبت است."
        : "برای ثبت، همه مراحل را کامل کن.";

      els.summaryStatus.classList.toggle("text-loomera-success", isReady);
      els.summaryStatus.classList.toggle("text-loomera-primaryText", !isReady);
    }
  }

  function syncInputLabelsFromHidden() {
    const customer = getSelectedCustomer();
    if (customer && !els.customerInput.value) els.customerInput.value = customer.label;

    const service = getSelectedService();
    if (service && !els.serviceInput.value) els.serviceInput.value = service.name;

    const stylist = getSelectedStylist();
    if (stylist && !els.stylistInput.value) els.stylistInput.value = stylist.name;

    if (state.selectedDate && !els.dateInput.value) {
      els.dateInput.value = formatGregorianToJalaliNumeric(state.selectedDate);
    }
    updateBookingSummary();
  }

  function resetScheduleSelection() {
    state.selectedDate = "";
    state.selectedTime = "";
    state.currentSlots = [];
    els.dateHidden.value = "";
    els.timeHidden.value = "";
    els.dateInput.value = "";
    els.selectedDateLabel.textContent = "";
    renderTimeSlots([]);
    updateBookingSummary();
  }

  function getServiceOptions(query = "") {
    const selectedStylist = getSelectedStylist();
    const normalizedQuery = normalizeDigits(query).trim().toLowerCase();
    return state.services.filter((service) => {
      const stylistCompatible = !selectedStylist || service.stylist_ids.includes(String(selectedStylist.id));
      const searchOk = !normalizedQuery || normalizeDigits(service.name).toLowerCase().includes(normalizedQuery);
      return stylistCompatible && searchOk;
    });
  }

  function getStylistOptions(query = "") {
    const selectedService = getSelectedService();
    const normalizedQuery = normalizeDigits(query).trim().toLowerCase();
    return state.stylists.filter((stylist) => {
      const serviceCompatible = !selectedService || stylist.service_ids.includes(String(selectedService.id));
      const searchOk = !normalizedQuery || normalizeDigits(stylist.name).toLowerCase().includes(normalizedQuery);
      return serviceCompatible && searchOk;
    });
  }

  function getCustomerOptions(query = "") {
    const normalizedQuery = normalizeDigits(query).trim().toLowerCase();
    return state.customers.filter((customer) => {
      if (!normalizedQuery) return true;
      return [customer.name, customer.family, customer.mobile, customer.label]
        .filter(Boolean)
        .some((part) => normalizeDigits(part).toLowerCase().includes(normalizedQuery));
    });
  }

  function renderSuggestionList(container, options, renderLabel, onSelect) {
    if (!container) return;
    if (!options.length) {
      container.innerHTML = '<div class="px-4 py-3 text-sm text-loomera-textMuted">موردی پیدا نشد.</div>';
      container.classList.remove("hidden");
      return;
    }

    container.innerHTML = options.map((option) => `
      <button type="button" class="flex w-full items-center justify-between gap-3 border-b border-loomera-borderSoft px-4 py-3 text-right text-sm text-loomera-textSecondary transition last:border-b-0 hover:bg-loomera-primarySoft/40 hover:text-loomera-primary" data-option-id="${option.id}">
        <span class="truncate">${renderLabel(option)}</span>
        <i class="fa-solid fa-arrow-left text-[10px] text-loomera-textMuted"></i>
      </button>
    `).join("");
    container.classList.remove("hidden");
    container.querySelectorAll("[data-option-id]").forEach((button) => {
      button.addEventListener("click", () => onSelect(button.dataset.optionId));
    });
  }

  function hideAllSuggestions() {
    [els.customerSuggestions, els.serviceSuggestions, els.stylistSuggestions].forEach((container) => container?.classList.add("hidden"));
  }

  function selectCustomer(id) {
    const customer = findById(state.customers, id);
    if (!customer) return;
    els.customerHidden.value = customer.id;
    els.customerInput.value = customer.label;
    hideAllSuggestions();
    updateBookingSummary();
  }

  function selectService(id) {
    const service = findById(state.services, id);
    if (!service) return;
    els.serviceHidden.value = service.id;
    els.serviceInput.value = service.name;
    const selectedStylist = getSelectedStylist();
    if (selectedStylist && !service.stylist_ids.includes(String(selectedStylist.id))) {
      els.stylistHidden.value = "";
      els.stylistInput.value = "";
    }
    resetScheduleSelection();
    hideAllSuggestions();
    updateBookingSummary();
    renderAvailabilityCalendar();
  }

  function selectStylist(id) {
    const stylist = findById(state.stylists, id);
    if (!stylist) return;
    els.stylistHidden.value = stylist.id;
    els.stylistInput.value = stylist.name;
    const selectedService = getSelectedService();
    if (selectedService && !stylist.service_ids.includes(String(selectedService.id))) {
      els.serviceHidden.value = "";
      els.serviceInput.value = "";
    }
    resetScheduleSelection();
    hideAllSuggestions();
    updateBookingSummary();
    renderAvailabilityCalendar();
  }

  function bindAutocomplete(input, container, getOptions, renderLabel, onSelect, onClear) {
    if (!input) return;
    input.addEventListener("focus", () => {
      renderSuggestionList(container, getOptions(input.value), renderLabel, onSelect);
    });
    input.addEventListener("input", () => {
      if (!input.value.trim()) onClear();
      renderSuggestionList(container, getOptions(input.value), renderLabel, onSelect);
    });
  }

  bindAutocomplete(els.customerInput, els.customerSuggestions, getCustomerOptions, (customer) => customer.label, selectCustomer, () => {
    els.customerHidden.value = "";
    updateBookingSummary();
  });

  bindAutocomplete(els.serviceInput, els.serviceSuggestions, getServiceOptions, (service) => service.name, selectService, () => {
    els.serviceHidden.value = "";
    resetScheduleSelection();
    updateBookingSummary();
    renderAvailabilityCalendar();
  })

  bindAutocomplete(els.stylistInput, els.stylistSuggestions, getStylistOptions, (stylist) => stylist.name, selectStylist, () => {
    els.stylistHidden.value = "";
    resetScheduleSelection();
    updateBookingSummary();
    renderAvailabilityCalendar();
  });

  document.addEventListener("click", (event) => {
    if (!event.target.closest("[data-autocomplete-root]")) hideAllSuggestions();
  });

  function mergeAvailabilityPayload(target, payload) {
    Object.entries(payload).forEach(([stylistId, days]) => {
      if (!target[stylistId]) target[stylistId] = {};
      Object.entries(days || {}).forEach(([dateStr, items]) => {
        target[stylistId][dateStr] = items || [];
      });
    });
  }

  async function loadAvailabilityForMonth(year, month) {
    const key = `${year}-${month}`;
    if (state.loadedMonths.has(key)) return;
    const response = await fetch(`/orders/api/availability/?salon_id=${encodeURIComponent(state.salonId)}&month=${month}&year=${year}`, { credentials: "same-origin" });
    if (!response.ok) throw new Error(`availability request failed: ${response.status}`);
    const data = await response.json();
    mergeAvailabilityPayload(state.schedules, data.schedules || {});
    mergeAvailabilityPayload(state.bookedTimes, data.booked_times || {});
    mergeAvailabilityPayload(state.timeOffs, data.time_offs || {});
    state.loadedMonths.add(key);
  }

  async function preloadAvailabilityWindow() {
    const today = JalaliDate.today();
    for (let offset = 0; offset < AVAILABILITY_MONTHS_TO_PRELOAD; offset += 1) {
      const target = shiftJalaliMonth(today.jy, today.jm, offset);
      await loadAvailabilityForMonth(target.year, target.month);
    }
  }

  function isBlockedByBookings(stylistId, dateStr, startMinutes, endMinutes) {
    const bookings = state.bookedTimes[stylistId]?.[dateStr] || [];
    return bookings.some((booking) => {
      if (!booking.time) return false;
      const bookingStart = toMinutes(booking.time);
      const bookingEnd = booking.end_time ? toMinutes(booking.end_time) : bookingStart + Number(booking.duration || 0);
      return slotOverlaps(startMinutes, endMinutes, bookingStart, bookingEnd);
    });
  }

  function isBlockedByTimeOff(stylistId, dateStr, startMinutes, endMinutes) {
    const timeOffs = state.timeOffs[stylistId]?.[dateStr] || [];
    return timeOffs.some((item) => {
      const offStart = item.start_time ? toMinutes(item.start_time) : 0;
      const offEnd = item.end_time ? toMinutes(item.end_time) : 24 * 60;
      return slotOverlaps(startMinutes, endMinutes, offStart, offEnd);
    });
  }

  function getScheduleWindows(stylistId, dateStr, serviceId) {
    const windows = state.schedules[stylistId]?.[dateStr] || [];
    return windows.filter((window) => !window.service_id || String(window.service_id) === String(serviceId));
  }

  function isToday(dateStr) {
    const now = new Date();
    return dateStr === `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  }

  function currentTimeMinutes() {
    const now = new Date();
    return now.getHours() * 60 + now.getMinutes();
  }

  function getAvailabilityForDate(dateStr) {
    const service = getSelectedService();
    const stylist = getSelectedStylist();
    if (!service || !stylist || !dateStr) return [];

    const stylistId = String(stylist.id);
    const duration = Number(service.duration || 0);
    const windows = getScheduleWindows(stylistId, dateStr, service.id);
    if (!windows.length) return [];

    const slotMap = new Map();
    windows.forEach((window) => {
      const start = toMinutes(window.start_time);
      const end = toMinutes(window.end_time);
      for (let minute = start; minute + duration <= end; minute += SLOT_STEP) {
        const slotEnd = minute + duration;
        if (isToday(dateStr) && minute <= currentTimeMinutes()) continue;
        if (isBlockedByBookings(stylistId, dateStr, minute, slotEnd)) continue;
        if (isBlockedByTimeOff(stylistId, dateStr, minute, slotEnd)) continue;
        const time = minutesToTime(minute);
        if (!slotMap.has(time)) {
          slotMap.set(time, {
            date: dateStr,
            time,
            end_time: minutesToTime(slotEnd),
          });
        }
      }
    });
    return Array.from(slotMap.values()).sort((a, b) => a.time.localeCompare(b.time));
  }

  function renderTimeSlots(slots) {
    if (!els.timeSlots) return;
    if (!slots.length) {
      const message = state.selectedDate
        ? 'برای این روز، زمان آزادی پیدا نشد.'
        : 'بعد از انتخاب روز، ساعت‌های آزاد همین‌جا نمایش داده می‌شوند.';
      els.timeSlots.innerHTML = `<div class="col-span-full rounded-[22px] border border-dashed border-loomera-borderSoft bg-loomera-bgSubtle/70 px-4 py-6 text-center text-sm text-loomera-textMuted">${message}</div>`;
      refreshWorkspaceLayout();
      return;
    }
    els.timeSlots.innerHTML = slots.map((slot) => {
      const active = state.selectedTime === slot.time;
      return `
        <button type="button" class="manual-booking-slot rounded-[22px] border px-3 py-3 text-center transition ${active ? 'border-loomera-primary bg-loomera-primary text-white shadow-[0_16px_32px_rgba(115,92,190,0.22)]' : 'border-loomera-borderSoft bg-white text-loomera-textPrimary hover:border-loomera-primary/30 hover:bg-loomera-primarySoft/55 hover:text-loomera-primary'}" data-time="${slot.time}">
          <div class="text-sm font-black">${slot.time}</div>
          <div class="mt-1 text-[11px] ${active ? 'text-white/80' : 'text-loomera-textMuted'}">تا ${slot.end_time}</div>
        </button>
      `;
    }).join("");
    els.timeSlots.querySelectorAll(".manual-booking-slot").forEach((button) => {
      button.addEventListener("click", () => {
        state.selectedTime = button.dataset.time;
        els.timeHidden.value = state.selectedTime;
        updateBookingSummary();
        renderTimeSlots(slots);
      });
    });

    refreshWorkspaceLayout();
  }

  async function renderAvailabilityCalendar() {
    const service = getSelectedService();
    const stylist = getSelectedStylist();

    if (!service || !stylist) {
      els.monthTitle.textContent = 'تقویم دسترسی آرایشگر';
      els.calendarHint.textContent = 'ابتدا خدمت و آرایشگر را انتخاب کنید';
      els.calendar.innerHTML = '<div class="col-span-full rounded-[22px] border border-dashed border-loomera-borderSoft bg-loomera-bgSubtle/70 px-4 py-6 text-center text-sm text-loomera-textMuted">بعد از انتخاب خدمت و آرایشگر، روزهای آزاد اینجا نمایش داده می‌شوند.</div>';
      return;
    }

    try {
      await preloadAvailabilityWindow();
    } catch (error) {
      console.error("[manual-booking] availability preload failed");
      els.calendar.innerHTML = '<div class="col-span-full rounded-[22px] border border-loomera-danger/20 bg-loomera-dangerSoft px-4 py-6 text-center text-sm text-loomera-danger">خطا در بارگذاری زمان‌های آزاد آرایشگر.</div>';
      return;
    }

    const today = JalaliDate.today();
    els.monthTitle.textContent = `تقویم ${today.getMonthName()} ${toPersianDigits(today.jy)}`;
    els.calendarHint.textContent = `${service.name} • ${stylist.name}`;

    const days = [];
    for (let offset = 0; offset < 45; offset += 1) {
      days.push(today.addDays(offset));
    }

    els.calendar.innerHTML = days.map((jalaliDay) => {
      const gregorian = jalaliDay.toGregorian();
      const dateStr = `${gregorian.getFullYear()}-${String(gregorian.getMonth() + 1).padStart(2, "0")}-${String(gregorian.getDate()).padStart(2, "0")}`;
      const slots = getAvailabilityForDate(dateStr);
      const available = slots.length > 0;
      const selected = state.selectedDate === dateStr;
      const classes = selected
        ? 'border-loomera-primary bg-loomera-primary text-white shadow-[0_16px_32px_rgba(115,92,190,0.22)]'
        : available
          ? 'border-loomera-success/20 bg-loomera-successSoft text-loomera-success hover:border-loomera-success/40 hover:bg-white'
          : 'border-loomera-borderSoft bg-white text-loomera-textMuted cursor-not-allowed opacity-70';
      const disabled = available ? '' : 'disabled';
      return `
        <button type="button" class="manual-booking-day rounded-[22px] border px-2 py-3 text-center transition ${classes}" data-date="${dateStr}" ${disabled}>
          <div class="text-[11px] font-bold">${jalaliDay.getShortDayName()}</div>
          <div class="mt-1 text-xl font-black">${toPersianDigits(jalaliDay.jd)}</div>
          <div class="mt-1 text-[10px] ${selected ? 'text-white/80' : available ? 'text-loomera-success' : 'text-loomera-textMuted'}">${available ? `${toPersianDigits(slots.length)} زمان` : 'غیرفعال'}</div>
        </button>
      `;
    }).join("");

    els.calendar.querySelectorAll('.manual-booking-day:not([disabled])').forEach((button) => {
      button.addEventListener('click', () => {
        state.selectedDate = button.dataset.date;
        els.dateHidden.value = state.selectedDate;
        els.dateInput.value = formatGregorianToJalaliNumeric(state.selectedDate);
        els.selectedDateLabel.textContent = formatGregorianToJalali(state.selectedDate, { withWeekday: true });
        updateBookingSummary();
        state.currentSlots = getAvailabilityForDate(state.selectedDate);
        renderAvailabilityCalendar();
        renderTimeSlots(state.currentSlots);
      });
    });

    if (state.selectedDate) {
      state.currentSlots = getAvailabilityForDate(state.selectedDate);
      if (!state.currentSlots.length) {
        state.selectedDate = '';
        state.selectedTime = '';
        els.dateHidden.value = '';
        els.timeHidden.value = '';
        els.dateInput.value = '';
        els.selectedDateLabel.textContent = '';
        updateBookingSummary();
        renderTimeSlots([]);
      } else {
        if (!state.currentSlots.some((slot) => slot.time === state.selectedTime)) {
          state.selectedTime = '';
          els.timeHidden.value = '';
          updateBookingSummary();
        }
        renderTimeSlots(state.currentSlots);
      }
    } else {
      renderTimeSlots([]);
    }
  }

  function initJalaliDatePicker() {
    if (typeof jalaliDatepicker === 'undefined' || !els.dateInput) return;
    try {
      jalaliDatepicker.startWatch({ selector: '#manualBookingDatePicker', autoHide: true });
    } catch (error) {
      console.warn("[manual-booking] jalaliDatepicker initialization failed");
    }

    els.dateInput.addEventListener('change', async () => {
      const gregorianDate = jalaliInputToGregorian(els.dateInput.value);
      if (!gregorianDate) return;
      const gDate = parseIsoDate(gregorianDate);
      const [jy, jm] = JalaliDate.gregorianToJalali(gDate.getFullYear(), gDate.getMonth() + 1, gDate.getDate());
      try {
        await loadAvailabilityForMonth(jy, jm);
      } catch (error) {
        console.error("[manual-booking] datepicker month load failed");
      }
      state.selectedDate = gregorianDate;
      els.dateHidden.value = gregorianDate;
      els.selectedDateLabel.textContent = formatGregorianToJalali(gregorianDate, { withWeekday: true });
      updateBookingSummary();
      state.currentSlots = getAvailabilityForDate(gregorianDate);
      if (!state.currentSlots.length) {
        els.timeHidden.value = '';
        state.selectedTime = '';
        updateBookingSummary();
      }
      renderAvailabilityCalendar();
      renderTimeSlots(state.currentSlots);
    });
  }

  syncInputLabelsFromHidden();
  initJalaliDatePicker();
  renderAvailabilityCalendar();

  if (state.selectedDate) {
    state.currentSlots = getAvailabilityForDate(state.selectedDate);
    renderTimeSlots(state.currentSlots);
    els.selectedDateLabel.textContent = formatGregorianToJalali(state.selectedDate, { withWeekday: true });
  }

  updateBookingSummary();
  refreshWorkspaceLayout();
  window.setTimeout(refreshWorkspaceLayout, 80);
  window.setTimeout(refreshWorkspaceLayout, 280);
}
