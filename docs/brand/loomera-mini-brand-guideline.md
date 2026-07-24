# Loomera Mini Brand Guideline

نسخه: 1.0  
زبان اصلی: فارسی  
وضعیت: source-ready / handoff-friendly

---

## 1) Brand Snapshot

### برند چیست
Loomera یک پلتفرم discovery + booking برای خدمات beauty، aesthetic treatments، massage و wellness است؛ برندی که باید انتخاب را روشن‌تر و رزرو را آرام‌تر، دقیق‌تر و قابل‌اعتمادتر کند. این تعریف با Brand Voice Guide و Core Copy Pack هم‌راستاست و در هر دو روی clarity، trust، precision و friction reduction تأکید شده است.

### برای چه کسانی است
برای کاربرانی که می‌خواهند مرکز، متخصص، خدمت و زمان مناسب را سریع اما با اطمینان انتخاب کنند؛ و برای کسب‌وکارها و ارائه‌دهندگانی که کیفیت تجربه‌ی رزرو را بخشی از کیفیت برند خود می‌دانند.

### چه نوع تجربه‌ای را باید منتقل کند
تجربه‌ی Loomera باید calm، trusted، clear، refined، human و quietly premium باشد؛ یعنی composed نه سرد، premium نه exclusionary، helpful نه robotic، و human نه casual یا noisy.

### 5 تا 7 keyword اصلی برند
- calm
- trust
- clarity
- precision
- refined
- human
- premium but accessible

این کلمات مستقیماً از Brand Voice Guide و Core Copy Pack استخراج شده‌اند.

### Brand Essence
**Loomera انتخاب را روشن‌تر می‌کند تا رزرو خدمات beauty و wellness آرام‌تر، دقیق‌تر و قابل‌اعتمادتر باشد.**

---

## 2) Logo System

### مبنای این بخش
Logo guidance این سند بر اساس assetهای فعلی Loomera که در handoff تصویری موجودند نوشته شده است: wordmark serif-led با نماد برگ/گل سه‌پره و sparkle، در نسخه‌ی full-color و monochrome. در خود repo فشرده‌ی فعلی هنوز favicon و برخی ارجاعات برند به هویت legacy متصل‌اند؛ بنابراین source of truth لوگو باید **asset pack جدید Loomera** باشد، نه favicon فعلی repo.

### Primary Logo
- لوگوی اصلی: wordmark «Loomera» به همراه symbol بالای آن.
- کاربرد: header، landing hero، brand cards، partner-facing assets، cover images.
- ترجیح: استفاده روی زمینه‌های روشن با wordmark بنفش عمیق و symbol چندرنگ.

### Secondary Logo
- نسخه‌ی stacked/compact یا horizontal simplified همان سیستم بصری.
- کاربرد: جاهایی که عرض محدود است ولی هنوز نیاز به wordmark وجود دارد.
- اگر تنها یک نسخه در implementation نگه داشته می‌شود، primary logo باید مرجع اصلی exportها بماند.

### Icon / App Glyph
- app glyph همان symbol مستقل برگ/گل + sparkle است.
- این علامت برای app icon، avatar، favicon، loader، watermark و social/avatar مناسب است.
- از آن‌جا که در assetهای جدید glyph مستقل وجود دارد، glyph باید جانشین favicon legacy repo شود.

### Monochrome Usage
- نسخه‌ی تک‌رنگ مشکی/charcoal برای چاپ تک‌رنگ، emboss، watermark ساده، یا زمینه‌های بسیار شلوغ.
- نسخه‌ی تک‌رنگ روشن برای زمینه‌های بسیار تیره.
- در monochrome، symbol و wordmark باید یک رنگ واحد بگیرند و جلوه‌های gradient حذف شوند.

### Reverse Usage
- روی زمینه‌ی تیره از wordmark روشن و symbol روشن/controlled استفاده شود.
- reverse فقط زمانی مجاز است که contrast کامل حفظ شود و glow باعث محوشدن outlineها نشود.

### Minimum Size Guidance
- full logo برای دیجیتال کمتر از 120px عرض استفاده نشود.
- wordmark + symbol برای موبایل‌های فشرده بهتر است از 144px به بالا بماند.
- app glyph برای favicon/app icon از نسخه‌ی بدون wordmark استفاده شود.
- در اندازه‌های کوچک sparkleها می‌توانند ساده‌سازی شوند، اما فرم اصلی glyph نباید بشکند.

### Clear Space Guidance
- clear space برابر حداقل ارتفاع بخش مرکزی glyph در اطراف لوگو در نظر گرفته شود.
- هیچ متن، badge، border، glow یا عکس نباید وارد این محدوده شود.
- در UI cardها، clear space لوگو از padding کلی کارت جدا حساب شود.

### Logo Do
- از فایل‌های vector/master جدید Loomera به‌عنوان source of truth استفاده کنید.
- از primary logo برای brand touchpointها و از glyph برای app/avatar/favicon استفاده کنید.
- contrast را قبل از استفاده روی سطوح tint یا gradient بررسی کنید.
- نسبت لوگو را ثابت نگه دارید.

### Logo Don’t
- از favicon یا آیکن legacy داخل repo به‌عنوان لوگوی Loomera استفاده نکنید.
- لوگو را stretch، rotate، outline، shadow-heavy یا recolor تصادفی نکنید.
- glyph را با آیکن‌های cliché beauty جایگزین نکنید.
- sparkle را به decorative noise تبدیل نکنید.

### جمع‌بندی اجرایی
از نظر سیستم، لوگوی Loomera باید **refined + organic + controlled** بماند؛ یعنی symbol می‌تواند soft و luminous باشد، اما اجرای آن در محصول باید تمیز و کم‌تزئین بماند تا با voice و token system سازگار باشد.

---

## 3) Color System Summary

### Color Direction
پالت Loomera بر محور Soft Violet و طیف‌های لطیف violet ساخته شده، با یک accent سبز طبیعی برای cues مربوط به wellness/trust و خانواده‌ی neutral گرم و refined برای متن و ساختار. در design tokens، Soft Violet با hex `#886FD6` به‌عنوان primary brand color تعریف شده و نقش «هویت اصلی برند / لوگو / marketing accents» را دارد؛ در کنار آن Lilac Mist `#B49AE6` به‌عنوان لایه‌ی دوم برند و Sage Bloom `#A7C8A1` به‌عنوان accent طبیعی آمده است. همچنین Slate Plum `#57526E` و Pearl White `#F7F6FA` برای متن و سطح‌ها تعریف شده‌اند.

### Primary Brand Color
- **Soft Violet — `#886FD6`**
- نقش: هویت اصلی برند، لوگو، accentهای اصلی مارکتینگ.
- در محصول، معادل عملیاتی primary در light mode روی `#735CBE` و در dark mode روی `#A688E6` نشسته است.

### Secondary Brand Color
- **Lilac Mist — `#B49AE6`**
- نقش: لایه‌ی دوم برند، پس‌زمینه‌های لطیف، glow و secondary emphasis.

### Accent
- **Sage Bloom — `#A7C8A1`**
- نقش: accent طبیعی، wellness cue، balance میان بنفش و حس انسانی/ارگانیک. در dark mode نسخه‌ی accent روی `#98BA93` آمده است.

### Neutral Family
- neutral scale از سفید تا plum تیره تعریف شده و text-safe ترین رنگ‌ها در usage notes مشخص شده‌اند: `#2E2A3C`، `#57526E`، `#7A738F`، `#FFFFFF`، `#F5F2FA` و `#1B1826`. این یعنی متن اصلی و ثانویه باید روی همین خانواده بماند، نه روی tintهای بنفش یا سبز.

### Surface / Background Family
- light mode: `bg #FCFBFE`، `bgSubtle #F7F6FA`، `surface #FFFFFF`، `surfaceSoft #F4F1F8`
- dark mode: `bg #16131F`، `bgSubtle #1D1928`، `surface #211C2E`، `surfaceRaised #2A2438`
- این ساختار نشان می‌دهد محصول باید luminous و soft باشد، نه stark white یا pitch black.

### State Colors
- success: `#5F9A73` / soft `#EEF7F0`
- warning: `#B88235` / soft `#FDF3E4`
- error: `#C85C6B` / soft `#FCECEF`
- info: `#5E80C8` / soft `#EDF3FC`
- در dark mode همه‌ی stateها نسخه‌ی deep و readable دارند.

### Light Mode Summary
- brand actionها با `primary #735CBE`
- selected/focus با `focusRing #C1A8F0` و `selection #EDE6FB`
- card highlight و calm glow با violet tintهای بسیار روشن
- accent wellness برای booking highlight و salon card accent.

### Dark Mode Summary
- primary روشن‌تر و قابل‌خواندن‌تر شده: `#A688E6`
- سطوح تیره plum-based هستند نه black-based
- link و focus هنوز بنفش‌اند تا memory برند حفظ شود
- accent و special surfaces با green/plum soft background تنظیم شده‌اند.

### نقش هر گروه رنگ در برند و محصول
- **Brand violet**: identity, CTA, links, focus, selection.
- **Secondary/lilac**: softness, layering, highlights.
- **Sage accent**: trust, wellness, booking reassurance.
- **Neutrals**: structure, text, depth, hierarchy.
- **State colors**: semantic messaging با لحن آرام و غیرalarmist.

### Color Usage Do / Don’t
**Do**
- متن اصلی را روی neutralهای text-safe نگه دارید.
- primary action در light mode را با `#735CBE` + white text اجرا کنید.
- accent sage را برای trust/wellness cue و background relief استفاده کنید.
- glow و lilac را controlled و در لایه‌های ثانویه نگه دارید.

**Don’t**
- از Lilac Mist یا Iris Glow برای body text استفاده نکنید.
- برند را با pinkهای legacy یا neon beauty cues مخلوط نکنید.
- از green accent به‌عنوان primary CTA استفاده نکنید.
- dark mode را با black خالص یا purple oversaturation خراب نکنید.

### Text-safe vs Accent-only
- **Text-safe:** `#2E2A3C`, `#57526E`, `#7A738F`, `#FFFFFF`, `#F5F2FA`, `#1B1826`
- **Accent / background only:** `#B49AE6`, `#DCCFF8`, `#A7C8A1`, `#F3EEFB`, `#F1F7EF`

---

## 4) Typography Summary

### Brand Typography Direction
تصمیم نهایی typography روشن است: **Brand / wordmark serif-led** و **Product UI sans-led**. خانواده‌ی اصلی Yekan Bakh است، fallbackها Vazirmatn و Inter هستند و Source Serif 4 به‌عنوان optional display accent برای brand/display تعریف شده است.

### Product Typography Direction
- product UI باید sans-led و readable باشد.
- headings محصول هم در توکن‌ها روی family UI نشسته‌اند، نه serif؛ یعنی serif بیشتر برای brand moments، display accents و wordmark است.

### Font Families
- **UI / sans:** `Yekan Bakh`, `Vazirmatn`, `Inter`, ...
- **Display / Brand:** `Source Serif 4`, Georgia, Times New Roman, serif.

### Display vs UI Usage
- display.xl و display.l در tokens با family display تعریف شده‌اند.
- headingها، bodyها، labelها، buttonها، inputها و table roles همگی روی family UI هستند.

### Hierarchy Summary
- Display XL: 64 / 72
- Display L: 52 / 60
- H1: 40 / 52
- H2: 32 / 44
- H3: 28 / 40
- H4: 24 / 34
- H5: 20 / 30
- Body L: 18 / 32
- Body: 16 / 28
- Body Small: 14 / 24
- Label: 13 / 20
- Caption: 12 / 18
- Button / Input: 15px base roles
- Metric: 32 / 40  
این scale مستقیماً برای product-ready hierarchy طراحی شده است.

### Persian + Latin Rules
- فارسی همیشه tracking صفر.
- در headingهای لاتین بزرگ، tracking منفی مجاز است.
- body فارسی line-height حدود 1.7 داشته باشد.
- display serif در context فارسی در CSS دوباره به UI font fallback می‌شود تا خوانایی در RTL حفظ شود.

### Numbers / LTR inside RTL Rules
- metric و table numbers باید tabular numerals باشند.
- URL، code، booking ID، phone و email داخل UI فارسی باید با `dir="ltr"` و `unicode-bidi:isolate` نمایش داده شوند.
- utilityهای `.lm-ltr`, `.lm-rtl`, `.lm-tabular` برای همین کار در theme تعریف شده‌اند.

### Responsive Type Summary
در mobile scale، display و headingها جمع‌تر می‌شوند: display.xl به 40/48، h1 به 32/40، h2 به 28/36 و h3 به 24/32 می‌رسند. در CSS نیز همین منطق در media query اعمال شده است تا hierarchy حفظ شود ولی UI فشرده نشود.

### Typography Do / Don’t
**Do**
- UI را با Yekan Bakh-led sans نگه دارید.
- brand/display accents را محدود و هدفمند استفاده کنید.
- در فارسی از tracking صفر و line-height باز استفاده کنید.
- اعداد dashboard، قیمت، جدول و metrics را tabular کنید.

**Don’t**
- serif را در بدنه‌ی UI یا فرم‌ها گسترش ندهید.
- از mixed RTL/LTR بدون isolate استفاده نکنید.
- body text را فشرده یا با line-height کم اجرا نکنید.
- لاتین و فارسی را بدون baseline و وزن هماهنگ کنار هم نگذارید.

---

## 5) Voice & Verbal Identity

### Brand Voice Summary
Loomera باید calm، refined، trustworthy، thoughtful، precise و human باشد و با calm confidence صحبت کند؛ یعنی تصمیم‌گیری را بدون فشار روشن کند، رزرو را قابل‌اسکن و support را مسئولانه نگه دارد.

### Tone Keywords
- calm
- clear
- refined
- trustworthy
- thoughtful
- reassuring  
این‌ها هم در Brand Voice Guide و هم در Mini Voice Board تکرار شده‌اند.

### Voice Formula
**Calm clarity + thoughtful precision + human reassurance**

### 5 Writing Principles
1. Reassure before you persuade.
2. Clarity is part of care.
3. Premium comes from restraint.
4. Beauty language should feel modern, never cliché.
5. Every sentence should reduce friction.

### 5 Writing Do / Don’t
**Do**
- واضح بنویسید، نه vague.
- کاربر را با «شما» خطاب کنید.
- CTA را action-led و explicit نگه دارید.
- در لحظه‌های حساس structure داشته باشید: what happened + impact + next step.
- متن را کوتاه ولی کامل بنویسید.

**Don’t**
- pushy یا over-promotional بنویسید.
- cliché beauty language به‌کار ببرید.
- از «تو» در context محصول/تراکنش استفاده کنید.
- از emoji در product copy استفاده کنید.
- از عباراتی مثل «شروع تجربه»، «بدرخش»، «شگفت‌زده شو» استفاده کنید.

### CTA Style Summary
CTAها باید direct، short و outcome-oriented باشند. نمونه‌های approved: «رزرو نوبت»، «ادامه»، «تأیید و ادامه»، «پرداخت و ثبت نهایی»، «مشاهده جزئیات»، «تغییر فیلترها».

### 5 Sample Approved Phrases
- رزرو نوبت
- جزئیات رزرو قبل از پرداخت نهایی نمایش داده می‌شود.
- نوبت شما ثبت شد.
- نتیجه‌ای با این فیلترها پیدا نشد. می‌توانید فیلترها را تغییر دهید.
- پرداخت کامل نشد. مبلغی کسر نشده است. لطفاً دوباره تلاش کنید.

### 5 Phrases to Avoid
- بهترین انتخاب شما
- بدرخشید
- جادوی زیبایی
- شروع تجربه
- بزن بریم

---

## 6) Brand in Product

### Booking Flow Feeling
step-based، supportive، confidence-building؛ کاربر باید حس کند در هر قدم orientation و reassurance دارد، نه عجله.

### Checkout Tone
highly precise، explicit، status-led و easy to scan. checkout باید ambiguity را کم کند، نه glamour اضافه کند.

### Support Tone
empathetic، practical، accountable و calm. ابتدا همدلی، بعد توضیح روشن، بعد next step.

### Dashboard Tone
product-functional، concise و trusted. metricها باید readable، textها explicit و actionها short باشند. این جهت با metric role، table typography و short-form microcopy هماهنگ است.

### Empty State Feeling
gentle corrective + helpful. خالی بودن صفحه نباید blameful باشد؛ باید next action روشن پیشنهاد دهد.

### Notification Tone
concise، useful و respectful of attention؛ بدون urgency theater و بدون فشار احساسی.

---

## 7) Visual Direction Summary

### Overall Visual Mood
soft، luminous، composed، quietly premium. ترکیب violet-led palette، surfaceهای روشن و plum-based dark mode، و typography sans-led در محصول این mood را می‌سازد.

### Shape Language
rounded و refined، نه sharp و technical. در CSS typography system نیز radiusها و button/card treatment نرم و controlled هستند.

### Spacing Personality
generous ولی نه decorative؛ spacing باید clarity بسازد، نه emptiness. line-heightهای body و heading scale همین intent را تقویت می‌کنند.

### Texture / Glow / Softness Direction
- glow فقط soft highlight باشد، نه neon effect.
- lilac و iris highlight برای selection/focus/background accent مناسب‌اند.
- softness باید به readability کمک کند، نه hierarchy را تضعیف کند.

### Premium Cues
- restraint در رنگ و copy
- serif فقط در brand moments
- neutralهای گرم به‌جای grayهای سرد
- surfaces تمیز و contrast کنترل‌شده
- interactionها روشن و polished.

### What to Avoid Visually
- pink/glam legacy look
- آیکن‌های cliché salon
- gradients پر سروصدا
- shadowهای سنگین
- typography شلوغ یا mixed-brand fonts
- black/white های سخت و بدون لطافت

---

## 8) Quick Usage Rules

### Logo Usage Quick Rules
- primary logo برای brand surfaces
- glyph برای app/avatar/favicon
- monochrome فقط در چاپ، watermark یا سطوح محدود
- legacy favicon repo استفاده نشود

### Color Usage Quick Rules
- primary CTA: violet operational token
- accent sage: reassurance / wellness / supportive surfaces
- text فقط روی text-safe neutrals
- lilac/highlight برای emphasis سطح دوم، نه body text

### Typography Quick Rules
- UI = Yekan Bakh-led sans
- brand/display = Source Serif 4 فقط در نقاط محدود
- فارسی tracking صفر
- body line-height باز
- numbers/table/metrics = tabular
- LTR data داخل RTL = isolate

### Copy Quick Rules
- clarify > reassure > guide
- CTA = فعل + موضوع
- احترام با «شما»
- بدون cliché beauty، hype یا jargon اداری
- در error/payment: چه شد + اثر + قدم بعدی

### UI Tone Quick Rules
- booking = calm + guided
- checkout = precise + explicit
- support = empathetic + accountable
- empty state = calm + next action
- notification = short + respectful

---

## 9) Implementation Notes

### برای Design Team
- asset pack جدید Loomera باید source of truth لوگو باشد.
- color decisions باید از `loomera_design_tokens.json` و `loomera-tailwind-theme.ts` خوانده شوند، نه از کلاس‌های legacy یا نمونه‌های قدیمی.
- serif را فقط در brand/display moments نگه دارید؛ dashboard و flows باید sans-led باقی بمانند.
- glow، lilac و badge tones را subtle نگه دارید.

### برای Frontend Team
- `loomera-typography.css` باید بعد از `output.css` در `templates/base.html` لود شود و `loomera-tailwind-typography.ts` در theme extension وارد شود.
- از token names جدید Loomera استفاده کنید؛ aliasهای legacy فقط موقت باشند.
- utilityهای `.lm-ltr` و `.lm-tabular` در فرم‌ها، booking IDها، قیمت‌ها و جدول‌ها اجباری‌اند.
- current repo هنوز title، favicon و بعضی کلاس‌ها/متن‌ها را با legacy brand نگه داشته؛ cleanup باید قبل از freeze برند انجام شود.

### برای Product / Content Team
- Brand Voice Guide منبع ruleهاست، Microcopy System منبع line-level execution است، و Core Copy Pack منبع message architecture برای surfaceهاست.
- در onboarding، booking، checkout، support و notifications، versionهای status-led و explicit را ترجیح دهید.
- language scope باید beauty + aesthetic treatments + massage + wellness را پوشش دهد، نه فقط salon-first framing.

### Source of Truth در Repo
این فایل‌ها باید مرجع اصلی باقی بمانند:
- `loomera_design_tokens.json`
- `loomera-tailwind-theme.ts`
- `loomera-typography-handoff.md`
- `loomera-typography.tokens.json`
- `loomera-typography.css`
- `loomera-brand-voice-guide.md`
- `loomera-microcopy-system.md`
- `loomera-core-copy-pack (2).md`
- `base.html.snippet.html`

### Namingهایی که باید یکدست شوند
در بررسی repo فشرده، این legacyها هنوز دیده می‌شوند و باید یکدست شوند:
- brand nameهای `هویت قبلی پروژه` در titleها، auth/support/privacy و footer
- utility/token aliases با نام `legacy-design-namespace-*`
- favicon فعلی repo که هنوز با هویت جدید Loomera align نیست
- copyهای generic قدیمی که Core Copy Pack هم اصلاحشان را پیشنهاد کرده است. این alignment fix در خود Core Copy Pack هم صریحاً آمده است.

---

## 10) Deliverables

این Mini Brand Guideline شامل این deliverableهاست:
1. Mini Brand Guideline کامل
2. خلاصه لوگو
3. خلاصه رنگ
4. خلاصه تایپوگرافی
5. خلاصه voice
6. quick rules page
7. implementation notes
8. نسخه‌ی summary-ready برای `docs/brand/`

---

## 11) Output Style Check

این سند عمداً:
- structured است
- concise اما واقعی است
- moodboard صرف نیست
- rule-driven و product-usable است
- برای design، frontend، product، content و marketing قابل رجوع است

---

## 12) Success Criteria Check

این guideline زمانی موفق است که:
- هویت Loomera را بین assetها، tokenها، typography و copy یکدست کند.
- تیم design و frontend بدانند چه چیز source of truth است.
- تیم product/content بدانند هر surface باید با چه لحن و ساختاری نوشته شود.
- شکاف بین brand identity جدید و product reality قدیمی repo را روشن کند.
- concise بماند، ولی سطحی نشود.

---

## Appendix — Summary-Ready Version for `docs/brand/`

### Loomera in one paragraph
Loomera یک پلتفرم discovery + booking برای خدمات beauty، aesthetic treatments، massage و wellness است. هویت آن باید calm، clear، trusted، refined و human باشد. در تصویر، این هویت با violet-led palette، accent سبز طبیعی، surfaceهای soft و typography serif-led برای brand و sans-led برای UI ساخته می‌شود. در کلام، Loomera با calm confidence صحبت می‌کند: clarify می‌کند، reassure می‌کند و guide می‌کند. در محصول، booking باید آرام و step-based باشد، checkout باید دقیق و status-led باشد، و support باید همدلانه و مسئولانه بماند. source of truth این برند فایل‌های Loomera tokens/theme/typography/voice/microcopy/core-copy هستند؛ نه legacy namingها، نه favicon فعلی repo، و نه کلاس‌ها و copyهای قدیمی برند قبلی/namespace قدیمی.
