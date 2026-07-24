# Loomera Category Artwork / Icons System

نسخه: 1.0  
وضعیت: source-ready / handoff-ready  
زبان: فارسی  
برند: Loomera

---

## 1) Source Review Summary

### جمع‌بندی کوتاه
بازبینی ZIP برند و سورس پروژه یک تصویر روشن می‌دهد:
- هویت Loomera روی **calm, trust, clarity, refinement, product maturity** بنا شده است.
- زبان بصری برند **violet-led** است، با **accent سبز کنترل‌شده**، neutralهای گرم، radiusهای نرم، و استفاده‌ی restrained از glow و tint.
- تایپوگرافی محصول **sans-led** است و برای UI فارسی، خوانایی، spacing و RTL از زیبایی تزئینی مهم‌تر است.
- در shell، checkout، empty states، placeholderها و dashboard یک قاعده‌ی مشترک وجود دارد: **brand باید حس بدهد، نه شلوغی بسازد**.

### از سورس درباره‌ی category navigation چه فهمیدیم
در repo فعلی، category navigation عملاً یکی از ورودی‌های اصلی discovery است:
- دسته‌ها در `GroupServices` مدل شده‌اند.
- top-level categoryها در صفحه‌ها و فیلترها به‌صورت card image + label نمایش داده می‌شوند.
- فیلتر جستجو category را با group id فعال می‌کند.
- در seed فعلی، categoryهای اجرایی محدودتر از دامنه‌ی برند هستند و بیشتر روی `مو / ناخن / پوست / آرایش` می‌چرخند.
- اما در brand docs و demo/docs، دامنه‌ی واقعی Loomera فراتر است: **beauty + aesthetic treatments + massage + wellness**.

### نتیجه‌ی استراتژیک
پس سیستم category باید دو کار را هم‌زمان انجام دهد:
1. برای محصول فعلی **inventory-safe** باشد.
2. برای دامنه‌ی واقعی Loomera **growth-ready** باشد.

### artwork و iconography در Loomera باید چه رفتاری داشته باشند
- **icon** باید سریع، کوچک‌مقیاس، readable و product-first باشد.
- **artwork** باید discovery را آسان کند، اما هرگز از title، filter state یا CTA جلو نزند.
- هر دو باید از یک family بیایند؛ یعنی اگر Hair یک icon با strand cue دارد، artwork آن هم باید همان منطق را در مقیاس بزرگ‌تر ادامه دهد.
- style باید **lightly representational** باشد؛ نه آن‌قدر abstract که category مبهم شود و نه آن‌قدر literal که stock-like یا cliché شود.

### constraintهای قطعی از سیستم‌های دیگر
این Category Artwork / Icons System باید با این محدودیت‌ها هم‌راستا بماند:
- **Color**: استفاده از `primary/secondary/accent` باید کنترل‌شده باشد؛ category نباید CTA-level saturation را اشغال کند.
- **Typography**: labelها باید با Yekan Bakh-led sans و scaleهای label/body-sm هماهنگ بمانند.
- **Shell**: category visualها نباید به mini branding یا logo repetition تبدیل شوند.
- **Placeholder / Empty State**: low-noise، utility-first، rounded، soft، 1px-ish linework، negative space بالا.
- **Dashboard**: brand intensity پایین‌تر از discovery است؛ dashboard shortcutها باید compact و operational بمانند.
- **RTL**: iconها باید directionally biased نباشند، مگر در جاهایی که معنای عملکردی دارند.

---

## 2) Category Strategy

### category system باید چه تجربه‌ای بسازد
Category system در Loomera باید تجربه‌ی **calm discoverability** بسازد؛ یعنی کاربر با کمترین اصطکاک بفهمد:
- این category چه نوع خدمتی را پوشش می‌دهد
- آیا با نیت فعلی او مرتبط است یا نه
- بدون باز کردن چندین صفحه، از کجا exploration را شروع کند

### service-led یا need-led؟
پیشنهاد نهایی برای Loomera: **hybrid با ستون فقرات service-led**

یعنی:
- taxonomy اصلی محصول service-led باشد، چون مدل داده و درک کاربر از رزرو بر همین منطق می‌نشیند.
- اما در discovery و collections بتوان از need-led framing استفاده کرد؛ مثل:
  - آرامش و ریکاوری
  - مراقبت و احیا
  - آماده‌سازی برای مراسم
  - خدمات نتیجه‌محور

**نتیجه:**
- top-level navigation = service-led familyها
- campaign / landing / curated strips = need-led collections

### artworkها abstract باشند یا lightly representational؟
پیشنهاد نهایی: **lightly representational**
- enough realism for recognition
- enough abstraction for brand refinement
- no stock-object literalness

### iconها symbol-led باشند یا object-led؟
پیشنهاد نهایی: **symbol-led with restrained service cues**
- iconها نباید عکس ابزار شوند.
- اما نباید آن‌قدر symbolic شوند که Hair، Skin و Massage از هم تمایز نداشته باشند.
- هر icon باید یک cue اصلی داشته باشد: strand / contour / arc / drop / wave / layer.

### میزان درست brand visibility
- در iconها: **low**
- در artworkها: **low to medium**
- در discovery cards: **medium**
- در chips/filters/menu: **very low**

### تعادل بین clarity، elegance و recognizability
قاعده‌ی نهایی Loomera:
- **clarity first**
- **elegance through restraint**
- **recognizability through silhouette, not decoration**

به بیان اجرایی:
- categoryها باید با silhouette و motif از هم جدا شوند، نه با paletteهای جداگانه‌ی پررنگ.
- اختلاف categoryها بیشتر از طریق **فرم و cue** ساخته شود تا از طریق رنگ.

---

## 3) Required Categories

### چیزی که سورس نشان می‌دهد
در implementation و seed فعلی، categoryهای واقعیِ عملیاتی محدودترند:
- خدمات مو
- خدمات ناخن
- خدمات پوست
- خدمات آرایش

اما در brand/docs دامنه‌ی رسمی Loomera این‌ها را هم پوشش می‌دهد:
- aesthetic treatments
- massage
- wellness
- providers beyond salon-first

### نتیجه‌ی پیشنهادی برای taxonomy نهایی
برای Loomera بهتر است category system در دو لایه تعریف شود:

### لایه 1 — Core Top-Level Categories
این‌ها باید در discovery اصلی، filter bar، category rows و shortcut surfaces حضور پیش‌فرض داشته باشند:
1. **All Services / همه خدمات**
2. **Hair / مو**
3. **Skin / Facial / پوست و فیشیال**
4. **Brow / Lash / ابرو و مژه**
5. **Nails / ناخن**
6. **Massage / ماساژ**
7. **Wellness / Wellness و ریکاوری**
8. **Aesthetic Treatments / درمان‌های زیبایی**
9. **Body Care / مراقبت بدن**
10. **Makeup / میکاپ و استایل**

### لایه 2 — Controlled Optional Families
این‌ها relevant هستند، اما بهتر است فقط وقتی inventory کافی وجود دارد top-level شوند:
- **Spa / Relaxation / اسپا و ریلکسیشن**
- **Clinic-like Beauty Treatments / خدمات کلینیکی زیبایی**

### merge / rename پیشنهادی
- `Skin` بهتر است در UI اصلی با عنوان **پوست و فیشیال** بیاید، نه فقط «پوست».
- `Wellness` بهتر است در فارسی consumer-facing به شکل **Wellness و ریکاوری** یا **تندرستی و ریکاوری** نمایش داده شود، نه ترجمه‌ی خشک و پزشکی.
- `Spa / Relaxation` در اکثر سطح‌های محصول بهتر است nested زیر Wellness باشد؛ اما برای tileهای curated و artwork asset می‌تواند asset مستقل داشته باشد.
- `Clinic-like Beauty Treatments` بهتر است top-level مستقل نشود مگر زمانی که inventory درمانی قابل‌توجه باشد؛ در غیر این صورت زیر **Aesthetic Treatments** تعریف شود.
- `Makeup` در consumer UI بهتر است **میکاپ و استایل** باشد تا narrow و event-only دیده نشود.

### Category Mapping پیشنهادی

| slug | label_fa | label_en | نقش | وضعیت |
|---|---|---|---|---|
| all-services | همه خدمات | All Services | catch-all / reset / broad discovery | اجباری |
| hair | مو | Hair | core service family | اجباری |
| skin | پوست و فیشیال | Skin / Facial | core service family | اجباری |
| brow-lash | ابرو و مژه | Brow / Lash | beauty detail family | اجباری |
| nails | ناخن | Nails | core service family | اجباری |
| massage | ماساژ | Massage | body service family | اجباری |
| wellness | wellness و ریکاوری | Wellness | calm / recovery family | اجباری |
| aesthetic-treatments | درمان‌های زیبایی | Aesthetic Treatments | clinic-adjacent result-led family | اجباری |
| body-care | مراقبت بدن | Body Care | support / treatment family | اجباری |
| makeup | میکاپ و استایل | Makeup | event / finish family | وابسته به inventory اما بهتر است آماده باشد |
| spa-relaxation | اسپا و ریلکسیشن | Spa / Relaxation | nested یا optional top-level | اختیاری کنترل‌شده |
| clinic-like-beauty | خدمات کلینیکی زیبایی | Clinic-like Beauty | nested under Aesthetic | nested recommended |

---

## 4) Category Roles by UI Context

| Context | هدف | preferred asset type | detail level | icon یا artwork | crop / size sensitivity | میزان برندینگ |
|---|---|---|---|---|---|---|
| A. Category Card | شروع exploration و درک سریع family | artwork-tile + small icon | medium | artwork اولویت دارد | بالا | low-medium |
| B. Category Chip | انتخاب/حذف سریع category در filter bar | icon + label | very low | icon اولویت دارد | very high | very low |
| C. Filter Icon | scannability در فیلترهای متراکم | icon-only یا icon+short label | ultra-low | icon | extremely high | none to very low |
| D. Explore Section Tile | discoverability + emotional cue | artwork-tile | medium | artwork | medium-high | medium |
| E. Search / Discovery Category Row | quick scan افقی در موبایل | tint tile + icon + label | low | icon+label | high | low |
| F. Empty State Support Icon | contextual reinforcement | mini icon یا tiny artwork | very low | icon بهتر است | high | very low |
| G. Dashboard Shortcut Tile | shortcut operational | icon + small tint slab | low | icon | high | low |
| H. Partner / Provider Category Label | tagging و metadata | label یا icon+label | ultra-low | icon optional | very high | none |
| I. Navigation / Menu Category Symbol | repeated navigation memory | icon-only | ultra-low | icon | extremely high | none |

### نکات تصمیم‌محور
- **Category Card** باید category را بفهماند، نه این‌که مثل banner تبلیغاتی رفتار کند.
- **Chip و Filter Icon** باید روی silhouette زنده باشند، چون جا برای detail وجود ندارد.
- **Explore Tile** جایی است که artwork می‌تواند کمی بیشتر narrative شود، اما هنوز باید low-noise بماند.
- **Dashboard Shortcut** باید operational بماند؛ artwork اینجا معمولاً زیاد است.
- **Provider Label** بهتر است semantic باشد، نه illustrated.

---

## 5) Icon System Rules

### تصمیم نهایی سیستم icon
برای Loomera مناسب‌ترین رویکرد:
**Hybrid restrained**

یعنی:
- پایه‌ی iconها **outline-led** باشد.
- در active state یا large-tile state، یک لایه‌ی fill/tint خیلی محدود مجاز باشد.
- filled icon کامل یا duotone سنگین به‌عنوان default توصیه نمی‌شود.

### چرا Hybrid Restrained بهتر از pure outline است
Pure outline اگر زیادی مینیمال اجرا شود، در categoryهای beauty/wellness به‌سرعت مبهم می‌شود. Hybrid restrained اجازه می‌دهد:
- small size readable بماند
- active state واضح‌تر شود
- بدون افتادن به دام stock icon، category cue تقویت شود

### قواعد دقیق iconography

#### stroke vs filled vs hybrid
- default: outline-led
- active / selected / featured: outline + soft inner tint
- full filled: فقط برای tiny badge یا decorative support، نه icon family اصلی
- duotone: فقط در artwork companion، نه در utility icons

#### line weight
- base grid: `24x24`
- primary stroke on 24: `1.75px` optically corrected
- compact 20px exports: `1.9px` معادل نوری
- mini 16px exports: simplified variant، نه scale-down خام

#### corner softness
- line caps: rounded
- line joins: rounded
- inner corners: softly eased
- هیچ گوشه‌ی knife-sharp یا CAD-like نباشد

#### geometry style
- geometry باید **soft-structured** باشد:
  - نه کاملاً geometric سخت
  - نه hand-drawn و نامنظم
- قوس‌ها باید controlled باشند.
- فرم‌ها باید به shell و placeholder family نزدیک باشند.

#### level of abstraction
- abstraction level: **medium**
- هر icon باید یک cue اصلی و حداکثر یک cue کمکی داشته باشد.
- بیشتر از دو معنای هم‌زمان icon را ضعیف می‌کند.

#### recognizability at small sizes
- هر icon باید در 16 و 20 پیکسل با نگاه اول category را یادآوری کند.
- جزئیاتی که فقط در 32 به بالا دیده می‌شوند، نباید بخشی از معنی اصلی icon باشند.

#### optical balance
- iconها باید center-balanced باشند، اما نه لزوماً mathematically centered.
- top sparkle, long stroke tail یا side leaf اگر category cue را می‌شکنند، باید حذف شوند.
- baseline بصری set باید هماهنگ بماند.

#### RTL neutrality
- iconها نباید چپ‌به‌راست یا راست‌به‌چپ bias ناخواسته داشته باشند.
- برای categoryها، symmetry یا center-anchor ترجیح دارد.
- اگر sweep line لازم است، باید در mirroring هم معنا از دست نرود.

#### how to avoid cliché
- به‌جای ابزار literal، از **action cue** استفاده شود.
- به‌جای face silhouette، از **care contour / arc / layer / wave** استفاده شود.
- به‌جای beauty symbolism جنسیت‌زده، از **service family geometry** استفاده شود.

#### consistency across the set
برای حفظ consistency، هر icon باید این فرمول را داشته باشد:
- 1 silhouette اصلی
- 1 internal cue
- 0 تا 1 support notch / accent
- max 2 line-depth levels
- no decorative sparkle unless semantically justified

### grid و construction rules
- master construction grid: `24 x 24`
- safe drawing area: `20 x 20`
- optical padding: `2px` در هر طرف
- stroke terminalها نباید به مرز safe box بچسبند
- هیچ icon نباید بیشتر از 70٪ area را fill کند

### family feeling rule
همه‌ی category iconها باید از یک family خوانده شوند، چون:
- line weight یکسان است
- curvature family یکسان است
- fill treatment یکسان است
- detail count یکسان است
- tension level یکسان است

---

## 6) Category Artwork Rules

### نقش artwork در Loomera
Artwork قرار نیست جای تصویر واقعی provider را بگیرد. نقش آن این است که:
- category را پیش از ورود به نتیجه‌ها توضیح دهد
- discovery را آرام‌تر و سریع‌تر کند
- از placeholder و empty-state family پیروی کند، اما کمی expressiveتر باشد

### illustration density
- **low to medium-low**
- 3 تا 5 لایه‌ی خوانا کافی است
- بیشتر از این، tile را decorative می‌کند

### composition style
- lightly representational
- center-anchored یا slightly off-center
- label-safe
- card-friendly
- crop-safe

### background behavior
- flat photo background ممنوع
- texture خیلی subtle و abstract مجاز
- soft planes / ribbons / layered fields اولویت دارند
- category artwork باید روی `surfaceSoft`, `cardHighlight`, `calmGlow`, `bookingHighlight` و dark equivalents بنشیند

### relation between icon and scene
بهترین رفتار:
- artwork از icon متولد شود، نه مستقل از آن
- یعنی icon cue همان skeleton اصلی artwork باشد
- artwork فقط context، scale و supporting surfaces اضافه کند

### use of abstract shapes
- مجاز و مطلوب است
- shapes باید functional باشند: depth، layering، calm emphasis
- shapeها نباید به pattern noise تبدیل شوند

### degree of realism
- low realism / high plausibility
- نه photo-like
- نه cartoon-like
- نه glossy 3D

### use of glow / gradient / soft surfaces
- glow فقط از جنس calm diffusion
- gradient محدود، gentle و brand-consistent
- metallic sheen، glassmorphism شدید یا glow-heavy surfaces ممنوع

### label compatibility
هر artwork باید یک zone واضح برای label داشته باشد:
- حداقل 35٪ tile برای label-safe area
- artwork نباید زیر title شلوغ شود
- اگر layout vertical است، motif در بالا/کنار و text در پایین/راست بنشیند

### how to stay calm and premium
- premium از **spacing، restraint، silhouette quality، crop safety** می‌آید
- نه از تزئینات زیاد
- نه از paletteهای زیاد
- نه از gradients پرقدرت

### decorative overload را چگونه avoid کنیم
- حداکثر یک hero motif
- حداکثر دو support plane
- accent spot کمتر از 12٪ سطح tile
- no floating ornaments
- no repeated sparkles as decoration

### نسبت‌های پیشنهادی artwork
- `1:1` برای shortcut tile و category card compact
- `4:3` برای explore tile و category row card
- `16:9` فقط برای hero strip یا featured editorial context

---

## 7) Category-by-Category Direction

### 7.1 Hair / مو
- **visual cue:** strand flow + layered sweep
- **موتیف مناسب:** یک قوس دو-لایه شبیه حرکت controlled مو، نه خودِ ابزار
- **avoid:** قیچی، سشوار، شانه، silhouette صورت با موی بلند
- **icon direction:** دو sweep line با یک anchor مرکزی یا پایین‌محور
- **artwork direction:** strand ribbon روی soft violet field با یک plane ثانویه برای depth
- **emotional tone:** polished, fluid, confident
- **color behavior:** `primarySoft`, `secondarySoft`, accent بسیار کم
- **recognizability note:** اختلاف Hair با Brow/Lash باید از «flow بلندتر و پهن‌تر» بیاید

### 7.2 Skin / Facial / پوست و فیشیال
- **visual cue:** skin layer + drop / glow halo
- **موتیف مناسب:** contour نرم + droplet-like cutout یا halo ring
- **avoid:** face silhouette کامل، ماسک صورت literal، برگ روی صورت
- **icon direction:** contour بی‌طرف + یک cue مربوط به care layer
- **artwork direction:** soft layered oval / surface planes با glow محدود و حس clean care
- **emotional tone:** clear, fresh, composed
- **color behavior:** `cardHighlight`, `calmGlow`, `surfaceSoft`
- **recognizability note:** Skin باید از Aesthetic نرم‌تر و less clinical دیده شود

### 7.3 Brow / Lash / ابرو و مژه
- **visual cue:** arch + fan rhythm
- **موتیف مناسب:** یک قوس ظریف اما readable با radial lash-like rhythm کنترل‌شده
- **avoid:** چشم کامل آرایشی، eyeliner dramatic، glamorous eye icon
- **icon direction:** brow arch + fine fan cue با simplification شدید
- **artwork direction:** close-detail-inspired abstract tile با arch motif و micro rhythm کم‌تعداد
- **emotional tone:** precise, delicate, neat
- **color behavior:** `secondarySoft`, `badgePremium`, متن neutral
- **recognizability note:** detail باید در 16px هم survive کند؛ fan count کم بماند

### 7.4 Nails / ناخن
- **visual cue:** fingertip arc + finish edge
- **موتیف مناسب:** curved fingertip panel یا manicure linework، نه bottle icon
- **avoid:** لاک‌پاک‌کن، بطری لاک، hand pose نمایشی، الماس و glitter
- **icon direction:** fingertip contour + finish band
- **artwork direction:** panelهای rounded با finish crescent و orderly spacing
- **emotional tone:** tidy, crafted, controlled
- **color behavior:** `surfaceSoft`, `badgePremium`, `calmGlow` محدود
- **recognizability note:** باید craftsmanship را برساند، نه glam fantasy را

### 7.5 Massage / ماساژ
- **visual cue:** pressure wave + body contour
- **موتیف مناسب:** soft wave intersecting with broad contour
- **avoid:** دست روی بدن، سنگ داغ، candle، تخت ماساژ literal
- **icon direction:** broad curve + wave compression cue
- **artwork direction:** layered horizontal wave field با حس release و support
- **emotional tone:** grounded, releasing, trustworthy
- **color behavior:** `bookingHighlight`, `accentSoft`, `surfaceSoft`
- **recognizability note:** Massage باید از Wellness فیزیکی‌تر و body-ledتر باشد

### 7.6 Wellness / Wellness و ریکاوری
- **visual cue:** breath arc + reset circle
- **موتیف مناسب:** horizon-like arc یا calm circular flow
- **avoid:** lotus، chakra، yin-yang، bamboo، incense
- **icon direction:** circular reset form + open breathing gap
- **artwork direction:** spacious tile با دو plane آرام و یک circular/horizon cue
- **emotional tone:** restorative, quiet, balanced
- **color behavior:** `accentSoft`, `bookingHighlight`, `bgSubtle`
- **recognizability note:** باید از Massage کمتر tactile و از Spa کمتر atmospheric باشد

### 7.7 Aesthetic Treatments / درمان‌های زیبایی
- **visual cue:** precision ring + treatment layer
- **موتیف مناسب:** focused zone, skin grid, target-like soft precision cue
- **avoid:** syringe, needle, scalpel, medical cross, graphic skin imagery
- **icon direction:** precise contour with a single controlled focal mark
- **artwork direction:** structured soft tile با zone-focused composition و حس professional precision
- **emotional tone:** precise, credible, modern
- **color behavior:** `primarySoft`, `dashboardAccent`, `surfaceSoft`
- **recognizability note:** باید clinic-adjacent باشد، نه hospital-like

### 7.8 Spa / Relaxation / اسپا و ریلکسیشن
- **visual cue:** steam ribbon + folded calm plane
- **موتیف مناسب:** towel-fold geometry یا soft mist arc
- **avoid:** candles, orchids, stones, bamboo, tropical cliché
- **icon direction:** folded plane + rising arc
- **artwork direction:** soft atmospheric tile با mist-like layered planes
- **emotional tone:** cushioned, quiet, immersive
- **color behavior:** `accentSoft` + `calmGlow` mix
- **recognizability note:** اگر inventory کم است، فقط در curated surfaces یا زیر Wellness استفاده شود

### 7.9 Body Care / مراقبت بدن
- **visual cue:** torso contour + wrap band / care zone
- **موتیف مناسب:** broad body section cue با یک supportive band
- **avoid:** body silhouette کامل، slimming tape imagery، sexualized curves
- **icon direction:** neutral body contour + care band cue
- **artwork direction:** broad, stable shape language با large rounded planes
- **emotional tone:** supportive, respectful, composed
- **color behavior:** `surfaceSoft`, `bookingHighlight`, `accentSoft`
- **recognizability note:** باید ethical و non-body-shaming بماند

### 7.10 Makeup / میکاپ و استایل
- **visual cue:** finish sweep + accent curve
- **موتیف مناسب:** brush-stroke-inspired but abstract finish arc
- **avoid:** lips, lipstick bullet, mascara wand, glam face icon
- **icon direction:** finish crescent + precise tip cue
- **artwork direction:** directional finish sweep روی soft premium field
- **emotional tone:** polished, event-ready, refined
- **color behavior:** `badgePremium`, `primarySoft`, `surface`
- **recognizability note:** باید از Nails و Brow/Lash متمایز بماند؛ finish-focused باشد

### 7.11 Clinic-like Beauty Treatments / خدمات کلینیکی زیبایی
- **visual cue:** structured precision + calm medical-adjacent order
- **موتیف مناسب:** segmented ring / measured layer / subtle plus-less geometry
- **avoid:** medical cross، syringe، device heads، shock imagery
- **icon direction:** geometric precision cue با softness بالا
- **artwork direction:** structured layered tile با cleanliness بالا و emotional temperature پایین‌تر
- **emotional tone:** exact, safe, composed
- **color behavior:** `surfaceSoft`, `dashboardAccent`, `borderSoft`
- **recognizability note:** این family بهتر است زیر Aesthetic Treatments بماند مگر inventory درمانی مستقل شود

### 7.12 All Services / همه خدمات
- **visual cue:** multi-node family cluster
- **موتیف مناسب:** 3–4 soft nodes از familyهای مختلف در یک composition کنترل‌شده
- **avoid:** collage ابزارهای مختلف، grid شلوغ، rainbow palette
- **icon direction:** clustered arcs / nodes / layered marks
- **artwork direction:** abstract family board که از همه categoryها hint بگیرد بدون dominance یک category
- **emotional tone:** broad, clear, orienting
- **color behavior:** `bgSubtle`, `surfaceSoft`, tiny spots of `primarySoft` و `accentSoft`
- **recognizability note:** reset / umbrella role باید روشن بماند

---

## 8) Color Rules

### منبع رنگ‌ها
این سیستم باید فقط از tokenهای واقعی Loomera بیاید؛ نه از paletteهای جدید و category-specific غیرهم‌خانواده.

### tokenهای مناسب برای iconها
برای icon stroke یا primary symbol:
- light mode:
  - `loomera.textSecondary`
  - `loomera.primary`
  - `loomera.textPrimary`
- dark mode:
  - `loomera.textSecondary`
  - `loomera.primary`
  - `loomera.textPrimary`

**قاعده:**
- icon resting state بهتر است بیشتر neutral باشد.
- primary فقط برای selected/featured/active به‌کار رود.

### tokenهای مناسب برای category artwork background
- light:
  - `loomera.surfaceSoft`
  - `loomera.cardHighlight`
  - `loomera.calmGlow`
  - `loomera.bookingHighlight`
  - `loomera.bgSubtle`
- dark:
  - `loomera.surfaceSoft`
  - `loomera.cardHighlight`
  - `loomera.calmGlow`
  - `loomera.bookingHighlight`
  - `loomera.bgSubtle`

### tokenهای مناسب برای accent spots
- `loomera.primarySoft`
- `loomera.secondarySoft`
- `loomera.accentSoft`
- `loomera.dashboardAccent`
- `loomera.badgePremium`

### light mode palette behavior
- default card: `surface` + `borderSoft`
- soft category tile: `surfaceSoft` یا `cardHighlight`
- wellness-led families: `bookingHighlight`
- focus/selected: `selection` + `primary` border or icon

### dark mode palette behavior
- default card: `surface` / `surfaceRaised`
- category tile: `surfaceSoft` / `cardHighlight`
- wellness-led families: `bookingHighlight`
- selected: `selection` یا `primarySoft` با icon روشن‌تر

### active / selected category treatment
بهترین treatment برای active category در Loomera:
- background tint subtle
- border یا ring واضح اما calm
- icon کمی پررنگ‌تر
- label weight یا color کمی stronger

**نمونه:**
- light: `selection` background + `primary` icon + `focusRing` ring
- dark: `selection` background + `primary` icon + subtle `primarySoft` support

### neutral / resting state
- icon: `textSecondary`
- tile: `surfaceSoft` or `bgSubtle`
- border: `borderSoft`
- label: `textPrimary`

### hover / focus state
- hover نباید به CTA شباهت پیدا کند
- بهتر است این سه تغییر رخ دهد:
  - border کمی قوی‌تر شود
  - background یک درجه tint بگیرد
  - icon کمی contrast بگیرد

### category-by-category color behavior matrix

| Category | light mode | dark mode | accent note |
|---|---|---|---|
| Hair | `primarySoft` + `secondarySoft` | `primarySoft` + `secondarySoft` | violet-led but not saturated |
| Skin | `cardHighlight` + `calmGlow` | `cardHighlight` + `calmGlow` | soft-care cue |
| Brow/Lash | `badgePremium` + `secondarySoft` | `badgePremium` + `secondarySoft` | refined detail cue |
| Nails | `surfaceSoft` + `badgePremium` | `surfaceSoft` + `badgePremium` | crafted / neat |
| Massage | `bookingHighlight` + `accentSoft` | `bookingHighlight` + `accentSoft` | body-release cue |
| Wellness | `accentSoft` + `bgSubtle` | `accentSoft` + `bgSubtle` | trust / recovery cue |
| Aesthetic | `primarySoft` + `dashboardAccent` | `primarySoft` + `dashboardAccent` | precision without coldness |
| Spa/Relaxation | `accentSoft` + `calmGlow` | `accentSoft` + `calmGlow` | atmospheric but controlled |
| Body Care | `surfaceSoft` + `bookingHighlight` | `surfaceSoft` + `bookingHighlight` | respectful body care cue |
| Makeup | `badgePremium` + `primarySoft` | `badgePremium` + `primarySoft` | finish / polish cue |
| All Services | `bgSubtle` + mixed soft accents | `bgSubtle` + mixed soft accents | umbrella role |

### usageهای ممنوع
- استفاده از `primary` به‌عنوان fill کامل tileهای category
- استفاده از `error`, `warning`, `info` به‌عنوان رنگ خانواده‌ی category
- ساخت palette جداگانه برای هر category خارج از token system
- neon purple، pink beauty cues، rose-gold luxury cues
- gradientهای noisy یا high-contrast
- متن روی `secondary` یا `highlight` بدون contrast-safe correction

---

## 9) Typography Relationship

### category label style
- desktop: `Label 13/20` یا `Body Small 14/24` با وزن 500 تا 600
- mobile dense: `Label 13/20`
- رنگ: `textPrimary`

### section heading style
- category sections: `H5 20/30` یا `H4 24/34` بسته به context
- در rows و strips متراکم: `Body Large` با وزن 600 هم کافی است

### chip text style
- `Label 13/20`
- در chipهای خیلی فشرده: `Caption 12/18`
- همیشه single-line و center-aligned optically

### card title style
- `Body 16/28` یا `Body Small 14/24` با وزن 600
- در artwork cardها می‌تواند دو خط باشد، اما بهتر است بیش از دو خط نشود

### helper text style
- `Caption 12/18`
- رنگ: `textMuted` یا `textSecondary`

### maximum label length
- top-level label فارسی: ideal تا 12 کاراکتر
- acceptable تا 18 کاراکتر در card context
- chip context: بهتر است 10–12 کاراکتر
- long bilingual labels در consumer UI توصیه نمی‌شود

### mixed Persian / English labels
- در UI اصلی: فارسی اولویت دارد
- انگلیسی فقط در design docs، CMS، developer config یا partner admin لازم است
- اگر mixed label نمایش داده شد، English باید secondary و کوچک‌تر باشد

### RTL spacing
- icon تا label در chip: `8px`
- icon تا label در row/card compact: `10–12px`
- artwork تا label block: `12–16px`
- title تا helper text: `4–6px`

### icon-to-label spacing rule
- spacing باید بخشی از family feel باشد
- فاصله‌ی کمتر از 6px icon را decorative و فاصله‌ی بیشتر از 14px ارتباط را ضعیف می‌کند

### artwork-to-label hierarchy
- artwork باید supporting layer باشد
- title باید همیشه سریع‌تر از artwork خوانده شود
- در cardهایی که CTA دارند، hierarchy درست این است:
  1. label
  2. category understanding
  3. optional helper
  4. artwork atmosphere

---

## 10) Product Fit Rules

### در discovery cards
- بهترین الگو: `artwork + label + helper`
- artwork باید context را بسازد، نه این‌که hero visual شود
- اگر card خیلی کوچک شد، به `icon + tint tile` downgrade کنید

### در filterها
- default: `icon + label`
- اگر جا کم است: `label only` یا `icon only` بسته به familiarity
- icon باید selected state را تقویت کند، نه پیچیدگی اضافه کند

### در horizontal rows
- mobile-first pattern: `tint tile + icon + label`
- artwork در horizontal row فقط اگر tile height کافی باشد

### در mobile grids
- بهترین pattern: square/soft-rect tile with icon-led center and short label
- artwork باید compact variant داشته باشد
- label wrapping در موبایل باید محدود بماند

### در search suggestionها
- بیشتر مواقع **icon + label** کافی است
- artwork در suggestion dropdown معمولاً noise ایجاد می‌کند

### در empty states
- default: icon یا mini artwork کوچک
- category artwork فقط وقتی useful است که state category-specific باشد

### در dashboard shortcuts
- default: icon + title
- artwork فقط در onboarding/welcome dashboard مجاز است

### در partner/provider-facing surfaces
- بهتر است semantic labelها غالب باشند
- icon optional است
- artwork معمولاً unnecessary است، مگر در setup wizard

### چه وقت فقط icon کافی است
- chip
- filter pill
- nav/menu
- dashboard shortcut
- inline label
- search suggestion

### چه وقت artwork لازم است
- category card در discovery
- explore section tile
- featured category strip
- onboarding / educational category surface

### چه وقت فقط label کافی است
- table cell
- provider metadata
- backend/admin dense list
- multi-select dense filter panel

### چه وقت icon + label + tint tile بهترین انتخاب است
- mobile category row
- compact discovery modules
- chipهایی که recognition plus tappability می‌خواهند
- dashboard cards با emphasis کم

---

## 11) Avoiding Cliché

### اصول کلی anti-cliché برای Loomera
Loomera نباید به این دام‌ها بیفتد:
- salon-only visual language
- over-feminine beauty codes
- over-luxury symbolism
- wellness spirituality clichés
- clinic harshness
- stock-vector object libraries

### category-specific cliché map

#### Hair
- avoid: scissors, comb, blow dryer, female head silhouette
- بهتر: strand movement, layered sweep, controlled flow

#### Skin / Facial
- avoid: face + leaf, shiny cheek sparkle, mask icon
- بهتر: care contour, glow layer, clarity halo

#### Brow / Lash
- avoid: sexy eye, dramatic eyeliner wing, glam eye makeup motif
- بهتر: refined arch, lash rhythm, precision curve

#### Nails
- avoid: nail polish bottle, diamonds, glitter bursts
- بهتر: fingertip contour, finish edge, crafted curve

#### Massage
- avoid: hot stones, candles, palms pressing a back, spa bed literal
- بهتر: pressure wave, release contour, grounded flow

#### Wellness
- avoid: lotus, chakra wheels, yoga clichés, bamboo
- بهتر: breath arc, reset circle, calm horizon

#### Aesthetic Treatments
- avoid: needle, syringe, scalpel, intense medical symbols
- بهتر: precision ring, treatment zone, structured softness

#### Spa / Relaxation
- avoid: candles, orchid, pebbles, tropical spa kit
- بهتر: steam ribbon, folded plane, softened atmosphere

#### Body Care
- avoid: hourglass body, slimming tape, sensual body outline
- بهتر: respectful contour, care band, support zone

#### Makeup
- avoid: lips, lipstick, glam lashes as a proxy for makeup
- بهتر: finish sweep, polish arc, detail cue

### چگونه categoryها recognizable بمانند بدون cliché شدن
- با **gesture** کار کنید، نه با object
- با **silhouette** کار کنید، نه با decorative detail
- با **care logic** کار کنید، نه با stereotype
- با **repetition of system rules** کار کنید، نه با تکرار visual tropes بازار beauty

### چه چیزهایی Loomera را بیش از حد salon-only می‌کنند
- قیچی، آینه، سشوار، brush-heavy iconography به‌عنوان زبان کل برند
- حذف کامل massage / wellness / aesthetic cues
- استفاده از paletteهای pink/rose به‌عنوان category cues

### چه چیزهایی Loomera را gender-coded می‌کنند
- لب، مژه، پاشنه‌بلند، جواهر، الماس، silhouette زنانه به‌عنوان زبان عمومی categoryها
- pose-based beauty symbolism
- overly delicate line weights که فقط حس fashion illustration بدهند

---

## 12) Do / Don’t Guide

### Do — 12 قانون مهم
1. از یک icon family واحد با stroke و curvature ثابت استفاده کنید.
2. top-level categoryها را service-led نگه دارید.
3. artworkها را crop-safe و label-safe بسازید.
4. از tokenهای واقعی Loomera استفاده کنید.
5. selected state را با tint و border بسازید، نه با saturation زیاد.
6. categoryها را بیشتر با silhouette از هم متمایز کنید تا با رنگ.
7. در small sizes از simplified variant استفاده کنید.
8. در artworkها negative space را حفظ کنید.
9. در categoryهای wellness/treatment از حس trust و care جلوتر از decoration استفاده کنید.
10. برای dark mode variant واقعی بسازید، نه فقط invert رنگ.
11. بین icon و artwork یک skeleton مشترک نگه دارید.
12. هر category asset را در context واقعی محصول تست کنید: chip، card، row، dashboard.

### Don’t — 12 خطای رایج
1. از stock icon pack beauty بدون customization استفاده نکنید.
2. strokeهای خیلی نازک برای iconهای موبایل استفاده نکنید.
3. برای هر category palette مستقل و اشباع طراحی نکنید.
4. artwork را از label و CTA dominantتر نکنید.
5. categoryها را با ابزار literal تعریف نکنید.
6. از face silhouette به‌عنوان راه‌حل میان‌بُر برای skin/makeup استفاده نکنید.
7. از lotus/candle/stone برای همه‌ی familyهای آرامش استفاده نکنید.
8. از medical cueهای تهاجمی برای aesthetic categories استفاده نکنید.
9. iconها را جهت‌دار و ناسازگار با RTL نسازید.
10. از sparkleهای اضافه برای premium-feel استفاده نکنید.
11. artwork بزرگ را بدون compact variant وارد mobile نکنید.
12. dark mode را با black خالص یا neon purple خراب نکنید.

---

## 13) Quality Checklist

هر icon یا artwork category باید با این checklist سنجیده شود:
- آیا در 16 و 20 پیکسل هنوز readable است؟
- آیا category را سریع و بدون توضیح طولانی می‌فهماند؟
- آیا با لحن calm و refined Loomera هم‌راستاست؟
- آیا به clichéهای رایج beauty/wellness نلغزیده؟
- آیا با tokenهای واقعی برند ساخته شده است؟
- آیا در light و dark mode هر دو خوب کار می‌کند؟
- آیا از CTA یا title توجه نمی‌دزدد؟
- آیا در mobile grid هنوز usable است؟
- آیا icon و artwork آن category به‌وضوح هم‌خانواده‌اند؟
- آیا با placeholder و empty-state system conflict ندارد؟
- آیا selected و resting state به‌وضوح از هم جدا هستند؟
- آیا برای provider/admin surfaces هم نسخه‌ی کم‌نویزتر دارد؟

---

## 14) Technical Delivery Notes

### preferred export formats
- **Icons:** SVG primary, PNG fallback
- **Artwork tiles:** SVG primary اگر vector-friendly است، WebP/PNG fallback برای raster export
- **Preview docs:** PNG/WebP

### minimum sizes
#### Icons
- `16x16`
- `20x20`
- `24x24` (master utility)
- `32x32` (marketing / featured UI)

#### Artwork
- `96x96` compact tile
- `160x120` small landscape
- `240x180` standard category tile
- `320x240` large discovery tile
- `512x384` high-res source tile

### icon grid guidance
- master grid: `24x24`
- safe area: `20x20`
- optical padding: `2px`
- stroke alignment: pixel-snapped where possible

### optical padding rules
- narrow motifs like Brow/Lash نیاز به padding بصری بیشتر دارند
- broad motifs like Massage/Body Care نباید edge-hugging شوند
- visual center مهم‌تر از geometric center است

### SVG usage notes
- icon stroke preferably `currentColor`
- selected variant اگر tint layer دارد، آن لایه classable باشد
- no embedded raster in icon SVGs
- remove unnecessary groups / metadata
- minify production SVGs

### raster artwork usage notes
- artworkهای gradient-heavy را به WebP هم export کنید
- tiles باید @1x و @2x داشته باشند
- text داخل artwork قرار نگیرد

### light/dark variants
- برای هر artwork حداقل این‌ها لازم است:
  - `light`
  - `dark`
- برای iconها:
  - `default`
  - `active`
  - optional `compact`

### selected/active variants
- `category_icon_active`
- `category_artwork_active`
- active variant نباید صرفاً brighter باشد؛ باید state را واضح‌تر کند

### suggested field naming
- `category_slug`
- `category_label_fa`
- `category_label_en`
- `category_icon`
- `category_icon_active`
- `category_icon_compact`
- `category_artwork`
- `category_artwork_dark`
- `category_artwork_active`
- `category_family`
- `category_order`
- `category_is_top_level`
- `category_parent_slug`

### folder structure پیشنهادی
```text
assets/
  category-system/
    icons/
      hair/
        category-icon-hair.svg
        category-icon-hair-active.svg
        category-icon-hair-compact.svg
      skin/
      brow-lash/
      nails/
      massage/
      wellness/
      aesthetic-treatments/
      spa-relaxation/
      body-care/
      makeup/
      all-services/
    artwork/
      light/
        category-artwork-hair.svg
        category-artwork-skin.svg
        ...
      dark/
        category-artwork-hair-dark.svg
        category-artwork-skin-dark.svg
        ...
      active/
        category-artwork-hair-active.svg
        ...
    manifests/
      category-visual-manifest.json
    docs/
      loomera-category-artwork-icons-system-fa.md
```

---

## 15) Design Directions

### Direction 1 — Minimal Abstract-Symbolic
**توضیح:**
iconها abstractتر، artworkها ساده‌تر و category cueها بیشتر بر silhouette و motion تکیه می‌کنند.

**مزیت:**
- بسیار clean
- strongly product-first
- برای dashboard و dense surfaces عالی

**ریسک:**
- ممکن است Hair / Skin / Wellness / Spa در بعضی sizes بیش از حد به هم نزدیک شوند
- برای discovery اولیه کمی سرد یا مبهم شود

**مناسب بودن برای Loomera:**
خوب است، اما به‌تنهایی برای category discovery اصلی کمی بیش از حد مینیمال است.

### Direction 2 — Softly Branded Service Cues
**توضیح:**
iconها symbol-led هستند اما service cue روشن دارند؛ artworkها lightly representational و tint-led هستند.

**مزیت:**
- بهترین تعادل clarity و refinement
- برای discovery، chips، rows و tiles همه usable است
- family feeling قوی می‌سازد

**ریسک:**
- اگر discipline از دست برود، به decorative tile نزدیک می‌شود

**مناسب بودن برای Loomera:**
بسیار بالا. این direction نزدیک‌ترین گزینه به DNA فعلی Loomera است.

### Direction 3 — Refined Editorial Category Tiles
**توضیح:**
artworkها editorialتر و atmosphere-ledتر می‌شوند؛ iconها secondary باقی می‌مانند.

**مزیت:**
- برای premium discovery strips و hero collections جذاب است
- حس quietly premium را خوب منتقل می‌کند

**ریسک:**
- برای filter chips, compact cards, dashboard و mobile dense surfaces بیش از حد heavy می‌شود
- نیازمند art direction پیوسته‌تر و production time بیشتر است

**مناسب بودن برای Loomera:**
به‌عنوان layer ثانویه یا campaign direction خوب است، اما نه به‌عنوان default system.

---

## 16) Final Recommendation

### direction نهایی پیشنهادی
**Direction 2 — Softly Branded Service Cues**
با discipline اجرایی Direction 1.

### برای Loomera بهترین نوع category iconography چیست
- **outline-led hybrid restrained icons**
- service cue روشن، بدون object literal
- small-size optimized

### artwork level چقدر باشد
- **medium-low**
- category را soften کند، نه dominate
- tile-friendly و crop-safe بماند

### abstraction level چقدر باشد
- **medium abstraction**
- enough meaning for quick recognition
- enough restraint for brand maturity

### color intensity چقدر باشد
- **low to medium-low**
- tint-based, not saturated
- selected states clearer, not louder

### categoryها چگونه distinct بمانند و هم family feel داشته باشند
- distinction by **silhouette + motion cue + category skeleton**
- family feel by **line weight + curvature + tint behavior + spacing discipline**
- رنگ، نقش ثانویه داشته باشد؛ فرم، نقش اصلی

### چرا این direction برای discovery + clarity + trust بهتر جواب می‌دهد
چون هم با repo فعلی که category را در card/filter/search به کار می‌برد سازگار است، هم با DNA برند که آرام، دقیق و quietly premium است. این direction:
- در chip و filter هم جواب می‌دهد
- در artwork tile هم گرم و قابل‌فهم می‌ماند
- categoryها را بدون cliché و بدون gender-coding قابل‌تشخیص نگه می‌دارد
- با placeholder، empty-state، dashboard و shell systems conflict نمی‌سازد

---

## 17) Deliverables

این خروجی شامل این لایه‌های handoff-ready است:
1. category strategy
2. required category mapping
3. icon system rules
4. artwork rules
5. category-by-category direction
6. color rules
7. typography relationship rules
8. product fit rules
9. anti-cliché rules
10. do/don’t guide
11. quality checklist
12. technical delivery notes
13. final recommended direction
14. summary-ready version

### Summary-ready version برای docs/design-system
**Loomera Category Artwork / Icons System** باید یک سیستم service-led و product-first باشد که categoryها را با iconهای outline-led hybrid و artworkهای lightly representational نمایش می‌دهد. تمایز categoryها باید از silhouette، cue و composition بیاید؛ نه از رنگ‌های پررنگ یا objectهای cliché. palette باید از tokenهای واقعی Loomera—به‌ویژه surfaceSoft، cardHighlight، calmGlow، bookingHighlight، primarySoft و accentSoft—بیاید و selected state با tint و border تعریف شود، نه با saturation بالا. category visualها باید در chip، filter، row، card، dashboard و empty-state رفتار سازگار و مقیاس‌پذیر داشته باشند و با سیستم‌های placeholder، empty-state، shell و typography کاملاً هم‌خانواده بمانند.

---

## 18) Asset Output Requirement

### assets اصلی icon
- `category-icon-hair`
- `category-icon-skin`
- `category-icon-brow-lash`
- `category-icon-nails`
- `category-icon-massage`
- `category-icon-wellness`
- `category-icon-aesthetic-treatments`
- `category-icon-spa-relaxation`
- `category-icon-body-care`
- `category-icon-all-services`
- `category-icon-makeup` (recommended optional)

### assets اصلی artwork
- `category-artwork-hair`
- `category-artwork-skin`
- `category-artwork-brow-lash`
- `category-artwork-nails`
- `category-artwork-massage`
- `category-artwork-wellness`
- `category-artwork-aesthetic-treatments`
- `category-artwork-spa-relaxation`
- `category-artwork-body-care`
- `category-artwork-all-services`
- `category-artwork-makeup` (recommended optional)

### variantهای پیشنهادی
- `light`
- `dark`
- `active`
- `compact`
- `icon-only`
- `artwork-tile`

### naming rule
```text
category-icon-{slug}.svg
category-icon-{slug}-active.svg
category-icon-{slug}-compact.svg
category-artwork-{slug}.svg
category-artwork-{slug}-dark.svg
category-artwork-{slug}-active.svg
```

---

## 19) Handoff Notes

### برای Design Team
#### consistency rules
- line weight، radius family، negative space و tint behavior در تمام categoryها ثابت بماند
- distinction را از silhouette بگیرید، نه از paletteهای متفاوت
- icon و artwork هر category باید یک skeleton مشترک داشته باشند

#### do / don’t
- do: service cue روشن، detail کنترل‌شده، crop-safe composition
- don’t: object literal، beauty cliché، sparkle decoration، gradient-heavy tile

#### anti-cliché rules
- از visual language market-default beauty فاصله بگیرید
- از candle/lotus/scissors/lips/diamond به‌عنوان shortcut استفاده نکنید
- categoryهای درمانی را neither scary nor sugary اجرا کنید

#### color restraint rules
- category tile نباید CTA را کمرنگ کند
- رنگ‌ها soft role داشته باشند
- selected state باید واضح‌تر، نه loudتر باشد

#### icon/artwork relationship rules
- artwork نباید world دیگری نسبت به icon بسازد
- icon = distilled category cue
- artwork = expanded category cue with calm context

### برای Frontend Team
#### suggested component naming
- `category-icon`
- `category-artwork-tile`
- `category-chip-icon`
- `category-filter-icon`
- `category-card-media`
- `category-shortcut-tile`

#### icon vs artwork logic
- `chip/filter/nav/dashboard` → icon-first
- `discovery/explore/category card` → artwork-first یا icon+tint tile
- `dense admin/provider tables` → label-first, icon optional

#### light/dark swap rules
- dark mode asset مستقیم داشته باشید
- از CSS invert برای artwork استفاده نکنید
- iconها ترجیحاً color-token driven باشند

#### active/selected state rules
- selected = tint + border/ring + stronger icon
- active variant باید semantic state را واضح کند
- hover نباید شبیه CTA شود

#### responsive behavior
- `lg+`: artwork tile مجاز
- `md`: icon+tint tile recommended
- `sm`: compact icon tile یا chip variant

#### SVG implementation notes
- currentColor-friendly icons
- accessible labels via `aria-hidden` / sr text when needed
- lazy-load artwork tiles if image-based
- dedupe SVG defs and gradients

#### fallback logic
- اگر artwork load نشد → icon+tint tile
- اگر compact space بود → icon-only or icon+short label
- اگر category ناشناخته بود → `all-services` neutral fallback asset

---

## 20) Success Criteria

یک Category Artwork / Icons System برای Loomera زمانی موفق است که:
- با هویت واقعی Loomera در ZIP برند و سورس align باشد
- calm, refined, clear و product-ready بماند
- categoryها distinct باشند اما stock-like یا cliché نشوند
- در small icon size و larger artwork size هر دو خوب کار کند
- با placeholder, empty-state, dashboard و discovery surfaces هماهنگ باشد
- در light و dark mode هر دو durable باشد
- برای design، frontend، product و content team بدون تفسیر دوباره usable باشد
- category discovery را بهتر کند، نه پیچیده‌تر

---

## Appendix — پیشنهاد اجرایی کوتاه

اگر این سیستم قرار است فازبندی شود، ترتیب درست rollout چنین است:
1. اول **icon system** برای 10 family اصلی نهایی شود.
2. بعد **compact category tiles** برای chip/row/card ساخته شوند.
3. سپس **artwork tiles** برای discovery و explore تولید شوند.
4. در انتها optional editorial / campaign variants اضافه شوند.

این ترتیب با ساختار فعلی repo هم سازگارتر است، چون categoryها همین حالا در filter و card و search حضور دارند و icon layer سریع‌تر از artwork بزرگ وارد محصول می‌شود.
