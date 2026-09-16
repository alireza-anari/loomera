const PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹";

function toPersianDigits(value) {
  return String(value ?? "").replace(
    /\d/g,
    (digit) => PERSIAN_DIGITS[Number(digit)],
  );
}

function normalizedTime(value) {
  return String(value || "").slice(0, 5);
}

export default function initStylistAddBookingAvailability() {
  const root = document.querySelector(
    '[data-dashboard-page="stylist-add-booking"]',
  );

  if (!root || root.dataset.availabilityReady === "true") {
    return;
  }

  const optionsUrl = root.dataset.stylistBookingAvailabilityUrl;

  const serviceSelect = document.getElementById("id_service");

  const dateValue = root.querySelector("[data-stylist-booking-date-value]");

  const timeValue = root.querySelector("[data-stylist-booking-time-value]");

  const dateSelect = root.querySelector("[data-stylist-booking-date]");

  const timeSelect = root.querySelector("[data-stylist-booking-time]");

  const status = root.querySelector(
    "[data-stylist-booking-availability-status]",
  );

  if (
    !optionsUrl ||
    !serviceSelect ||
    !dateValue ||
    !timeValue ||
    !dateSelect ||
    !timeSelect
  ) {
    return;
  }

  root.dataset.availabilityReady = "true";

  let availability = [];
  let requestController = null;

  const initialDate = String(dateValue.value || "").trim();
  const initialTime = normalizedTime(timeValue.value);

  function statusMessage(message, tone = "neutral") {
    if (!status) {
      return;
    }

    const toneClasses = {
      neutral:
        "border-loomera-borderSoft bg-loomera-bgSubtle/55 text-loomera-textMuted",

      loading:
        "border-loomera-primary/15 bg-loomera-primarySoft/45 text-loomera-primaryText",

      empty: "border-amber-200 bg-amber-50 text-amber-800",

      error: "border-rose-200 bg-rose-50 text-rose-700",
    };

    status.innerHTML = `
      <div
        class="
          rounded-[18px]
          border
          px-3.5
          py-2.5
          text-[11px]
          font-bold
          leading-6
          ${toneClasses[tone] || toneClasses.neutral}
        "
      >
        ${message}
      </div>
    `;
  }

  function resetTime(message = "ابتدا تاریخ آزاد را انتخاب کن") {
    timeSelect.innerHTML = `
      <option value="">
        ${message}
      </option>
    `;

    timeSelect.disabled = true;
    timeValue.value = "";
  }

  function resetDate(message = "ابتدا خدمت را انتخاب کن") {
    dateSelect.innerHTML = `
      <option value="">
        ${message}
      </option>
    `;

    dateSelect.disabled = true;
    dateValue.value = "";

    resetTime();
  }

  function renderTimes(date, preferredTime = "") {
    const selectedDay = availability.find(
      (day) => String(day.value) === String(date),
    );

    const times = Array.isArray(selectedDay?.times) ? selectedDay.times : [];

    timeSelect.innerHTML = `
      <option value="">
        ساعت آزاد را انتخاب کن
      </option>
    `;

    times.forEach((time) => {
      const value = normalizedTime(time);

      const option = document.createElement("option");

      option.value = value;
      option.textContent = toPersianDigits(value);

      if (value === normalizedTime(preferredTime)) {
        option.selected = true;
      }

      timeSelect.appendChild(option);
    });

    timeSelect.disabled = times.length === 0;

    const preferredExists = times.some(
      (time) => normalizedTime(time) === normalizedTime(preferredTime),
    );

    timeValue.value = preferredExists ? normalizedTime(preferredTime) : "";
  }

  function renderAvailability(days, preferredDate = "", preferredTime = "") {
    availability = Array.isArray(days)
      ? days.filter((day) => Array.isArray(day.times) && day.times.length)
      : [];

    if (!availability.length) {
      resetDate("تاریخ آزادی وجود ندارد");

      statusMessage("برای این خدمت در بازه فعلی زمان آزادی پیدا نشد.", "empty");

      return;
    }

    dateSelect.innerHTML = `
      <option value="">
        تاریخ آزاد را انتخاب کن
      </option>
    `;

    availability.forEach((day) => {
      const option = document.createElement("option");

      option.value = day.value;
      option.textContent = day.label || day.value;

      if (String(day.value) === String(preferredDate)) {
        option.selected = true;
      }

      dateSelect.appendChild(option);
    });

    dateSelect.disabled = false;

    const preferredExists = availability.some(
      (day) => String(day.value) === String(preferredDate),
    );

    if (preferredExists) {
      dateValue.value = preferredDate;

      renderTimes(preferredDate, preferredTime);
    } else {
      dateValue.value = "";

      resetTime();
    }

    statusMessage(
      "فقط تاریخ‌ها و ساعت‌هایی نمایش داده می‌شوند که در برنامه کاری شما آزاد هستند.",
    );
  }

  async function loadAvailability({ preserveInitial = false } = {}) {
    const serviceId = String(serviceSelect.value || "").trim();

    if (!serviceId) {
      availability = [];

      resetDate();

      statusMessage(
        "بعد از انتخاب خدمت، تاریخ‌ها و ساعت‌های آزاد همان خدمت نمایش داده می‌شوند.",
      );

      return;
    }

    if (requestController) {
      requestController.abort();
    }

    requestController = new AbortController();

    resetDate("در حال دریافت تاریخ‌های آزاد…");

    statusMessage("در حال بررسی برنامه و نوبت‌های ثبت‌شده…", "loading");

    try {
      const url = new URL(optionsUrl, window.location.origin);

      url.searchParams.set("service_id", serviceId);

      const response = await fetch(url.toString(), {
        credentials: "same-origin",

        headers: {
          Accept: "application/json",
        },

        signal: requestController.signal,
      });

      const payload = await response.json();

      if (!response.ok) {
        throw new Error(payload?.error || "دریافت زمان‌های آزاد انجام نشد.");
      }

      renderAvailability(
        payload.availability,

        preserveInitial ? initialDate : "",

        preserveInitial ? initialTime : "",
      );
    } catch (error) {
      if (error.name === "AbortError") {
        return;
      }

      availability = [];

      resetDate("دریافت زمان‌های آزاد ناموفق بود");

      statusMessage(
        window.LoomeraFeedback?.safeMessage?.(error.message, "error") || "دریافت زمان‌های آزاد انجام نشد.",
        "error",
      );
    }
  }

  serviceSelect.addEventListener("change", () => {
    loadAvailability();
  });

  dateSelect.addEventListener("change", () => {
    dateValue.value = dateSelect.value || "";

    renderTimes(dateSelect.value, "");
  });

  timeSelect.addEventListener("change", () => {
    timeValue.value = normalizedTime(timeSelect.value);
  });

  loadAvailability({
    preserveInitial: true,
  });
}

if (document.readyState === "loading") {
  document.addEventListener(
    "DOMContentLoaded",
    initStylistAddBookingAvailability,
    {
      once: true,
    },
  );
} else {
  initStylistAddBookingAvailability();
}

document.addEventListener("htmx:afterSwap", initStylistAddBookingAvailability);

document.addEventListener("turbo:load", initStylistAddBookingAvailability);
