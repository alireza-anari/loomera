from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .crypto import decrypt_token, encrypt_token


class InstagramConnectionStatus(models.TextChoices):
    CONNECTED = "connected", "Connected"
    NEEDS_REAUTH = "needs_reauth", "Needs re-authentication"
    DISCONNECTED = "disconnected", "Disconnected"


class InstagramAccountConnection(models.Model):
    # stylist is NULL: account belongs to the whole salon.
    # stylist is set: account belongs to that stylist inside that salon.
    salon = models.ForeignKey(
        "salons.Salon",
        on_delete=models.CASCADE,
        related_name="instagram_connections",
    )
    stylist = models.ForeignKey(
        "accounts.Stylist",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="instagram_connections",
    )

    instagram_account_id = models.CharField(max_length=64, unique=True, db_index=True)
    username = models.CharField(max_length=150, blank=True, default="")
    account_type = models.CharField(max_length=32, blank=True, default="")

    # Ciphertext only. Never expose this field in templates/logs/API responses.
    encrypted_access_token = models.TextField(blank=True, default="")
    token_expires_at = models.DateTimeField(null=True, blank=True)
    granted_scopes = models.JSONField(default=list, blank=True)

    status = models.CharField(
        max_length=32,
        choices=InstagramConnectionStatus.choices,
        default=InstagramConnectionStatus.DISCONNECTED,
        db_index=True,
    )
    connected_at = models.DateTimeField(null=True, blank=True)
    disconnected_at = models.DateTimeField(null=True, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "instagram_account_connections"
        ordering = ["-updated_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["salon"],
                condition=models.Q(stylist__isnull=True),
                name="uniq_instagram_salon_context",
            ),
            models.UniqueConstraint(
                fields=["salon", "stylist"],
                condition=models.Q(stylist__isnull=False),
                name="uniq_instagram_stylist_context",
            ),
        ]
        indexes = [
            models.Index(fields=["salon", "status"], name="ig_conn_salon_status"),
            models.Index(fields=["stylist", "status"], name="ig_conn_sty_status"),
        ]

    def __str__(self):
        owner = (
            f"stylist:{self.stylist_id}"
            if self.stylist_id
            else f"salon:{self.salon_id}"
        )
        username = f"@{self.username}" if self.username else self.instagram_account_id
        return f"{username} -> {owner}"

    @property
    def context_kind(self):
        return "stylist" if self.stylist_id else "salon"

    def clean(self):
        super().clean()

        if not self.salon_id:
            raise ValidationError({"salon": "Instagram connection requires a salon."})

        if self.stylist_id and not self._stylist_has_active_membership():
            raise ValidationError(
                {
                    "stylist": (
                        "Stylist Instagram context must belong to an active "
                        "membership in the selected salon."
                    )
                }
            )

    def save(self, *args, **kwargs):
        # Enforce cross-salon isolation at persistence time, not by prompt.
        self.full_clean()
        return super().save(*args, **kwargs)

    def _stylist_has_active_membership(self):
        if not self.salon_id or not self.stylist_id:
            return False

        from apps.salons.models import SalonMembership, SalonMembershipStatus

        return SalonMembership.objects.filter(
            salon_id=self.salon_id,
            stylist_id=self.stylist_id,
            status=SalonMembershipStatus.ACTIVE,
        ).exists()

    def is_context_active(self):
        if self.status != InstagramConnectionStatus.CONNECTED:
            return False

        if not self.stylist_id:
            return bool(getattr(self.salon, "is_active", False))

        return bool(
            getattr(self.salon, "is_active", False)
            and getattr(self.stylist, "is_active", False)
            and self._stylist_has_active_membership()
        )

    def set_access_token(self, raw_token):
        self.encrypted_access_token = encrypt_token(raw_token)

    def get_access_token(self):
        return decrypt_token(self.encrypted_access_token)

    def clear_access_token(self):
        self.encrypted_access_token = ""
        self.token_expires_at = None

    def mark_connected(self):
        now = timezone.now()
        self.status = InstagramConnectionStatus.CONNECTED
        self.connected_at = now
        self.disconnected_at = None

    def mark_disconnected(self):
        self.status = InstagramConnectionStatus.DISCONNECTED
        self.disconnected_at = timezone.now()
        self.clear_access_token()
