# Loomera Checkout Branding Kit

نسخه: 1.0  
وضعیت: source-ready / handoff-ready  
برند: Loomera

---

## 1) Source Review Summary

از سورس Loomera این تصویر روشن به‌دست می‌آید: برند از نظر لحن باید **calm, refined, trustworthy, precise, human** باشد؛ از نظر بصری باید روی **violet-led palette** با neutralهای گرم، accent سبز کنترل‌شده و typography sans-led در UI تکیه کند؛ و از نظر حضور لوگو در shell باید **restrained** بماند و فقط در contextهای trust-led کمی پررنگ‌تر شود.

در review سورس فعلی checkout، ساختار پایه وجود دارد: هدر sticky، summary رزرو، payment method، cost summary، policy/reassurance block، sticky CTA و نتیجه‌ی پرداخت. اما brand layer هنوز کامل systematize نشده است. بنابراین این kit همان ساختار را حفظ می‌کند، اما آن را از نظر لوگو، رنگ، copy، hierarchy و state system یکدست می‌کند.

Tone دقیق checkout باید این باشد: **highly precise + explicit + easy to scan + reassuring without pressure**.

**تفاوت checkout با shellهای دیگر:**
- در dashboard حضور برند باید medium-low باشد.
- در checkout برند باید **visible but restrained** بماند.
- در checkout، Loomera باید بیشتر «platform trust layer» باشد تا «marketing brand layer».

**Constraintهای اصلی:**
- لوگو نباید با provider identity رقابت کند.
- primary CTA باید از token واقعی Loomera بیاید.
- متن‌ها باید کوتاه، واضح و status-led باشند.
- LTR data در RTL باید isolate شود.
- success / failed / cancelled / refund باید روشن و غیرهیجانی باشند.

---

## 2) Checkout Branding Strategy

### مدل تجربه‌ی checkout در Loomera

- **Brand presence level:** medium
- **Trust level:** high
- **Precision level:** very high
- **Emotional temperature:** low-to-warm
- **Visual restraint level:** high
- **Platform vs provider identity balance:** provider-first, platform-assuring

### تفسیر اجرایی

در checkout، Loomera نباید نقش «برند غالب» را بازی کند. کاربر در این لحظه در حال نهایی‌سازی رزروی برای یک **provider / center / specialist** مشخص است؛ پس هویت provider باید در summary و context اصلی زنده بماند.

نقش Loomera در checkout:
- مسیر را روشن کند
- امنیت و قطعیت فرایند را منتقل کند
- ambiguity را کم کند

### فرمول نهایی

**Provider identity for decision context + Loomera identity for trust context**

یعنی:
- کارت provider / specialist باید واقعی، readable و انسانی بماند.
- header برند باید کوتاه، تمیز و بدون رفتار تبلیغاتی باشد.
- reassurance و payment status باید بیشتر از لوگو اعتماد بسازند.
- logo usage باید کم‌تعداد اما دقیق باشد.

---

## 3) Checkout Logo Treatment

### قاعده‌ی اصلی

برای checkout، نسخه‌ی پیشنهادی **compact logo** است؛ نه full logo دائمی و نه glyph-only در desktop.

### Ruleها

- **Desktop / tablet:** `compact logo`
- **Trust-heavy confirmation header:** `compact logo` یا در success نهایی `full logo` یک‌بار
- **Mobile top header:** `glyph-only` یا compact minimal اگر title مستقل حذف شده باشد
- **Dark / tinted surfaces:** mostly single-tone / reduced-color
- **White / light shell:** monochrome deep violet یا restrained full-color
- **ممنوع:** لوگو داخل summary rows، payment method cards، CTA button، discount rows، error banners

### Placement

- محل درست لوگو: **بالای flow** و داخل یک trust header کوتاه
- alignment در RTL: **سمت راست**
- provider/service block باید پایین‌تر و مستقل بیاید
- لوگو نباید داخل sticky CTA تکرار شود

### Min / Max Size

- `checkout-brand-header`: عرض `132px – 156px`
- `checkout signature`: حداکثر `168px`
- `header logo height`: حدود `24px – 28px`
- `glyph mobile`: باکس `24px – 32px`

### Named Rules

#### `checkout-brand-header`
compact logo + یک reassurance line کوتاه. background شفاف یا very soft surface. border پایین بسیار ملایم. بدون shadow سنگین.

#### `payment-summary-brand-lockup`
اگر لازم باشد فقط در summary panel desktop استفاده شود؛ نه به شکل لوگوی کامل، بلکه glyph یا text label خیلی subtle مثل:
`پرداخت توسط Loomera پردازش می‌شود`

#### `confirmation-header-brand`
در success screen یک‌بار compact یا full logo مجاز است. در failed / cancelled بهتر است compact بماند.

#### `mobile-checkout-glyph`
فقط glyph، در باکس `28px – 32px`، بدون wordmark، با spacing پایدار و مستقل از title / action icons.

---

## 4) Checkout Layout Zones

### A. Trust Header
- **هدف:** orientation + trust cue
- **visual priority:** بالا
- **brand intensity:** medium
- **recommended components:** compact logo، title، one-line reassurance، back action
- **spacing direction:** `16–20px` top/bottom
- **content tone:** روشن، آرام، بدون marketing

### B. Booking / Service Summary
- **هدف:** تأیید چیزی که کاربر دارد می‌پردازد
- **visual priority:** very high
- **brand intensity:** low
- **recommended components:** service rows، duration، price، badgeهای محدود
- **spacing direction:** `16px` داخلی، `12px` بین rowها
- **content tone:** factual + scan-friendly

### C. Provider / Specialist Info
- **هدف:** حفظ context واقعی رزرو
- **visual priority:** high
- **brand intensity:** low
- **recommended components:** provider image/logo/initial، نام مرکز، آدرس کوتاه، specialist name
- **spacing direction:** `16–20px`
- **content tone:** factual, human, non-promotional

### D. Date & Time Review
- **هدف:** جلوگیری از ambiguity زمانی
- **visual priority:** high
- **brand intensity:** very low
- **recommended components:** date chips، time chips، helper note
- **spacing direction:** chip gap `8px`، block padding `16px`
- **content tone:** precise + confidence-building

### E. Payment Method Section
- **هدف:** تصمیم اصلی مالی
- **visual priority:** very high
- **brand intensity:** low-medium
- **recommended components:** selector cards، method note، wallet balance، gateway note
- **spacing direction:** `14–16px` بین options
- **content tone:** explicit, practical

### F. Price Breakdown
- **هدف:** readability مالی
- **visual priority:** very high
- **brand intensity:** low
- **recommended components:** subtotal، discounts، tax، total
- **spacing direction:** `10–12px` بین rows، `14px` قبل از total
- **content tone:** exact + clean

### G. Primary Action Zone
- **هدف:** نهایی‌سازی با وضوح
- **visual priority:** highest
- **brand intensity:** medium
- **recommended components:** sticky total + primary CTA
- **spacing direction:** safe-area aware، `12–16px` padding
- **content tone:** decisive, reassuring

### H. Secondary / Help Zone
- **هدف:** کاهش ریسک و حفظ راه خروج امن
- **visual priority:** medium
- **brand intensity:** low
- **recommended components:** edit booking، back، help link
- **spacing direction:** `8–12px` gap
- **content tone:** supportive, not alarming

### I. Security / Reassurance Strip
- **هدف:** اطمینان پیش از اقدام
- **visual priority:** medium
- **brand intensity:** medium
- **recommended components:** secure payment note، policy hint، access-to-details note
- **spacing direction:** `14–16px` padding
- **content tone:** calm, non-legalistic

### J. Status / Result Screen
- **هدف:** بستن uncertainty بعد از اقدام
- **visual priority:** highest
- **brand intensity:** medium
- **recommended components:** status icon, title, body, next action, transaction meta
- **spacing direction:** `20–24px` top content، `16px` between sections
- **content tone:** state-led + explicit

### K. Receipt / Confirmation Block
- **هدف:** record + next-access clarity
- **visual priority:** high
- **brand intensity:** low-medium
- **recommended components:** booking ID، amount، payment provider، tracking code، next steps
- **spacing direction:** `12px` row gap
- **content tone:** formal-light, exact, readable

---

## 5) Color System for Checkout

### Token Logic

- **background:** `loomera.bg #FCFBFE`
- **surface:** `loomera.surface #FFFFFF`
- **raised surface:** `loomera.surfaceRaised #FFFFFF`
- **border:** `loomera.border #DDD8E8`
- **divider:** `loomera.divider #E8E4EF`
- **text primary:** `loomera.textPrimary #2E2A3C`
- **text secondary:** `loomera.textSecondary #57526E`
- **text muted:** `loomera.textMuted #7A738F`
- **primary action:** `loomera.primary #735CBE`
- **focus ring:** `loomera.focusRing #C1A8F0`
- **success:** `loomera.success #5F9A73`
- **warning:** `loomera.warning #B88235`
- **error:** `loomera.error #C85C6B`
- **info:** `loomera.info #5E80C8`
- **booking highlight:** `loomera.bookingHighlight #F1F7EF`
- **calm glow:** `loomera.calmGlow #F2ECFE`
- **secure/reassurance surfaces:** `accentSoft` یا `primarySoft`

### Light Mode Checkout
- پس‌زمینه‌ی کل: `bg`
- کارت‌ها: `surface`
- summary secondary blocks: `surfaceSoft`
- borderها: `border / divider`
- CTA اصلی: `primary` با متن سفید
- reassurance strip: `bookingHighlight` یا `primarySoft`

### Dark Mode Checkout
- background: `#16131F`
- card: `#211C2E`
- raised sticky zone: `#2A2438`
- border: `#3B3550`
- text primary: `#F5F2FA`
- CTA: `#A688E6` با متن `#1B1826`
- reassurance surfaces: `#233126` یا `#2A2340`

### Payment States
- **Pending / Processing:** info tone + neutral card
- **Success:** success + successSoft
- **Failed:** error + errorSoft
- **Cancelled:** warningSoft یا neutral-soft
- **Refund:** successSoft + muted neutral rows
- **Session expired:** warningSoft + neutral CTA

### Summary Cards
سفید با border نرم؛ total row با divider نرم. total color باید brand-led بماند، نه neon.

### Sticky CTA Area
سطح جدا اما هم‌خانواده: `surface` یا `surfaceRaised` با blur بسیار ملایم و border-top نرم.

### Success / Failed / Cancelled / Refund Screens
- light card center-led
- icon circle soft tone
- title با textPrimary
- body با textSecondary
- meta block با surfaceSoft

---

## 6) Typography for Checkout

مبنای درست: **UI = Yekan Bakh-led sans**، serif فقط برای brand/display moments محدود. checkout باید کاملاً sans-led بماند.

### Role Map

#### checkout title style
- **role:** title اصلی صفحه
- **suggested token / class direction:** `heading.h4` / `lm-h4`
- **readability notes:** concise, strong, نه display-heavy

#### section title style
- **role:** بخش‌بندی اصلی
- **suggested token / class direction:** `heading.h5`
- **readability notes:** وزن 600، مناسب scan

#### summary label style
- **role:** label در rows
- **suggested token / class direction:** `label.md`
- **readability notes:** secondary color

#### summary value style
- **role:** مقدارهای رزرو
- **suggested token / class direction:** `body.md`
- **readability notes:** tabular برای قیمت/زمان

#### price / total style
- **role:** emphasis مالی
- **suggested token / class direction:** `component.metric.lg` برای total، `body.md` bold برای sub-rows
- **readability notes:** tabular numerals

#### helper / reassurance text style
- **role:** کاهش ابهام
- **suggested token / class direction:** `caption.md` یا `body.sm`
- **readability notes:** یک جمله، نرم، نه verbose

#### input / field style
- **role:** coupon / form fields
- **suggested token / class direction:** `component.input.md`
- **readability notes:** placeholder secondary، focus ring token-based

#### button text style
- **role:** CTA / secondary action
- **suggested token / class direction:** `component.button.md`
- **readability notes:** explicit, `1–4` words

#### status title / status body style
- **role:** state screens
- **suggested token / class direction:** title=`heading.h4`، body=`body.md`
- **readability notes:** title state-led, body explanatory

#### receipt / confirmation typography
- **role:** invoice-like clarity
- **suggested token / class direction:** labels=`label.md`، values=`body.md`، meta=`caption.md`
- **readability notes:** hierarchy operational بماند

### LTR Handling

برای این‌ها حتماً `dir="ltr"` + `unicode-bidi:isolate`:
- booking ID
- amount
- phone
- email
- transaction code
- gateway tracking
- receipt reference

و برای اعداد مالی و متریک‌ها `.lm-tabular` توصیه می‌شود.

---

## 7) Checkout Components Kit

### checkout header
- **visual treatment:** slim sticky trust header
- **tone:** calm + orienting
- **state behavior:** sticky on scroll
- **hierarchy:** logo > title > reassurance
- **do:** compact logo + one-line trust
- **don’t:** hero-like brand block

### order summary card
- **visual treatment:** white surface, soft border, rounded xl
- **tone:** factual
- **state behavior:** stable
- **hierarchy:** service > specialist > time > price
- **do:** rows scannable
- **don’t:** decorative gradients

### provider info card
- **visual treatment:** image/initial + provider name + address
- **tone:** human + grounded
- **state behavior:** always visible بالا
- **hierarchy:** provider before platform
- **do:** preserve identity context
- **don’t:** giant Loomera branding

### price breakdown list
- **visual treatment:** compact ledger
- **tone:** exact
- **state behavior:** total pinned visually
- **hierarchy:** subtotal > discounts > tax > total
- **do:** divider before total
- **don’t:** louder discounts than total

### promo / discount input
- **visual treatment:** quiet input + secondary action
- **tone:** optional, low-pressure
- **state behavior:** applied / invalid / removed
- **hierarchy:** below payment decision
- **do:** helper text friction-reducing
- **don’t:** overpromise savings

### payment method selector
- **visual treatment:** stacked cards with radio + body copy
- **tone:** practical
- **state behavior:** selected / disabled / unavailable / insufficient
- **hierarchy:** title > label > explanation
- **do:** explain consequence
- **don’t:** hide conditions

### secure payment note
- **visual treatment:** reassurance strip with icon
- **tone:** confident, restrained
- **state behavior:** static
- **hierarchy:** short statement then optional detail
- **do:** keep `1–2` lines
- **don’t:** legal wall of text

### consent / terms row
- **visual treatment:** subtle inline row
- **tone:** formal-light
- **state behavior:** unchecked / checked / validation
- **hierarchy:** checkbox > statement > link
- **do:** plain language
- **don’t:** dense paragraph

### sticky payment CTA
- **visual treatment:** raised bottom bar
- **tone:** decisive
- **state behavior:** idle / loading / disabled
- **hierarchy:** total first, CTA second
- **do:** keep total visible
- **don’t:** add logo here

### inline validation
- **visual treatment:** caption-sized line under field
- **tone:** helpful
- **state behavior:** error / success / neutral
- **hierarchy:** after field
- **do:** say what to fix
- **don’t:** blame user

### error banner
- **visual treatment:** soft semantic banner
- **tone:** calm, direct
- **state behavior:** dismissible if non-critical
- **hierarchy:** what happened > impact > next step
- **do:** actionable copy
- **don’t:** raw technical detail

### success state card
- **visual treatment:** centered card + soft success icon
- **tone:** settled, reassuring
- **state behavior:** final
- **hierarchy:** title > body > next actions > receipt meta
- **do:** tell user where details are available
- **don’t:** overcelebrate

### failed payment state card
- **visual treatment:** semantic error card, no alarmism
- **tone:** clear, non-blaming
- **state behavior:** retry / alternative path
- **hierarchy:** failure > impact > next action
- **do:** say whether amount was deducted
- **don’t:** vague error copy

### cancelled payment state card
- **visual treatment:** warning/neutral blend
- **tone:** respectful
- **state behavior:** retry or back
- **hierarchy:** cancelled > not finalized > return path
- **do:** recovery easy
- **don’t:** present as fatal

### refund info card
- **visual treatment:** soft success-neutral card
- **tone:** accountable
- **state behavior:** conditional
- **hierarchy:** refund > amount > destination > time
- **do:** show destination clearly
- **don’t:** mix with generic success

### receipt / confirmation block
- **visual treatment:** structured details card
- **tone:** operational
- **state behavior:** printable/downloadable/in-app
- **hierarchy:** booking details > payment details > next steps
- **do:** isolate IDs and codes
- **don’t:** overload with decorative content

### support escalation block
- **visual treatment:** last card or footer block
- **tone:** calm + available
- **state behavior:** static or conditional
- **hierarchy:** help statement > support route
- **do:** link to support path
- **don’t:** place above primary action by default

---

## 8) Copy & Reassurance Layer

### Copy Direction

checkout copy باید **کوتاه، explicit و status-led** باشد. هر خط ideally باید یکی از این سه کار را بکند:
- clarify
- reassure
- guide

### Sample Lines

#### checkout intro line
`این مرحله برای مرور نهایی رزرو و ثبت آن با جزئیات روشن طراحی شده است.`

#### review reminder line
`لطفاً پیش از ادامه، زمان، خدمت و مبلغ را یک‌بار دیگر بررسی کنید.`

#### payment reassurance lines
- `مبلغ نهایی پیش از پرداخت نمایش داده می‌شود.`
- `جزئیات رزرو قبل از پرداخت نهایی در دسترس شماست.`

#### security lines
- `اطلاعات پرداخت شما با امنیت پردازش می‌شود.`
- `وضعیت پرداخت و نتیجه‌ی رزرو پس از تکمیل، روشن و قابل‌پیگیری است.`

#### confirmation copy direction
- `پرداخت انجام شد و رزرو شما نهایی شد.`
- `جزئیات رزرو در همین صفحه و بخش نوبت‌های من در دسترس است.`

#### failed payment copy direction
`پرداخت کامل نشد. مبلغی کسر نشده است. لطفاً دوباره تلاش کنید.`

#### cancelled payment copy direction
`پرداخت لغو شد. در صورت تمایل می‌توانید دوباره ادامه دهید.`

#### refund copy direction
`بازگشت وجه انجام شد. مبلغ به مسیر بازگشت تعریف‌شده منتقل شد و جزئیات آن در همین بخش قابل بررسی است.`

#### support/help line in checkout
`اگر درباره‌ی پرداخت یا وضعیت رزرو سؤالی دارید، از همین مسیر می‌توانید با پشتیبانی در تماس باشید.`

#### booking finality line
`پس از ثبت نهایی، جزئیات رزرو همیشه از بخش نوبت‌های من در دسترس خواهد بود.`

#### what happens next line
`پس از تأیید پرداخت، نتیجه‌ی رزرو بلافاصله نمایش داده می‌شود و رسید در دسترس شما قرار می‌گیرد.`

### CTA Format

- primary: `پرداخت و ثبت نهایی`
- secondary: `بازگشت به رزرو`
- recovery CTA: `دوباره تلاش می‌کنم`

### ترتیب copy در لحظه‌های حساس
1. state
2. impact
3. next step
4. optional support path

---

## 9) Payment State Visual System

### A. Pending / Redirecting
- **title direction:** `در حال انتقال به درگاه پرداخت`
- **body direction:** کوتاه و توضیح‌محور
- **icon / illustration style:** spinner یا gateway arrow نرم
- **color treatment:** infoSoft / neutral
- **button / next action:** none یا `بازگشت`
- **brand intensity:** low
- **trust note:** `پس از بازگشت، نتیجه به‌صورت خودکار نمایش داده می‌شود.`

### B. Processing
- **title direction:** `در حال بررسی پرداخت`
- **body direction:** `لطفاً این صفحه را نبندید.`
- **icon / illustration style:** subtle progress ring
- **color treatment:** neutral + info hint
- **button / next action:** none
- **brand intensity:** low
- **trust note:** pending, not alarming

### C. Success
- **title direction:** `پرداخت انجام شد و رزرو شما نهایی شد`
- **body direction:** دسترسی به booking + receipt
- **icon / illustration style:** check inside soft circle
- **color treatment:** success + successSoft
- **button / next action:** `مشاهده نوبت`
- **brand intensity:** medium
- **trust note:** محل دسترسی به جزئیات گفته شود

### D. Failed
- **title direction:** `پرداخت کامل نشد`
- **body direction:** impact + retry
- **icon / illustration style:** soft alert
- **color treatment:** error + errorSoft
- **button / next action:** `دوباره تلاش می‌کنم`
- **brand intensity:** low-medium
- **trust note:** اگر مبلغ کسر نشده، صریح گفته شود

### E. Cancelled
- **title direction:** `پرداخت لغو شد`
- **body direction:** رزرو نهایی نشده + مسیر برگشت
- **icon / illustration style:** x inside soft warning circle
- **color treatment:** warningSoft / neutral
- **button / next action:** `بازگشت به پرداخت`
- **brand intensity:** low-medium
- **trust note:** re-entry friction low

### F. Refunded
- **title direction:** `بازگشت وجه انجام شد`
- **body direction:** amount + destination + time
- **icon / illustration style:** wallet / refresh icon
- **color treatment:** successSoft with neutral text
- **button / next action:** `مشاهده جزئیات رسید`
- **brand intensity:** medium
- **trust note:** destination explicit

### G. Session Expired
- **title direction:** `زمان این مرحله به پایان رسیده است`
- **body direction:** `برای ادامه، دوباره به مرحله‌ی پرداخت برگردید.`
- **icon / illustration style:** clock
- **color treatment:** warningSoft
- **button / next action:** `بازگشت به پرداخت`
- **brand intensity:** low
- **trust note:** blame-free

### H. Provider-side Review Pending
- **title direction:** `رزرو ثبت شد و در انتظار تأیید است`
- **body direction:** provider-side confirmation context
- **icon / illustration style:** pending badge
- **color treatment:** infoSoft یا bookingHighlight
- **button / next action:** `مشاهده وضعیت رزرو`
- **brand intensity:** medium
- **trust note:** تفاوت payment success و provider approval روشن بماند

---

## 10) Email / Receipt / Confirmation Alignment

### booking confirmation email
- **recommended sender identity:** `bookings@loomera.ir` / `رزرو Loomera`
- **tone:** precise, reassuring
- **subject/header direction:** `رزرو شما ثبت شد`
- **visual continuity with checkout:** summary structure مشابه
- **recommended signature style:** `رزرو Loomera`

### payment receipt email
- **recommended sender identity:** `billing@loomera.ir` / `مالی Loomera`
- **tone:** exact, calm
- **subject/header direction:** `رسید پرداخت شما`
- **visual continuity with checkout:** receipt block مشابه in-app
- **recommended signature style:** `مالی Loomera`

### payment issue email
- **recommended sender identity:** `billing@loomera.ir`
- **tone:** explanatory, non-blaming
- **subject/header direction:** `پرداخت شما نهایی نشد`
- **visual continuity with checkout:** failed state palette نرم
- **recommended signature style:** `مالی Loomera`

### refund email
- **recommended sender identity:** `billing@loomera.ir`
- **tone:** accountable
- **subject/header direction:** `بازگشت وجه انجام شد`
- **visual continuity with checkout:** soft success-neutral
- **recommended signature style:** `مالی Loomera`

### support follow-up
- **recommended sender identity:** `support@loomera.ir` / `پشتیبانی Loomera`
- **tone:** empathetic + practical
- **subject/header direction:** `پیگیری درخواست شما`
- **visual continuity with checkout:** minimal, text-led
- **recommended signature style:** `پشتیبانی Loomera`

### printable / downloadable receipt
- **recommended sender identity:** Loomera billing layer
- **tone:** formal-light
- **subject/header direction:** compact logo + receipt title
- **visual continuity with checkout:** same summary hierarchy
- **recommended signature style:** `مالی Loomera`

### in-app confirmation
- **recommended sender identity:** platform UI
- **tone:** short, status-led
- **subject/header direction:** same as success state
- **visual continuity with checkout:** exact mirror of checkout state system

---

## 11) Mobile Checkout Rules

- **logo treatment:** glyph-only یا compact minimal
- **header compression:** title کوتاه، no duplicate brand text
- **sticky CTA behavior:** total همیشه visible؛ CTA single-row؛ safe-area aware
- **summary collapse/expand behavior:** provider + total visible، details collapsible
- **spacing priorities:** summary و CTA اولویت اول
- **total amount visibility:** باید بدون scroll اضافی پیدا باشد
- **trust note placement:** زیر header یا بالای CTA
- **failure/success state readability:** title کوتاه، body حداکثر `2–3` خط
- **keyboard/input considerations:** input نباید sticky CTA را بپوشاند
- **RTL handling:** header right-anchored؛ amount / booking ID / phone / email / code حتماً LTR isolate

---

## 12) Design Directions

### direction 1: minimal trusted
- **توضیح کوتاه:** checkout تقریباً brand-light
- **مزیت:** بسیار product-clean
- **ریسک:** Loomera کمی generic می‌شود
- **مناسب بودن برای Loomera:** خوب، ولی بیش از حد خاموش

### direction 2: softly branded premium
- **توضیح کوتاه:** brand presence نرم در header، CTA و reassurance surfaces
- **مزیت:** بهترین تعادل بین trust، premium feel و usability
- **ریسک:** اگر tintها زیاد شوند، flow کم‌کنتراست می‌شود
- **مناسب بودن برای Loomera:** بسیار مناسب

### direction 3: product-led reassurance
- **توضیح کوتاه:** system-first execution با تأکید زیاد روی status و totals
- **مزیت:** برای payment UX عالی
- **ریسک:** اگر logo treatment ضعیف شود، brand memory افت می‌کند
- **مناسب بودن برای Loomera:** مناسب، ولی بهتر است با direction 2 ترکیب شود

---

## 13) Final Recommendation

### Direction نهایی
**Softly Branded Premium + Product-Led Reassurance**

### Balance نهایی
- **logo usage نهایی:** compact logo در trust header و success confirmation؛ glyph-only در mobile
- **color intensity:** low-to-medium؛ violet فقط برای CTA، focus و select emphasis
- **copy tone:** status-led, calm, exact, respectful
- **summary vs payment hierarchy:**
  1. provider / booking context
  2. service/date review
  3. payment method
  4. total
  5. CTA
  6. help/support

### چرا این گزینه درست‌تر است
چون Loomera باید در checkout «فشار نیاورد»، بلکه «اطمینان بدهد». این direction هم brand memory را نگه می‌دارد، هم provider identity را له نمی‌کند، هم checkout را شبیه SaaS generic یا beauty checkout تزئینی نمی‌کند.

---

## 14) Handoff Spec

### A. برای Design Team

#### brand rules
- checkout brand should be trust-led, not promo-led
- compact logo only in trust header / success confirmation
- provider identity remains first-class

#### component rules
- cards white / soft / rounded
- selector cards fully clickable
- summary rows ledger-like
- sticky CTA separate but quiet

#### state rules
- semantic soft colors only
- success / failed / cancelled / refund visually distinct
- pending / processing calm, not alarming

#### spacing and emphasis rules
- generous vertical rhythm
- only one dominant CTA
- total row strongest numeric emphasis
- reassurance copy max `1–2` lines

### B. برای Frontend Team

#### component naming suggestions
- `checkout-brand-header`
- `checkout-summary-card`
- `payment-method-block`
- `checkout-security-strip`
- `payment-status-card`
- `checkout-receipt-block`
- `checkout-help-block`

#### class/token usage direction
- migrate checkout from legacy `legacy-design-namespace-*` aliases to `loomera.*`
- use `loomera.primary`, `surface`, `border`, `textPrimary`, `focusRing`
- typography roles should map to Loomera UI roles

#### dark/light mode notes
- light: `bg / surface / primary`
- dark: plum-based surfaces, no pure black, no neon purple
- status cards should swap cleanly to dark semantic-soft surfaces

#### RTL/LTR handling
- wrapper RTL
- IDs, amounts, phones, emails, transaction codes = `.lm-ltr`
- numeric money/metrics = `.lm-tabular`

#### state implementation notes
- CTA loading state should lock duplicate submit
- payment verify screen should distinguish success / cancelled / failed / refunded
- provider-side pending should be a separate state

---

## 15) Deliverables

این خروجی شامل این deliverableهاست:

1. checkout branding strategy
2. logo treatment rules
3. layout zones spec
4. color rules for checkout
5. typography rules for checkout
6. components kit
7. copy/reassurance layer
8. payment state visual system
9. mobile checkout rules
10. final recommended direction
11. design handoff
12. frontend handoff
13. summary-ready version برای docs/product یا docs/design-system

### summary-ready version

**Loomera checkout should be softly branded, trust-led, and highly precise.**  
Brand presence must stay visible but restrained through a compact trust header, Loomera token-based CTA, quiet reassurance surfaces, and a consistent payment state system. Provider identity should remain central in booking context, while Loomera acts as the platform trust layer. Color usage must come from the existing Loomera token system, typography must stay sans-led with proper RTL/LTR isolation, and payment states must communicate clear status, impact, and next step without pressure or noise. This creates a checkout that feels calm, secure, readable, and quietly premium.

---

## 16) Success Criteria

- kit باید از assetها و system فعلی Loomera بیاید
- checkout باید trusted, calm, precise و product-ready باشد
- در رنگ، تایپوگرافی و logo usage با repo align باشد
- copy باید با voice و microcopy system سازگار باشد
- payment stateها باید روشن و reassuring باشند
- mobile و RTL باید به‌خوبی پوشش داده شوند
- نتیجه باید source-ready و handoff-ready باشد
