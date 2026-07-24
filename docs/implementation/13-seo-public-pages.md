# مرحله 13 - SEO، صفحات عمومی، ساختار URL و رشد ارگانیک

## هدف
این مرحله پایه SEO فنی و صفحات عمومی Loomera را بدون بازنویسی UI فعلی تکمیل می‌کند. تمرکز روی URLهای slugدار، sitemap، robots.txt، canonical، schema صفحه سالن/خدمت/مقاله و جلوگیری از index شدن صفحات فیلترشده جستجو است.

## تصمیم‌های سازگاری
- مسیر قدیمی `detail_salon/<id>/` حذف نشد و به مسیر slugدار جدید 301 redirect می‌شود.
- صفحه جستجو همچنان همان UI فعلی را دارد، اما `noindex,follow` و canonical ثابت دریافت کرد.
- templateهای عمومی فقط meta/schema/canonical دریافت کردند و layout، Tailwind و پالت رنگی تغییر نکرد.
- sitemap مقاله‌های قبلی حفظ شد و sitemap سالن/خدمات/دسته خدمات/صفحات ثابت به آن اضافه شد.

## قابلیت‌های اضافه‌شده
- `django.contrib.sitemaps` در `INSTALLED_APPS` فعال شد.
- `/sitemap.xml` اضافه شد.
- `/robots.txt` اضافه شد.
- مدل `Salon` فیلدهای SEO گرفت: `slug`, `seo_title`, `seo_description`, `canonical_url`, `allow_indexing`, `og_image`.
- مدل‌های `Services` و `GroupServices` فیلدهای SEO و slug گرفتند.
- مسیر جدید سالن: `/salons/<salon_slug>/`.
- مسیر قدیمی سالن: `/detail_salon/<id>/` به مسیر جدید redirect می‌شود.
- مسیر جدید پروفایل آرایشگر داخل سالن: `/salons/<salon_slug>/stylists/<stylist_id>/`.
- مسیر جدید دسته خدمات: `/services/category/<slug>/`.
- مسیر جدید جزئیات خدمت: `/services/<slug>/`.
- صفحه سالن schema از نوع `BeautySalon` و breadcrumb schema گرفت.
- صفحه خدمت schema از نوع `Service` و breadcrumb schema گرفت.
- صفحه مقاله FAQ schema گرفت.
- تناقض `allow_indexing=False` در ArticleDetailView اصلاح شد: مقاله منتشرشده ولی noindex قابل مشاهده می‌ماند و فقط meta robots می‌گیرد.

## فایل‌های مهم
- `apps/salons/models.py`
- `apps/salons/views.py`
- `apps/salons/urls.py`
- `apps/salons/sitemaps.py`
- `apps/services/models.py`
- `apps/services/views.py`
- `apps/services/urls.py`
- `apps/services/sitemaps.py`
- `apps/main/views.py`
- `apps/main/sitemaps.py`
- `apps/main/seo.py`
- `apps/articles/views.py`
- `loomera/urls.py`
- `templates/pages/detail_salon.html`
- `templates/pages/search.html`
- `templates/pages/salon_stylist_profile.html`
- `templates/services/all_services.html`
- `templates/services/service_detail.html`

## دستورات اجرا
```bash
python manage.py migrate
python manage.py check
```

## QA دستی
1. `/sitemap.xml` باز شود و URLهای سالن، خدمات، دسته خدمات و مقاله‌ها را نشان دهد.
2. `/robots.txt` باز شود و sitemap را نمایش دهد.
3. مسیر قدیمی `/detail_salon/<id>/` باید به `/salons/<slug>/` redirect 301 شود.
4. صفحه سالن باید بدون تغییر ظاهری باز شود و canonical/schema داشته باشد.
5. صفحه جستجو باید noindex باشد.
6. صفحه مقاله noindex اگر `allow_indexing=False` باشد باید باز شود اما robots noindex داشته باشد.
7. مسیر `/services/<slug>/` و `/services/category/<slug>/` باز شود.

## نکته‌های بعدی
- صفحات landing شهر/محله/خدمت می‌تواند در مرحله‌های بعدی روی همین پایه ساخته شود.
- Redirect manager و SEO dashboard در ادمین می‌تواند بعداً اضافه شود.
