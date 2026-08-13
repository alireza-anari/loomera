// static/js/pages/edit_profile.js

/**
 * Edit Profile Page Initialization
 * - Image preview handling
 * - Form validation
 * - Jalali/Gregorian date conversion
 */

export default function initEditProfile() {
  // ==========================================
  // Profile Image Preview
  // ==========================================
  const profileImageInput = document.getElementById('profileImageInput');
  const profileImagePreview = document.getElementById('profileImagePreview');
  const editForm = document.getElementById('editProfileForm');

  if (profileImageInput) {
    profileImageInput.addEventListener('change', (event) => {
      const file = event.target.files[0];
      if (file && file.type.startsWith('image/')) {
        const reader = new FileReader();
        reader.onload = (e) => {
          if (profileImagePreview) {
            if (profileImagePreview.tagName === 'IMG') {
              profileImagePreview.src = e.target.result;
            } else {
              // Convert div to img
              const img = document.createElement('img');
              img.id = 'profileImagePreview';
              img.src = e.target.result;
              img.className = 'w-full h-full rounded-full object-cover border-4 border-white shadow-md';
              profileImagePreview.replaceWith(img);
            }
          }
        };
        reader.readAsDataURL(file);
      }
    });
  }

  // ==========================================
  // Form Validation
  // ==========================================
  if (editForm) {
    editForm.addEventListener('submit', (e) => {
      const birthDay = editForm.querySelector('input[name="birth_day"]').value;
      const birthMonth = editForm.querySelector('select[name="birth_month"]').value;
      const birthYear = editForm.querySelector('input[name="birth_year"]').value;

      // If any birth field is filled, all must be filled
      const anyBirthFieldFilled = birthDay || birthMonth || birthYear;
      const allBirthFieldsFilled = birthDay && birthMonth && birthYear;

      if (anyBirthFieldFilled && !allBirthFieldsFilled) {
        e.preventDefault();
        alert('لطفاً تمام فیلدهای تاریخ تولد را پر کنید یا همه را خالی بگذارید.');
      }

      // Validate birth year is reasonable (1900-2024)
      if (birthYear && (parseInt(birthYear) < 1300 || parseInt(birthYear) > 1410)) {
        e.preventDefault();
        alert('سال تاریخ تولد را درست بررسی کنید.');
      }

      // Validate day
      if (birthDay && (parseInt(birthDay) < 1 || parseInt(birthDay) > 31)) {
        e.preventDefault();
        alert('روز نمی‌تواند کمتر از ۱ یا بیش‌تر از ۳۱ باشد.');
      }
    });
  }

  // ==========================================
  // Mobile Number Formatting (RTL)
  // ==========================================
  const mobileInput = editForm?.querySelector('input[name="mobile_number"]');
  if (mobileInput) {
    // Mobile is read-only, so just ensure proper dir
    mobileInput.dir = 'ltr';
  }

  // ==========================================
  // Numeric Input Handling
  // ==========================================
  const dayInput = editForm?.querySelector('input[name="birth_day"]');
  const yearInput = editForm?.querySelector('input[name="birth_year"]');

  if (dayInput) {
    dayInput.addEventListener('input', (e) => {
      // Keep only digits and limit to 2 characters
      e.target.value = e.target.value.replace(/[^0-9]/g, '').slice(0, 2);
    });
  }

  if (yearInput) {
    yearInput.addEventListener('input', (e) => {
      // Keep only digits and limit to 4 characters
      e.target.value = e.target.value.replace(/[^0-9]/g, '').slice(0, 4);
    });
  }

}
