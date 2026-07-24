from django.test import TestCase
from django.db.models import Avg

# مدل‌هایی که برای تست به آن‌ها نیاز داریم را import می‌کنیم
from .models import CustomUser, Stylist, Customer
from apps.comments_scores_favories.models import Scoring


class StylistModelTest(TestCase):
    """
    این کلاس، تست‌های مربوط به مدل Stylist را در خود جای می‌دهد.
    """

    def setUp(self):
        """
        این متد قبل از اجرای هر تست، یک بار اجرا می‌شود.
        ما در اینجا، داده‌های اولیه‌ای که برای تست‌هایمان نیاز داریم را می‌سازیم.
        """
        # ۱. یک کاربر برای آرایشگر می‌سازیم
        self.user1 = CustomUser.objects.create_user(
            mobile_number="09123456789",
            password="testpassword123",
            name="علی",
            family="رضایی"
        )
        # ۲. پروفایل آرایشگر را برای کاربر بالا می‌سازیم
        self.stylist1 = Stylist.objects.create(
            user=self.user1,
            expert="متخصص رنگ مو"
        )

        # ۳. یک مشتری برای امتیاز دهی می‌سازیم
        self.customer_user = CustomUser.objects.create_user(
            mobile_number="09111111111", password="testpassword"
        )
        self.customer = Customer.objects.create(user=self.customer_user)


    def test_get_full_name(self):
        """
        تست می‌کند که آیا متد get_fullName نام و نام خانوادگی را به درستی برمی‌گرداند یا خیر.
        """
        print("Running test for get_fullName...")
        # انتظار داریم که خروجی متد برابر با "علی رضایی" باشد
        expected_full_name = "علی رضایی"
        # آبجکت آرایشگری که در متد setUp ساختیم را دوباره از دیتابیس می‌خوانیم
        stylist_from_db = Stylist.objects.get(user=self.user1)
        
        # با استفاده از assertEqual بررسی می‌کنیم که آیا خروجی واقعی با خروجی مورد انتظار ما برابر است یا نه
        self.assertEqual(stylist_from_db.get_fullName(), expected_full_name)
        print("Test for get_fullName PASSED.")


    def test_get_average_score_with_scores(self):
        """
        تست می‌کند که آیا متد get_average_score میانگین امتیازات را به درستی محاسبه می‌کند یا خیر.
        """
        print("Running test for get_average_score with scores...")
        # برای آرایشگر خود چند امتیاز ثبت می‌کنیم (امتیازات ۳ و ۵)
        Scoring.objects.create(stylist=self.stylist1, scoring_user=self.customer, score=3)
        Scoring.objects.create(stylist=self.stylist1, scoring_user=self.customer, score=5)
        
        # انتظار داریم که میانگین امتیازات برابر با ۴.۰ باشد
        expected_avg = 4.0
        stylist_from_db = Stylist.objects.get(user=self.user1)
        
        # بررسی می‌کنیم که آیا میانگین محاسبه شده توسط متد ما با مقدار مورد انتظار برابر است
        self.assertEqual(stylist_from_db.get_average_score(), expected_avg)
        print("Test for get_average_score with scores PASSED.")


    def test_get_average_score_without_scores(self):
        """
        تست می‌کند که آیا متد get_average_score در صورت نبود امتیاز، مقدار 0 را برمی‌گرداند.
        """
        print("Running test for get_average_score without scores...")
        # در این تست، هیچ امتیازی برای آرایشگر ثبت نمی‌کنیم
        
        # انتظار داریم که خروجی 0 باشد
        expected_avg = 0
        stylist_from_db = Stylist.objects.get(user=self.user1)
        
        self.assertEqual(stylist_from_db.get_average_score(), expected_avg)
        print("Test for get_average_score without scores PASSED.")