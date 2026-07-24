# Loomera Dashboard Visual Kit

نسخه: 1.0  
وضعیت: source-ready / handoff-ready  
زبان اصلی: فارسی  
برند: Loomera

---

## 1) Source Review Summary

### جمع‌بندی کوتاه
Dashboard در Loomera باید یک لایه‌ی **operational clarity** باشد؛ نه یک سطح brand-heavy یا marketing-like. در هویت فعلی Loomera، اعتماد از طریق **وضوح، ساختار، دقت، تایپوگرافی خوانا، رنگ‌های کنترل‌شده و hierarchy درست** ساخته می‌شود؛ نه از طریق تزئین یا تکرار لوگو.

### dashboard باید از چه brand elementهایی استفاده کند
- logo system فقط در shell
- palette بنفش-محور با neutralهای گرم
- accent سبز کنترل‌شده برای reassurance / wellness cue
- typography sans-led برای UI و data
- placeholder و empty-stateهای low-noise و utility-first

### tone dashboard
- calm
- trusted
- structured
- readable
- quietly premium
- product-mature

### تفاوت dashboard با checkout، landing و discovery
- **Landing**: برند پررنگ‌تر، کمی expressiveتر
- **Discovery**: تصمیم‌سازی برای انتخاب provider/service
- **Checkout**: trust-heavy و status-led
- **Dashboard**: operational, structured, concise, less branded

### constraintهای اصلی
- logo در content area تکرار نشود
- shell brand restrained بماند
- typography باید tabular/LTR-safe باشد
- chartها باید calm و data-friendly بمانند
- empty stateها باید blame-free و action-supportive باشند
- mobile و RTL باید از ابتدا در ساختار دیده شوند

---

## 2) Dashboard Strategy

### تجربه‌ی مطلوب dashboard در Loomera
- **brand presence level:** medium-low
- **data density level:** medium تا medium-high
- **trust level:** high
- **precision level:** high
- **emotional temperature:** low-to-warm
- **visual restraint level:** high
- **product vs brand balance:** product-first

### تصمیم نهایی
Dashboard Loomera باید بیشتر **operational clarity layer** باشد تا **brand expression layer**.

### چرا
چون هویت Loomera بر پایه‌ی calm confidence, clarity, trust و premium restraint بنا شده است. در dashboard، کاربر باید سریع‌تر بفهمد:
- چه اتفاقی افتاده
- الان چه چیزی مهم است
- چه اقدامی باید انجام دهد
- وضعیت کسب‌وکار / رزرو / مالی / اعلان‌ها چگونه است

### تفسیر اجرایی
- برند در shell دیده می‌شود، نه داخل هر widget
- data surface باید از برند پیروی کند، نه زیر سایه‌ی آن برود
- summary و action از تزئین مهم‌ترند
- dashboard باید usable، mature و quiet بماند

---

## 3) Dashboard Types

### A. Customer Dashboard / Account Dashboard
**هدف:** مدیریت نوبت‌ها، اعلان‌ها، علاقه‌مندی‌ها، پرداخت و حساب کاربری  
**primary information:** نوبت‌های آینده، وضعیت پرداخت، اعلان‌های اخیر  
**secondary information:** پروفایل، روش‌های پرداخت، favorites، تنظیمات  
**action density:** low-to-medium  
**preferred visual emphasis:** next actions + booking history + reassurance

### B. Provider / Salon / Clinic Dashboard
**هدف:** مدیریت رزروها، مشتریان، خدمات، تیم، مالی و فعالیت روزانه  
**primary information:** رزروهای امروز/هفته، مشتریان، سرویس‌ها، درآمد، وضعیت تیم  
**secondary information:** quick actions، alerts، recent activity  
**action density:** medium-high  
**preferred visual emphasis:** KPI row + bookings table + quick actions

### C. Specialist Dashboard
**هدف:** دید سریع شخصی برای برنامه‌ی روز، نوبت‌ها و وضعیت خدمات  
**primary information:** برنامه‌ی امروز، نوبت‌های آینده، سرویس‌های فعال  
**secondary information:** time off، quick actions، reminders  
**action density:** medium  
**preferred visual emphasis:** schedule clarity + today list + next items

### D. Bookings Overview Dashboard
**هدف:** مانیتورینگ و مدیریت نوبت‌ها به‌صورت عملیاتی  
**primary information:** table رزروها، وضعیت‌ها، زمان، provider/specialist، customer  
**secondary information:** filters، range selector، chartهای روند  
**action density:** high  
**preferred visual emphasis:** filter bar + table/list + compact trend chart

### E. Payments / Wallet Dashboard
**هدف:** مرور مالی، wallet، payout، settlement و وضعیت تراکنش‌ها  
**primary information:** available balance، pending payout، payment status، transaction list  
**secondary information:** finance notices، export، receipt access  
**action density:** medium  
**preferred visual emphasis:** balance tiles + finance table + status block

### F. Support / Requests Dashboard
**هدف:** پیگیری درخواست‌ها، پاسخ‌ها و وضعیت رسیدگی  
**primary information:** request status، آخرین پاسخ، موضوع درخواست، زمان آخرین به‌روزرسانی  
**secondary information:** help links، escalation CTA، FAQ path  
**action density:** low-to-medium  
**preferred visual emphasis:** status-led list + support guidance block

### G. Internal / Admin-like Dashboards
**هدف:** نظارت سراسری بر عملیات، اختلاف‌ها، برداشت‌ها، flagها یا review queue  
**primary information:** platform KPIs، flagged rows، pending reviews، finance summaries  
**secondary information:** notes، export، quick drill-down  
**action density:** medium-high  
**preferred visual emphasis:** system KPIs + alerts + ranked tables

### H. Generic Module Dashboard Pattern
**هدف:** الگوی reusable برای هر ماژول dashboard  
**primary information:** یک metric، chart، list یا table اصلی  
**secondary information:** helper line، CTA، status cue  
**action density:** variable  
**preferred visual emphasis:** one dominant payload per card

---

## 4) Dashboard Layout Zones

### A. Shell Header / Page Header
- **هدف:** orientation
- **visual priority:** بالا
- **brand intensity:** medium-low
- **recommended components:** page title، subtitle کوتاه، date range یا context meta
- **spacing direction:** 16 تا 24px عمودی
- **content tone:** concise, orienting

### B. Top KPI / Metric Row
- **هدف:** snapshot سریع
- **visual priority:** very high
- **brand intensity:** low
- **recommended components:** 3 تا 5 KPI card
- **spacing direction:** 12 تا 16px gap
- **content tone:** factual + scan-friendly

### C. Filters / Range / Segmentation Bar
- **هدف:** کنترل state و data scope
- **visual priority:** high
- **brand intensity:** low
- **recommended components:** search, status filter, date range, segment control, clear/reset
- **spacing direction:** 12 تا 16px داخلی، 8 تا 12px بین controls
- **content tone:** explicit, neutral

### D. Chart Area
- **هدف:** فهم روند
- **visual priority:** medium-high
- **brand intensity:** low-to-medium
- **recommended components:** line/area/bar chart + compact legend + helper line
- **spacing direction:** 16 تا 20px
- **content tone:** analytical, calm

### E. Table / List Area
- **هدف:** detail عملیاتی
- **visual priority:** highest در flowهای data-heavy
- **brand intensity:** very low
- **recommended components:** table card، list rows، status chips، row actions
- **spacing direction:** compact but breathable
- **content tone:** direct, operational

### F. Quick Actions Block
- **هدف:** کاهش اصطکاک برای actionهای پرتکرار
- **visual priority:** medium
- **brand intensity:** low-to-medium
- **recommended components:** action tiles, links, primary/secondary actions
- **spacing direction:** 12px gaps
- **content tone:** action-first

### G. Status / Alerts / Notices
- **هدف:** نشان دادن ریسک، وضعیت یا اخطارهای آرام ولی مهم
- **visual priority:** medium-high
- **brand intensity:** low
- **recommended components:** semantic banner، soft alert card، readiness note
- **spacing direction:** 12 تا 16px
- **content tone:** calm, accountable

### H. Secondary Widgets
- **هدف:** حمایت از reading اصلی
- **visual priority:** medium
- **brand intensity:** low
- **recommended components:** ranking widget، breakdown، compact summaries
- **spacing direction:** 12 تا 16px
- **content tone:** concise

### I. Activity Feed / Recent Items
- **هدف:** traceability و recency
- **visual priority:** medium
- **brand intensity:** low
- **recommended components:** latest bookings، latest notifications، latest payments، recent actions
- **spacing direction:** 10 تا 12px stacked
- **content tone:** recent, readable

### J. Empty Module State
- **هدف:** حفظ structure وقتی یک module داده ندارد
- **visual priority:** medium
- **brand intensity:** low
- **recommended components:** title، body، CTA، optional small artwork
- **spacing direction:** title/body/CTA با ریتم 16-8-16
- **content tone:** blame-free, next-step-led

### K. Full Empty Dashboard State
- **هدف:** onboarding، first-session یا no-setup-yet state
- **visual priority:** بالا
- **brand intensity:** medium
- **recommended components:** compact brand lockup، illustration، title، body، CTA
- **spacing direction:** generous
- **content tone:** warm, guided, calm

---

## 5) Dashboard Logo & Brand Presence

### تصمیم اصلی
در dashboard، **logo باید shell-owned باشد**، نه content-owned.

### کدام variant استفاده شود
- **Desktop / expanded shell:** compact logo
- **Collapsed sidebar:** glyph-only
- **Mobile top bar:** glyph-only
- **Major welcome / full empty dashboard:** compact یا full logo فقط یک‌بار

### لوگو دقیقاً کجا حضور داشته باشد
- sidebar head
- desktop shell header
- mobile app bar در حالت glyph-only
- full empty / welcome dashboard

### در content area باید لوگو تکرار شود؟
خیر. تکرار لوگو در content area باعث noise، حس generic SaaS و brand overuse می‌شود.

### brand cue مجاز در widgets
- soft violet tint
- subtle radius / surface treatment
- icon rhythm کنترل‌شده
- shape language مشترک با shell

### کجا glyph مجاز است
- collapsed sidebar
- mobile shell
- loading state
- system-owned mini empty blocks

### کجا glyph noise محسوب می‌شود
- داخل KPI cards
- داخل chart canvas
- کنار table rows
- داخل هر widget header
- داخل bannerها مگر در context system-owned

### treatment مناسب برای empty dashboard shell
- brand lockup فقط یک‌بار در بالا
- سپس artwork + title + body + CTA
- بدون watermark
- بدون logo repeat

### قواعد نهایی
- **dashboard-shell-brand:** compact logo در desktop، glyph در collapsed/mobile
- **dashboard-header-brand:** subtle, one-time, shell-only
- **dashboard-empty-brand-lockup:** فقط در full empty / welcome state
- **dashboard-widget-brand-cue:** tint و shape، نه logo

---

## 6) Color System for Dashboard

### Color Logic پایه
Dashboard باید مستقیماً از tokenهای فعلی Loomera بیاید.

#### Core surfaces
- **background:** `loomera.bg`
- **shell background:** `loomera.bgSubtle`
- **page surface:** `loomera.surface`
- **raised widget surface:** `loomera.surfaceRaised`
- **surface soft:** `loomera.surfaceSoft`

#### Structural colors
- **border:** `loomera.border`
- **divider:** `loomera.divider`
- **text primary:** `loomera.textPrimary`
- **text secondary:** `loomera.textSecondary`
- **text muted:** `loomera.textMuted`

#### Interactive colors
- **primary action:** `loomera.primary`
- **focus ring:** `loomera.focusRing`
- **selection:** `loomera.selection`

#### Calm dashboard-specific tokens
- **dashboardAccent**
- **cardHighlight**
- **calmGlow**
- **bookingHighlight**

### Light Mode Dashboard
- canvas روشن و نرم
- cards سفید یا near-white
- borders visible but quiet
- KPI emphasis با tint نرم، نه solid fill
- selected states با `primarySoft` یا `selection`
- notices با state-soft، نه saturated state colors

### Dark Mode Dashboard
- plum-based surfaces، نه black-based
- widgetها روی `surface` و `surfaceRaised`
- outlineها با `borderSoft` یا `border`
- chartها روی surfaceهای dark-muted، نه glossy
- بدون neon violet
- بدون glow-heavy effect

### KPI Cards
- default: `surface` + `border`
- highlighted: `cardHighlight`
- booking-related: `bookingHighlight`
- avoid: full primary fill for standard metrics

### Charts
- one dominant series = primary
- second series = secondary
- reassurance/positive series = accent یا success
- بیش از 4 رنگ chromatic فعال استفاده نشود
- plot area باید neutral-first بماند

### Tables
- table header = bgSubtle / surfaceSoft
- row hover = surfaceSoft
- selected row = selection
- inline chip = stateSoft + semantic text

### Empty Modules
- base = `surfaceSoft`, `cardHighlight` یا `calmGlow`
- CTA فقط در صورت نیاز واقعی با primary
- artwork هرگز dominant color field نباشد

### Sticky Filters / Headers
- `surface` یا `surfaceRaised` + border نرم
- optional blur خیلی ملایم
- بدون tinted heavy blocks

### Status Banners
- successSoft / warningSoft / errorSoft / infoSoft
- متن روی bannerها باید neutral-safe و readable بماند

---

## 7) Typography for Dashboard

### اصل کلی
Dashboard باید کاملاً **sans-led** بماند. serif فقط برای brand/display moments است، نه برای data UI.

### Role Map

#### dashboard page title style
- **role:** عنوان اصلی صفحه
- **suggested token / class direction:** `heading.h4` / `lm-h4`
- **readability notes:** واضح، concise، بدون display styling

#### section title style
- **role:** عنوان هر بخش یا widget
- **suggested token / class direction:** `heading.h5`
- **readability notes:** semibold و compact

#### KPI label style
- **role:** label متریک
- **suggested token / class direction:** `label.md`
- **readability notes:** secondary و scannable

#### KPI value style
- **role:** مقدار متریک
- **suggested token / class direction:** `component.metric.lg`
- **readability notes:** tabular numerals ضروری

#### delta / status style
- **role:** تغییر نسبت به بازه قبلی یا status meta
- **suggested token / class direction:** `caption.md` یا helper class
- **readability notes:** concise و color-assisted

#### chart label style
- **role:** label plot / legend
- **suggested token / class direction:** `label.md`
- **readability notes:** کوتاه و readable

#### axis / legend style
- **role:** اطلاعات کمکی chart
- **suggested token / class direction:** `caption.md`
- **readability notes:** low emphasis

#### table header style
- **role:** هدر جدول
- **suggested token / class direction:** `component.table.header`
- **readability notes:** bold enough to scan, not loud

#### table cell style
- **role:** بدنه جدول
- **suggested token / class direction:** `component.table.cell`
- **readability notes:** compact but breathable

#### widget title style
- **role:** عنوان widget card
- **suggested token / class direction:** `heading.h5` یا strong label
- **readability notes:** متناسب با density

#### helper / note style
- **role:** توضیح کوتاه، trend note، guidance
- **suggested token / class direction:** `caption.md` یا `body.sm`
- **readability notes:** یک جمله، نه بیشتر

#### empty module title/body style
- **role:** title و body برای حالت خالی
- **suggested token / class direction:** title=`heading.h5`، body=`body.sm`
- **readability notes:** blame-free، short, direct

#### quick action label style
- **role:** label tile یا button
- **suggested token / class direction:** `component.button.md`
- **readability notes:** action-led

### قواعد خیلی مهم برای data

#### metric numbers
- همیشه tabular باشند
- alignment پایدار داشته باشند
- از لحاظ visual size dominant بمانند

#### `.lm-tabular`
در این موارد ضروری است:
- KPI values
- prices / amounts
- wallet balances
- counts
- transaction totals
- settlement values
- chart tooltips اگر numeric-heavy باشند

#### LTR isolate
برای این dataها حتماً `dir="ltr"` + `unicode-bidi:isolate`:
- booking IDs
- payment codes
- transaction references
- phone
- email
- IBAN-like values
- amount strings در بعضی contextها

#### mixed RTL/LTR behavior
- wrapper کلی dashboard RTL بماند
- cellهای code/ID/phone/email isolate شوند
- table structure هرگز به‌خاطر LTR data نشکند
- number blocks alignment-consistent باقی بمانند

---

## 8) KPI / Metric Card System

### size families
- **S:** compact summary tile
- **M:** standard KPI card
- **L:** hero metric / finance total / wallet balance

### hierarchy between label / value / delta
1. label
2. value
3. delta / meta

### use of icon
- optional
- small and quiet
- فقط وقتی scanning را بهتر می‌کند
- icon هرگز از value dominantتر نشود

### use of trend cue
- delta text + semantic color
- optional trend arrow
- sparkline فقط برای trend-specific card، نه KPI عمومی

### use of background highlight
- default: none
- soft highlight: `cardHighlight`
- booking/trust highlight: `bookingHighlight`
- calm emphasis: `dashboardAccent` به‌صورت controlled tint

### positive / negative / neutral states
- **positive:** success text / soft badge
- **negative:** error text / soft semantic area
- **neutral:** muted meta
- **warning:** amber-soft, not loud

### target number of metrics per row
- desktop: 4 standard یا 5 compact
- tablet: 2
- mobile: 1 یا 2 حداکثر

### when a KPI card becomes too dense
وقتی بیش از این داشته باشد:
- یک helper line
- یک secondary number
- یک delta
- یک status cue
- یا بیش از یک action

### card emphasis rules
- فقط 1 یا 2 KPI در هر row می‌توانند visually برجسته باشند
- همه‌ی KPIها نباید highlighted باشند
- card emphasis باید از data priority بیاید، نه از brand رنگی

### component-specific rules

#### total bookings
- tone: stable, core metric
- emphasis: medium-high
- cue: neutral یا soft violet tint

#### upcoming appointments
- tone: operational readiness
- emphasis: medium-high
- cue: bookingHighlight یا calmGlow

#### revenue / payout / wallet balance
- tone: exact, finance-led
- emphasis: high
- cue: L-size card + tabular + finance-safe spacing

#### cancellation / no-show / conversion-like metrics
- tone: analytical, low-drama
- emphasis: medium
- cue: semantic text، نه loud card background

#### provider performance cards
- tone: comparative
- emphasis: medium
- cue: ممکن است mini trend داشته باشد

#### customer summary cards
- tone: account-oriented, lighter than provider dashboard
- emphasis: medium
- cue: summary + next action

---

## 9) Chart System

### chart family recommendations
- **Line:** روند رزرو/درآمد/مشتری در زمان
- **Area:** همان trend در نسخه‌ی softer
- **Bar:** مقایسه دسته‌ها، خدمات، اعضای تیم
- **Donut:** ترکیب وضعیت‌ها یا payment method split
- **Stacked Bar:** ترکیب وضعیت‌های رزرو یا سهم دسته‌ها

### when to use
- line = trend over time
- area = softer trend with one or two series max
- bar = ranked comparison
- donut = simple proportion only
- stacked = composition view

### chart density limits
- بیش از 12 x-point پیش‌فرض در یک view استاندارد نمایش داده نشود
- بیش از 4 series فعال استفاده نشود
- label clutter باید حذف شود

### gridline treatment
- بسیار نرم و کم‌کنتراست
- ترجیحاً horizontal only
- بدون box-heavy plotting frame

### legend treatment
- compact و inline
- short Persian labels
- اگر فضا کم است، legend داخل header/summary قرار بگیرد

### tooltip treatment
- card-like, calm
- 2 تا 3 line max
- value first, context second
- بدون animation سنگین

### axis labeling in Persian
- کوتاه و readable
- روز/هفته/ماه با labels خلاصه
- در RTL خوانا و منظم

### currency / amount formatting
- axis: short money format
- tooltip: full amount format
- numerals: tabular recommended

### date/time formatting
- labels کوتاه روی axis
- details کامل‌تر در tooltip
- consistency across booking/payment reports

### empty chart state
- chart area نباید broken grid بماند
- به empty module تبدیل شود
- title و helper line حفظ شوند

### loading chart state
- skeleton یا chart placeholder
- empty artwork استفاده نشود

### style rules
- calm و readable
- brand-tinted but not over-branded
- dark mode clean و low-glow
- avoid saturated gradients
- avoid high data-ink overload

---

## 10) Table & List System

### header treatment
- soft background
- semibold و compact
- sticky فقط در data-heavy cases

### row density
- desktop: medium density
- mobile: cardified rows

### hover / selected / active states
- hover = `surfaceSoft`
- selected = `selection`
- active = subtle accent cue، نه heavy fill

### zebra or no zebra
- **no zebra by default**
- از divider + hover بهتر استفاده شود

### inline status chips
- short
- semantic-soft
- maximum 1 یا 2 chip در هر row

### action placement
- action اصلی مشخص و محدود
- overflow action secondary
- row action نباید table را noisy کند

### pagination / load more
- operational table: pagination بهتر است
- activity feed / notifications: load more or progressive list

### empty table state
- title/context حفظ شود
- اگر table large است، empty row card داخل همان surface
- اگر widget کوچک است، compact empty module کافی است

### long text handling
- truncate برای columns متراکم
- detail/full text در expanded row یا detail page
- mobile cardها می‌توانند multiline محدود داشته باشند

### numeric alignment
- consistent
- tabular
- amountها، counts و transaction values باید stable باشند

### date/time alignment
- date و time به‌صورت block یکپارچه دیده شوند
- در contextهای مالی/تراکنشی، LTR isolate در صورت نیاز

### mixed RTL/LTR cell handling
- overall table RTL
- code/ID/email/phone/amount LTR isolate
- layout کلی table نباید تغییر کند

### Context-specific rules

#### bookings tables
- columns: customer, service, time, provider/specialist, status, action
- emphasis: status + time clarity

#### payment tables
- columns: amount, method, status, code/reference, date
- emphasis: amount + settlement clarity

#### provider tables
- emphasis: name + readiness/performance

#### activity lists
- compact rows with recency meta

#### support/request lists
- status-led + last response + action path

#### recent items cards
- max 3 یا 4 data point per item

---

## 11) Widget & Module Kit

### 1. Metric Card
- **visual treatment:** white or soft surface card
- **tone:** factual
- **hierarchy:** label > value > delta
- **state behavior:** default / highlighted / semantic delta
- **do:** tabular numerals
- **don’t:** multiple decorative layers

### 2. Trend Card
- **visual treatment:** KPI + micro trend or delta summary
- **tone:** analytical
- **hierarchy:** metric first
- **state behavior:** positive/negative/neutral
- **do:** one insight per card
- **don’t:** overload with stats

### 3. Chart Card
- **visual treatment:** title + helper + chart + compact legend
- **tone:** interpretive
- **hierarchy:** chart dominates body area
- **state behavior:** default / empty / loading
- **do:** helper line where needed
- **don’t:** marketing headline

### 4. Table Card
- **visual treatment:** operational surface
- **tone:** direct
- **hierarchy:** title > controls > table
- **state behavior:** filtered / empty / loading / selected rows
- **do:** support pagination/responsiveness
- **don’t:** desktop-only thinking

### 5. Activity Feed Card
- **visual treatment:** stacked rows with soft separators
- **tone:** recent + traceable
- **hierarchy:** title > items
- **state behavior:** unread / read / empty
- **do:** show time meta clearly
- **don’t:** oversized icons

### 6. Quick Action Card
- **visual treatment:** compact action tile
- **tone:** action-led
- **hierarchy:** icon optional, label primary
- **state behavior:** active / disabled
- **do:** keep labels short
- **don’t:** use long helper paragraphs

### 7. Status Banner
- **visual treatment:** soft semantic banner
- **tone:** calm, accountable
- **hierarchy:** what happened > what next
- **state behavior:** success / info / warning / error
- **do:** actionable line
- **don’t:** long prose

### 8. Filter Bar
- **visual treatment:** grouped controls in raised surface
- **tone:** utility-first
- **hierarchy:** date + segment + search + filters
- **state behavior:** active / reset / collapsed on mobile
- **do:** show active state clearly
- **don’t:** hero-style filter strip

### 9. Segment Control
- **visual treatment:** pill or compact tab row
- **tone:** neutral
- **hierarchy:** equal choices
- **state behavior:** selected / hover / disabled
- **do:** 3 تا 5 item
- **don’t:** over-crowd

### 10. Date Range Control
- **visual treatment:** compact picker or preset selector
- **tone:** precise
- **hierarchy:** active date visible
- **state behavior:** default / selected / custom range
- **do:** integrate with filters cleanly
- **don’t:** hide current scope

### 11. Dashboard Hero / Introduction Card
- **visual treatment:** restrained intro surface
- **tone:** orienting, not promotional
- **hierarchy:** title > short line > CTA optional
- **state behavior:** mostly top-of-page or onboarding only
- **do:** use sparingly
- **don’t:** place on every dashboard subpage

### 12. Compact Summary Tile
- **visual treatment:** mini metric surface
- **tone:** quiet
- **hierarchy:** one number or one state
- **state behavior:** default / selected
- **do:** use in side rails or secondary sections
- **don’t:** overload with actions

### 13. Empty Module Card
- **visual treatment:** low-noise empty surface
- **tone:** blame-free
- **hierarchy:** title > body > CTA
- **state behavior:** context-specific
- **do:** keep artwork optional and small
- **don’t:** make empty state louder than filled state

### 14. Dashboard Welcome Card
- **visual treatment:** onboarding-friendly but restrained
- **tone:** supportive
- **hierarchy:** title > intro > setup CTA
- **state behavior:** first session only
- **do:** useful for no-setup / no-data cases
- **don’t:** keep after maturity

### 15. Provider Profile Completion Card
- **visual treatment:** progress-led module
- **tone:** practical encouragement
- **hierarchy:** completion state > next steps > CTA
- **state behavior:** incomplete / almost done / done
- **do:** show progress clearly
- **don’t:** guilt-based language

### 16. Payout / Billing Summary Card
- **visual treatment:** ledger-like card
- **tone:** exact
- **hierarchy:** available > pending > next payout > CTA
- **state behavior:** normal / delayed / action needed
- **do:** separate available and pending visually
- **don’t:** merge all finance states into one number

---

## 12) Empty Modules & Dashboard Empty States

### تفاوت module-empty و full-page empty
- **dashboard module خالی:** فقط یک widget داده ندارد؛ layout کلی برقرار است
- **full-page empty:** کل dashboard هنوز data/setup ندارد یا first-session است

### چه وقت از placeholder استفاده شود
- وقتی media یا card structure باید حفظ شود
- وقتی widget در حال نمایش یک slot یا shell content است

### چه وقت از empty-state artwork استفاده شود
- وقتی empty بودن نیاز به cue احساسی/جهتی دارد
- برای onboarding, no-results, no-bookings, no-notifications, dashboard-empty

### چه وقت text-only کافی است
- widgetهای کوچک
- finance/support tables کوچک
- chart cardهای جمع‌وجور
- compact admin modules

### level مناسب illustration در dashboard widgets
- low
- بیشتر abstract
- brand visibility پایین
- logo-free by default

### title/body/CTA spacing
- title تا body: 8px
- body تا CTA: 16px
- illustration تا title: 16px

### قواعد state-specific

#### dashboard-empty-module
- generic empty card
- short title/body
- one CTA max

#### dashboard-empty-analytics
- وقتی chart data ندارد
- title: روشن و non-alarming
- body: تغییر بازه یا فیلتر را پیشنهاد دهد

#### dashboard-empty-bookings
- برای no bookings / no appointments
- next step باید روشن باشد: start setup / open booking flow / check another range

#### dashboard-empty-wallet
- wallet یا payout setup نشده
- CTA: افزودن روش پرداخت / تکمیل اطلاعات مالی

#### dashboard-empty-support
- هنوز درخواستی ثبت نشده
- CTA: ثبت درخواست

#### dashboard-empty-generic
- fallback calm state
- بدون blame
- بدون decorative treatment

---

## 13) Copy & Tone Layer

### اصول copy برای dashboard
- کوتاه
- واضح
- status-led
- calm
- handoff-friendly
- not promotional

### dashboard intro line
باید context بدهد، نه pitch.  
نمونه: `مرور سریع وضعیت امروز، رزروها و اقدام‌های بعدی`

### KPI helper notes
- کوتاه
- comparative یا scope-led
- مثال: `نسبت به ۷ روز گذشته`

### filter helper line
- در صورت نیاز
- مثال: `بازه و وضعیت فعال روی جدول و نمودار اثر می‌گذارد.`

### chart explanation line
- فقط وقتی ambiguity هست
- مثال: `این نمودار روند رزروها را در بازه‌ی فعال نشان می‌دهد.`

### table empty state line
- مثال: `در این بازه موردی برای نمایش وجود ندارد.`

### quick action labels
- verb + object
- مثال:
  - `افزودن نوبت جدید`
  - `ثبت مشتری جدید`
  - `مدیریت زمان‌ها`
  - `مشاهده گزارش‌ها`

### onboarding/setup dashboard lines
- warm but restrained
- مثال: `برای شروع، اطلاعات اصلی را کامل کنید تا dashboard تصویر دقیق‌تری نشان دهد.`

### provider dashboard guidance lines
- practical
- مثال: `برای مرور دقیق‌تر امروز، رزروهای آینده و وضعیت مالی را هم بررسی کنید.`

### status banner tone
- calm, direct, accountable
- structure: what happened + impact + next step

### operational notices tone
- concise
- one line if possible
- no pressure language

### rules کلی
- titleها: 2 تا 5 کلمه
- helper text: فقط در صورت نیاز واقعی
- notice و alertها ترجیحاً یک‌خطی یا دوخطی کوتاه
- تعادل clarity و quietness با حذف hype و کلی‌گویی حفظ شود

---

## 14) Mobile Dashboard Rules

### header compression
- subtitle اول حذف شود
- logo به glyph-only برسد
- page title باقی بماند

### logo treatment
- glyph-only برای mobile top bar
- no wordmark in tight layouts

### KPI stack behavior
- 1 یا 2 card per row
- یکی از KPIها اگر واقعاً مهم‌تر است، بالاتر از بقیه قرار بگیرد

### chart simplification
- labelها کمتر شوند
- chartهای multi-series ساده شوند
- در صورت نیاز sections به accordion/card stack تبدیل شوند

### table-to-card transformations
- tableها در mobile به card row تبدیل شوند
- status بالا باشد
- 3 تا 4 fact اصلی نمایش داده شود
- action پایین card قرار بگیرد

### sticky filter behavior
- compact pill bar یا bottom sheet filter
- active state همیشه visible بماند

### empty module behavior
- artwork کوچک‌تر شود
- CTA thumb-reachable باشد

### action placement
- primary action نزدیک ناحیه‌ی قابل‌دسترس
- secondary actionها inline یا داخل menu

### spacing priorities
- scan rhythm مهم‌تر از visual flourish
- ریتم spacing پیشنهادی: 12 تا 16px

### tap target requirements
- همه‌ی chip/button/tileها comfortable tap size داشته باشند
- controls فشرده ولی نه cramped

### scroll rhythm
- summary → detail → action
- از تکرار کارت‌های هم‌شکل بدون hierarchy پرهیز شود

### RTL behavior در mobile data views
- کلیت UI RTL
- data fragmentهای LTR isolate
- icons و affordanceها در inline-start مناسب بنشینند

---

## 15) Design Directions

### Direction 1: Minimal Operational Calm
**توضیح کوتاه:**  
Dashboard بسیار restrained با brand tint کم و emphasis کامل روی داده و structure.

**مزیت:**  
خیلی usable، mature و کم‌نویز.

**ریسک:**  
ممکن است کمی generic یا بیش از حد خشک به‌نظر برسد.

**مناسب بودن برای Loomera:**  
خوب، اما کمی کمتر از حد مطلوبِ brand warmth.

### Direction 2: Softly Branded Data UI
**توضیح کوتاه:**  
Dashboard data-heavy با brand tintهای کنترل‌شده، shell-branded و widgetهای quietly premium.

**مزیت:**  
بهترین تعادل بین usability و identity.

**ریسک:**  
اگر accentها زیاد شوند، از calmness فاصله می‌گیرد.

**مناسب بودن برای Loomera:**  
بسیار مناسب.

### Direction 3: Premium Product Analytics
**توضیح کوتاه:**  
نسخه‌ای polishedتر و executiveتر با hierarchy قوی‌تر و analytics-driven surfaces.

**مزیت:**  
اعتماد و maturity بالا، مناسب finance/admin.

**ریسک:**  
برای dashboardهای روزمره ممکن است کمی formal یا heavy شود.

**مناسب بودن برای Loomera:**  
برای بعضی contextها عالی، ولی base system نباید فقط این باشد.

---

## 16) Final Recommendation

### Direction نهایی
**Softly Branded Data UI**

### dashboard Loomera باید دقیقاً چه balanceی داشته باشد
- shell slightly branded
- content strongly product-first
- calm hierarchy
- readable metrics
- tables and lists as core operational surfaces
- chartها secondary but useful

### brand presence نهایی
- low-to-medium
- shell-led
- widget-level subtle only

### color intensity
- controlled
- mostly neutral + soft violet tint
- accent green فقط برای cues محدود

### metric emphasis
- strong but quiet
- size + spacing + tabular numerals مهم‌تر از background noise

### chart style
- calm
- lightly tinted
- limited color set
- readable in dark and light

### empty modules
- utility-first
- artwork optional and restrained
- full empty dashboard only place for slightly stronger onboarding feel

### چرا این گزینه درست‌تر است
چون Loomera باید در dashboard حس **structure, trust, clarity, product maturity و quiet confidence** بدهد. این direction هم هویت برند را حفظ می‌کند، هم اجازه نمی‌دهد dashboard به یک سطح decorative یا generic SaaS تبدیل شود.

---

## 17) Handoff Spec

### A. برای Design Team

#### brand rules
- brand در shell دیده شود، نه در همه‌ی modules
- logo در content area تکرار نشود
- tintهای برند نرم و کنترل‌شده بمانند

#### data visualization rules
- هر chart فقط یک داستان اصلی بگوید
- max 4 series فعال
- legend compact
- gridlines نرم و کم‌کنتراست

#### metric / table / widget rules
- KPIها tabular و hierarchy-driven باشند
- tableها readable و action-safe بمانند
- widgetها یک dominant payload داشته باشند

#### spacing and emphasis rules
- ریتم sectionها 16 تا 24px
- فقط 1 یا 2 emphasis point در هر viewport
- summary بالاتر از detail، detail بالاتر از decoration

#### empty-state / placeholder rules
- module empty = low-noise
- full empty = welcome/setup capable
- placeholder = structure-preserving
- empty artwork = context-softening

### B. برای Frontend Team

#### component naming suggestions
- `dashboard-page-header`
- `dashboard-kpi-card`
- `dashboard-chart-card`
- `dashboard-table-card`
- `dashboard-activity-feed`
- `dashboard-filter-bar`
- `dashboard-empty-module`
- `dashboard-status-banner`
- `dashboard-quick-actions`
- `dashboard-summary-tile`

#### class / token usage direction
- از tokenهای Loomera برای surface, border, text, focus, state و special accents استفاده شود
- `dashboardAccent`, `cardHighlight`, `calmGlow`, `surfaceSoft`, `bookingHighlight` فقط controlled مصرف شوند
- legacy aliasها و namingهای قدیمی به naming شفاف Loomera remap شوند

#### dark / light mode notes
- light = surface-led, luminous, soft
- dark = plum-based, not black-based
- no neon glow

#### RTL / LTR handling
- wrapper کلی RTL
- code/ID/phone/email/amount با isolate LTR
- `.lm-tabular` برای metrics و money و count

#### chart implementation notes
- loading = skeleton
- no data = empty module
- empty artwork برای chart loading استفاده نشود
- axis labels کوتاه بمانند

#### empty module logic
- اگر data نداریم ولی context مشخص است → state-specific empty
- اگر media نداریم → placeholder
- اگر فقط loading است → skeleton

#### responsive behavior notes
- desktop table → mobile cards
- filter bars در mobile compact یا sheet-based
- chartها در small screens simplified شوند

---

## 18) Deliverables

این Dashboard Visual Kit شامل این خروجی‌هاست:

1. dashboard visual strategy  
2. dashboard type mapping  
3. layout zones spec  
4. color rules for dashboard  
5. typography rules for dashboard  
6. KPI card system  
7. chart system  
8. table/list system  
9. widget/module kit  
10. empty module rules  
11. mobile dashboard rules  
12. final recommended direction  
13. design handoff  
14. frontend handoff  
15. summary-ready version برای docs/product یا docs/design-system

---

## 19) Summary-Ready Version

Dashboard Loomera باید یک **softly branded operational UI** باشد؛ یعنی shell برند را حفظ کند، اما خودِ dashboard بر پایه‌ی **clarity, structure, readability و product maturity** طراحی شود. KPIها باید concise و tabular باشند، chartها باید calm و token-based بمانند، tableها باید surface اصلی عملیات باشند، empty modules باید blame-free و low-noise عمل کنند، و mobile/RTL باید از ابتدا در معماری componentها دیده شوند. نتیجه باید trusted، structured، quietly premium و کاملاً usable باشد؛ نه generic SaaS و نه decorative brand layer.

---

## 20) Suggested File Placement

برای درج در سورس، این فایل می‌تواند در یکی از مسیرهای زیر قرار بگیرد:

- `docs/design-system/loomera-dashboard-visual-kit.md`
- `docs/product/loomera-dashboard-visual-kit.md`
- `design-system/handbook/loomera-dashboard-visual-kit.md`

---

## 21) Suggested Companion Assets

برای اجرای کامل این kit، این اسناد باید کنار آن به‌عنوان source of truth باقی بمانند:
- Mini Brand Guideline
- Design Tokens
- Typography Handoff
- Product Shell Logo System
- Checkout Branding Kit
- Placeholder Set
- Empty State Illustration System
- Brand Voice Guide
- Microcopy System
- Core Copy Pack
