let directEditBound = false;

const fieldSnapshot = (form) => {
  const parts = [];
  const fields = Array.from(form.elements || []);
  fields.forEach((field) => {
    if (!field?.name || field.disabled || ["submit", "button", "reset"].includes(field.type)) return;
    if (field.type === "file") {
      parts.push(`${field.name}:file:${field.files?.length || 0}`);
      return;
    }
    if ((field.type === "checkbox" || field.type === "radio") && !field.checked) {
      parts.push(`${field.name}:unchecked`);
      return;
    }
    parts.push(`${field.name}:${field.value ?? ""}`);
  });
  return parts.join("|");
};

const setStatus = (form, dirty, submitting = false) => {
  const status = form.querySelector("[data-direct-edit-status]");
  if (!status) return;

  status.classList.remove("text-loomera-warning", "text-loomera-success", "text-loomera-textPrimary");
  if (submitting) {
    status.textContent = "در حال ذخیره…";
    status.classList.add("text-loomera-primaryText");
  } else if (dirty) {
    status.textContent = "تغییرات ذخیره نشده";
    status.classList.add("text-loomera-warning");
  } else {
    status.textContent = "همه تغییرات ذخیره شده‌اند";
    status.classList.add("text-loomera-success");
  }
};

export default function initDashboardDirectEdit() {
  const forms = Array.from(document.querySelectorAll("[data-direct-edit-form]"));
  if (!forms.length) return;

  forms.forEach((form) => {
    if (form.dataset.directEditReady === "true") return;
    form.dataset.directEditReady = "true";

    const initial = fieldSnapshot(form);
    form.dataset.directEditDirty = "false";
    setStatus(form, false);

    const refresh = () => {
      const dirty = fieldSnapshot(form) !== initial;
      form.dataset.directEditDirty = dirty ? "true" : "false";
      setStatus(form, dirty);
    };

    form.addEventListener("input", refresh);
    form.addEventListener("change", refresh);
    form.addEventListener("submit", () => {
      form.dataset.directEditSubmitting = "true";
      setStatus(form, true, true);
    });
  });

  if (!directEditBound) {
    directEditBound = true;
    window.addEventListener("beforeunload", (event) => {
      const dirtyForm = document.querySelector('[data-direct-edit-form][data-direct-edit-dirty="true"]:not([data-direct-edit-submitting="true"])');
      if (!dirtyForm) return;
      event.preventDefault();
      event.returnValue = "";
    });
  }
}
