from __future__ import annotations

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.services.models import GroupServices, Services


class PublicServiceApiSecurityTests(TestCase):
    def _group(self, title, *, is_active=True, parent=None):
        return GroupServices.objects.create(
            group_title=title,
            slug=title.replace(" ", "-"),
            group_image="test/service-group.jpg",
            is_active=is_active,
            group_parent=parent,
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

    def test_get_subgroups_requires_get(self):
        parent = self._group("زیبایی")

        response = self.client.post(reverse("services:get_subgroups", args=[parent.pk]))

        self.assertEqual(response.status_code, 405)

    def test_get_subgroups_rejects_inactive_parent(self):
        parent = self._group("گروه غیرفعال", is_active=False)

        response = self.client.get(reverse("services:get_subgroups", args=[parent.pk]))

        self.assertEqual(response.status_code, 404)

    def test_get_subgroups_hides_inactive_children(self):
        parent = self._group("زیبایی")
        active_child = self._group("ناخن", parent=parent, is_active=True)
        inactive_child = self._group("غیرفعال", parent=parent, is_active=False)

        response = self.client.get(reverse("services:get_subgroups", args=[parent.pk]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        returned_ids = {item["id"] for item in payload["subgroups"]}
        self.assertIn(active_child.pk, returned_ids)
        self.assertNotIn(inactive_child.pk, returned_ids)

    def test_service_price_list_rejects_non_catalog_service(self):
        group = self._group("زیبایی")
        service = self._service(
            "خدمت اختصاصی سالن",
            group=group,
            is_active=True,
            is_platform_catalog=False,
        )

        response = self.client.get(
            reverse("services:service_priceList", args=[service.pk])
        )

        self.assertEqual(response.status_code, 404)

    def test_dynamic_content_requires_ajax_header(self):
        group = self._group("زیبایی")
        service = self._service("کوتاهی مو", group=group)

        response = self.client.get(
            reverse("services:service_dynamic_content"),
            data={
                "service_id": str(service.pk),
                "content_type": "info",
            },
        )

        self.assertEqual(response.status_code, 400)

    def test_dynamic_content_rejects_invalid_service_id(self):
        response = self.client.get(
            reverse("services:service_dynamic_content"),
            data={
                "service_id": "abc",
                "content_type": "info",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 400)

    def test_dynamic_content_rejects_invalid_content_type(self):
        group = self._group("زیبایی")
        service = self._service("کوتاهی مو", group=group)

        response = self.client.get(
            reverse("services:service_dynamic_content"),
            data={
                "service_id": str(service.pk),
                "content_type": "<script>",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 400)

    def test_dynamic_content_rejects_non_catalog_service(self):
        group = self._group("زیبایی")
        service = self._service(
            "خدمت اختصاصی",
            group=group,
            is_active=True,
            is_platform_catalog=False,
        )

        response = self.client.get(
            reverse("services:service_dynamic_content"),
            data={
                "service_id": str(service.pk),
                "content_type": "info",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 404)

    @override_settings(SERVICE_SUGGESTIONS_QUERY_MAX_CHARS=10)
    def test_service_suggestions_rejects_too_long_query(self):
        response = self.client.get(
            reverse("services:service_suggestions"),
            data={"q": "الف" * 11},
        )

        self.assertEqual(response.status_code, 400)

    def test_service_suggestions_hides_inactive_and_non_catalog_services(self):
        group = self._group("زیبایی")
        public_service = self._service(
            "پاکسازی پوست",
            group=group,
            is_active=True,
            is_platform_catalog=True,
        )
        inactive_service = self._service(
            "پاکسازی پوست غیرفعال",
            group=group,
            is_active=False,
            is_platform_catalog=True,
        )
        private_service = self._service(
            "پاکسازی پوست اختصاصی",
            group=group,
            is_active=True,
            is_platform_catalog=False,
        )

        response = self.client.get(
            reverse("services:service_suggestions"),
            data={"q": "پاکسازی"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        service_ids = {item["id"] for item in payload["services"]}
        self.assertIn(public_service.pk, service_ids)
        self.assertNotIn(inactive_service.pk, service_ids)
        self.assertNotIn(private_service.pk, service_ids)
