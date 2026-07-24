# Loomera Notification / Email Visual Header System

نسخه: 1.0  
وضعیت: source-ready / handoff-ready  
برند: Loomera

## 1) Source Review Summary

بررسی ZIP `files` و سورس پروژه نشان می‌دهد Loomera از نظر هویت بصری یک برند **calm, refined, trustworthy, quietly premium** است؛ با پالت violet-led، accent سبز کنترل‌شده، neutralهای گرم، و typography محصولی sans-led با Yekan Bakh / Vazirmatn / Inter و brand/display serif-led برای logo/brand moments. لوگوی اصلی wordmark serif-led با symbol ارگانیک برگ/گل + sparkle است و glyph مستقل آن برای سطوح کوچک و utility مناسب‌تر از full logo است.

در محصول، touchpointهای notification و email عمدتاً در booking lifecycle، payment/result، support، auth/OTP، dashboard notification center و provider/partner coordination معنا پیدا می‌کنند. در سورس فعلی، notification center داخل dashboard وجود دارد، مدل `AppointmentNotification` برای کانال‌های dashboard/email/sms تعریف شده، و lifecycle emailها فعلاً با `send_mail` به‌صورت plain-text ارسال می‌شوند؛ اما **سیستم HTML email header منسجم و reusable در سورس فعلی وجود ندارد**.

Constraintهای کلیدی:
- brand voice: reassure before persuade، status-first، no hype
- checkout: visible but restrained، trust-layer نه marketing-layer
- shell/logo system: glyph برای utility، compact/full logo فقط در trust-heavy contexts
- domain/email system: sender-based differentiation (`رزرو Loomera`، `مالی Loomera`، `امنیت Loomera`، `پشتیبانی Loomera`، `ارائه‌دهندگان Loomera`)
- product structure: RTL-first، Persian readability، LTR isolation برای شناسه‌ها و داده‌های سیستمی

نتیجه: headerها برای Loomera باید **trust-first** باشند، نه brand-first.

## 2) Header System Strategy

نقش visual header در emailهای Loomera این است که پیش از body، سه چیز را سریع و بی‌ابهام منتقل کند:
1. این پیام از کدام family است.
2. وضعیت یا intent آن چیست.
3. این touchpoint متعلق به یک پلتفرم بالغ و قابل‌اعتماد است.

میزان درست brand visibility در این سیستم **low to medium** است. لوگو باید هویت را تثبیت کند، اما جای status و utility را نگیرد.

همه‌ی emailها نباید یک header کاملاً یکسان داشته باشند. ساختار پایه مشترک می‌ماند، اما **family-based variation** لازم است:
- transactional / generic: neutral base + minimal brand cue
- booking / reminder: calm booking cue
- payment / receipt / refund: financial-status cue
- auth / security: security-first cue
- support: humane but structured cue
- provider / partner: operational / B2B cue

برای in-app notification surfaces همین language باید حفظ شود، اما نسخه‌ی adapted و سبک‌تر. in-app نباید از image-based email header تقلید کند؛ باید typographic, compact, status-led بماند.

## 3) Required Notification / Email Types

### A. Booking Confirmation Email
- هدف: تثبیت ثبت رزرو و کاهش uncertainty
- tone: روشن، آرام، تأییدی
- trust level: بالا
- logo prominence: low-medium
- icon/glyph: بله، glyph یا cue موفقیت ظریف
- text density: کم تا متوسط
- visual intensity: پایین

### B. Booking Reminder Email
- هدف: یادآوری زمان و آماده‌سازی کاربر
- tone: concise, respectful
- trust level: متوسط رو به بالا
- logo prominence: low
- icon/glyph: اختیاری؛ ترجیحاً clock/calendar cue ساده
- text density: کم
- visual intensity: بسیار پایین

### C. Payment Receipt Email
- هدف: ثبت شفاف پرداخت و مرجع‌پذیری
- tone: exact, calm
- trust level: خیلی بالا
- logo prominence: low
- icon/glyph: بله، receipt cue یا status line
- text density: متوسط
- visual intensity: پایین

### D. Payment Issue / Failed Payment Email
- هدف: توضیح وضعیت بدون ایجاد panic
- tone: explanatory, non-blaming
- trust level: خیلی بالا
- logo prominence: very low
- icon/glyph: بله، warning cue کنترل‌شده
- text density: متوسط
- visual intensity: پایین تا متوسط

### E. Refund Email
- هدف: اعلام مسئولانه‌ی بازگشت وجه
- tone: accountable, precise
- trust level: خیلی بالا
- logo prominence: low
- icon/glyph: بله، refund/success cue نرم
- text density: متوسط
- visual intensity: پایین

### F. Auth / OTP / Security Email
- هدف: امنیت، تایید هویت، فوریت روشن
- tone: short, direct, secure
- trust level: خیلی بالا
- logo prominence: very low
- icon/glyph: بله، security cue یا shield/lock style cue ساده
- text density: کم
- visual intensity: پایین اما focused

### G. Support Reply Email
- هدف: نشان دادن ownership و ادامه‌ی رسیدگی
- tone: empathetic, practical
- trust level: بالا
- logo prominence: low
- icon/glyph: اختیاری؛ support cue آرام
- text density: متوسط
- visual intensity: پایین

### H. Help Center Escalation / Case Update Email
- هدف: پیشبرد پرونده و روشن نگه‌داشتن مرحله‌ی بعد
- tone: accountable, structured
- trust level: بالا
- logo prominence: very low
- icon/glyph: بله، case/update cue کوچک
- text density: متوسط
- visual intensity: پایین

### I. Provider / Partner Onboarding Email
- هدف: خوش‌آمدگویی عملیاتی و معرفی گام بعد
- tone: polished, structured, welcoming
- trust level: بالا
- logo prominence: medium
- icon/glyph: بله، glyph یا partner cue مینیمال
- text density: متوسط
- visual intensity: low-medium

### J. Product Update / Account Notice Email
- هدف: اطلاع‌رسانی غیرتراکنشی ولی product-safe
- tone: concise, informative
- trust level: متوسط
- logo prominence: medium-low
- icon/glyph: اختیاری
- text density: متوسط
- visual intensity: پایین

### K. Generic Transactional Email
- هدف: انتقال state یا next step بدون ambiguity
- tone: direct, calm
- trust level: بالا
- logo prominence: low
- icon/glyph: بر اساس status
- text density: کم تا متوسط
- visual intensity: پایین

### L. In-App Notification Header Surface
- هدف: scannability سریع در list/detail
- tone: status-led
- trust level: متوسط
- logo prominence: none or very low
- icon/glyph: yes, status cue بهتر از logo
- text density: کم
- visual intensity: بسیار پایین

## 4) Header Architecture

ساختار پایه‌ی هر header باید این لایه‌ها را داشته باشد:
- top spacing
- brand row
- category/status cue row
- header title zone
- optional support line
- divider / transition into body

### Base structure
1. **Top spacing**: 24–32px در desktop email، 20–24px در mobile email.
2. **Logo/Glyph area**: یک row کوچک و ثابت؛ نه centered hero block. در RTL روی راست.
3. **Category / Status cue**: overline یا chip سبک با label خانواده پیام.
4. **Header title zone**: عنوان 1 یا 2 خطی.
5. **Optional support line**: یک خط reassurance یا operational note.
6. **Divider / transition**: hairline border یا spacing break نرم.
7. **Safe body handoff**: body باید بدون پرش بصری شروع شود.

### Optional parts
- support line: فقط وقتی ambiguity را کم می‌کند
- status icon: برای payment/auth/refund/issue/reply مفید؛ برای reminder و generic اختیاری
- reassurance strip: فقط در payment/auth/support، نه در همه‌ی emailها

### Layout rules
- safe area داخلی header: 24px افقی / 24–28px عمودی
- mobile-safe stacking: brand row، سپس cue، سپس title، سپس support line
- background treatment باید flat یا softly tinted باشد، نه image-led

## 5) Logo / Glyph Rules

قاعده‌ی اصلی:
- **Full logo** فقط در touchpointهای trust-heavy یا partner-facing
- **Compact logo** برای transactional email header استاندارد
- **Glyph** برای utility / auth / compact / mobile / in-app
- **Logo-free header** برای بعضی support case updates یا dense receipts مجاز است، اگر sender name و subject clarity کافی باشد

### Where each is right
- **Full logo**: provider onboarding، partner email، نخستین welcome-style product notice، بعضی support/brand-level notices
- **Compact logo**: booking confirmation، payment receipt، generic transactional، refund
- **Glyph-only**: reminder، auth/security، payment issue، mobile-safe compact header
- **Logo-free**: receiptهای بسیار dense، escalation updateهای thread-like، in-app notification detail headerهای بسیار utility-first

### In-app rule
in-app notification header بهتر است بیشتر **status cue + title** باشد. glyph فقط در detail surfaces یا empty/high-level states، نه در هر list item.

### Named rules
- `notification-header-brand`: default = none; اگر لازم شد glyph کوچک 16–20px
- `email-header-brand-lockup`: compact logo, width 112–140px
- `receipt-header-brand`: compact logo یا logo-free + financial overline
- `support-email-header`: compact logo کوچک یا text-based sender cue
- `auth-email-header`: glyph-only یا brand text minimal
- `mobile-email-header-brand`: glyph 18–22px یا compact logo حداکثر 96px width

### Anti-noise rule
هرجا لوگو مجبور می‌شود خیلی کوچک، رنگیِ اضافی، یا تکرارشونده شود، بهتر است به glyph یا typographic cue downgrade شود.

## 6) Color Rules

Headerها باید از tokenهای واقعی Loomera بیایند، اما از CTA-level saturation دور بمانند.

### Core header tokens
- email header background default: `loomera.bgSubtle #F7F6FA` یا `loomera.surface #FFFFFF`
- surface soft layer: `loomera.surfaceSoft #F4F1F8`
- border/divider: `loomera.divider #E8E4EF` یا `loomera.borderSoft #ECE8F2`
- title: `loomera.textPrimary #2E2A3C`
- subtitle/support line: `loomera.textSecondary #57526E`
- micro label/meta: `loomera.textMuted #7A738F`

### Status accents
- success / confirmed / refund done: `loomera.success #5F9A73` + `loomera.successSoft #EEF7F0`
- reminder / schedule / neutral info: `loomera.info #5E80C8` + `loomera.infoSoft #EDF3FC`
- payment pending / waiting: `loomera.warning #B88235` + `loomera.warningSoft #FDF3E4`
- payment failed / issue / security concern: `loomera.error #C85C6B` + `loomera.errorSoft #FCECEF`
- trust/reassurance strip: `loomera.bookingHighlight #F1F7EF` یا `loomera.primarySoft #EEE8FA`
- brand accent-only areas: `loomera.primarySoft #EEE8FA`, `loomera.secondarySoft #F3EEFB`, `loomera.calmGlow #F2ECFE`

### Family mappings
- booking / reminder: base neutral + bookingHighlight / primarySoft
- payment receipt: base neutral + very soft primarySoft
- payment issue: neutral base + warning/error accent line
- refund: neutral base + successSoft
- auth/security: neutral base + infoSoft یا errorSoft depending on seriousness
- support: neutral base + surfaceSoft, almost colorless
- partner/business: surface + subtle primarySoft band

### Dark-safe direction
برای HTML email dark mode، layout همچنان باید روی light-first طراحی شود؛ اما assetها و logoها باید روی auto-invert نشکنند. dark-safe variant فقط این موارد را داشته باشد:
- background نزدیک به `#211C2E`
- title `#F5F2FA`
- border `#3B3550`
- accentها نسخه dark tokens

## 7) Typography Rules

مبنای سیستم تایپوگرافی Loomera برای headerها **UI sans-led** است؛ نه serif-led. Serif فقط برای لوگو/wordmark.

### Roles
- email header title: معادل `heading.h4` یا بین `20/30` و `24/34`
- mobile title: `18/26` تا `20/28`
- support line: `body.sm 14/24`
- status label: `overline` یا `label.md 13/20`
- small metadata label: `caption.md 12/18`
- receipt/confirmation header typography: title متوسط + meta labels tabular-safe

### Persian readability
- tracking فارسی همیشه 0
- title حداکثر 2 خط
- support line حداکثر 2 خط
- title line length: حدود 18–28 کاراکتر فارسی در هر خط بسته به container
- support line line length: بهتر است زیر 42–48 کاراکتر فارسی بماند

### English pair behavior
اگر subject یا internal English label وجود دارد، در header فارسی نباید dominant شود. الگوی درست:
- title فارسی first
- optional English label فقط در metadata یا file/export surfaces

### RTL + mixed content
برای این‌ها همیشه `dir="ltr"` + `unicode-bidi:isolate`:
- booking ID
- transaction code
- amount اگر با ارقام لاتین ارسال می‌شود
- email
- phone
- case/reference number

### Limits
- category/status label: 1 line
- title: 1–2 lines
- support line: 0–2 lines
- no multi-paragraph header copy

## 8) Status-Aware Visual System

### success
- visual temperature: calm positive
- accent intensity: low
- icon/glyph: optional yes
- title tone: definitive
- support line: optional
- color: success + neutral
- trust note: optional

### reminder
- visual temperature: light, anticipatory
- accent intensity: very low
- icon/glyph: optional clock/calendar
- title tone: concise
- support line: only if useful
- color: infoSoft / primarySoft
- trust note: usually no

### payment pending
- visual temperature: procedural
- accent intensity: low-medium
- icon/glyph: yes
- title tone: clear, non-alarmist
- support line: yes
- color: warningSoft
- trust note: yes, if action is needed

### payment failed
- visual temperature: serious but calm
- accent intensity: medium, never loud
- icon/glyph: yes
- title tone: explicit
- support line: yes
- color: errorSoft + error line
- trust note: yes, especially “مبلغی کسر نشده است” when true

### refund
- visual temperature: resolved / accountable
- accent intensity: low
- icon/glyph: yes
- title tone: exact
- support line: yes if destination/time matters
- color: successSoft
- trust note: yes

### security/auth
- visual temperature: focused / secure
- accent intensity: low-medium
- icon/glyph: yes
- title tone: direct
- support line: short
- color: infoSoft or errorSoft depending on severity
- trust note: yes

### support/help
- visual temperature: human, composed
- accent intensity: minimal
- icon/glyph: optional
- title tone: accountable
- support line: often useful
- color: mostly neutral
- trust note: optional

### neutral transactional
- visual temperature: balanced
- accent intensity: very low
- icon/glyph: optional
- title tone: explicit
- support line: optional
- color: primarySoft / surfaceSoft
- trust note: optional

### partner/business
- visual temperature: operationally confident
- accent intensity: low-medium
- icon/glyph: yes or compact logo
- title tone: structured
- support line: useful
- color: primarySoft + surface
- trust note: optional

## 9) Copy Relationship

Copy داخل header باید short, precise, client-safe و non-promotional باشد.

### Tone rules
- booking: confirming and reassuring
- payment: exact and explicit
- support: calm and ownership-led
- auth: short and secure
- partner: structured and polished
- in-app: even shorter, status-first

### Support line rules
- فقط وقتی به clarity کمک می‌کند
- نه بیشتر از یک جمله کوتاه
- بهتر است state یا next step را روشن کند

### Reassurance line
برای payment/auth/support گاهی لازم است. برای reminder و generic transactional غالباً لازم نیست.

### Balance rule
Loomera باید بین clarity و warmth این‌گونه تعادل بسازد:
- clarity در title
- warmth در support line
- restraint در visual treatment

## 10) Email-Client & Product Constraints

### Email-safe implementation
- safest layout: table-based container, single-column, max-width حدود 560–640px
- header safest pattern: solid background color + nested table + inline styles
- avoid: CSS grid, background-blend, heavy gradients, masked SVG tricks, text-over-image hero
- border radius limited and non-essential؛ در Outlook نباید حیاتی باشد

### Background treatment risk
- safest: solid color or very subtle flat tint
- acceptable: 1px divider, small colored strip, inline icon block
- risky: full-width gradient, image background, transparency-dependent overlays

### Logo safe sizing
- compact logo width: 112–140px desktop
- full logo width: 132–168px only when justified
- glyph: 18–28px depending on header density

### Text-over-image
مجاز نیست؛ برای transactional emailهای Loomera باید ممنوع باشد.

### Dark mode behavior
- clients ممکن است colorها را auto-shift کنند
- logo asset باید transparent-safe و invert-resistant باشد
- rely on contrast, not subtle brand tint only
- dark-safe variant optional، اما light-first system باید به‌تنهایی هم قابل‌خواندن بماند

### In-app difference
in-app notification header محدودیت‌های email را ندارد؛ می‌تواند از CSS tokenها، sticky header، icon tint و state borderها استفاده کند. اما نباید از email system visually جدا شود.

## 11) In-App Notification Alignment

زبان بصری باید مشترک باشد، اما نسخه‌ی in-app **adapted** باشد.

### Shared principles
- same status colors
- same title tone
- same restraint level
- same logo discipline

### Notification list item header
- no logo
- status icon or colored dot/chip کافی است
- title + short meta + optional category pill
- primary cue typographic باشد، نه تصویری

### Notification detail header
- optional glyph کوچک یا category chip
- title واضح
- support line کوتاه در صورت نیاز
- status cue ترجیحاً typographic + subtle color wash

### Brand presence
در in-app باید **کمتر از email** باشد، چون کاربر از قبل داخل محیط Loomera است.

## 12) Design Directions

### Direction 1: minimal trusted transactional
**توضیح:** almost-neutral header با logo بسیار restrained، status cue کوچک و title واضح.  
**مزیت:** بالاترین compatibility، mature، email-safe.  
**ریسک:** اگر بیش از حد مینیمال شود، family differentiation ضعیف می‌شود.  
**مناسب بودن:** بسیار مناسب.

### Direction 2: softly branded reassurance
**توضیح:** neutral base + soft violet/sage tint bands + compact brand lockup.  
**مزیت:** هویت Loomera را بهتر حفظ می‌کند و هنوز utility-first است.  
**ریسک:** اگر tintها زیاد شوند، به decorative banner نزدیک می‌شود.  
**مناسب بودن:** بهترین تعادل برای Loomera.

### Direction 3: refined platform messaging
**توضیح:** structure-heavy header با category row، support line، dividerهای دقیق و brand almost editorial.  
**مزیت:** برای partner/support/product noticeها خیلی بالغ و platform-like است.  
**ریسک:** برای transactional emailهای کوتاه ممکن است کمی رسمی یا سنگین شود.  
**مناسب بودن:** خوب، اما نه به‌عنوان default family.

## 13) Final Recommendation

جهت نهایی پیشنهادی برای Loomera: **Direction 2 — softly branded reassurance**.

### Why
- با brand palette واقعی Loomera هم‌راستاست
- نسبت به direction 1 warmth و continuity بیشتری دارد
- نسبت به direction 3 برای emailهای تراکنشی سبک‌تر و usableتر است
- با checkout kit و shell logo system perfectly aligned است: visible but restrained

### Final stance
- brandedness: low-to-medium
- logo prominence: compact and controlled
- status differentiation: clear but muted
- colors: soft tint-led, never saturated blocks
- in-app alignment: same logic, lighter execution

## 14) Required Deliverables

1. header system strategy  
2. email/notification type mapping  
3. header architecture  
4. logo/glyph rules  
5. color rules  
6. typography rules  
7. status-aware visual rules  
8. copy relationship rules  
9. client/product constraints  
10. in-app alignment rules  
11. final recommended direction  
12. mini handoff spec برای design team  
13. mini handoff spec برای frontend/email implementation team

## 15) Asset Output Requirement

### Required variants
- `email-header-booking-confirmation`
- `email-header-booking-reminder`
- `email-header-payment-receipt`
- `email-header-payment-issue`
- `email-header-refund`
- `email-header-auth-security`
- `email-header-support`
- `email-header-partner`
- `email-header-generic-transactional`
- `inapp-notification-header-generic`
- `inapp-notification-header-status`

### Optional modifiers
- `light`
- `dark-safe`
- `compact`
- `mobile-safe`
- `no-status-icon`
- `status-accented`

### Suggested naming + folder structure
```text
branding/
  notification-email-header/
    docs/
      loomera-notification-email-visual-header-system.md
    email/
      email-header-booking-confirmation.light.svg
      email-header-booking-reminder.light.svg
      email-header-payment-receipt.light.svg
      email-header-payment-issue.light.svg
      email-header-refund.light.svg
      email-header-auth-security.light.svg
      email-header-support.light.svg
      email-header-partner.light.svg
      email-header-generic-transactional.light.svg
      dark-safe/
      mobile-safe/
      compact/
    inapp/
      inapp-notification-header-generic.light.svg
      inapp-notification-header-status.light.svg
    tokens/
      notification-email-header.tokens.json
    snippets/
      email-visual-header.html
      transactional-email-header.html
      support-email-header.html
      auth-email-header.html
      receipt-email-header.html
      notification-header-surface.html
```

## 16) Handoff Notes

### For Design Team
**Consistency rules**
- structure ثابت بماند؛ variation فقط در cue و tint
- title tone همیشه status-first باشد
- headerها تصویرمحور نشوند

**Do**
- از compact logo یا glyph با restraint استفاده کنید
- color را در حد tint، strip یا chip نگه دارید
- روی hierarchy و readability تمرکز کنید

**Don’t**
- از banner-style hero استفاده نکنید
- purple blockهای سنگین یا gradientهای شدید نسازید
- لوگو را در هر variant بزرگ نکنید

**Color restraint rules**
- primary violet برای accent، نه برای full header block
- success/warning/error همیشه soft-first باشند
- support header تقریباً colorless بماند

**Logo usage rules**
- full logo فقط در partner/welcome/trust-heavy
- compact logo پیش‌فرض email
- glyph برای auth/reminder/mobile
- no logo برای list item headers

**Status cue rules**
- cue باید secondary to title بماند
- icon + chip + tint هر سه را هم‌زمان فقط در stateهای مهم استفاده کنید

**Email vs in-app**
- email: brand cue کمی بیشتر
- in-app: status cue مهم‌تر از brand cue

### For Frontend / Email Team
**Suggested component naming**
- `email-visual-header`
- `transactional-email-header`
- `support-email-header`
- `auth-email-header`
- `receipt-email-header`
- `notification-header-surface`

**HTML email-safe notes**
- table wrapper + inline styles
- single-column layout
- background images ممنوع
- iconها ترجیحاً inline image یا bulletproof VML-safe fallback if necessary
- text content should not depend on image load

**Light/dark handling**
- light-first HTML
- dark-safe logo asset
- no reliance on subtle background-only contrast

**Fallback logic**
- if logo blocked: sender name + title باید همچنان کافی باشد
- if icon missing: category text remains
- if dark mode shifts colors: borders and text hierarchy still hold

**Safe image/text usage**
- image only for brand mark/icon
- never put title text inside image
- alt text must be present for logo/icon assets

**Responsive behavior**
- padding reduce to 20px on mobile
- logo switch to glyph/compact when width is tight
- title scales down one step on mobile

**Accessibility notes**
- minimum AA contrast for title/body
- semantic heading hierarchy where client allows
- meaningful alt text
- avoid color-only status signaling

## 17) Success Criteria

سیستم نهایی زمانی موفق است که:
- با هویت واقعی Loomera در ZIP و repo align باشد
- trusted, calm, refined و readable بماند
- در Gmail / Outlook / mobile clients نشکند
- از tokenهای واقعی رنگ و typography استفاده کند
- status differentiation روشن اما کنترل‌شده داشته باشد
- با domain/email sender system هماهنگ باشد
- in-app notification surfaces را هم با همان منطق پوشش دهد
- برای design و implementation هر دو handoff-ready باشد

## Mini Handoff Spec — Design Team
- یک master architecture بسازید و همه‌ی familyها را از همان derive کنید.
- default family را `softly branded reassurance` نگه دارید.
- فقط payment/auth/support/partner familyها variation محسوس داشته باشند.
- full logo را exceptional نگه دارید.
- headerها را utility surface ببینید، نه canvas برای brand expression.

## Mini Handoff Spec — Frontend / Email Implementation Team
- ابتدا `transactional-email-header` را به‌عنوان base component بسازید.
- variantها را با props/state map کنترل کنید: `type`, `status`, `brandMode`, `showIcon`, `compact`, `mobileSafe`.
- logo asset set: `full`, `compact`, `glyph`, `dark-safe`.
- output HTML email را table-safe نگه دارید و copy را از image جدا کنید.
- in-app surface را CSS-token-based و logo-light پیاده‌سازی کنید.
