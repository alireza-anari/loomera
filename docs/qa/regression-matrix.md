# Loomera Regression Matrix

این ماتریس نشان می‌دهد تغییر هر بخش، کدام سناریوها را دوباره باید تست کند.

| بخش تغییر | سناریوهای اجباری QA | ریسک اصلی |
|---|---|---|
| Accounts/Auth | ثبت‌نام، OTP، ورود، حذف حساب | قفل شدن ورود کاربران |
| SalonMembership | افزودن آرایشگر، تغییر وضعیت همکاری، context سالن | نشت داده بین سالن‌ها |
| Booking Lifecycle | رزرو، تأیید، حضور، شروع، پایان، no-show | خراب شدن هسته رزرو |
| Finance | snapshot، StaffEarning، Ledger، payout request | اختلاف مالی |
| Stylist Dashboard | نوبت‌های من، درآمد، مرخصی، چندسالن | نمایش داده اشتباه |
| Content | مقاله، استوری، گزارش محتوا، moderation | انتشار محتوای نامناسب |
| Notifications | unread count، delivery، mark as read | اعلان تکراری یا گم‌شده |
| Platform Admin | سالن‌ها، کاربران، مالی، audit | عملیات حساس بدون لاگ |
| Support/Disputes | تیکت، پیام، پیوست، dispute | گم شدن شکایت کاربر |
| Search | فیلتر، sort، نقشه، availability | نمایش وقت یا سالن اشتباه |
| Discounts | eligibility، redemption، snapshot | سوءاستفاده یا محاسبه غلط |
| Analytics | daily metrics، export | گزارش نادرست |
| SEO | sitemap، robots، canonical، redirect | duplicate یا index اشتباه |
| Infrastructure | scheduled tasks، cache، health | خطای production |
