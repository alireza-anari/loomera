# Loomera CRM Implementation Notes

## Naming system
`crm.{lifecycle_family}.{audience}.{channel}.{variant}`

Examples:
- `crm.welcome.customer.email.rich`
- `crm.abandoned_booking.customer.push.short`
- `crm.reminders.customer.sms.t_minus_2h`
- `crm.payment_recovery.customer.email.failed_payment`
- `crm.support_followup.customer.email.resolution_check`
- `crm.partner_onboarding.provider.email.setup_reminder`

## Folder structure
```text
crm/
  welcome/
  abandoned_booking/
  reminders/
  previsit/
  postvisit/
  review_request/
  rebook/
  winback/
  favorites/
  payment_recovery/
  refund_followup/
  support_followup/
  feature_education/
  seasonal_campaign/
  partner_onboarding/
shared/
  modules/
    email_header/
    footer/
    reassurance_block/
    booking_summary/
    payment_status/
    support_signature/
  tokens/
    personalization_tokens.json
    cadence_rules.json
    channel_rules.json
```

## Placeholder naming
Use snake_case inside `{{ }}`:
`{{first_name}}`, `{{provider_name}}`, `{{service_name}}`, `{{appointment_date}}`, `{{appointment_time}}`, `{{city}}`, `{{order_id}}`, `{{payment_retry_url}}`.

## Shared modules
- `email_header.transactional`
- `email_header.booking`
- `email_header.payment`
- `email_header.support`
- `email_header.partner`
- `booking_summary.compact`
- `payment_status.reassurance`
- `support_signature.human`
- `footer.preferences`

## Channel adaptation
Email مادر محتواست؛ push/SMS خلاصه مکانیکی email نیست، بلکه یک پیام مستقل با همان trigger و CTA واحد است. In-app باید context-aware باشد و وقتی کاربر داخل flow است، توضیح اضافه ندهد.
