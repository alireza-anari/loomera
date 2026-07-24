# Stage 2 Manual Test Checklist — Provider Setup Readiness

این چک‌لیست برای **هر کدام از providerهای demo/beta** باید اجرا شود.

> Terminology note: برای برندسازی Loomera، این فایل از provider/center/specialist استفاده می‌کند. در implementation فعلی ممکن است این مفهوم با `salon` و `stylist` مدل شده باشد.

## A) پروفایل پایه‌ی provider
- [ ] نام provider ثبت شده است
- [ ] شماره‌ی تماس provider ثبت شده است
- [ ] توضیح provider ثبت شده و متن بی‌کیفیت/خیلی کوتاه نیست
- [ ] تصویر banner یا cover نمایش داده می‌شود
- [ ] در صفحه‌ی عمومی provider، نام/بنر/توضیح بدون شکست UI دیده می‌شود

## B) آدرس و موقعیت
- [ ] zone ثبت شده است
- [ ] neighborhood درست انتخاب شده است
- [ ] آدرس دقیق ذخیره می‌شود
- [ ] پین روی نقشه انتخاب شده و بعد از refresh باقی می‌ماند
- [ ] صفحه‌ی عمومی provider موقعیت را درست نشان می‌دهد

## C) ساعات کاری
- [ ] هر ۷ روز هفته مقدار دارند
- [ ] روزهای تعطیل درست مشخص شده‌اند
- [ ] ساعت شروع/پایان نامعتبر ذخیره نمی‌شود
- [ ] بعد از refresh ساعت‌ها از بین نمی‌روند

## D) خدمات و قیمت‌ها
- [ ] حداقل ۳ خدمت واقعی برای هر provider ثبت شده است
- [ ] ترکیب خدمات فقط salon-first نیست و حداقل یکی از treatment / massage / wellness را هم پوشش می‌دهد
- [ ] هر خدمت duration واقعی دارد
- [ ] هر خدمت حداقل برای یک متخصص price دارد
- [ ] دسته‌بندی خدمت درست است
- [ ] خدمت غیرفعال در صفحه‌ی عمومی/رزرو به‌اشتباه دیده نمی‌شود

## E) تیم و پوشش خدمات
- [ ] حداقل ۱ مدیر provider و ۱ متخصص فعال وجود دارد
- [ ] اطلاعات متخصص کامل است
- [ ] هر متخصص فقط خدمات خودش را می‌بیند
- [ ] سرویس بدون متخصصِ پوشش‌دهنده وارد flow رزرو نمی‌شود

## F) برنامه‌ی کاری و Time Off
- [ ] برای هر متخصص regular shifts ثبت شده است
- [ ] time off ثبت می‌شود
- [ ] time off واقعاً availability را می‌بندد
- [ ] schedule متخصص بعد از refresh درست باقی می‌ماند

## G) تنظیمات مالی و لغو
- [ ] شبا ثبت شده است
- [ ] نام صاحب حساب ثبت شده است
- [ ] موبایل مسئول مالی ثبت شده است
- [ ] پنجره‌ی لغو آنلاین ثبت شده است
- [ ] درصد بازگشت وجه ثبت شده است
- [ ] توضیح سیاست لغو ثبت شده است

## H) سه نمای اصلی
- [ ] صفحه‌ی عمومی provider از دید مشتری بررسی شد
- [ ] dashboard مدیر provider بررسی شد
- [ ] workflow متخصص از دید خودش بررسی شد

## ابزار تست
- مرورگر دسکتاپ + موبایل
- Django admin
- صفحه‌ی dashboard manager
- صفحه‌ی dashboard specialist/stylist
- صفحه‌ی public provider
- لاگ ترمینال runserver

## خروجی ثبت تست برای هر provider
```text
provider_name:
provider_type:
manager_user:
specialist_count:
service_count:
beauty_services:
treatment_services:
massage_or_wellness_services:
step1:
step2:
step3:
description:
services:
pricing:
team:
schedules:
time_off:
finance:
public_page:
manager_dashboard:
specialist_workflow:
pass/fail:
notes:
```
