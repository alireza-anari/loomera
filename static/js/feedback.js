(function () {
  "use strict";

  const META = {
    error: { title: "انجام نشد", icon: "fa-circle-exclamation", role: "alert" },
    success: { title: "انجام شد", icon: "fa-circle-check", role: "status" },
    warning: { title: "نیاز به بررسی", icon: "fa-triangle-exclamation", role: "alert" },
    info: { title: "اطلاع", icon: "fa-circle-info", role: "status" },
  };

  const DEFAULTS = {
    error: "انجام این عملیات با مشکل روبه‌رو شد. لطفاً دوباره تلاش کنید.",
    success: "عملیات با موفقیت انجام شد.",
    warning: "این مورد نیاز به بررسی دارد.",
    info: "اطلاعات به‌روزرسانی شد.",
  };

  const latinPattern = /[A-Za-z]/;
  const persianPattern = /[\u0600-\u06FF]/;
  const technicalPattern = /traceback|exception|error\s*[:=]|sql|django\.|python|keyerror|typeerror|valueerror|integrityerror|object\s+at\s+0x|<[^>]+>|https?:\/\//i;

  const replacements = [
    [/\bLoomera\b/gi, "لومرا"],
    [/\bJPEG\b/gi, "جی‌پی‌اِگ"],
    [/\bJPG\b/gi, "جی‌پی‌جی"],
    [/\bPNG\b/gi, "پی‌اِن‌جی"],
    [/\bWEBP\b/gi, "وِب‌پی"],
    [/\bPDF\b/gi, "پی‌دی‌اِف"],
    [/\bMP4\b/gi, "اِم‌پی۴"],
    [/\bOTP\b/gi, "کد تأیید"],
    [/\bSMS\b/gi, "پیامک"],
    [/\bIR\b/gi, "آی‌آر"],
    [/\bLIVE\b/gi, "عملیاتی"],
    [/\bWORKFLOW\b/gi, "فرایند"],
    [/\bSCOPE\b/gi, "محدوده"],
    [/\bCHECKOUT\b/gi, "تسویه"],
    [/\bCOMMAND\b/gi, "فرمان پردازش"],
    [/\bLEDGER\b/gi, "دفتر مالی"],
  ];

  function normalizeMessage(value, fallback, allowLatinData = false) {
    let text = String(value || "").trim().replace(/\s+/g, " ");
    replacements.forEach(([pattern, replacement]) => {
      text = text.replace(pattern, replacement);
    });
    if (
      !text ||
      !persianPattern.test(text) ||
      technicalPattern.test(text) ||
      (!allowLatinData && latinPattern.test(text))
    ) {
      return fallback;
    }
    return text;
  }

  function stack() {
    let node = document.querySelector("[data-lm-feedback-stack]");
    if (node) return node;
    node = document.createElement("div");
    node.dataset.lmFeedbackStack = "true";
    node.className = "fixed top-4 left-1/2 z-[100] w-full max-w-md -translate-x-1/2 space-y-3 px-4";
    node.setAttribute("aria-live", "polite");
    node.setAttribute("aria-atomic", "false");
    document.body.appendChild(node);
    return node;
  }

  function dismiss(node) {
    if (!node || node.dataset.lmDismissing === "true") return;
    node.dataset.lmDismissing = "true";
    node.classList.add("opacity-0", "translate-y-2");
    window.setTimeout(() => node.remove(), 300);
  }

  function bind(node, index) {
    if (!(node instanceof HTMLElement) || node.dataset.lmFeedbackReady === "true") return;
    node.dataset.lmFeedbackReady = "true";
    const close = node.querySelector("[data-flash-close]");
    const duration = Number.parseInt(node.dataset.dismissAfter || "5000", 10);
    close?.addEventListener("click", () => dismiss(node));
    if (Number.isFinite(duration) && duration > 0) {
      window.setTimeout(() => dismiss(node), duration + (index || 0) * 180);
    }
  }

  function create(message, type, duration) {
    const tone = META[type] ? type : "info";
    const meta = META[tone];
    const allowLatinData = tone === "success" || tone === "info";
    const text = normalizeMessage(message, DEFAULTS[tone], allowLatinData);
    const node = document.createElement("div");
    node.dataset.flashMessage = "true";
    node.dataset.dismissAfter = String(duration || 5000);
    node.className = `lm-flash lm-flash--${tone} transition duration-300 ease-out`;
    node.setAttribute("role", meta.role);

    const row = document.createElement("div");
    row.className = "flex items-start justify-between gap-3";

    const content = document.createElement("div");
    content.className = "flex min-w-0 items-start gap-3";

    const icon = document.createElement("span");
    icon.className = "lm-flash__icon mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full";
    icon.setAttribute("aria-hidden", "true");
    icon.innerHTML = `<i class="fa-solid ${meta.icon}"></i>`;

    const copy = document.createElement("div");
    copy.className = "min-w-0";
    const title = document.createElement("p");
    title.className = "text-xs font-black leading-5";
    title.textContent = meta.title;
    const body = document.createElement("p");
    body.className = "mt-0.5 text-sm font-bold leading-6";
    body.textContent = text;
    copy.append(title, body);
    content.append(icon, copy);

    const close = document.createElement("button");
    close.type = "button";
    close.dataset.flashClose = "true";
    close.className = "shrink-0 rounded-full p-1 opacity-70 transition hover:bg-white/70 hover:opacity-100";
    close.setAttribute("aria-label", "بستن پیام");
    close.innerHTML = '<i class="fa-solid fa-xmark" aria-hidden="true"></i>';

    row.append(content, close);
    node.appendChild(row);
    return node;
  }

  function show(message, type = "info", options = {}) {
    const node = create(message, type, options.duration);
    stack().appendChild(node);
    bind(node, 0);
    return node;
  }

  function hydrate() {
    document.querySelectorAll("[data-flash-message]").forEach((node, index) => bind(node, index));
  }

  window.LoomeraFeedback = {
    show,
    error: (message, options) => show(message, "error", options),
    success: (message, options) => show(message, "success", options),
    warning: (message, options) => show(message, "warning", options),
    info: (message, options) => show(message, "info", options),
    safeMessage: (message, type = "error") => {
      const tone = META[type] ? type : "error";
      const allowLatinData = tone === "success" || tone === "info";
      return normalizeMessage(message, DEFAULTS[tone], allowLatinData);
    },
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", hydrate, { once: true });
  else hydrate();
})();
