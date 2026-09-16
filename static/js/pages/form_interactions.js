const FORM_SELECTOR = 'form:not([data-lm-form-ux="off"])';
const EDITABLE_SELECTOR = 'input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="reset"]), select, textarea';

let beforeUnloadBound = false;

function fieldSnapshot(form) {
  const fields = Array.from(form.querySelectorAll(EDITABLE_SELECTOR));
  return fields.map((field) => {
    if (!field.name || field.disabled) return '';
    if (field.type === 'file') {
      const names = Array.from(field.files || []).map((file) => `${file.name}:${file.size}`).join(',');
      return `${field.name}:file:${names}`;
    }
    if (field.type === 'checkbox' || field.type === 'radio') {
      return `${field.name}:${field.checked ? '1' : '0'}:${field.value || ''}`;
    }
    return `${field.name}:${field.value ?? ''}`;
  }).join('|');
}

function hasMeaningfulEditableFields(form) {
  return Array.from(form.querySelectorAll(EDITABLE_SELECTOR)).some((field) => {
    if (!field.name || field.disabled) return false;
    if (field.type === 'search' && String(form.method || '').toLowerCase() === 'get') return false;
    return true;
  });
}

function restoreSubmitter(submitter) {
  if (!(submitter instanceof HTMLElement) || submitter.dataset.lmSubmitPending !== 'true') return;
  submitter.dataset.lmSubmitPending = 'false';
  submitter.removeAttribute('aria-busy');
  submitter.removeAttribute('disabled');
  submitter.classList.remove('lm-submit-pending');

  if (submitter instanceof HTMLInputElement && submitter.dataset.lmOriginalValue !== undefined) {
    submitter.value = submitter.dataset.lmOriginalValue;
    delete submitter.dataset.lmOriginalValue;
  } else if (submitter.dataset.lmOriginalHtml !== undefined) {
    submitter.innerHTML = submitter.dataset.lmOriginalHtml;
    delete submitter.dataset.lmOriginalHtml;
  }
}

function markSubmitterPending(submitter) {
  if (!(submitter instanceof HTMLElement) || submitter.dataset.lmSubmitPending === 'true') return;
  if (submitter.matches('[data-lm-no-submit-feedback]')) return;

  submitter.dataset.lmSubmitPending = 'true';
  submitter.setAttribute('aria-busy', 'true');
  submitter.setAttribute('disabled', 'disabled');
  submitter.classList.add('lm-submit-pending');

  const rawLabel = (submitter.textContent || submitter.value || '').trim();
  const inferredLabel = (() => {
    if (/ذخیره|ویرایش/.test(rawLabel)) return 'در حال ذخیره…';
    if (/ثبت/.test(rawLabel)) return 'در حال ثبت…';
    if (/ارسال|کد/.test(rawLabel)) return 'در حال ارسال…';
    if (/ساخت/.test(rawLabel)) return 'در حال ساخت…';
    if (/ورود/.test(rawLabel)) return 'در حال ورود…';
    if (/تأیید|تایید/.test(rawLabel)) return 'در حال تأیید…';
    if (/فعال/.test(rawLabel)) return 'در حال فعال‌سازی…';
    if (/حذف/.test(rawLabel)) return 'در حال حذف…';
    if (/لغو/.test(rawLabel)) return 'در حال لغو…';
    return 'در حال انجام…';
  })();
  const pendingLabel = submitter.dataset.lmSubmittingLabel || inferredLabel;
  if (submitter instanceof HTMLInputElement) {
    submitter.dataset.lmOriginalValue = submitter.value;
    submitter.value = pendingLabel;
  } else {
    submitter.dataset.lmOriginalHtml = submitter.innerHTML;
    submitter.innerHTML = `<i class="fa-solid fa-circle-notch fa-spin" aria-hidden="true"></i><span>${pendingLabel}</span>`;
  }
}

function initForm(form) {
  if (!(form instanceof HTMLFormElement) || form.dataset.lmFormUxReady === 'true') return;
  form.dataset.lmFormUxReady = 'true';

  const method = String(form.method || 'get').toLowerCase();
  const inPartnerDashboard = document.body?.dataset?.shell === 'partner-dashboard';
  const shouldTrackDirty = method !== 'get' && hasMeaningfulEditableFields(form) && !form.matches('[data-direct-edit-form]') && (inPartnerDashboard || form.matches('[data-lm-dirty-guard]'));
  const initial = shouldTrackDirty ? fieldSnapshot(form) : '';

  if (shouldTrackDirty) {
    form.dataset.lmDirty = 'false';
    const refreshDirty = () => {
      form.dataset.lmDirty = fieldSnapshot(form) !== initial ? 'true' : 'false';
    };
    form.addEventListener('input', refreshDirty);
    form.addEventListener('change', refreshDirty);
  }

  form.addEventListener('invalid', handleClientInvalid, true);
  form.addEventListener('input', (event) => {
    const field = event.target;
    if (field instanceof HTMLInputElement || field instanceof HTMLSelectElement || field instanceof HTMLTextAreaElement) {
      if (field.validity.valid) clearClientInvalid(field);
    }
  });

  form.addEventListener('submit', (event) => {
    const submitter = event.submitter;
    queueMicrotask(() => {
      if (event.defaultPrevented) return;
      form.dataset.lmSubmitting = 'true';
      form.dataset.lmDirty = 'false';
      markSubmitterPending(submitter);
    });
  });
}

function localizedConstraintMessage(field) {
  if (!(field instanceof HTMLInputElement || field instanceof HTMLSelectElement || field instanceof HTMLTextAreaElement)) {
    return 'مقدار این فیلد معتبر نیست.';
  }
  const validity = field.validity;
  if (validity.valueMissing) return 'تکمیل این فیلد الزامی است.';
  if (validity.typeMismatch) {
    if (field.type === 'email') return 'ایمیل را با قالب معتبر وارد کنید.';
    if (field.type === 'url') return 'نشانی اینترنتی را با قالب معتبر وارد کنید.';
    return 'مقدار واردشده با قالب این فیلد هماهنگ نیست.';
  }
  if (validity.patternMismatch) return 'مقدار واردشده با الگوی مورد انتظار هماهنگ نیست.';
  if (validity.tooShort) return `حداقل ${field.minLength} کاراکتر وارد کنید.`;
  if (validity.tooLong) return `حداکثر ${field.maxLength} کاراکتر مجاز است.`;
  if (validity.rangeUnderflow) return `مقدار باید حداقل ${field.min} باشد.`;
  if (validity.rangeOverflow) return `مقدار باید حداکثر ${field.max} باشد.`;
  if (validity.stepMismatch) return 'مقدار واردشده با فاصله‌های مجاز این فیلد هماهنگ نیست.';
  if (validity.badInput) return 'مقدار واردشده قابل پردازش نیست. آن را بررسی کنید.';
  return 'مقدار این فیلد معتبر نیست. لطفاً آن را اصلاح کنید.';
}

function fieldShellFor(field) {
  return field.closest('[data-form-field], .lm-field, .form-group, label') || field.parentElement;
}

function ensureInlineError(field, message, source = 'client') {
  if (!(field instanceof HTMLElement)) return null;
  const shell = fieldShellFor(field);
  if (!(shell instanceof HTMLElement)) return null;

  const selector = source === 'client' ? '[data-client-field-error]' : `[data-synthesized-error-for="${CSS.escape(field.getAttribute('name') || '')}"]`;
  let node = shell.querySelector(selector);
  if (!(node instanceof HTMLElement)) {
    node = document.createElement('p');
    node.className = 'lm-field-error mt-1 text-xs font-extrabold leading-6';
    node.dataset.fieldError = 'true';
    if (source === 'client') node.dataset.clientFieldError = 'true';
    else node.dataset.synthesizedErrorFor = field.getAttribute('name') || '';
    shell.appendChild(node);
  }
  node.textContent = message;
  markFieldInvalid(field, node);
  return node;
}

function formActionPath(form) {
  if (!(form instanceof HTMLFormElement)) return '';
  try {
    return new URL(form.getAttribute('action') || window.location.href, window.location.href).pathname;
  } catch (_) {
    return '';
  }
}

function formForErrorItem(item, root = document) {
  const containingForm = item.closest('form');
  if (containingForm instanceof HTMLFormElement) return containingForm;

  const redirectContract = item.closest('[data-lm-redirect-form-errors]');
  const actionPath = redirectContract?.dataset?.actionPath || '';
  if (actionPath) {
    const matchingForm = Array.from(root.querySelectorAll('form')).find((form) => formActionPath(form) === actionPath);
    if (matchingForm instanceof HTMLFormElement) return matchingForm;
  }
  return null;
}

function revealFieldOnError(field) {
  if (!(field instanceof HTMLElement)) return;
  const revealTarget = field.closest('[data-lm-reveal-on-error]');
  if (revealTarget instanceof HTMLElement) {
    revealTarget.hidden = false;
    revealTarget.classList.remove('hidden');
  }
}

function hydrateSummaryFieldErrors(root = document) {
  const selector = '[data-form-error-summary] [data-error-for], [data-lm-redirect-form-errors] [data-error-for]';
  root.querySelectorAll(selector).forEach((item) => {
    if (!(item instanceof HTMLElement)) return;
    const form = formForErrorItem(item, root);
    const name = item.dataset.errorFor || '';
    if (!name || !(form instanceof HTMLFormElement)) return;
    const field = form.querySelector(`[name="${CSS.escape(name)}"]`);
    if (!(field instanceof HTMLElement)) return;

    revealFieldOnError(field);
    const shell = fieldShellFor(field);
    const alreadyInline = shell?.querySelector?.('.errorlist, [data-field-error], .lm-field-error, .lm-auth-field-error, .lm-signup-error');
    if (alreadyInline) {
      markFieldInvalid(field, alreadyInline);
      return;
    }
    ensureInlineError(field, item.dataset.errorMessage || item.textContent || 'مقدار این فیلد معتبر نیست.', 'server');
  });
}

function hydrateRedirectNonFieldErrors(root = document) {
  root.querySelectorAll('[data-lm-redirect-form-errors] [data-form-error-message]').forEach((item) => {
    if (!(item instanceof HTMLElement)) return;
    const form = formForErrorItem(item, root);
    if (!(form instanceof HTMLFormElement)) return;

    let node = form.querySelector('[data-lm-redirect-nonfield-error]');
    if (!(node instanceof HTMLElement)) {
      node = document.createElement('p');
      node.className = 'lm-form-error mb-3 text-xs font-extrabold leading-6';
      node.dataset.lmRedirectNonfieldError = 'true';
      node.dataset.formError = 'true';
      node.setAttribute('role', 'alert');
      form.prepend(node);
    }
    node.textContent = item.dataset.errorMessage || 'اطلاعات فرم معتبر نیست. لطفاً آن را بررسی کنید.';
  });
}

function handleClientInvalid(event) {
  const field = event.target;
  if (!(field instanceof HTMLInputElement || field instanceof HTMLSelectElement || field instanceof HTMLTextAreaElement)) return;
  event.preventDefault();
  ensureInlineError(field, localizedConstraintMessage(field), 'client');

  const form = field.form;
  if (form && form.dataset.lmClientValidationNotice !== 'true') {
    form.dataset.lmClientValidationNotice = 'true';
    window.LoomeraFeedback?.error?.('لطفاً موارد مشخص‌شده زیر فیلدها را اصلاح کنید.');
    window.setTimeout(() => { delete form.dataset.lmClientValidationNotice; }, 500);
  }
}

function clearClientInvalid(field) {
  if (!(field instanceof HTMLElement)) return;
  const shell = fieldShellFor(field);
  const clientError = shell?.querySelector?.('[data-client-field-error]');
  clientError?.remove();
  if (!shell?.querySelector?.('.errorlist, [data-field-error]:not([data-client-field-error]), .lm-field-error:not([data-client-field-error]), .lm-auth-field-error, .lm-signup-error')) {
    field.removeAttribute('aria-invalid');
    field.classList.remove('is-invalid');
    shell?.classList.remove('lm-field--invalid');
  }
}

function markFieldInvalid(field, errorNode = null) {
  if (!(field instanceof HTMLElement)) return;
  field.setAttribute('aria-invalid', 'true');
  field.classList.add('is-invalid');

  const fieldShell = field.closest('label, [data-form-field], .lm-field, .form-group');
  fieldShell?.classList.add('lm-field--invalid');

  const compoundControl = field.closest('.lm-login-control, .lm-signup-control, .lm-auth-password-control');
  compoundControl?.classList.add('is-invalid');

  if (!(errorNode instanceof HTMLElement)) return;
  errorNode.setAttribute('role', errorNode.getAttribute('role') || 'alert');
  if (!errorNode.id) {
    const base = field.id || field.name || 'field';
    errorNode.id = `${base}-error-${Math.random().toString(36).slice(2, 7)}`;
  }
  const describedBy = new Set((field.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean));
  describedBy.add(errorNode.id);
  field.setAttribute('aria-describedby', Array.from(describedBy).join(' '));
}

function hydrateInvalidFields(root = document) {
  root.querySelectorAll('[aria-invalid="true"]:not([type="hidden"])').forEach((field) => markFieldInvalid(field));

  const errorSelector = '.errorlist:not(.nonfield), [data-field-error], .lm-field-error, .lm-auth-field-error, .lm-signup-error';
  root.querySelectorAll(errorSelector).forEach((errorNode) => {
    if (!(errorNode instanceof HTMLElement)) return;

    let scope = errorNode.closest('label, [data-form-field], .lm-field, .form-group');
    if (!scope) {
      let candidate = errorNode.parentElement;
      for (let depth = 0; candidate && depth < 3; depth += 1, candidate = candidate.parentElement) {
        if (candidate instanceof HTMLFormElement) break;
        const fields = candidate.querySelectorAll(EDITABLE_SELECTOR);
        if (fields.length === 1) {
          scope = candidate;
          break;
        }
      }
    }

    const field = scope?.querySelector?.(EDITABLE_SELECTOR);
    if (field) markFieldInvalid(field, errorNode);
    else errorNode.setAttribute('role', errorNode.getAttribute('role') || 'alert');
  });

  root.querySelectorAll('.errorlist.nonfield, .lm-form-error, .lm-auth-error, [data-form-error]').forEach((errorNode) => {
    if (errorNode instanceof HTMLElement) errorNode.setAttribute('role', errorNode.getAttribute('role') || 'alert');
  });
}

function focusFirstInvalidField(root = document) {
  if (document.documentElement.dataset.lmInvalidFocused === 'true') return;

  let field = root.querySelector('[aria-invalid="true"]:not([type="hidden"]):not([disabled])');
  if (!field) {
    const error = root.querySelector('.errorlist, [data-field-error], .lm-form-error');
    if (error) {
      const scope = error.closest('label, [data-form-field], .lm-field, .form-group, div') || error.parentElement;
      field = scope?.querySelector?.(EDITABLE_SELECTOR) || null;
    }
  }
  if (!(field instanceof HTMLElement)) return;

  document.documentElement.dataset.lmInvalidFocused = 'true';
  window.requestAnimationFrame(() => {
    field.scrollIntoView({ behavior: 'smooth', block: 'center' });
    try { field.focus({ preventScroll: true }); } catch (_) { field.focus(); }
  });
}

function hydrate(root = document) {
  root.querySelectorAll(FORM_SELECTOR).forEach(initForm);
  hydrateSummaryFieldErrors(root);
  hydrateRedirectNonFieldErrors(root);
  hydrateInvalidFields(root);
}

export default function initFormInteractions(root = document) {
  hydrate(root);
  focusFirstInvalidField(root);

  if (!beforeUnloadBound) {
    beforeUnloadBound = true;
    window.addEventListener('beforeunload', (event) => {
      const dirtyForm = document.querySelector('form[data-lm-dirty="true"]:not([data-lm-submitting="true"]), form[data-direct-edit-dirty="true"]:not([data-direct-edit-submitting="true"])');
      if (!dirtyForm) return;
      event.preventDefault();
      event.returnValue = '';
    });

    window.addEventListener('pageshow', () => {
      document.querySelectorAll('[data-lm-submit-pending="true"]').forEach(restoreSubmitter);
    });
  }

  if (document.documentElement.dataset.lmFormUxObserver === 'true') return;
  document.documentElement.dataset.lmFormUxObserver = 'true';
  const observer = new MutationObserver((mutations) => {
    const hasNewForms = mutations.some((mutation) => Array.from(mutation.addedNodes).some((node) =>
      node instanceof Element && (node.matches?.(FORM_SELECTOR) || node.querySelector?.(FORM_SELECTOR))
    ));
    if (hasNewForms) hydrate(document);
    else hydrateInvalidFields(document);
  });
  observer.observe(document.body, { childList: true, subtree: true });
}
