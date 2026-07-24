(function () {
  "use strict";

  const FORM_SELECTOR = "[data-checkout-guard-form]";
  const FINAL_SUBMIT_SELECTOR = "[data-checkout-final-submit]";
  const PAYMENT_OPTION_SELECTOR = "[data-payment-option]";
  const PAYMENT_INPUT_SELECTOR = 'input[name="payment_method"]';
  const MOBILE_BAR_SELECTOR = "[data-checkout-mobile-bar]";
  const COUPON_INPUT_SELECTOR = "[data-checkout-coupon-input]";

  const ACTION_PROXY_NAME = "form_action";
  const CONFIRM_ACTION = "confirm_checkout";

  const PAYMENT_PRESENTATIONS = {
    online: {
      label: "پرداخت و ثبت رزرو",
      loadingLabel: "در حال انتقال به درگاه",
      icon: "fa-lock",
    },
    wallet: {
      label: "پرداخت از کیف پول",
      loadingLabel: "در حال پرداخت",
      icon: "fa-wallet",
    },
    pay_in_salon: {
      label: "ثبت رزرو",
      loadingLabel: "در حال ثبت رزرو",
      icon: "fa-calendar-check",
    },
  };

  const DEFAULT_PAYMENT_PRESENTATION = {
    label: "ثبت رزرو",
    loadingLabel: "در حال ثبت رزرو",
    icon: "fa-calendar-check",
  };

  const originalLabels = new WeakMap();

  function finalSubmitButtons(form) {
    const formId = form.getAttribute("id");
    const scopedButtons = Array.from(
      form.querySelectorAll(FINAL_SUBMIT_SELECTOR),
    );

    if (!formId) {
      return scopedButtons;
    }

    const externalButtons = Array.from(
      document.querySelectorAll(
        `${FINAL_SUBMIT_SELECTOR}[form="${CSS.escape(formId)}"]`,
      ),
    );

    return Array.from(new Set([...scopedButtons, ...externalButtons]));
  }

  function rememberOriginalLabel(button) {
    if (!originalLabels.has(button)) {
      originalLabels.set(button, button.innerHTML);
    }
  }

  function selectedPaymentMethod(form) {
    const selectedInput = form.querySelector(
      `${PAYMENT_INPUT_SELECTOR}:checked`,
    );

    return selectedInput ? selectedInput.value : "";
  }

  function paymentPresentation(method) {
    return PAYMENT_PRESENTATIONS[method] || DEFAULT_PAYMENT_PRESENTATION;
  }

  function paymentButtonHtml(presentation) {
    return [
      `<i class="fa-solid ${presentation.icon} text-xs" aria-hidden="true"></i>`,
      `<span>${presentation.label}</span>`,
    ].join("");
  }

  function updatePaymentOptionState(form) {
    form.querySelectorAll(PAYMENT_OPTION_SELECTOR).forEach((option) => {
      const input = option.querySelector('input[type="radio"]');
      const selected = Boolean(input && input.checked);

      option.dataset.selected = selected ? "1" : "0";
    });
  }

  function updatePaymentPresentation(form) {
    const method = selectedPaymentMethod(form);
    const presentation = paymentPresentation(method);
    const idleHtml = paymentButtonHtml(presentation);
    const busy = form.dataset.checkoutSubmitting === "1";

    updatePaymentOptionState(form);

    finalSubmitButtons(form).forEach((button) => {
      originalLabels.set(button, idleHtml);
      button.dataset.loadingLabel = presentation.loadingLabel;

      if (!busy) {
        button.innerHTML = idleHtml;
      }
    });
  }

  function setBusy(form, busy) {
    form.dataset.checkoutSubmitting = busy ? "1" : "0";
    form.setAttribute("aria-busy", busy ? "true" : "false");

    finalSubmitButtons(form).forEach((button) => {
      rememberOriginalLabel(button);

      button.disabled = busy;
      button.setAttribute("aria-disabled", busy ? "true" : "false");
      button.classList.toggle("opacity-70", busy);
      button.classList.toggle("cursor-not-allowed", busy);

      if (busy) {
        const label = button.dataset.loadingLabel || "در حال ثبت رزرو";

        button.innerHTML = [
          '<i class="fa-solid fa-spinner fa-spin text-xs" aria-hidden="true"></i>',
          `<span>${label}</span>`,
        ].join("");
      } else {
        button.innerHTML = originalLabels.get(button);
      }
    });
  }

  function removeActionProxy(form) {
    form
      .querySelectorAll('input[data-checkout-action-proxy="1"]')
      .forEach((input) => input.remove());
  }

  function ensureConfirmActionProxy(form) {
    removeActionProxy(form);

    const input = document.createElement("input");
    input.type = "hidden";
    input.name = ACTION_PROXY_NAME;
    input.value = CONFIRM_ACTION;
    input.dataset.checkoutActionProxy = "1";

    form.appendChild(input);
  }

  function submittedAction(event) {
    const submitter = event.submitter;

    if (!submitter) {
      return "";
    }

    return submitter.value || "";
  }

  function mobileCheckoutBar(form) {
    return form.querySelector(MOBILE_BAR_SELECTOR);
  }

  function setMobileBarKeyboardHidden(form, hidden) {
    const bar = mobileCheckoutBar(form);

    if (!bar) {
      return;
    }

    bar.dataset.keyboardHidden = hidden ? "true" : "false";
    bar.setAttribute("aria-hidden", hidden ? "true" : "false");
  }

  function bindPaymentUX(form) {
    if (form.dataset.checkoutPaymentUxBound === "1") {
      return;
    }

    form.dataset.checkoutPaymentUxBound = "1";

    form.addEventListener("change", function (event) {
      if (!event.target.matches(PAYMENT_INPUT_SELECTOR)) {
        return;
      }

      updatePaymentPresentation(form);
    });

    updatePaymentPresentation(form);
  }

  function bindCouponKeyboardUX(form) {
    if (form.dataset.checkoutKeyboardUxBound === "1") {
      return;
    }

    const couponInput = form.querySelector(COUPON_INPUT_SELECTOR);
    const mobileBar = mobileCheckoutBar(form);

    if (!couponInput || !mobileBar) {
      return;
    }

    form.dataset.checkoutKeyboardUxBound = "1";

    couponInput.addEventListener("focus", function () {
      setMobileBarKeyboardHidden(form, true);
    });

    couponInput.addEventListener("blur", function () {
      setMobileBarKeyboardHidden(form, false);
    });
  }

  function bindForm(form) {
    if (!form || form.dataset.checkoutGuardBound === "1") {
      return;
    }

    form.dataset.checkoutGuardBound = "1";

    bindPaymentUX(form);
    bindCouponKeyboardUX(form);
    setBusy(form, false);

    form.addEventListener("submit", function (event) {
      const action = submittedAction(event);

      if (action !== CONFIRM_ACTION) {
        removeActionProxy(form);
        return;
      }

      if (form.dataset.checkoutSubmitting === "1") {
        event.preventDefault();
        event.stopPropagation();
        return;
      }

      ensureConfirmActionProxy(form);
      setBusy(form, true);
    });
  }

  function bindAll() {
    document.querySelectorAll(FORM_SELECTOR).forEach(bindForm);
  }

  document.addEventListener("DOMContentLoaded", bindAll);

  window.addEventListener("pageshow", function () {
    document.querySelectorAll(FORM_SELECTOR).forEach((form) => {
      removeActionProxy(form);
      setMobileBarKeyboardHidden(form, false);
      updatePaymentPresentation(form);
      setBusy(form, false);
    });
  });
})();
