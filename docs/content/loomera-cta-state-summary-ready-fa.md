# Loomera CTA & State Message Library — Summary Ready
نسخه: 1.0  
کاربرد: docs/content, docs/design-system, product handoff

## Core Direction
- Loomera باید آرام، دقیق، قابل‌اعتماد و انسانی بماند.
- CTAها باید کوتاه، فعل‌محور و بی‌ابهام باشند.
- state messageها باید state-led، blame-free و در لحظه‌های حساس reassuring باشند.
- premium بودن از restraint و clarity می‌آید، نه از لحن تبلیغاتی.

## CTA Rules
- فرمت اصلی: `فعل + مفعول`
- طول ترجیحی: 1 تا 4 واژه
- نمونه‌های approved:
  - رزرو نوبت
  - مشاهده جزئیات
  - انتخاب زمان
  - تأیید و ادامه
  - پرداخت و ثبت نهایی
  - تماس با پشتیبانی
- avoid:
  - شروع تجربه
  - همین حالا رزرو کن
  - بزن بریم
  - از دست نده

## State Rules
- الگوی اصلی: `چه شد + اثر آن + قدم بعدی`
- مثال‌های approved:
  - نوبت شما ثبت شد.
  - پرداخت تأیید نشد. اگر مبلغی از حسابت کم شده یا نتیجه نامشخص است، دوباره پرداخت نکن و وضعیت همان تراکنش را پیگیری کن.
  - نتیجه‌ای با این فیلترها پیدا نشد. می‌توانید فیلترها را تغییر دهید.
  - جلسه شما منقضی شده است. لطفاً دوباره وارد شوید.
  - درخواست شما ثبت شد. نتیجه بررسی از همین بخش قابل پیگیری است.

## Directness by Context
- discovery: gentle-direct
- booking: clear-direct
- checkout/payment: explicit-direct
- auth/security: short and secure
- support: accountable and warm
- dashboard: utility-first and concise

## Approved Status Labels
- تأیید شد
- در انتظار
- انجام شد
- لغو شد
- ناموفق
- بازگشت وجه
- نیازمند اقدام
- غیرفعال
- فعال

## Empty State Direction
- title کوتاه و روشن
- body یک قدم بعدی را روشن کند
- CTA خروج از بن‌بست بدهد
- کاربر را مقصر جلوه ندهد

## Validation Direction
- کوتاه، field-specific، non-blaming
- نمونه‌ها:
  - این فیلد را کامل کنید.
  - شماره موبایل را با فرمت درست وارد کنید.
  - ایمیل را با فرمت درست وارد کنید.
  - کد تأیید معتبر نیست.

## Implementation Namespaces
- `cta.discovery`
- `cta.booking`
- `cta.checkout`
- `cta.account`
- `cta.support`
- `cta.retry`
- `cta.destructive`
- `state.success`
- `state.warning`
- `state.error`
- `state.pending`
- `state.empty`
- `state.confirmation`
- `state.validation`
- `state.security`
- `label.status`

## Final Recommendation
Loomera should sound direct enough to remove friction, but calm enough to preserve trust.  
در discovery باید دعوت‌کننده باشد، در booking راهنما، در checkout بسیار دقیق، و در support مسئولانه و انسانی.
