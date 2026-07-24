# Loomera Domain & Email System
**نسخه نهایی — بازار ایران**  
**Primary domain:** `loomera.ir`

## 1) مبنای تصمیم

Loomera در سورس یک برند **calm, refined, trustworthy, human** با positioning روشن در **beauty + aesthetic treatments + massage + wellness** است؛ نه یک برند salon-only. لحن آن باید در touchpointهای booking، payment، support و notification، شفاف، reassuring و friction-reducing بماند. بر همین اساس، سیستم دامنه و ایمیل هم باید **brand-led، روشن، حرفه‌ای، کم‌نویز و operationally sound** باشد.

با توجه به اینکه بازار هدف فقط ایران است و دامنه **`loomera.ir`** هم خریداری شده، بهترین تصمیم این است که کل identity دیجیتال برند روی همین root domain بسته شود و همه‌ی touchpointهای product, support, billing, provider onboarding و notification حول آن یکپارچه شوند. این انتخاب با brand voice فعلی Loomera هم‌راستاست، چون برند باید trusted, calm و product-ready باشد، نه صرفاً marketing-first.

---

## 2) Domain Strategy

### Domain personality
دامنه‌ی Loomera باید این حس را منتقل کند:
- آرام و مطمئن
- refined و تمیز
- روشن و قابل‌اعتماد
- مناسب محصول واقعی، نه فقط کمپین مارکتینگ
- سازگار با beauty، treatments، massage و wellness، بدون salon-first framing

### Domain naming principles
- brand-led باشد
- کوتاه و مستقیم باشد
- قابل‌اعتماد و رسمی بماند
- برای محصول، رزرو، پشتیبانی، پرداخت و همکاری قابل استفاده باشد
- از namingهای noisy، category-heavy و generic دور بماند

### Final decision
- **Root domain:** `loomera.ir`
- **Canonical public brand domain:** `www.loomera.ir`
- **Canonical product domain:** `app.loomera.ir`

این ساختار برای بازار ایران، ساده‌ترین و حرفه‌ای‌ترین انتخاب است: هم local trust می‌سازد، هم در همه‌ی لایه‌های brand + product + operations یکپارچه می‌ماند. این تصمیم یک fallback نیست؛ تصمیم اصلی و نهایی است.

---

## 3) Primary Domain Recommendation

### گزینه نهایی
**`loomera.ir`**

### چرا این گزینه درست است
- brand-first است
- برای بازار ایران طبیعی و معتبر است
- برای product, support, billing, legal و provider flows به‌خوبی جواب می‌دهد
- دامنه را به salon محدود نمی‌کند
- در sender naming و touchpointهای رسمی، تمیز و حرفه‌ای دیده می‌شود

### حس منتقل‌شده
- trusted
- calm
- refined
- local-ready
- product-ready

---

## 4) Subdomain Architecture

### Required

#### `www.loomera.ir`
**کاربرد:** سایت اصلی برند، landingها، صفحات معرفی، SEO، صفحات public  
**logic:** canonical public website  
**نوع:** public  
**وضعیت:** required

#### `app.loomera.ir`
**کاربرد:** محصول اصلی، رزرو، ورود، حساب کاربری، نوبت‌ها، پرداخت، dashboard  
**logic:** جداسازی روشن بین marketing و product  
**نوع:** public authenticated  
**وضعیت:** required

#### `help.loomera.ir`
**کاربرد:** help center، FAQ، راهنما، درخواست پشتیبانی، policy navigation  
**logic:** برای کاربر فارسی‌زبان humanتر و واضح‌تر از `support.` است  
**نوع:** public  
**وضعیت:** required

#### `business.loomera.ir`
**کاربرد:** onboarding و acquisition برای مراکز، کلینیک‌ها، استودیوها، سالن‌ها و ارائه‌دهندگان  
**logic:** broad و future-proof؛ بهتر از `salons.` یا `clinics.` به‌عنوان canonical  
**نوع:** public  
**وضعیت:** required

### Recommended

#### `status.loomera.ir`
**کاربرد:** اعلام اختلال، وضعیت سرویس، maintenance، payment/booking incident pages  
**logic:** trust-building operational surface  
**نوع:** public  
**وضعیت:** recommended

### Optional

#### `api.loomera.ir`
**کاربرد:** API عمومی یا partner integrations  
**نوع:** public controlled  
**وضعیت:** optional

#### `admin.loomera.ir`
**کاربرد:** پنل داخلی ادمین یا ops  
**نوع:** internal/restricted  
**وضعیت:** optional

#### `assets.loomera.ir`
**کاربرد:** CDN / static assets  
**نوع:** infra/public  
**وضعیت:** optional

#### `notify.loomera.ir`
**کاربرد:** زیرساخت ارسال ایمیل‌های تراکنشی در scale بالاتر  
**نوع:** infra  
**وضعیت:** optional-now / recommended-later

### Booking links
برای شروع، booking links بهتر است **path-based** باشند، نه provider subdomain-based.  
پیشنهاد:
- `app.loomera.ir/book/...`
- `loomera.ir/p/...`

این ساختار ساده‌تر، قابل‌مدیریت‌تر و scalableتر است.

---

## 5) Brand Email Architecture

### A. Core Brand Emails

#### `support@loomera.ir`
**کاربرد:** inbox اصلی پشتیبانی کاربران  
**tone implication:** calm, practical, accountable  
**نوع:** public-facing  
**وضعیت:** **recommended**

#### `bookings@loomera.ir`
**کاربرد:** ثبت نوبت، تغییر نوبت، یادآوری، لغو، مسائل رزرو  
**tone implication:** precise, reassuring, status-led  
**نوع:** public-facing / transactional  
**وضعیت:** **recommended**

#### `billing@loomera.ir`
**کاربرد:** رسید، پرداخت، بازگشت وجه، خطاهای مالی، invoice-like notices  
**tone implication:** exact, clear, trustworthy  
**نوع:** public-facing / transactional  
**وضعیت:** **recommended**

#### `privacy@loomera.ir`
**کاربرد:** درخواست‌های حریم خصوصی، حذف یا دریافت داده، consent-related inquiries  
**tone implication:** formal but readable  
**نوع:** public-facing  
**وضعیت:** **recommended**

#### `legal@loomera.ir`
**کاربرد:** مسائل حقوقی، notices، قراردادها، legal correspondence  
**tone implication:** formal, exact  
**نوع:** public-facing  
**وضعیت:** **recommended**

#### `partnerships@loomera.ir`
**کاربرد:** همکاری تجاری، affiliate، partnership، strategic outreach  
**tone implication:** structured, polished  
**نوع:** public-facing  
**وضعیت:** **recommended**

#### `providers@loomera.ir`
**کاربرد:** onboarding و ارتباط با ارائه‌دهندگان خدمات  
**tone implication:** commercially confident, operational, clear  
**نوع:** public-facing  
**وضعیت:** **recommended**

#### `auth@loomera.ir`
**کاربرد:** OTP، login verification، account access mail  
**tone implication:** short, secure, clear  
**نوع:** transactional  
**وضعیت:** **recommended**

#### `notifications@loomera.ir`
**کاربرد:** notificationهای عمومی و تراکنشی  
**tone implication:** concise, status-led  
**نوع:** outbound / controlled  
**وضعیت:** **recommended**

#### `no-reply@loomera.ir`
**کاربرد:** fallback sender برای mailهای non-conversational  
**tone implication:** system-only  
**نوع:** outbound  
**وضعیت:** **recommended as fallback**

### B. Useful Secondary Emails

#### `hello@loomera.ir`
**کاربرد:** تماس عمومی نرم‌تر، پیام‌های اولیه، برخی touchpointهای brand  
**tone implication:** warm, polished  
**نوع:** public-facing  
**وضعیت:** optional

#### `care@loomera.ir`
**کاربرد:** customer care لایه‌ی گرم‌تر برای caseهای خاص  
**tone implication:** more attentive, more human  
**نوع:** public-facing  
**وضعیت:** optional  
**نکته:** canonical support inbox نباشد

#### `security@loomera.ir`
**کاربرد:** امنیت حساب، disclosure، suspicious activity  
**tone implication:** serious, calm, exact  
**نوع:** public-facing  
**وضعیت:** optional-now / recommended-later

#### `press@loomera.ir`
**کاربرد:** رسانه و روابط عمومی  
**نوع:** public-facing  
**وضعیت:** optional

#### `careers@loomera.ir`
**کاربرد:** استخدام  
**نوع:** public-facing  
**وضعیت:** optional

### C. Functional/Internal Emails

#### `ops@loomera.ir`
برای coordinationهای عملیاتی  
**وضعیت:** optional

#### `finance@loomera.ir`
برای coordination مالی داخلی/نیمه‌خارجی  
**وضعیت:** optional-now / recommended-later

#### `compliance@loomera.ir`
برای compliance، policy review و regulated partner matters  
**وضعیت:** optional-now / recommended-later

---

## 6) Sender Name System

برای بازار ایران، بهتر است **local-partها انگلیسی و ساده** بمانند، اما sender nameها فارسی‌دوست و brand-consistent باشند. این کار هم از نظر usability بهتر است، هم با tone نیمه‌رسمی و human-first Loomera سازگارتر است. همچنین چون email در UI فارسی باید LTR نمایش داده شود، local-partهای کوتاه و واضح ترجیح دارند.

### Sender names نهایی

- **Loomera**  
  برای: announcementهای عمومی، onboardingهای سبک، updateهای برند، notificationهای عمومی

- **پشتیبانی Loomera**  
  برای: پاسخ‌های support، escalationها، help center follow-up

- **رزرو Loomera**  
  برای: booking confirmation، reminder، reschedule، cancellation

- **مالی Loomera**  
  برای: receipt، payment issue، refund، billing notice

- **امنیت Loomera**  
  برای: OTP، login verification، account alerts، suspicious activity

- **حریم خصوصی Loomera**  
  برای: privacy/data handling requests

- **حقوقی Loomera**  
  برای: legal notices و correspondence رسمی

- **همکاری با Loomera**  
  برای: partnership outreach، affiliate، business development

- **ارائه‌دهندگان Loomera**  
  برای: provider onboarding، listing review، operational coordination

- **Loomera**  
  برای: notificationهای عمومی که نیاز به function-specific sender ندارند

---

## 7) Email Use-Case Mapping

### signup / OTP
- **email:** `auth@loomera.ir`
- **sender:** `امنیت Loomera`
- **tone:** short, clear, secure

### booking confirmation
- **email:** `bookings@loomera.ir`
- **sender:** `رزرو Loomera`
- **tone:** precise, reassuring, status-led

### booking reminder
- **email:** `bookings@loomera.ir`
- **sender:** `رزرو Loomera`
- **tone:** concise, respectful, non-pushy

### payment receipt
- **email:** `billing@loomera.ir`
- **sender:** `مالی Loomera`
- **tone:** exact, calm

### payment issue
- **email:** `billing@loomera.ir`
- **sender:** `مالی Loomera`
- **tone:** explanatory, reassuring, non-blaming

### refund notice
- **email:** `billing@loomera.ir`
- **sender:** `مالی Loomera`
- **tone:** precise, accountable

### support reply
- **email:** `support@loomera.ir`
- **sender:** `پشتیبانی Loomera`
- **tone:** empathetic, practical, calm

### help center escalation
- **email:** `support@loomera.ir`
- **sender:** `پشتیبانی Loomera`
- **tone:** accountable, clear

### provider onboarding
- **email:** `providers@loomera.ir`
- **sender:** `ارائه‌دهندگان Loomera`
- **tone:** structured, operational, welcoming

### partner outreach
- **email:** `partnerships@loomera.ir`
- **sender:** `همکاری با Loomera`
- **tone:** polished, commercially confident

### press contact
- **email:** `press@loomera.ir`
- **sender:** `Loomera`
- **tone:** formal, brand-safe

### legal/privacy request
- **email:** `privacy@loomera.ir` / `legal@loomera.ir`
- **sender:** `حریم خصوصی Loomera` / `حقوقی Loomera`
- **tone:** formal, readable, exact

### account security alert
- **email:** `security@loomera.ir` یا `auth@loomera.ir`
- **sender:** `امنیت Loomera`
- **tone:** serious, calm, direct

### newsletter / product updates
- **email:** `hello@loomera.ir`
- **sender:** `Loomera`
- **tone:** refined, warm, concise

---

## 8) Naming Rules

1. **همه‌ی email local-partها lowercase و ساده باشند.**  
   مثل `support`, `bookings`, `billing`.

2. **برای mailboxهای اصلی از hyphen استفاده نشود.**  
   تنها استثنای مجاز: `no-reply`.

3. **local-partها کوتاه بمانند.**  
   mailboxهای طولانی و noisy ساخته نشوند.

4. **برای inboxهای shared از role-based naming استفاده شود.**  
   `support@` بهتر از inboxهای شخصی برای touchpointهای اصلی است.

5. **`support@` inbox اصلی باشد، نه `care@`.**  
   `care@` فقط alias یا لایه‌ی secondary باشد.

6. **`providers@` canonical باشد، نه `salons@` یا `clinics@`.**  
   چون scope برند broader از salon-only است.

7. **sender names یک الگوی ثابت داشته باشند.**  
   یا `Loomera`  
   یا `[Function] Loomera`

8. **marketing و transactional reputation در scale بالاتر از هم جدا شوند.**

9. **email addressها در UI فارسی به‌صورت LTR نمایش داده شوند.**  
   این برای readability و consistency ضروری است.

10. **از namingهای overly corporate یا generic اجتناب شود.**  
   mailbox باید روشن، human و operationally usable باشد، نه مبهم یا سرد.

---

## 9) Recommended Final Set

### Minimal viable set

#### Domains
- `loomera.ir`
- `www.loomera.ir`
- `app.loomera.ir`
- `help.loomera.ir`
- `business.loomera.ir`
- `status.loomera.ir`

#### Emails
- `support@loomera.ir`
- `bookings@loomera.ir`
- `billing@loomera.ir`
- `privacy@loomera.ir`
- `legal@loomera.ir`
- `partnerships@loomera.ir`
- `providers@loomera.ir`
- `auth@loomera.ir`
- `notifications@loomera.ir`
- `no-reply@loomera.ir`

#### Sender names
- `Loomera`
- `پشتیبانی Loomera`
- `رزرو Loomera`
- `مالی Loomera`
- `امنیت Loomera`
- `حریم خصوصی Loomera`
- `حقوقی Loomera`
- `همکاری با Loomera`
- `ارائه‌دهندگان Loomera`

### Growth-ready extended set

#### Additional domains
- `api.loomera.ir`
- `admin.loomera.ir`
- `assets.loomera.ir`
- `notify.loomera.ir`

#### Additional emails
- `hello@loomera.ir`
- `care@loomera.ir`
- `security@loomera.ir`
- `press@loomera.ir`
- `careers@loomera.ir`
- `ops@loomera.ir`
- `finance@loomera.ir`
- `compliance@loomera.ir`

---

## 10) Optional Technical Guidance

- برای شروع، visible emailها می‌توانند همگی روی `@loomera.ir` باشند.
- در scale بالاتر، بهتر است transactional sending reputation از newsletter/marketing جدا شود.
- اگر ارسال تراکنشی زیاد شد، می‌توان از `notify.loomera.ir` برای infrastructure استفاده کرد.
- `help.loomera.ir` برای user-facing support مناسب‌تر از `support.loomera.ir` است.
- `status.loomera.ir` برای trust و incident communication ارزش بالایی دارد.
- `mail.` و `notify.` بیشتر technical-layer هستند و نباید جایگزین visible brand addressها شوند.

---

## 11) Brand Fit Check

این architecture با هویت Loomera align است چون:
- brand-led و calm است
- clarity و trust را در naming حفظ می‌کند
- بیش از حد corporate یا noisy نیست
- برای product, support, booking, billing و provider ops usable است
- برند را به salon-only محدود نمی‌کند
- با voice ruleهای clarify > reassure > guide و toneهای status-led / empathetic / respectful سازگار است

---

## 12) Summary-ready Version for `docs/brand` or `docs/ops`

**Loomera should use `loomera.ir` as its single primary domain for the Iranian market.**  
Canonical public and product domains should be `www.loomera.ir` and `app.loomera.ir`, with `help.loomera.ir` for help/support content, `business.loomera.ir` for provider acquisition and onboarding, and `status.loomera.ir` for service health communication.

The canonical public email set should be:  
`support@loomera.ir`, `bookings@loomera.ir`, `billing@loomera.ir`, `privacy@loomera.ir`, `legal@loomera.ir`, `partnerships@loomera.ir`, `providers@loomera.ir`, `auth@loomera.ir`, `notifications@loomera.ir`, and `no-reply@loomera.ir`.

Canonical sender names should be:  
`Loomera`, `پشتیبانی Loomera`, `رزرو Loomera`, `مالی Loomera`, `امنیت Loomera`, `حریم خصوصی Loomera`, `حقوقی Loomera`, `همکاری با Loomera`, and `ارائه‌دهندگان Loomera`.

This system is designed to keep Loomera calm, trusted, refined, and operationally clear across booking, payment, support, provider onboarding, and legal/privacy touchpoints, while staying consistent with the brand’s broader beauty, aesthetic treatments, massage, and wellness scope.
