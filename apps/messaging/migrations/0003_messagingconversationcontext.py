from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("messaging", "0002_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="MessagingConversationContext",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "scope_type",
                    models.CharField(
                        choices=[
                            ("global", "عمومی"),
                            ("salon", "سالن"),
                            ("stylist", "متخصص"),
                        ],
                        db_index=True,
                        default="global",
                        max_length=24,
                        verbose_name="نوع scope",
                    ),
                ),
                (
                    "scope_object_id",
                    models.PositiveIntegerField(
                        blank=True,
                        db_index=True,
                        null=True,
                        verbose_name="شناسه آبجکت scope",
                    ),
                ),
                (
                    "source",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=40,
                        verbose_name="منبع context",
                    ),
                ),
                (
                    "start_payload",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=128,
                        verbose_name="payload شروع",
                    ),
                ),
                (
                    "metadata",
                    models.JSONField(blank=True, default=dict, verbose_name="متادیتا"),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="آخرین تغییر")),
                (
                    "identity",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="loomi_context",
                        to="messaging.messagingidentity",
                        verbose_name="هویت پیام‌رسان",
                    ),
                ),
            ],
            options={
                "verbose_name": "context مکالمه لومی",
                "verbose_name_plural": "contextهای مکالمه لومی",
                "ordering": ["-updated_at", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="messagingconversationcontext",
            index=models.Index(
                fields=["scope_type", "scope_object_id"],
                name="msg_loomi_scope_idx",
            ),
        ),
    ]
