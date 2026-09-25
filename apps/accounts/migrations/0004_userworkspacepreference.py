# Additive preference data: all historic users, profiles and salon relations stay unchanged.
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_initial"),
        ("salons", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserWorkspacePreference",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(
                    blank=True, default="", max_length=12,
                    choices=[("customer", "مشتری"), ("stylist", "متخصص"), ("manager", "مدیر سالن")],
                )),
                ("has_chosen_multirole_workspace", models.BooleanField(default=False)),
                ("was_salon_workspace", models.BooleanField(default=False)),
                ("salon", models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name="+", to="salons.salon",
                )),
                ("user", models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="workspace_preference", to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "verbose_name": "ترجیح محیط فعالیت",
                "verbose_name_plural": "ترجیحات محیط فعالیت",
            },
        ),
    ]
