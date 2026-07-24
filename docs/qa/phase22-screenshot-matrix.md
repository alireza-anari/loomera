# Phase 22 — Screenshot Matrix

## Customer mobile — 390×844

| Page / flow | Route candidate | State | Reference benchmark | Pass criteria |
|---|---|---|---|---|
| Home / discovery | `/` or customer home | logged-out / logged-in | Fresha Customer Android home | app-like, no desktop shrink, bottom nav safe |
| Search results | `search:search_page` | with query + empty query | Fresha Customer Android search/list/map | topbar, chips, cards, no overflow |
| Venue profile | salon detail route | with services/photos; no photos fallback | Fresha Android venue profile | gallery/summary/services/sticky CTA safe |
| Service selection | venue profile services | selected / not selected | Fresha service picker | selected state clear |
| Staff selection | `orders:select_stylists` | any specialist + staff list | Fresha staff picker | summary + sticky CTA |
| Date/time | `orders:select_dateTime` | slots / no slots | Fresha date/time picker | date rail/time slots readable |
| Checkout | `orders:reservation_preview` | payment required / pay in salon | Fresha checkout | summary/payment/CTA clear |
| Confirmation | confirmation route if exists | success | Fresha confirmation | success state clear, actions real |
| Account/bookings | customer account route | upcoming/past/empty | Fresha account/bookings | status badges readable |
| Favorites | favorites route | with/empty | Fresha favorites | empty state helpful |

## Partner mobile — 390×844

| Page / flow | Route candidate | State | Reference benchmark | Pass criteria |
|---|---|---|---|---|
| Dashboard home | partner dashboard route | with/empty today | Fresha Partner Android home | top context/cards/quick actions |
| Calendar | partner calendar route | today with/empty appointments | Fresha Partner calendar | day agenda and status clear |
| Appointment detail | appointment detail route | confirmed/pending/cancelled | Fresha Partner appointment detail | service/customer/payment readable |
| Clients | clients route | list/empty | Fresha Partner clients | search/cards/actions real |
| Client detail | client detail route | with history / no history | Fresha Partner client profile | history/status readable |
| Finance/payments | payments route | with payments/empty | Fresha Partner sales/payments | amount/status/cards readable |
| Invoices/POS | invoices/POS route | with/empty | Fresha Partner POS | real actions only |
| Marketing/reviews | marketing/reviews route | with/empty reviews | Fresha Partner marketing/reviews | review/campaign/profile cards |
| Reports | reports route | with data/no data | Fresha Partner reports | KPI/insight cards readable |

## Desktop public — 1440×1024

| Page / flow | Route candidate | Pass criteria |
|---|---|---|
| Homepage | `/` | website-like hero/search/services/cities/business CTA |
| Search | search route | list + filters + map/panel if real; no fake map |
| Venue profile | salon detail route | gallery + main content + booking sidebar |
| Booking flow | service/staff/date/checkout | desktop side summary and clear CTA |
| Auth/login/signup | account routes | split layout and role clarity |

## Desktop partner — 1440×1024

| Page / flow | Pass criteria |
|---|---|
| Dashboard | web-app shell, sidebar/topbar, no mobile bottom nav |
| Calendar | scheduler/list clarity, real staff/resource data only |
| CRM | table/list + detail/history readable |
| Finance | payments/invoices table and summaries readable |
| Marketing | campaign/review/profile layout readable |
| Reports | KPI grid, chart/table widgets readable |
| Onboarding/profile creator | stepper, form rhythm, action hierarchy |

## Screenshot naming

Use:

`phase22/<area>/<breakpoint>/<route-key>__<state>.png`

Examples:

- `phase22/customer-mobile/390x844/home__logged-out.png`
- `phase22/partner-desktop/1440x1024/reports__with-data.png`
