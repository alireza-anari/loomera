const AVAILABLE_DATES_INITIAL_LIMIT = 8;

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
  const [jy, jm, jd] = JalaliDate.gregorianToJalali(
    date.getFullYear(),
    date.getMonth() + 1,
    date.getDate(),
  );
  const months = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"];
  const weekdays = ["یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه", "شنبه"];
  const base = `${toPersianDigits(jd)} ${months[jm - 1]}`;
  if (options.withYear) return `${base} ${toPersianDigits(jy)}`;
  return options.withWeekday ? `${weekdays[date.getDay()]} ${base}` : base;
}

function toMinutes(timeStr) {
  const [hour, minute] = String(timeStr || "").split(":").map(Number);
  return (hour || 0) * 60 + (minute || 0);
}

function minutesToTime(minutes) {
  const normalized = Math.max(0, Number(minutes) || 0);
  const hour = Math.floor(normalized / 60);
  const minute = normalized % 60;
  return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
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
      console.error(`[manual-booking] invalid json payload: ${id}`, error);
      return [];
    }
  }

  const state = {
    customers: readJsonScript("manualBookingCustomersData"),
    services: readJsonScript("manualBookingServicesData"),
    stylists: readJsonScript("manualBookingStylistsData"),
    availability: [],
    availabilityRequestId: 0,
    showAllDates: false,
    selectedDate: document.getElementById("id_appointment_date")?.value || "",
    selectedTime: document.getElementById("id_start_time")?.value || "",
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
    moreDates: document.getElementById("manualBookingMoreDates"),
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
    return findById(state.customers, els.customerHidden?.value);
  }

  function getSelectedService() {
    return findById(state.services, els.serviceHidden?.value);
  }

  function getSelectedStylist() {
    return findById(state.stylists, els.stylistHidden?.value);
  }

  function setText(element, value, fallback = "—") {
    if (element) element.textContent = value || fallback;
  }

  function updateBookingSummary() {
    const customer = getSelectedCustomer();
    const service = getSelectedService();
    const stylist = getSelectedStylist();
    const dateLabel = state.selectedDate
      ? formatGregorianToJalali(state.selectedDate, { withWeekday: true })
      : "";

    setText(els.summaryCustomer, customer?.label || els.customerInput?.value?.trim(), "انتخاب نشده");
    setText(els.summaryService, service?.name || els.serviceInput?.value?.trim(), "انتخاب نشده");
    setText(els.summaryStylist, stylist?.name || els.stylistInput?.value?.trim(), "انتخاب نشده");
    setText(els.summaryDate, dateLabel, "—");
    setText(els.summaryTime, state.selectedTime, "—");

    if (els.summaryStatus) {
      const isReady = Boolean(
        els.customerHidden?.value &&
        els.serviceHidden?.value &&
        els.stylistHidden?.value &&
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
    if (customer && !els.customerInput?.value) els.customerInput.value = customer.label;
    const service = getSelectedService();
    if (service && !els.serviceInput?.value) els.serviceInput.value = service.name;
    const stylist = getSelectedStylist();
    if (stylist && !els.stylistInput?.value) els.stylistInput.value = stylist.name;
    updateBookingSummary();
  }

  function clearSelectedSlot() {
    state.selectedDate = "";
    state.selectedTime = "";
    if (els.dateHidden) els.dateHidden.value = "";
    if (els.timeHidden) els.timeHidden.value = "";
    if (els.dateInput) els.dateInput.value = "";
    if (els.selectedDateLabel) els.selectedDateLabel.textContent = "";
    updateBookingSummary();
  }

  function resetAvailability() {
    state.availability = [];
    state.showAllDates = false;
    clearSelectedSlot();
    renderAvailableDates();
    renderTimeSlots([]);
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
    [els.customerSuggestions, els.serviceSuggestions, els.stylistSuggestions]
      .forEach((container) => container?.classList.add("hidden"));
  }

  function selectCustomer(id) {
    const customer = findById(state.customers, id);
    if (!customer) return;
    els.customerHidden.value = customer.id;
    els.customerInput.value = customer.label;
    hideAllSuggestions();
    updateBookingSummary();
  }

  async function selectService(id) {
    const service = findById(state.services, id);
    if (!service) return;
    els.serviceHidden.value = service.id;
    els.serviceInput.value = service.name;
    const selectedStylist = getSelectedStylist();
    if (selectedStylist && !service.stylist_ids.includes(String(selectedStylist.id))) {
      els.stylistHidden.value = "";
      els.stylistInput.value = "";
    }
    resetAvailability();
    hideAllSuggestions();
    updateBookingSummary();
    await loadAvailability();
  }

  async function selectStylist(id) {
    const stylist = findById(state.stylists, id);
    if (!stylist) return;
    els.stylistHidden.value = stylist.id;
    els.stylistInput.value = stylist.name;
    const selectedService = getSelectedService();
    if (selectedService && !stylist.service_ids.includes(String(selectedService.id))) {
      els.serviceHidden.value = "";
      els.serviceInput.value = "";
    }
    resetAvailability();
    hideAllSuggestions();
    updateBookingSummary();
    await loadAvailability();
  }

  function bindAutocomplete(input, container, getOptions, renderLabel, onSelect, onClear) {
    if (!input) return;
    input.addEventListener("focus", () => {
      renderSuggestionList(container, getOptions(input.value), renderLabel, onSelect);
    });
    input.addEventListener("input", () => {
      onClear();
      renderSuggestionList(container, getOptions(input.value), renderLabel, onSelect);
    });
  }

  bindAutocomplete(
    els.customerInput,
    els.customerSuggestions,
    getCustomerOptions,
    (customer) => customer.label,
    selectCustomer,
    () => {
      els.customerHidden.value = "";
      updateBookingSummary();
    },
  );

  bindAutocomplete(
    els.serviceInput,
    els.serviceSuggestions,
    getServiceOptions,
    (service) => service.name,
    selectService,
    () => {
      els.serviceHidden.value = "";
      resetAvailability();
      updateBookingSummary();
    },
  );

  bindAutocomplete(
    els.stylistInput,
    els.stylistSuggestions,
    getStylistOptions,
    (stylist) => stylist.name,
    selectStylist,
    () => {
      els.stylistHidden.value = "";
      resetAvailability();
      updateBookingSummary();
    },
  );

  document.addEventListener("click", (event) => {
    if (!event.target.closest("[data-autocomplete-root]")) hideAllSuggestions();
  });

  function findAvailabilityDay(dateValue) {
    return state.availability.find((day) => day.value === dateValue);
  }

  function getSlotsForDay(day) {
    const service = getSelectedService();
    const duration = Number(service?.duration || 0);
    return (day?.times || []).map((time) => ({
      date: day.value,
      time,
      end_time: minutesToTime(toMinutes(time) + duration),
    }));
  }

  function renderTimeSlots(slots) {
    if (!els.timeSlots) return;
    if (!slots.length) {
      const message = state.selectedDate
        ? "برای این روز، زمان آزادی باقی نمانده است."
        : "بعد از انتخاب یکی از روزهای آزاد، ساعت‌های قابل رزرو همین‌جا نمایش داده می‌شوند.";
      els.timeSlots.innerHTML = `<div class="col-span-full rounded-[22px] border border-dashed border-loomera-borderSoft bg-loomera-bgSubtle/70 px-4 py-5 text-center text-sm text-loomera-textMuted">${message}</div>`;
      refreshWorkspaceLayout();
      return;
    }

    els.timeSlots.innerHTML = slots.map((slot) => {
      const active = state.selectedTime === slot.time;
      return `
        <button type="button" class="manual-booking-slot rounded-[20px] border px-3 py-3 text-center transition ${active ? "border-loomera-primary bg-loomera-primary text-white shadow-[0_16px_32px_rgba(115,92,190,0.22)]" : "border-loomera-borderSoft bg-white text-loomera-textPrimary hover:border-loomera-primary/30 hover:bg-loomera-primarySoft/55 hover:text-loomera-primary"}" data-time="${slot.time}">
          <div class="text-sm font-black">${slot.time}</div>
          <div class="mt-1 text-[11px] ${active ? "text-white/80" : "text-loomera-textMuted"}">تا ${slot.end_time}</div>
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

  function selectAvailableDate(dateValue) {
    const day = findAvailabilityDay(dateValue);
    if (!day) return;
    state.selectedDate = day.value;
    state.selectedTime = "";
    els.dateHidden.value = day.value;
    els.timeHidden.value = "";
    if (els.dateInput) els.dateInput.value = day.value;
    els.selectedDateLabel.textContent = formatGregorianToJalali(day.value, { withWeekday: true });
    updateBookingSummary();
    renderAvailableDates();
    renderTimeSlots(getSlotsForDay(day));
  }

  function renderAvailableDates() {
    if (!els.calendar) return;
    const service = getSelectedService();
    const stylist = getSelectedStylist();

    if (!service || !stylist) {
      els.monthTitle.textContent = "روزهای آزاد متخصص";
      els.calendarHint.textContent = "ابتدا خدمت و متخصص را انتخاب کن";
      els.calendar.innerHTML = '<div class="col-span-full rounded-[22px] border border-dashed border-loomera-borderSoft bg-white/70 px-4 py-5 text-center text-sm text-loomera-textMuted">بعد از انتخاب خدمت و متخصص، فقط روزهای دارای ظرفیت نمایش داده می‌شوند.</div>';
      els.moreDates?.classList.add("hidden");
      refreshWorkspaceLayout();
      return;
    }

    if (!state.availability.length) {
      els.monthTitle.textContent = "روزهای آزاد متخصص";
      els.calendarHint.textContent = `${service.name} • ${stylist.name}`;
      els.calendar.innerHTML = '<div class="col-span-full rounded-[22px] border border-dashed border-loomera-borderSoft bg-white/70 px-4 py-5 text-center text-sm text-loomera-textMuted">در بازه پیش رو، زمان آزادی برای این متخصص پیدا نشد.</div>';
      els.moreDates?.classList.add("hidden");
      refreshWorkspaceLayout();
      return;
    }

    const visibleDays = state.showAllDates
      ? state.availability
      : state.availability.slice(0, AVAILABLE_DATES_INITIAL_LIMIT);
    els.monthTitle.textContent = "روزهای آزاد بعدی";
    els.calendarHint.textContent = `${service.name} • ${stylist.name} • ${toPersianDigits(state.availability.length)} روز دارای ظرفیت`;

    els.calendar.innerHTML = visibleDays.map((day) => {
      const selected = state.selectedDate === day.value;
      const slotCount = Array.isArray(day.times) ? day.times.length : 0;
      return `
        <button type="button" class="manual-booking-day rounded-[20px] border px-3 py-3 text-center transition ${selected ? "border-loomera-primary bg-loomera-primary text-white shadow-[0_16px_32px_rgba(115,92,190,0.22)]" : "border-loomera-success/20 bg-white text-loomera-textPrimary hover:border-loomera-success/40 hover:bg-loomera-successSoft"}" data-date="${day.value}">
          <div class="text-xs font-black">${formatGregorianToJalali(day.value, { withWeekday: true })}</div>
          <div class="mt-1 text-[10px] ${selected ? "text-white/80" : "text-loomera-success"}">${toPersianDigits(slotCount)} زمان آزاد</div>
        </button>
      `;
    }).join("");

    els.calendar.querySelectorAll(".manual-booking-day").forEach((button) => {
      button.addEventListener("click", () => selectAvailableDate(button.dataset.date));
    });

    if (els.moreDates) {
      const hasMore = state.availability.length > AVAILABLE_DATES_INITIAL_LIMIT;
      els.moreDates.classList.toggle("hidden", !hasMore || state.showAllDates);
      els.moreDates.classList.toggle("flex", hasMore && !state.showAllDates);
      if (hasMore && !state.showAllDates) {
        const remaining = state.availability.length - AVAILABLE_DATES_INITIAL_LIMIT;
        els.moreDates.textContent = `نمایش ${toPersianDigits(remaining)} تاریخ آزاد بیشتر`;
      }
    }
    refreshWorkspaceLayout();
  }

  function renderLoadingAvailability() {
    if (!els.calendar) return;
    els.monthTitle.textContent = "در حال بررسی برنامه متخصص";
    els.calendarHint.textContent = "زمان‌های آزاد واقعی در حال محاسبه هستند";
    els.calendar.innerHTML = '<div class="col-span-full flex min-h-20 items-center justify-center gap-2 rounded-[22px] border border-dashed border-loomera-borderSoft bg-white/70 px-4 text-sm font-bold text-loomera-textMuted"><i class="fa-solid fa-spinner fa-spin text-loomera-primary" aria-hidden="true"></i><span>در حال دریافت زمان‌های آزاد…</span></div>';
    els.moreDates?.classList.add("hidden");
  }

  async function loadAvailability() {
    const service = getSelectedService();
    const stylist = getSelectedStylist();
    if (!service || !stylist) {
      renderAvailableDates();
      return;
    }

    const endpoint = source.dataset.availabilityUrl;
    if (!endpoint) {
      console.error("[manual-booking] availability URL is missing");
      return;
    }

    const requestId = ++state.availabilityRequestId;
    renderLoadingAvailability();
    renderTimeSlots([]);

    const query = new URLSearchParams({
      service_id: String(service.id),
      stylist_id: String(stylist.id),
    });

    try {
      const response = await fetch(`${endpoint}?${query.toString()}`, {
        credentials: "same-origin",
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      const data = await response.json().catch(() => ({}));
      if (requestId !== state.availabilityRequestId) return;
      if (!response.ok) throw new Error(data.error || "زمان‌های آزاد دریافت نشد.");

      state.availability = Array.isArray(data.availability) ? data.availability : [];
      state.showAllDates = false;

      const selectedDay = findAvailabilityDay(state.selectedDate);
      if (!selectedDay) {
        clearSelectedSlot();
      } else {
        const slots = getSlotsForDay(selectedDay);
        if (!slots.some((slot) => slot.time === state.selectedTime)) {
          state.selectedTime = "";
          els.timeHidden.value = "";
        }
        els.selectedDateLabel.textContent = formatGregorianToJalali(selectedDay.value, { withWeekday: true });
        renderTimeSlots(slots);
      }
      renderAvailableDates();
      updateBookingSummary();
    } catch (error) {
      if (requestId !== state.availabilityRequestId) return;
      console.error("[manual-booking] availability request failed", error);
      state.availability = [];
      clearSelectedSlot();
      els.monthTitle.textContent = "زمان‌های آزاد";
      els.calendarHint.textContent = "دریافت برنامه متخصص ناموفق بود";
      const safeAvailabilityError = window.LoomeraFeedback?.safeMessage?.(error.message, "error") || "زمان‌های آزاد دریافت نشد.";
      els.calendar.innerHTML = `<div class="col-span-full rounded-[22px] border border-loomera-danger/20 bg-loomera-dangerSoft px-4 py-5 text-center text-sm text-loomera-danger">${safeAvailabilityError}</div>`;
      renderTimeSlots([]);
      refreshWorkspaceLayout();
    }
  }

  els.moreDates?.addEventListener("click", () => {
    state.showAllDates = true;
    renderAvailableDates();
  });

  syncInputLabelsFromHidden();
  renderAvailableDates();
  renderTimeSlots([]);
  if (getSelectedService() && getSelectedStylist()) {
    loadAvailability();
  }
  updateBookingSummary();
  refreshWorkspaceLayout();
  window.setTimeout(refreshWorkspaceLayout, 80);
  window.setTimeout(refreshWorkspaceLayout, 280);
}
