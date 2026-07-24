# Loomera Placeholder Set

نسخه: 1.0  
وضعیت: source-ready / handoff-ready  
برند: Loomera

---

## 1) Source Review Summary

هویت فعلی Loomera از نظر برند، یک سیستم **calm، refined، trustworthy، precise و human** است؛ از نظر کلامی باید با «calm confidence» عمل کند و در محصول clarify، reassure و guide را جلوتر از هر چیز نگه دارد. از نظر بصری، سیستم روی پالت violet-led با neutralهای گرم، accent سبز کنترل‌شده، UI sans-led و حضور restrained برند در shell و checkout بنا شده است.

از نظر رفتار در محصول، حضور لوگو و glyph باید محدود، context-aware و trust-led باشد: در shellهای متراکم و mobile، glyph-first؛ در auth و checkout، compact/full logo فقط در ناحیه‌های trust. همین منطق باعث می‌شود placeholderها هم **system-led** باشند، نه logo-led و نه decorative.

در بازبینی سورس فشرده‌ی فعلی، fallbackها و empty stateها هنوز بیشتر generic هستند: کارت dashed خاکستری، icon-led empty state، initial-based avatar ساده، و چند رنگ/کلاس legacy. بنابراین Placeholder Set جدید باید این شکاف را پر کند و یک لایه‌ی یکدست، low-noise و brand-consistent بسازد.

**جمع‌بندی خیلی کوتاه:**
- placeholderها باید **utility-first** باشند، نه illustration-first
- brand presence باید **subtle** بماند
- softness باید از tint و shape بیاید، نه از افکت‌های پرنور
- identity واقعی Loomera باید در **tone, color, spacing, restraint** دیده شود، نه در تکرار لوگو

---

## 2) Placeholder Strategy

### نقش Placeholderها در Loomera
Placeholder در Loomera یک «وسیله‌ی گذار» نیست؛ بخشی از continuity محصول است. وقتی تصویر واقعی نیست، UI نباید فروبپاشد یا generic شود. Placeholder باید:
- ساختار کارت را حفظ کند
- quality perception را نگه دارد
- حس incomplete بودن را کاهش دهد
- همچنان فضا را برای محتوای واقعی خالی بگذارد

### استراتژی اصلی
- **system-led, not logo-led**
- **abstract-first, object-lite where useful**
- **lightly representational only where context improves clarity**
- **brand visibility = low to medium-low**
- **texture and tint = controlled, soft, sparse**

### تصمیم نهایی استراتژیک
Placeholderهای Loomera باید بیشتر **abstract utility surfaces** باشند با مقدار کمی **context cue**. یعنی:
- provider/service/gallery در ابعاد بزرگ‌تر می‌توانند image-like abstraction داشته باشند
- avatarها می‌توانند human-lite یا initial-led باشند
- upload/empty/media tiles باید واضح، آرام و instructional بمانند
- glyph فقط در contextهای app-like/system-owned و mini utility slotها مجاز است

### چیزی که placeholderها را professional و low-noise نگه می‌دارد
- contrast کنترل‌شده
- geometry ساده و تکرارپذیر
- detail کم
- لایه‌بندی 2 تا 4 سطحی، نه بیشتر
- icon usage محدود
- logo usage نادر
- no hero treatment

---

## 3) Placeholder Categories

### A. Provider / Center Image Placeholder
**هدف:** fallback برای سالن، کلینیک، استودیو، spa، wellness center، massage center  
**جهت بصری:** abstract interior-lite؛ ترکیبی از 2 یا 3 plane نرم، horizon line خیلی لطیف، و یک focal slab برای حفظ حس «مکان»  
**ماهیت:** image-like but abstract  
**glyph:** خیر  
**شدت برند:** low  
**shape language:** rounded panels + soft frame  
**background treatment:** `cardHighlight` یا `calmGlow` در light، `cardHighlight` یا `calmGlow` dark counterpart در dark

### B. Specialist Avatar Placeholder
**هدف:** fallback برای متخصص، therapist، aesthetic practitioner، stylist  
**جهت بصری:** human-lite bust silhouette یا monogram-safe frame  
**ماهیت:** نیمه‌انتزاعی  
**glyph:** خیر  
**شدت برند:** low-medium  
**shape language:** circle یا squircle  
**background treatment:** `surfaceSoft` با linework خیلی ظریف؛ در حالت named fallback، initial اولویت دارد

### C. Customer Avatar Placeholder
**هدف:** fallback برای حساب کاربری، نظرات و comment surfaces  
**جهت بصری:** initial-first، نه silhouette-first  
**ماهیت:** abstract  
**glyph:** خیر  
**شدت برند:** low  
**shape language:** circle  
**background treatment:** neutral-soft؛ برای named users از initial با رنگ textSecondary یا primary muted

### D. Service Image Placeholder
**هدف:** fallback برای service card و service detail  
**جهت بصری:** care-layer composition؛ 3 سطح نرم که حس «service module» بدهد، نه شیء خاص  
**ماهیت:** image-like but non-literal  
**glyph:** خیر  
**شدت برند:** low  
**shape language:** rounded rectangles with one focal soft ribbon/bar  
**background treatment:** `calmGlow` برای beauty/treatment و `bookingHighlight` برای wellness/massage-safe variants

### E. Gallery Slot Placeholder
**هدف:** slot خالی در گالری مرکز، نمونه‌کار و media grid  
**جهت بصری:** frame-within-frame؛ تاکید بر جای عکس، نه illustration  
**ماهیت:** abstract utility  
**glyph:** فقط در حالت very small optional، ترجیحاً خیر  
**شدت برند:** very low  
**shape language:** image frame + inner inset + optional ratio chip  
**background treatment:** `surfaceSoft` + `borderSoft`

### F. Before/After Media Placeholder
**هدف:** media blockهای before/after وقتی فایل موجود نیست  
**جهت بصری:** دو panel متقارن با divider مرکزی ظریف  
**ماهیت:** abstract utility با labeling support  
**glyph:** خیر  
**شدت برند:** very low  
**shape language:** split card, half-panels  
**background treatment:** left/right tinted neutrals با تفاوت خیلی کم؛ نه contrast نمایشی

### G. Booking / Appointment Placeholder
**هدف:** cardهای نوبت وقتی provider media یا service image وجود ندارد  
**جهت بصری:** booking-led media slab؛ ترکیب thumbnail area + calm schedule cue  
**ماهیت:** abstract with context cue  
**glyph:** فقط در mini version optional  
**شدت برند:** low-medium  
**shape language:** rounded media tile + subtle timing stripe  
**background treatment:** `bookingHighlight` در light، dark equivalent در dark

### H. Dashboard Widget Placeholder
**هدف:** stat card، module card، quick access block  
**جهت بصری:** module-first؛ pseudo content blocks و metric-safe structure  
**ماهیت:** abstract  
**glyph:** optional در حالت empty-module system-owned، نه default  
**شدت برند:** low  
**shape language:** card skeleton geometry  
**background treatment:** `cardHighlight` یا `surfaceSoft`

### I. Saved / Favorites Placeholder
**هدف:** surfaces مربوط به saved providers/services  
**جهت بصری:** content tile + subtle saved marker area  
**ماهیت:** abstract  
**glyph:** خیر  
**شدت برند:** low  
**shape language:** rounded tile + tiny corner cue  
**background treatment:** `cardHighlight` با accent spot بسیار محدود

### J. Notification / Message Media Placeholder
**هدف:** notification item یا support thread item  
**جهت بصری:** ultra-compact system tile  
**ماهیت:** abstract  
**glyph:** فقط برای platform-originated/system notification مجاز  
**شدت برند:** low-medium only in system-owned cases  
**shape language:** 1:1 mini tile  
**background treatment:** `surfaceSoft` یا `badgePremium`/dark equivalent

### K. Checkout / Receipt Mini Placeholder
**هدف:** summary thumbnail، receipt mini media slot، payment-related small media  
**جهت بصری:** restrained and trust-led  
**ماهیت:** abstract mini tile  
**glyph:** optional، فقط اگر slot به خود platform تعلق دارد  
**شدت برند:** medium-low  
**shape language:** compact rounded rectangle  
**background treatment:** `cardHighlight` یا `surfaceSoft`؛ در checkout از CTA color پرهیز شود

### L. Generic Empty Media Tile
**هدف:** uploaderها، image slotها، attachment blockها، drag/drop area  
**جهت بصری:** clear upload frame + calm helper zone  
**ماهیت:** utility-first  
**glyph:** optional بسیار محدود؛ ترجیحاً upload icon ساده یا بدون آیکن  
**شدت برند:** low  
**shape language:** dashed یا soft-outline tile با inset panel  
**background treatment:** `surfaceSoft` + `borderSoft`; در dark از `surfaceSoft` dark + `borderSoft` dark

---

## 4) Visual Language Rules

### Shape language
- rounded و soft، نه sharp و technical
- large media: radius نزدیک به card XL
- medium tiles: radius نزدیک به LG
- small utility tiles: radius MD تا LG
- avatar: circle یا squircle؛ customer avatar ترجیحاً circle

### Corner radius
بهترین مبنا، radiusهای فعلی Loomera در typography CSS است: `md 0.875rem`، `lg 1rem`، `xl 1.25rem`؛ placeholderها باید با همین خانواده هم‌راستا بمانند.

### Line quality
- 1px soft linework
- borderها از `borderSoft` یا `line` بیایند
- no thick strokes
- no hard black outlines

### Pattern density
- حداکثر 2 pattern zone در هر placeholder
- patternها باید کمتر از 15٪ سطح را اشغال کنند
- pattern برای texture است، نه narrative illustration

### Icon usage
- icon only when function matters: upload, attachment, system media, before/after labeling
- icon must be outline or soft filled
- icon نباید قهرمان تصویر شود

### Illustration complexity
- low
- هیچ placeholder نباید بیش از 4 لایه‌ی خوانا داشته باشد
- چهره، ابزار زیبایی، وسایل سالن و objectهای literal ممنوع مگر در حد abstract cue بسیار سبک

### Amount of detail
- large provider/service placeholders: medium-low detail
- avatar placeholders: very low detail
- upload/receipt/notification placeholders: very low detail

### Texture / blur / glow
- blur فقط در حد soft diffusion layer
- glow فقط از جنس `calmGlow`، نه نور موضعی شدید
- no neon, no bloom, no glossy orb

### Negative space
- زیاد و intentional
- حداقل 35٪ فضای خالی در large placeholders
- حداقل 45٪ در avatar و mini tiles

### Tonal contrast
- textless placeholder باید contrast پایین‌تری از هر محتوای واقعی صفحه داشته باشد
- placeholder باید خوانا باشد، نه dominant
- contrast هدف: visible but recessive

### حس «premium but utility-first» چگونه ساخته می‌شود
- restraint در رنگ
- فضای خالی کافی
- سطوح نرم با linework دقیق
- عدم استفاده از عناصر شلوغ یا trend-driven
- consistency بیشتر از novelty

---

## 5) Color Rules

### Tokenهای مناسب برای placeholder background
بر اساس tokenهای فعلی Loomera، بهترین خانواده‌ها برای placeholderها این‌ها هستند:
- light: `bgSubtle #F7F6FA`, `surfaceSoft #F4F1F8`, `cardHighlight #F8F5FE`, `bookingHighlight #F1F7EF`, `calmGlow #F2ECFE`  
- dark: `bgSubtle #1D1928`, `surfaceSoft #251F33`, `cardHighlight #261F38`, `bookingHighlight #233126`, `calmGlow #2C2440`  
این پالت‌ها دقیقاً با violet-led surfaces، warmth کنترل‌شده و dark mode plum-based Loomera هماهنگ‌اند.

### Tokenهای مناسب برای subtle linework
- light: `borderSoft #ECE8F2`, `border #DDD8E8`, `line #D5D0E0`
- dark: `borderSoft #312B43`, `border #3B3550`, `line #403955`

### Tokenهای مناسب برای accent spot
- violet accent light: `secondary #9B80E0` یا `dashboardAccent #DCCFF8`
- sage accent light: `accent #A7C8A1` یا `bookingHighlight #F1F7EF`
- violet accent dark: `secondary #C1A8F0` یا `dashboardAccent #3A3157`
- sage accent dark: `accent #98BA93` یا `bookingHighlight #233126`  
accent spotها باید کمتر از 8 تا 10٪ سطح placeholder را اشغال کنند.

### Light mode placeholder palette
- neutral base: `bgSubtle`, `surfaceSoft`
- premium soft tint: `cardHighlight`, `calmGlow`
- wellness support tint: `bookingHighlight`
- outline: `borderSoft`
- accent detail: `dashboardAccent` یا low-opacity `secondary`

### Dark mode placeholder palette
- neutral base: `bgSubtle`, `surfaceSoft`
- premium tint: `cardHighlight`, `calmGlow`
- wellness tint: `bookingHighlight`
- outline: `borderSoft`
- accent detail: `secondarySoft`, `dashboardAccent`

### Textless placeholder contrast
- باید همیشه یک پله پایین‌تر از card content واقعی باشد
- light mode: بین surface و content-level، نه در سطح CTA
- dark mode: readable روی plum surfaces، بدون رسیدن به روشنایی متن اصلی

### کاربرد tokenهای خاص
- `calmGlow`: provider/service/gallery large backgrounds
- `cardHighlight`: dashboard/favorites/receipt mini
- `bookingHighlight`: booking/appointment/trust-supportive placeholders
- `surfaceSoft`: upload tile, generic empty media, customer avatar base
- `borderSoft`: outline, inset frame, split divider

### رنگ‌های نامناسب یا ممنوع
- primary CTA token به‌عنوان fill اصلی placeholder ممنوع مگر در micro accent بسیار کم
- pinkهای glamour / legacy beauty tone ممنوع
- pure black / pure white hard pairing ممنوع
- green accent به‌عنوان dominant field ممنوع
- gradientهای اشباع‌شده یا glow-heavy ممنوع

---

## 6) Logo / Glyph Usage Rules

### قاعده‌ی اصلی
Placeholderهای Loomera باید **logo-free by default** باشند.

### آیا glyph استفاده شود؟
بله، اما فقط در این contextها:
- app-like small tiles
- system-originated mini media
- checkout mini placeholder در سطوح platform-owned
- loading/empty shellهای بزرگ product-wide، نه provider/service-specific

### contextهایی که glyph مناسب نیست
- provider placeholder
- service image placeholder
- specialist/customer avatar placeholder
- gallery slot عمومی
- before/after placeholder

### چرا provider placeholder نباید glyph داشته باشد
چون طبق shell و checkout rules، provider identity باید first-class بماند و Loomera بیشتر نقش trust layer را داشته باشد، نه اینکه با هویت provider رقابت کند.

### چه وقت logo usage زیاد و اشتباه محسوب می‌شود
- وقتی در بیشتر fallbackها لوگو تکرار شود
- وقتی media placeholder شبیه تبلیغ برند شود
- وقتی logo به‌جای structure، معنا و نسبتِ فضا را پر کند
- وقتی در کارت‌های واقعی attention را از محتوای اصلی بدزدد

### رفتار در سایزهای کوچک
- در mini slotها فقط glyph اگر لازم شد
- wordmark در placeholderهای کوچک استفاده نشود
- در مقیاس زیر 32px، glyph هم فقط در system-owned cases

### سطح مجاز brand visibility
- default: 0
- optional/system-owned: 1
- trust-specific mini: 2
- هر چیزی بیشتر از این برای Placeholder Set اشتباه است

---

## 7) Typography / Label Rules

### اصل کلی
Placeholderهای نهایی باید تا حد امکان **textless** باشند. متن فقط جایی بیاید که function دارد: upload instruction، empty media label، before/after label، ratio tag، helper line.

### Roleهای مناسب از typography system
- placeholder title: `body.sm` یا در empty blockهای بزرگ `heading.h5`
- support line / helper: `caption.md` یا `body.sm`
- upload label: `label.md`
- ratio / dimension label: `caption.md`
- helper text: `caption.md`
- button-like inline action: `component.button.md`  
سیستم تایپوگرافی Loomera برای UI روی Yekan Bakh-led sans، وزن‌های میانه و scaleهای short-form تنظیم شده و برای label/caption دقیقاً مناسب همین contextهای utility است.

### Rule برای placeholder title
- حداکثر 1 خط
- 2 تا 5 کلمه
- tone = calm, direct
- مثال: `تصویری ثبت نشده است`

### Rule برای support line
- حداکثر 1 جمله
- ساختار: what happened + next step
- مثال: `می‌توانید تصویر را اکنون بارگذاری کنید یا بعداً برگردید.`

### Rule برای upload label
- فعل روشن + object
- مثال‌ها: `افزودن تصویر`, `بارگذاری فایل`, `انتخاب تصویر`

### Rule برای empty media label
- calm و blame-free
- مثال‌ها:
  - `تصویری ثبت نشده است`
  - `رسانه‌ای برای نمایش وجود ندارد`
  - `نمونه‌کاری ثبت نشده است`

### Rule برای ratio / dimension label
- همیشه text-light و secondary
- مثل: `4:3`, `1200×900`, `JPG / PNG`
- در span جدا و isolate‌شده نمایش داده شود

### RTL spacing و alignment
- title و helper در RTL راست‌چین
- icon اگر وجود دارد، در inline-start بنشیند
- spacing بین title و helper از 6 تا 8px
- helper text باید line-height باز و breathing space کافی داشته باشد

### LTR file names / dimension labels
طبق typography handoff، هر چیزی مثل URL، code، booking ID، email، phone و مشابه آن باید با `dir="ltr"` و `unicode-bidi:isolate` نمایش داده شود؛ همین قاعده برای file name، extension و dimension labels هم باید اعمال شود.

---

## 8) Product Context Mapping

### search result cards
- **placeholder:** Provider / Service Placeholder
- **ratio:** `4:3`
- **priority:** تصویر واقعی همیشه اول؛ placeholder فقط برای حفظ ساختار کارت

### provider cards
- **placeholder:** Provider / Center Image Placeholder
- **ratio:** `4:3` یا `1:1` در compact cards
- **priority:** real image > branded abstract placeholder > plain background

### specialist lists
- **placeholder:** Specialist Avatar Placeholder
- **ratio:** `1:1`
- **priority:** real avatar > named initial avatar > silhouette-lite avatar

### service cards
- **placeholder:** Service Image Placeholder
- **ratio:** `4:3`
- **priority:** real image > service abstract placeholder

### profile header
- **placeholder:** Customer Avatar / Specialist Avatar بسته به actor
- **ratio:** `1:1`
- **priority:** real image > initial-based fallback > abstract avatar

### account page
- **placeholder:** Customer Avatar Placeholder + Generic Empty Media Tile where needed
- **ratio:** `1:1`, `4:3`
- **priority:** real media > initial/fallback > empty tile

### bookings list
- **placeholder:** Booking / Appointment Placeholder
- **ratio:** `16:9` یا compact `4:3` thumbnail
- **priority:** provider/service real media > booking placeholder

### support thread
- **placeholder:** Notification / Message Media Placeholder
- **ratio:** `1:1`
- **priority:** attachment preview > system mini tile

### dashboard cards
- **placeholder:** Dashboard Widget Placeholder
- **ratio:** flexible card ratio
- **priority:** real content module > dashboard empty module tile

### gallery uploader
- **placeholder:** Gallery Slot Placeholder + Generic Upload Tile
- **ratio:** `3:2`
- **priority:** uploaded image > gallery slot > generic upload state

### checkout summary
- **placeholder:** Checkout / Receipt Mini Placeholder
- **ratio:** compact horizontal or square mini
- **priority:** provider/service media > restrained trust placeholder

### favorites
- **placeholder:** Saved / Favorites Placeholder
- **ratio:** `4:3` or list thumb `1:1`
- **priority:** real media > favorite tile placeholder

### notifications
- **placeholder:** Notification / Message Media Placeholder
- **ratio:** `1:1`
- **priority:** specific actor media > system-owned mini tile

### CMS/admin upload slots
- **placeholder:** Generic Empty Media Tile, Gallery Slot Placeholder, Before/After Placeholder
- **ratio:** context-driven
- **priority:** upload instruction clarity مهم‌تر از brand visibility

---

## 9) Design Directions

### direction 1: abstract minimal
**توضیح:** هندسه‌ی خالص، linework کم، تقریباً بدون cue موضوعی  
**مزیت:** بسیار تمیز، scalable، کم‌ریسک برای product  
**ریسک:** ممکن است برای beauty/wellness کمی بیش از حد generic و بی‌حس شود  
**مناسب بودن برای Loomera:** خوب، اما کمی خشک

### direction 2: softly branded utility
**توضیح:** abstract placeholderها با tintهای کنترل‌شده، shape language نرم و context cue محدود  
**مزیت:** بهترین تعادل بین brand feel و utility  
**ریسک:** اگر accent زیاد شود، از low-noise بودن خارج می‌شود  
**مناسب بودن برای Loomera:** بسیار مناسب

### direction 3: calm editorial product
**توضیح:** image-like abstraction با compositionهای spacious و حس editorial restraint  
**مزیت:** premium و refined  
**ریسک:** در dashboard/admin/uploader ممکن است زیادی aesthetic و کم‌کارکرد شود  
**مناسب بودن برای Loomera:** مناسب برای marketing-facing surfaces، نه هسته‌ی placeholder system

---

## 10) Final Recommendation

### Direction نهایی
**Softly Branded Utility**

### تصمیم اجرایی نهایی
- Placeholder Set نهایی Loomera باید **بیشتر abstract** باشد با مقدار کمی **light representational cue** در provider/service contexts
- branding level باید **low تا medium-low** بماند
- glyph usage باید **rare و system-owned** باشد
- color intensity باید **low-to-medium** بماند و primary CTA color مصرف نشود
- usability balance باید به نفع **clarity, continuity, and calm structure** باشد

### چرا این direction بهترین گزینه است
چون هم با voice restraint برند هماهنگ است، هم با shell logo system که logo را context-aware و subdued نگه می‌دارد، و هم با checkout kit که بر trust-led و precise بودن تأکید دارد. این جهت، Loomera را از placeholderهای generic دور می‌کند، بدون اینکه آن را به illustration brand campaign تبدیل کند.

---

## 11) Required Deliverables

این Placeholder System باید این deliverableها را شامل شود:
1. Placeholder Set master direction
2. دسته‌بندی کامل placeholderها
3. visual rules
4. color rules
5. logo/glyph usage rules
6. typography/label rules
7. context mapping
8. final recommended direction
9. mini handoff spec برای design team
10. mini handoff spec برای frontend team

---

## 12) Asset Output Requirement

### Asset list نهایی
- `provider-placeholder-4x3`
- `provider-placeholder-1x1`
- `specialist-avatar-placeholder-1x1`
- `customer-avatar-placeholder-1x1`
- `service-placeholder-4x3`
- `gallery-placeholder-3x2`
- `booking-placeholder-16x9`
- `dashboard-placeholder-card`
- `generic-upload-placeholder`
- `checkout-mini-placeholder`

### Naming recommendation
- `loomera-provider-placeholder-4x3-light`
- `loomera-provider-placeholder-4x3-dark`
- `loomera-specialist-avatar-placeholder-1x1-light`
- `loomera-generic-upload-placeholder-light`

### Folder structure suggestion
```text
static/
  branding/
    placeholders/
      provider/
      avatar/
      service/
      gallery/
      booking/
      dashboard/
      upload/
      checkout/
```

### File format recommendation
- SVG for deterministic vector placeholders
- PNG fallback for environments without inline SVG support
- token-aware CSS version برای reusable component placeholders

---

## 13) Handoff Notes

### برای Design Team
**guideline کوتاه برای consistency**
- همه‌ی placeholderها باید از یک grid و یک radius family پیروی کنند
- accent فقط برای emphasis جزئی استفاده شود
- هیچ placeholder نباید illustrative hero شود
- avatarها و media tileها باید از یک family spacing تبعیت کنند

**shape / tint / icon rules**
- shapeها rounded و stable
- tintها soft و low-saturation
- icon فقط در upload/system contexts
- اگر text ندارید، structure باید خودش context را القا کند

**do**
- placeholder را در کنار card واقعی تست کنید
- light و dark را pair-wise طراحی کنید
- textless default بسازید و labeled variant را جدا نگه دارید

**don’t**
- از لوگو برای پر کردن خلا استفاده نکنید
- از آیکن‌های cliché beauty استفاده نکنید
- از gradientهای noisy یا glow زیاد استفاده نکنید
- برای هر category style جدید نسازید؛ family consistency مهم‌تر است

### برای Frontend Team
**suggested component naming**
- `provider-image-placeholder`
- `specialist-avatar-fallback`
- `customer-avatar-fallback`
- `service-media-placeholder`
- `gallery-slot-placeholder`
- `booking-card-placeholder`
- `dashboard-widget-placeholder`
- `generic-upload-tile`
- `checkout-mini-placeholder`

**fallback logic**
1. real image exists → show real image
2. named avatar but no image → initial-based fallback
3. no media but context-known → category placeholder
4. no media and context-generic → generic upload/empty tile
5. skeleton only for loading, not for persistent no-media states

**dark/light mode swap rules**
- SVG/CSS placeholders should bind to Loomera tokens
- do not invert light assets blindly
- each placeholder family needs light and dark tuned versions

**object-fit / ratio behavior**
- provider/service/gallery placeholders باید همان ratio نهایی کامپوننت را نگه دارند
- `object-fit: cover` فقط برای image assets، نه برای vector placeholders اگر crop معنی را عوض می‌کند
- avatar fallbackها fixed aspect `1/1`

**when to show initial vs placeholder vs real image**
- customer/specialist with known name: initial first
- provider/service/gallery: category placeholder first
- platform-owned mini media: optional glyph tile

**recommended CSS/token mapping**
- backgrounds: `bgSubtle`, `surfaceSoft`, `cardHighlight`, `bookingHighlight`, `calmGlow`
- borders: `borderSoft`, `line`
- text: `textSecondary`, `textMuted`
- accent details: `secondary`, `dashboardAccent`, `accent`
- never map placeholder main fill to `primary`

---

## 14) Success Criteria

Placeholder Set زمانی موفق است که:
- با color system، typography و brand mood فعلی Loomera align باشد
- utility-first و product-ready بماند
- generic نباشد اما decorative هم نشود
- در light و dark mode هر دو خوب کار کند
- در RTL product context طبیعی بنشیند
- brand presence subtle و کنترل‌شده بماند
- برای beauty + treatments + massage + wellness مناسب باشد بدون cliché
- برای design و frontend handoff-ready باشد

---

## Summary-ready Version

**Loomera Placeholder Set should be softly branded, utility-first, and mostly abstract.**  
The system should use calm token-based surfaces, restrained geometry, and low-noise composition to preserve product continuity when real media is missing. Provider and service placeholders can be lightly representational, avatar fallbacks should stay human and simple, upload and gallery states should be instructional without becoming noisy, and glyph usage should remain rare and system-owned. The result should feel calm, clear, refined, and quietly premium—aligned with Loomera’s brand, shell, checkout, typography, and voice systems.
