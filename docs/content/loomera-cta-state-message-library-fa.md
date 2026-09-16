# Loomera CTA & State Message Library
نسخه: 1.0  
وضعیت: source-ready / handoff-ready  
زبان پایه: فارسی (RTL)  
Companion labels: EN فقط در صورت نیاز فنی یا analytics key  
برند: Loomera

---

## 1) Source Review Summary

بررسی ZIP برند (`files.zip`) و سورس پروژه (`loomera.zip`) نشان می‌دهد که Loomera در اسناد مرجع خود—به‌ویژه **Brand Voice Guide**، **Microcopy System**، **Core Copy Pack**، **Mini Brand Guideline**، **Checkout Branding Kit**، **Dashboard Visual Kit**، **Empty State Illustration System**، **Notification / Email Visual Header System** و **Support Handoff**—بر یک هویت ثابت تکیه دارد:

- **calm confidence**: اقدام را روشن می‌کند، اما کاربر را هل نمی‌دهد.
- **premium by restraint**: premium بودن از دقت، سکون و وضوح می‌آید؛ نه از اغراق.
- **clarity as care**: روشن‌بودن متن بخشی از مراقبت از کاربر است.
- **reassure before persuade**: مخصوصاً در booking، payment، auth و support.
- **human-first, never robotic**: حتی پیام‌های سیستمی باید برای انسان نوشته شوند.

از review templateهای واقعی محصول—از جمله `templates/orders/checkout.html`، `templates/payments/appointment_result.html`، `templates/accounts/login.html`، `templates/accounts/verify.html`، `templates/search/search_results.html`، `templates/components/appointments_empty_state.html` و `templates/main/support/contact_form.html`—این جهت‌گیری عملیاتی تأیید شد:

- CTAهای خوب Loomera کوتاه، **action-led** و outcome-aware هستند:  
  `مشاهده جزئیات`، `پاک کردن فیلترها`، `تأیید و ادامه`
- State messageهای خوب Loomera **state-led** و non-dramatic هستند:  
  `نتیجه‌ای با این فیلترها پیدا نشد`، `پرداخت لغو شد`، `کد فقط تا ... دقیقه معتبر است`
- در checkout و payment، tone باید **high precision + reassurance** داشته باشد.
- در dashboard و empty states، tone باید **utility-first + blame-free** بماند.
- در support، tone باید **accountable, empathetic, practical** باشد.

### Constraintsی که باید رعایت شوند
1. زبان فارسی و UI راست‌چین است.
2. CTAها باید کوتاه و ترجیحاً فعل‌محور باشند.
3. state messageها باید یا minimal بمانند یا ساختار `چه شد + اثر آن + قدم بعدی` را رعایت کنند.
4. در payment، booking، auth و support، اطمینان‌بخشی باید explicit باشد.
5. از beauty clichés، urgency theater، لحن فروش‌محور و wordingهای generic باید پرهیز شود.
6. بین CTA، badge، helper text، alert، empty state، confirmation و notification باید مرز روشن وجود داشته باشد.

---

## 2) System Principles

### 1. Action باید روشن باشد، نه پرزرق‌وبرق
CTA باید دقیقاً بگوید کاربر با کلیک چه می‌کند.  
**Preferred:** `رزرو نوبت`  
**Avoid:** `شروع تجربه`

### 2. هر پیام باید اصطکاک را کم کند
هر state line باید یا clarify کند، یا reassure، یا guide.

### 3. در لحظه‌های حساس، اول uncertainty را کم کن
در payment، OTP، booking failure، cancellation و support:
- اول state را بگو
- بعد impact را روشن کن
- سپس next step را بده

### 4. Premium از کنترل می‌آید، نه از تزئین
کلمات باید polished باشند، نه نمایشی.

### 5. پیام‌ها باید انسانی باشند، نه process-facing
**Preferred:** `پرداخت تأیید نشد. اگر مبلغی از حسابت کم شده یا نتیجه نامشخص است، دوباره پرداخت نکن و وضعیت همان تراکنش را پیگیری کن.`  
**Avoid:** `Transaction failed due to processing error.`

### 6. Empty state نباید کاربر را مقصر نشان دهد
Empty state باید blame-free، hopeful و action-supportive باشد.

### 7. CTAهای discovery باید gentle-direct باشند
دعوت به بررسی، مقایسه و مشاهده؛ نه فشار برای اقدام فوری.

### 8. CTAهای transactional باید explicit باشند
در checkout، destructive action، security و payment ambiguity جایز نیست.

### 9. Error copy باید recoverable باشد
اگر امکان بازیابی وجود دارد، حتماً action path بده:
- دوباره تلاش کنید
- روش دیگری را انتخاب کنید
- با پشتیبانی تماس بگیرید

### 10. Reassurance باید کوتاه و معتبر باشد
اطمینان‌بخشی نباید marketing copy شود.  
**Preferred:** `مبلغ نهایی پیش از پرداخت نمایش داده می‌شود.`

### 11. State labelها باید scan-friendly باشند
برچسب‌ها باید کوتاه، پایدار و بدون نوسان واژگانی باشند.

### 12. Support tone باید مسئولانه و همراه باشد
نه بیش‌ازحد عذرخواهانه، نه خشک و اداری.

---

## 3) CTA Taxonomy

### A. Primary CTA
- **نقش:** اقدام اصلی صفحه یا flow
- **tone:** direct, calm, confident
- **length:** 1 تا 4 واژه
- **preferred verb style:** فعل + مفعول
- **avoid:** wording مبهم، شعاری، هیجانی
- **نمونه:** `رزرو نوبت`، `تأیید و ادامه`

### B. Secondary CTA
- **نقش:** مسیر جایگزین یا کم‌ریسک
- **tone:** respectful, low-pressure
- **length:** 1 تا 4 واژه
- **preferred verb style:** مشاهده / بازگشت / ویرایش / بعداً
- **avoid:** رقابت با CTA اصلی
- **نمونه:** `بازگشت`، `ویرایش زمان`

### C. Supportive CTA
- **نقش:** رفع ابهام یا ایجاد اعتماد
- **tone:** helpful, light
- **length:** 2 تا 5 واژه
- **preferred verb style:** `بیشتر بدانید`، `تماس با پشتیبانی`
- **avoid:** نمایش بیش‌ازحد در surfaces شلوغ

### D. Discovery CTA
- **نقش:** explore، compare، review
- **tone:** soft-direct
- **length:** 2 تا 4 واژه
- **preferred verb style:** مشاهده / بررسی / مقایسه / فیلتر
- **avoid:** `همین حالا رزرو کن`

### E. Booking CTA
- **نقش:** حرکت کاربر در flow رزرو
- **tone:** guiding, clear
- **length:** 1 تا 4 واژه
- **preferred verb style:** انتخاب / ادامه / مرور / رزرو
- **avoid:** vague transition labels

### F. Checkout / Payment CTA
- **نقش:** مرور، پرداخت، نهایی‌سازی
- **tone:** precise, trust-building
- **length:** 2 تا 5 واژه
- **preferred verb style:** تأیید / پرداخت / ثبت / بازگشت
- **avoid:** playful wording

### G. Account / Settings CTA
- **نقش:** مدیریت حساب، ذخیره‌سازی، به‌روزرسانی
- **tone:** practical
- **length:** 2 تا 4 واژه
- **preferred verb style:** ذخیره / ویرایش / افزودن / مدیریت
- **avoid:** vague nouns

### H. Provider / Partner CTA
- **نقش:** onboarding و collaboration
- **tone:** structured, composed
- **length:** 2 تا 4 واژه
- **preferred verb style:** شروع / ثبت / مشاهده / درخواست
- **avoid:** sales-heavy phrasing

### I. Modal / Alert CTA
- **نقش:** تصمیم قطعی، پرخطر یا برگشت‌ناپذیر
- **tone:** explicit, unambiguous
- **length:** 1 تا 4 واژه
- **preferred verb style:** حذف / لغو / خروج / ادامه
- **avoid:** نرم‌کردن بیش‌ازحد action خطرناک

### J. Empty State CTA
- **نقش:** خروج کاربر از بن‌بست
- **tone:** helpful, low-pressure
- **length:** 2 تا 4 واژه
- **preferred verb style:** مشاهده / تغییر / جست‌وجوی جدید / افزودن
- **avoid:** CTAهای generic مثل `شروع`

---

## 4) State Message Taxonomy

| Family | هدف | Emotional tone | Structure | Max length | CTA companion |
|---|---|---|---|---|---|
| Success | تثبیت نتیجه | calm, affirmative | state + useful next detail | title: 2–6 words / body: 1 sentence | اختیاری |
| Info | توضیح context | neutral, useful | what is true now | 1 sentence | گاهی |
| Warning | جلب توجه بدون alarm | steady, cautionary | risk + implication + option | 1–2 sentences | بله |
| Error | توضیح failure و recovery | accountable, clear | what happened + impact + next step | 1–2 sentences | بله |
| Pending / Processing | کاهش اضطراب انتظار | calm, transparent | current process + optional note | 1 sentence | گاهی |
| Empty | خروج از بن‌بست | neutral-positive | what is absent + what to do | 1–2 sentences | بله |
| Confirmation | تأیید تصمیم | explicit, respectful | decision + consequence | 1–2 sentences | بله |
| Recovery / Retry | بازگرداندن flow | practical, encouraging | issue + retry path | 1 sentence | بله |
| Locked / Restricted | توضیح محدودیت | firm, respectful | why unavailable + allowed path | 1 sentence | بله |
| Help / Guidance | راهنمایی | supportive, concise | what helps | 1 sentence | اختیاری |
| Validation | اصلاح ورودی | direct, non-blaming | field issue + constraint | 3–10 words | نه، مگر global form state |
| Neutral system state | اطلاع وضعیت سیستم | factual, low-noise | current system state | 1 sentence | معمولاً نه |

---

## 5) CTA Style Rules

### Case و فرم
- در فارسی، **sentence-style UI copy** استفاده شود، نه title case انگلیسی.
- CTA ترجیحاً با فعل شروع شود.
- فرم غالب: `فعل + مفعول`
- در CTAهای ثانویه کوتاه، `بازگشت`، `انصراف`، `ادامه` مجاز است.

### درجه‌ی امر
- **Primary transactional:** direct
- **Discovery:** soft-direct
- **Sensitive / safe actions:** direct but respectful
- **Help CTA:** inviting, not needy
- **Retry CTA:** practical, not dramatic

### طول پیشنهادی
- ایده‌آل: 1 تا 3 واژه
- قابل‌قبول: تا 5 واژه
- بیش از 5 واژه فقط برای CTAهای partner یا legal-heavy context

### CTA style by context
- **Discovery CTA:** `مشاهده جزئیات`، `بررسی زمان‌ها`
- **Transactional CTA:** `پرداخت و ثبت نهایی`
- **Sensitive CTA:** `لغو رزرو`
- **Retry CTA:** `دوباره تلاش می‌کنم`
- **Help CTA:** `تماس با پشتیبانی`

### Verbهای preferred
- مشاهده
- بررسی
- انتخاب
- ادامه
- تأیید
- تکمیل
- ثبت
- ذخیره
- تغییر
- افزودن
- مدیریت
- پیگیری
- تماس
- بازگشت
- تلاش دوباره

### Verbهای avoid
- شروع تجربه
- کشف کن
- از دست نده
- شگفت‌زده شو
- بزن بریم
- امتحانش کن
- فعال‌سازی جادویی
- نجات بده
- رزرو کن الآن

### فرمت CTAهای Loomera
1. دقیق
2. کوتاه
3. بی‌ابهام
4. بدون علامت تعجب
5. بدون قیدهای تبلیغاتی مثل `همین حالا`
6. بدون promise مبهم

---

## 6) State Message Style Rules

### Title structure
- title باید state-led باشد:
  - `پرداخت کامل نشد`
  - `نوبت شما ثبت شد`
  - `هنوز اعلانی ندارید`

### Body structure
در صورت نیاز:
1. **چه شد**
2. **چرا مهم است / اثر آن چیست**
3. **قدم بعدی چیست**

### Short vs Long
- **Short format:** toast، badge، inline state، small module  
  مثال: `تغییرات ذخیره شد.`
- **Long format:** payment result، modal، support status، security notice  
  مثال: `پرداخت تأیید نشد. اگر مبلغی از حسابت کم شده یا نتیجه نامشخص است، دوباره پرداخت نکن و وضعیت همان تراکنش را پیگیری کن.`

### Sequencing rule
- اول state
- بعد impact
- سپس recovery

### Reassurance level
- **Low:** dashboard/info/status label
- **Medium:** empty state / auth helper
- **High:** checkout / payment / OTP / support / cancellation

### When to include explanation
- payment
- booking failure
- session timeout
- security
- destructive actions
- stateهای غیرمنتظره

### When to stay minimal
- toast success
- badge
- inline save state
- list status labels
- predictable neutral states

### When to add support/help pathway
- اگر recovery path فوری روشن نیست
- اگر risk مالی یا زمانی وجود دارد
- اگر user action چند بار fail شده
- اگر access restriction user-specific است

---

## 7) Product Context Mapping

| Context | CTA style | State message style | Reassurance level | Directness |
|---|---|---|---|---|
| A. Search / Discovery | soft-direct, review-led | neutral + optional guidance | low-medium | نرم ولی روشن |
| B. Service / Provider Detail | review-led + booking-forward | clarity + trust hints | medium | نیمه‌مستقیم |
| C. Booking Flow | step-led, explicit | short guidance + confirmation | medium-high | مستقیم |
| D. Checkout / Payment | exact, transactional | state-led + impact + next step | high | مستقیم و بدون ابهام |
| E. Auth / OTP / Security | direct, low-noise | short, secure, reassuring | high | مستقیم |
| F. Account / Settings | practical | minimal success/error | low-medium | مستقیم |
| G. Dashboard | utility-first | concise, operational | low | مستقیم و کوتاه |
| H. Support / Help | respectful, human | accountable + practical | high | نرم-مستقیم |
| I. Notifications | short action یا no-action | status-led | medium | کوتاه |
| J. Provider / Partner Onboarding | structured, composed | explanatory but concise | medium | مستقیم کنترل‌شده |
| K. Empty States | unblock-focused | blame-free + next step | medium | gentle-direct |
| L. Modal / Alert / Destructive | explicit | consequence-led | high | بسیار مستقیم |

---

## 8) Booking & Checkout Messages

### Step CTA rules
- `انتخاب متخصص`
- `انتخاب زمان`
- `ادامه`
- `مرور رزرو`
- `تأیید و ادامه`

### Review CTA rules
- `تغییر زمان`
- `ویرایش خدمت`
- `بازگشت`
- `بررسی دوباره`

### Pay / Confirm CTA rules
- `پرداخت و ثبت نهایی`
- `تأیید و ثبت رزرو`
- `ادامه به پرداخت`

### Edit / Change CTA rules
- `تغییر زمان`
- `تغییر روش پرداخت`
- `ویرایش رزرو`

### Payment success
- **Title:** `پرداخت با موفقیت انجام شد`
- **Body:** `رزرو شما نهایی شد و جزئیات آن در بخش نوبت‌های من در دسترس است.`

### Payment failed
- **Title:** `پرداخت کامل نشد`
- **Body:** `پرداخت تأیید نشد. اگر مبلغی از حسابت کم شده یا نتیجه نامشخص است، دوباره پرداخت نکن و وضعیت همان تراکنش را پیگیری کن.`

### Cancelled payment
- **Title:** `پرداخت لغو شد`
- **Body:** `این پرداخت نهایی نشد. در صورت تمایل می‌توانید دوباره به مرحله پرداخت برگردید.`

### Refund
- **Title:** `بازگشت وجه انجام شد`
- **Body:** `مبلغ مربوطه طبق شرایط رزرو بازگردانده شد. جزئیات آن از همین بخش قابل بررسی است.`

### Booking confirmed
- **Title:** `نوبت شما ثبت شد`
- **Body:** `جزئیات رزرو در همین صفحه و در بخش نوبت‌های من در دسترس است.`

### Next-step guidance
- `پیش از پرداخت، لطفاً زمان، خدمت و مبلغ را یک‌بار دیگر بررسی کنید.`
- `در صورت نیاز، می‌توانید پیش از نهایی‌سازی زمان دیگری انتخاب کنید.`

### Booking / checkout hard rules
1. مبلغ و نتیجه همیشه باید explicit باشند.
2. برای failure مالی، impact باید روشن باشد.
3. نتیجه‌ی رزرو و نتیجه‌ی پرداخت نباید در یک جمله‌ی مبهم ادغام شوند.
4. در callback یا pending state باید از copy ضداضطراب استفاده شود.
5. در refund wording باید دقیق و non-defensive باشد.

---

## 9) Auth & Security Messages

### Login CTA
- `ورود`
- `ادامه`
- `دریافت کد`

### Signup CTA
- `شروع`
- `تکمیل اطلاعات`
- `ساخت حساب`

### Resend code CTA
- `ارسال دوباره کد`
- `دریافت کد جدید`

### Verification success
- `تأیید انجام شد. می‌توانید ادامه دهید.`

### Verification failure
- `کد واردشده درست نیست. لطفاً دوباره بررسی کنید.`

### Expired code
- `زمان کد به پایان رسیده است. کد جدید دریافت کنید.`

### Account protection messages
- `برای ادامه، لطفاً دوباره وارد شوید.`
- `برای حفظ امنیت حساب، این اقدام نیاز به تأیید دوباره دارد.`

### Password / reset-related
- `رمز عبور با موفقیت تغییر کرد.`
- `لینک بازیابی دیگر معتبر نیست. لطفاً دوباره درخواست دهید.`

### Suspicious activity tone
- direct, calm, non-alarmist
- مثال:
  - `فعالیت غیرعادی روی حساب شما شناسایی شد. برای ادامه، لطفاً دوباره وارد شوید.`
  - `برای حفظ امنیت حساب، این نشست پایان یافته است.`

---

## 10) Support & Help Messages

### Contact support CTA
- `تماس با پشتیبانی`
- `ثبت درخواست`

### Read help article CTA
- `مشاهده راهنما`
- `مطالعه مقاله`

### Submit request CTA
- `ارسال درخواست`
- `ثبت درخواست`

### Reply sent success
- `درخواست شما ثبت شد. نتیجه بررسی از همین بخش قابل پیگیری است.`

### Ticket update
- `پاسخ جدیدی برای درخواست شما ثبت شد.`

### No support requests yet
- `هنوز درخواستی ثبت نکرده‌اید.`

### Resolution pending
- `موضوع شما در حال بررسی است.`

### Escalation messaging
- `این موضوع برای بررسی دقیق‌تر به تیم مربوط ارجاع شد. نتیجه از همین مسیر اطلاع‌رسانی می‌شود.`

### Human reassurance tone
- warm but controlled
- helpful, never over-apologetic
- examples:
  - `جزئیات رزرو را بررسی کردیم.`
  - `اگر هنوز نیاز به راهنمایی دارید، از همین مسیر پاسخ دهید.`

---

## 11) Empty & No-Data Messages

| State | Title direction | Body direction | CTA direction | Optimism level |
|---|---|---|---|---|
| No results | نتیجه پیدا نشد | تغییر جست‌وجو یا فیلتر | `تغییر فیلترها` / `جست‌وجوی جدید` | neutral-positive |
| No bookings | هنوز نوبتی ندارید | رزرو اول را معرفی کن | `مشاهده خدمات` | positive |
| No availability | زمانی در دسترس نیست | گزینه دیگر پیشنهاد کن | `مشاهده زمان‌های دیگر` | neutral |
| No notifications | هنوز اعلانی ندارید | بگو چه چیزهایی اینجا می‌آیند | `بازگشت` | neutral |
| No favorites | هنوز موردی ذخیره نکرده‌اید | invite to explore | `مشاهده خدمات` | positive |
| No payment methods | هنوز روشی اضافه نکرده‌اید | explain benefit | `افزودن روش پرداخت` | neutral |
| No services | هنوز خدمتی ثبت نشده است | context-aware | `بازگشت` / `افزودن خدمت` | neutral |
| No gallery/media | هنوز تصویری برای نمایش وجود ندارد | utility explanation | `بازگشت` | neutral |
| No dashboard data | هنوز داده‌ای برای نمایش وجود ندارد | explain when it appears | `بازگشت به داشبورد` | neutral |
| First-time account | خوش آمدید | orientation + next step | `تکمیل حساب` / `شروع رزرو` | warm-positive |

### Direction rules
- title کوتاه، بدون استعاره
- body فقط یک قدم بعدی را روشن کند
- artwork یا illustration باید supportive باشد، نه dominant

---

## 12) Validation & Error Library

### Required field
- **Preferred:** `این فیلد را کامل کنید.`
- **Avoid:** `وارد کردن این قسمت الزامی می‌باشد.`

### Invalid phone / email
- `شماره موبایل را با فرمت درست وارد کنید.`
- `ایمیل را با فرمت درست وارد کنید.`

### Invalid payment input
- `اطلاعات پرداخت کامل نیست. لطفاً دوباره بررسی کنید.`

### Expired session
- `جلسه شما منقضی شده است. لطفاً دوباره وارد شوید.`

### Network issue
- `اتصال برقرار نشد. لطفاً چند لحظه دیگر دوباره تلاش کنید.`

### Retry suggestion
- `در حال حاضر انجام این کار ممکن نیست. لطفاً دوباره تلاش کنید.`

### Unavailable slot
- `این زمان دیگر در دسترس نیست. لطفاً زمان دیگری انتخاب کنید.`

### Duplicate action prevention
- `این درخواست قبلاً ثبت شده است. لطفاً وضعیت فعلی را بررسی کنید.`

### Save / update failed
- `امکان ذخیره تغییرات وجود نداشت. دوباره تلاش کنید.`

### Upload failed
- `بارگذاری فایل کامل نشد. لطفاً فایل دیگری انتخاب کنید یا دوباره تلاش کنید.`

### کوتاه‌ترین wordingهای product-ready
- `کامل نشد`
- `در دسترس نیست`
- `منقضی شده است`
- `معتبر نیست`
- `ثبت نشد`
- `ذخیره نشد`

### wordingهایی که باید avoid شوند
- `خطایی رخ داده است`
- `مشکلی پیش آمد`
- `عملیات ناموفق بود`
- `اطلاعات اشتباه است`  
- `درخواست شما قابل پردازش نمی‌باشد`

---

## 13) Labels, Chips & Status Badges

| Semantic | Label پیشنهادی | Tone | Compact form |
|---|---|---|---|
| confirmed | تأیید شد | confident | تأیید |
| pending | در انتظار | neutral-caution | انتظار |
| completed | انجام شد | final-positive | انجام |
| cancelled | لغو شد | neutral-final | لغو |
| failed | ناموفق | clear-negative | ناموفق |
| refunded | بازگشت وجه | precise | بازگشت |
| draft | پیش‌نویس | neutral | پیش‌نویس |
| unavailable | در دسترس نیست | factual | ناموجود |
| verified | تأییدشده | trust | تأییدشده |
| new | جدید | light-positive | جدید |
| popular | پرطرفدار | discovery cue | محبوب |
| premium | ویژه | refined | ویژه |
| needs attention | نیازمند اقدام | action cue | اقدام لازم |
| hidden | پنهان | neutral | پنهان |
| inactive | غیرفعال | neutral | غیرفعال |
| active | فعال | quiet-positive | فعال |

### Badge rules
- حداکثر 1 تا 2 واژه
- از تنوع واژگانی بی‌دلیل پرهیز شود
- `در حال انجام` و `در جریان` و `pending` برای یک مفهوم هم‌زمان استفاده نشود

---

## 14) CTA Library

### A. Discovery CTA
**Strong options**
1. ★ مشاهده جزئیات
2. ★ بررسی خدمات
3. ★ بررسی زمان‌ها
4. ★ تغییر فیلترها
5. ★ جست‌وجوی جدید
6. مشاهده متخصص‌ها
7. دیدن همه خدمات
8. مقایسه گزینه‌ها
9. بررسی این مرکز
10. مشاهده نزدیک‌ترین‌ها

**Weaker / avoid**
- همین حالا رزرو کن
- شروع تجربه
- کشف کن

### B. Booking CTA
**Strong options**
1. ★ رزرو نوبت
2. ★ انتخاب زمان
3. ★ انتخاب متخصص
4. ★ ادامه
5. ★ مرور رزرو
6. تأیید و ادامه
7. ثبت رزرو
8. بررسی جزئیات رزرو
9. تغییر زمان
10. بازگشت به خدمات

**Weaker / avoid**
- برو مرحله بعد
- نهایی‌سازی جادویی
- بزن بریم

### C. Checkout CTA
**Strong options**
1. ★ پرداخت و ثبت نهایی
2. ★ تأیید و ادامه
3. ★ ادامه به پرداخت
4. ★ انتخاب روش پرداخت
5. ★ بررسی دوباره
6. ویرایش رزرو
7. تغییر روش پرداخت
8. بازگشت به رزرو
9. اعمال تخفیف
10. حذف کد

**Weaker / avoid**
- خرید
- ادامه خرید
- پرداخت کن

### D. Account CTA
**Strong options**
1. ★ ذخیره تغییرات
2. ★ ویرایش اطلاعات
3. ★ تکمیل حساب
4. افزودن روش پرداخت
5. مدیریت اعلان‌ها
6. به‌روزرسانی شماره تماس
7. تغییر رمز عبور
8. ذخیره تنظیمات
9. مشاهده نوبت‌ها
10. خروج از حساب

**Weaker / avoid**
- ثبت
- انجامش بده
- فعال‌سازی

### E. Support CTA
**Strong options**
1. ★ تماس با پشتیبانی
2. ★ ثبت درخواست
3. ★ مشاهده راهنما
4. ★ پیگیری درخواست
5. ارسال پاسخ
6. دیدن مقاله مرتبط
7. مشاهده وضعیت درخواست
8. بازگشت به پشتیبانی
9. ارسال دوباره درخواست
10. بررسی پاسخ‌ها

**Weaker / avoid**
- کمک!
- گزارش مشکل
- تماس فوری

### F. Empty State CTA
**Strong options**
1. ★ مشاهده خدمات
2. ★ تغییر فیلترها
3. ★ جست‌وجوی جدید
4. ★ بازگشت
5. ★ افزودن روش پرداخت
6. بررسی زمان‌های دیگر
7. شروع رزرو
8. دیدن مراکز
9. تکمیل حساب
10. تماس با پشتیبانی

**Weaker / avoid**
- شروع
- ادامه
- امتحان کن

### G. Retry / Recovery CTA
**Strong options**
1. ★ دوباره تلاش می‌کنم
2. ★ تلاش دوباره
3. ★ بررسی دوباره
4. ★ ورود دوباره
5. ★ دریافت کد جدید
6. انتخاب روش دیگر
7. بازگشت به رزرو
8. بارگذاری دوباره
9. بررسی وضعیت
10. ادامه از ابتدا

**Weaker / avoid**
- امتحان مجدد
- حلش کن
- دوباره بزن

### H. Destructive Actions CTA
**Strong options**
1. ★ لغو رزرو
2. ★ حذف
3. ★ خروج بدون ذخیره
4. ★ حذف روش پرداخت
5. ★ بستن حساب
6. ادامه لغو
7. تأیید حذف
8. انصراف
9. بازگشت
10. حذف تصویر

**Weaker / avoid**
- مطمئنم
- پاکش کن
- نابودش کن

### I. Provider / Partner CTA
**Strong options**
1. ★ درخواست همکاری
2. ★ مشاهده امکانات
3. ★ شروع ثبت سالن
4. ★ تکمیل پروفایل مرکز
5. ثبت خدمات
6. افزودن متخصص
7. مدیریت زمان‌ها
8. مشاهده داشبورد
9. ادامه ثبت‌نام
10. بررسی درخواست

**Weaker / avoid**
- جذب مشتری بیشتر
- رشد انفجاری
- شروع موفقیت

### J. Dashboard Quick Actions
**Strong options**
1. ★ مشاهده نوبت‌ها
2. ★ افزودن خدمت
3. ★ افزودن متخصص
4. ★ تنظیم زمان‌ها
5. ★ بررسی پرداخت‌ها
6. مشاهده گزارش‌ها
7. پیگیری درخواست‌ها
8. به‌روزرسانی پروفایل
9. دیدن اعلان‌ها
10. مدیریت تنظیمات

**Weaker / avoid**
- سریع‌تر شو
- مدیریت حرفه‌ای
- رشد بده

---

## 15) State Message Library

### A. Success messages
1. نوبت شما ثبت شد.
2. پرداخت با موفقیت انجام شد و رزرو شما نهایی شد.
3. تغییرات ذخیره شد.
4. روش پرداخت با موفقیت اضافه شد.
5. زمان نوبت به‌روزرسانی شد.
6. درخواست شما ثبت شد.
7. کد تأیید ارسال شد.
8. پروفایل شما کامل شد.
9. لینک با موفقیت کپی شد.
10. اعلان‌ها به‌روزرسانی شد.

### B. Warning messages
1. این زمان به‌سرعت در حال تکمیل است. بهتر است زودتر تصمیم بگیرید.
2. جلسه شما رو به پایان است. برای ادامه، دوباره وارد شوید.
3. این رزرو شامل شرایط لغو خاص است. لطفاً پیش از ادامه بررسی کنید.
4. موجودی کیف پول برای این پرداخت کافی نیست.
5. بعضی از اطلاعات واردشده هنوز ذخیره نشده است.
6. این کد تخفیف فقط برای برخی خدمات این رزرو اعمال می‌شود.
7. اگر این پرداخت را لغو کنید، رزرو نهایی نمی‌شود.
8. این فایل بزرگ‌تر از حد مجاز است.

### C. Error messages
1. اتصال برقرار نشد. لطفاً چند لحظه دیگر دوباره تلاش کنید.
2. پرداخت تأیید نشد. اگر مبلغی از حسابت کم شده یا نتیجه نامشخص است، دوباره پرداخت نکن و وضعیت همان تراکنش را پیگیری کن.
3. این زمان دیگر در دسترس نیست. لطفاً زمان دیگری انتخاب کنید.
4. ورود انجام نشد. لطفاً دوباره تلاش کنید.
5. امکان ذخیره تغییرات وجود نداشت. دوباره تلاش کنید.
6. کد واردشده معتبر نیست. لطفاً دوباره بررسی کنید.
7. بارگذاری فایل کامل نشد. لطفاً دوباره تلاش کنید.
8. دسترسی به این بخش برای شما فعال نیست.
9. امکان نهایی‌سازی این رزرو در حال حاضر وجود ندارد.
10. این پرداخت تأیید نشد. لطفاً روش دیگری را امتحان کنید.

### D. Pending messages
1. در حال آماده‌سازی زمان‌های در دسترس...
2. در حال بررسی پرداخت...
3. در حال انتقال به درگاه پرداخت...
4. در حال ثبت رزرو...
5. در حال بارگذاری اطلاعات...
6. درخواست شما در حال بررسی است.
7. در حال به‌روزرسانی تنظیمات...
8. در حال ارسال کد تأیید...

### E. Empty messages
1. نتیجه‌ای با این فیلترها پیدا نشد. می‌توانید جست‌وجو یا فیلترها را تغییر دهید.
2. هنوز نوبتی ثبت نکرده‌اید. خدمات را ببینید و زمان مناسب خود را انتخاب کنید.
3. در حال حاضر زمان خالی برای این گزینه موجود نیست. می‌توانید زمان یا متخصص دیگری را بررسی کنید.
4. هنوز اعلانی برای شما وجود ندارد.
5. هنوز درخواستی ثبت نکرده‌اید.
6. هنوز روشی برای پرداخت ذخیره نکرده‌اید.
7. هنوز موردی به علاقه‌مندی‌ها اضافه نکرده‌اید.
8. هنوز داده‌ای برای نمایش در این بخش وجود ندارد.

### F. Confirmation messages
1. آیا می‌خواهید این رزرو را لغو کنید؟ جزئیات شرایط لغو پیش از تأیید نمایش داده می‌شود.
2. آیا می‌خواهید این روش پرداخت را حذف کنید؟
3. اگر از این صفحه خارج شوید، تغییرات ثبت نخواهد شد.
4. آیا می‌خواهید این تصویر را حذف کنید؟
5. آیا از خروج از حساب مطمئن هستید؟
6. این اقدام قابل بازگشت نیست. ادامه می‌دهید؟
7. آیا می‌خواهید این درخواست را ببندید؟
8. آیا می‌خواهید زمان جدید را جایگزین زمان قبلی کنید؟

### G. Retry / recovery messages
1. دوباره تلاش کنید.
2. می‌توانید روش دیگری را انتخاب کنید.
3. لطفاً چند لحظه دیگر دوباره تلاش کنید.
4. برای ادامه، دوباره وارد شوید.
5. کد جدید دریافت کنید.
6. صفحه را یک‌بار دیگر بارگذاری کنید.
7. جزئیات را بررسی و دوباره تلاش کنید.
8. در صورت ادامه مشکل، با پشتیبانی تماس بگیرید.

### H. Informational messages
1. مبلغ نهایی پیش از پرداخت نمایش داده می‌شود.
2. جزئیات رزرو پیش از نهایی‌سازی دوباره نمایش داده می‌شود.
3. این اطلاعات فقط برای هماهنگی رزرو استفاده می‌شود.
4. اطلاع‌رسانی‌های مهم رزرو و پرداخت در این بخش نمایش داده می‌شود.
5. فقط زمان‌هایی نمایش داده می‌شود که در حال حاضر قابل رزرو هستند.
6. نتیجه بررسی از همین بخش قابل پیگیری است.
7. می‌توانید ترجیحات خود را بعداً هم تغییر دهید.
8. کد تأیید فقط تا چند دقیقه معتبر است.

### I. Validation messages
1. این فیلد را کامل کنید.
2. شماره موبایل را با فرمت درست وارد کنید.
3. ایمیل را با فرمت درست وارد کنید.
4. کد تأیید معتبر نیست.
5. رمز عبور باید حداقل ۸ کاراکتر باشد.
6. این مقدار از حد مجاز بیشتر است.
7. لطفاً یک روش پرداخت انتخاب کنید.
8. لطفاً زمان رزرو را انتخاب کنید.
9. فایل انتخاب‌شده پشتیبانی نمی‌شود.
10. توضیح کوتاه و روشن به بررسی سریع‌تر کمک می‌کند.

---

## 16) Vocabulary Rules

### Preferred words
- روشن
- جزئیات
- بررسی
- انتخاب
- زمان مناسب
- قابل رزرو
- نهایی
- پیگیری
- ذخیره
- به‌روزرسانی
- درخواست
- در دسترس
- نیازمند اقدام

### Safer alternatives
- به‌جای `مشکل` → `کامل نشد` / `ممکن نشد`
- به‌جای `اطلاعات اشتباه` → `فرمت درست وارد کنید`
- به‌جای `رد شد` → `تأیید نشد`
- به‌جای `با موفقیت کامل شد` → `انجام شد`

### Verbs to use often
- مشاهده
- بررسی
- انتخاب
- ادامه
- تأیید
- ثبت
- تکمیل
- تغییر
- ذخیره
- افزودن
- پیگیری

### Verbs to avoid
- کشف
- رها کن
- بزن
- شگفت‌زده شو
- فعال کن
- از دست نده
- بقاپ

### Phrases that feel too aggressive
- همین حالا
- از دست نده
- فقط چند ساعت باقی مانده
- فوری اقدام کن
- آخرین فرصت

### Phrases that feel too vague
- شروع
- ثبت
- ادامه فرآیند
- عملیات موفق
- مشکل پیش آمد

### Phrases that feel too salesy
- تجربه‌ای بی‌نظیر
- درخشش شما
- خاص‌ترین انتخاب
- رزرو رویایی
- لوکس‌ترین تجربه

### Phrases that feel too robotic
- درخواست شما با خطا مواجه گردید
- عملیات ناموفق بود
- اطلاعات معتبر نمی‌باشد
- این بخش برای شما مجاز نیست
- پردازش انجام نپذیرفت

---

## 17) Do / Don’t Guide

### Do
1. CTA را با فعل روشن شروع کنید.
2. در payment، outcome را دقیق بگویید.
3. اگر پول درگیر است، impact را explicit کنید.
4. برای error، recovery path بدهید.
5. در empty state، next step پیشنهاد دهید.
6. از واژه‌های آشنا و محترمانه استفاده کنید.
7. titleها را state-led بنویسید.
8. body را به یک ایده محدود کنید.
9. از consistency واژگانی محافظت کنید.
10. بین رزرو، پرداخت و حساب تمایز زبانی نگه دارید.
11. در support، مسئولانه و همدلانه بمانید.
12. در auth/security، مستقیم و کوتاه بنویسید.
13. در dashboard، utility-first بمانید.
14. در modalهای حساس، consequence را روشن کنید.
15. wording را قبل از انتشار در context واقعی UI تست کنید.

### Don’t
1. CTA را شعاری نکنید.
2. از beauty cliché استفاده نکنید.
3. کاربر را برای خطا سرزنش نکنید.
4. state labelها را بی‌دلیل تغییر ندهید.
5. از exclamation mark در product copy استفاده نکنید.
6. وعده‌ی مبهم ندهید.
7. body message را طولانی نکنید.
8. error را بدون action path رها نکنید.
9. success را بیش از حد celebratory نکنید.
10. payment و booking result را با هم قاطی نکنید.
11. از ترجمه‌های تحت‌اللفظی فنی استفاده نکنید.
12. در empty state کاربر را under-pressure نگذارید.
13. CTAهای destructive را soft و مبهم نکنید.
14. در dashboard از headlineهای marketing-style استفاده نکنید.
15. در security notice panic ایجاد نکنید.

---

## 18) Quality Checklist

قبل از approve هر CTA یا state message بررسی شود:

- آیا فوراً روشن است؟
- آیا دقیقاً معلوم است چه اتفاقی افتاده؟
- آیا قدم بعدی برای کاربر معلوم است؟
- آیا wording بیش از حد تبلیغاتی نیست؟
- آیا طول برای UI مناسب است؟
- آیا لحن calm و trusted باقی مانده؟
- آیا در لحظه حساس reassuring است؟
- آیا از واژگان approved استفاده می‌کند؟
- آیا با taxonomy درست map شده است؟
- آیا با context صفحه سازگار است؟
- آیا با برچسب‌ها و statusهای دیگر یکدست است؟
- آیا ambiguity مالی، زمانی یا امنیتی ندارد؟
- آیا در صورت failure مسیر recovery دارد؟
- آیا در صورت empty state مسیر خروج از بن‌بست دارد؟
- آیا در صورت destructive action consequence روشن است؟
- آیا در فارسی طبیعی و محترمانه است؟
- آیا از cliché و urgency theater دور است؟
- آیا با Brand Voice و Microcopy System هم‌راستاست؟

---

## 19) Implementation Notes

### Naming پیشنهادی برای library sections
- `cta.primary`
- `cta.secondary`
- `cta.discovery`
- `cta.booking`
- `cta.checkout`
- `cta.account`
- `cta.support`
- `cta.empty`
- `cta.retry`
- `cta.destructive`
- `cta.partner`
- `state.success`
- `state.info`
- `state.warning`
- `state.error`
- `state.pending`
- `state.empty`
- `state.confirmation`
- `state.recovery`
- `state.validation`
- `state.security`
- `state.support`
- `label.status`
- `badge.discovery`

### چه چیزهایی shared token-like باشند
- approved verbs
- approved status labels
- empty state patterns
- payment core messages
- auth / OTP core messages
- support response starters / closers
- destructive modal patterns

### چه چیزهایی per-context override شوند
- provider vs customer wording
- dashboard operational copy
- partner onboarding copy
- payment provider-specific helper text
- legal/policy-specific confirmations
- split booking / multi-day booking messaging

### اتصال به Microcopy System
این Library باید به‌عنوان **execution layer** روی Brand Voice و Microcopy System بنشیند:
- Brand Voice = tone constraints
- Microcopy System = pattern rules
- CTA & State Library = approved production strings + usage rules

### Suggested repo structure
```text
docs/
  content/
    loomera-cta-state-message-library-fa.md
    loomera-cta-state-summary-ready-fa.md
  design-system/
    loomera-copy-taxonomy.json
src/
  content/
    cta.ts
    states.ts
    labels.ts
    validation.ts
```

### Suggested key structure
```json
{
  "cta": {
    "discovery": {},
    "booking": {},
    "checkout": {},
    "account": {},
    "support": {},
    "empty": {},
    "retry": {},
    "destructive": {},
    "partner": {}
  },
  "state": {
    "success": {},
    "info": {},
    "warning": {},
    "error": {},
    "pending": {},
    "empty": {},
    "confirmation": {},
    "recovery": {},
    "validation": {},
    "security": {},
    "support": {}
  },
  "label": {
    "status": {},
    "badge": {}
  }
}
```

### Frontend behavior notes
- CTA keyها semantic باشند، نه page-specific مگر واقعاً لازم باشد.
- state messages باید title/body/action جداگانه داشته باشند.
- Validation messageها field-level و form-level از هم تفکیک شوند.
- payment result screen باید booking status و payment status را در keyهای مجزا نگه دارد.
- notification copy بهتر است template-based باشد.

### Source maintenance rule
- هر string جدید ابتدا باید به taxonomy map شود.
- aliasهای legacy باید حذف یا migrate شوند.
- هر context جدید قبل از ship باید با این checklist ارزیابی شود.

---

## 20) Final Recommendation

### سطح directness پیشنهادی CTA system
CTAهای Loomera باید **direct but calm** باشند:
- نه soft تا حد مبهم‌بودن
- نه direct تا حد فشار
- در discovery: gentle-direct
- در booking: clear-direct
- در checkout / destructive / security: explicit-direct

### میزان explanatory بودن state system
state messageها باید **selectively explanatory** باشند:
- در utility contextها minimal
- در contextهای مالی، زمانی، امنیتی و پشتیبانی explanatory
- توضیح اضافه فقط وقتی uncertainty یا risk واقعی وجود دارد

### tone نهایی در لحظه‌های product-critical
- calm
- exact
- reassuring
- responsible
- human
- quietly premium

### چرا این رویکرد برای Loomera بهتر جواب می‌دهد
1. در discovery، friction ذهنی را کم می‌کند.
2. در booking، تصمیم را روشن‌تر می‌کند.
3. در checkout، trust و completion rate را تقویت می‌کند.
4. در auth و support، اضطراب را کاهش می‌دهد.
5. در dashboard، maturity و consistency محصول را بالا می‌برد.
6. برای beauty + treatments + massage + wellness مناسب است، بدون افتادن در cliché.

---

## 21) Deliverables

این پکیج شامل این خروجی‌هاست:
1. system principles
2. CTA taxonomy
3. state message taxonomy
4. CTA style rules
5. state message style rules
6. context mapping
7. booking/checkout message rules
8. auth/security message rules
9. support/help message rules
10. empty-state message rules
11. validation/error library
12. labels/chips/status badges
13. CTA library
14. state message library
15. vocabulary rules
16. do/don’t guide
17. quality checklist
18. implementation notes
19. final recommendation
20. summary-ready version برای docs/content یا docs/design-system

---

## 22) Summary-ready Version for Docs / Design System

### Loomera CTA & State System — خلاصه اجرایی

**Tone core:** calm, trusted, refined, human  
**Primary writing goal:** clarity first, reassurance where needed, action without pressure

### Approved CTA direction
- کوتاه
- فعل‌محور
- direct but calm
- بدون urgency theater
- بدون beauty cliché

**Best patterns**
- `فعل + مفعول`
- `رزرو نوبت`
- `مشاهده جزئیات`
- `پرداخت و ثبت نهایی`
- `تماس با پشتیبانی`

### Approved state direction
- state-led
- blame-free
- impact-aware
- action-supportive

**Best patterns**
- success: `نوبت شما ثبت شد.`
- error: `پرداخت تأیید نشد. اگر مبلغی از حسابت کم شده یا نتیجه نامشخص است، دوباره پرداخت نکن و وضعیت همان تراکنش را پیگیری کن.`
- empty: `نتیجه‌ای با این فیلترها پیدا نشد. می‌توانید فیلترها را تغییر دهید.`

### Directness scale
- discovery: gentle-direct
- booking: direct
- checkout/security: explicit-direct
- support: warm-direct

### Mandatory rules
1. payment copy must be precise
2. empty states must offer a path
3. validation copy must be short and field-specific
4. destructive actions must be explicit
5. status labels must remain consistent

### Recommended core namespaces
- `cta.discovery`
- `cta.booking`
- `cta.checkout`
- `cta.account`
- `cta.support`
- `state.success`
- `state.error`
- `state.empty`
- `state.validation`
- `state.security`
- `label.status`

### North star
Loomera should help users make self-care decisions with less friction, more clarity, and more trust.
