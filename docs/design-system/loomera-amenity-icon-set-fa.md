# Loomera Amenity Icon Set

نسخه: 1.0  
وضعیت: source-ready / handoff-ready  
زبان: فارسی  
برند: Loomera

---

## 1) Source Review Summary

### جمع‌بندی خیلی کوتاه
بررسی ZIP برند (`files.zip`) و سورس پروژه (`loomera.zip`) نشان می‌دهد Loomera یک برند **calm، clear، trusted، refined و quietly premium** است؛ با پالت violet-led، accent سبز کنترل‌شده، UI sans-led بر پایه‌ی **Yekan Bakh** و رفتار بصری کم‌نویز. Category Icon System فعلی هم با آیکن‌های **دو-رنگ، stroke-led، کم‌جزئیات و organic-utility** اجرا شده است.

### amenityها در Loomera چه نقشی دارند
amenityها در این محصول باید به تصمیم رزرو کمک کنند:  
- ریسک ادراک‌شده را کم کنند  
- انتظارات واقعی از فضا را روشن کنند  
- تفاوت میان مراکز را بدون شلوغی نشان دهند  
- در listing، detail، filter و reassurance block به کار بیایند

### تفاوت Amenity Icon Set با Category Icon Set
- **Category icons**: برای نوع خدمت/دامنه‌ی سرویس‌اند و کمی expressiveتر و category-led هستند.  
- **Amenity icons**: باید functionalتر، trust-facingتر و product-first باشند.  
- category icon نباید جای amenity icon استفاده شود؛ چون category دلالت «چه خدمتی» دارد، اما amenity دلالت «در این مرکز چه شرایط/امکاناتی» دارد.

### constraintهایی که باید رعایت شوند
- از tokenهای واقعی Loomera استفاده شود: `loomera.primary`, `secondary`, `accent`, `borderSoft`, `textMuted`, `focusRing`
- با typography فارسی و RTL موجود هم‌نشین باشد
- با Placeholder، Empty State، Shell و Dashboard language هم‌خانواده بماند
- در 20px تا 24px هم readable باشد
- شلوغ، cliché، beauty-gimmicky یا marketing-heavy نشود

---

## 2) Amenity Strategy

### تجربه‌ای که amenity iconها باید بسازند
Amenity iconهای Loomera باید حس **راهنمایی آرام** بدهند؛ نه تبلیغ. کاربر باید خیلی سریع بفهمد «این مرکز چه چیزهایی دارد» و «آیا برای من مناسب است یا نه».

### informational یا trust-building؟
**هر دو**؛ اما با اولویت product clarity.  
- در listing و filters: informational-first  
- در detail page و booking reassurance: trust-building + informational

### symbol-led یا object-led؟
برای Loomera، amenity iconها باید **object-led with restrained symbolism** باشند.  
یعنی:
- Wi‑Fi، Parking، Elevator، Card Payment → object-led / conventional
- Clean Environment، Premium Experience، Quiet Space → object-led + symbolic support cue
- Privacy-focused یا Women-friendly → هرگز صرفاً symbolic و مبهم نباشند؛ label لازم است

### سطح abstraction مناسب
- **low to medium abstraction**
- نه literal و stock-like
- نه آن‌قدر abstract که بدون label مبهم شوند

### تعادل clarity / softness / recognizability
- ساختار اصلی باید واضح و سریع‌فهم باشد
- گوشه‌ها نرم و line endingها rounded باشند
- جزئیات باید محدود و cue ثانویه کنترل‌شده باشد

### این iconها چقدر quiet باشند؟
**quiet but not timid**  
یعنی:
- حضورشان باید محسوس باشد
- ولی هرگز از title، rating، price، CTA یا booking state مهم‌تر نشوند

---

## 3) Amenity Families

برای Loomera این گروه‌بندی از groupingهای generic بهتر جواب می‌دهد:

### A. Access & Mobility
- Easy Access / Step-free Access
- Wheelchair Accessible
- Elevator

### B. Comfort & Stay Quality
- Waiting Area
- Refreshments
- Wi‑Fi
- Air Conditioning / Climate Comfort

### C. Privacy & Personal Space
- Private Room
- Privacy-focused
- Women-friendly
- VIP Room

### D. Cleanliness & Trust
- Clean / Sanitized Environment
- Quiet / Relaxing Space
- Premium Experience

### E. Practical Readiness
- Card Payment
- Online Booking
- Open Late / Flexible Hours
- Lockers
- Shower

### F. Arrival & Transport
- Parking
- Nearby Transit

### G. Family / Companion Suitability
- Family / Companion Friendly
- Child-Friendly

### دلیل این grouping
این grouping در UI واقعی بهتر map می‌شود، چون کاربر در discovery معمولاً amenityها را از منظر این سؤال‌ها می‌خواند:
1. آیا رسیدن و ورود راحت است؟
2. آیا ماندن در فضا راحت است؟
3. آیا حریم خصوصی / کیفیت فضا مناسب است؟
4. آیا این مرکز آماده و قابل‌اعتماد است؟
5. آیا برای من و همراه من مناسب است؟

---

## 4) Required Amenities

### amenityهای اصلی پیشنهادی
#### هسته‌ی لازم برای Loomera
- Parking → **پارکینگ**
- Wheelchair Accessible → **دسترسی ویلچر**
- Elevator → **آسانسور**
- Private Room → **اتاق خصوصی**
- VIP Room → **اتاق VIP**
- Waiting Area → **فضای انتظار**
- Refreshments → **پذیرایی**
- Wi‑Fi → **وای‌فای**
- Card Payment → **پرداخت با کارت**
- Online Booking → **رزرو آنلاین**
- Nearby Transit → **نزدیک حمل‌ونقل عمومی**
- Shower → **دوش**
- Lockers → **لاکر**
- Clean / Sanitized Environment → **محیط پاکیزه**
- Quiet / Relaxing Space → **فضای آرام**
- Family / Companion Friendly → **مناسب همراه و خانواده**
- Child-Friendly → **مناسب کودک**
- Premium Experience → **تجربه پریمیوم**
- Open Late / Flexible Hours → **ساعت کاری منعطف**
- Air Conditioning / Climate Comfort → **تهویه مطبوع**

#### direction-only / optional
- Easy Access → بهتر است به **ورود آسان / Step-free Access** rename شود تا با Elevator قاطی نشود
- Women-Friendly / Privacy-focused → فقط وقتی واقعاً operationally true است استفاده شود و **icon + label** داشته باشد
- Privacy-Focused → برای مراکز treatment/private بهتر از سالن‌های عمومی معنا دارد

### merge / rename پیشنهادشده
- `Easy Access` ← بهتر است با wording **Step-free Access / ورود آسان** بیاید
- `Women-Friendly` و `Privacy-focused` را merge نکنید؛ اولی social/service framing دارد، دومی spatial/privacy framing
- `Premium Experience` نباید به‌عنوان quality claim بی‌ضابطه برای همه‌ی مراکز استفاده شود؛ فقط برای tier یا curated flag

---

## 5) Amenity Roles by UI Context

### A. Listing Card Amenity Row
- **هدف:** اسکن سریع و comparative cue
- **preferred detail level:** خیلی کم
- **icon-only یا icon+label:** حداکثر 2–3 مورد icon-only برای cueهای universal؛ بقیه با tooltip یا خلاصه
- **size sensitivity:** بسیار بالا
- **brand presence:** پایین

### B. Detail Page Feature List
- **هدف:** توضیح روشن امکانات
- **preferred detail level:** medium
- **icon-only یا icon+label:** حتماً icon + label
- **size sensitivity:** متوسط
- **brand presence:** low-to-medium

### C. Amenity Chip
- **هدف:** tag-like clarity
- **preferred detail level:** کم
- **icon-only یا icon+label:** تقریباً همیشه icon + label
- **size sensitivity:** بالا
- **brand presence:** restrained

### D. Filter / Facet Icon
- **هدف:** کمک به orientation، نه تزیین
- **preferred detail level:** کم
- **icon-only یا icon+label:** label لازم است
- **size sensitivity:** بسیار بالا
- **brand presence:** خیلی کم

### E. Booking Reassurance Block
- **هدف:** کاهش تردید قبل از رزرو
- **preferred detail level:** medium
- **icon-only یا icon+label:** icon + short label
- **size sensitivity:** متوسط
- **brand presence:** medium-low

### F. Provider / Center Info Panel
- **هدف:** ساختن profile of place
- **preferred detail level:** medium
- **icon-only یا icon+label:** icon + label
- **size sensitivity:** متوسط
- **brand presence:** restrained

### G. Dashboard / Provider CMS Feature Toggle
- **هدف:** مدیریت داده، نه brand expression
- **preferred detail level:** کم
- **icon-only یا icon+label:** icon + label در فرم‌ها و toggleها
- **size sensitivity:** متوسط
- **brand presence:** low

### H. Empty State / Placeholder Support Cue
- **هدف:** فقط cue کمکی، در صورت نیاز
- **preferred detail level:** بسیار کم
- **icon-only یا icon+label:** معمولاً icon-only یا اصلاً بدون icon
- **size sensitivity:** متوسط
- **brand presence:** very low

---

## 6) Icon System Rules

### سیستم مناسب Loomera برای amenityها
**hybrid restrained outline**

یعنی:
- پایه: outline / stroke-led
- secondary cue: یک خط یا cue کمکی با accent ثانویه
- fill: فقط در dotهای بسیار کوچک یا handleهای micro
- duotone: بله، اما restrained و بدون mass fill

### ruleها
- **stroke style:** outline-first
- **line weight:** 3.75px برای ساختار اصلی در 64px؛ 2.75px برای cue ثانویه
- **active:** 4px / 3px
- **corner softness:** rounded cap + rounded join
- **geometry:** more geometric than category icons
- **recognizability:** در 20px هم silhouette باید قابل‌تشخیص بماند
- **optical balance:** center of gravity نباید بیش از حد بالا/پایین برود
- **grid discipline:** 64×64 master grid؛ safe area حدود 16–48
- **negative space:** deliberate و باز
- **brand alignment:** softness از radius و spacing بیاید، نه تزئین
- **alignment with Category Icon System:** همان family feel، ولی amenity icons باید utilitarianتر و کمتر gestural باشند

### نتیجه
Amenity iconهای Loomera نباید fully filled، glossy یا duotone-heavy باشند. بهترین اجرا همان **hybrid restrained outline** است.

---

## 7) Amenity-by-Amenity Direction

| Amenity | Visual cue | Avoid | Abstraction | Icon-only? | Tone | Recognizability note | Misuse risk |
|---|---|---|---|---|---|---|---|
| Parking | parking bay + clear P | car silhouette شلوغ | low | بله | practical | در 20px خوب می‌ماند | letter-like bias |
| Private Room | room frame + divider | bed / home-like room | low | نه | discreet | با label بهتر است | with VIP confusion |
| VIP Room | private room + sparkle | crown / diamond | low-med | نه | premium calm | بدون label با premium اشتباه می‌شود | claim inflation |
| Waiting Area | bench seat | sofa لوکس / lounge cliché | low | نه | reassuring | باید bench سریع فهمیده شود | with premium lounge |
| Refreshments | cup + soft steam | cocktail / café-heavy | low | نه | hospitable | بدون label می‌تواند beverage-only خوانده شود | service mismatch |
| Wi‑Fi | signal arcs | device silhouettes | low | بله | neutral | universal | low |
| Card Payment | card face + chip | wallet pile / currency | low | بله | transactional trust | universal enough | low |
| Online Booking | calendar + check | browser window / phone | low | بله با احتیاط | ready / easy | با label بهتر | with flexible hours |
| Wheelchair Access | accessibility figure + wheel | generic person icon | low | بله | inclusive | باید استاندارد بماند | accessibility claim |
| Elevator | lift door + arrows | stairs or building | low | بله | practical | در small size clear | with easy access |
| Shower | shower head + drops | spa steam bowl | low | بله با label بهتر | clean / wellness | clear if drops visible | with refreshments/steam |
| Lockers | locker grid + handles | wardrobe / cabinet home-like | low | بله با label بهتر | organized | grid باید واضح باشد | with waiting storage |
| Clean Environment | shield + sparkle | spray bottle / medical cross | med | نه | trust-led | label لازم است | overclaim |
| Quiet Space | cushion form + calm lines | mute speaker slash سنگین | med | نه | calm | icon-only کافی نیست | with premium/spa |
| Family Friendly | adult pair + child | pink/blue gender cues | med | نه | welcoming | label لازم است | age/gender ambiguity |
| Child Friendly | play block + cue star | teddy / cartoon | med | نه | gentle | بدون label مبهم است | too playful |
| Near Transit | pin + transit line | bus front detailed | low-med | نه | practical | با label سریع‌تر | with location generic |
| Flexible Hours | clock + soft crescent | alarm / urgency cue | med | نه | accommodating | icon-only مبهم | with online booking |
| Premium Experience | elevated surface + sparkle | crown / gem / trophy | med | نه | refined | فقط با label | overclaim |
| Air Conditioning | vent + air lines | snowflake overload | low-med | بله با label بهتر | comfort | airflow باید خوانا بماند | seasonal misunderstanding |

---

## 8) Color Rules

### tokenهای مناسب
- resting/default light: `loomera.primaryHover #6B55B3`
- resting/default dark: `loomera.primaryHover #B49AE6`
- secondary support cue light: `loomera.accent #A7C8A1` یا `loomera.secondary #9B80E0`
- secondary support cue dark: `loomera.accent #98BA93` یا `loomera.secondary #C1A8F0`

### resting state
- stroke اصلی: primaryHover / link-like violet
- cue ثانویه: accent یا secondary
- contrast: text-level contrast لازم نیست، اما icon باید clearly visible باشد

### active / selected
- light: `loomera.primary #735CBE` + `focusRing / secondary`
- dark: `loomera.primary #A688E6` + `secondary`
- برای active فقط کمی weight و glow خیلی نرم مجاز است

### muted informational state
- light: `loomera.textMuted #7A738F`
- dark: `loomera.textMuted #A79FB9`
- برای rows کم‌اهمیت، placeholder-like contexts، disabled filters

### chip / badge background
- light:
  - neutral chip: `surfaceSoft #F4F1F8`
  - soft premium chip: `badgePremium #F3EEFB`
  - trust/support chip: `bookingHighlight #F1F7EF`
- dark:
  - neutral chip: `surfaceSoft #251F33`
  - premium chip: `badgePremium #332B49`
  - trust/support chip: `bookingHighlight #233126`

### hover / focus
- hover = color jump بزرگ نداشته باشد؛ بهتر است background یا border subtly تغییر کند
- focus = از `focusRing` در container/chip استفاده شود، نه داخل خود icon

### چه رنگ‌هایی مناسب نیستند
- success green پررنگ به‌عنوان default icon
- warning / error palette برای amenityهای عادی
- CTA-level purple fill
- multi-color rainbow / gradient / neon
- yellow rating-like highlight

---

## 9) Typography Relationship

### label style
- amenity label: معادل `label.md`
- chip text: معادل `lm-chip-text`
- list label: `label.md` یا `body.sm`
- helper/tooltip: `caption.md`

### فونت
- UI family: **Yekan Bakh**, fallback: Vazirmatn + Inter
- فارسی tracking باید صفر بماند
- body فارسی line-height حدود 1.7، ولی chip و amenity label باید جمع‌وجورتر بمانند

### طول label
- حداکثر ترجیحی در chip: **14–18 کاراکتر فارسی**
- اگر بلندتر است:
  - یا wording را کوتاه کنید
  - یا فقط در list/context detail استفاده کنید

### mixed Persian / English
- label فارسی اصلی باشد
- companion English فقط در docs/CMS یا bilingual admin
- acronymهایی مثل Wi‑Fi, VIP, CMS, SVG با `dir="ltr"` و isolate بیایند

### RTL spacing
- icon تا label: 8px در chip/list
- icon تا text در compact rows: 6px
- icon همیشه در سمت راست label در RTL
- wrap rule: در dense UI ترجیح با single-line + ellipsis است؛ در detail list دوخطی مجاز

---

## 10) Product Fit Rules

### listing card
- 2 یا حداکثر 3 amenity مهم
- ترجیحاً compact icon + short label یا icon + tooltip
- اگر amenities زیادند: `+N مورد دیگر`

### detail page
- full amenity list
- grouped by family یا priority
- icon + label ضروری

### search filters
- icon فقط cue کمکی است
- label باید dominant بماند
- selected state در chip/filter bar واضح باشد

### chips
- 20px icon + label
- background نرم
- از fill سنگین پرهیز

### booking reassurance block
- 2 تا 4 amenity trust-facing
- مثال: محیط پاکیزه، رزرو آنلاین، پرداخت با کارت، فضای آرام

### dashboard / CMS toggles
- icon کوچک + label
- اگر space محدود است، icon optional است

### mobile layouts
- compact variant اولویت دارد
- icon-only فقط برای universal cues
- privacy/premium/family items روی موبایل هم label بخواهند

### compact rows
- icon 16–20px
- label 13px equivalent
- اگر فضا خیلی کم است: فقط text بهتر از icon مبهم است

### چه وقت icon-only کافی است؟
- Parking
- Wi‑Fi
- Card Payment
- Online Booking
- Wheelchair Access
- Elevator
- Shower
- Lockers

### چه وقت icon + label لازم است؟
- تقریبا همه‌ی trust-facing و quality-facing amenityها
- به‌خصوص Quiet Space، Premium Experience، Family Friendly، Child Friendly، Clean Environment

### چه وقت فقط text بهتر است؟
- وقتی claim حساس است
- وقتی amenity uncommon یا culturally sensitive است
- وقتی label خودش روشن‌تر از icon عمل می‌کند

### چه وقت “more” pattern لازم است؟
- listing card
- grid cards
- compact search results
- mobile chips row

---

## 11) Avoiding Cliché & Ambiguity

### کلیشه‌هایی که باید avoid شوند
- تاج، الماس، شاین بیش از حد برای premium
- صورت زنانه، مژه، لب، ناخن برای amenityها
- برگ/گل بیش‌ازحد decorative
- فنجان fancy یا cocktail-like برای refreshments
- علامت medical cross برای clean
- خانه/مبل خانگی برای waiting/private
- car silhouette detailed برای parking
- کودک کارتونی یا teddy bear برای child-friendly
- mute speaker تهاجمی برای quiet space

### symbolهای ambiguous یا weak
- star تنها برای premium
- shield تنها برای clean
- pin تنها برای near transit
- clock تنها برای flexible hours
- heart تنها برای family-friendly
- sparkle تنها برای VIP

### چگونه elegant ولی واضح بمانند
- یک object اصلی + یک cue ثانویه
- geometry منظم، rounded و کم‌جزئیات
- رنگ کنترل‌شده و بدون fill انبوه
- label در contextهای حساس

### چه چیزهایی آن‌ها را salon-only یا gender-coded می‌کند
- comb, lipstick, heel, eyelashes
- pink-only palette
- feminine silhouettes
- “luxury lounge” trope
- ornament-heavy beauty motifs

---

## 12) Do / Don’t Guide

### Do — 12 قانون مهم
1. اول meaning، بعد style  
2. روی 20px تست کنید  
3. یک ساختار اصلی و یک cue ثانویه کافی است  
4. strokeها را consistent نگه دارید  
5. rounded cap و rounded join را حفظ کنید  
6. از tokenهای واقعی Loomera استفاده کنید  
7. iconها را با label واقعی تست کنید  
8. light و dark را pair-wise بررسی کنید  
9. در filters روی text dominance تأکید کنید  
10. amenity و category را بصری از هم متمایز نگه دارید  
11. برای claimهای حساس icon-only استفاده نکنید  
12. “quiet premium” را از restraint بگیرید، نه تزئین

### Don’t — 12 خطای رایج
1. استفاده از stock iconهای generic  
2. نازک‌کردن بیش از حد stroke  
3. fill سنگین و decorative  
4. استفاده از gradient، glow یا neon  
5. استفاده از چند motif داخل یک icon  
6. تکیه بر symbolهای مبهم بدون label  
7. gender-coding ناخواسته  
8. قاطی‌کردن amenity با category/service icon  
9. استفاده از CTA color به‌عنوان default  
10. تبدیل premium به crown/diamond cliché  
11. overclaim در clean / premium / accessibility  
12. ساختن variantهای متعدد بدون rule روشن

---

## 13) Quality Checklist

- آیا در 20px خواناست؟
- آیا meaning در کمتر از 1–2 ثانیه فهمیده می‌شود؟
- آیا با Category Icons اشتباه گرفته نمی‌شود؟
- آیا silhouette واضح است؟
- آیا cue ثانویه ضروری و کنترل‌شده است؟
- آیا icon در chip، list و filter سالم می‌ماند؟
- آیا light و dark هر دو خوب‌اند؟
- آیا با label فارسی خوب می‌نشیند؟
- آیا در RTL spacing درست دارد؟
- آیا overclaim ایجاد نمی‌کند؟
- آیا از clichéهای salon/beauty دور مانده؟
- آیا tone برند Loomera حفظ شده است؟

---

## 14) Technical Delivery Notes

### preferred export formats
- SVG = master
- PNG preview = فقط برای review
- در محصول: inline SVG یا sprite/component export

### minimum sizes
- master: 64×64
- standard UI: 20–24px
- compact: 16–20px
- هرگز کمتر از 16px برای amenityهای non-universal

### icon grid guidance
- 64×64 viewBox
- safe drawing area around 16–48
- optical padding آزاد اما controlled

### SVG usage notes
- `stroke-linecap="round"`
- `stroke-linejoin="round"`
- fill فقط برای dotهای micro
- active variant با drop shadow خیلی سبک مجاز است
- CSS color override فقط اگر contrast حفظ می‌شود

### optical padding rules
- top/bottom drift نداشته باشد
- در chip، icon از baseline text جدا دیده شود
- visual center را نه بر اساس box، بلکه بر اساس perception تنظیم کنید

### variants
- light
- dark
- active-light
- active-dark
- muted-light
- muted-dark
- compact-light
- compact-dark

### suggested field naming
- `amenity_icon`
- `amenity_icon_dark`
- `amenity_icon_active`
- `amenity_label_fa`
- `amenity_label_en`
- `amenity_slug`
- `amenity_family`
- `amenity_order`
- `amenity_is_highlighted`
- `amenity_icon_compact`

### folder structure پیشنهادی
```text
loomera-amenity-icon-set/
  assets/
    svg/
      light/
      dark/
      active-light/
      active-dark/
      muted-light/
      muted-dark/
      compact-light/
      compact-dark/
  docs/
  manifest/
  preview/
```

---

## 15) Design Directions

### direction 1: minimal functional outline
- **توضیح:** کاملاً utility-led، تقریباً mono-tone، بدون cue ثانویه پررنگ
- **مزیت:** بالاترین readability و کمترین noise
- **ریسک:** ممکن است کمی خشک و generic شود
- **مناسب بودن برای Loomera:** خوب است، اما کمی از softness برند کم می‌کند

### direction 2: softly branded utility icons
- **توضیح:** outline utility با cue ثانویه‌ی نرم و palette کنترل‌شده
- **مزیت:** هم product-ready است، هم family feel برند را حفظ می‌کند
- **ریسک:** اگر cue ثانویه زیاد شود، با category icons overlap پیدا می‌کند
- **مناسب بودن برای Loomera:** **بسیار مناسب**

### direction 3: refined hybrid amenity symbols
- **توضیح:** کمی expressiveتر، با abstraction و secondary motif بیشتر
- **مزیت:** distinctiveness بالاتر
- **ریسک:** در small size ambiguity بیشتر می‌شود
- **مناسب بودن برای Loomera:** فقط برای بعضی trust-facing contexts، نه به‌عنوان default

---

## 16) Final Recommendation

### انتخاب نهایی
برای Loomera بهترین گزینه:
**direction 2 — softly branded utility icons**

### چرا
چون Loomera نیاز دارد amenityها:
- سریع فهمیده شوند
- اعتماد بسازند
- با category icon system هم‌خانواده باشند
- اما در product UI زیادی expressive یا decorative نشوند

### مشخصات direction نهایی
- **abstraction level:** low to medium
- **color intensity:** restrained
- **default style:** outline-led با secondary cue محدود
- **icon-only:** فقط برای universal cues کافی است
- **family feel:** stroke, radius, spacing و two-tone discipline مشترک
- **distinctness:** amenityها با geometry utilitarian و gesture کمتر از categoryها جدا می‌مانند

### نتیجه
این direction بهترین تعادل را برای **trust + usability + booking decision** می‌سازد، چون:
- clutter تولید نمی‌کند
- در small size می‌ماند
- برای filter/list/detail یکدست است
- و premium بودن را بدون ادعا و تزئین حفظ می‌کند

---

## 17) Deliverables

1. amenity strategy  
2. amenity family mapping  
3. required amenity mapping  
4. icon system rules  
5. amenity-by-amenity direction  
6. color rules  
7. typography relationship rules  
8. product fit rules  
9. anti-cliché / anti-ambiguity rules  
10. do/don’t guide  
11. quality checklist  
12. technical delivery notes  
13. final recommended direction  
14. summary-ready version برای docs/design-system یا docs/brand

---

## 18) Asset Output Requirement

### assetهای ساخته‌شده
- `amenity-icon-parking`
- `amenity-icon-private-room`
- `amenity-icon-vip-room`
- `amenity-icon-waiting-area`
- `amenity-icon-refreshments`
- `amenity-icon-wifi`
- `amenity-icon-card-payment`
- `amenity-icon-online-booking`
- `amenity-icon-wheelchair-access`
- `amenity-icon-elevator`
- `amenity-icon-shower`
- `amenity-icon-lockers`
- `amenity-icon-clean-environment`
- `amenity-icon-quiet-space`
- `amenity-icon-family-friendly`
- `amenity-icon-child-friendly`
- `amenity-icon-near-transit`
- `amenity-icon-flexible-hours`
- `amenity-icon-premium-experience`
- `amenity-icon-air-conditioning`

### variantها
- light
- dark
- active-light
- active-dark
- muted-light
- muted-dark
- compact-light
- compact-dark

### naming
`amenity-icon-{slug}.svg`

---

## 19) Handoff Notes

### برای Design Team
- Amenity و Category را visual cousin نگه دارید، نه clone
- secondary cue را هرگز dominant نکنید
- claim-sensitive iconها را با label استفاده کنید
- در review حتماً 20px test و chip test انجام دهید
- برای privacy/premium/family از text support استفاده کنید
- از color restraint خارج نشوید

### برای Frontend Team
- component naming پیشنهادی:
  - `amenity-icon`
  - `amenity-chip`
  - `amenity-feature-row`
  - `amenity-filter-icon`
  - `amenity-list-item`
  - `amenity-reassurance-badge`
- icon vs icon+label:
  - universal cues → icon-only مجاز
  - بقیه → icon + label
- light/dark:
  - asset pair-wise swap
- selected/filter state:
  - از active variant + chip background نرم استفاده شود
- responsive:
  - mobile = compact icon + short label یا more pattern
- SVG implementation:
  - inline SVG ترجیح دارد
  - title/desc را می‌توان در SSR حذف یا سفارشی کرد
- fallback logic:
  - اگر icon ناشناخته بود → text-only label
  - اگر label طولانی بود → full list context، نه chip

---

## 20) Success Criteria

- Amenity Icon Set با هویت واقعی Loomera align باشد
- calm، refined، clear و product-ready بماند
- amenityها سریع و دقیق فهمیده شوند
- در 20px و compact UI سالم بمانند
- با Category Icons، Placeholderها و Product Shell هماهنگ باشند
- light و dark mode هر دو خوب کار کنند
- handoff-ready برای design، frontend، product و content باشند
