let dashboardManagerProfileBound = false;

export default function initDashboardManagerProfile() {
  if (dashboardManagerProfileBound) return;

  const form = document.querySelector("[data-manager-profile-form]");
  if (!form) return;
  dashboardManagerProfileBound = true;

  const imageInput = document.getElementById("managerProfileImageInput");
  const avatarPreview = document.querySelector("[data-manager-avatar-preview]");
  const nameInput = form.querySelector('[name="name"]');
  const familyInput = form.querySelector('[name="family"]');
  const previewName = document.querySelector("[data-manager-preview-name]");

  const refreshName = () => {
    if (!previewName) return;
    const fullName = [nameInput?.value?.trim(), familyInput?.value?.trim()]
      .filter(Boolean)
      .join(" ");
    previewName.textContent = fullName || "مدیر مجموعه";
  };

  [nameInput, familyInput].forEach((input) => {
    input?.addEventListener("input", refreshName);
  });

  imageInput?.addEventListener("change", function () {
    const file = this.files?.[0];
    if (!file || !avatarPreview) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      const src = event.target?.result;
      if (!src) return;

      const current = avatarPreview.querySelector("#managerProfileImagePreview");
      const image = document.createElement("img");
      image.id = "managerProfileImagePreview";
      image.src = src;
      image.alt = "پیش‌نمایش تصویر پروفایل مدیر";
      image.className = "h-24 w-24 rounded-full border-4 border-white object-cover shadow-lm-card lg:h-28 lg:w-28";
      current?.replaceWith(image);
    };
    reader.readAsDataURL(file);
  });

  refreshName();
}

initDashboardManagerProfile();
