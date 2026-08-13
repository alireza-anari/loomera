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
