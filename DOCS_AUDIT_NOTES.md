# Content audit notes — 2026-08-26 staging

این فایل برای تیم توسعه است، نه متن قابل نمایش به کاربر.

منابع اولیه تولید `production_docs.json` از branch `staging`:

- `apps/dashboards/views.py`: TeamMemberView, AddStylistView, toggle_stylist_status, ServiceMenuView, AddServicesView, toggle_service_status, ScheduledShiftsView, SetRegularShiftsView, AddTimeOffView, DashboardManualBookingView, StylistScheduleView, StylistAddScheduleView, StylistAddTimeOffView, StylistAppointmentsView, `_build_team_capacity_setup_workspace`.
- `apps/dashboards/payment_views.py`: SalonCouponManagementView / Toggle / Delete, SalonDiscountBasketManagementView, SalonDiscountCampaignManagementView.
- `apps/discounts/forms.py`: SalonCouponForm, SalonDiscountBasketForm, SalonDiscountCampaignForm.
- `apps/orders/views.py`: checkout conflict behavior, RescheduleDateTimeView, RescheduleConfirmView.
- `apps/payments/views.py`: wallet feature flag, WalletDetailView, WalletChargeView, WalletTransactionsView.
- `apps/accounts/urls.py`: customer addresses routes.
- `apps/main/support_services.py`: support initialization.

نکته: `source_refs` برای کاربر نمایش داده نمی‌شود؛ citation کاربر همیشه به مقاله `/help/article/.../` اشاره می‌کند. این refها فقط برای audit داخلی نویسندگان مستندات‌اند.
