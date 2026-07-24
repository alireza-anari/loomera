# Phase 16 — Partner POS, Payments & Invoices Changelog

## Scope

Phase 16 فقط presentation و UX بخش مالی partner را تغییر می‌دهد. هیچ route، URLconf، view logic، context/query builder، payment/gateway/wallet backend، invoice backend، refund/settlement logic، booking logic، model، migration، asset، logo، font file یا `static/css/output.css` تغییر نکرد.

## Real templates and routes reviewed

| Area | Route / template | Notes |
|---|---|---|
| Finance reports | `dashboards:finance_reports` / `templates/dashboards/finance_reports.html` | اصلی‌ترین صفحه واقعی برای فروش، پرداخت‌ها، wallet flow، settlement و reconciliation. |
| Finance export | `dashboards:finance_reports_export` | لینک CSV موجود حفظ شد. |
| Payout settings | `dashboards:payout_settings` / `templates/dashboards/payout_settings.html` | route واقعی برای wallet، withdrawal و اطلاعات مالی سالن؛ تغییر داده نشد. |
| Coupons | `dashboards:finance_coupons` | route واقعی تخفیف‌ها؛ فقط به عنوان quick action استفاده شد. |
| Discount baskets | `dashboards:finance_baskets` | route واقعی سبدهای تخفیف؛ فقط به عنوان quick action استفاده شد. |

## Real data used

- `summary_cards`
- `filters`
- `payment_method_options`
- `payout_state_options`
- `payment_breakdown`
- `wallet_summary`
- `wallet_transactions`
- `reconciliation_rows`
- `campaign_cards`
- `coupon_performance`
- `basket_performance`
- `withdrawal_summary`
- `finance_alerts`
- `export_url`

## Mobile finance branch

A mobile-only branch was added to `templates/dashboards/finance_reports.html`:

```html
<section class="lm-finance-mobile lg:hidden" data-finance-home="partner-mobile">
```

Desktop content was preserved in:

```html
<div class="hidden lg:block" data-finance-home="partner-desktop">
```

## Actions used

Only existing routes/actions were used:

- `dashboards:payout_settings`
- `dashboards:finance_coupons`
- `dashboards:finance_baskets`
- `dashboards:finance_reports`
- `export_url`

No refund, print, invoice, POS sale or gateway action was created because no confirmed route/action was used in this phase.

## What was not faked

- payment
- invoice
- POS sale
- revenue
- transaction
- wallet balance
- refund
- gateway/reference state
- customer/appointment line item
- finance trend
- settlement state

## CSS helpers added

Scoped helpers were appended to `static/css/loomera-brand.css`:

- `lm-finance-mobile`
- `lm-finance-mobile-hero`
- `lm-finance-mobile-filter`
- `lm-finance-mobile-section`
- `lm-finance-mobile-metrics`
- `lm-finance-mobile-action`
- `lm-finance-mobile-payment-card`
- `lm-finance-mobile-transaction`
- `lm-finance-mobile-reconciliation`
- `lm-finance-mobile-wallet-grid`

## Backlog

| Item | Future phase |
|---|---|
| Dedicated POS sale flow | Requires real route/backend; not in Phase 16. |
| Invoice list/detail | Requires real invoice route/data if product wants it. |
| Payment/refund detail drawer | Only if real payment/refund actions are exposed. |
| Customer financial profile integration | Can build on CRM Phase 15 and finance data later. |
| Financial insight/trend cards | Phase 18 Reports/Insights, only with real data. |
