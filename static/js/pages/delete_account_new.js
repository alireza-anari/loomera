export default function initDeleteAccount() {
  let currentStep = 1;

  function initializeStepNavigation() {
    const form = document.getElementById("deleteAccountForm");
    if (!form) {
      console.error("[delete-account] form not found");
      return;
    }

    const stepDots = document.querySelectorAll(".step-dot");
    const stepContents = document.querySelectorAll(".step-content");
    const nextButtons = document.querySelectorAll(".next-step-btn");
    const prevButtons = document.querySelectorAll(".prev-step-btn");

    function updateStep(step) {
      currentStep = step;

      stepDots.forEach((dot) => {
        const dotStep = Number.parseInt(dot.getAttribute("data-step"), 10);
        dot.classList.toggle("active", dotStep === step);
      });

      stepContents.forEach((content) => {
        const contentStep = Number.parseInt(
          content.getAttribute("data-step"),
          10,
        );
        content.classList.toggle("active", contentStep === step);
      });

      const modal = document.querySelector(".bg-white");
      if (modal) {
        modal.scrollTop = 0;
      }
    }

    nextButtons.forEach((button) => {
      button.addEventListener("click", (event) => {
        event.preventDefault();

        if (currentStep === 1) {
          const reasonSelected = form.querySelector(
            'input[name="reason"]:checked',
          );
          if (!reasonSelected) {
            window.alert("لطفاً یک دلیل انتخاب کنید");
            return;
          }
        } else if (currentStep === 2) {
          const confirmAppointments = form.querySelector(
            'input[name="confirm_appointments"]',
          )?.checked;
          const confirmBookings = form.querySelector(
            'input[name="confirm_bookings"]',
          )?.checked;

          if (!confirmAppointments || !confirmBookings) {
            window.alert("لطفاً تمام موارد را تایید کنید");
            return;
          }
        }

        if (currentStep < 3) {
          updateStep(currentStep + 1);
        }
      });
    });

    prevButtons.forEach((button) => {
      button.addEventListener("click", (event) => {
        event.preventDefault();

        if (currentStep > 1) {
          updateStep(currentStep - 1);
        }
      });
    });

    updateStep(1);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializeStepNavigation, {
      once: true,
    });
  } else {
    window.setTimeout(initializeStepNavigation, 100);
  }
}
