# Loomera Asset Pack Reference

این فایل مرجع naming و usage برای asset packageهای برند Loomera است تا handoff بین design، frontend و content تیم‌ها یکدست بماند.

## بسته‌های مرجع
- `Logo.zip`
- `loomera-favicon-pack (1).zip`
- `Og Images.zip`

## نکته‌ی مهم
بعضی فایل‌های خام export شده از ابزار طراحی هنوز نام‌های generic یا timestamp-based دارند. این نام‌ها برای آرشیو اولیه قابل قبول‌اند، اما **canonical naming** برای repo و handoff نیستند.

## Naming Convention پیشنهادی برای import به repo

### Logo
```text
static/branding/logo/
  loomera-logo-primary.png
  loomera-logo-primary-dark.png
  loomera-logo-monochrome-dark.png
  loomera-logo-monochrome-light.png
  loomera-glyph-primary.png
  loomera-glyph-monochrome.png
```

### Favicon / App Icons
```text
static/branding/favicon/
  favicon.svg
  favicon.ico
  favicon-16x16.png
  favicon-32x32.png
  favicon-48x48.png
  favicon-64x64.png
  apple-touch-icon.png
  android-chrome-192x192.png
  android-chrome-512x512.png
  maskable-icon-512x512.png
  safari-pinned-tab.svg
  site.webmanifest
```

### OG Images
```text
static/branding/og/
  loomera-og-primary.png
  loomera-og-alt-soft.png
  loomera-og-alt-dark.png
```

## Implementation Priority
1. favicon pack برای head/meta و PWA touchpointها
2. primary logo + glyph برای header/app/avatar surfaces
3. OG image برای social/meta previews

## Brand Alignment Rules
- از **glyph** برای favicon، app icon و avatar استفاده شود.
- از **primary logo** برای brand hero، partner docs و cover assets استفاده شود.
- از نام‌های generic مثل `ChatGPT Image ...` در repo نهایی استفاده نشود.
- اگر asset قدیمی هنوز در template استفاده می‌شود، در doc به‌عنوان legacy note مشخص شود، نه canonical reference.

## Legacy note
در وضعیت فعلی repo، `templates/base.html` هنوز یک `favicon.png` تک‌فایلی را لود می‌کند. این setup باید از نظر implementation به favicon system چندسایزه Loomera replace شود؛ اما مرجع این تغییر، فایل‌های داخل favicon pack و snippetهای design-system هستند.
