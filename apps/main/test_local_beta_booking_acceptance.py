from __future__ import annotations

import json
from datetime import datetime, timedelta
from io import StringIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Customer, Stylist
from apps.main.management.commands.seed_local_demo_data import (
    MOBILE_PREFIX,
)
from apps.orders.booking_utils import (
    get_available_slots_for_service,
    get_service_buffer_minutes,
)
from apps.orders.forms import AppointmentCheckoutForm
from apps.orders.models import Order, OrderDetail
from apps.payments.models import Payment, WalletTransaction
from apps.salons.models import Salon
from apps.stylists.models import StylistSchedule


@override_settings(
    DEBUG=True,
    PASSWORD_HASHERS=[
        "django.contrib.auth.hashers.MD5PasswordHasher",
    ],
    ONLINE_PAYMENT_ENABLED=False,
    PAYMENT_MODE="mock",
    MESSAGING_OUTBOUND_ENABLED=False,
    EMAIL_BACKEND="django.core.mail.backends.dummy.EmailBackend",
    CACHES={
        "default": {
            "BACKEND": ("django.core.cache.backends.locmem." "LocMemCache"),
            "LOCATION": "local-beta-booking-acceptance",
        }
    },
    STORAGES={
        "default": {
            "BACKEND": ("django.core.files.storage." "FileSystemStorage"),
        },
        "staticfiles": {
            "BACKEND": ("django.contrib.staticfiles.storage." "StaticFilesStorage"),
        },
    },
)
class LocalBetaBookingAcceptanceTests(TestCase):
    seed_slugs = [
        "local-seed-salon-1",
        "local-seed-salon-2",
        "local-seed-salon-3",
        "local-seed-salon-4",
        "local-seed-salon-5",
    ]

    public_stylist_visibilities = (
        Stylist.PublicVisibility.PUBLIC,
        Stylist.PublicVisibility.SALON_ONLY,
    )

    def _find_bookable_candidate(self, salon):
        schedules = (
            StylistSchedule.objects.filter(
                salon=salon,
                date__gte=timezone.localdate(),
                service__isnull=False,
                service__is_active=True,
                stylist__is_active=True,
                stylist__public_visibility__in=(self.public_stylist_visibilities),
            )
            .select_related(
                "service",
                "stylist",
                "stylist__user",
            )
            .order_by(
                "date",
                "start_time",
                "stylist__user_id",
            )
        )

        for schedule in schedules:
            service = schedule.service
            stylist = schedule.stylist

            if service is None:
                continue

            if not (service.is_platform_catalog or service.catalog_source_id):
                continue

            if not salon.services.filter(
                pk=service.pk,
                is_active=True,
            ).exists():
                continue

            if not salon.stylists.filter(
                pk=stylist.pk,
                is_active=True,
            ).exists():
                continue

            if not stylist.services_of_stylist.filter(
                pk=service.pk,
                is_active=True,
            ).exists():
                continue

            slots = get_available_slots_for_service(
                salon=salon,
                stylist=stylist,
                service=service,
                date_value=schedule.date,
            )

            if not slots:
                continue

            start_time, end_time = slots[0]

            return {
                "service": service,
                "stylist": stylist,
                "date": schedule.date,
                "start_time": start_time,
                "end_time": end_time,
            }

        self.fail(f"No usable public booking slot found for " f"{salon.slug}.")

    def _build_selection(self, candidate):
        service = candidate["service"]
        stylist = candidate["stylist"]
        stylist_user_id = str(stylist.user_id)
        stylist_name = stylist.get_fullName()

        return {
            "serviceId": service.pk,
            "serviceName": service.service_name,
            "serviceDuration": int(service.duration_minutes or 0),
            "serviceBuffer": int(service.buffer_minutes or 0),
            "stylistId": stylist_user_id,
            "stylistName": stylist_name,
            "requestedStylistId": stylist_user_id,
            "requestedStylistName": stylist_name,
        }

    def _run_booking_flow(self, *, salon, customer):
        candidate = self._find_bookable_candidate(salon)
        service = candidate["service"]
        stylist = candidate["stylist"]

        selection = self._build_selection(candidate)

        datetime_key = f"{stylist.user_id}_{service.pk}"

        datetime_selections = {
            datetime_key: {
                "date": candidate["date"].isoformat(),
                "time": candidate["start_time"].strftime("%H:%M"),
            }
        }

        public_response = self.client.get(
            reverse(
                "salons:detail_salon_slug",
                kwargs={
                    "salon_slug": salon.slug,
                },
            )
        )

        self.assertEqual(
            public_response.status_code,
            200,
        )
        self.assertContains(
            public_response,
            salon.salon_name,
        )

        stylist_response = self.client.post(
            reverse("orders:select_stylists"),
            data={
                "salon_id": str(salon.pk),
                "stylist_selections": json.dumps(
                    [selection],
                    ensure_ascii=False,
                ),
            },
        )

        self.assertRedirects(
            stylist_response,
            reverse("orders:select_dateTime"),
            fetch_redirect_response=False,
        )

        session = self.client.session
        self.assertEqual(
            session["salon_id"],
            str(salon.pk),
        )
        self.assertEqual(
            session["stylist_selections"][0]["serviceId"],
            service.pk,
        )

        datetime_response = self.client.post(
            reverse("orders:select_dateTime"),
            data={
                "booking_data": json.dumps(
                    {
                        "salon_id": str(salon.pk),
                        "stylist_selections": [selection],
                        "datetime_selections": (datetime_selections),
                    },
                    ensure_ascii=False,
                )
            },
        )

        self.assertRedirects(
            datetime_response,
            reverse("orders:reservation_preview"),
            fetch_redirect_response=False,
        )

        preview_response = self.client.get(reverse("orders:reservation_preview"))

        self.assertEqual(
            preview_response.status_code,
            200,
        )
        self.assertContains(
            preview_response,
            salon.salon_name,
        )
        self.assertContains(
            preview_response,
            service.service_name,
        )

        previous_order_ids = list(
            Order.objects.filter(customer=customer).values_list("pk", flat=True)
        )

        with self.captureOnCommitCallbacks(execute=True):
            checkout_response = self.client.post(
                reverse("orders:checkout"),
                data={
                    "form_action": ("confirm_checkout"),
                    "coupon_code": "",
                    "payment_method": (AppointmentCheckoutForm.PAYMENT_METHOD_SALON),
                },
            )

        self.assertRedirects(
            checkout_response,
            reverse("orders:appointments"),
            fetch_redirect_response=False,
        )

        new_orders = Order.objects.filter(customer=customer).exclude(
            pk__in=previous_order_ids
        )

        self.assertEqual(
            new_orders.count(),
            1,
        )

        order = new_orders.get()

        self.assertEqual(
            order.salon,
            salon,
        )
        self.assertEqual(
            order.status,
            "pending",
        )
        self.assertTrue(order.is_finally)
        self.assertFalse(order.is_paid)
        self.assertEqual(
            order.selected_payment_method,
            "pay_in_salon",
        )
        self.assertFalse(order.requires_online_payment)

        appointment = OrderDetail.objects.get(order=order)

        self.assertEqual(
            appointment.salon,
            salon,
        )
        self.assertEqual(
            appointment.service,
            service,
        )
        self.assertEqual(
            appointment.stylist,
            stylist,
        )
        self.assertEqual(
            appointment.date,
            candidate["date"],
        )
        self.assertEqual(
            appointment.time,
            candidate["start_time"],
        )
        self.assertEqual(
            appointment.end_time,
            candidate["end_time"],
        )

        expected_duration = int(service.duration_minutes or 0)
        expected_buffer = int(get_service_buffer_minutes(service))
        expected_occupied_until = (
            datetime.combine(
                candidate["date"],
                candidate["end_time"],
            )
            + timedelta(minutes=expected_buffer)
        ).time()

        self.assertEqual(
            appointment.scheduled_duration_minutes,
            expected_duration,
        )
        self.assertEqual(
            appointment.buffer_minutes,
            expected_buffer,
        )
        self.assertEqual(
            appointment.occupied_until,
            expected_occupied_until,
        )

        self.assertFalse(Payment.objects.filter(order=order).exists())
        self.assertFalse(WalletTransaction.objects.filter(order=order).exists())

        session = self.client.session

        self.assertNotIn(
            "salon_id",
            session,
        )
        self.assertNotIn(
            "stylist_selections",
            session,
        )
        self.assertNotIn(
            "datetime_selections",
            session,
        )

        detail_response = self.client.get(
            reverse(
                "orders:appointment_detail",
                kwargs={
                    "pk": appointment.pk,
                },
            )
        )

        self.assertEqual(
            detail_response.status_code,
            200,
        )
        self.assertContains(
            detail_response,
            service.service_name,
        )
        self.assertContains(
            detail_response,
            "پرداخت در مجموعه",
        )

        return order

    def test_customer_can_book_all_five_beta_salons(
        self,
    ):
        with TemporaryDirectory() as media_root:
            with self.settings(
                MEDIA_ROOT=media_root,
            ):
                call_command(
                    "seed_local_demo_data",
                    reset=True,
                    beta_acceptance=True,
                    days=14,
                    stdout=StringIO(),
                )

                salons = list(
                    Salon.objects.filter(slug__in=self.seed_slugs).order_by("slug")
                )

                self.assertEqual(
                    len(salons),
                    5,
                )

                customer = Customer.objects.select_related("user").get(
                    user__mobile_number=(f"{MOBILE_PREFIX}30008")
                )

                self.client.force_login(customer.user)

                payment_count_before = Payment.objects.count()
                wallet_transaction_count_before = WalletTransaction.objects.count()

                created_orders = []

                with (
                    patch(
                        "apps.orders.views." "schedule_order_reminder"
                    ) as schedule_reminder,
                    patch(
                        "apps.orders.views." "notify_manager_and_stylists_for_booking"
                    ) as notify_team,
                    patch(
                        "apps.orders.views." "notify_booking_created"
                    ) as notify_customer,
                    patch(
                        "apps.payments.finance." "sync_settlement_for_order"
                    ) as sync_settlement,
                ):
                    for salon in salons:
                        created_orders.append(
                            self._run_booking_flow(
                                salon=salon,
                                customer=customer,
                            )
                        )

                self.assertEqual(
                    len(created_orders),
                    5,
                )
                self.assertEqual(
                    len({order.salon_id for order in created_orders}),
                    5,
                )

                created_order_ids = [order.pk for order in created_orders]

                self.assertEqual(
                    OrderDetail.objects.filter(order_id__in=created_order_ids).count(),
                    5,
                )

                self.assertEqual(
                    Payment.objects.count(),
                    payment_count_before,
                )
                self.assertEqual(
                    WalletTransaction.objects.count(),
                    wallet_transaction_count_before,
                )

                self.assertEqual(
                    schedule_reminder.call_count,
                    5,
                )
                self.assertEqual(
                    notify_team.call_count,
                    5,
                )
                self.assertEqual(
                    notify_customer.call_count,
                    5,
                )
                self.assertEqual(
                    sync_settlement.call_count,
                    5,
                )
