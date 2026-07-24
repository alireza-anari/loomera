# Loomera Product Shell Logo System

نسخه: 1.0  
وضعیت: source-ready / handoff-ready  
برند: Loomera

---

## 1) Source Review Summary

### ساختار لوگوی فعلی Loomera
سیستم لوگوی فعلی Loomera باید از assetهای موجود برند بیاید، نه از طراحی جدید. ساختار صحیح آن شامل این لایه‌هاست:

- **Primary full logo**: wordmark اصلی Loomera به‌همراه symbol
- **Compact logo**: نسخه‌ی فشرده‌تر برای contextهای product shell
- **Glyph / app mark**: نماد مستقل برای فضاهای کوچک، app-facing و utility
- **Monochrome / reverse variants**: برای dark shell، tinted surface و contextهای low-noise

### منطق استفاده از glyph و wordmark در محصول
در product shell، wordmark نباید everywhere و بدون منطق استفاده شود. اصل سیستم این است:

- **glyph** نقش anchor اصلی در shellهای متراکم و کوچک را بازی می‌کند
- **wordmark** نقش signature برند را در shellهای high-trust یا low-noise دارد
- **full logo** فقط در جاهایی می‌آید که brand reassurance یا continuity مهم‌تر است
- **compact logo** برای هدرهای desktop و shellهای میانی مناسب است

### نوع UI در shell محصول
shell محصول Loomera چند context اصلی دارد:

- app header
- desktop sidebar
- collapsed sidebar
- mobile top bar
- auth shell
- checkout shell
- dashboard shell
- empty / loading shell

این shellها همگی باید restrained، readable، calm و product-first بمانند.

### مهم‌ترین constraintها برای logo placement در shell
- لوگو نباید decorative یا noisy شود
- wordmark نباید در فضاهای خیلی کوچک استفاده شود
- desktop و mobile باید منطق مشترک ولی context-aware داشته باشند
- RTL باید در placement و alignment رعایت شود
- حضور برند باید حس trust و continuity بدهد، نه اینکه با عملکرد UI رقابت کند

---

## 2) Shell Logo Strategy

### چه زمانی از full logo استفاده شود
از **full logo** در این contextها استفاده شود:

- auth shell
- checkout trust header
- desktop sidebar در حالت expanded
- major empty state shell
- startup / welcome shell

### چه زمانی از compact logo استفاده شود
از **compact logo** در این contextها استفاده شود:

- top header / app header در desktop
- tablet shell bars
- dashboard shellهای نسبتاً باز
- shellهایی که حضور برند باید readable باشد اما full logo زیادی dominant می‌شود

### چه زمانی فقط glyph استفاده شود
از **glyph-only** در این contextها استفاده شود:

- collapsed sidebar
- mobile top bar
- app icon / favicon
- loading shell
- utility headers
- narrow surfaces
- shellهایی که action density بالاست

### چه زمانی monochrome یا reduced-color لازم است
- روی dark shell
- روی tinted surfaces
- روی translucent headerها
- روی soft violet backgroundها
- روی سطح‌هایی که full-color contrast یا calmness را کاهش می‌دهد

### کجا wordmark نباید استفاده شود
- collapsed sidebar
- mobile top barهای فشرده
- floating bars
- action clusters
- narrow utility areas
- icon-size buttons
- loading marks
- هرجایی که برای readability مجبور می‌شوید wordmark را بیش از حد کوچک کنید

---

## 3) Product Shell Contexts

### A. Desktop Sidebar

#### Recommended logo variant
- **Expanded:** compact یا full logo
- **Collapsed:** glyph-only

#### Placement
در بالاترین بخش sidebar، قبل از provider/salon block و قبل از navigation.

#### Size logic
- Expanded logo width: `132px – 156px`
- Collapsed glyph box: `32px – 40px`

#### Spacing
- top padding: `20px`
- logo تا divider بعدی: `16px`
- logo تا provider block: `12px`

#### Behavior in expanded state
- لوگو یک brand anchor ثابت باشد
- نام سالن/مرکز زیر آن بیاید، نه اینکه جای لوگو را بگیرد
- logo area clickable به home یا app root باشد

#### Behavior in collapsed state
- فقط glyph باقی بماند
- wordmark کاملاً حذف شود
- glyph به‌صورت centered و balanced نمایش داده شود

---

### B. Top Header / App Header

#### Recommended logo variant
**Compact logo**

#### Vertical alignment
- centered on header baseline
- alignment باید optical باشد، نه فقط geometric center

#### Left/right placement in RTL
در UI فارسی و RTL، logo روی **سمت راست** بنشیند.

#### Max height / width guidance
- height: `24px – 28px`
- max width: `120px`

#### Interaction with nav and actions
- لوگو نباید با page title رقابت کند
- اگر page title وجود دارد، logo باید نقش orientation cue داشته باشد
- logo clickable باشد
- action buttons فضای بیشتری از logo area نگیرند، اما logo هم نباید dominant شود

---

### C. Mobile Top Bar

#### Recommended logo variant
**Glyph-only** در اکثر حالت‌ها

#### آیا glyph-only بهتر است یا compact mark
- برای mobile فشرده، **glyph-only** بهترین گزینه است
- compact mark فقط زمانی قابل‌قبول است که top bar بلندتر و title مستقل حذف شده باشد

#### Safe area logic
- glyph داخل box برابر `28px – 32px`
- safe inset موبایل رعایت شود
- logo area نباید به action icons بچسبد

#### Readability in small width
- wordmark حذف شود
- top bar برای title و actionها آزاد بماند
- glyph به‌عنوان brand presence کافی است

---

### D. Auth Shell

#### Recommended logo treatment
**Full logo**

#### آیا logo باید visibleتر از app shell باشد
بله.  
auth shell یکی از معدود جاهایی است که brand reassurance باید کمی visibleتر باشد.

#### Spacing around welcome/auth content
- logo تا headline: `20px – 24px`
- headline تا subtitle: `8px`
- logo block تا form card: `24px – 32px`

#### Additional guidance
- auth shell باید canonical asset لوگو را نمایش دهد
- از text-only brand block استفاده نشود
- logo باید در بالای auth card یا auth content column بنشیند، نه به‌صورت تزئینی در background

---

### E. Checkout Shell

#### Recommended logo treatment
**Compact یا full logo** در trust header

#### Trust-oriented placement
- بالای review/payment section
- نزدیک reassurance line یا secure payment line
- visible ولی restrained

#### Relation to payment and review sections
- provider identity باید همچنان اولویت داشته باشد
- Loomera logo نقش platform trust layer را بازی کند
- logo نباید payment UI را سنگین یا noisy کند

---

### F. Dashboard Shell

#### Persistent brand presence level
**Medium-low**

#### Logo emphasis vs functional UI balance
- در sidebar: visible
- در top navbar: compact یا subtle
- در content area: بدون تکرار اضافه

#### Guidance
dashboard shell باید brand را حفظ کند اما کاملاً product-first بماند.

---

### G. Empty / Loading Shell

#### Static logo or glyph
- Loading: **glyph-only**
- Major empty shell: **compact یا full logo**

#### Subtle loading mark relation
- loader بهتر است از glyph derive شود
- animation باید subtle باشد
- sparkle motif نباید به decorative motion تبدیل شود

---

## 4) Visual Rules

### Clear space
حداقل clear space در اطراف لوگو باید برابر با ارتفاع بخش مرکزی glyph در نظر گرفته شود.

### Minimum size
- full logo: حداقل `120px` عرض
- compact/full logo برای mobile-safe use: ترجیحاً `144px+`
- glyph: حداقل `20px`، ترجیحاً `24px+`

### Maximum size
- shell header logo height: حداکثر `28px`
- sidebar expanded logo width: حداکثر `156px`
- auth/checkout signature width: حداکثر `168px`

### Opacity / use on tinted surfaces
- روی tinted surface از full-color فقط در صورت contrast مناسب استفاده شود
- در translucent headers نسخه‌ی reduced-color ترجیح دارد
- opacity پایین فقط برای reverse/light version روی dark glass surface مجاز است

### Background contrast
- روی light shell: primary logo یا monochrome dark
- روی dark shell: reverse/light یا monochrome light
- روی soft violet surface: monochrome deep یا reduced-color
- روی white cards: compact/full logo فقط اگر card brand-signature role دارد

### Use on light shell
- restrained
- clean
- بدون glow
- ترجیحاً violet-deep یا monochrome dark

### Use on dark shell
- reverse/light version
- یا monochrome light
- بدون oversaturated neon violet

### Use on soft violet surfaces
- reduced-color
- deep violet monochrome
- نه full-color if noisy

### Use on white cards
- compact logo یا glyph
- اگر white card informational است، logo باید subtle باشد

### Icon alignment with typography
- alignment باید optical باشد
- کنار متن فارسی، glyph ممکن است نیاز به 1px optical adjustment داشته باشد
- فاصله‌ی mark تا wordmark: `8px – 10px`

---

## 5) Color Rules

### Light mode
بهترین نتیجه روی light mode معمولاً با این منطق به‌دست می‌آید:

- product shell mostly restrained
- dark/deep violet یا monochrome dark روی `bg`, `bgSubtle`, `surface`
- full-color فقط در shellهای low-noise یا trust-led

### Dark mode
در dark mode:

- reverse/light version یا monochrome light استفاده شود
- background بهتر است plum-based و soft باشد، نه black خالص
- logo نباید glowing یا decorative شود

### آیا logo باید full-color باشد یا mostly single-tone
برای product shell، لوگو باید **mostly single-tone / restrained** باشد.

#### Full-color preferred contexts
- auth shell
- major empty state
- expanded sidebar brand block
- onboarding or welcome moments

#### Single-tone preferred contexts
- app header
- mobile top bar
- collapsed sidebar
- dashboard shell
- dark tinted surfaces

### Glyph in active/highlight surfaces
- glyph روی active/highlight surface می‌تواند تک‌رنگ باشد
- روی selected panel از deep violet یا white استفاده شود
- accent سبز برای خود لوگو استفاده نشود

### Usageهای ممنوع
- recolor تصادفی لوگو
- pink / glam / cosmetic cliché palette
- سبز به‌عنوان رنگ اصلی لوگو
- glow-heavy brand treatment
- gradientهای noisy
- استفاده از logo روی سطح‌هایی که contrast را از بین می‌برند

---

## 6) Typography Relationship

### لوگو کنار چه type scaleهایی باید بنشیند
در shell، logo باید کنار type scaleهای UI بنشیند، نه display serif-heavy blockها.

#### Recommended companions
- top bar labels / page labels
- section titles
- H5 / label / body roles
- dashboard labels

### نسبت logo height با top bar height
اگر top bar حدود `64px` باشد:
- logo visual height: `24px – 28px`

یعنی حدود 40٪ ارتفاع bar.

### نسبت logo با sidebar section titleها
logo نباید از نظر حضور بصری از section titleها بیش از حد dominant شود.  
در expanded sidebar، لوگو باید حدود 1.5 تا 2 برابر visual block یک section title باشد.

### Relation با Yekan Bakh-led UI
- wordmark می‌تواند brand serif باشد
- اما تمام shell textها باید با UI sans system هماهنگ بمانند
- در محصول فارسی، baseline harmony با Yekan Bakh مهم‌تر از decorative brand treatment است

### Distance لوگو از page title / nav items
- logo تا page title: حداقل `16px`
- logo تا first nav item: حداقل `20px`
- logo تا action cluster: حداقل `24px`

---

## 7) Responsive & RTL Rules

### لوگو در desktop RTL کجا بنشیند
در desktop RTL، brand anchor باید در **سمت راست** shell بنشیند.

### در mobile RTL چه فشرده‌سازی‌ای مناسب است
- ابتدا wordmark حذف شود
- سپس logo به glyph-only تبدیل شود
- از کاهش شدید اندازه‌ی full logo اجتناب شود

### در collapsed sidebar چه چیزی باقی بماند
فقط **glyph** باقی بماند.

### Mixed layouts (LTR data inside RTL UI)
- logo area نباید با mixed content shift شود
- wrapper لوگو باید fixed و `flex-none` باشد
- email / code / booking ID / phone باید در blockهای LTR isolate شوند، اما لوگو area unaffected بماند

### آیا placement باید در همه shellها یکدست باشد یا slightly vary کند
logic کلی باید یکدست باشد، اما execution می‌تواند context-based کمی vary کند:

- auth: stronger
- checkout: trust-led
- dashboard: quieter
- mobile: glyph-led

---

## 8) Design Directions

### Direction 1: Minimal Restrained

#### توضیح کوتاه
glyph-first system با حضور بسیار محدود full logo.

#### مزیت
- بسیار product-clean
- کم‌نویز
- مناسب UIهای متراکم

#### ریسک
- warmth و presence برند کمتر احساس می‌شود

#### مناسب بودن برای Loomera
خوب است، اما برای Loomera کمی بیش از حد خشک و austere می‌شود.

---

### Direction 2: Softly Branded

#### توضیح کوتاه
full/compact logo در contextهای trust-led و expanded؛ glyph در contextهای compact و utility.

#### مزیت
- تعادل عالی بین brand presence و usability
- calm و premium بدون noise
- مناسب برای product shell واقعی

#### ریسک
اگر spacing یا contrast درست اجرا نشود، می‌تواند در sidebar کمی سنگین شود.

#### مناسب بودن برای Loomera
**بسیار مناسب**

---

### Direction 3: Product-Forward Premium

#### توضیح کوتاه
compact brand lockup در desktop shellها با اجرای بسیار refined و monochrome-heavy.

#### مزیت
- premium
- systematized
- mature

#### ریسک
در mobile و dashboardهای dense ممکن است زیادی formal یا سنگین شود.

#### مناسب بودن برای Loomera
مناسب است، اما از نظر اجرا حساس‌تر است.

---

## 9) Final Recommendation

### Direction نهایی
**Softly Branded**

### چرا این direction برای Loomera مناسب‌تر است
چون بهترین تعادل را بین این دو می‌سازد:

- **brand presence**
- **product usability**

### Balance نهایی
این سیستم باعث می‌شود:

- برند دیده شود اما غالب نشود
- در auth و checkout حس trust تقویت شود
- در dashboard و mobile shell usability اولویت داشته باشد
- desktop و mobile هر دو منطق یکسان ولی context-aware داشته باشند
- RTL بدون inconsistency اجرا شود

### خلاصه اجرایی
- expanded desktop sidebar + auth + checkout = full/compact logo
- desktop header + tablet bars = compact logo
- mobile + collapsed sidebar + loading = glyph-only

---

## 10) Deliverables

این سند شامل این deliverableهاست:

1. shell logo strategy
2. usage rules by context
3. visual rules
4. color rules
5. responsive / RTL rules
6. final recommended direction
7. mini handoff spec for design team
8. mini handoff spec for frontend team
9. component / naming recommendations

---

## 11) Implementation Notes

### Component naming recommendation
- `app-shell-logo`
- `app-shell-logo--full`
- `app-shell-logo--compact`
- `app-shell-logo--glyph`
- `sidebar-brand-lockup`
- `mobile-shell-glyph`
- `checkout-brand-header`
- `auth-brand-block`

### Variant mapping
#### Full logo
- `auth-brand-block`
- `checkout-brand-header`
- `sidebar-brand-lockup` در expanded
- major empty shell

#### Compact logo
- `app-shell-logo`
- desktop app header
- tablet shell bars

#### Glyph
- `mobile-shell-glyph`
- collapsed sidebar
- loading shell
- favicon / app icon

### Suggested structure
```html
<a class="app-shell-logo app-shell-logo--compact" href="/">
  <img class="app-shell-logo__mark" src="{% static 'branding/logo/loomera-glyph-primary.png' %}" alt="">
  <img class="app-shell-logo__wordmark" src="{% static 'branding/logo/loomera-logo-primary.png' %}" alt="Loomera">
</a>
```

```html
<a class="sidebar-brand-lockup" href="/">
  <!-- expanded logo -->
</a>

<a class="mobile-shell-glyph" href="/">
  <!-- glyph only -->
</a>

<div class="checkout-brand-header">
  <!-- compact logo + reassurance line -->
</div>

<div class="auth-brand-block">
  <!-- full logo + intro -->
</div>
```

### Suggested behavior hooks
```css
.app-shell-logo--glyph .app-shell-logo__wordmark {
  display: none;
}

.is-collapsed .sidebar-brand-lockup .app-shell-logo__wordmark {
  display: none;
}

.is-dark-shell .app-shell-logo {
  /* use reverse or monochrome-light asset */
}

.is-tinted-shell .app-shell-logo {
  /* prefer reduced-color or monochrome-deep asset */
}
```

### Frontend notes
- logo wrapper باید fixed-width و stable باشد
- collapse logic باید glyph-safe باشد
- logo area نباید با page title یا action buttons shift شود
- asset naming canonical باشد، نه export timestamp-based

### Design notes
- glow استفاده نشود
- provider identity و platform identity از هم جدا بمانند
- full logo فقط در contextهای trust یا continuity استفاده شود
- logo system در shell باید restrained، readable و repeatable باشد

---

## 12) Success Criteria

این سیستم زمانی موفق است که:

- از logo system فعلی Loomera بیاید، نه از لوگوی جدید
- در product shell تمیز، restrained و product-ready باشد
- در desktop و mobile consistent باشد
- در RTL خوب بنشیند
- با color system و typography فعلی align باشد
- balance درست بین brand presence و usability ایجاد کند
- برای handoff به design و frontend تیم آماده باشد

---

## Summary-Ready Version

**Loomera’s product shell logo system should be glyph-led in compact contexts and full-logo-led in trust contexts.**  
Expanded desktop sidebar, auth shell, and checkout trust zones should use the full or compact logo. Desktop headers and tablet shell bars should use the compact logo. Mobile top bars, collapsed sidebars, loading states, favicon, and app icon should use the glyph only.

The system should remain calm, restrained, readable, and RTL-aware. Brand presence must support orientation and trust without competing with functional UI. The final recommended direction for Loomera is **Softly Branded**: a balanced system that keeps the product premium, clear, and quietly branded.
