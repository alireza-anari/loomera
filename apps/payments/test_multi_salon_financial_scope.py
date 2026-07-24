"""
Regression tests for multi-salon stylist financial isolation.

Place this file at:
    apps/payments/test_multi_salon_financial_scope.py

Run:
    python manage.py test apps.payments.test_multi_salon_financial_scope

These tests protect the critical rule:
    A stylist wallet can be global, but every transaction and withdrawal request
    that is shown or managed in a salon dashboard must be scoped by salon.
"""

from datetime import time, timedelta
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.accounts.models import CustomUser, Customer, SalonManager, Stylist
from apps.dashboards.finance_withdrawal_forms import StylistWithdrawalRequestForm
from apps.orders.models import Order, OrderDetail
from apps.payments.models import (
    OrderDetailFinancialSnapshot,
    StylistWallet,
    StylistWalletTransaction,
    StylistWalletWithdrawalRequest,
)
from apps.salons.models import Salon
from apps.services.models import Services


class FinancialScopeStaticGuardTests(SimpleTestCase):
    """Static guards catch dangerous replace mistakes before runtime tests."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.base_dir = Path(settings.BASE_DIR)

    def read_project_file(self, relative_path):
        return (self.base_dir / relative_path).read_text(encoding="utf-8")

    def test_no_broken_for_salon_replace_left_in_project(self):
        suspicious_files = [
            "apps/payments/models.py",
            "apps/dashboards/finance_withdrawal_forms.py",
            "apps/dashboards/finance_withdrawal_views.py",
            "apps/dashboards/finance_cost_views.py",
            "apps/dashboards/payment_views.py",
        ]

        for relative_path in suspicious_files:
            with self.subTest(file=relative_path):
                self.assertNotIn(
                    "_for_salon(salon)_for_salon",
                    self.read_project_file(relative_path),
                )

    def test_wallet_record_does_not_assign_property_total_balance(self):
        source = self.read_project_file("apps/payments/models.py")

        self.assertNotIn(
            "wallet.total_balance =",
            source,
            "StylistWallet.total_balance is a property, not a database field. "
            "_record must only update pending_balance and available_balance.",
        )
        self.assertNotIn(
            "\"total_balance\",\n                    \"updated_at\"",
            source,
            "Do not include total_balance in update_fields for StylistWallet.save().",
        )

    def test_withdrawal_form_requires_salon_scope(self):
        source = self.read_project_file("apps/dashboards/finance_withdrawal_forms.py")

        self.assertIn("def __init__(self, *args, wallet=None, salon=None", source)
        self.assertIn("self.salon = salon", source)
        self.assertIn("available_balance_for_salon(self.salon)", source)
        self.assertNotIn("available_balance_for_salon(salon)", source)
        self.assertIn("create_withdrawal_request(\n            salon=self.salon", source)

    def test_manager_withdrawal_views_never_filter_by_membership_for_money(self):
        source = self.read_project_file("apps/dashboards/finance_withdrawal_views.py")

        self.assertNotIn(
            "wallet__stylist__stylists_of_salon",
            source,
            "Manager withdrawal pages must filter requests with salon=salon, not by stylist membership.",
        )
        self.assertIn("StylistWalletWithdrawalRequest.objects.filter(\n            salon=salon", source)

    def test_finance_hub_does_not_count_stylist_withdrawals_by_membership(self):
        source = self.read_project_file("apps/dashboards/payment_views.py")

        self.assertNotIn(
            "wallet__stylist__stylists_of_salon",
            source,
            "Finance hub must count stylist withdrawal requests with salon=salon only.",
        )

    def test_profit_report_template_does_not_call_methods_with_arguments(self):
        source = self.read_project_file("templates/dashboards/finance_profit_report.html")

        forbidden_template_calls = [
            "pending_balance_for_salon(salon)",
            "available_balance_for_salon(salon)",
            "total_balance_for_salon(salon)",
        ]
        for forbidden in forbidden_template_calls:
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(
                    forbidden,
                    source,
                    "Django templates cannot call Python methods with arguments. "
                    "Prepare row.pending_balance / row.available_balance / row.total_balance in the view.",
                )

    def test_financial_scope_migration_or_initial_baseline_is_safe(self):
        migrations_dir = self.base_dir / "apps/payments/migrations"
        historical_migrations = sorted(
            migrations_dir.glob("0017*.py")
        )
        models_source = self.read_project_file(
            "apps/payments/models.py"
        )

        receipt_paths = (
            'upload_to="wallet_withdrawal_receipts/"',
            'upload_to="salon_wallet_withdrawal_receipts/"',
            'upload_to="stylist_wallet_withdrawal_receipts/"',
        )

        for receipt_path in receipt_paths:
            with self.subTest(receipt_path=receipt_path):
                self.assertEqual(
                    models_source.count(receipt_path),
                    1,
                    "Each withdrawal model must keep its own "
                    "receipt path.",
                )

        if historical_migrations:
            source = historical_migrations[0].read_text(
                encoding="utf-8"
            )

            self.assertIn("migrations.RunPython(", source)
            self.assertIn(
                "backfill_stylist_wallet_transaction_salon",
                source,
            )

            for receipt_path in receipt_paths:
                self.assertIn(receipt_path, source)

            return

        initial_files = [
            migrations_dir / "0001_initial.py",
            migrations_dir / "0002_initial.py",
        ]

        for initial_file in initial_files:
            self.assertTrue(
                initial_file.exists(),
                "Initial migration baseline is incomplete: "
                f"{initial_file.name}",
            )

        initial_source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in initial_files
        )

        for receipt_path in receipt_paths:
            with self.subTest(
                initial_receipt_path=receipt_path
            ):
                self.assertEqual(
                    initial_source.count(receipt_path),
                    1,
                    "The initial baseline must preserve "
                    "distinct receipt paths.",
                )

        self.assertIn(
            'model_name="stylistwallettransaction"',
            initial_source,
        )
        self.assertIn(
            'model_name="stylistwalletwithdrawalrequest"',
            initial_source,
        )

        for index_name in (
            "sty_wal_tx_salon_created_idx",
            "sty_wal_tx_wallet_salon_idx",
            "sty_wd_salon_status_idx",
            "sty_wd_wallet_salon_idx",
        ):
            with self.subTest(index_name=index_name):
                self.assertIn(index_name, initial_source)


class MultiSalonStylistWalletScopeTests(TestCase):
    """Runtime tests for a stylist active in two salons."""

    @classmethod
    def setUpTestData(cls):
        cls.manager_a_user = cls.create_user("09120000001", "مدیر", "الف")
        cls.manager_b_user = cls.create_user("09120000002", "مدیر", "ب")
        cls.stylist_user = cls.create_user("09120000003", "متخصص", "مشترک")
        cls.customer_user = cls.create_user("09120000004", "مشتری", "تست")

        cls.manager_a = SalonManager.objects.create(
            user=cls.manager_a_user,
            is_active=True,
        )
        cls.manager_b = SalonManager.objects.create(
            user=cls.manager_b_user,
            is_active=True,
        )
        cls.stylist = Stylist.objects.create(
            user=cls.stylist_user,
            is_active=True,
            expert="زیبایی",
        )
        cls.customer = Customer.objects.create(user=cls.customer_user)

        cls.salon_a = Salon.objects.create(
            salon_name="سالن A",
            salon_manager=cls.manager_a,
            is_active=True,
        )
        cls.salon_b = Salon.objects.create(
            salon_name="سالن B",
            salon_manager=cls.manager_b,
            is_active=True,
        )

        cls.salon_a.stylists.add(cls.stylist)
        cls.salon_b.stylists.add(cls.stylist)

        cls.service_a = cls.create_service("خدمت سالن A", 1_000_000)
        cls.service_b = cls.create_service("خدمت سالن B", 700_000)

        cls.salon_a.services.add(cls.service_a)
        cls.salon_b.services.add(cls.service_b)
        cls.service_a.stylists.add(cls.stylist)
        cls.service_b.stylists.add(cls.stylist)

    @staticmethod
    def create_user(mobile, name, family):
        user = CustomUser.objects.create_user(
            mobile_number=mobile,
            active_code="test-code",
            name=name,
            family=family,
            password="test-pass-123",
        )
        user.is_active = True
        user.save(update_fields=["is_active"])
        return user

    @staticmethod
    def create_service(name, price):
        return Services.objects.create(
            service_name=name,
            base_price=price,
            duration_minutes=60,
            buffer_minutes=0,
            is_active=True,
        )

    def create_order_bundle(
        self,
        *,
        salon,
        service,
        gross_amount,
        stylist_share,
        date_offset_days=1,
    ):
        order = Order.objects.create(
            customer=self.customer,
            salon=salon,
            status="completed",
            is_finally=True,
            is_paid=True,
            stylist_approved=True,
            selected_payment_method="pay_in_salon",
            subtotal_amount=gross_amount,
            total_amount=gross_amount,
        )
        order_detail = OrderDetail.objects.create(
            order=order,
            salon=salon,
            service=service,
            stylist=self.stylist,
            price=gross_amount,
            date=timezone.localdate() + timedelta(days=date_offset_days),
            time=time(10, 0),
            end_time=time(11, 0),
            scheduled_duration_minutes=60,
            buffer_minutes=0,
            occupied_until=time(11, 0),
        )
        snapshot = OrderDetailFinancialSnapshot.objects.create(
            order_detail=order_detail,
            order=order,
            salon=salon,
            stylist=self.stylist,
            service=service,
            payment_method="pay_in_salon",
            gross_amount=gross_amount,
            paid_amount_allocated=gross_amount,
            net_after_platform=gross_amount,
            share_base_amount=gross_amount,
            stylist_gross_share=stylist_share,
            stylist_net_share=stylist_share,
            salon_gross_share=max(gross_amount - stylist_share, 0),
            salon_net_share=max(gross_amount - stylist_share, 0),
            salon_net_profit=max(gross_amount - stylist_share, 0),
            status=OrderDetailFinancialSnapshot.Status.FINALIZED,
            finalized_at=timezone.now(),
        )
        return order, order_detail, snapshot

    def wallet(self):
        wallet, _ = StylistWallet.objects.get_or_create(stylist=self.stylist)
        return wallet

    def test_transaction_salon_is_resolved_from_snapshot_order_detail_and_order(self):
        wallet = self.wallet()
        order_a, detail_a, snapshot_a = self.create_order_bundle(
            salon=self.salon_a,
            service=self.service_a,
            gross_amount=1_000_000,
            stylist_share=600_000,
        )
        order_b, detail_b, snapshot_b = self.create_order_bundle(
            salon=self.salon_b,
            service=self.service_b,
            gross_amount=700_000,
            stylist_share=350_000,
        )

        tx_from_snapshot = wallet.add_pending(
            10_000,
            description="از سند مالی",
            financial_snapshot=snapshot_a,
        )
        tx_from_detail = wallet.add_pending(
            20_000,
            description="از آیتم رزرو",
            order_detail=detail_b,
        )
        tx_from_order = wallet.add_pending(
            30_000,
            description="از سفارش",
            order=order_a,
        )

        self.assertEqual(tx_from_snapshot.salon_id, self.salon_a.id)
        self.assertEqual(tx_from_detail.salon_id, self.salon_b.id)
        self.assertEqual(tx_from_order.salon_id, self.salon_a.id)

    def test_salon_balances_are_isolated_even_when_global_wallet_has_money(self):
        wallet = self.wallet()

        wallet.add_pending(1_000_000, salon=self.salon_a, description="درآمد A")
        wallet.release_pending(1_000_000, salon=self.salon_a, description="آزادسازی A")

        self.assertEqual(wallet.available_balance_for_salon(self.salon_a), 1_000_000)
        self.assertEqual(wallet.pending_balance_for_salon(self.salon_a), 0)
        self.assertEqual(wallet.total_balance_for_salon(self.salon_a), 1_000_000)

        self.assertEqual(wallet.available_balance_for_salon(self.salon_b), 0)
        self.assertEqual(wallet.pending_balance_for_salon(self.salon_b), 0)
        self.assertEqual(wallet.total_balance_for_salon(self.salon_b), 0)

        wallet.refresh_from_db()
        self.assertEqual(int(wallet.available_balance), 1_000_000)
        self.assertEqual(int(wallet.total_balance), 1_000_000)

    def test_withdrawal_request_is_created_only_for_the_active_salon_balance(self):
        wallet = self.wallet()
        wallet.add_pending(1_000_000, salon=self.salon_a, description="درآمد A")
        wallet.release_pending(1_000_000, salon=self.salon_a, description="آزادسازی A")

        withdrawal = wallet.create_withdrawal_request(
            salon=self.salon_a,
            amount=300_000,
            iban="IR" + "1" * 24,
            account_holder_name="متخصص مشترک",
            bank_name="بانک تست",
        )

        self.assertEqual(withdrawal.salon_id, self.salon_a.id)
        self.assertEqual(wallet.available_balance_for_salon(self.salon_a), 700_000)
        self.assertEqual(wallet.available_balance_for_salon(self.salon_b), 0)
        self.assertTrue(
            StylistWalletTransaction.objects.filter(
                wallet=wallet,
                salon=self.salon_a,
                withdrawal_request=withdrawal,
                transaction_type=StylistWalletTransaction.TransactionType.WITHDRAW_REQUEST,
                available_delta=-300_000,
            ).exists()
        )

    def test_withdrawal_request_cannot_use_other_salon_balance(self):
        wallet = self.wallet()
        wallet.add_pending(1_000_000, salon=self.salon_a, description="درآمد A")
        wallet.release_pending(1_000_000, salon=self.salon_a, description="آزادسازی A")

        with self.assertRaises(ValidationError):
            wallet.create_withdrawal_request(
                salon=self.salon_b,
                amount=300_000,
                iban="IR" + "2" * 24,
                account_holder_name="متخصص مشترک",
            )

        self.assertFalse(
            StylistWalletWithdrawalRequest.objects.filter(
                wallet=wallet,
                salon=self.salon_b,
            ).exists()
        )
        self.assertFalse(
            StylistWalletTransaction.objects.filter(
                wallet=wallet,
                salon=self.salon_b,
                transaction_type=StylistWalletTransaction.TransactionType.WITHDRAW_REQUEST,
            ).exists()
        )

    def test_withdrawal_form_validates_against_selected_salon_not_global_wallet(self):
        wallet = self.wallet()
        wallet.add_pending(1_000_000, salon=self.salon_a, description="درآمد A")
        wallet.release_pending(1_000_000, salon=self.salon_a, description="آزادسازی A")

        form = StylistWithdrawalRequestForm(
            data={
                "amount": "300000",
                "iban": "IR" + "3" * 24,
                "account_holder_name": "متخصص مشترک",
                "bank_name": "بانک تست",
                "note": "",
            },
            wallet=wallet,
            salon=self.salon_b,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("amount", form.errors)
        self.assertFalse(
            StylistWalletWithdrawalRequest.objects.filter(
                wallet=wallet,
                salon=self.salon_b,
            ).exists()
        )

    def test_rejected_withdrawal_restores_available_balance_only_to_same_salon(self):
        wallet = self.wallet()
        wallet.add_pending(1_000_000, salon=self.salon_a, description="درآمد A")
        wallet.release_pending(1_000_000, salon=self.salon_a, description="آزادسازی A")

        withdrawal = wallet.create_withdrawal_request(
            salon=self.salon_a,
            amount=400_000,
            iban="IR" + "4" * 24,
            account_holder_name="متخصص مشترک",
        )
        self.assertEqual(wallet.available_balance_for_salon(self.salon_a), 600_000)
        self.assertEqual(wallet.available_balance_for_salon(self.salon_b), 0)

        withdrawal.reject(note="رد تستی")
        wallet.refresh_from_db()

        self.assertEqual(wallet.available_balance_for_salon(self.salon_a), 1_000_000)
        self.assertEqual(wallet.available_balance_for_salon(self.salon_b), 0)
        self.assertTrue(
            StylistWalletTransaction.objects.filter(
                wallet=wallet,
                salon=self.salon_a,
                withdrawal_request=withdrawal,
                transaction_type=StylistWalletTransaction.TransactionType.WITHDRAW_RESTORE,
                available_delta=400_000,
            ).exists()
        )

    def test_manager_safe_query_does_not_show_other_salon_withdrawals(self):
        wallet = self.wallet()
        wallet.add_pending(1_000_000, salon=self.salon_a, description="درآمد A")
        wallet.release_pending(1_000_000, salon=self.salon_a, description="آزادسازی A")
        withdrawal = wallet.create_withdrawal_request(
            salon=self.salon_a,
            amount=200_000,
            iban="IR" + "5" * 24,
            account_holder_name="متخصص مشترک",
        )

        safe_for_salon_b = StylistWalletWithdrawalRequest.objects.filter(
            salon=self.salon_b,
        )
        unsafe_membership_based_for_salon_b = StylistWalletWithdrawalRequest.objects.filter(
            wallet__stylist__stylists_of_salon=self.salon_b,
        ).distinct()

        self.assertEqual(safe_for_salon_b.count(), 0)

        # This assertion documents why wallet__stylist__stylists_of_salon is forbidden
        # in finance manager views: it leaks salon A withdrawal into salon B because
        # the stylist is a member of both salons.
        self.assertIn(withdrawal, list(unsafe_membership_based_for_salon_b))

    def test_financial_snapshots_for_profit_report_are_salon_scoped(self):
        self.create_order_bundle(
            salon=self.salon_a,
            service=self.service_a,
            gross_amount=1_000_000,
            stylist_share=600_000,
        )

        summary_a = OrderDetailFinancialSnapshot.objects.filter(
            salon=self.salon_a,
            stylist=self.stylist,
        ).count()
        summary_b = OrderDetailFinancialSnapshot.objects.filter(
            salon=self.salon_b,
            stylist=self.stylist,
        ).count()

        self.assertEqual(summary_a, 1)
        self.assertEqual(summary_b, 0)

    def test_legacy_rows_without_salon_are_not_in_manager_salon_queries(self):
        wallet = self.wallet()
        legacy = StylistWalletWithdrawalRequest.objects.create(
            wallet=wallet,
            salon=None,
            amount=100_000,
            iban="IR" + "6" * 24,
            account_holder_name="legacy",
        )

        self.assertFalse(
            StylistWalletWithdrawalRequest.objects.filter(
                salon=self.salon_a,
                pk=legacy.pk,
            ).exists()
        )
        self.assertFalse(
            StylistWalletWithdrawalRequest.objects.filter(
                salon=self.salon_b,
                pk=legacy.pk,
            ).exists()
        )
