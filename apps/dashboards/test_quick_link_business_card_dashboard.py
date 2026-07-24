from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

from django.contrib.auth import get_user_model
from django.test import (
    Client,
    RequestFactory,
    TestCase,
    override_settings,
)
from django.urls import reverse
from PIL import Image

from apps.accounts.models import SalonManager, Stylist
from apps.orders.models import BookingQuickLink
from apps.orders.quick_link_print_templates import (
    _business_card_salon_data,
    generate_booking_quick_link_business_card_side,
    generate_booking_quick_link_business_card_zip,
)
from apps.salons.models import (
    Salon,
    SalonMembership,
    SalonMembershipStatus,
)


User = get_user_model()


@override_settings(
    ALLOWED_HOSTS=["testserver", "loomera.test"]
)
class BusinessCardDashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager_user = User.objects.create_user(
            mobile_number="09123338001",
            password="test-pass-123",
            name="مدیر",
            family="کارت ویزیت",
        )
        cls.manager_user.is_active = True
        cls.manager_user.save(update_fields=["is_active"])

        cls.manager = SalonManager.objects.create(
            user=cls.manager_user,
            is_active=True,
        )
        cls.salon = Salon.objects.create(
            salon_name="سالن کارت ویزیت",
            salon_manager=cls.manager,
            is_active=True,
            canonical_url="https://karino.example/",
            insta_link="https://instagram.com/karino.beauty/",
            phone_number="02112345678",
            address="تهران، خیابان نمونه، پلاک ۱۲",
        )

        cls.stylist_user = User.objects.create_user(
            mobile_number="09123338003",
            password="test-pass-123",
            name="متخصص",
            family="کارت ویزیت",
        )
        cls.stylist_user.is_active = True
        cls.stylist_user.save(update_fields=["is_active"])
        cls.stylist = Stylist.objects.create(
            user=cls.stylist_user,
            expert="مو",
            is_active=True,
        )
        cls.salon.stylists.add(cls.stylist)
        SalonMembership.objects.create(
            salon=cls.salon,
            stylist=cls.stylist,
            status=SalonMembershipStatus.ACTIVE,
        )

        cls.manager_link = BookingQuickLink.objects.create(
            creator=cls.manager_user,
            salon=cls.salon,
            title="کارت ویزیت مدیر",
            mode=BookingQuickLink.Mode.SALON,
            placement=BookingQuickLink.Placement.DIRECT,
            payload={
                "mode": "salon",
                "salon_id": cls.salon.pk,
                "service_ids": [],
                "stylist_user_id": None,
            },
            is_permanent=True,
        )
        cls.stylist_link = BookingQuickLink.objects.create(
            creator=cls.stylist_user,
            salon=cls.salon,
            stylist=cls.stylist,
            title="کارت ویزیت متخصص",
            mode=BookingQuickLink.Mode.STYLIST,
            placement=BookingQuickLink.Placement.DIRECT,
            payload={
                "mode": "stylist",
                "salon_id": cls.salon.pk,
                "service_ids": [],
                "stylist_user_id": cls.stylist.pk,
            },
            is_permanent=True,
        )

    def request(self):
        return RequestFactory().get(
            "/",
            HTTP_HOST="loomera.test",
        )

    def stylist_client(self):
        client = Client()
        client.force_login(self.stylist_user)
        session = client.session
        session["active_stylist_salon_id"] = str(self.salon.pk)
        session.save()
        return client

    def test_real_salon_fields_are_used(self):
        data = _business_card_salon_data(
            request=self.request(),
            salon=self.salon,
        )
        self.assertEqual(data["salon_name"], "سالن کارت ویزیت")
        self.assertEqual(data["website"], "karino.example")
        self.assertEqual(data["instagram"], "@karino.beauty")
        self.assertEqual(data["phone"], "02112345678")
        self.assertIn("خیابان نمونه", data["address"])

    def test_front_back_and_zip_are_valid(self):
        for side in ("front", "back"):
            generated = generate_booking_quick_link_business_card_side(
                request=self.request(),
                quick_link=self.manager_link,
                side=side,
                preview=False,
            )
            self.assertEqual((generated.width, generated.height), (1075, 575))
            self.assertEqual(generated.dpi, 300)
            with Image.open(BytesIO(generated.content)) as image:
                self.assertEqual(image.size, (1075, 575))

        bundle = generate_booking_quick_link_business_card_zip(
            request=self.request(),
            quick_link=self.manager_link,
        )
        with ZipFile(BytesIO(bundle.content)) as archive:
            names = archive.namelist()
            self.assertEqual(len(names), 2)
            self.assertTrue(any("front" in name for name in names))
            self.assertTrue(any("back" in name for name in names))

    def test_manager_gallery_and_endpoints(self):
        client = Client()
        client.force_login(self.manager_user)

        gallery = client.get(
            reverse(
                "dashboards:quick_link_print_templates",
                kwargs={"link_id": self.manager_link.pk},
            )
        )
        self.assertEqual(gallery.status_code, 200)
        self.assertContains(gallery, "روی کارت")
        self.assertContains(gallery, "پشت کارت")
        self.assertContains(gallery, "دانلود ZIP دو رو")

        back = client.get(
            reverse(
                "dashboards:quick_link_business_card_back_preview",
                kwargs={"link_id": self.manager_link.pk},
            )
        )
        bundle = client.get(
            reverse(
                "dashboards:quick_link_business_card_zip",
                kwargs={"link_id": self.manager_link.pk},
            )
        )
        self.assertEqual(back.status_code, 200)
        self.assertEqual(back["Content-Type"], "image/png")
        self.assertEqual(bundle.status_code, 200)
        self.assertEqual(bundle["Content-Type"], "application/zip")

    def test_stylist_only_accesses_own_card(self):
        client = self.stylist_client()
        allowed = client.get(
            reverse(
                "dashboards:stylist_quick_link_business_card_back_preview",
                kwargs={"link_id": self.stylist_link.pk},
            )
        )
        forbidden = client.get(
            reverse(
                "dashboards:stylist_quick_link_business_card_back_preview",
                kwargs={"link_id": self.manager_link.pk},
            )
        )
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(forbidden.status_code, 404)

    def test_blank_optional_fields_do_not_crash(self):
        self.salon.canonical_url = ""
        self.salon.insta_link = ""
        self.salon.phone_number = ""
        self.salon.address = ""
        self.salon.save(
            update_fields=[
                "canonical_url",
                "insta_link",
                "phone_number",
                "address",
            ]
        )
        generated = generate_booking_quick_link_business_card_side(
            request=self.request(),
            quick_link=self.manager_link,
            side="back",
            preview=False,
        )
        self.assertTrue(generated.content)
