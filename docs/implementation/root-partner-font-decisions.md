# Loomera implementation decisions — root, partner mobile, Yekan Bakh

## 1. Root route

The project root `/` is now a public website-style landing page, aligned with the Fresha public website pattern.

- Root page: `templates/pages/home.html`
- Root view: `apps.salons.views.PublicHomeView`
- Root URL name: `salons:home`
- Customer discovery page remains available at: `salons:show_salons`
- Customer discovery URL: `/salons/`

This keeps desktop/public discovery separate from the mobile app-like customer experience.

## 2. Partner mobile theme

Partner mobile should stay light and Loomera-branded. The dark Fresha reference was caused by the phone OS theme, not a product requirement.

Implemented safeguards:

- `static/css/loomera-brand.css` sets `color-scheme: light`.
- `templates/dashboard_template.html` adds `data-theme="loomera-light"`.
- Partner dashboard surfaces remain light unless a future explicit dark-theme phase is added.

## 3. Yekan Bakh font readiness

The project is prepared for licensed Yekan Bakh files, but the font files themselves are not included.

Copy purchased webfont files into:

`static/fonts/yekan-bakh/`

Required filenames:

- `YekanBakh-Regular.woff2`
- `YekanBakh-Medium.woff2`
- `YekanBakh-SemiBold.woff2`
- `YekanBakh-Bold.woff2`

The CSS references are already active in:

`static/css/loomera-typography.css`

Until the files are placed there, the fallback font stack remains active.
