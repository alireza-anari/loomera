from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("salons", "0004_salon_onboarding_contact_address_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="salon",
            name="city",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                max_length=100,
                verbose_name="شهر",
            ),
        ),
        migrations.AddField(
            model_name="salon",
            name="zone_label",
            field=models.CharField(
                blank=True,
                default="",
                max_length=100,
                verbose_name="منطقه / ناحیه",
            ),
        ),
    ]
