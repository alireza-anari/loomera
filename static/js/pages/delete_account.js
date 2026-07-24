export default function initDeleteAccount() {
  const deleteAccountBtn = document.getElementById('deleteAccountBtn');
  const deleteAccountModal = document.getElementById('deleteAccountModal');
  const closeButtons = deleteAccountModal?.querySelectorAll('[onclick*="deleteAccountModal"]') || [];

  if (deleteAccountBtn) {
    deleteAccountBtn.addEventListener('click', function() {
      deleteAccountModal.classList.remove('hidden');
      // Add animation by triggering reflow
      deleteAccountModal.offsetHeight;
      deleteAccountModal.querySelector('.bg-white').classList.add('animate-slideUp');
    });
  }

  // Close modal when clicking outside
  if (deleteAccountModal) {
    deleteAccountModal.addEventListener('click', function(e) {
      if (e.target === this) {
        this.classList.add('hidden');
        this.querySelector('.bg-white').classList.remove('animate-slideUp');
      }
    });
  }
}
