export default function initDeleteAccount() {
  let currentStep = 1;

  function initializeStepNavigation() {
    const form = document.getElementById('deleteAccountForm');
    if (!form) {
      console.error('Form not found');
      return;
    }

    const stepDots = document.querySelectorAll('.step-dot');
    const stepContents = document.querySelectorAll('.step-content');
    const nextButtons = document.querySelectorAll('.next-step-btn');
    const prevButtons = document.querySelectorAll('.prev-step-btn');

    function updateStep(step) {
      currentStep = step;
      // Update dots
      stepDots.forEach(dot => {
        const dotStep = parseInt(dot.getAttribute('data-step'));
        if (dotStep === step) {
          dot.classList.add('active');
        } else {
          dot.classList.remove('active');
        }
      });

      // Update content
      stepContents.forEach(content => {
        const contentStep = parseInt(content.getAttribute('data-step'));
        if (contentStep === step) {
          content.classList.add('active');
        } else {
          content.classList.remove('active');
        }
      });

      // Scroll to top
      const modal = document.querySelector('.bg-white');
      if (modal) {
        modal.scrollTop = 0;
      }
    }

    // Next button listeners
    nextButtons.forEach((btn, index) => {
      btn.addEventListener('click', function(e) {
        e.preventDefault();

        // Validate current step before moving to next
        if (currentStep === 1) {
          const reasonSelected = form.querySelector('input[name="reason"]:checked');
          if (!reasonSelected) {
            window.LoomeraFeedback?.error?.('لطفاً یک دلیل انتخاب کنید');
            return;
          }
        } else if (currentStep === 2) {
          const confirm1 = form.querySelector('input[name="confirm_appointments"]')?.checked;
          const confirm2 = form.querySelector('input[name="confirm_bookings"]')?.checked;
          if (!confirm1 || !confirm2) {
            window.LoomeraFeedback?.error?.('لطفاً تمام موارد را تایید کنید');
            return;
          }
        }

        if (currentStep < 3) {
          updateStep(currentStep + 1);
        }
      });
    });

    // Previous button listeners
    prevButtons.forEach(btn => {
      btn.addEventListener('click', function(e) {
        e.preventDefault();
        if (currentStep > 1) {
          updateStep(currentStep - 1);
        }
      });
    });

    // Initialize first step
    updateStep(1);
  }

  // Call initialization immediately
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeStepNavigation);
  } else {
    // DOM is already loaded
    setTimeout(initializeStepNavigation, 100);
  }
}
