# Loomera Loader / Splash System

نسخه: 1.0  
وضعیت: source-ready / handoff-ready  
زبان: فارسی  
برند: Loomera

---

## 1) Source Review Summary

### جمع‌بندی کوتاه
هویت فعلی Loomera در سورس و پکیج‌های همراه، یک هویت **calm، trusted، refined، precise و quietly premium** است. از نظر بصری، سیستم روی **violet-led palette** با neutralهای گرم، accent سبز کنترل‌شده، سطوح نرم، radiusهای generous و typography **Yekan Bakh-led sans** برای UI بنا شده است. serif بیشتر متعلق به wordmark و brand moments است، نه رابط محصول.

### نقش loading و splash در Loomera
در این محصول، loading نباید یک وقفه‌ی تزئینی باشد؛ باید بخشی از **continuity** تجربه باشد. کاربر در Loomera عمدتاً در contextهای discovery، booking، payment، dashboard و support حرکت می‌کند. پس loading باید:
- ابهام را کم کند
- انتظار را نرم‌تر کند
- ساختار صفحه را حفظ کند
- حس اعتماد را از بین نبرد
- از محتوای واقعی مهم‌تر نشود

### constraintهای مهم از سیستم‌های موجود
- **Shell**: برند در shell دیده می‌شود، نه در هر ماژول.
- **Placeholder Set**: utility-first، logo-free by default، abstract-first.
- **Empty State System**: expressive اما restrained؛ برای loading نباید جایگزین skeleton شود.
- **Checkout Kit**: trust-heavy، explicit، provider-first و platform-assuring.
- **Dashboard Visual Kit**: operational clarity، brand intensity پایین، logo فقط در shell.
- **Logo System**: glyph در shellهای فشرده و loading shellها مناسب‌تر از wordmark است.
- **Typography**: متن‌های loading باید کوتاه، status-led و readable باشند.

### utility-first یا brand-visible؟
Loaderهای Loomera باید **عمدتاً utility-first** باشند و فقط در نقاط خاص، **controlled brand visibility** داشته باشند. یعنی:
- بیشتر loadingها: skeleton / subtle loader / progress
- splash و چند context trust-heavy: brand-visible به‌صورت محدود
- button و inline loading: تقریباً همیشه logo-free

### نکته‌ی مهم از review سورس فعلی
در repo فعلی چند loading هنوز generic یا legacy هستند:
- Font Awesome spinner در booking و wallet actionها
- pulse skeleton عمومی در search sheet
- purple/pink gradientهای قدیمی در چند فرم و کیف پول
- نبود dashboard skeleton system منسجم
- نبود rule روشن برای cold launch / route transition / async state

بنابراین سیستم پیشنهادی باید این پراکندگی را به یک زبان واحد تبدیل کند.

---

## 2) Loader / Splash Strategy

### تصمیم اصلی
در Loomera باید بین **Splash**، **Loader**، **Skeleton**، **Pending State** و **Progress State** مرز روشن وجود داشته باشد.

### splash چه زمانی لازم است
Splash فقط برای این contextها لازم است:
- **cold app launch** یا launch بعد از boot سنگین
- **PWA / app-shell entry** وقتی assets یا session در حال initialize شدن‌اند
- **restoring session** اگر کمتر از چند لحظه طول نکشد

Splash برای route transitionهای عادی، submitهای سبک یا refreshهای کوتاه لازم نیست.

### loader چه زمانی لازم است
Loader وقتی مناسب است که:
- ساختار محتوا از قبل معلوم نیست یا خیلی کوچک است
- عمل کاربر inline است و skeleton معنی ندارد
- انتظار کوتاه تا متوسط داریم
- یک action منفرد در حال انجام است

### skeleton چه زمانی بهتر از spinner است
Skeleton انتخاب اول است وقتی:
- ساختار صفحه، کارت، جدول یا فرم از قبل معلوم است
- فهرست، detail page، dashboard module یا chart در حال loading است
- می‌خواهیم layout shift کم شود
- کاربر باید حس کند «چیزی در حال آمدن است»، نه اینکه «سیستم گیر کرده»

### progress state چه زمانی بهتر از loader است
Progress state بهتر است وقتی:
- فرایند **چندمرحله‌ای** است
- انتظار می‌تواند طولانی شود
- کاربر باید بداند در چه مرحله‌ای است
- payment verification، upload، processing یا multi-step booking اتفاق می‌افتد

### برند در loading چقدر visible باشد
- **low** در 80٪ loadingها
- **medium-low** در splash و full-page pendingهای trust-heavy
- **medium** فقط در app launch و checkout/payment pending full-screen
- **high** هرگز لازم نیست

### motion intensity
- low به‌صورت پیش‌فرض
- subtle و polished
- بدون rotateهای نمایشی، bounce، zoom شدید یا glowهای تهاجمی

### emotional temperature
انتظار در Loomera باید این حس را بدهد:
- «در حال پیش رفتن است» نه «در حال گیر کردن است»
- «سیستم تحت کنترل است» نه «در حال نمایش دادن animation»
- «چند لحظه‌ی آرام» نه «وقفه‌ی بی‌منطق»

فرمول احساسی:
**calm clarity + gentle momentum + low-stress reassurance**

---

## 3) Required Loading Contexts

### A. App Launch Splash
- **هدف:** شروع نرم، اطمینان از load اولیه و تثبیت brand memory
- **treatment:** splash screen + glyph-led motion
- **brand intensity:** medium
- **text:** معمولاً بدون متن؛ در launch طولانی یک support line کوتاه مجاز است
- **logo/glyph:** glyph اصلی؛ full logo فقط در cold launchهای مشخص
- **duration behavior:** فقط وقتی initialization واقعاً محسوس است؛ بدون delay مصنوعی

### B. Auth Loading
- **هدف:** session check، submit auth، restore state
- **treatment:** برای page entry = compact shell loader؛ برای submit = button loading
- **brand intensity:** medium-low
- **text:** entry در صورت نیاز یک line؛ submit بدون متن اضافه جز label button
- **logo/glyph:** entry می‌تواند glyph داشته باشد؛ submit logo-free
- **duration behavior:** submit کوتاه؛ اگر طولانی شد helper line اضافه شود

### C. Route Transition Loader
- **هدف:** حفظ continuity بین صفحات بدون full interruption
- **treatment:** top edge progress line یا shell veil خیلی سبک
- **brand intensity:** very low
- **text:** خیر
- **logo/glyph:** خیر
- **duration behavior:** برای transitionهای کوتاه و سریع؛ نباید به splash تبدیل شود

### D. Search / Discovery Loading
- **هدف:** نشان دادن اینکه query یا filter در حال اعمال است
- **treatment:** skeleton list/card + status line کوتاه
- **brand intensity:** low
- **text:** بله، یک line کوتاه در header/status area
- **logo/glyph:** خیر
- **duration behavior:** skeleton بلافاصله، text در صورت طولانی‌شدن یا تغییر state

### E. Listing / Card Grid Loading
- **هدف:** حفظ grid structure و کاهش shift
- **treatment:** card skeleton
- **brand intensity:** low
- **text:** معمولاً خیر
- **logo/glyph:** خیر
- **duration behavior:** تا دریافت batch اول داده؛ سپس stagger بسیار ملایم در reveal

### F. Service / Provider Detail Loading
- **هدف:** حفظ hierarchy صفحه‌ی detail
- **treatment:** detail page skeleton
- **brand intensity:** low
- **text:** خیر، مگر API طولانی یا partial failure
- **logo/glyph:** خیر
- **duration behavior:** skeleton از hero تا meta و booking box

### G. Booking Flow Loading
- **هدف:** کاهش اضطراب کاربر در انتخاب زمان/خدمت/مرحله بعدی
- **treatment:** hybrid = skeleton + short status copy + stage progress where relevant
- **brand intensity:** low-medium
- **text:** بله، status-led و کوتاه
- **logo/glyph:** خیر در step loading؛ progress line بله
- **duration behavior:** اگر >2.5s شد، helper line یا fallback action

### H. Checkout / Payment Pending State
- **هدف:** ایجاد اعتماد در حساس‌ترین نقطه
- **treatment:** dedicated pending state / progress state
- **brand intensity:** medium
- **text:** بله، title + body کوتاه
- **logo/glyph:** glyph مجاز؛ full logo فقط در shell header، نه مرکز state
- **duration behavior:** اگر callback طولانی شد، state باید actionable بماند و timeout/fallback بدهد

### I. Dashboard Module Loading
- **هدف:** حفظ ساختار عملیاتی dashboard
- **treatment:** module skeleton
- **brand intensity:** very low
- **text:** خیر، مگر module-specific refresh طولانی شود
- **logo/glyph:** خیر
- **duration behavior:** skeleton first؛ در refreshهای ثانویه cross-fade یا thin top progress

### J. Table / Chart Loading
- **هدف:** حفظ خوانایی data surface
- **treatment:** table skeleton / chart skeleton
- **brand intensity:** very low
- **text:** خیر
- **logo/glyph:** خیر
- **duration behavior:** سریع، کم‌حرکت، data-first

### K. Media / Gallery Loading
- **هدف:** نشان دادن slotها و نسبت‌ها تا زمان load media
- **treatment:** media skeleton
- **brand intensity:** low
- **text:** خیر
- **logo/glyph:** خیر
- **duration behavior:** نسبت‌ها باید از ابتدا ثابت باشند

### L. Inline Async Action Loading
- **هدف:** save/update کوچک در context
- **treatment:** inline loader + disabled state + text update
- **brand intensity:** very low
- **text:** بله، یک label کوتاه در صورت نیاز
- **logo/glyph:** خیر
- **duration behavior:** immediate feedback؛ اگر طولانی شد toast یا helper line

### M. Button Loading State
- **هدف:** جلوگیری از دوباره‌کلیک و روشن‌کردن status
- **treatment:** button loading state
- **brand intensity:** none to very low
- **text:** بله، خود label button
- **logo/glyph:** خیر
- **duration behavior:** spinner یا micro loader داخل button؛ width button ثابت بماند

### N. Generic Full-Page Loader
- **هدف:** fallback زمانی که skeleton meaningful نیست
- **treatment:** full-page loader با glyph یا logo-free mark بسیار محدود
- **brand intensity:** medium-low
- **text:** یک line کوتاه مجاز
- **logo/glyph:** glyph مجاز؛ wordmark فقط در app-entry
- **duration behavior:** فقط برای pageهای transitional یا callback-heavy

### O. Generic Section Loader
- **هدف:** loading یک card/section مستقل
- **treatment:** section skeleton یا line-based loader
- **brand intensity:** very low
- **text:** معمولاً خیر
- **logo/glyph:** خیر
- **duration behavior:** short-lived؛ در refreshهای ثانویه حتی lighter

---

## 4) Splash Screen Rules

### آیا full logo یا glyph؟
قاعده‌ی اصلی:
- **default:** glyph
- **cold launch رسمی:** full logo فقط یک‌بار و restrained
- **warm launch / route-level app entry:** glyph-only

### logo placement
- glyph یا logo در مرکز بصری صفحه
- نه خیلی بالا، نه پایین نزدیک safe area
- با فضای خالی generous اطراف

### background treatment
**Light mode**
- base: `bg #FCFBFE` یا `bgSubtle #F7F6FA`
- optional radial tint: `calmGlow #F2ECFE` با شدت پایین

**Dark mode**
- base: `bg #16131F` یا `bgSubtle #1D1928`
- optional calm field: `calmGlow #2C2440`

### motion style
- sequential fade / soft reveal
- slight scale drift بسیار کم
- no spinning logo
- no bounce
- no sweeping glossy gradient

### مدت حضور پیشنهادی
- **cold launch:** تا وقتی app واقعاً آماده شود
- **target visual presence:** حدود 600 تا 1200ms در حالت طبیعی
- **absolute rule:** هیچ delay مصنوعی فقط برای نمایش برند اعمال نشود

### tagline یا support line؟
- **default:** بدون tagline
- **optional support line:** فقط اگر initialization از آستانه‌ی کوتاه عبور کرد
- مثال مناسب: «در حال آماده‌سازی فضای شما»
- بیش از یک خط مجاز نیست

### light / dark mode behavior
- light: luminous, soft, airy
- dark: deep plum-based, calm, non-neon
- در هر دو mode contrast mark باید واضح باشد، اما halo باید restrained بماند

### app launch vs PWA/app shell
- **cold app launch:** glyph + optional full logo signature
- **PWA restore / app shell resume:** glyph-only یا even minimal transition veil
- **in-app route transition:** splash ممنوع

### چیزهای ممنوع در splash
- full-screen animated gradient
- spinner generic در مرکز صفحه
- لوگوی rotating
- sparkleهای زیاد یا twinkleهای تزئینی
- support lineهای marketing-like
- delay عمدی
- CTA داخل splash

---

## 5) Loader Visual Language

### shape language
- soft, rounded, petal-adjacent geometry
- pill, arc, petal-segment, rounded bar
- نه sharp، نه techno-industrial

### motion direction
- gentle upward or inward coherence
- ریتم باید progressive باشد، نه attention-seeking
- اگر sequence داریم، بهتر است از راست به چپ با RTL context هم‌راستا نباشد؛ sequence باید **neutral** بماند، نه directional copy cue

### easing feel
- ease-out نرم برای reveal
- ease-in-out برای loopهای subtle
- از linear طولانی فقط در shimmerهای خیلی ملایم

### density
- low density
- یک عنصر غالب کافی است
- loader نباید compositional center صفحه را شلوغ کند

### line weight
- 1px تا 1.5px برای line-based loaders
- بدون stroke سنگین

### softness
- از radius، tint، contrast پایین و spacing می‌آید
- نه از blur شدید یا glow

### pulse / fade / rotate / draw / shimmer
- **pulse:** مناسب برای inline و stateهای کوچک، با دامنه‌ی کم
- **fade:** بهترین گزینه برای app-loader-primary
- **rotate:** فقط برای micro utility loader در fallback؛ نه برای برند
- **draw:** برای route progress line یا segment line مناسب‌تر از spinner است
- **shimmer:** فقط برای skeletonها، آن هم low-contrast و کند

### چگونه calm و premium بماند
- حرکت کم، نه صفر
- contrast پایین‌تر از CTA
- brand tint کمتر از 15٪ سطح visible loader
- reveal آرام‌تر از interaction animationهای عادی

### چگونه حس generic SaaS spinner نگیرد
- استفاده نکردن از circle spinner پیش‌فرض به‌عنوان الگوی اصلی
- استفاده از petal-derived segment loader برای app-loader-primary
- اتکا به skeleton و progress به‌جای spinner در سطوح محتوایی
- حذف pink/neon/gradient-heavy executionهای قدیمی

---

## 6) Skeleton System

### اصول کلی skeleton
- skeletonها باید **structure-first** باشند
- fidelity در حدی باشد که layout را روشن کند، نه آن‌قدر زیاد که UI fake به نظر برسد
- shimmer پیش‌فرض نیست؛ فقط وقتی به خوانش کمک کند
- baseها باید از surface family بیایند، نه CTA family

### 6.1 Card Skeleton
- **structure:** media block + 2 line title/meta + CTA ghost
- **fidelity:** medium
- **shimmer:** optional low shimmer
- **color:** `surfaceSoft` + `borderSoft`
- **radius:** 1rem تا 1.25rem
- **spacing:** مطابق card واقعی، نه فشرده‌تر
- **better than loader when:** grid/list structure معلوم است

### 6.2 List Item Skeleton
- **structure:** avatar/thumb + 2 text lines + trailing meta chip
- **fidelity:** medium-low
- **shimmer:** ترجیحاً بدون shimmer یا shimmer خیلی کند
- **color:** `bgSubtle` / `surfaceSoft`
- **radius:** 0.875rem تا 1rem
- **spacing:** row height واقعی حفظ شود
- **better than loader when:** search results، support list، notifications

### 6.3 Profile Header Skeleton
- **structure:** avatar circle + name line + subtitle + action pill
- **fidelity:** medium
- **shimmer:** no shimmer یا single sweep بسیار آرام
- **color:** `surfaceSoft` + `calmGlow`
- **radius:** avatar circle، action pill full rounded
- **spacing:** generous
- **better than loader when:** profile / provider header

### 6.4 Detail Page Skeleton
- **structure:** hero/media slab + headline + meta chips + content blocks + booking module
- **fidelity:** medium-high
- **shimmer:** فقط روی media slab یا یک sweep کلی خیلی ملایم
- **color:** `cardHighlight`, `surfaceSoft`
- **radius:** 1.25rem برای hero و cards
- **spacing:** hierarchy واقعی حفظ شود
- **better than loader when:** service/provider detail

### 6.5 Booking Summary Skeleton
- **structure:** selected items, time row, amount rows, sticky CTA ghost
- **fidelity:** high enough to reduce uncertainty
- **shimmer:** minimal
- **color:** `bookingHighlight` mix + `surfaceSoft`
- **radius:** 1rem تا 1.25rem
- **spacing:** summary stack preserved
- **better than loader when:** review / pre-checkout stage

### 6.6 Checkout Form Skeleton
- **structure:** method block, amount rows, trust note, CTA placeholder
- **fidelity:** medium-high
- **shimmer:** no shimmer preferred
- **color:** `surface`, `surfaceSoft`, `borderSoft`
- **radius:** 1rem+
- **spacing:** trust card spacing preserved
- **better than loader when:** payment methods / summary load

### 6.7 Dashboard Metric Skeleton
- **structure:** title label + big metric block + helper line + icon tile
- **fidelity:** medium
- **shimmer:** off by default
- **color:** `cardHighlight` / `surfaceSoft`
- **radius:** 1rem تا 1.25rem
- **spacing:** metric card real proportions
- **better than loader when:** KPI row

### 6.8 Chart Skeleton
- **structure:** title, legend stubs, axes hint, 1 abstract trend line / bars area
- **fidelity:** medium-low
- **shimmer:** خیر
- **color:** `surfaceSoft`, `dashboardAccent` tint بسیار کم
- **radius:** card radius 1.25rem
- **spacing:** chart padding واقعی حفظ شود
- **better than loader when:** analytics modules

### 6.9 Table Row Skeleton
- **structure:** 4 تا 6 cell line + optional avatar dot + action menu ghost
- **fidelity:** medium-low
- **shimmer:** off یا ultra-low sweep
- **color:** `bgSubtle`, `borderSoft`
- **radius:** small cell bars 0.5rem تا 0.75rem
- **spacing:** row height واقعی حفظ شود
- **better than loader when:** bookings/payments tables

### 6.10 Gallery / Media Skeleton
- **structure:** fixed ratio tiles + subtle inner frame
- **fidelity:** low-medium
- **shimmer:** فقط روی image area، آن هم ضعیف
- **color:** `surfaceSoft`, `calmGlow`
- **radius:** متناسب با gallery tile
- **spacing:** ratio-safe
- **better than loader when:** media-heavy surfaces

### rules نهایی skeleton
- در first load طولانی: skeleton
- در refresh ثانویه کوتاه: soft overlay یا cross-fade بهتر از skeleton کامل
- shimmer فقط روی blockهای بزرگ و نه همه‌ی صفحه هم‌زمان
- skeletonها نباید آیکن یا لوگوی برند را تقلید کنند

---

## 7) Color Rules

### tokenهای پیشنهادی برای loading system

#### splash background
- **light:** `bg #FCFBFE`, `bgSubtle #F7F6FA`, optional `calmGlow #F2ECFE`
- **dark:** `bg #16131F`, `bgSubtle #1D1928`, optional `calmGlow #2C2440`

#### loader foreground / accent
- **light primary loader:** `primary #735CBE`
- **light soft accent:** `secondary #9B80E0`
- **dark primary loader:** `primary #A688E6`
- **dark soft accent:** `secondary #C1A8F0`

#### skeleton base
- **light:** `surfaceSoft #F4F1F8`, `bgSubtle #F7F6FA`
- **dark:** `surfaceSoft #251F33`, `bgSubtle #1D1928`

#### skeleton shimmer
- **light:** `borderSoft #ECE8F2` + `calmGlow #F2ECFE`
- **dark:** `borderSoft #312B43` + `calmGlow #2C2440`

#### pending / payment state palette
- base surfaces از `surface`, `surfaceSoft`, `cardHighlight`
- emphasis از `primary`
- trust support از `bookingHighlight` / `accentSoft`
- semantic info only where needed: `info`, `warning`, `error`, `success`

### light mode loading palette
- neutral foreground text: `textSecondary #57526E`
- primary loading mark: `#735CBE`
- soft veil: `#F7F6FA`
- skeleton edge: `#ECE8F2`

### dark mode loading palette
- neutral foreground text: `textSecondary #D4CDE3`
- primary loading mark: `#A688E6`
- soft veil: `#1D1928`
- skeleton edge: `#312B43`

### subdued brand tint usage
- brand tint باید لایه‌ی دوم باشد، نه fill غالب
- loader area نباید شبیه CTA شود
- primary saturation فقط در active focal mark یا thin progress line

### رنگ‌های نامناسب
- gradientهای purple-to-pink قدیمی
- neon violet
- glowهای آبی-بنفش شدید
- سبز به‌عنوان loader primary
- قرمز/amber برای loadingهای خنثی

### rule کلیدی
Loading system باید از palette برند بیاید، اما **primary CTA saturation را نسوزاند**. CTA باید هنوز قوی‌ترین بنفش سیستم باقی بماند.

---

## 8) Logo / Glyph Usage Rules

### اصل کلی
**logo-free by default, glyph where system-owned, wordmark only where trust-owned**

### splash screen
- **default:** glyph
- **cold launch خاص:** full logo یک‌بار و کوتاه
- **no repeated logo loops**

### generic loader
- بهتر است **logo-free** باشد
- اگر full-page system-owned باشد، glyph-led مجاز است
- section/inline/button loaderها باید logo-free بمانند

### button loader
- قطعاً **logo-free**
- فقط micro loader داخل button + label swap

### checkout pending state
- full-screen pending: glyph مجاز
- shell header: compact/full logo طبق checkout rules
- داخل CTA یا amount block: logo ممنوع

### dashboard module loader
- فقط skeleton
- glyph یا logo در widgetها noise محسوب می‌شود

### چه وقت logo usage مفید است
- cold app launch
- auth/app entry با trust moment
- payment pending full-page
- generic full-page loader وقتی صفحه system-owned است و structure نامعلوم است

### چه وقت noise می‌شود
- card grid loading
- button loading
- table/chart loading
- section refresh
- dashboard widgets
- provider/service-specific contexts

### rule نهایی
- **wordmark:** rare
- **glyph:** limited and system-owned
- **logo frequency:** very low

---

## 9) Typography & Copy Rules

### آیا splash text داشته باشد؟
- پیش‌فرض: خیر
- اگر launch از آستانه عبور کرد: یک support line کوتاه
- title و body کامل برای splash لازم نیست

### loader text چه زمانی لازم است
- وقتی action کاربر ممکن است اضطراب‌زا یا مبهم باشد
- وقتی انتظار بیش از لحظه‌ی خیلی کوتاه می‌شود
- وقتی نتیجه transactional است

### pending state title/body چگونه نوشته شود
- **title:** status-led و کوتاه
- **body:** impact + next step یا reassurance
- حداکثر 2 خط body

### processing/payment loading tone
- دقیق، آرام، non-dramatic
- بدون وعده یا اغراق
- بدون «لطفاً منتظر بمانید...»های مبهم مگر در fallback

### search loading / dashboard loading helper line
- search: یک helper line مجاز
- dashboard module: معمولاً بدون helper line
- refreshهای کوچک: text لازم نیست

### max text density
- **button / inline:** 1 line
- **section loader:** 0 تا 1 line
- **full-page pending:** title + یک body کوتاه
- **splash:** صفر یا یک support line

### refinementهای پیشنهادی برای copy

#### به‌جای «در حال آماده‌سازی...»
- **پیشنهادی:** در حال آماده‌سازی فضای شما
- **فشرده‌تر:** در حال آماده‌سازی

#### به‌جای «در حال بارگذاری نتایج...»
- **پیشنهادی:** در حال بارگذاری نتایج
- **helper optional:** فقط گزینه‌های قابل‌رزرو نمایش داده می‌شوند.

#### به‌جای «در حال بررسی پرداخت...»
- **پیشنهادی:** در حال بررسی پرداخت
- **helper optional:** نتیجه تا چند لحظه دیگر نمایش داده می‌شود.

#### به‌جای «در حال به‌روزرسانی...»
- **پیشنهادی:** در حال به‌روزرسانی
- **helper optional:** تغییرات شما در حال اعمال است.

#### به‌جای «کمی صبر کنید...»
- **فقط در fallback:** لطفاً چند لحظه صبر کنید.
- این خط نباید copy اصلی باشد؛ بیشتر fallback انسانی است

### قوانین نوشتن
- ellipsis پیش‌فرض استفاده نشود
- هر خط یک ایده
- status اول، reassurance بعد
- tone همیشه calm و explicit

---

## 10) Motion Rules

### duration ranges
- **micro feedback:** 120–180ms
- **button/inline state shift:** 160–220ms
- **route progress reveal:** 180–260ms
- **section/full-page loader reveal:** 220–320ms
- **primary loader loop:** 900–1400ms
- **skeleton shimmer cycle:** 1800–2200ms

### loop style
- seamless
- low-amplitude
- بدون kick شدید در ابتدای loop

### preferred motion behavior
- fade sequence
- slight opacity breathing
- subtle line travel
- very small scale drift only for splash/glyph loader

### reduced motion
- loop حذف یا بسیار کند شود
- shimmer خاموش یا static gradient شود
- progress line باقی بماند چون informational است
- skeletonها static block بمانند

### accessibility considerations
- animation نباید تنها signal state باشد
- status مهم با text یا semantic role همراه شود
- contrast mark باید کافی باشد
- focus stateها از loading جدا بمانند

### when to use static fallback
- reduced motion فعال
- battery save / low power mode اگر detect شد
- loadingهای طولانی که motion fatigue ایجاد می‌کنند
- data-dense dashboard areas

### shimmer چه زمانی مناسب است
- card grid
- detail hero media
- gallery
- limited list loading

### pulse چه زمانی مناسب است
- inline status dot
- button micro loader
- small utility loader

### motion باید چه زمانی minimal بماند
- dashboard
- table/chart
- settings save
- background refresh
- any repeated context in a session

### اصل حرکتی
Motion در Loomera باید **آرام، polished و low-stress** باشد؛ چیزی که کاربر متوجه کنترل‌شدگی آن می‌شود، نه خود animation را.

---

## 11) Product Context Mapping

### app shell
- **treatment:** splash برای cold launch، route progress برای transitions
- **intensity:** medium در launch، very low در route
- **copy:** معمولاً بدون copy
- **timeout/fallback:** اگر launch طولانی شد support line

### auth
- **treatment:** entry loader یا short shell loader + button loading
- **intensity:** medium-low
- **copy:** کوتاه
- **timeout/fallback:** helper line بعد از آستانه‌ی کوتاه

### search results
- **treatment:** skeleton + status line
- **intensity:** low
- **copy:** بله
- **timeout/fallback:** no-results/limited-results logic بعد از fetch

### provider/service detail
- **treatment:** detail skeleton
- **intensity:** low
- **copy:** خیر
- **timeout/fallback:** error surface if fetch fails

### booking flow
- **treatment:** hybrid = skeleton + progress + short status
- **intensity:** low-medium
- **copy:** بله
- **timeout/fallback:** show helper/fallback actions after longer wait

### checkout/payment
- **treatment:** progress / pending state / button loading
- **intensity:** medium
- **copy:** بله، دقیق
- **timeout/fallback:** explicit retry / wallet / order detail paths

### dashboard metrics
- **treatment:** metric skeleton
- **intensity:** very low
- **copy:** خیر
- **timeout/fallback:** soft empty or stale-data note

### dashboard tables
- **treatment:** table skeleton
- **intensity:** very low
- **copy:** خیر
- **timeout/fallback:** empty table state after data resolve

### dashboard charts
- **treatment:** chart skeleton
- **intensity:** very low
- **copy:** خیر
- **timeout/fallback:** chart unavailable note if needed

### support/messages
- **treatment:** list skeleton + inline action loading
- **intensity:** low
- **copy:** optional in send/update
- **timeout/fallback:** supportive retry copy

### media upload
- **treatment:** progress state + upload tile status
- **intensity:** low-medium
- **copy:** بله
- **timeout/fallback:** actionable retry / remove / continue later

### inline settings save
- **treatment:** inline loader / status chip
- **intensity:** very low
- **copy:** یک line در صورت نیاز
- **timeout/fallback:** toast or inline error

### button submit
- **treatment:** button loading state
- **intensity:** none to very low
- **copy:** خود label button
- **timeout/fallback:** اگر طولانی شد surrounding helper state

---

## 12) Design Directions

### direction 1: minimal calm system
**توضیح:** تقریباً همه‌چیز بر skeleton، progress line و loaderهای بدون برند تکیه دارد. splash هم تا حد ممکن minimal است.

**مزیت:**
- بسیار mature و low-risk
- برای dashboard و product-heavy contextها عالی

**ریسک:**
- ممکن است brand memory در entry و pendingها کمی کم شود
- برای Loomera شاید بیش از حد generic و سرد شود

**مناسب بودن برای Loomera:** خوب، اما کمی کمتر از حد مطلوبِ هویت برند

### direction 2: softly branded motion
**توضیح:** سیستم عمدتاً utility-first است، اما app launch و چند pending state با glyph-driven motion نرم و controlled امضای برند را حفظ می‌کنند.

**مزیت:**
- تعادل خوب بین brand continuity و product restraint
- با shell logo rules، checkout trust layer و placeholder philosophy هماهنگ است

**ریسک:**
- اگر تیم اجرا کنترل نداشته باشد، ممکن است glyph usage آرام‌آرام زیاد شود

**مناسب بودن برای Loomera:** بسیار مناسب

### direction 3: refined product polish
**توضیح:** loadingها کمی cinematic‌تر می‌شوند؛ surface transitions، subtle veils و richer composition دارند.

**مزیت:**
- polished و premium
- برای marketing-facing یا app showcase عالی

**ریسک:**
- در محصول واقعی، به‌خصوص dashboard و booking، ممکن است زیادی prominent شود
- احتمال فاصله گرفتن از restraint برند بیشتر است

**مناسب بودن برای Loomera:** مناسب به‌عنوان accent layer، نه هسته‌ی سیستم

---

## 13) Final Recommendation

### direction نهایی
**Direction 2 — Softly Branded Motion**

### تصمیم نهایی برای Loomera
- loader system باید **lightly branded** باشد، نه logo-driven
- splash باید **limited but memorable** باشد
- glyph usage باید **rare, system-owned, high-judgment** باشد
- skeletonها باید **medium-fidelity و structure-preserving** باشند
- motion intensity باید **low** بماند

### چرا این direction بهتر است
چون Loomera نیاز دارد:
1. از generic SaaS feeling فاصله بگیرد
2. اما در دام brand overuse هم نیفتد
3. در checkout و app entry اعتماد بسازد
4. در dashboard و discovery مزاحم خوانش نشود
5. با placeholder و empty-state system هم‌خانواده بماند

### خلاصه‌ی اجرایی recommendation
- **Splash:** glyph-first، short-lived، no marketing copy
- **Primary app loader:** petal-segment fade loader
- **Most product loading:** skeleton-first
- **Inline/button:** logo-free micro loading
- **Payment pending:** dedicated progress state با copy دقیق و glyph محدود

---

## 14) Required Deliverables

### 1. loader/splash strategy
همین سند باید source of truth استراتژیک باشد.

### 2. loading context map
در بخش 3 و 11 تعریف شده است.

### 3. splash rules
در بخش 4 تعریف شده است.

### 4. loader visual language
در بخش 5 تعریف شده است.

### 5. skeleton system
در بخش 6 تعریف شده است.

### 6. color rules
در بخش 7 تعریف شده است.

### 7. logo/glyph rules
در بخش 8 تعریف شده است.

### 8. typography/copy rules
در بخش 9 تعریف شده است.

### 9. motion rules
در بخش 10 تعریف شده است.

### 10. final recommended direction
در بخش 13 مشخص شده است.

### 11. mini handoff spec برای design team
در بخش 16 آمده است.

### 12. mini handoff spec برای frontend team
در بخش 16 آمده است.

---

## 15) Asset Output Requirement

### assetهای اصلی
- `splash-screen-main`
- `splash-screen-dark`
- `app-loader-primary`
- `section-loader`
- `inline-loader`
- `button-loader`
- `checkout-pending-loader`
- `dashboard-card-skeleton`
- `dashboard-chart-skeleton`
- `table-skeleton`
- `gallery-skeleton`
- `generic-fullpage-loader`

### variantها
- `light`
- `dark`
- `reduced-motion`
- `compact`
- `mobile-safe`

### naming پیشنهادی
- `lm-splash-screen`
- `lm-app-loader`
- `lm-section-loader`
- `lm-inline-loader`
- `lm-button-loading`
- `lm-skeleton-card`
- `lm-skeleton-chart`
- `lm-skeleton-table`
- `lm-payment-pending`

### folder structure پیشنهادی
```text
src/
  components/
    loading/
      splash/
        app-splash-screen.tsx
        app-splash-screen.dark.tsx
      loaders/
        app-loader-primary.tsx
        section-loader.tsx
        inline-loader.tsx
        button-loader.tsx
        generic-fullpage-loader.tsx
      skeletons/
        dashboard-card-skeleton.tsx
        dashboard-chart-skeleton.tsx
        table-skeleton.tsx
        gallery-skeleton.tsx
        detail-page-skeleton.tsx
        booking-summary-skeleton.tsx
      states/
        checkout-pending-state.tsx
        upload-progress-state.tsx
      styles/
        loading.tokens.css
        loading.motion.css
      utils/
        loading-thresholds.ts
        prefers-reduced-motion.ts
        loading-copy.ts
```

### token naming پیشنهادی
```text
--lm-loading-bg
--lm-loading-surface
--lm-loading-surface-soft
--lm-loading-line
--lm-loading-brand-soft
--lm-loading-brand-strong
--lm-loading-shimmer-base
--lm-loading-shimmer-highlight
```

---

## 16) Handoff Notes

### برای Design Team

#### consistency rules
- loading باید ادامه‌ی shell و surface system باشد، نه یک family جدا
- skeleton radiusها با card radiusهای واقعی هم‌راستا باشند
- glyph فقط در stateهای system-owned
- shimmer intensity در تمام سیستم یکسان و subdued بماند

#### do
- از `surfaceSoft`, `cardHighlight`, `calmGlow` استفاده کنید
- structure واقعی UI را حفظ کنید
- loading و empty state را از هم جدا نگه دارید
- برای dashboard از skeletonهای data-first استفاده کنید

#### don’t
- spinner پیش‌فرض دایره‌ای را به الگوی اصلی تبدیل نکنید
- logo را در button، table، card grid یا section refresh تکرار نکنید
- pink gradient، glow شدید یا motion نمایشی اضافه نکنید
- loading را expressiveتر از empty state طراحی نکنید

#### motion restraint rules
- هر motion باید توجیه functional داشته باشد
- amplitude پایین
- durationهای آرام ولی نه کند
- repeated contexts باید motion سبک‌تری داشته باشند

#### logo/glyph usage rules
- splash: glyph-first
- payment pending full-page: glyph allowed
- dashboard/content loading: logo-free
- button/inline: logo-free

#### relation with placeholder and empty-state systems
- skeleton و placeholder باید از یک خانواده‌ی surface و shape باشند
- empty state illustration فقط بعد از resolve شدن «خالی بودن» استفاده شود
- اگر هنوز data نیامده، empty artwork هرگز جای skeleton را نگیرد

### برای Frontend Team

#### suggested component naming
- `app-splash-screen`
- `global-loader`
- `section-loader`
- `inline-loader`
- `button-loading-state`
- `dashboard-skeleton-card`
- `checkout-pending-state`

#### reduced-motion handling
- از `prefers-reduced-motion` تبعیت کنید
- shimmer را خاموش یا static کنید
- loopهای glyph را به static state تبدیل کنید
- progress line informational باقی بماند

#### light/dark swap rules
- token-based swap، نه classهای دستی per loader
- skeleton base و shimmer token جدا باشند
- dark mode حتماً از plum surfaces استفاده کند، نه black خالص

#### fallback logic
- `< 180ms`: هیچ loader نشان ندهید اگر لازم نیست
- `180–400ms`: route progress / button micro state
- `400–1200ms`: inline/section loader یا short veil
- `> 1200ms`: skeleton برای surfaces ساختاری
- `> 2500ms`: helper line یا progress state
- `> 6000ms`: fallback action / retry / status explanation

#### when to show skeleton vs spinner vs progress
- **skeleton:** page/module/table/card/detail
- **spinner-like micro loader:** button/inline فقط
- **progress:** upload، payment verification، multi-step booking، route top line

#### timeout behavior
- در payment یا booking هرگز silent timeout نداشته باشید
- state باید یا success/failure/cancelled شود یا helper/fallback action بدهد
- background refreshها می‌توانند silent باشند، اما first load نه

#### accessibility notes
- `aria-busy` برای containerها
- `aria-live="polite"` برای status textهای مهم
- button loading همراه با `disabled` و label واضح
- focus trap در splash نداشته باشید
- contrast skeleton از content کمتر، اما از background قابل‌تشخیص باشد

---

## 17) Success Criteria

این سیستم زمانی موفق است که:
- با هویت واقعی Loomera در سورس align بماند
- calm, trusted, refined و product-ready باشد
- motion آن subtle و polished بماند
- در light و dark mode خوب بنشیند
- با shell, checkout, dashboard, placeholder و empty-state systems هماهنگ باشد
- brand presence controlled بماند
- برای beauty + treatments + massage + wellness مناسب باشد، بدون cliché
- برای تیم طراحی و فرانت‌اند handoff-ready و source-ready باشد

---

## Appendix A — Source-driven Implementation Notes

### فرصت‌های بهبود مستقیم در repo فعلی
1. spinnerهای Font Awesome در booking، wallet charge و withdraw با `button-loader` و `inline-loader` جدید جایگزین شوند.
2. `searchLoading` فعلی از pulse عمومی به skeleton system جدید migrate شود.
3. `select_datetime` از full-page generic spinner card به booking flow hybrid loading منتقل شود.
4. route transition برای dashboard و shell با progress line بسیار سبک اضافه شود.
5. payment callback / pending state به یک state مشخص و trust-led تبدیل شود.
6. gradientهای purple/pink legacy در loading و auth surfaces از loader system حذف شوند.
7. dashboard برای KPI، chart و table skeletonهای مستقل بگیرد.

### token mapping سریع
- `legacy-design-namespace-primary` در loaderهای جدید باید به tokenهای Loomera primary map شود
- loading surfaces از `surfaceSoft`, `bgSubtle`, `cardHighlight`, `calmGlow` بیایند
- payment trust blocks می‌توانند از `bookingHighlight` / `accentSoft` بهره ببرند

### primary visual idea for app-loader-primary
سه segment نرم مشتق از فرم مرکزی glyph، بدون sparkle، با fade sequence و scale drift بسیار کم. این mark باید حس «continuity» بدهد، نه نمایش لوگو.
