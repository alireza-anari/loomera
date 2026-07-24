import initDetailSalon from "./pages/detail_salon.js";
import initSalons from "./pages/show_salons.js";
import initSearchPage from "./pages/search.js";
import initOrdersPage from "./pages/orders.js";
import initProfilePage from "./pages/profile.js";
import initEditProfile from "./pages/edit_profile.js";
import initNotificationSettings from "./pages/notification_settings.js";
import initChangePassword from "./pages/change_password.js";
import initDeleteAccount from "./pages/delete_account_new.js";
import initDashboardLayout from "./pages/dashboard_layout.js";
import "./pages/dashboard_workspace.js";
import initAppointmentsManagement from "./pages/appointments_management.js";
import initReportsDashboard from "./pages/reports_dashboard.js";
import initEditDaySchedule from "./pages/edit_day_schedule.js";
import initSetRegularShifts from "./pages/set_regular_shifts.js";
import initAddTimeOff from "./pages/add_time_off.js";
import initAddStylist from "./pages/add_stylist.js";
import initEditStylist from "./pages/edit_stylist.js";
import initEditService from "./pages/edit_service.js";
import initManualBookingPage from "./pages/manual_booking.js";
import { initMagazinePage } from "./pages/magazine.js";
import initCustomerNotificationHeader from "./pages/customer_notification_header.js";
import initLoomeraDatepickers from "./pages/datepickers.js";
// NOTE: select_datetime is loaded directly in template (non-module)

document.addEventListener("DOMContentLoaded", async () => {
  const body = document.body;
  const page = body.getAttribute("data-page");
  const dashboardPage = body.getAttribute("data-dashboard-page");

  try {
    initLoomeraDatepickers();
  } catch (error) {
    console.error("[app] datepicker initialization failed");
  }

  try {
    initCustomerNotificationHeader();
  } catch (error) {
    console.error("[app] customer notification header initialization failed");
  }

  const pages = {
    detail_salon: initDetailSalon,
    salons: initSalons,
    search: initSearchPage,
    magazine: initMagazinePage,
    orders: initOrdersPage,
    profile: initProfilePage,
    "edit-profile": initEditProfile,
    "notification-settings": initNotificationSettings,
    "change-password": initChangePassword,
    "delete-account": initDeleteAccount,
    "dashboard-layout": initDashboardLayout,
    "appointments-management": initAppointmentsManagement,
    "reports-dashboard": initReportsDashboard,
    "edit-day-schedule": initEditDaySchedule,
    "set-regular-shifts": initSetRegularShifts,
    "add-time-off": initAddTimeOff,
    "add-stylist": initAddStylist,
    "edit-stylist":initEditStylist,
    "edit-service": initEditService,
    "manual-booking": initManualBookingPage,
  };

  if (pages[page]) {
    try {
      pages[page]();
    } catch (error) {
      console.error("[app] page initialization failed");
    }
  }

  try {
    initLoomeraDatepickers(document);
  } catch (error) {
    console.error("[app] datepicker refresh failed");
  }

  if (!dashboardPage) return;

  try {
    if (dashboardPage === "salon-location-step") {
      const module = await import("./pages/salon_location_step.js");
      if (module?.default) module.default();
    }

    if (dashboardPage === "salon-working-hours-step") {
      const module = await import("./pages/salon_working_hours_step.js");
      if (module?.default) module.default();
    }

    if (dashboardPage === "salon-features-step") {
      const module = await import("./pages/salon_features_step.js");
      if (module?.default) module.default();
    }
  } catch (error) {
    console.error("[app] dashboard page initialization failed");
  }
});