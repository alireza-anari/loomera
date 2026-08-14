from django.db import migrations, models


def backfill_legacy_contact(apps, schema_editor):
    Salon = apps.get_model("salons", "Salon")
    for salon in Salon.objects.exclude(phone_number__isnull=True).exclude(phone_number="").iterator():
        digits = "".join(ch for ch in str(salon.phone_number) if ch.isdigit())
        if digits.startswith("98"):
            digits = "0" + digits[2:]
        if len(digits) == 10 and digits.startswith("9"):
            digits = "0" + digits

        update_fields = []
        if len(digits) == 11 and digits.startswith("09") and not salon.mobile_phone:
            salon.mobile_phone = digits
            update_fields.append("mobile_phone")
        elif len(digits) == 11 and digits.startswith("0") and not salon.landline_phone:
            salon.landline_phone = digits
            update_fields.append("landline_phone")

        if update_fields:
            salon.save(update_fields=update_fields)


class Migration(migrations.Migration):
    dependencies = [
        ("salons", "0003_alter_salon_phone_number"),
    ]

    operations = [
        migrations.AddField(
            model_name="salon",
            name="address_plaque",
            field=models.CharField(blank=True, default="", max_length=32, verbose_name="پلاک"),
        ),
        migrations.AddField(
            model_name="salon",
            name="address_unit",
            field=models.CharField(blank=True, default="", max_length=32, verbose_name="واحد"),
        ),
        migrations.AddField(
            model_name="salon",
            name="landline_phone",
            field=models.CharField(blank=True, default="", max_length=11, verbose_name="شماره ثابت مجموعه با کد شهر"),
        ),
        migrations.AddField(
            model_name="salon",
            name="mobile_phone",
            field=models.CharField(blank=True, default="", max_length=11, verbose_name="شماره همراه مجموعه"),
        ),
        migrations.RunPython(backfill_legacy_contact, migrations.RunPython.noop),
    ]
