# Loomera Payment, Refund, and Provider Finance Operations Policy

## Scope
This document defines the current product and technical rules for appointment checkout, coupon handling, wallet payment, refund-to-wallet behavior, first-visit commission, provider finance wallet readiness, and settlement behavior.

> Terminology note: user-facing Loomera docs may use **provider / center / clinic / studio / specialist**. The current implementation still uses `salon` and `stylist` model names in several places. Where the implementation matters, this document keeps the technical wording explicit.

## Core product rules
1. A customer's **first visit to a specific provider** must be paid digitally. In the current implementation, this rule is evaluated per customer + salon.
2. Digital payment means either **online gateway** or **customer wallet**.
3. Repeat visits by the same customer to the same provider may use online payment, wallet payment, or pay-in-salon.
4. First-visit commission is calculated **per customer + salon**, not globally across the platform.
5. Cancellation and refund rules are stored **per salon/provider** in the database.
6. Refund after cancellation is supported only for **online** and **wallet** payments. Pay-in-salon orders do not receive an automatic refund.
7. Provider payout information, cancellation policy, discount tools, and finance wallet are managed from the dashboard finance center.

## Checkout flow
- Date/time and specialist selections are validated and normalized.
- The merged review/checkout page shows selected services, final amount, coupon field, payment method, and cancellation policy.
- If a coupon is valid, it is applied and stored on the order.
- If a coupon is invalid and the user wants to finalize the booking, checkout continues **without discount** and the user receives a warning instead of a dead-end validation state.
- Booking records are locked before final order creation to reduce slot conflicts.

## Customer payment methods
### Online gateway
- Creates a payment record.
- Redirects to the active provider mode (`mock`, `sandbox`, or `live`).
- Final verification updates order payment state and settlement snapshot.

### Wallet payment
- Requires sufficient wallet balance.
- Deducts the amount from the customer wallet atomically.
- Stores a `PURCHASE` wallet transaction linked to the booking.
- Creates a `Payment` record with provider `wallet`.
- Marks the order as paid immediately.

### Pay in salon
- Available only for repeat visits.
- Creates the booking without digital payment.
- Does not create automatic refund eligibility.

## Refund-to-wallet logic
Refund is allowed only when all of the following are true:
- The appointment belongs to the authenticated customer.
- The appointment is still eligible for online cancellation.
- The order was paid digitally (`online` or `wallet`).
- No wallet refund has already been recorded for the same order.

Refund result:
- Refund amount = `order.total_amount * salon.cancellation_refund_percent / 100`
- Refund is credited to the customer's wallet.
- The order stores refund amount and refund timestamp.
- The related settlement record is updated.
- The provider finance wallet is also adjusted so the net receivable remains accurate.

## Provider finance wallet
Each provider currently has a dedicated finance wallet with two balances:
- `pending_balance`: digital revenue that has been registered but is still under the configured payout delay / cancellation risk window.
- `available_balance`: amount eligible for withdrawal by the salon manager/provider owner.

### How it works
- A successful digital booking creates a settlement snapshot.
- The provider's net receivable is added to `pending_balance`.
- After `payout_delay_days`, eligible funds move from pending to available.
- If the booking is refunded or adjusted before payout, the provider wallet is reduced accordingly.

### Withdrawal
- Withdrawal requests are created from `available_balance` only.
- Requests store amount, IBAN, account holder, bank name, and status.
- This is currently a **request + manual review** workflow, not an automatic bank transfer.

## Settlement record
Each appointment order stores a dedicated settlement snapshot including:
- gross service amount
- discount amount
- paid amount
- refund amount
- first-visit commission flag and amount
- net amount due to salon/provider
- payout state and hold reason
- salon policy snapshot at the time of the order

## Provider-managed policy fields
Per salon/provider:
- payout IBAN
- account holder name
- bank name
- payout contact mobile
- cancellation window hours
- cancellation refund percent
- payout delay days
- cancellation policy note

## Discount tools
Dashboard finance now supports:
- provider-specific coupon codes
- provider-specific discount baskets for grouping campaign services

Notes:
- Coupon codes can already be applied during checkout.
- Discount baskets are currently managed as a structured campaign layer in the dashboard and can be expanded to auto-apply pricing logic in a later pass.

## Security notes
- Gateway secrets must come only from environment variables.
- Callback handling must remain verification-based.
- Internal settlement or gateway identifiers should not be shown in customer-facing pages.
- Refund logic must remain idempotent.
- Financial snapshots must not be recalculated retroactively from mutable live data when historical records are needed.
- Wallet and finance-wallet changes should remain atomic to reduce race-condition risk.
