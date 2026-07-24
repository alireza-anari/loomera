(function () {
  'use strict';

  const SLOT_STEP = 15;
  const MONTHS_TO_PRELOAD = 3;

  const state = {
    salonId: null,
    selections: [],
    currentIndex: 0,
    schedules: {},
    bookedTimes: {},
    timeOffs: {},
    loadedMonths: new Set(),
    candidateStylistsCache: {},
    bestAvailableByService: {},
    picked: {},
    currentDate: null,
    currentTime: null,
    currentSlots: [],
    availabilityCache: {},
    splitDayByIndex: {},
  };

  async function init() {
    try {
      loadDataFromPage();
      await preloadAvailabilityWindow();
      setupEventListeners();
      await renderCurrentStep();
    } catch (error) {
      console.error("[select-datetime] initialization failed");
      alert('زمان‌های قابل رزرو بارگذاری نشد. لطفاً دوباره تلاش کنید.');
    }
  }

  function loadDataFromPage() {
    const source = document.getElementById('hiddenData');
    if (!source) throw new Error('hidden data not found');

    state.salonId = source.dataset.salonId;
    state.selections = JSON.parse(source.dataset.selections || '[]').map((selection) => ({
      ...selection,
      serviceId: String(selection.serviceId),
      serviceDuration: Number(selection.serviceDuration || 30),
      serviceBuffer: Number(selection.serviceBuffer || 0),
      requestedStylistId: String(selection.requestedStylistId || selection.stylistId || 'any'),
      requestedStylistName: selection.requestedStylistName || selection.stylistName || 'فرقی ندارد',
      stylistId: String(selection.stylistId || selection.requestedStylistId || 'any'),
      stylistName: selection.stylistName || selection.requestedStylistName || 'فرقی ندارد',
    }));

    if (!state.selections.length) throw new Error('no selections available');
  }

  function setupEventListeners() {
    document.getElementById('continueBtn')?.addEventListener('click', handleContinue);
    document.getElementById('desktopContinueBtn')?.addEventListener('click', handleContinue);
  }

  async function preloadAvailabilityWindow() {
    const today = JalaliDate.today();
    for (let offset = 0; offset < MONTHS_TO_PRELOAD; offset += 1) {
      const target = shiftJalaliMonth(today.jy, today.jm, offset);
      await loadAvailabilityForMonth(target.year, target.month);
    }
  }

  function shiftJalaliMonth(year, month, delta) {
    let newYear = year;
    let newMonth = month + delta;
    while (newMonth > 12) {
      newMonth -= 12;
      newYear += 1;
    }
    while (newMonth < 1) {
      newMonth += 12;
      newYear -= 1;
    }
    return { year: newYear, month: newMonth };
  }

  async function loadAvailabilityForMonth(year, month) {
    const key = `${year}-${month}`;
    if (state.loadedMonths.has(key)) return;

    const response = await fetch(
      `/orders/api/availability/?salon_id=${encodeURIComponent(state.salonId)}&month=${month}&year=${year}`,
      { credentials: 'same-origin' }
    );

    if (!response.ok) throw new Error(`availability request failed: ${response.status}`);

    const data = await response.json();
    mergeAvailabilityPayload(state.schedules, data.schedules || {});
    mergeAvailabilityPayload(state.bookedTimes, data.booked_times || {});
    mergeAvailabilityPayload(state.timeOffs, data.time_offs || {});
    state.loadedMonths.add(key);
  }

  function mergeAvailabilityPayload(target, payload) {
    Object.entries(payload).forEach(([stylistId, days]) => {
      if (!target[stylistId]) target[stylistId] = {};
      Object.entries(days || {}).forEach(([dateStr, items]) => {
        target[stylistId][dateStr] = items || [];
      });
    });
  }

  function getSelectionKey(selection) {
    return `${selection.requestedStylistId || selection.stylistId}_${selection.serviceId}`;
  }

  function getPickedForIndex(index) {
    const selection = state.selections[index];
    if (!selection) return null;
    return state.picked[getSelectionKey(selection)] || null;
  }

  function getCurrentSelection() {
    return state.selections[state.currentIndex] || null;
  }

  function getPreviousPicked() {
    if (state.currentIndex <= 0) return null;
    return getPickedForIndex(state.currentIndex - 1);
  }

  function isSplitDayEnabled(index = state.currentIndex) {
    return Boolean(state.splitDayByIndex[index]);
  }

  function getSuggestedSameDay(index = state.currentIndex) {
    if (index <= 0) return null;
    const previousPicked = getPickedForIndex(index - 1);
    return previousPicked ? previousPicked.date : null;
  }

  function getDefaultDateForCurrentStep() {
    const selection = getCurrentSelection();
    const existing = getPickedForIndex(state.currentIndex);
    if (existing) return existing.date;

    const suggested = getSuggestedSameDay();
    if (suggested && !isSplitDayEnabled()) return suggested;

    if (selection?.requestedStylistId === 'any') {
      const best = state.bestAvailableByService[String(selection.serviceId)];
      if (best?.next_date) return best.next_date;
    }

    return formatDate(new Date());
  }

  function getEarliestMinutesForDate(dateStr) {
    if (isSplitDayEnabled()) return null;
    const previousPicked = getPreviousPicked();
    if (!previousPicked || previousPicked.date !== dateStr) return null;
    return toMinutes(previousPicked.end_time || previousPicked.time);
  }

  function getCurrentDisplayStylist(selection) {
    if (!selection) return 'متخصص';
    if (selection.requestedStylistId === 'any') return 'فرقی ندارد';
    return selection.stylistName || selection.requestedStylistName || 'متخصص';
  }

  async function getCandidateStylists(selection) {
    if (!selection) return [];
    if (selection.requestedStylistId !== 'any') {
      return [{
        id: String(selection.stylistId),
        name: selection.stylistName || selection.requestedStylistName || 'متخصص',
        profile_image: selection.stylistProfileImage || null,
      }];
    }

    if (state.candidateStylistsCache[selection.serviceId]) {
      return state.candidateStylistsCache[selection.serviceId];
    }

    const response = await fetch(
      `/orders/api/stylists-for-service/?salon_id=${encodeURIComponent(state.salonId)}&service_id=${encodeURIComponent(selection.serviceId)}`,
      { credentials: 'same-origin' }
    );

    if (!response.ok) {
      state.candidateStylistsCache[selection.serviceId] = [];
      return [];
    }

    const data = await response.json();

    if (data.best_available) {
      state.bestAvailableByService[String(selection.serviceId)] = {
        ...data.best_available,
        id: String(data.best_available.id),
      };
    }

    const stylists = (data.stylists || []).map((stylist) => ({
      ...stylist,
      id: String(stylist.id),
    }));

    state.candidateStylistsCache[selection.serviceId] = stylists;
    return stylists;
  }

  function toMinutes(timeStr) {
    const [hour, minute] = String(timeStr || '00:00').split(':').map(Number);
    return (hour * 60) + (minute || 0);
  }

  function minutesToTime(minutes) {
    const normalized = Math.max(0, minutes);
    const hour = Math.floor(normalized / 60);
    const minute = normalized % 60;
    return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
  }

  function ceilToStep(minutes, step = SLOT_STEP) {
    return Math.ceil(minutes / step) * step;
  }

  function isToday(dateStr) {
    const now = new Date();
    return dateStr === formatDate(now);
  }

  function currentTimeMinutes() {
    const now = new Date();
    return (now.getHours() * 60) + now.getMinutes();
  }

  function slotOverlaps(startA, endA, startB, endB) {
    return startA < endB && startB < endA;
  }

  function isBlockedByBookings(stylistId, dateStr, startMinutes, endMinutes) {
    const bookings = state.bookedTimes[stylistId]?.[dateStr] || [];
    return bookings.some((booking) => {
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
    return windows.filter((item) => !item.service_id || String(item.service_id) === String(serviceId));
  }

  function compareIsoDates(a, b) {
    return String(a).localeCompare(String(b));
  }

  async function getAvailabilityForDate(selection, dateStr) {
    const earliestMinutes = getEarliestMinutesForDate(dateStr);
    const cacheKey = [
      selection.serviceId,
      selection.stylistId,
      selection.requestedStylistId,
      dateStr,
      earliestMinutes === null ? 'start' : earliestMinutes,
      isSplitDayEnabled() ? 'split' : 'same',
    ].join('|');

    if (state.availabilityCache[cacheKey]) return state.availabilityCache[cacheKey];

    const candidates = await getCandidateStylists(selection);
    const duration = Number(selection.serviceDuration || 30);
    const buffer = Math.max(0, Number(selection.serviceBuffer || 0));
    const occupiedDuration = duration + buffer;
    const results = [];
    const slotMap = new Map();

    candidates.forEach((stylist) => {
      const windows = getScheduleWindows(stylist.id, dateStr, selection.serviceId);
      windows.forEach((windowItem) => {
        const windowStart = toMinutes(windowItem.start_time);
        const windowEnd = toMinutes(windowItem.end_time);
        const earliestAllowed = earliestMinutes !== null ? Math.max(windowStart, earliestMinutes) : windowStart;
        const firstSlot = ceilToStep(earliestAllowed);
        const lastSlot = windowEnd - occupiedDuration;

        for (let minute = firstSlot; minute <= lastSlot; minute += SLOT_STEP) {
          if (isToday(dateStr) && minute < currentTimeMinutes()) continue;
          const serviceEnd = minute + duration;
          const occupiedEnd = minute + occupiedDuration;
          if (isBlockedByBookings(stylist.id, dateStr, minute, occupiedEnd)) continue;
          if (isBlockedByTimeOff(stylist.id, dateStr, minute, occupiedEnd)) continue;

          const time = minutesToTime(minute);
          const entry = {
            date: dateStr,
            time,
            end_time: minutesToTime(serviceEnd),
            occupied_until: minutesToTime(occupiedEnd),
            stylistId: stylist.id,
            stylistName: stylist.name,
            stylistProfileImage: stylist.profile_image || null,
          };

          if (selection.requestedStylistId === 'any') {
            if (!slotMap.has(time)) slotMap.set(time, entry);
          } else {
            results.push(entry);
          }
        }
      });
    });

    const output = selection.requestedStylistId === 'any'
      ? Array.from(slotMap.values()).sort((a, b) => a.time.localeCompare(b.time) || a.stylistId.localeCompare(b.stylistId))
      : results.sort((a, b) => a.time.localeCompare(b.time));

    state.availabilityCache[cacheKey] = output;
    return output;
  }

  async function renderCurrentStep() {
    if (state.currentIndex < 0) state.currentIndex = 0;
    if (state.currentIndex >= state.selections.length) state.currentIndex = state.selections.length - 1;

    const selection = getCurrentSelection();
    if (!selection) return;

    const existing = getPickedForIndex(state.currentIndex);
    if (existing) {
      const suggested = getSuggestedSameDay();
      if (suggested && existing.date !== suggested) state.splitDayByIndex[state.currentIndex] = true;
    }

    state.currentDate = existing?.date || getDefaultDateForCurrentStep();
    state.currentTime = existing?.time || null;

    updateProgressBar();
    updateBookingSummaries();
    renderServiceSwitcher();
    renderStepContent(selection, existing);
    await renderHorizontalCalendar();
    if (state.currentDate) await loadTimesForDate(state.currentDate, { keepExistingSelection: Boolean(existing) });
    updateContinueButton();
  }

  function updateProgressBar() {
    const progressBar = document.getElementById('progressBar');
    const progress = ((state.currentIndex + 1) / state.selections.length) * 100;
    if (progressBar) progressBar.style.width = `${progress}%`;

    const serviceName = document.getElementById('serviceName');
    const serviceMeta = document.getElementById('serviceMeta');
    const bookingStepLabel = document.getElementById('bookingStepLabel');
    const selection = getCurrentSelection();
    if (serviceName && selection) serviceName.textContent = selection.serviceName || 'خدمت';
    if (serviceMeta && selection) {
      const parts = [getCurrentDisplayStylist(selection), formatDuration(selection.serviceDuration)].filter(Boolean);
      const price = getSelectionPrice(selection);
      if (price > 0) parts.push(`${formatAmount(price)} تومان`);
      serviceMeta.textContent = parts.join(' • ');
    }
    if (bookingStepLabel) {
      bookingStepLabel.textContent = `خدمت ${toPersianDigits(state.currentIndex + 1)} از ${toPersianDigits(state.selections.length)}`;
    }
  }

  function renderServiceSwitcher() {
    const container = document.getElementById('serviceSwitcher');
    if (!container) return;

    const firstIncomplete = state.selections.findIndex((selection) => !state.picked[getSelectionKey(selection)]);
    const maxReachable = firstIncomplete === -1 ? state.selections.length - 1 : Math.max(firstIncomplete, state.currentIndex);

    container.innerHTML = state.selections.map((selection, index) => {
      const picked = state.picked[getSelectionKey(selection)];
      const isCurrent = index === state.currentIndex;
      const isClickable = index <= maxReachable;
      const statusClass = isCurrent
        ? 'border-loomera-primary bg-loomera-primary text-white shadow-lm-soft'
        : picked
          ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
          : 'border-loomera-borderSoft bg-white text-loomera-textSecondary';
      const subtitle = picked ? `${formatGregorianToJalali(picked.date)} • ${picked.time}` : formatDuration(selection.serviceDuration);
      return `
        <button type="button"
                class="min-w-[148px] rounded-2xl border px-3 py-3 text-right transition hover:border-loomera-primary/40 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-loomera-focusRing/30 ${statusClass} ${isClickable ? '' : 'cursor-not-allowed opacity-50'}"
                data-step-index="${index}"
                ${isClickable ? '' : 'disabled'}
                aria-current="${isCurrent ? 'step' : 'false'}">
          <span class="block truncate text-xs font-black">${selection.serviceName || 'خدمت'}</span>
          <span class="mt-1 block truncate text-[11px] opacity-80">${subtitle || 'در انتظار زمان'}</span>
        </button>
      `;
    }).join('');

    container.querySelectorAll('[data-step-index]:not([disabled])').forEach((button) => {
      button.addEventListener('click', async () => {
        state.currentIndex = Number(button.dataset.stepIndex);
        state.currentDate = getDefaultDateForCurrentStep();
        state.currentTime = getPickedForIndex(state.currentIndex)?.time || null;
        await renderCurrentStep();
      });
    });
  }

  function renderStepContent(selection, existing) {
    const sameDayAnchor = getSuggestedSameDay();
    const splitEnabled = isSplitDayEnabled();
    const sameDayLabel = sameDayAnchor ? formatGregorianToJalali(sameDayAnchor) : '';
    const selectedSummary = existing
      ? `
        <div class="mt-3 flex flex-wrap items-center gap-2 text-xs text-emerald-700">
          <span class="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1"><i class="fa-regular fa-calendar" aria-hidden="true"></i>${formatGregorianToJalali(existing.date)}</span>
          <span class="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1"><i class="fa-regular fa-clock" aria-hidden="true"></i>${existing.time} تا ${existing.end_time}</span>
          <span class="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1"><i class="fa-solid fa-user" aria-hidden="true"></i>${existing.stylistName || getCurrentDisplayStylist(selection)}</span>
        </div>
      `
      : '';

    const dayModeBlock = state.currentIndex > 0 ? `
      <div class="mt-4 rounded-2xl border border-loomera-borderSoft bg-loomera-bgSubtle p-3">
        <p class="text-xs font-black text-loomera-textPrimary">رزرو چندخدمتی</p>
        <p class="mt-1 text-xs leading-6 text-loomera-textSecondary">ابتدا تلاش می‌کنیم این خدمت هم در همان روز قبلی قرار بگیرد. اگر ممکن نبود، می‌توانی برای این خدمت روز دیگری انتخاب کنی.</p>
        <div class="mt-3 flex flex-wrap gap-2">
          <button type="button" data-day-mode="same" class="day-mode-btn inline-flex items-center rounded-full border px-4 py-2 text-xs font-black transition ${!splitEnabled ? 'border-loomera-primary bg-loomera-primary text-white shadow-lm-soft' : 'border-loomera-borderSoft bg-white text-loomera-textSecondary hover:border-loomera-primary/40 hover:bg-loomera-primarySoft hover:text-loomera-primary'}">همان روز • ${sameDayLabel || 'پیشنهادی'}</button>
          <button type="button" data-day-mode="split" class="day-mode-btn inline-flex items-center rounded-full border px-4 py-2 text-xs font-black transition ${splitEnabled ? 'border-loomera-primary bg-loomera-primary text-white shadow-lm-soft' : 'border-loomera-borderSoft bg-white text-loomera-textSecondary hover:border-loomera-primary/40 hover:bg-loomera-primarySoft hover:text-loomera-primary'}">روز دیگری برای این خدمت</button>
        </div>
      </div>
    ` : `
      <p class="mt-3 text-xs leading-6 text-loomera-textSecondary">تاریخ و ساعت مناسب را برای این خدمت انتخاب کن.</p>
    `;

    const content = document.getElementById('content');
    if (!content) return;

    content.innerHTML = `
      <section class="rounded-[28px] border border-loomera-borderSoft bg-loomera-surface p-4 shadow-lm-card lg:p-5" aria-labelledby="currentBookingStepTitle">
        <div class="flex items-start gap-4">
          <div class="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-loomera-primarySoft text-loomera-primary">
            <i class="fa-regular fa-clock text-xl" aria-hidden="true"></i>
          </div>
          <div class="min-w-0 flex-1">
            <div class="flex items-center justify-between gap-3">
              <div class="min-w-0">
                <p class="mb-1 text-xs font-black text-loomera-textMuted">خدمت ${toPersianDigits(state.currentIndex + 1)} از ${toPersianDigits(state.selections.length)}</p>
                <h2 id="currentBookingStepTitle" class="truncate text-lg font-black text-loomera-textPrimary">${selection.serviceName || 'خدمت'}</h2>
              </div>
              <span class="rounded-full bg-loomera-bgSubtle px-3 py-1 text-xs font-black text-loomera-textSecondary">${formatDuration(selection.serviceDuration) || 'مدت نامشخص'}</span>
            </div>
            <p class="mt-2 text-sm text-loomera-textSecondary">${getCurrentDisplayStylist(selection)}</p>
            ${dayModeBlock}
            ${selectedSummary}
          </div>
        </div>
      </section>

      <section class="rounded-[28px] border border-loomera-borderSoft bg-loomera-surface p-4 shadow-lm-card lg:p-5" aria-labelledby="datePickerTitle">
        <div class="mb-4 flex items-center justify-between gap-3">
          <div>
            <h3 id="monthTitle" class="text-lg font-black text-loomera-textPrimary"></h3>
            <p id="calendarHint" class="mt-1 text-xs text-loomera-textMuted"></p>
          </div>
          <div class="relative">
            <button id="openCalendar" type="button" onclick="window.openSalonCalendarPicker && window.openSalonCalendarPicker()" aria-label="باز کردن تقویم شمسی" class="flex h-11 w-11 items-center justify-center rounded-full border border-loomera-borderSoft bg-white transition hover:border-loomera-primary/40 hover:bg-loomera-primarySoft focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-loomera-focusRing/30">
              <i class="fa-regular fa-calendar pointer-events-none text-loomera-textSecondary" aria-hidden="true"></i>
            </button>
            <input id="bookingDatePicker" type="text" data-jdp data-jdp-only-date="true" tabindex="-1" aria-hidden="true" class="pointer-events-none absolute inset-0 opacity-0" autocomplete="off" />
          </div>
        </div>
        <div id="calendar" class="-mx-4 flex gap-3 overflow-x-auto px-4 pb-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden" role="list" aria-label="تاریخ‌های قابل انتخاب"></div>
      </section>

      <section id="timesSection" class="hidden rounded-[28px] border border-loomera-borderSoft bg-loomera-surface p-4 shadow-lm-card lg:p-5" aria-labelledby="timeSlotsTitle">
        <div class="mb-4 flex items-center justify-between gap-3">
          <div>
            <h3 id="timeSlotsTitle" class="flex items-center gap-2 text-base font-black text-loomera-textPrimary"><i class="fa-regular fa-clock text-loomera-primary" aria-hidden="true"></i>ساعت‌های قابل رزرو</h3>
            <p class="mt-1 text-xs text-loomera-textMuted">فقط زمان‌های واقعی و آزاد نمایش داده می‌شوند.</p>
          </div>
          <span id="selectedDateLabel" class="rounded-full bg-loomera-bgSubtle px-3 py-1 text-xs font-black text-loomera-textSecondary"></span>
        </div>
        <div id="times"></div>
      </section>

      <section id="emptyState" class="rounded-[28px] border border-dashed border-loomera-border bg-white px-5 py-10 text-center text-loomera-textMuted shadow-lm-soft" role="status">
        <div class="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-loomera-bgSubtle text-loomera-textMuted"><i class="fa-regular fa-calendar-check text-2xl" aria-hidden="true"></i></div>
        <p class="text-base font-black text-loomera-textPrimary">یک روز را برای دیدن زمان‌های در دسترس انتخاب کن</p>
        <p class="mt-2 text-sm leading-7 text-loomera-textSecondary">اگر همان روز ممکن نبود، می‌توانی برای خدمات بعدی روز دیگری انتخاب کنی.</p>
      </section>
    `;

    content.querySelectorAll('.day-mode-btn').forEach((button) => {
      button.addEventListener('click', async () => {
        const mode = button.dataset.dayMode;
        const previousDate = getSuggestedSameDay();
        if (mode === 'same') {
          delete state.splitDayByIndex[state.currentIndex];
          state.currentDate = previousDate || null;
        } else {
          state.splitDayByIndex[state.currentIndex] = true;
          if (state.currentDate && previousDate && compareIsoDates(state.currentDate, previousDate) < 0) {
            state.currentDate = previousDate;
          }
        }
        state.currentTime = null;
        clearAvailabilityCache();
        await renderCurrentStep();
      });
    });

    initBookingDatePicker();
  }

  async function renderHorizontalCalendar() {
    const selection = getCurrentSelection();
    if (!selection) return;

    const calendar = document.getElementById('calendar');
    const monthTitle = document.getElementById('monthTitle');
    const calendarHint = document.getElementById('calendarHint');
    if (!calendar || !monthTitle || !calendarHint) return;

    const today = JalaliDate.today();
    const sameDayAnchor = getSuggestedSameDay();
    const splitEnabled = isSplitDayEnabled();
    const dates = [];
    for (let offset = 0; offset < 90; offset += 1) dates.push(today.addDays(offset));

    monthTitle.textContent = `${today.getMonthName()} ${toPersianDigits(today.jy)}`;
    if (!sameDayAnchor || state.currentIndex === 0) {
      calendarHint.textContent = 'روزهای آزاد و غیرفعال این خدمت در ۹۰ روز آینده';
    } else if (splitEnabled) {
      calendarHint.textContent = `پیش‌فرض همچنان ${formatGregorianToJalali(sameDayAnchor)} است، اما می‌توانید روز دیگری هم انتخاب کنید.`;
    } else {
      calendarHint.textContent = `پیش‌فرض این خدمت همان روز ${formatGregorianToJalali(sameDayAnchor)} است.`;
    }

    const cards = await Promise.all(dates.map(async (jalaliDay) => {
      const gregorian = jalaliDay.toGregorian();
      const dateStr = `${gregorian.getFullYear()}-${String(gregorian.getMonth() + 1).padStart(2, '0')}-${String(gregorian.getDate()).padStart(2, '0')}`;
      const isHoliday = gregorian.getDay() === 5;
      const isCurrent = state.currentDate === dateStr || (!state.currentDate && !sameDayAnchor && dateStr === formatDate(new Date()));
      const beforeAnchor = sameDayAnchor && compareIsoDates(dateStr, sameDayAnchor) < 0;
      const hardSameDayLock = sameDayAnchor && !splitEnabled && sameDayAnchor !== dateStr;
      const disabledBySequence = beforeAnchor || hardSameDayLock;
      const slots = disabledBySequence ? [] : await getAvailabilityForDate(selection, dateStr);
      const hasAvailability = slots.length > 0;
      const disabled = disabledBySequence || (!hasAvailability && !splitEnabled && sameDayAnchor === dateStr && state.currentIndex > 0);
      let footerLabel = 'بدون وقت';
      if (hasAvailability) footerLabel = `${toPersianDigits(slots.length)} زمان`;
      else if (hardSameDayLock) footerLabel = 'همان روز';
      else if (beforeAnchor) footerLabel = 'قبل از خدمت قبلی';
      else if (sameDayAnchor === dateStr && !splitEnabled) footerLabel = 'بدون جای خالی';
      else if (sameDayAnchor === dateStr && splitEnabled) footerLabel = hasAvailability ? footerLabel : 'پیشنهادی';

      const buttonClass = [
        'flex h-full w-full min-w-[88px] flex-col items-center rounded-3xl border px-3 py-3 text-center transition focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-loomera-focusRing/30',
        isCurrent ? 'border-loomera-primary bg-loomera-primary text-white shadow-lm-card' : 'border-loomera-borderSoft bg-white text-loomera-textPrimary hover:border-loomera-primary/40 hover:bg-loomera-primarySoft/50',
        disabled ? 'cursor-not-allowed opacity-45 hover:border-loomera-borderSoft hover:bg-white' : '',
        isHoliday && !isCurrent ? 'bg-loomera-bgSubtle' : '',
      ].filter(Boolean).join(' ');

      const footerClass = hasAvailability
        ? (isCurrent ? 'text-white/90' : 'text-emerald-600')
        : (isCurrent ? 'text-white/80' : 'text-loomera-textMuted');

      return `
        <div class="flex-shrink-0" style="min-width: 88px;" role="listitem">
          <button type="button"
                  class="${buttonClass}"
                  data-date-card
                  data-date="${dateStr}"
                  ${disabled ? 'disabled aria-disabled="true"' : ''}
                  aria-pressed="${isCurrent ? 'true' : 'false'}"
                  aria-label="${jalaliDay.getShortDayName()} ${toPersianDigits(jalaliDay.jd)}، ${footerLabel}">
            <span class="block text-[11px] font-black opacity-80">${jalaliDay.getShortDayName()}</span>
            <span class="mt-1 block text-2xl font-black leading-none">${toPersianDigits(jalaliDay.jd)}</span>
            <span class="mt-1 block text-[10px] opacity-75">${toPersianDigits(jalaliDay.jm)}/${toPersianDigits(jalaliDay.jy)}</span>
            <span class="mt-2 block text-[10px] font-black ${footerClass}">${footerLabel}</span>
          </button>
        </div>
      `;
    }));

    calendar.innerHTML = cards.join('');
    calendar.querySelectorAll('[data-date-card]:not([disabled])').forEach((button) => {
      button.addEventListener('click', async () => {
        state.currentDate = button.dataset.date;
        state.currentTime = null;
        await renderHorizontalCalendar();
        await loadTimesForDate(state.currentDate);
      });
    });
  }

  async function loadTimesForDate(dateStr, options = {}) {
    const timesSection = document.getElementById('timesSection');
    const timesEl = document.getElementById('times');
    const selectedDateLabel = document.getElementById('selectedDateLabel');
    if (!timesSection || !timesEl) return;

    timesSection.classList.remove('hidden');
    document.getElementById('emptyState')?.classList.add('hidden');
    if (selectedDateLabel) selectedDateLabel.textContent = formatGregorianToJalali(dateStr, { withWeekday: true });

    timesEl.innerHTML = `<div class="py-10 text-center text-loomera-textMuted"><i class="fa-solid fa-spinner fa-spin mb-3 text-2xl text-loomera-primary" aria-hidden="true"></i><p class="text-sm font-black">در حال بررسی زمان‌های آزاد واقعی...</p></div>`;

    const selection = getCurrentSelection();
    const slots = await getAvailabilityForDate(selection, dateStr);
    state.currentSlots = slots;

    if (!slots.length) {
      const canOfferSplit = state.currentIndex > 0 && !isSplitDayEnabled();
      const selectionForFallback = getCurrentSelection();
      const bestFallback = state.bestAvailableByService[String(selectionForFallback?.serviceId || '')];

      if (
        bestFallback?.next_date &&
        bestFallback.next_date !== dateStr &&
        selectionForFallback?.requestedStylistId === 'any'
      ) {
        state.currentDate = bestFallback.next_date;
        state.currentTime = null;
        await renderHorizontalCalendar();
        await loadTimesForDate(state.currentDate);
        return;
      }
      timesEl.innerHTML = `
        <div class="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-6 text-center text-amber-900" role="status">
          <div class="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-white text-amber-500"><i class="fa-regular fa-calendar-xmark text-xl" aria-hidden="true"></i></div>
          <p class="text-sm font-black">برای این روز زمانی موجود نیست</p>
          <p class="mt-2 text-xs leading-6 text-amber-800">روز دیگری را انتخاب کن یا اگر این خدمت بعد از خدمت قبلی جا نمی‌شود، آن را در روز دیگری قرار بده.</p>
          ${canOfferSplit ? '<button type="button" id="enableSplitDayBtn" class="mt-4 inline-flex items-center justify-center rounded-full border border-amber-200 bg-white px-4 py-2 text-xs font-black text-amber-800 shadow-sm transition hover:bg-amber-100">برای این خدمت روز دیگری انتخاب می‌کنم</button>' : ''}
        </div>
      `;
      document.getElementById('enableSplitDayBtn')?.addEventListener('click', async () => {
        state.splitDayByIndex[state.currentIndex] = true;
        state.currentTime = null;
        clearAvailabilityCache();
        await renderCurrentStep();
      });
      updateContinueButton();
      return;
    }

    renderTimeSlots(slots, selection, options.keepExistingSelection);
    updateContinueButton();
  }

  function renderTimeSlots(slots, selection, keepExistingSelection = false) {
    const picked = keepExistingSelection ? getPickedForIndex(state.currentIndex) : null;
    const selectedTime = picked?.time || state.currentTime;
    const container = document.getElementById('times');
    if (!container) return;
    const groups = groupSlotsByPeriod(slots);

    container.innerHTML = groups.map((group) => `
      <section aria-labelledby="period-${group.key}">
        <div class="mb-3 mt-5 flex items-center gap-2 first:mt-0">
          <span class="flex h-8 w-8 items-center justify-center rounded-full bg-loomera-primarySoft text-loomera-primary"><i class="fa-solid ${group.icon}" aria-hidden="true"></i></span>
          <h4 id="period-${group.key}" class="text-sm font-black text-loomera-textPrimary">${group.label}</h4>
          <span class="text-xs text-loomera-textMuted">${toPersianDigits(group.slots.length)} زمان</span>
        </div>
        <div class="grid grid-cols-2 gap-3 sm:grid-cols-3" role="list">
          ${group.slots.map((slot) => {
            const isSelected = slot.time === selectedTime;
            const showStylist = selection.requestedStylistId === 'any';
            const buttonClass = isSelected
              ? 'border-loomera-primary bg-loomera-primary text-white shadow-lm-card'
              : 'border-loomera-borderSoft bg-white text-loomera-textPrimary hover:border-loomera-primary/40 hover:bg-loomera-primarySoft/50';
            return `
              <button type="button"
                      class="rounded-2xl border px-3 py-3 text-center transition focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-loomera-focusRing/30 ${buttonClass}"
                      data-time-slot
                      data-time="${slot.time}"
                      aria-pressed="${isSelected ? 'true' : 'false'}"
                      aria-label="ساعت ${slot.time} تا ${slot.end_time}${showStylist ? `، ${slot.stylistName}` : ''}">
                <span class="block text-base font-black">${slot.time}</span>
                <span class="mt-1 block text-[11px] opacity-75">تا ${slot.end_time}</span>
                ${showStylist ? `<span class="mt-2 block truncate text-[11px] opacity-75">${slot.stylistName}</span>` : ''}
              </button>
            `;
          }).join('')}
        </div>
      </section>
    `).join('');

    container.querySelectorAll('[data-time-slot]').forEach((button) => {
      button.addEventListener('click', () => {
        state.currentTime = button.dataset.time;
        renderTimeSlots(slots, selection, false);
        updateContinueButton();
      });
    });
  }

  function updateContinueButton() {
    const mobileButton = document.getElementById('continueBtn');
    const desktopButton = document.getElementById('desktopContinueBtn');
    const mobileSummary = document.getElementById('mobileStickySummary');
    const ready = Boolean(state.currentDate && state.currentTime);
    const isLast = state.currentIndex === state.selections.length - 1;
    const text = ready ? (isLast ? 'ادامه و پیش‌نمایش رزرو' : 'ثبت این خدمت و ادامه') : 'ابتدا تاریخ و زمان را انتخاب کنید';

    [mobileButton, desktopButton].forEach((button) => {
      if (!button) return;
      button.disabled = !ready;
      button.textContent = text;
    });

    if (mobileSummary) {
      if (!ready) {
        mobileSummary.textContent = state.currentDate ? 'حالا ساعت نوبت را انتخاب کن' : 'برای ادامه، تاریخ و ساعت را انتخاب کن';
      } else {
        mobileSummary.textContent = `${formatGregorianToJalali(state.currentDate)} • ${state.currentTime}`;
      }
    }
    updateBookingSummaries();
  }

  function updateBookingSummaries() {
    const totals = calculateBookingTotals();
    const servicesSummary = document.getElementById('bookingServicesSummary');
    const desktopList = document.getElementById('desktopSelectedServicesList');
    const desktopPicked = document.getElementById('desktopPickedSummary');
    const totalParts = [];
    if (totals.count > 0) totalParts.push(`${toPersianDigits(totals.count)} خدمت`);
    if (totals.duration > 0) totalParts.push(formatDuration(totals.duration));
    if (totals.price > 0) totalParts.push(`${formatAmount(totals.price)} تومان`);

    const rows = state.selections.map((selection, index) => {
      const summary = buildSelectionSummaryLine(selection, index);
      const isCurrent = index === state.currentIndex;
      const pickedClass = summary.picked ? 'text-emerald-700 bg-emerald-50 border-emerald-100' : 'text-loomera-textMuted bg-white border-loomera-borderSoft';
      const rowClass = isCurrent
        ? 'border-loomera-primary/30 bg-loomera-primarySoft/40'
        : 'border-loomera-borderSoft bg-white';
      return `
        <li class="flex items-center justify-between gap-3 rounded-2xl border px-3 py-3 ${rowClass}" role="listitem">
          <div class="min-w-0 flex-1">
            <p class="truncate text-sm font-black text-loomera-textPrimary">${summary.parts[0] || 'خدمت'}</p>
            <p class="mt-1 truncate text-xs text-loomera-textSecondary">${summary.specialist}</p>
          </div>
          <span class="rounded-full border px-3 py-1 text-[11px] font-black ${pickedClass}">${summary.pickedLabel}</span>
        </li>
      `;
    }).join('');

    if (servicesSummary) {
      servicesSummary.innerHTML = `
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p class="text-xs font-black text-loomera-textMuted">خلاصه خدمات و متخصص‌ها</p>
            <h2 class="mt-1 text-base font-black text-loomera-textPrimary">${totalParts.join(' • ') || 'خدمات انتخاب‌شده'}</h2>
          </div>
          <span class="inline-flex rounded-full border border-loomera-primary/20 bg-loomera-primarySoft px-3 py-1 text-xs font-black text-loomera-primary">مرحله زمان</span>
        </div>
        <ul class="mt-4 space-y-2" role="list">${rows}</ul>
      `;
    }

    if (desktopList) {
      desktopList.innerHTML = `
        <div class="rounded-2xl border border-loomera-borderSoft bg-loomera-bgSubtle p-4">
          <p class="text-xs font-black text-loomera-textMuted">خدمات و متخصص‌ها</p>
          <ul class="mt-3 space-y-2" role="list">${rows}</ul>
        </div>
      `;
    }

    if (desktopPicked) {
      const pickedRows = state.selections.map((selection, index) => {
        const summary = buildSelectionSummaryLine(selection, index);
        if (!summary.picked) return `<p class="rounded-xl border border-dashed border-loomera-borderSoft bg-white px-3 py-2 text-xs text-loomera-textMuted">${selection.serviceName || 'خدمت'}: زمان انتخاب نشده</p>`;
        return `<p class="rounded-xl border border-emerald-100 bg-emerald-50 px-3 py-2 text-xs font-black text-emerald-700">${selection.serviceName || 'خدمت'}: ${summary.pickedLabel}</p>`;
      }).join('');
      desktopPicked.innerHTML = pickedRows || 'هنوز زمانی انتخاب نشده است.';
    }
  }
  function buildSelectionSummaryLine(selection, index) {
    const savedPicked = getPickedForIndex(index);
    let picked = savedPicked;
    if (!picked && index === state.currentIndex && state.currentDate && state.currentTime) {
      const slot = state.currentSlots.find((item) => item.time === state.currentTime);
      picked = {
        date: state.currentDate,
        time: state.currentTime,
        end_time: slot?.end_time || '',
        stylistName: slot?.stylistName || selection.stylistName || selection.requestedStylistName || '',
      };
    }
    const parts = [];
    if (selection.serviceName) parts.push(selection.serviceName);
    if (formatDuration(selection.serviceDuration)) parts.push(formatDuration(selection.serviceDuration));
    const price = getSelectionPrice(selection);
    if (price > 0) parts.push(`${formatAmount(price)} تومان`);
    const specialist = selection.requestedStylistId === 'any'
      ? 'فرقی ندارد'
      : (selection.requestedStylistName || selection.stylistName || 'متخصص');
    const pickedLabel = picked
      ? `${formatGregorianToJalali(picked.date)}، ${picked.time}${picked.end_time ? ` تا ${picked.end_time}` : ''}`
      : 'زمان انتخاب نشده';
    return { parts, specialist, pickedLabel, picked };
  }

  function calculateBookingTotals() {
    return state.selections.reduce((totals, selection) => {
      totals.count += 1;
      totals.duration += Number(selection.serviceDuration || 0);
      totals.price += getSelectionPrice(selection);
      return totals;
    }, { count: 0, duration: 0, price: 0 });
  }

  function getSelectionPrice(selection) {
    const candidates = [selection?.stylistPrice, selection?.servicePrice, selection?.price, selection?.minPrice, selection?.serviceMinPrice];
    for (const value of candidates) {
      const parsed = Number(value || 0);
      if (Number.isFinite(parsed) && parsed > 0) return parsed;
    }
    return 0;
  }

  function formatAmount(value) {
    const amount = Number(value || 0);
    if (!Number.isFinite(amount) || amount <= 0) return '';
    return toPersianDigits(new Intl.NumberFormat('fa-IR').format(Math.round(amount)));
  }

  function formatDuration(minutes) {
    const value = Number(minutes || 0);
    if (!Number.isFinite(value) || value <= 0) return '';
    return `${toPersianDigits(value)} دقیقه`;
  }

  function getPeriodMeta(time) {
    const minutes = toMinutes(time);
    if (minutes < 12 * 60) return { key: 'morning', label: 'صبح', icon: 'fa-sun' };
    if (minutes < 16 * 60) return { key: 'noon', label: 'ظهر', icon: 'fa-cloud-sun' };
    if (minutes < 20 * 60) return { key: 'evening', label: 'عصر', icon: 'fa-cloud-moon' };
    return { key: 'night', label: 'شب', icon: 'fa-moon' };
  }

  function groupSlotsByPeriod(slots) {
    const groups = [];
    const index = new Map();
    slots.forEach((slot) => {
      const meta = getPeriodMeta(slot.time);
      if (!index.has(meta.key)) {
        const group = { ...meta, slots: [] };
        groups.push(group);
        index.set(meta.key, group);
      }
      index.get(meta.key).slots.push(slot);
    });
    return groups;
  }

  function clearAvailabilityCache() {
    state.availabilityCache = {};
  }

  async function handleContinue() {
    const selection = getCurrentSelection();
    if (!selection || !state.currentDate || !state.currentTime) {
      alert('لطفاً تاریخ و زمان را انتخاب کنید.');
      return;
    }

    const previousPicked = getPreviousPicked();
    if (previousPicked && compareIsoDates(state.currentDate, previousPicked.date) < 0) {
      alert('این خدمت نمی‌تواند قبل از خدمت قبلی زمان‌بندی شود.');
      return;
    }

    const slot = state.currentSlots.find((item) => item.time === state.currentTime);
    if (!slot) {
      alert('زمان انتخابی دیگر در دسترس نیست. لطفاً دوباره انتخاب کنید.');
      return;
    }

    if (selection.requestedStylistId === 'any') {
      selection.stylistId = slot.stylistId;
      selection.stylistName = slot.stylistName;
      selection.resolvedStylistId = slot.stylistId;
      selection.resolvedStylistName = slot.stylistName;
      selection.stylistProfileImage = slot.stylistProfileImage || null;
    }

    state.picked[getSelectionKey(selection)] = {
      date: slot.date,
      time: slot.time,
      end_time: slot.end_time,
      stylistId: slot.stylistId,
      stylistName: slot.stylistName,
    };
    if (previousPicked) state.splitDayByIndex[state.currentIndex] = slot.date !== previousPicked.date;

    clearAvailabilityCache();

    if (state.currentIndex < state.selections.length - 1) {
      state.currentIndex += 1;
      state.currentDate = getDefaultDateForCurrentStep();
      state.currentTime = null;
      window.scrollTo({ top: 0, behavior: 'smooth' });
      await renderCurrentStep();
      return;
    }

    submitBooking();
  }

  function submitBooking() {
    const bookingData = {
      salon_id: state.salonId,
      stylist_selections: state.selections,
      datetime_selections: state.picked,
    };

    const bookingInput = document.getElementById('bookingDataInput');
    const bookingForm = document.getElementById('dateTimeSelectionForm');
    if (!bookingInput || !bookingForm) {
      console.error('booking form elements not found');
      alert('ثبت اطلاعات رزرو کامل نشد. لطفاً دوباره تلاش کنید.');
      return;
    }

    bookingInput.value = JSON.stringify(bookingData);
    bookingForm.submit();
  }

  function formatDate(dateObject) {
    return `${dateObject.getFullYear()}-${String(dateObject.getMonth() + 1).padStart(2, '0')}-${String(dateObject.getDate()).padStart(2, '0')}`;
  }

  function parseIsoDate(dateStr) {
    if (!dateStr) return new Date();
    const [year, month, day] = String(dateStr).split('-').map(Number);
    return new Date(year, (month || 1) - 1, day || 1);
  }

  function toPersianDigits(value) {
    const map = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹'];
    return String(value).replace(/\d/g, (d) => map[Number(d)]);
  }

  function normalizeDigits(value) {
    const fa = '۰۱۲۳۴۵۶۷۸۹';
    const ar = '٠١٢٣٤٥٦٧٨٩';
    return String(value || '')
      .replace(/[۰-۹]/g, (d) => String(fa.indexOf(d)))
      .replace(/[٠-٩]/g, (d) => String(ar.indexOf(d)));
  }

  function formatGregorianToJalaliNumeric(dateStr, separator = '/') {
    if (!dateStr) return '';
    const date = parseIsoDate(dateStr);
    const [jy, jm, jd] = JalaliDate.gregorianToJalali(date.getFullYear(), date.getMonth() + 1, date.getDate());
    return [toPersianDigits(jy), toPersianDigits(String(jm).padStart(2, '0')), toPersianDigits(String(jd).padStart(2, '0'))].join(separator);
  }

  function jalaliInputToGregorian(jalaliValue) {
    const normalized = normalizeDigits(jalaliValue).replace(/\//g, '-').trim();
    const match = normalized.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
    if (!match) return null;
    const [gy, gm, gd] = JalaliDate.jalaliToGregorian(Number(match[1]), Number(match[2]), Number(match[3]));
    return `${gy}-${String(gm).padStart(2, '0')}-${String(gd).padStart(2, '0')}`;
  }

  function initBookingDatePicker() {
    const pickerInput = document.getElementById('bookingDatePicker');
    if (!pickerInput) return;

    pickerInput.value = state.currentDate ? formatGregorianToJalaliNumeric(state.currentDate) : '';
    if (typeof jalaliDatepicker !== 'undefined') {
      try {
        jalaliDatepicker.startWatch({ selector: '#bookingDatePicker', autoHide: true });
      } catch (error) {
        console.warn("[select-datetime] jalaliDatepicker initialization failed");
      }
    }

    if (pickerInput.dataset.bound === '1') return;
    pickerInput.dataset.bound = '1';
    pickerInput.addEventListener('change', async () => {
      const gregorianDate = jalaliInputToGregorian(pickerInput.value);
      if (!gregorianDate) return;
      const previousPicked = getPreviousPicked();
      if (previousPicked && compareIsoDates(gregorianDate, previousPicked.date) < 0) return;

      state.currentDate = gregorianDate;
      state.currentTime = null;

      const gDate = parseIsoDate(gregorianDate);
      const [jy, jm] = JalaliDate.gregorianToJalali(gDate.getFullYear(), gDate.getMonth() + 1, gDate.getDate());
      try {
        await loadAvailabilityForMonth(jy, jm);
      } catch (error) {
        console.error("[select-datetime] datepicker month load failed");
      }

      await renderHorizontalCalendar();
      await loadTimesForDate(state.currentDate);
    });
  }

  function formatGregorianToJalali(dateStr, options = {}) {
    if (!dateStr) return '';
    const date = parseIsoDate(dateStr);
    const [jy, jm, jd] = JalaliDate.gregorianToJalali(date.getFullYear(), date.getMonth() + 1, date.getDate());
    const months = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند'];
    const weekdays = ['یکشنبه', 'دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنج‌شنبه', 'جمعه', 'شنبه'];
    const base = `${toPersianDigits(jd)} ${months[jm - 1]} ${toPersianDigits(jy)}`;
    return options.withWeekday ? `${weekdays[date.getDay()]} ${base}` : base;
  }

  function openCalendarModal() {
    const pickerInput = document.getElementById('bookingDatePicker');
    if (!pickerInput) return;
    pickerInput.focus();
    pickerInput.click();
  }

  window.openSalonCalendarPicker = openCalendarModal;
  window.openSalonCalendarModal = openCalendarModal;
  window.SelectDateTime = { state, reload: init, openCalendarModal };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
