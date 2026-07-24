# Generated for Loomera beta staging: preserve salon landline leading zero.

from django.db import migrations, models


def normalize_existing_salon_phone_numbers(apps, schema_editor):
    Salon = apps.get_model("salons", "Salon")
    for salon in Salon.objects.exclude(phone_number__isnull=True).exclude(phone_number=""):
        raw = str(salon.phone_number or "").strip()
        digits = "".join(ch for ch in raw if ch.isdigit())
        if digits.startswith("98") and len(digits) >= 10:
            digits = "0" + digits[2:]
        if digits and not digits.startswith("0") and len(digits) == 10:
            digits = "0" + digits
        if digits and digits != raw:
            Salon.objects.filter(pk=salon.pk).update(phone_number=digits)


class Migration(migrations.Migration):

    dependencies = [
        ("salons", "0002_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="salon",
            name="phone_number",
            field=models.CharField(blank=True, max_length=32, null=True, verbose_name="شماره تلفن "),
        ),
        migrations.RunPython(normalize_existing_salon_phone_numbers, migrations.RunPython.noop),
    ]
