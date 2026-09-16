// static/js/pages/change_password.js

/**
 * Change Password Page Initialization
 * - Password visibility toggle
 * - Form validation
 * - Password strength indicator (optional)
 */

export default function initChangePassword() {
  const toggleButtons = document.querySelectorAll('.toggle-password');
  const form = document.getElementById('changePasswordForm');

  // ==========================================
  // Password Visibility Toggle
  // ==========================================
  toggleButtons.forEach(button => {
    button.addEventListener('click', function(e) {
      e.preventDefault();

      const targetId = this.getAttribute('data-target');
      const input = document.getElementById(targetId);
      const icon = this.querySelector('i');

      if (input.type === 'password') {
        input.type = 'text';
        icon.classList.remove('fa-eye');
        icon.classList.add('fa-eye-slash');
      } else {
        input.type = 'password';
        icon.classList.remove('fa-eye-slash');
        icon.classList.add('fa-eye');
      }
    });
  });

  // ==========================================
  // Form Validation
  // ==========================================
  if (form) {
    form.addEventListener('submit', function(e) {
      const newPassword = document.getElementById('newPassword');
      const confirmPassword = document.getElementById('confirmPassword');
      const currentPassword = document.getElementById('currentPassword');

      // Check if passwords match
      if (newPassword.value !== confirmPassword.value) {
        e.preventDefault();
        window.LoomeraFeedback?.error?.('رمز عبور و تکرار آن مطابقت ندارند');
        return false;
      }

      // Check minimum length
      if (newPassword.value.length < 6) {
        e.preventDefault();
        window.LoomeraFeedback?.error?.('رمز عبور باید حداقل ۶ کاراکتر باشد');
        return false;
      }

      // If current password field exists, check it's not empty
      if (currentPassword && !currentPassword.value) {
        e.preventDefault();
        window.LoomeraFeedback?.error?.('لطفاً رمز عبور فعلی را وارد کنید');
        return false;
      }

      // Check that new password is different from current
      if (currentPassword && newPassword.value === currentPassword.value) {
        e.preventDefault();
        window.LoomeraFeedback?.error?.('رمز عبور جدید نباید برابر با رمز عبور فعلی باشد');
        return false;
      }
    });
  }

}
