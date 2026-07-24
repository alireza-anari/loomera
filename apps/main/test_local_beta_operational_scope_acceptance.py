from __future__ import annotations

from datetime import time, timedelta
from io import StringIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import (
    Customer,
    CustomUser,
    Stylist,
)
from apps.main.management.commands.seed_local_demo_data import (
    MOBILE_PREFIX,
    SEED_TAG,
)
from apps.orders.models import Order, OrderDetail
from apps.payments.models import (
    LedgerEntry,
    Payment,
    StaffEarning,
    WalletTransaction,
)
from apps.salons.models import Salon
from apps.services.models import Services


@override_settings(
    DEBUG=True,
    PASSWORD_HASHERS=[
        "django.contrib.auth.hashers.MD5PasswordHasher",
    ],
    ONLINE_PAYMENT_ENABLED=False,
    PAYMENT_MODE="mock",
    MESSAGING_OUTBOUND_ENABLED=False,
    EMAIL_BACKEND=("django.core.mail.backends.dummy.EmailBackend"),
    CACHES={
        "default": {
            "BACKEND": ("django.core.cache.backends.locmem." "LocMemCache"),
            "LOCATION": ("local-beta-operational-scope"),
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
class LocalBetaOperationalScopeAcceptanceTests(TestCase):
    def _set_active_stylist_salon(
        self,
        salon,
    ):
        session = self.client.session
        session["active_stylist_salon_id"] = str(salon.pk)
        session.save()

    def _appointment_card_ids(
        self,
        response,
    ):
        return {item["id"] for item in response.context["all_appointment_cards"]}

    def _create_shared_stylist_order(
        self,
        *,
        salon,
        stylist,
        customer,
    ):
        service = (
            Services.objects.filter(
                services_of_salon=salon,
                stylists=stylist,
                is_active=True,
            )
            .distinct()
            .order_by("pk")
            .first()
        )

        self.assertIsNotNone(service)

        price = int(service.base_price or 0)
        appointment_date = timezone.localdate() + timedelta(days=8)

        order = Order.objects.create(
            customer=customer,
            salon=salon,
            status="pending",
            is_finally=False,
            is_paid=False,
            description=(f"{SEED_TAG}:acceptance:" "shared-stylist-salon-2"),
            stylist_approved=False,
            selected_payment_method=("pay_in_salon"),
            requires_online_payment=False,
            subtotal_amount=price,
            total_amount=price,
            salon_payout_amount=price,
            booking_source="customer",
        )

        appointment = OrderDetail.objects.create(
            order=order,
            service=service,
            stylist=stylist,
            salon=salon,
            price=price,
            date=appointment_date,
            time=time(9, 0),
            end_time=None,
            scheduled_duration_minutes=int(service.duration_minutes or 30),
            buffer_minutes=int(service.buffer_minutes or 0),
        )

        return order, appointment

    def test_manager_and_multi_salon_stylist_scope(
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

                salon_one = Salon.objects.get(slug="local-seed-salon-1")
                salon_two = Salon.objects.get(slug="local-seed-salon-2")

                manager_one = CustomUser.objects.get(
                    mobile_number=(f"{MOBILE_PREFIX}10001")
                )
                manager_two = CustomUser.objects.get(
                    mobile_number=(f"{MOBILE_PREFIX}10002")
                )

                shared_stylist = Stylist.objects.select_related("user").get(
                    user__mobile_number=(f"{MOBILE_PREFIX}20001")
                )

                unrelated_stylist = Stylist.objects.select_related("user").get(
                    user__mobile_number=(f"{MOBILE_PREFIX}20004")
                )

                customer = Customer.objects.select_related("user").get(
                    user__mobile_number=(f"{MOBILE_PREFIX}30008")
                )

                salon_one_order = Order.objects.get(
                    description=(f"{SEED_TAG}:order:" "pending-pay-in-salon")
                )
                salon_one_appointment = salon_one_order.order_details1.select_related(
                    "salon",
                    "stylist",
                ).get()

                self.assertEqual(
                    salon_one_appointment.salon,
                    salon_one,
                )
                self.assertEqual(
                    salon_one_appointment.stylist,
                    shared_stylist,
                )

                (
                    salon_two_order,
                    salon_two_appointment,
                ) = self._create_shared_stylist_order(
                    salon=salon_two,
                    stylist=shared_stylist,
                    customer=customer,
                )

                # ------------------------------------------
                # Manager scope
                # ------------------------------------------

                manager_one_detail_url = reverse(
                    "dashboards:appointment_detail",
                    kwargs={
                        "salon_id": salon_one.pk,
                        "appointment_id": (salon_one_appointment.pk),
                    },
                )

                salon_two_detail_url = reverse(
                    "dashboards:appointment_detail",
                    kwargs={
                        "salon_id": salon_two.pk,
                        "appointment_id": (salon_two_appointment.pk),
                    },
                )

                salon_two_action_url = reverse(
                    "dashboards:appointment_action",
                    kwargs={
                        "salon_id": salon_two.pk,
                        "appointment_id": (salon_two_appointment.pk),
                    },
                )

                self.client.force_login(manager_one)

                own_manager_response = self.client.get(manager_one_detail_url)

                self.assertEqual(
                    own_manager_response.status_code,
                    200,
                )
                self.assertEqual(
                    own_manager_response.context["salon"],
                    salon_one,
                )

                # Manager one must not read salon two.
                foreign_manager_response = self.client.get(salon_two_detail_url)

                self.assertEqual(
                    foreign_manager_response.status_code,
                    404,
                )

                original_salon_two_status = salon_two_order.status

                # A forged action request must also fail
                # before any state transition.
                foreign_manager_action = self.client.post(
                    salon_two_action_url,
                    {
                        "action": "cancel",
                    },
                )

                self.assertEqual(
                    foreign_manager_action.status_code,
                    404,
                )

                salon_two_order.refresh_from_db()

                self.assertEqual(
                    salon_two_order.status,
                    original_salon_two_status,
                )

                self.client.force_login(manager_two)

                own_salon_two_response = self.client.get(salon_two_detail_url)

                self.assertEqual(
                    own_salon_two_response.status_code,
                    200,
                )
                self.assertEqual(
                    own_salon_two_response.context["salon"],
                    salon_two,
                )

                # ------------------------------------------
                # Multi-salon stylist — salon one active
                # ------------------------------------------

                self.client.force_login(shared_stylist.user)
                self._set_active_stylist_salon(salon_one)

                stylist_list_url = reverse("dashboards:" "stylist_appointments")

                stylist_one_detail_url = reverse(
                    "dashboards:" "stylist_appointment_detail",
                    kwargs={
                        "appointment_id": (salon_one_appointment.pk),
                    },
                )

                stylist_two_detail_url = reverse(
                    "dashboards:" "stylist_appointment_detail",
                    kwargs={
                        "appointment_id": (salon_two_appointment.pk),
                    },
                )

                salon_one_list_response = self.client.get(stylist_list_url)

                self.assertEqual(
                    salon_one_list_response.status_code,
                    200,
                )

                salon_one_card_ids = self._appointment_card_ids(salon_one_list_response)

                self.assertIn(
                    salon_one_appointment.pk,
                    salon_one_card_ids,
                )
                self.assertNotIn(
                    salon_two_appointment.pk,
                    salon_one_card_ids,
                )

                self.assertEqual(
                    self.client.get(stylist_one_detail_url).status_code,
                    200,
                )
                self.assertEqual(
                    self.client.get(stylist_two_detail_url).status_code,
                    404,
                )

                original_confirmation_status = salon_two_appointment.confirmation_status

                # Even the correct stylist cannot mutate an
                # appointment belonging to another active salon.
                inactive_salon_action = self.client.post(
                    stylist_two_detail_url,
                    {
                        "action": "confirm",
                    },
                )

                self.assertEqual(
                    inactive_salon_action.status_code,
                    404,
                )

                salon_two_appointment.refresh_from_db()

                self.assertEqual(
                    salon_two_appointment.confirmation_status,
                    original_confirmation_status,
                )

                # ------------------------------------------
                # Switch active salon through real endpoint
                # ------------------------------------------

                switch_response = self.client.post(
                    reverse("dashboards:" "set_stylist_active_salon"),
                    {
                        "salon_id": str(salon_two.pk),
                        "next": stylist_list_url,
                    },
                )

                self.assertRedirects(
                    switch_response,
                    stylist_list_url,
                    fetch_redirect_response=False,
                )

                self.assertEqual(
                    str(self.client.session.get("active_stylist_salon_id")),
                    str(salon_two.pk),
                )

                salon_two_list_response = self.client.get(stylist_list_url)

                self.assertEqual(
                    salon_two_list_response.status_code,
                    200,
                )

                salon_two_card_ids = self._appointment_card_ids(salon_two_list_response)

                self.assertIn(
                    salon_two_appointment.pk,
                    salon_two_card_ids,
                )
                self.assertNotIn(
                    salon_one_appointment.pk,
                    salon_two_card_ids,
                )

                self.assertEqual(
                    self.client.get(stylist_two_detail_url).status_code,
                    200,
                )
                self.assertEqual(
                    self.client.get(stylist_one_detail_url).status_code,
                    404,
                )

                # ------------------------------------------
                # Unrelated stylist in the same salon
                # ------------------------------------------

                self.client.force_login(unrelated_stylist.user)
                self._set_active_stylist_salon(salon_two)

                unrelated_get_response = self.client.get(stylist_two_detail_url)

                self.assertEqual(
                    unrelated_get_response.status_code,
                    404,
                )

                unrelated_post_response = self.client.post(
                    stylist_two_detail_url,
                    {
                        "action": "confirm",
                    },
                )

                self.assertEqual(
                    unrelated_post_response.status_code,
                    404,
                )

                salon_two_appointment.refresh_from_db()

                self.assertEqual(
                    salon_two_appointment.confirmation_status,
                    original_confirmation_status,
                )

                # ------------------------------------------
                # Authorized stylist state transition
                # ------------------------------------------

                self.client.force_login(shared_stylist.user)
                self._set_active_stylist_salon(salon_two)

                financial_counts_before = {
                    "payments": (Payment.objects.count()),
                    "wallet_transactions": (WalletTransaction.objects.count()),
                    "ledger_entries": (LedgerEntry.objects.count()),
                    "staff_earnings": (StaffEarning.objects.count()),
                }

                with patch(
                    "apps.payments.finance." "sync_settlement_for_order"
                ) as sync_settlement:
                    authorized_response = self.client.post(
                        stylist_two_detail_url,
                        {
                            "action": "confirm",
                        },
                    )

                self.assertRedirects(
                    authorized_response,
                    stylist_two_detail_url,
                    fetch_redirect_response=False,
                )

                salon_two_appointment.refresh_from_db()
                salon_two_order.refresh_from_db()

                self.assertEqual(
                    salon_two_appointment.confirmation_status,
                    (OrderDetail.ConfirmationStatus.CONFIRMED),
                )
                self.assertEqual(
                    salon_two_appointment.lifecycle_status,
                    (OrderDetail.ServiceLifecycleStatus.CONFIRMED),
                )
                self.assertEqual(
                    salon_two_order.status,
                    "confirmed",
                )
                self.assertTrue(salon_two_order.is_finally)
                self.assertTrue(salon_two_order.stylist_approved)
                self.assertEqual(
                    salon_two_order.salon,
                    salon_two,
                )
                self.assertEqual(
                    salon_two_appointment.stylist,
                    shared_stylist,
                )

                sync_settlement.assert_called_once()

                self.assertEqual(
                    Payment.objects.count(),
                    financial_counts_before["payments"],
                )
                self.assertEqual(
                    WalletTransaction.objects.count(),
                    financial_counts_before["wallet_transactions"],
                )
                self.assertEqual(
                    LedgerEntry.objects.count(),
                    financial_counts_before["ledger_entries"],
                )
                self.assertEqual(
                    StaffEarning.objects.count(),
                    financial_counts_before["staff_earnings"],
                )
