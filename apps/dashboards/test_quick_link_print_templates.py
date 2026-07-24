from __future__ import annotations

from io import BytesIO

from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from PIL import Image

from apps.accounts.models import (
    SalonManager,
    Stylist,
)
from apps.orders.models import BookingQuickLink
from apps.orders.quick_link_print_templates import (
    generate_booking_quick_link_print_template,
    list_booking_quick_link_print_templates,
)
from apps.salons.models import (
    Salon,
    SalonMembership,
    SalonMembershipStatus,
)
from apps.services.models import Services


User = get_user_model()


class QuickLinkPrintTemplateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager_user = User.objects.create_user(
            mobile_number="09124443001",
            password="test-pass-123",
            name="مدیر",
            family="قالب چاپ",
        )
        cls.manager_user.is_active = True
        cls.manager_user.save(
            update_fields=["is_active"]
        )

        cls.other_manager_user = User.objects.create_user(
            mobile_number="09124443002",
            password="test-pass-123",
            name="مدیر",
            family="سالن دیگر",
        )
        cls.other_manager_user.is_active = True
        cls.other_manager_user.save(
            update_fields=["is_active"]
        )

        cls.manager = SalonManager.objects.create(
            user=cls.manager_user,
            is_active=True,
        )
        cls.other_manager = SalonManager.objects.create(
            user=cls.other_manager_user,
            is_active=True,
        )

        cls.salon = Salon.objects.create(
            salon_name="سالن قالب چاپ",
            salon_manager=cls.manager,
            is_active=True,
        )
        cls.other_salon = Salon.objects.create(
            salon_name="سالن خارج از Scope",
            salon_manager=cls.other_manager,
            is_active=True,
        )

        cls.stylist_user = User.objects.create_user(
            mobile_number="09124443003",
            password="test-pass-123",
            name="متخصص",
            family="قالب چاپ",
        )
        cls.stylist_user.is_active = True
        cls.stylist_user.save(
            update_fields=["is_active"]
        )

        cls.other_stylist_user = User.objects.create_user(
            mobile_number="09124443004",
            password="test-pass-123",
            name="متخصص",
            family="دیگر",
        )
        cls.other_stylist_user.is_active = True
        cls.other_stylist_user.save(
            update_fields=["is_active"]
        )

        cls.stylist = Stylist.objects.create(
            user=cls.stylist_user,
            expert="مو",
            is_active=True,
        )
        cls.other_stylist = Stylist.objects.create(
            user=cls.other_stylist_user,
            expert="پوست",
            is_active=True,
        )
        cls.salon.stylists.add(
            cls.stylist,
            cls.other_stylist,
        )

        cls.service = Services.objects.create(
            service_name="خدمت قالب چاپ",
            is_active=True,
            duration_minutes=30,
            base_price=100000,
        )
        cls.salon.services.add(cls.service)
        cls.service.stylists.add(
            cls.stylist,
            cls.other_stylist,
        )

        SalonMembership.objects.create(
            salon=cls.salon,
            stylist=cls.stylist,
            status=SalonMembershipStatus.ACTIVE,
        )

    def create_link(
        self,
        *,
        creator=None,
        salon=None,
        stylist=None,
        title="لینک قالب چاپ",
    ):
        creator = creator or self.manager_user
        salon = salon or self.salon
        service = self.service if salon == self.salon else None
        mode = (
            BookingQuickLink.Mode.SERVICE_STYLIST
            if stylist
            else BookingQuickLink.Mode.SERVICE
        )

        return BookingQuickLink.objects.create(
            creator=creator,
            salon=salon,
            service=service,
            stylist=stylist,
            title=title,
            mode=mode,
            placement=(
                BookingQuickLink.Placement.MIRROR_LABEL
            ),
            campaign_name="کمپین قالب چاپ",
            payload={
                "mode": mode,
                "salon_id": salon.pk,
                "service_ids": (
                    [service.pk] if service else []
                ),
                "stylist_user_id": (
                    stylist.pk if stylist else None
                ),
                "date": "",
                "time": "",
                "summary": {
                    "service": (
                        service.service_name
                        if service
                        else "—"
                    ),
                    "stylist": (
                        stylist.get_fullName()
                        if stylist
                        else "—"
                    ),
                },
            },
            is_permanent=True,
        )

    def stylist_client(self):
        client = Client()
        client.force_login(self.stylist_user)
        session = client.session
        session["active_stylist_salon_id"] = str(
            self.salon.pk
        )
        session.save()
        return client

    def test_registry_contains_four_print_templates(self):
        specs = list(
            list_booking_quick_link_print_templates()
        )

        self.assertEqual(
            [spec.key for spec in specs],
            [
                "mirror_label",
                "business_card",
                "table_stand",
                "counter_card",
            ],
        )
        self.assertEqual(len(specs), 4)

    def test_service_generates_valid_previews(self):
        quick_link = self.create_link()
        request = RequestFactory().get("/")

        for spec in list_booking_quick_link_print_templates():
            generated = (
                generate_booking_quick_link_print_template(
                    request=request,
                    quick_link=quick_link,
                    template_key=spec.key,
                    preview=True,
                )
            )

            self.assertTrue(
                generated.content.startswith(
                    b"\x89PNG\r\n\x1a\n"
                )
            )

            with Image.open(
                BytesIO(generated.content)
            ) as image:
                self.assertLessEqual(
                    max(image.size),
                    900,
                )

    def test_mirror_download_is_transparent_and_print_size(self):
        quick_link = self.create_link()
        request = RequestFactory().get("/")
        generated = generate_booking_quick_link_print_template(
            request=request,
            quick_link=quick_link,
            template_key="mirror_label",
            preview=False,
        )

        self.assertEqual(
            (generated.width, generated.height),
            (945, 945),
        )
        self.assertEqual(generated.dpi, 300)

        with Image.open(
            BytesIO(generated.content)
        ) as image:
            self.assertEqual(image.mode, "RGBA")
            self.assertEqual(
                image.getpixel((0, 0))[3],
                0,
            )

    def test_manager_gallery_and_png_endpoints(self):
        quick_link = self.create_link()
        client = Client()
        client.force_login(self.manager_user)

        gallery_url = reverse(
            "dashboards:quick_link_print_templates",
            kwargs={"link_id": quick_link.pk},
        )
        response = client.get(gallery_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "لیبل کنار آینه")
        self.assertContains(response, "کارت ویزیت")
        self.assertContains(response, "استند رومیزی")
        self.assertContains(response, "کارت روی میز")

        preview = client.get(
            reverse(
                "dashboards:quick_link_print_template_preview",
                kwargs={
                    "link_id": quick_link.pk,
                    "template_key": "business_card",
                },
            )
        )
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(
            preview["Content-Type"],
            "image/png",
        )
        self.assertIn(
            "inline",
            preview["Content-Disposition"],
        )

        download = client.get(
            reverse(
                "dashboards:quick_link_print_template_download",
                kwargs={
                    "link_id": quick_link.pk,
                    "template_key": "business_card",
                },
            )
        )
        self.assertEqual(download.status_code, 200)
        self.assertIn(
            "attachment",
            download["Content-Disposition"],
        )

    def test_warning_requires_explicit_download_confirmation(self):
        quick_link = self.create_link()
        quick_link.is_active = False
        quick_link.save(update_fields=["is_active"])

        client = Client()
        client.force_login(self.manager_user)
        url = reverse(
            "dashboards:quick_link_print_template_download",
            kwargs={
                "link_id": quick_link.pk,
                "template_key": "mirror_label",
            },
        )

        blocked = client.get(url)
        confirmed = client.get(
            url,
            {"confirm": "1"},
        )

        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(confirmed.status_code, 200)

    def test_manager_scope_blocks_other_salon(self):
        quick_link = self.create_link(
            creator=self.other_manager_user,
            salon=self.other_salon,
        )
        client = Client()
        client.force_login(self.manager_user)

        response = client.get(
            reverse(
                "dashboards:quick_link_print_templates",
                kwargs={"link_id": quick_link.pk},
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_stylist_scope_only_allows_own_link(self):
        own_link = self.create_link(
            creator=self.stylist_user,
            stylist=self.stylist,
        )
        manager_link = self.create_link(
            creator=self.manager_user,
            stylist=self.stylist,
            title="لینک مدیر",
        )
        other_link = self.create_link(
            creator=self.other_stylist_user,
            stylist=self.other_stylist,
            title="لینک متخصص دیگر",
        )
        client = self.stylist_client()

        own_response = client.get(
            reverse(
                "dashboards:stylist_quick_link_print_templates",
                kwargs={"link_id": own_link.pk},
            )
        )
        manager_response = client.get(
            reverse(
                "dashboards:stylist_quick_link_print_templates",
                kwargs={"link_id": manager_link.pk},
            )
        )
        other_response = client.get(
            reverse(
                "dashboards:stylist_quick_link_print_templates",
                kwargs={"link_id": other_link.pk},
            )
        )

        self.assertEqual(own_response.status_code, 200)
        self.assertEqual(manager_response.status_code, 404)
        self.assertEqual(other_response.status_code, 404)

    def test_list_and_detail_pages_link_to_print_gallery(self):
        manager_link = self.create_link()
        stylist_link = self.create_link(
            creator=self.stylist_user,
            stylist=self.stylist,
        )

        manager_client = Client()
        manager_client.force_login(self.manager_user)
        list_response = manager_client.get(
            reverse("dashboards:quick_links")
        )
        detail_response = manager_client.get(
            reverse(
                "dashboards:quick_link_detail",
                kwargs={"link_id": manager_link.pk},
            )
        )

        manager_gallery = reverse(
            "dashboards:quick_link_print_templates",
            kwargs={"link_id": manager_link.pk},
        )
        self.assertContains(list_response, manager_gallery)
        self.assertContains(detail_response, manager_gallery)

        stylist_response = self.stylist_client().get(
            reverse("dashboards:stylist_quick_links")
        )
        stylist_gallery = reverse(
            "dashboards:stylist_quick_link_print_templates",
            kwargs={"link_id": stylist_link.pk},
        )
        self.assertContains(stylist_response, stylist_gallery)
