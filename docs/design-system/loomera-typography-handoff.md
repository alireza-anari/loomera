# Loomera Typography Handoff

## تصمیم نهایی
- Brand / wordmark: serif-led
- Product UI: sans-led
- Main family: Yekan Bakh
- Fallback: Vazirmatn + Inter
- Optional display accent: Source Serif 4

## اندازه‌های اصلی
- Display XL: 64 / 72
- Display L: 52 / 60
- H1: 40 / 52
- H2: 32 / 44
- H3: 28 / 40
- H4: 24 / 34
- H5: 20 / 30
- Body Large: 18 / 32
- Body: 16 / 28
- Body Small: 14 / 24
- Label: 13 / 20
- Caption: 12 / 18
- Overline: 11 / 16
- Button Text: 15 / 22
- Input Text: 15 / 24
- Table Header: 13 / 20
- Table Cell: 14 / 22
- Metric: 32 / 40

## قواعد مهم
- فارسی: tracking همیشه صفر
- لاتین در headingهای بزرگ: tracking منفی مجاز
- body فارسی: line-height حدود 1.7
- metric / table numbers: tabular numerals
- URL / code / booking ID / phone / email در UI فارسی: `dir="ltr"` + `unicode-bidi:isolate`

## نصب
در `templates/base.html` بعد از `output.css`:
```django
<link rel="stylesheet" href="{% static 'css/loomera-typography.css' %}">
```

## Tailwind
فایل `design-system/loomera-tailwind-typography.ts` را در config یا theme extension خود import کن.
