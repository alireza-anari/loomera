# Loomera Favicon Pack

## 1) Source Review Summary
- لوگوی اصلی Loomera در assetهای مرجع، یک wordmark serif-led با symbol ارگانیکِ برگ/گل + sparkle است و Mini Brand Guideline همین symbol را glyph مناسب برای app icon، avatar و favicon معرفی می‌کند.
- برای favicon، مناسب‌ترین عنصر همان symbol مستقل است، نه wordmark؛ چون guideline نیز استفاده از glyph را برای favicon توصیه می‌کند.
- برای ابعاد خیلی کوچک، simplification کنترل‌شده لازم بود: کاهش sparkleهای ریز، حذف تزئینات ریز و حفظ silhouette اصلی petals.
- legacy repo فقط یک `favicon.png` بزرگ را مستقیم در template لود می‌کرد و title هنوز `برند قبلی` بود؛ بنابراین هم از نظر برند و هم از نظر multi-size readiness باید جایگزین می‌شد.

## 2) Favicon Strategy
- **Base:** symbol-derived glyph from the main Loomera logo system.
- **16–32px:** simplified glyph with one dominant sparkle and four main organic forms.
- **48–64px:** full favicon master with full sparkle set.
- **Light surfaces:** violet + sage system on transparent/light canvas.
- **Dark surfaces:** lightened violet/lilac/sage remap for contrast.
- **Monochrome:** yes, included for pinned-tab, emboss-like surfaces, and contexts where full color is not appropriate.

## 3) Design Direction
- brand-consistent
- flat-first
- high-contrast
- small-size optimized
- crisp
- legible
- memorable
- not decorative

## 4) Required Deliverables
### A. Primary favicon master
- `icons/favicon.svg`
- `icons/favicon-light.svg`

### B. Small-size optimized version
- `icons/favicon-small.svg`
- `icons/favicon-16x16.png`
- `icons/favicon-32x32.png`
- `icons/favicon-48x48.png`

### C. Monochrome favicon
- `icons/favicon-monochrome.svg`
- `icons/safari-pinned-tab.svg`

### D. Light-background version
- `icons/favicon-light.svg`

### E. Dark-background version
- `icons/favicon-dark.svg`

### F. App / PWA icon direction
- `icons/apple-touch-icon.png`
- `icons/android-chrome-192x192.png`
- `icons/android-chrome-512x512.png`
- `icons/maskable-icon-512x512.png`

## 5) Required Export Sizes
Included:
- 16x16
- 32x32
- 48x48
- 64x64
- 180x180
- 192x192
- 512x512

Also included:
- maskable 512x512
- pinned-tab SVG
- ICO bundle for legacy/browser fallback

## 6) Implementation Deliverables
### Suggested filenames
- `favicon.svg`
- `favicon.ico`
- `favicon-16x16.png`
- `favicon-32x32.png`
- `favicon-48x48.png`
- `favicon-64x64.png`
- `apple-touch-icon.png`
- `android-chrome-192x192.png`
- `android-chrome-512x512.png`
- `maskable-icon-512x512.png`
- `safari-pinned-tab.svg`
- `site.webmanifest`

### Suggested folder structure
```text
static/
  branding/
    favicon/
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

### `<head>` snippet
See: `snippets/head-favicon-snippet.html`

### Manifest / theme-color
See: `snippets/site.webmanifest`
- `theme_color`: `#735CBE`
- `background_color`: `#FCFBFE`

### What each file is for
- `favicon.svg`: modern browser primary icon.
- `favicon.ico`: legacy fallback.
- `favicon-16/32/48.png`: explicit raster fallbacks.
- `apple-touch-icon.png`: iOS home screen icon.
- `android-chrome-192/512.png`: PWA/app icon assets.
- `maskable-icon-512x512.png`: Android adaptive icon safe area.
- `safari-pinned-tab.svg`: monochrome pinned tab.

## 7) Visual Presentation
See: `preview/loomera-favicon-preview.png`
It shows:
- favicon on light background
- favicon on dark background
- browser tab preview
- mobile/app icon preview
- alignment next to the main logo reference

## 8) Success Criteria
- directly derived from the Loomera logo symbol
- readable at small sizes
- aligned with current brand color system
- controlled visual noise
- usable across browser, mobile, PWA and app surfaces
- replaces the legacy single-file favicon setup cleanly
