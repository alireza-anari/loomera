# Loomera — Product Integration Notes for Provider Intro Video

## Current source observation
- مدل `Salon` در سورس Django فعلی فیلد `video` دارد.
- برای تجربه محصول بهتر، این ویدئو باید در detail page به‌عنوان یک media component مستقل نمایش داده شود.
- پیشنهاد می‌شود برای poster، mobile و teaser فیلدهای تکمیلی یا metadata اضافه شود.

## Recommended UI behavior
1. اگر `provider_intro_video` موجود است: poster-first card نمایش داده شود.
2. play action ویدئو را باز کند یا inline پخش کند.
3. default باید muted باشد.
4. در mobile، poster و play button خوانا و touch-friendly باشد.
5. اگر ویدئو وجود ندارد، UI به cover image و سپس gallery lead fallback کند.

## Accessibility
- دکمه play باید label قابل خواندن داشته باشد.
- video نباید بدون کنترل و با صدا autoplay شود.
- برای `prefers-reduced-motion` autoplay teaser خاموش شود.
- alt text / caption برای context تصویری در CMS ثبت شود.

## Performance
- استفاده از `preload="metadata"` برای full video.
- lazy load برای ویدئوهای پایین صفحه.
- poster بهینه WebP/JPEG.
- استفاده از teaser کوتاه برای discovery، نه فایل full.

## Suggested naming
- `provider_intro_video`
- `provider_intro_video_poster`
- `provider_intro_video_mobile`
- `provider_intro_video_teaser`
- `provider_intro_video_duration`
- `provider_intro_video_aspect_ratio`
- `provider_intro_video_focus_x`
- `provider_intro_video_focus_y`
