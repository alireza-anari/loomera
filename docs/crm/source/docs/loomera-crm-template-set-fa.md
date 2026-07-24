# Loomera CRM Template Set

نسخه: 1.0  
زبان: فارسی / RTL-first  
وضعیت: source-ready / handoff-ready / lifecycle-ready  
مرجع: `files.zip` برای هویت برند، copy، visual email و guidelineها؛ `loomera.zip` برای triggerهای واقعی محصول، booking، checkout، notification center، payment، support و dashboard.

---

## 1) Source Review Summary

بررسی ZIPها نشان داد `files.zip` کامل‌ترین و منسجم‌ترین منبع برند است: Mini Brand Guideline، Core Copy Pack، Microcopy System، CTA & State Message Library، Domain & Email System، Notification / Email Visual Header System، Checkout Branding Kit، Product Shell Logo System، Partner Onboarding One-Pager، visual kits و design tokens را دارد. `loomera.zip` منبع واقعیت محصول است: صفحات search، booking، checkout، account، appointments، favorites، support، dashboard و notification center را نشان می‌دهد و در `apps/orders/lifecycle.py` مسیرهای notification با channelهای `dashboard`، `email` و `sms` دیده می‌شود.

هویت Loomera در منبع برند: **calm, trusted, clear, refined, human, quietly premium**. برند باید انتخاب خدمات beauty، aesthetic treatments، massage و wellness را روشن‌تر و رزرو را آرام‌تر، دقیق‌تر و قابل‌اعتمادتر کند.

Constraintهای CRM:
- فارسی و RTL-first؛ شناسه‌ها، ایمیل‌ها، URLها و order IDها به‌صورت LTR isolate شوند.
- اول clarity و reassurance، بعد persuasion.
- در booking، payment، refund، auth و support ساختار `چه شد + اثرش چیست + قدم بعدی چیست` الزامی است.
- CTAها کوتاه، فعل‌محور و explicit باشند.
- email senderها طبق domain/email system باشند: `رزرو Loomera`، `مالی Loomera`، `پشتیبانی Loomera`، `امنیت Loomera`، `ارائه‌دهندگان Loomera`.
- visual email header باید trust-first باشد، نه brand-first.
- transactional emailها با promotion مخلوط نشوند.

CRM برای Loomera باید **balanced** باشد: booking-led چون محصول discovery + booking است، و retention-led چون ارزش واقعی از repeat booking، review، saved providers، پشتیبانی قابل اعتماد و رابطه‌ی آرام با کاربر ساخته می‌شود.

---

## 2) CRM Strategy

CRM در Loomera فقط ابزار ارسال پیام نیست؛ لایه ارتباطی بین **intent، discovery، booking، payment، visit، support، review و rebook** است. هدف CRM این است که کاربر را به تصمیم نزدیک کند بدون اینکه حس فشار، عجله یا تبلیغات noisy ایجاد شود.

تعادل پیشنهادی:
- **Trust:** بالا، مخصوصاً در payment، booking، support و partner/provider onboarding.
- **Retention:** بالا، اما با cadence محدود و محترمانه.
- **Reminders:** دقیق، utility-first و بدون فروش.
- **Education:** کوتاه، کاربردی و متصل به benefit واقعی.
- **Conversion:** متوسط و context-aware، نه pressure-selling.

Cadence باید restrained باشد. برای high-intent userها اول in-app و notification center مناسب‌تر است؛ email زمانی استفاده شود که توضیح، reference یا بازگشت بعدی اهمیت دارد. SMS فقط برای زمان، پرداخت، OTP/security، appointment change یا support critical استفاده شود.

Discount/promos باید نقش محدود داشته باشند. Offer می‌تواند برای seasonal campaign یا partner-specific activation بیاید، اما default strategy نباید discount-first باشد. Promo باید tasteful باشد: context، quality و planning را تقویت کند، نه urgency مصنوعی بسازد.

Strictly transactional بمانند:
- booking confirmation، booking change، cancellation، payment failed/pending/success، refund، OTP/security، support case status، policy/legal/privacy notice.

---

## 3) Audience & Lifecycle Segments

| Segment | وضعیت کاربر | هدف CRM | Tone | ریسک over-messaging | بهترین channelها |
|---|---|---|---|---|---|
| A. New Visitor / New Sign-up | تازه وارد یا ثبت‌نام کرده، هنوز رزرو ندارد | جهت‌دهی به discovery و ساخت اعتماد اولیه | welcoming، clear، non-pushy | متوسط | Email، in-app، notification center |
| B. First-Time Booker | اولین رزرو را شروع یا تکمیل کرده | کاهش ابهام، تثبیت رزرو، اعتماد به checkout | reassuring، precise | بالا | Email، SMS برای reminder، in-app |
| C. Active Returning Customer | سابقه رزرو و بازگشت دارد | repeat booking و convenience | warm، helpful، concise | متوسط | Email، push، in-app |
| D. Inactive / Lapsing Customer | مدتی رزرو نکرده | reactivation بدون فشار | warm، calm، choice-led | بالا | Email کم‌تعداد، push محدود |
| E. High-Intent Browsing User | سرچ، فیلتر، مشاهده provider یا service زیاد دارد | کمک به تصمیم و save/book | helpful، discovery-led | متوسط | in-app، notification center، email محدود |
| F. Abandoned Booking User | booking/checkout را نیمه‌کاره رها کرده | بازگشت به flow و رفع uncertainty | exact، reassuring، no guilt | خیلی بالا | Email اول، push/SMS فقط permission-based |
| G. Post-Appointment User | خدمت انجام شده | تشکر، review، rebook در cadence جدا | appreciative، gentle | متوسط | Email، in-app، push محدود |
| H. Payment Issue User | پرداخت ناموفق/در انتظار/Refund دارد | state recovery و trust | exact، accountable، non-blaming | خیلی بالا | Email + in-app، SMS ضروری |
| I. Support-Engaged User | ticket یا تعامل پشتیبانی دارد | ownership، resolution، clarity | empathetic، practical | بالا | Email/thread، in-app، notification center |
| J. Favorite / Saved Provider User | provider/service ذخیره کرده | بازگشت به گزینه ذخیره‌شده | gentle، reminder-like | متوسط | in-app، push محدود، email کم‌تعداد |
| K. Partner / Provider lifecycle | مرکز/متخصص در onboarding یا dashboard | setup completion، profile quality، first booking | structured، operational، polished | متوسط | Email، provider dashboard notifications، in-app |

---

## 4) Channel Strategy

| Channel | نقش | Tone | Recommended use cases | What to avoid | طول پیشنهادی | Urgency tolerance |
|---|---|---|---|---|---|---|
| Email | توضیح، اعتماد، جزئیات و reference | calm + structured | welcome، booking، payment، refund، support، education، win-back | طولانی‌کردن transactional، promotion در confirmation | 90–180 واژه؛ transactional کمتر | متوسط؛ فقط payment/auth/support بالاتر |
| SMS | یادآوری و action ضروری | بسیار کوتاه و دقیق | نوبت، payment retry، تغییر مهم، OTP-like | marketing، چند CTA، متن احساسی | 70–140 کاراکتر فارسی | بالا فقط برای زمان/پرداخت |
| Push | nudge کوتاه و timely | کوتاه، انسانی، context-aware | reminder، abandoned booking، favorite، rebook | pushهای بدون context یا فروش‌محور | title 24–35، body 70–90 | متوسط؛ noisy نشود |
| In-app | guidance داخل محصول | product-led، clear | onboarding، incomplete flow، feature education، recovery | تکرار عین email، modal اجباری | title 18–32، body 60–140 | پایین تا متوسط |
| Notification center | record و scannability | status-led | booking/payment/support/provider events | campaign feed و متن marketing | title 32، body 100 | پایین؛ مثل log رفتار کند |
| WhatsApp-like | فقط اگر بعداً اضافه شود و consent دارد | conversational but restrained | support/partner coordination | broadcast marketing | 1–3 جمله | operational only |
| Partner/provider CRM | فعال‌سازی عملیاتی | polished، clear | setup، profile incomplete، first booking، freshness | وعده درآمد اغراق‌آمیز | email 120–220 واژه | متوسط برای ops |

---

## 5) Template Families

| Family | هدف | Emotional tone | Best channels | Ideal timing | Personalization | CTA intensity |
|---|---|---|---|---|---|---|
| A. Welcome / Onboarding | فعال‌سازی اولیه و راهنمایی به اولین discovery | welcoming، calm، clear | Email، in-app | بعد از sign-up / اولین session | نام، شهر، category | low-medium |
| B. Browse / Discovery Nudge | تبدیل intent به save/book | helpful، discovery-led | in-app، email محدود | بعد از رفتار high-intent | category، city، saved item | low |
| C. Abandoned Booking | بازگشت به booking ناقص | reassuring، non-guilty | Email، push محدود | 1–3 ساعت بعد، سپس 24h | service، provider، time | medium |
| D. Booking Reminder | یادآوری دقیق نوبت | concise، respectful | SMS، push، email | 24h و 2h قبل | service، time، provider، address | medium |
| E. Pre-Visit Reassurance | کاهش ابهام قبل از مراجعه | calm، practical | Email، in-app | 24h یا صبح مراجعه | address، policy، time | low |
| F. Post-Visit Follow-up | تشکر و بستن تجربه | warm، appreciative | Email، in-app | 2–6 ساعت بعد | service، provider | low |
| G. Review / Feedback Request | دریافت feedback بدون فشار | gentle، permission-based | Email، in-app، push محدود | 12–24 ساعت بعد | provider، service | low-medium |
| H. Rebook / Return Prompt | تشویق طبیعی به رزرو دوباره | helpful، warm | Email، push محدود | بر اساس چرخه خدمت | previous service/provider | medium |
| I. Reactivation / Win-back | بازگرداندن کاربر inactive | warm، choice-led | Email، push محدود | 45/90 روز | city، preferred category | low |
| J. Favorites Reminder | تبدیل save به تصمیم | gentle، reminder-like | in-app، push، email | 3–7 روز بعد از save | favorite count/provider | low |
| K. Payment / Billing Follow-up | recovery و transparency | exact، accountable | Email، in-app، SMS ضروری | فوری/30–60m | order id، amount، status | high but calm |
| L. Support / Service Recovery | ownership و حل مسئله | empathetic، practical | Email، notification center | status-based | ticket id، topic، status | medium |
| M. Seasonal / Campaign | discovery فصلی restrained | tasteful، soft | Email، in-app | ماهانه/مناسبتی | city، category | medium-low |
| N. Product / Feature Education | آموزش قابلیت با benefit | helpful، concise | Email، in-app | بعد از inactivity یا feature relevance | behavior cue | low |
| O. Loyalty / VIP / Repeat Relationship | رابطه بلندمدت با کاربران فعال | attentive، refined | Email، in-app | پس از repeat behavior | history، preferences | low-medium |
| P. Partner / Provider Lifecycle | setup، quality و activation partner | operational، polished | Email، provider dashboard | مرحله‌ای | provider name، setup step | medium |

---

## 6) Journey Mapping

| Journey | Trigger | Template family | Channel priority | Timing logic | Do | Don’t |
|---|---|---|---|---|---|---|
| signup → first browse | ثبت‌نام / اولین ورود | Welcome | in-app سپس email | فوری تا 30 دقیقه | مسیر شروع را روشن کن | چند welcome پشت‌سرهم نفرست |
| browse → save/favorite | save provider/service | Favorites | in-app، notification center | همان لحظه + یادآوری 3–7 روز | ادامه انتخاب را آسان کن | فشار برای رزرو نده |
| browse → book | انتخاب service/time | Discovery/booking guidance | in-app | همان session | friction را کم کن | پیام marketing اضافه نکن |
| book started → incomplete | abandon booking/checkout | Abandoned booking | email، push محدود | 1–3 ساعت، 24h اگر معتبر است | state + next step | guilt یا FOMO مصنوعی |
| booked → confirmed | booking_created / booking_paid / stylist_confirmed | Transactional booking | email + notification center | فوری | جزئیات و اطمینان بده | cross-sell در confirmation |
| confirmed → reminder | reminder_due_at یا موعد مراجعه | Reminder | SMS/push + email | 24h و 2h قبل | زمان/آدرس/CTA | promo در reminder |
| completed → review / rebook | service_completed/payment_completed | Postvisit، Review، Rebook | email/in-app | تشکر 2–6h، review 12–24h، rebook service-cycle | gentle ask | review فوری و چندباره |
| inactive → reactivation | 45/90 روز بدون رزرو | Win-back | email، push محدود | capped | انتخاب را یادآوری کن | discount-first یا noisy |
| payment issue → recovery | payment failed/pending | Payment recovery | in-app + email، SMS ضروری | فوری و 30–60m | state دقیق + next step | panic/blame |
| support request → follow-up | ticket created/resolved/escalated | Support | email/thread | receipt فوری، check-in 24–48h | ownership | generic بدون مسیر |
| provider journey | setup incomplete/first booking/profile stale | Partner lifecycle | email + dashboard | مرحله‌ای | operational clarity | وعده درآمد تضمینی |

---

## 7) Required Template Set

| Template | هدف | Trigger | Channel | Subject / title direction | Body structure | CTA direction | Personalization fields |
|---|---|---|---|---|---|---|---|
| Welcome email | معرفی آرام و شروع discovery | sign_up_completed | email | به Loomera خوش آمدید | greeting → value → first step → reassurance | شروع جست‌وجو | first_name، city، category |
| Welcome in-app | راهنمایی داخل محصول | first_session | in-app | به Loomera خوش آمدید | کوتاه + action | شروع جست‌وجو | first_name |
| First browse encouragement | ادامه discovery | high_intent_browse | in-app/email | گزینه‌های مناسب آماده مرورند | context → suggestion → CTA | مرور گزینه‌ها | category، city |
| Abandoned booking email | recovery رزرو ناقص | booking_abandoned | email | رزرو شما هنوز کامل نشده است | state → details → reassurance → CTA | ادامه رزرو | service، provider، time |
| Abandoned booking push/SMS | بازگشت کوتاه | booking_abandoned_valid | push/SMS | رزرو نیمه‌تمام | state + link | ادامه رزرو | resume_url |
| Booking reminder email | یادآوری با جزئیات | reminder_24h | email | یادآوری نوبت شما | details → preparation → CTA | مشاهده نوبت | service، date، time، provider |
| Booking reminder short | یادآوری ضروری | reminder_2h | SMS/push | یادآوری نوبت | service/time/link | مشاهده جزئیات | time، url |
| Pre-visit reassurance | آماده‌سازی مراجعه | previsit_24h | email/in-app | قبل از مراجعه | address/time/tips | مرور جزئیات | location، policy |
| Post-visit thank-you | بستن تجربه | service_completed | email | امیدواریم تجربه خوبی داشته باشید | thanks → details → next step | مشاهده نوبت | service، provider |
| Review request | feedback | review_requested | email/in-app | اگر فرصت دارید، تجربه‌تان را ثبت کنید | permission → value → CTA | ثبت دیدگاه | review_url |
| Rebook reminder | repeat booking | service_cycle_due | email/push | زمان رزرو دوباره؟ | cycle cue → options → no pressure | بررسی زمان‌ها | service، provider |
| Favorites reminder | saved item nudge | favorite_stale | in-app/push/email | ذخیره‌شده‌ها آماده مرورند | saved context → options | مشاهده ذخیره‌شده‌ها | favorites_count |
| Win-back email | reactivation | inactive_45d/90d | email | هر زمان آماده بودید | warm return → discovery | مرور گزینه‌های جدید | city، category |
| Win-back short | reactivation کوتاه | inactive_push_allowed | push/SMS | گزینه‌های جدید آماده‌اند | soft cue + link | مرور گزینه‌ها | discovery_url |
| Seasonal soft campaign | campaign restrained | monthly/seasonal | email/in-app | برای فصل پیش‌رو | context → curated options | مرور پیشنهادها | season، city |
| Feature education | product adoption | feature_relevant | email/in-app | انتخاب زمان ساده‌تر | pain point → feature → CTA | دیدن نحوه رزرو | feature_url |
| Payment issue follow-up | recovery پرداخت | payment_failed/pending | email/SMS/in-app | پرداخت کامل نشد | state → impact → next step | تلاش دوباره | order_id، amount، retry_url |
| Refund follow-up | transparency مالی | refund_issued | email | وضعیت بازگشت وجه | amount/status/timing | مشاهده وضعیت | refund_amount، order_id |
| Support follow-up | service recovery | ticket_updated/resolved | email/in-app | پیگیری درخواست پشتیبانی | status → next step → reply path | مشاهده درخواست | ticket_id، status |
| Partner welcome | شروع همکاری | partner_created | email | شروع همکاری با Loomera | welcome → setup overview | تکمیل اطلاعات مرکز | provider_name |
| Setup completion reminder | تکمیل onboarding | setup_incomplete | email/dashboard | راه‌اندازی مرکز آماده ادامه است | missing steps → value | ادامه راه‌اندازی | setup_step |
| Profile incomplete reminder | کیفیت پروفایل | profile_incomplete | dashboard/email | چند بخش پروفایل کامل نیست | missing fields → impact | تکمیل پروفایل | missing_fields |
| First booking congratulations | milestone partner | first_booking | email/dashboard | اولین رزرو شما ثبت شد | milestone → next ops | مشاهده رزرو | booking_id |
| Profile freshness reminder | reactivation provider | profile_stale | email/dashboard | پروفایل مرکز نیاز به مرور دارد | freshness → trust | مرور پروفایل | last_updated |

---

## 8) Email Template Rules

- **Header usage:** transactional base header پیش‌فرض است؛ compact logo یا glyph کوچک، category/status cue، title، support line اختیاری.
- **Logo presence:** full logo فقط welcome/partner/major notice؛ compact logo برای booking/payment/refund؛ glyph برای reminder/auth/payment issue.
- **Subject line:** state-led، مستقیم، بدون clickbait. برای transactional حدود 35–55 کاراکتر فارسی.
- **Preheader:** ادامه subject، نه تکرار آن؛ بهتر است reassurance یا next step بدهد.
- **Headline:** یک state روشن: «رزرو شما ثبت شد»، «پرداخت کامل نشد»، «جزئیات نوبت آماده است».
- **Body:** transactional = state → key details → next step → reassurance. Lifecycle = context → benefit → one CTA.
- **CTA placement:** یک CTA اصلی. secondary فقط برای support/help/change booking.
- **Reassurance block:** فقط وقتی ambiguity را کم می‌کند: checkout، payment، refund، support، appointment change.
- **Footer:** مدیریت اعلان‌ها، پشتیبانی، مسیر official؛ بدون copy تبلیغاتی.
- **Signature:** `تیم Loomera`، `تیم رزرو Loomera`، `تیم مالی Loomera`، `تیم پشتیبانی Loomera`.
- **Max density:** یک headline، یک summary card، حداکثر 3 detail row، یک CTA.
- **Email-safe:** table-safe، inline CSS، width حدود 600px، متن اصلی داخل image نباشد.

---

## 9) SMS / Push / Short-Form Rules

- SMS ایده‌آل: 70–140 کاراکتر فارسی؛ یک link؛ یک action.
- Push title: 24–35 کاراکتر؛ body: 70–90 کاراکتر.
- Tone: concise، status-led، polite.
- personalization فقط وقتی داده دقیق است: service/time/provider.
- booking reminder: `یادآوری + خدمت/زمان + link جزئیات`.
- payment issue: `state + action`؛ توضیح طولانی ممنوع.
- win-back: نرم و بدون urgency.
- support/recovery: state update + مسیر مشاهده.
- ultra-short بمانند: OTP/security، reminder دو ساعت قبل، payment retry، appointment change critical.

---

## 10) In-App / Notification Rules

- Title: 18–32 کاراکتر فارسی.
- Body: 60–140 کاراکتر.
- CTA: یک action واضح؛ inline برای flow، card-like برای announcement/recovery.
- Badge/status: finance، appointments، customer، stylist، all.
- calmness level بالا؛ notification center نباید campaign feed شود.
- inline message وقتی user داخل flow است؛ card notification برای dashboard/account.
- اگر email/SMS ارسال شده، in-app فقط state و shortcut را نمایش دهد، نه متن تکراری کامل.

---

## 11) Copy Rules

CRM copy باید clarify، reassure و guide کند. Subjectها direct باشند، body تا جایی explanatory باشد که ambiguity کم شود، CTAها action-led باشند. Reminder reassuring است، نه urgent. Win-back warm و low-pressure است. Review request gentle و permission-based است.

Avoid:
- «همین حالا»، «آخرین فرصت»، «از دست نده»، «تخفیف انفجاری»، «زیبایی رویایی»، «فرصت طلایی»، «عجله کنید».
- robotic copy مثل «درخواست شما پردازش شد» یا «تراکنش ناموفق بود» بدون human next step.

---

## 12) Subject Line / Title Rules

- Subject باید وعده کوچک و واقعی بدهد.
- Preheader باید subject را کامل کند.
- Open-rate از clarity بیاید، نه clickbait.
- transactional subjects کوتاه‌تر؛ education/campaign می‌تواند medium باشد.
- payment/support دقیق و non-dramatic.
- reactivation warm و choice-led.

| Family | Subject / Title directions |
|---|---|
| Welcome | «به Loomera خوش آمدید»، «انتخاب روشن‌تر از همین‌جا شروع می‌شود»، «شروع آرام در Loomera» |
| Discovery | «گزینه‌های مناسب‌تر آماده مرورند»، «برای انتخاب بعدی، از اینجا شروع کنید» |
| Abandoned booking | «رزرو شما هنوز کامل نشده است»، «جزئیات رزرو آماده ادامه است» |
| Reminder | «یادآوری نوبت شما»، «نوبت فردا / امروز شما در Loomera» |
| Pre-visit | «قبل از مراجعه؛ جزئیات آماده است»، «زمان و آدرس نوبت را مرور کنید» |
| Post-visit | «امیدواریم تجربه خوبی داشته باشید»، «نوبت شما تکمیل شد» |
| Review | «اگر فرصت دارید، تجربه‌تان را ثبت کنید»، «بازخورد کوتاه شما ارزشمند است» |
| Rebook | «زمان مناسبی برای رزرو دوباره؟»، «گزینه‌های جدید برای رزرو بعدی» |
| Win-back | «هر زمان آماده بودید، Loomera اینجاست»، «گزینه‌های جدید آماده مرورند» |
| Payment | «پرداخت رزرو کامل نشد»، «وضعیت پرداخت شما به‌روزرسانی شد» |
| Refund | «وضعیت بازگشت وجه رزرو شما»، «بازگشت وجه ثبت شد» |
| Support | «پیگیری درخواست پشتیبانی شما»، «وضعیت درخواست شما به‌روزرسانی شد» |
| Partner | «شروع همکاری با Loomera»، «Setup مرکز شما آماده ادامه است» |

---

## 13) Personalization Rules

Safe fields:
- `first_name`, `provider_name`, `specialist_name`, `service_name`, `appointment_date`, `appointment_time`, `city`, `location`, `order_id`, `ticket_id`, `appointment_url`, `support_url`.

Optional fields:
- `preferred_category`, `previous_booking_reference`, `favorites_count`, `recommendation_reason`, `refund_amount`, `estimated_refund_time`, `booking_resume_url`, `payment_retry_url`.

Rules:
- نام کاربر در welcome/lifecycle خوب است؛ در payment/support لازم نیست.
- provider/specialist/service فقط وقتی دقیق است استفاده شود.
- date/time برای reminder ضروری است؛ اگر ناقص است SMS نفرستید.
- recommendation cue نرم باشد: «بر اساس گزینه‌هایی که مرور کرده‌اید» نه «ما می‌دانیم شما چه می‌خواهید».
- token خالی هرگز نمایش داده نشود. fallback انسانی یا حذف جمله لازم است.

---

## 14) Cadence & Frequency Rules

| Flow | Cadence پیشنهادی | Frequency cap |
|---|---|---|
| Welcome | in-app فوری، email تا 30 دقیقه، education بعد از 2–3 روز فقط اگر inactive بود | 2 پیام در 7 روز |
| Browse nudge | بعد از 2+ session یا intent واضح | 1 email در 7 روز؛ 2 in-app در هفته |
| Abandoned booking | 1–3 ساعت بعد؛ follow-up حداکثر 24 ساعت اگر slot معتبر است | 2 پیام برای هر attempt |
| Reminder | 24 ساعت قبل email/push، 2 ساعت قبل SMS/push؛ same-day فقط یک reminder | 2 reminder برای هر appointment |
| Review | 12–24 ساعت بعد، یک reminder نرم 3–5 روز بعد | 2 درخواست برای هر appointment |
| Rebook | 14/30/45/60 روز بسته به service cycle؛ بدون داده عمومی 30–45 روز | 1 پیام در 30 روز |
| Win-back | 45 روز، 90 روز؛ بعد از آن کاهش محسوس | 1 پیام در 45 روز |
| Seasonal | ماهانه یا مناسبتی، نه هفتگی | 1 campaign در ماه |
| Payment recovery | فوری، سپس 30–60 دقیقه اگر هنوز unpaid | 2 پیام در 24 ساعت |
| Support follow-up | receipt فوری، update فقط با status change، resolution check بعد از 24–48 ساعت | status-based |
| Partner setup | welcome فوری، setup reminder بعد از 24–48 ساعت، profile freshness ماهانه | 2 reminder در هفته setup؛ 1 freshness در ماه |

Quiet hours: 21:00 تا 09:00 برای push/SMS غیراضطراری. Exception فقط security، payment critical و appointment change critical.

---

## 15) Promotional Restraint Rules

پروموشن در Loomera نقش supporting دارد، نه default CRM engine. Discount-first مناسب نیست در confirmation، reminder، payment/refund/support، review request و early partner onboarding.

Offer tasteful وقتی است که:
- context دارد: فصل، category، cycle یا partner-specific.
- کیفیت و برنامه‌ریزی را تقویت می‌کند.
- urgency واقعی و policy-backed دارد.
- یک CTA روشن دارد.

Avoid tropeها:
- تخفیف انفجاری، فقط امروز، از دست نده، بهترین قیمت شهر، زیبایی بی‌نهایت، FOMO-driven messaging.

---

## 16) State & Recovery Messaging

| State | Title direction | Explanation style | CTA | Reassurance | Channel priority |
|---|---|---|---|---|---|
| payment failed | پرداخت کامل نشد | چه شد + اثر روی رزرو + قدم بعدی | تلاش دوباره برای پرداخت | مبلغ/رزرو فقط با certainty بیان شود | in-app، email، SMS ضروری |
| payment pending | پرداخت در حال بررسی است | وضعیت موقت + مسیر پیگیری | مشاهده وضعیت پرداخت | از پرداخت دوباره بی‌مورد جلوگیری کن | in-app، email |
| refund issued | بازگشت وجه ثبت شد | مبلغ/روش/زمان احتمالی | مشاهده وضعیت بازگشت وجه | accountable و دقیق | email، notification center |
| booking issue | رزرو نیاز به بررسی دارد | issue ساده، بدون blame | مشاهده جزئیات / پشتیبانی | مسیر حل روشن | email، in-app |
| appointment change | تغییر در نوبت شما | چه تغییری و از چه زمانی | مرور نوبت | گزینه بررسی/پشتیبانی | SMS/push + email |
| cancellation | رزرو لغو شد | علت اگر safe است + refund/next step | مشاهده جزئیات | بدون tone احساسی | email، in-app |
| support escalation | درخواست شما در حال پیگیری بیشتر است | مالکیت + مرحله بعد | مشاهده درخواست | accountable | email |
| service unavailable | این زمان/خدمت فعلاً در دسترس نیست | state + alternatives | دیدن زمان‌های دیگر | blame-free | in-app |
| slot no longer available | این زمان دیگر قابل رزرو نیست | state + next step | انتخاب زمان دیگر | کوتاه و مستقیم | in-app فوری |
| incomplete profile/setup | اطلاعات مرکز هنوز کامل نیست | بخش‌های ناقص + اثر | تکمیل اطلاعات | operational، نه سرزنشی | provider dashboard + email |

---

## 17) Template Library Output

### 17.1 Welcome / Onboarding — `crm-template-welcome`
**Email**  
Subject: به Loomera خوش آمدید؛ انتخاب روشن‌تر از همین‌جا شروع می‌شود  
Preheader: خدمات beauty، treatments، massage و wellness را با آرامش و اطمینان پیدا و رزرو کنید.  
Body:
سلام {{first_name}}،  
Loomera برای این ساخته شده که پیدا کردن مرکز، متخصص و زمان مناسب برای خدمات beauty، aesthetic treatments، massage و wellness روشن‌تر و قابل‌اعتمادتر باشد. برای شروع می‌توانید شهر، نوع خدمت یا مرکز موردنظر را جست‌وجو کنید. هر زمان آماده بودید، مسیر رزرو قدم‌به‌قدم و قبل از پرداخت با جزئیات کامل نمایش داده می‌شود.  
CTA: شروع جست‌وجو  
Tokens: `first_name`, `city`, `preferred_category`  
Fallback: اگر نام کاربر نیست، greeting حذف شود.

**Short-form**  
Push: به Loomera خوش آمدید. خدمات beauty و wellness را روشن‌تر پیدا و آرام‌تر رزرو کنید.  
SMS: به Loomera خوش آمدید. برای شروع، خدمات و زمان‌های قابل رزرو را مرور کنید: {{discovery_url}}  
In-app: به Loomera خوش آمدید — از جست‌وجو شروع کنید و گزینه‌های مناسب را با جزئیات روشن‌تر ببینید.

### 17.2 Browse / Discovery Nudge — `crm-template-discovery-nudge`
Email subject: گزینه‌های مناسب‌تر آماده مرورند  
Body: بر اساس گزینه‌هایی که مرور کرده‌اید، چند مسیر برای ادامه انتخاب آماده است. می‌توانید خدمات، متخصص‌ها و زمان‌های موجود را بدون عجله مقایسه کنید.  
CTA: مرور گزینه‌ها  
Push: گزینه‌های مرتبط با جست‌وجوی اخیر شما آماده مرورند.  
Tokens: `city`, `preferred_category`, `recent_search_url`.

### 17.3 Abandoned Booking — `crm-template-abandoned-booking`
Email subject: رزرو شما هنوز کامل نشده است  
Preheader: اگر هنوز این زمان برایتان مناسب است، می‌توانید جزئیات را مرور و رزرو را ادامه دهید.  
Body: رزرو {{service_name}} برای {{provider_name}} هنوز نهایی نشده است. زمان و جزئیات قبل از پرداخت دوباره نمایش داده می‌شود تا با اطمینان تصمیم بگیرید. اگر زمان یا متخصص دیگری برایتان مناسب‌تر است، می‌توانید همان‌جا انتخاب را تغییر دهید.  
CTA: ادامه رزرو  
Push: رزرو شما هنوز کامل نشده است. جزئیات را مرور کنید و هر زمان آماده بودید ادامه دهید.  
SMS: رزرو شما در Loomera نهایی نشده است. ادامه رزرو: {{booking_resume_url}}  
Tokens: `service_name`, `provider_name`, `appointment_date`, `appointment_time`, `booking_resume_url`.

### 17.4 Booking Reminder — `crm-template-booking-reminder`
Email subject: یادآوری نوبت شما در Loomera  
Preheader: جزئیات زمان، مرکز و خدمت را قبل از مراجعه مرور کنید.  
Body: یادآوری کوتاه برای نوبت شما: {{service_name}} در {{provider_name}}، {{appointment_date}} ساعت {{appointment_time}}. اگر نیاز دارید جزئیات را مرور کنید، همه‌چیز در صفحه نوبت در دسترس است.  
CTA: مشاهده جزئیات نوبت  
Push: یادآوری نوبت: {{service_name}}، {{appointment_time}}. جزئیات در Loomera آماده است.  
SMS: یادآوری Loomera: نوبت {{service_name}} شما {{appointment_date}} ساعت {{appointment_time}} است. جزئیات: {{appointment_url}}.

### 17.5 Pre-Visit Reassurance — `crm-template-previsit`
Subject: قبل از مراجعه؛ جزئیات نوبت شما آماده است  
Body: برای اینکه مراجعه‌تان روشن‌تر و بی‌ابهام‌تر باشد، جزئیات نوبت در حساب شما آماده است. پیشنهاد می‌کنیم زمان، آدرس و توضیحات مرکز را قبل از مراجعه مرور کنید.  
CTA: مرور جزئیات مراجعه  
Push: قبل از مراجعه، زمان، آدرس و نکات نوبت را مرور کنید.

### 17.6 Post-Visit Thank-you — `crm-template-postvisit`
Subject: امیدواریم تجربه خوبی داشته باشید  
Body: نوبت {{service_name}} شما تکمیل شد. از اینکه مسیر انتخاب و رزرو را از Loomera انجام دادید ممنونیم. جزئیات این نوبت در حساب شما باقی می‌ماند و اگر خواستید می‌توانید بعداً برای رزرو دوباره یا ثبت دیدگاه به آن برگردید.  
CTA: مشاهده نوبت  
In-app: نوبت تکمیل شد — اگر مایل باشید، می‌توانید بعداً دیدگاهتان را ثبت کنید یا دوباره رزرو کنید.

### 17.7 Review Request — `crm-template-review-request`
Subject: اگر فرصت دارید، تجربه‌تان را ثبت کنید  
Preheader: بازخورد کوتاه شما به انتخاب بهتر کاربران دیگر کمک می‌کند.  
Body: اگر مایل باشید، می‌توانید تجربه خود از {{provider_name}} را کوتاه ثبت کنید. نظر شما به کاربران دیگر کمک می‌کند با دید روشن‌تری انتخاب کنند و به مرکز هم برای بهبود تجربه کمک می‌کند.  
CTA: ثبت دیدگاه  
Push: اگر فرصت دارید، تجربه‌تان را کوتاه ثبت کنید.

### 17.8 Rebook Reminder — `crm-template-rebook`
Subject: زمان مناسبی برای رزرو دوباره؟  
Body: اگر {{service_name}} را به‌صورت دوره‌ای انجام می‌دهید، اکنون می‌توانید زمان‌های جدید را بررسی کنید. هیچ عجله‌ای نیست؛ فقط گزینه‌ها آماده‌اند اگر بخواهید مرور کنید.  
CTA: بررسی زمان‌های جدید  
Push: اگر زمان رزرو بعدی نزدیک است، گزینه‌های جدید آماده مرورند.

### 17.9 Win-back — `crm-template-winback`
Subject: هر زمان آماده بودید، Loomera اینجاست  
Body: مدتی است در Loomera رزروی ثبت نکرده‌اید. اگر دوباره به دنبال خدمت، مرکز یا متخصص مناسب هستید، می‌توانید گزینه‌های جدید را بدون عجله مرور کنید. ما مسیر انتخاب و رزرو را روشن نگه می‌داریم؛ تصمیم با شماست.  
CTA: مرور گزینه‌های جدید  
Push: هر زمان آماده بودید، گزینه‌های جدید در Loomera قابل مرورند.

### 17.10 Favorites Reminder — `crm-template-favorites`
Subject: گزینه‌های ذخیره‌شده شما آماده مرورند  
Body: چند گزینه را در Loomera ذخیره کرده‌اید. اگر هنوز در حال تصمیم‌گیری هستید، می‌توانید جزئیات، خدمات و زمان‌های قابل رزرو را دوباره مرور کنید.  
CTA: مشاهده ذخیره‌شده‌ها  
Push: گزینه‌های ذخیره‌شده شما هنوز آماده مرورند.

### 17.11 Payment Recovery — `crm-template-payment-recovery`
Subject: پرداخت رزرو کامل نشد  
Preheader: رزرو فقط پس از پرداخت موفق نهایی می‌شود؛ می‌توانید دوباره تلاش کنید.  
Body: پرداخت رزرو شما کامل نشد. اگر مبلغی از حساب شما کسر شده باشد، وضعیت آن طبق فرآیند پرداختی بررسی و برگشت داده می‌شود. رزرو فقط پس از پرداخت موفق نهایی می‌شود. می‌توانید دوباره پرداخت را انجام دهید یا از صفحه رزرو روش قابل‌دسترس دیگری را بررسی کنید.  
CTA: تلاش دوباره برای پرداخت  
SMS: پرداخت رزرو کامل نشد. برای تلاش دوباره: {{payment_retry_url}}.

### 17.12 Refund Follow-up — `crm-template-refund-followup`
Subject: وضعیت بازگشت وجه رزرو شما  
Body: بازگشت وجه مربوط به رزرو {{order_id}} ثبت شد. مبلغ {{refund_amount}} طبق روش پرداخت/کیف پول شما پردازش می‌شود. زمان نهایی نمایش در حساب ممکن است به سرویس پرداخت یا بانک وابسته باشد.  
CTA: مشاهده وضعیت بازگشت وجه  
Push: وضعیت بازگشت وجه رزرو شما به‌روزرسانی شد.

### 17.13 Support Follow-up — `crm-template-support-followup`
Subject: پیگیری درخواست پشتیبانی شما  
Body: درخواست پشتیبانی شما درباره {{support_topic}} بررسی شد/در حال بررسی است. اگر هنوز ابهامی باقی مانده، می‌توانید از همان مسیر پاسخ دهید تا تیم پشتیبانی ادامه موضوع را پیگیری کند. هدف ما این است که وضعیت، قدم بعدی و نتیجه برای شما روشن بماند.  
CTA: مشاهده درخواست پشتیبانی  
Push: درخواست پشتیبانی شما به‌روزرسانی شد.

### 17.14 Feature Education — `crm-template-feature-education`
Subject: یک راه ساده‌تر برای انتخاب زمان مناسب  
Body: گاهی سخت‌ترین بخش رزرو، مطمئن شدن از جزئیات است. در Loomera قبل از نهایی‌سازی، می‌توانید خدمت، متخصص، زمان و اطلاعات اصلی مرکز را یک‌جا مرور کنید.  
CTA: دیدن نحوه رزرو  
In-app: قبل از نهایی‌سازی، همه جزئیات اصلی را یک‌جا ببینید.

### 17.15 Seasonal Soft Campaign — `crm-template-seasonal-campaign`
Subject: برای فصل پیش‌رو، با آرامش برنامه‌ریزی کنید  
Body: اگر برای روزهای پیش‌رو برنامه مراقبت، زیبایی یا wellness دارید، می‌توانید گزینه‌های مناسب را در Loomera مرور کنید. پیشنهادهای این پیام برای کشف گزینه‌هاست؛ تخفیف یا فوریت ساختگی محور آن نیست.  
CTA: مرور پیشنهادهای فصلی  
Push: برای فصل پیش‌رو، گزینه‌های مناسب beauty و wellness را مرور کنید.

### 17.16 Partner / Provider Lifecycle — `crm-template-partner-onboarding`
Subject: شروع همکاری با Loomera  
Preheader: مسیر setup مرکز شما مرحله‌به‌مرحله و قابل بازبینی جلو می‌رود.  
Body: به Loomera خوش آمدید. برای فعال‌سازی حضور مرکز شما، ابتدا اطلاعات اصلی مرکز، خدمات، تیم، زمان‌های کاری و چند تصویر باکیفیت تکمیل می‌شود. هر بخش قابل بازبینی است و هدف این است که پروفایل شما روشن، قابل‌اعتماد و آماده رزرو نمایش داده شود.  
CTA: تکمیل اطلاعات مرکز  
Dashboard: راه‌اندازی مرکز آماده ادامه است — اطلاعات خدمات، تیم، زمان‌ها و تصاویر را مرحله‌به‌مرحله کامل کنید.

---

## 18) Vocabulary Rules

| نوع | Preferred | Softer alternatives | Avoid |
|---|---|---|---|
| Reminder | یادآوری، مرور، آماده است، زمان نوبت | اگر فرصت دارید، هر زمان آماده بودید | فرصت را از دست نده، همین حالا، عجله کنید |
| Review | ثبت دیدگاه، بازخورد کوتاه، تجربه شما | اگر مایل باشید، اگر فرصت دارید | نظر بدهید تا جایزه بگیرید، امتیاز بده همین الان |
| Rebook | رزرو دوباره، زمان بعدی، گزینه‌های جدید | زمان مناسب بعدی، مرور زمان‌ها | دوباره باید رزرو کنید، نوبتت دیر شد |
| Help | پشتیبانی، پیگیری، روشن‌تر کنیم | اگر ابهامی مانده | تیکت، پروسه، درخواست پردازش شد |
| Payment | پرداخت کامل نشد، در حال بررسی، بازگشت وجه | وضعیت پرداخت، مسیر پیگیری | failed transaction، مشکل از شماست |
| Promo | پیشنهاد فصلی، گزینه‌های منتخب | برای برنامه‌ریزی آرام‌تر | تخفیف انفجاری، فقط امروز، از دست نده |

---

## 19) Do / Don’t Guide

### Do
1. هر پیام را با trigger واقعی و هدف مشخص شروع کنید.
2. در booking/payment/support اول state را روشن کنید، بعد CTA بدهید.
3. فارسی نیمه‌رسمی، طبیعی و RTL-first بنویسید.
4. CTAها کوتاه، فعل‌محور و outcome-aware باشند.
5. personalization فقط با داده قابل اعتماد استفاده شود.
6. email transactional را با promotion ترکیب نکنید.
7. reminder را respectful و زمان‌محور بنویسید.
8. payment/recovery را non-blaming بنویسید.
9. review request را permission-based بنویسید.
10. rebook را بر اساس چرخه واقعی خدمت تنظیم کنید.
11. sender name را بر اساس role انتخاب کنید.
12. in-app از email کوتاه‌تر و context-aware باشد.
13. SMS فقط برای action ضروری یا یادآوری حساس باشد.
14. support message accountable و practical باشد.
15. conflict با touchpointهای دیگر را قبل از ارسال چک کنید.

### Don’t
1. urgency مصنوعی نسازید.
2. confirmation email را با cross-sell شلوغ نکنید.
3. discount را محور همه lifecycleها نکنید.
4. از کلیشه‌های beauty زیاد استفاده نکنید.
5. پیام کوتاه را به email فشرده تبدیل نکنید.
6. چند CTA هم‌سطح در یک پیام نگذارید.
7. payment info را مبهم یا بیش از حد قطعی بیان نکنید.
8. token خالی نمایش ندهید.
9. user را بابت رهاکردن رزرو سرزنش نکنید.
10. support را cold یا robotic ننویسید.
11. campaign را با transactional sender نفرستید.
12. pushهای متعدد برای یک intent ارسال نکنید.
13. subject clickbait ننویسید.
14. در partner lifecycle وعده درآمد تضمینی ندهید.
15. tone را بین email، SMS و in-app متناقض نکنید.

---

## 20) Quality Checklist

- آیا template با calm confidence و هویت quietly premium Loomera هم‌راستاست؟
- آیا trigger واضح و قابل اندازه‌گیری است؟
- آیا channel-fit است؟
- آیا CTA قدم بعدی را دقیق توضیح می‌دهد؟
- آیا personalization طبیعی و safe است؟
- آیا fallback tokenها تعریف شده‌اند؟
- آیا tone بیش از حد promotional نیست؟
- آیا cadence با frequency cap تداخل ندارد؟
- آیا پیام با transactional/promo/support boundary conflict ندارد؟
- آیا sender name و address درست انتخاب شده است؟
- آیا برای payment/support، state + impact + next step کامل است؟
- آیا density برای mobile مناسب است؟
- آیا فارسی روان، RTL و بدون ترجمه‌زدگی است؟
- آیا در نبود داده، پیام کامل و انسانی می‌ماند؟
- آیا metric هدف مثل completion، review، rebook یا support resolution مشخص است؟

---

## 21) Implementation Notes

### Naming system
الگو: `crm.{lifecycle_family}.{audience}.{channel}.{variant}`

نمونه‌ها:
- `crm.welcome.customer.email.rich`
- `crm.abandoned_booking.customer.push.short`
- `crm.reminders.customer.sms.t_minus_2h`
- `crm.payment_recovery.customer.email.failed_payment`
- `crm.support_followup.customer.email.resolution_check`
- `crm.partner_onboarding.provider.email.setup_reminder`

### Folder structure
```text
crm/
  welcome/
  abandoned_booking/
  reminders/
  previsit/
  postvisit/
  review_request/
  rebook/
  winback/
  favorites/
  payment_recovery/
  refund_followup/
  support_followup/
  feature_education/
  seasonal_campaign/
  partner_onboarding/
shared/
  modules/
    email_header/
    footer/
    reassurance_block/
    booking_summary/
    payment_status/
    support_signature/
  tokens/
    personalization_tokens.json
    cadence_rules.json
    channel_rules.json
```

### Placeholder naming
`{{first_name}}`, `{{provider_name}}`, `{{service_name}}`, `{{appointment_date}}`, `{{appointment_time}}`, `{{city}}`, `{{order_id}}`, `{{payment_retry_url}}`.

### Shared modules
- `email_header.transactional`
- `email_header.booking`
- `email_header.payment`
- `email_header.support`
- `email_header.partner`
- `booking_summary.compact`
- `payment_status.reassurance`
- `support_signature.human`
- `footer.preferences`

### Channel adaptation logic
Email مادر محتواست؛ push/SMS خلاصه مکانیکی email نیست، بلکه یک پیام مستقل با همان trigger و CTA واحد است. In-app باید context-aware باشد و وقتی user داخل flow است توضیح اضافه ندهد.

---

## 22) Final Recommendation

CRM system Loomera باید **warmth متوسط رو به بالا** و **directness بالا** داشته باشد: مهربان اما نه پرحرف؛ دقیق اما نه سرد. Retention strategy باید booking-led باشد، اما با relationship building پشتیبانی شود. Reminder، rebook و win-back باید به‌ترتیب **reassuring، helpful و warm-choice-led** بمانند. Promotions نقش مکمل دارند، نه ستون اصلی.

این رویکرد برای trust + rebook + lifecycle value بهتر جواب می‌دهد چون در beauty، aesthetic treatments، massage و wellness اعتماد از وضوح، مراقبت، پیش‌بینی‌پذیری و پیگیری ساخته می‌شود؛ نه از فشار فروش.

---

## 23) Deliverables

1. CRM strategy
2. segment mapping
3. channel strategy
4. template family mapping
5. journey mapping
6. required template set
7. email rules
8. short-form rules
9. in-app rules
10. copy rules
11. subject line rules
12. personalization rules
13. cadence & frequency rules
14. promotional restraint rules
15. recovery/state messaging rules
16. full template library
17. vocabulary rules
18. do/don’t guide
19. quality checklist
20. implementation notes
21. final recommendation
22. summary-ready version برای docs/marketing یا docs/crm

---

## 24) Asset Output Requirement

Family/asset groups:
- `crm-template-welcome`
- `crm-template-abandoned-booking`
- `crm-template-booking-reminder`
- `crm-template-previsit`
- `crm-template-postvisit`
- `crm-template-review-request`
- `crm-template-rebook`
- `crm-template-winback`
- `crm-template-favorites`
- `crm-template-payment-recovery`
- `crm-template-refund-followup`
- `crm-template-support-followup`
- `crm-template-feature-education`
- `crm-template-seasonal-campaign`
- `crm-template-partner-onboarding`

Channel variants:
- email
- sms
- push
- inapp
- notification-center
- short-form
- rich-email
- minimal-transactional

---

## 25) Success Criteria

- با هویت واقعی Loomera در ZIPها align است.
- calm، trusted، refined، human و lifecycle-ready است.
- برای beauty + treatments + massage + wellness مناسب است و کلیشه‌ای نیست.
- برای customer lifecycle و partner/provider lifecycle قابل استفاده است.
- با Brand Voice، Core Copy Pack، CTA Library، domain/email system و email visual system هماهنگ است.
- source-ready و handoff-ready است.
