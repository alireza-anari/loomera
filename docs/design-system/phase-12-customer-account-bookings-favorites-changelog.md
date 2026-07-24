# Phase 12 — Customer Account, Bookings & Favorites Changelog

## Scope
Phase 12 فقط presentation حساب مشتری، نوبت‌ها، علاقه‌مندی‌ها و جزئیات نوبت را تغییر می‌دهد. هیچ route، view logic، model، migration، booking/payment/cancellation/favorite backend logic یا dashboard data logic تغییر نکرد.

## Templates
- `templates/accounts/customer_panel.html`
  - account home به card-based customer hub تبدیل شد.
  - profile summary، wallet، quick actions، bookings entry و settings/support entry pointها بازآرایی شدند.
- `templates/orders/appointments.html`
  - لیست نوبت‌ها به بخش‌های upcoming و past با layout موبایل/دسکتاپ واضح‌تر تبدیل شد.
- `templates/components/appointment_upcoming_card.html`
  - کارت نوبت آینده با status/payment badge، service/staff/date/time و actions polish شد.
- `templates/components/appointment_past_item.html`
  - ردیف نوبت گذشته با status badge و rebook/detail actions هماهنگ شد.
- `templates/components/appointments_empty_state.html`
  - empty state با برند Loomera و CTA جستجوی سالن‌ها هماهنگ شد.
- `templates/orders/appointment_detail.html`
  - جزئیات نوبت به ساختار summary مشابه confirmation فاز ۱۱ تبدیل شد.
  - services، finance، progress، policy، salon info و actions card-based شدند.
- `templates/csf/partials/favorite_salons.html`
  - صفحه علاقه‌مندی‌ها به grid/card layout responsive تبدیل شد.
- `templates/components/favorits_salon_card.html`
  - کارت سالن مورد علاقه با rhythm جدید search/profile هماهنگ شد.

## Real data used
- `upcoming_appointments`
- `past_appointments`
- `appointment`
- `order_items`
- `payment_status_label`
- `finance_summary`
- `payment_record`
- `financial_transactions`
- `customer_progress`
- `cancellation_policy`
- `salons`
- `wallet`
- `primary_address`
- `address_count`

## Actions preserved
- مشاهده جزئیات نوبت
- رزرو دوباره
- مسیر سالن
- افزودن به تقویم
- مدیریت/لغو نوبت از modal موجود
- پرداخت در سالن از form موجود
- ثبت دیدگاه با `review_url`
- علاقه‌مندی‌ها با favorite route موجود

## What was not added
- هیچ booking fake اضافه نشد.
- هیچ payment status fake اضافه نشد.
- هیچ wallet/review/favorite fake اضافه نشد.
- هیچ action بدون route/backend واقعی اضافه نشد.
- هیچ payment/cancellation/favorite/rebook logic تغییر نکرد.

## Backlog
- اگر نیاز به segmentation دقیق‌تر cancelled/failed وجود دارد، باید context جدا در view اضافه شود.
- اگر wallet summary غنی‌تر لازم است، باید از data واقعی wallet در فاز جدا استفاده شود.
- review prompts فقط در appointment detail و با `customer_progress.can_review` واقعی نمایش داده می‌شوند.
- اگر account home بخواهد next appointment preview داشته باشد، باید context واقعی upcoming appointment به `CustomerPanelPageView` اضافه شود؛ در این فاز انجام نشد.
