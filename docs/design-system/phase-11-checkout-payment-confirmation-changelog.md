# Phase 11 — Checkout, Payment & Confirmation

## Scope
This phase updates presentation for booking preview, checkout and payment confirmation only. It does not change routes, URLconf, Django views, models, migrations, booking logic, availability logic, payment gateway logic, wallet logic, dashboard logic, assets, fonts or generated Tailwind output.

## Real templates audited
- `templates/orders/reservation_preview.html`
- `templates/orders/checkout.html`
- `templates/payments/appointment_result.html`

## Real routes/views audited
- `orders:reservation_preview` renders `orders/reservation_preview.html` through `ReservationPreview`.
- `orders:checkout` is the existing final checkout endpoint used by current forms.
- `payments:appointment_result` renders `payments/appointment_result.html` for payment success/cancel/failure states.

## Preserved form and backend hooks
- `#appointment-checkout-form`
- `action="{% url 'orders:checkout' %}"`
- `{% csrf_token %}`
- `name="form_action"` values: `apply_coupon`, `clear_coupon`, `confirm_checkout`
- `form.coupon_code`
- `form.payment_method`
- existing payment choice values from `AppointmentCheckoutForm`: `online`, `wallet`, `pay_in_salon`
- existing checkout payload keys such as `checkout.service_details`, `checkout.total_amount`, `checkout.booking_policy`, `checkout.wallet_balance`, `checkout.requires_online_payment`

## Presentation changes
- Added booking progress step 4/4.
- Converted preview/checkout to card-based review structure.
- Added mobile sticky final CTA using Phase 01 primitives.
- Added desktop side summary card with total amount and final CTA.
- Polished payment method cards without changing payment values.
- Polished discount/coupon presentation without changing form behavior.
- Polished policy/trust card using existing `checkout.booking_policy` only.
- Polished confirmation states for success, cancelled and failed payment outcomes.
- Added optional order detail list in confirmation using existing `order.order_details1` relation.

## Data decisions
No fake price, payment method, discount, cancellation policy, confirmation state, service, staff, date or time was added. All monetary values shown come from existing checkout/order/payment context.

## Mobile/desktop behavior
- Mobile: compact header, progress, summary cards, sticky CTA and safe-area friendly spacing.
- Desktop: main review column plus sticky side summary.
- Confirmation: success/failure/cancelled state card plus next actions using existing routes.

## Backlog
- Phase 12 should align customer account/bookings with the confirmation details shown here.
- A future payment-specific phase can improve gateway error state granularity if backend exposes more structured states.
- A future localization pass can standardize date formats across all booking/account screens.
