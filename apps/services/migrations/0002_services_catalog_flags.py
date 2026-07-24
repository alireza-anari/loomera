from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("services", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="services",
            name="catalog_source",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="salon_custom_versions",
                to="services.services",
                verbose_name="خدمت پایه پلتفرم",
            ),
        ),
        migrations.AddField(
            model_name="services",
            name="is_platform_catalog",
            field=models.BooleanField(
                db_index=True,
                default=True,
                help_text="اگر غیرفعال باشد، این رکورد نسخه اختصاصی یک مجموعه از خدمت پایه است و در کاتالوگ عمومی سایت نمایش داده نمی‌شود.",
                verbose_name="خدمت کاتالوگ پلتفرم",
            ),
        ),
    ]
