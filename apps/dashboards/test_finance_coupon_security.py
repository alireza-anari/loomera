from __future__ import annotations

from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import CustomUser, SalonManager
from apps.discounts.models import Coupon
from apps.salons.models import Salon


class FinanceCouponSecurityTests(TestCase):
    def _user(self, *, mobile, name="مدیر", family="تست"):
        return CustomUser.objects.create(
            mobile_number=mobile,
            name=name,
            family=family,
            is_active=True,
        )

    def _manager(self, *, mobile):
        user = self._user(mobile=mobile)
        return SalonManager.objects.create(user=user, is_active=True)

    def _salon(self, *, mobile="09128000001", name="سالن تست"):
        return Salon.objects.create(
            salon_name=name,
            salon_manager=self._manager(mobile=mobile),
            is_active=True,
            address="تهران",
        )

    def _coupon(self, *, salon, code="TEST20", is_active=True):
        now = timezone.now()
        return Coupon.objects.create(
            salon=salon,
            coupon_code=code,
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=10),
            discount=20,
            discount_value=20,
            is_active=is_active,
        )

    def _valid_coupon_payload(self, *, code="NEW20"):
        today = timezone.localdate()
        return {
            "coupon_code": code,
            "discount": "20",
            "max_discount_amount": "100000",
            "start_date": "1405/01/01",
            "end_date": "1405/01/10",
            "is_active": "on",
            "description": "تست",
        }

    @override_settings(FINANCE_COUPON_POST_MAX_BYTES=20)
    def test_create_coupon_rejects_large_payload(self):
        salon = self._salon(mobile="09128000101")
        self.client.force_login(salon.salon_manager.user)

        response = self.client.post(
            reverse("dashboards:finance_coupons"),
            data={
                **self._valid_coupon_payload(),
                "description": "الف" * 100,
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Coupon.objects.count(), 0)

    @override_settings(FINANCE_COUPON_CODE_MAX_CHARS=8)
    def test_create_coupon_rejects_long_code(self):
        salon = self._salon(mobile="09128000102")
        self.client.force_login(salon.salon_manager.user)

        response = self.client.post(
            reverse("dashboards:finance_coupons"),
            data=self._valid_coupon_payload(code="LONG-CODE-123"),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Coupon.objects.count(), 0)

    def test_toggle_foreign_coupon_returns_404(self):
        own_salon = self._salon(mobile="09128000103", name="سالن خودی")
        foreign_salon = self._salon(mobile="09128000104", name="سالن دیگر")
        foreign_coupon = self._coupon(salon=foreign_salon)

        self.client.force_login(own_salon.salon_manager.user)

        response = self.client.post(
            reverse(
                "dashboards:finance_coupon_toggle",
                kwargs={"coupon_id": foreign_coupon.pk},
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_toggle_own_coupon_changes_status(self):
        salon = self._salon(mobile="09128000105")
        coupon = self._coupon(salon=salon, is_active=True)

        self.client.force_login(salon.salon_manager.user)

        response = self.client.post(
            reverse(
                "dashboards:finance_coupon_toggle",
                kwargs={"coupon_id": coupon.pk},
            )
        )

        self.assertEqual(response.status_code, 302)

        coupon.refresh_from_db()
        self.assertFalse(coupon.is_active)

    def test_delete_foreign_coupon_returns_404(self):
        own_salon = self._salon(mobile="09128000106", name="سالن خودی")
        foreign_salon = self._salon(mobile="09128000107", name="سالن دیگر")
        foreign_coupon = self._coupon(salon=foreign_salon)

        self.client.force_login(own_salon.salon_manager.user)

        response = self.client.post(
            reverse(
                "dashboards:finance_coupon_delete",
                kwargs={"coupon_id": foreign_coupon.pk},
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_invalid_edit_query_redirects_safely(self):
        salon = self._salon(mobile="09128000108")
        self.client.force_login(salon.salon_manager.user)

        response = self.client.get(
            reverse("dashboards:finance_coupons"),
            data={"edit": "abc"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            response["Location"].endswith(reverse("dashboards:finance_coupons"))
        )
