# سیستم Empty State Illustration برای Loomera
نسخه: 1.0  
وضعیت: source-ready / handoff-ready  
زبان: فارسی

## 1) Source Review Summary
هویت Loomera باید آرام، قابل‌اعتماد، refined، دقیق و انسانی بماند. محصول فارسی و RTL است، UI بر پایه‌ی Yekan Bakh-led sans تنظیم شده و رنگ‌های عملیاتی روی violet-led palette با neutralهای گرم و accent سبز کنترل‌شده سوار هستند. در چنین سیستمی، empty state باید بیشتر utility-driven باشد تا illustration-driven: یعنی هم حس continuity بدهد و هم مسیر بعدی را روشن کند، بدون اینکه decorative یا noisy شود.

### تفاوت Placeholder و Empty State Illustration
- **Placeholder**: نگه‌داشتن ساختار در غیاب media، تکرارپذیر، abstract، کم‌جزئیات
- **Empty State Illustration**: یک لایه‌ی expressive‌تر برای وضعیت‌های «خالی بودن»، با cue احساسی و راهنمایی ملایم

### Constraintهای اصلی
- blame-free
- CTA-supportive
- logo-free به‌صورت پیش‌فرض
- light/dark-safe
- هم‌خانواده با Placeholder Set، اما کمی humanتر و expressiveتر

## 2) Empty State Strategy
نقش artwork در Loomera این است که:
1. وضعیت را soften کند
2. حس بن‌بست ایجاد نکند
3. copy و CTA را support کند
4. product maturity را بالا ببرد

**سطح expressiveness:** low تا medium  
**سطح abstraction:** بیشتر abstract، با cue محدود  
**brand visibility:** پایین  
**glyph usage:** فقط در contextهای system-owned و خیلی محدود

## 3) Required States
این پکیج این stateها را پوشش می‌دهد:

- empty-state-no-results
- empty-state-no-bookings
- empty-state-no-availability
- empty-state-no-notifications
- empty-state-no-favorites
- empty-state-no-support
- empty-state-no-payment-method
- empty-state-no-services
- empty-state-no-gallery
- empty-state-dashboard-empty
- empty-state-welcome
- empty-state-generic

برای هر state دو variant ارائه شده:
- light
- dark

## 4) Visual Rules
- shape language: rounded, soft, quiet
- line quality: 1px soft / low-contrast
- detail density: کم
- negative space: زیاد و intentional
- texture/glow: فقط ملایم
- human presence: فقط در welcome و بعضی contextهای account/product به‌صورت غیرمستقیم

## 5) Color Rules
### Light
- bg: #FCFBFE
- surface: #FFFFFF
- surfaceSoft: #F4F1F8
- borderSoft: #ECE8F2
- primary: #735CBE
- secondary: #9B80E0
- accent: #A7C8A1
- calmGlow: #F2ECFE

### Dark
- bg: #16131F
- surface: #211C2E
- surfaceSoft: #251F33
- borderSoft: #312B43
- primary: #A688E6
- secondary: #C1A8F0
- accent: #98BA93
- calmGlow: #2C2440

### Usage Notes
- primary CTA color نباید fill غالب artwork شود
- accent فقط برای spotهای کوچک و reassurance cueها استفاده شود
- text-safe colors فقط در لایه‌ی copy مصرف شوند، نه داخل خود artwork به‌عنوان عنصر dominant

## 6) Logo / Glyph Rules
- default = بدون لوگو
- استفاده از glyph فقط در stateهای کاملاً system-owned و آن هم به‌صورت بسیار محدود
- provider/service/favorites/gallery artworkها باید بدون لوگو بمانند
- wordmark در empty artwork استفاده نشود

## 7) Copy Relationship
ترتیب پیشنهادی در UI:
1. illustration
2. title
3. short body
4. CTA

### Tone
- title: کوتاه، آرام، شفاف
- body: یک جمله، راهگشا
- CTA: explicit و action-led

### نمونه‌های پیشنهادی
- **No Results**
  - title: نتیجه‌ای پیدا نشد
  - body: می‌توانید جست‌وجو یا فیلترها را تغییر دهید.
  - CTA: تغییر فیلترها

- **No Bookings Yet**
  - title: هنوز نوبتی ثبت نکرده‌اید
  - body: پس از اولین رزرو، جزئیات آن از همین بخش در دسترس خواهد بود.
  - CTA: مشاهده خدمات

- **No Availability**
  - title: در حال حاضر زمان خالی موجود نیست
  - body: می‌توانید زمان یا متخصص دیگری را بررسی کنید.
  - CTA: مشاهده زمان‌های دیگر

- **No Notifications**
  - title: هنوز اعلانی ندارید
  - body: اطلاع‌رسانی‌های مهم رزرو و پرداخت در این بخش نمایش داده می‌شود.
  - CTA: بازگشت

## 8) Product Context Mapping
- search results → no-results
- bookings area → no-bookings / no-availability
- notifications → no-notifications
- favorites → no-favorites
- support center → no-support
- wallet/payment area → no-payment-method
- provider admin / CMS → no-services / no-gallery
- dashboard modules → dashboard-empty
- onboarding / first session → welcome
- generic fallback → generic

## 9) Asset Naming
نمونه‌ی naming:
- `assets/svg/light/empty-state-no-results-light.svg`
- `assets/svg/dark/empty-state-no-results-dark.svg`

## 10) Handoff Notes — Design Team
- از این artworkها به‌عنوان illustration layer استفاده کنید، نه image replacement
- light و dark را pair-wise تست کنید
- title/body/CTA باید از artwork dominantتر باشند
- از افزودن glow، iconهای اضافی یا logo watermark خودداری کنید

## 11) Handoff Notes — Frontend Team
### پیشنهادی برای component naming
- `empty-state-artwork`
- `empty-state-card`
- `dashboard-empty-state`
- `generic-empty-state`
- `media-empty-state`
- `support-empty-state`

### Behavior
- اگر داده نداریم ولی context مشخص است → state-specific artwork
- اگر media نداریم → Placeholder Set
- اگر فقط loading است → skeleton، نه empty artwork
- SVGها inline یا file-based قابل استفاده‌اند

### Spacing
- illustration تا title: 16px
- title تا body: 8px
- body تا CTA: 16px
- در mobile اندازه‌ی artwork کوچک‌تر شود، اما ratio حفظ شود

## 12) Success Criteria
این پکیج زمانی درست استفاده شده است که:
- با هویت واقعی Loomera align باشد
- با Placeholder Set هم‌خانواده بماند
- copy و CTA را support کند
- در light و dark mode equally calm بماند
- decorative نشود
- در beauty + treatments + massage + wellness context طبیعی و refined دیده شود
