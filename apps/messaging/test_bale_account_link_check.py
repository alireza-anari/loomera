from __future__ import annotations

import io
import json

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.accounts.models import CustomUser
from apps.messaging.constants import (
    MessagingConnectionStatus,
    MessagingIdentityStatus,
    MessagingProviderKey,
)
from apps.messaging.management.commands.bale_account_link_check import (
    run_bale_account_link_check,
)
from apps.messaging.models import (
    MessagingAccountConnection,
    MessagingIdentity,
    MessagingProvider,
)
from apps.messaging.services import connect_identity_to_user, ensure_default_providers


class BaleAccountLinkCheckTests(TestCase):
    def setUp(self):
        ensure_default_providers()
        self.bale = MessagingProvider.objects.get(key=MessagingProviderKey.BALE)
        self.user = CustomUser.objects.create_user(
            mobile_number="09121112233",
            email="bale-account-link@example.com",
            name="Bale",
            family="Account",
            password="pass12345",
        )

    def _identity(
        self, *, status=MessagingIdentityStatus.GUEST, user=None, chat_id="chat-1"
    ):
        return MessagingIdentity.objects.create(
            provider=self.bale,
            provider_user_id=f"provider-user-{MessagingIdentity.objects.count() + 1}",
            chat_id=chat_id,
            user=user,
            status=status,
            display_name="کاربر بله",
        )

    def test_clean_active_connection_has_no_issue(self):
        identity = self._identity()
        connect_identity_to_user(identity, self.user)

        result = run_bale_account_link_check()

        self.assertEqual(result["summary"]["issue_count"], 0)
        self.assertEqual(result["summary"]["problem_connection_count"], 0)

    def test_detects_active_connection_with_non_linked_identity(self):
        identity = self._identity(status=MessagingIdentityStatus.GUEST, user=self.user)
        MessagingAccountConnection.objects.create(
            provider=self.bale,
            identity=identity,
            user=self.user,
            status=MessagingConnectionStatus.ACTIVE,
        )

        result = run_bale_account_link_check()

        self.assertEqual(result["summary"]["problem_connection_count"], 1)
        self.assertIn(
            "identity_not_linked",
            result["problem_connections"][0]["codes"],
        )

    def test_repair_active_identities_is_dry_run_by_default(self):
        identity = self._identity(status=MessagingIdentityStatus.GUEST, user=self.user)
        MessagingAccountConnection.objects.create(
            provider=self.bale,
            identity=identity,
            user=self.user,
            status=MessagingConnectionStatus.ACTIVE,
        )

        result = run_bale_account_link_check(repair_active_identities=True)

        identity.refresh_from_db()
        self.assertTrue(result["summary"]["dry_run"])
        self.assertEqual(result["summary"]["repaired_count"], 0)
        self.assertEqual(identity.status, MessagingIdentityStatus.GUEST)

    def test_apply_repairs_active_connection_identity_status_only_when_safe(self):
        identity = self._identity(status=MessagingIdentityStatus.GUEST, user=self.user)
        MessagingAccountConnection.objects.create(
            provider=self.bale,
            identity=identity,
            user=self.user,
            status=MessagingConnectionStatus.ACTIVE,
        )

        result = run_bale_account_link_check(
            repair_active_identities=True,
            apply=True,
        )

        identity.refresh_from_db()
        self.assertEqual(result["summary"]["repaired_count"], 1)
        self.assertEqual(identity.status, MessagingIdentityStatus.LINKED)
        self.assertEqual(identity.user_id, self.user.pk)
        self.assertIsNotNone(identity.connected_at)
        self.assertIsNone(identity.disconnected_at)

    def test_repair_skips_user_mismatch(self):
        other_user = CustomUser.objects.create_user(
            mobile_number="09121112234",
            email="other-bale-account-link@example.com",
            name="Other",
            family="User",
            password="pass12345",
        )
        identity = self._identity(status=MessagingIdentityStatus.GUEST, user=other_user)
        MessagingAccountConnection.objects.create(
            provider=self.bale,
            identity=identity,
            user=self.user,
            status=MessagingConnectionStatus.ACTIVE,
        )

        result = run_bale_account_link_check(
            repair_active_identities=True,
            apply=True,
        )

        identity.refresh_from_db()
        self.assertEqual(result["summary"]["repaired_count"], 0)
        self.assertEqual(identity.status, MessagingIdentityStatus.GUEST)
        self.assertEqual(result["summary"]["skipped_count"], 1)

    def test_detects_linked_identity_without_active_connection(self):
        self._identity(status=MessagingIdentityStatus.LINKED, user=self.user)

        result = run_bale_account_link_check()

        self.assertEqual(result["summary"]["linked_without_connection_count"], 1)
        self.assertEqual(result["summary"]["issue_count"], 1)

    def test_detects_active_connection_without_chat_id(self):
        identity = self._identity(
            status=MessagingIdentityStatus.LINKED,
            user=self.user,
            chat_id="",
        )
        MessagingAccountConnection.objects.create(
            provider=self.bale,
            identity=identity,
            user=self.user,
            status=MessagingConnectionStatus.ACTIVE,
        )

        result = run_bale_account_link_check()

        self.assertEqual(result["summary"]["active_without_chat_id_count"], 1)
        self.assertIn(
            "missing_chat_id",
            result["problem_connections"][0]["codes"],
        )

    def test_json_output_masks_provider_user_and_chat_ids(self):
        identity = self._identity(
            status=MessagingIdentityStatus.LINKED,
            user=self.user,
            chat_id="very-secret-chat-id",
        )
        MessagingAccountConnection.objects.create(
            provider=self.bale,
            identity=identity,
            user=self.user,
            status=MessagingConnectionStatus.ACTIVE,
        )

        out = io.StringIO()
        call_command("bale_account_link_check", "--json", stdout=out)

        raw = out.getvalue()
        payload = json.loads(raw)

        self.assertNotIn("very-secret-chat-id", raw)
        self.assertIn("identities", payload["counts"])
        self.assertEqual(payload["summary"]["error_count"], 0)

    def test_strict_fails_when_issue_exists(self):
        self._identity(status=MessagingIdentityStatus.LINKED, user=self.user)

        with self.assertRaises(CommandError):
            call_command("bale_account_link_check", "--strict")
