from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("help_center", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="helppagecontext",
            name="route_name",
            field=models.CharField(blank=True, db_index=True, default="", max_length=220, verbose_name="نام Route"),
        ),
        migrations.AlterField(
            model_name="helppagecontext",
            name="path_pattern",
            field=models.CharField(blank=True, default="", max_length=500, verbose_name="Regex مسیر"),
        ),
        migrations.AddField(
            model_name="helpconversation",
            name="page_route_name",
            field=models.CharField(blank=True, db_index=True, default="", max_length=220, verbose_name="نام Route صفحه"),
        ),
        migrations.RemoveConstraint(
            model_name="helppagecontext",
            name="hc_unique_role_path_pattern",
        ),
        migrations.AddConstraint(
            model_name="helppagecontext",
            constraint=models.UniqueConstraint(
                fields=("role", "route_name"),
                condition=~models.Q(route_name=""),
                name="hc_unique_role_route_name",
            ),
        ),
        migrations.AddConstraint(
            model_name="helppagecontext",
            constraint=models.UniqueConstraint(
                fields=("role", "path_pattern"),
                condition=~models.Q(path_pattern=""),
                name="hc_unique_role_path_pattern_nonempty",
            ),
        ),
        migrations.AddIndex(
            model_name="helppagecontext",
            index=models.Index(fields=["route_name", "is_active"], name="hc_ctx_route_active"),
        ),
        migrations.AddIndex(
            model_name="helpconversation",
            index=models.Index(fields=["page_route_name", "-created_at"], name="hc_conv_route_time"),
        ),
    ]
