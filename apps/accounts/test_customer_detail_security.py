from __future__ import annotations

from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from tests_stage1_helpers import Stage1DomainFactoryMixin

from apps.salons.models import CustomerNote


def _image_upload(
    *,
    name="note.jpg",
    size=(64, 64),
    image_format="JPEG",
    content_type="image/jpeg",
):
    buffer = BytesIO()
    image = Image.new("RGB", size, color=(240, 240, 240))
    image.save(buffer, format=image_format)
    buffer.seek(0)

    return SimpleUploadedFile(name, buffer.read(), content_type=content_type)


def _animated_gif_upload(*, name="note.gif", content_type="image/gif"):
    buffer = BytesIO()

    frame_one = Image.new("RGB", (32, 32), color=(255, 0, 0))
    frame_two = Image.new("RGB", (32, 32), color=(0, 255, 0))

    frame_one.save(
        buffer,
        format="GIF",
        save_all=True,
        append_images=[frame_two],
        duration=100,
        loop=0,
    )
    buffer.seek(0)

    return SimpleUploadedFile(name, buffer.read(), content_type=content_type)


class CustomerDetailSecurityTests(Stage1DomainFactoryMixin, TestCase):
    def _setup_two_salons(self):
        manager_one = self.make_salon_manager()
        manager_two = self.make_salon_manager()

        salon_one = self.make_salon(manager=manager_one)
        salon_two = self.make_salon(manager=manager_two)

        return manager_one, salon_one, manager_two, salon_two

    def test_customer_detail_requires_login(self):
        manager, salon, _other_manager, _other_salon = self._setup_two_salons()
        customer = self.make_customer(added_by_salon=salon)

        response = self.client.get(
            reverse("accounts:detail_customer", args=[customer.pk])
        )

        self.assertEqual(response.status_code, 302)

    def test_customer_detail_rejects_foreign_salon_customer(self):
        manager_one, _salon_one, _manager_two, salon_two = self._setup_two_salons()
        foreign_customer = self.make_customer(added_by_salon=salon_two)

        self.client.force_login(manager_one.user)
        response = self.client.get(
            reverse("accounts:detail_customer", args=[foreign_customer.pk])
        )

        self.assertEqual(response.status_code, 404)

    def test_customer_detail_allows_own_added_customer(self):
        manager_one, salon_one, _manager_two, _salon_two = self._setup_two_salons()
        customer = self.make_customer(added_by_salon=salon_one)

        self.client.force_login(manager_one.user)
        response = self.client.get(
            reverse("accounts:detail_customer", args=[customer.pk])
        )

        self.assertEqual(response.status_code, 200)

    def test_customer_detail_order_details_are_scoped_to_current_salon(self):
        manager_one, salon_one, manager_two, salon_two = self._setup_two_salons()
        customer = self.make_customer()

        stylist_one = self.make_stylist()
        stylist_two = self.make_stylist()
        service_one = self.make_service()
        service_two = self.make_service()

        self.connect_service(salon=salon_one, stylist=stylist_one, service=service_one)
        self.connect_service(salon=salon_two, stylist=stylist_two, service=service_two)

        order_one = self.make_order(customer=customer, salon=salon_one)
        order_two = self.make_order(customer=customer, salon=salon_two)

        today = timezone.localdate()
        self.make_order_detail(
            order=order_one,
            service=service_one,
            stylist=stylist_one,
            salon=salon_one,
            date_value=today,
            start=timezone.datetime.strptime("10:00", "%H:%M").time(),
            end=timezone.datetime.strptime("10:30", "%H:%M").time(),
            price=120000,
        )
        self.make_order_detail(
            order=order_two,
            service=service_two,
            stylist=stylist_two,
            salon=salon_two,
            date_value=today,
            start=timezone.datetime.strptime("12:00", "%H:%M").time(),
            end=timezone.datetime.strptime("12:30", "%H:%M").time(),
            price=990000,
        )

        self.client.force_login(manager_one.user)
        response = self.client.get(
            reverse("accounts:detail_customer", args=[customer.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["order_details"]), 1)
        self.assertEqual(response.context["order_details"][0].salon_id, salon_one.id)
        self.assertEqual(response.context["total_sales"], 120000)

    def test_customer_note_rejects_foreign_customer(self):
        manager_one, _salon_one, _manager_two, salon_two = self._setup_two_salons()
        foreign_customer = self.make_customer(added_by_salon=salon_two)

        self.client.force_login(manager_one.user)
        response = self.client.post(
            reverse("accounts:detail_customer", args=[foreign_customer.pk]),
            data={"note": "یادداشت غیرمجاز"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(CustomerNote.objects.count(), 0)

    def test_customer_note_accepts_valid_jpeg(self):
        manager_one, salon_one, _manager_two, _salon_two = self._setup_two_salons()
        customer = self.make_customer(added_by_salon=salon_one)

        self.client.force_login(manager_one.user)
        response = self.client.post(
            reverse("accounts:detail_customer", args=[customer.pk]),
            data={
                "note": "یادداشت تست",
                "note_image": _image_upload(
                    name="note.jpg",
                    image_format="JPEG",
                    content_type="image/jpeg",
                ),
            },
        )

        self.assertEqual(response.status_code, 302)
        note = CustomerNote.objects.get()
        self.assertEqual(note.salon_id, salon_one.id)
        self.assertEqual(note.customer_id, customer.pk)
        self.assertTrue(note.note_image)

    def test_customer_note_rejects_gif_with_jpg_filename(self):
        manager_one, salon_one, _manager_two, _salon_two = self._setup_two_salons()
        customer = self.make_customer(added_by_salon=salon_one)

        self.client.force_login(manager_one.user)
        response = self.client.post(
            reverse("accounts:detail_customer", args=[customer.pk]),
            data={
                "note": "یادداشت تست",
                "note_image": _animated_gif_upload(
                    name="note.jpg",
                    content_type="image/jpeg",
                ),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(CustomerNote.objects.count(), 0)

    @override_settings(CUSTOMER_NOTE_TEXT_MAX_CHARS=10)
    def test_customer_note_rejects_too_long_text(self):
        manager_one, salon_one, _manager_two, _salon_two = self._setup_two_salons()
        customer = self.make_customer(added_by_salon=salon_one)

        self.client.force_login(manager_one.user)
        response = self.client.post(
            reverse("accounts:detail_customer", args=[customer.pk]),
            data={"note": "این متن خیلی طولانی است"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(CustomerNote.objects.count(), 0)

    def test_delete_customer_note_is_scoped_to_customer_and_salon(self):
        manager_one, salon_one, _manager_two, _salon_two = self._setup_two_salons()
        customer_one = self.make_customer(added_by_salon=salon_one)
        customer_two = self.make_customer(added_by_salon=salon_one)

        note = CustomerNote.objects.create(
            salon=salon_one,
            customer=customer_one,
            note="یادداشت تست",
            created_by=manager_one.user,
        )

        self.client.force_login(manager_one.user)
        response = self.client.post(
            reverse(
                "accounts:delete_customer_note",
                args=[customer_two.pk, note.pk],
            )
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(CustomerNote.objects.filter(pk=note.pk).exists())
