from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("help_center", "0002_route_identity"),
    ]

    operations = [
        migrations.AlterField(
            model_name="helparticle",
            name="key",
            field=models.CharField(
                db_index=True,
                help_text="مثال: manager.team یا customer.addresses",
                max_length=140,
                unique=True,
                verbose_name="کلید صفحه/مقاله",
            ),
        ),
    ]
