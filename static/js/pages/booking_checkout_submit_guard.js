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
  const APPLY_COUPON_ACTION = "apply_coupon";
  const CLEAR_COUPON_ACTION = "clear_coupon";
  const ACTION_BUTTON_SELECTOR = 'button[type="submit"][name="form_action"]';

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

  function ensureActionProxy(form, action) {
    removeActionProxy(form);

    const input = document.createElement("input");
    input.type = "hidden";
    input.name = ACTION_PROXY_NAME;
    input.value = action;
    input.dataset.checkoutActionProxy = "1";

    form.appendChild(input);
  }

  function submittedAction(event, form) {
    const submitter = event.submitter;

    if (submitter && submitter.value) {
      return submitter.value;
    }

    const requestedAction = form.dataset.checkoutRequestedAction || "";
    if (requestedAction) {
      return requestedAction;
    }

    const couponInput = form.querySelector(COUPON_INPUT_SELECTOR);
    if (couponInput && document.activeElement === couponInput) {
      return APPLY_COUPON_ACTION;
    }

    return "";
  }

  function actionButtons(form) {
    const buttons = Array.from(form.querySelectorAll(ACTION_BUTTON_SELECTOR));
    const formId = form.getAttribute("id");

    if (!formId) {
      return buttons;
    }

    const externalButtons = Array.from(
      document.querySelectorAll(
        `${ACTION_BUTTON_SELECTOR}[form="${CSS.escape(formId)}"]`,
      ),
    );

    return Array.from(new Set([...buttons, ...externalButtons]));
  }

  function bindActionIntent(form) {
    actionButtons(form).forEach((button) => {
      button.addEventListener("click", function () {
        const action = button.value || "";
        form.dataset.checkoutRequestedAction = action;

        // Put the action in the form *before* the browser starts its native
        // submit algorithm. Some browsers do not include controls appended
        // from the later submit event in the POST payload consistently.
        if (action) {
          ensureActionProxy(form, action);
        }
      });
    });
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

    couponInput.addEventListener("keydown", function (event) {
      if (event.key !== "Enter" || event.isComposing) {
        return;
      }

      event.preventDefault();
      form.dataset.checkoutRequestedAction = APPLY_COUPON_ACTION;
      ensureActionProxy(form, APPLY_COUPON_ACTION);

      const applyButton = form.querySelector(
        '[data-checkout-coupon-action="apply"]',
      );

      if (typeof form.requestSubmit === "function") {
        form.requestSubmit(applyButton || undefined);
      } else {
        form.submit();
      }
    });
  }

  function bindForm(form) {
    if (!form || form.dataset.checkoutGuardBound === "1") {
      return;
    }

    form.dataset.checkoutGuardBound = "1";

    bindPaymentUX(form);
    bindCouponKeyboardUX(form);
    bindActionIntent(form);
    setBusy(form, false);

    form.addEventListener("submit", function (event) {
      const action = submittedAction(event, form);

      if (!action) {
        // Never allow an implicit/ambiguous submit to become a reservation.
        event.preventDefault();
        event.stopPropagation();
        removeActionProxy(form);
        return;
      }

      if (action === APPLY_COUPON_ACTION || action === CLEAR_COUPON_ACTION) {
        ensureActionProxy(form, action);
        form.dataset.checkoutRequestedAction = "";
        return;
      }

      if (action !== CONFIRM_ACTION) {
        event.preventDefault();
        event.stopPropagation();
        removeActionProxy(form);
        form.dataset.checkoutRequestedAction = "";
        return;
      }

      if (form.dataset.checkoutSubmitting === "1") {
        event.preventDefault();
        event.stopPropagation();
        return;
      }

      ensureActionProxy(form, CONFIRM_ACTION);
      form.dataset.checkoutRequestedAction = "";
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
      form.dataset.checkoutRequestedAction = "";
      setMobileBarKeyboardHidden(form, false);
      updatePaymentPresentation(form);
      setBusy(form, false);
    });
  });
})();
