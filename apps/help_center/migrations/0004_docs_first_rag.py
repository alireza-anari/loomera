from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("help_center", "0003_alter_helparticle_key"),
    ]

    operations = [
        migrations.AddField(
            model_name="helparticle",
            name="article_type",
            field=models.CharField(
                choices=[
                    ("guide", "راهنما"),
                    ("workflow", "انجام کار"),
                    ("troubleshooting", "رفع مشکل"),
                    ("faq", "پرسش پرتکرار"),
                ],
                db_index=True,
                default="guide",
                max_length=24,
                verbose_name="نوع مقاله",
            ),
        ),
        migrations.AddField(
            model_name="helparticle",
            name="aliases",
            field=models.TextField(
                blank=True,
                default="",
                help_text="هر عبارت در یک خط؛ مثال: استایلیست، آرایشگر، عضو تیم",
                verbose_name="نام‌ها و عبارت‌های مشابه",
            ),
        ),
        migrations.AddField(
            model_name="helparticle",
            name="is_featured",
            field=models.BooleanField(
                db_index=True,
                default=False,
                verbose_name="پیشنهاد ویژه",
            ),
        ),
        migrations.AddField(
            model_name="helparticle",
            name="source_refs",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="مسیر فایل/route/viewهایی که این راهنما از روی آن‌ها بازبینی شده است.",
                verbose_name="منابع داخلی مستند",
            ),
        ),
        migrations.CreateModel(
            name="HelpArticleChunk",
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
                ("position", models.PositiveIntegerField(default=0, verbose_name="ترتیب")),
                (
                    "heading",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=240,
                        verbose_name="عنوان بخش",
                    ),
                ),
                ("content", models.TextField(verbose_name="متن بخش")),
                (
                    "search_text",
                    models.TextField(blank=True, default="", verbose_name="متن جستجو"),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="ایجاد")),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True,
                        db_index=True,
                        verbose_name="بروزرسانی",
                    ),
                ),
                (
                    "article",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chunks",
                        to="help_center.helparticle",
                        verbose_name="مقاله",
                    ),
                ),
            ],
            options={
                "verbose_name": "بخش قابل جستجوی راهنما",
                "verbose_name_plural": "بخش‌های قابل جستجوی راهنما",
                "db_table": "HC_ArticleChunks",
                "ordering": ["article_id", "position", "id"],
            },
        ),
        migrations.AddIndex(
            model_name="helparticle",
            index=models.Index(
                fields=["article_type", "is_published"],
                name="hc_art_type_pub",
            ),
        ),
        migrations.AddIndex(
            model_name="helparticle",
            index=models.Index(
                fields=["audience", "is_featured", "is_published"],
                name="hc_art_aud_feat_pub",
            ),
        ),
        migrations.AddConstraint(
            model_name="helparticlechunk",
            constraint=models.UniqueConstraint(
                fields=("article", "position"),
                name="hc_unique_article_chunk_position",
            ),
        ),
        migrations.AddIndex(
            model_name="helparticlechunk",
            index=models.Index(
                fields=["article", "position"],
                name="hc_chunk_article_pos",
            ),
        ),
    ]
