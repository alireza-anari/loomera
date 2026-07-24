from __future__ import annotations

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import CustomUser, SalonManager, Stylist
from apps.salons.models import Salon
from apps.services.models import GroupServices, Services


class PublicSuggestionsSecurityTests(TestCase):
    def _group(self, title, *, is_active=True):
        return GroupServices.objects.create(
            group_title=title,
            slug=title.replace(" ", "-"),
            group_image="test/group.jpg",
            is_active=is_active,
        )

    def _service(
        self,
        name,
        *,
        group=None,
        is_active=True,
        is_platform_catalog=True,
    ):
        service = Services.objects.create(
            service_name=name,
            slug=name.replace(" ", "-"),
            is_active=is_active,
            is_platform_catalog=is_platform_catalog,
            duration_minutes=30,
            base_price=100000,
        )
        if group is not None:
            service.service_group.add(group)
        return service

    def _user(self, *, mobile, name, family="تست"):
        return CustomUser.objects.create(
            mobile_number=mobile,
            name=name,
            family=family,
            is_active=True,
        )

    def _manager(self, *, mobile="09120000001"):
        user = self._user(mobile=mobile, name="مدیر", family="سالن")
        return SalonManager.objects.create(user=user, is_active=True)

    def _salon(self, *, name="سالن تست", is_active=True, mobile="09120000002"):
        manager = self._manager(mobile=mobile)
        return Salon.objects.create(
            salon_name=name,
            salon_manager=manager,
            is_active=is_active,
            address="تهران",
        )

    def _stylist(
        self,
        *,
        mobile,
        name,
        expert="رنگ مو",
        is_active=True,
        public_visibility=Stylist.PublicVisibility.PUBLIC,
    ):
        user = self._user(mobile=mobile, name=name, family="متخصص")
        return Stylist.objects.create(
            user=user,
            is_active=is_active,
            expert=expert,
            public_visibility=public_visibility,
        )

    def test_search_suggestions_requires_get(self):
        response = self.client.post(reverse("search:search_suggestions"))

        self.assertEqual(response.status_code, 405)

    @override_settings(SEARCH_SUGGESTIONS_QUERY_MAX_CHARS=10)
    def test_search_suggestions_rejects_too_long_query(self):
        response = self.client.get(
            reverse("search:search_suggestions"),
            data={"q": "الف" * 11},
        )

        self.assertEqual(response.status_code, 400)

    def test_search_suggestions_hides_non_catalog_services(self):
        group = self._group("زیبایی")
        public_service = self._service(
            "پاکسازی پوست",
            group=group,
            is_active=True,
            is_platform_catalog=True,
        )
        private_service = self._service(
            "پاکسازی پوست اختصاصی",
            group=group,
            is_active=True,
            is_platform_catalog=False,
        )

        response = self.client.get(
            reverse("search:search_suggestions"),
            data={"q": "پاکسازی"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        service_ids = {item["id"] for item in payload["services"]}
        self.assertIn(public_service.pk, service_ids)
        self.assertNotIn(private_service.pk, service_ids)

    def test_search_suggestions_hides_services_with_inactive_group(self):
        inactive_group = self._group("گروه غیرفعال", is_active=False)
        service = self._service(
            "اصلاح تخصصی",
            group=inactive_group,
            is_active=True,
            is_platform_catalog=True,
        )

        response = self.client.get(
            reverse("search:search_suggestions"),
            data={"q": "اصلاح"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        service_ids = {item["id"] for item in payload["services"]}
        self.assertNotIn(service.pk, service_ids)

    def test_search_suggestions_hides_hidden_or_salon_only_stylists(self):
        active_salon = self._salon(name="سالن فعال", is_active=True)

        public_stylist = self._stylist(
            mobile="09120000101",
            name="سارا",
            expert="رنگ خاص تست",
            public_visibility=Stylist.PublicVisibility.PUBLIC,
        )
        hidden_stylist = self._stylist(
            mobile="09120000102",
            name="سارا",
            expert="رنگ خاص تست",
            public_visibility=Stylist.PublicVisibility.HIDDEN,
        )
        salon_only_stylist = self._stylist(
            mobile="09120000103",
            name="سارا",
            expert="رنگ خاص تست",
            public_visibility=Stylist.PublicVisibility.SALON_ONLY,
        )

        active_salon.stylists.add(public_stylist, hidden_stylist, salon_only_stylist)

        response = self.client.get(
            reverse("search:search_suggestions"),
            data={"q": "رنگ خاص تست"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        stylist_ids = {item["id"] for item in payload["stylists"]}
        self.assertIn(public_stylist.pk, stylist_ids)
        self.assertNotIn(hidden_stylist.pk, stylist_ids)
        self.assertNotIn(salon_only_stylist.pk, stylist_ids)

    def test_search_suggestions_hides_public_stylist_without_active_salon(self):
        inactive_salon = self._salon(
            name="سالن غیرفعال",
            is_active=False,
            mobile="09120000009",
        )
        stylist = self._stylist(
            mobile="09120000104",
            name="مهسا",
            expert="براشینگ ویژه",
            public_visibility=Stylist.PublicVisibility.PUBLIC,
        )
        inactive_salon.stylists.add(stylist)

        response = self.client.get(
            reverse("search:search_suggestions"),
            data={"q": "براشینگ ویژه"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        stylist_ids = {item["id"] for item in payload["stylists"]}
        self.assertNotIn(stylist.pk, stylist_ids)

    def test_location_suggestions_requires_get(self):
        response = self.client.post(reverse("search:location_suggestions"))

        self.assertEqual(response.status_code, 405)

    @override_settings(LOCATION_SUGGESTIONS_QUERY_MAX_CHARS=10)
    def test_location_suggestions_rejects_too_long_query(self):
        response = self.client.get(
            reverse("search:location_suggestions"),
            data={"q": "الف" * 11},
        )

        self.assertEqual(response.status_code, 400)

    @override_settings(SALON_SEARCH_QUERY_MAX_CHARS=10)
    def test_salon_search_rejects_too_long_query(self):
        response = self.client.get(
            reverse("search:salon_search"),
            data={"q": "الف" * 11},
        )

        self.assertEqual(response.status_code, 400)

    def test_salon_search_does_not_match_private_service_name(self):
        salon = self._salon(name="سالن عمومی", is_active=True)
        private_service = self._service(
            "خدمت محرمانه تست",
            is_active=True,
            is_platform_catalog=False,
        )
        salon.services.add(private_service)

        response = self.client.get(
            reverse("search:salon_search"),
            data={"q": "خدمت محرمانه تست"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        salon_ids = {item["id"] for item in payload["salons"]}
        self.assertNotIn(salon.pk, salon_ids)
