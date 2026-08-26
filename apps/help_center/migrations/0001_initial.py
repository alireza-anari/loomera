import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("main", "0003_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="HelpCategory",
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
                    "slug",
                    models.SlugField(max_length=100, unique=True, verbose_name="اسلاگ"),
                ),
                ("title", models.CharField(max_length=160, verbose_name="عنوان")),
                (
                    "description",
                    models.TextField(blank=True, default="", verbose_name="توضیح"),
                ),
                (
                    "icon",
                    models.CharField(
                        blank=True,
                        default="fa-regular fa-circle-question",
                        max_length=100,
                        verbose_name="کلاس آیکون",
                    ),
                ),
                (
                    "audience",
                    models.CharField(
                        choices=[
                            ("all", "همه"),
                            ("customer", "مشتری"),
                            ("manager", "مدیر مجموعه"),
                            ("stylist", "متخصص"),
                        ],
                        db_index=True,
                        default="all",
                        max_length=20,
                        verbose_name="مخاطب",
                    ),
                ),
                (
                    "sort_order",
                    models.PositiveIntegerField(
                        db_index=True, default=100, verbose_name="ترتیب"
                    ),
                ),
                (
                    "is_published",
                    models.BooleanField(
                        db_index=True, default=True, verbose_name="منتشر شده"
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="ایجاد"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="بروزرسانی"),
                ),
            ],
            options={
                "verbose_name": "دسته راهنما",
                "verbose_name_plural": "دسته‌های راهنما",
                "db_table": "HC_Categories",
                "ordering": ["sort_order", "title", "id"],
            },
        ),
        migrations.CreateModel(
            name="HelpLegalDocument",
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
                    "slug",
                    models.SlugField(
                        db_index=True, max_length=120, verbose_name="اسلاگ"
                    ),
                ),
                ("title", models.CharField(max_length=220, verbose_name="عنوان")),
                ("version", models.CharField(max_length=40, verbose_name="نسخه")),
                (
                    "summary",
                    models.TextField(blank=True, default="", verbose_name="خلاصه"),
                ),
                (
                    "content",
                    models.TextField(blank=True, default="", verbose_name="متن سند"),
                ),
                (
                    "audience",
                    models.CharField(
                        choices=[
                            ("all", "همه"),
                            ("customer", "مشتری"),
                            ("manager", "مدیر مجموعه"),
                            ("stylist", "متخصص"),
                        ],
                        db_index=True,
                        default="all",
                        max_length=20,
                        verbose_name="مخاطب",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "پیش‌نویس"),
                            ("published", "منتشر شده"),
                            ("archived", "آرشیو"),
                        ],
                        db_index=True,
                        default="draft",
                        max_length=20,
                        verbose_name="وضعیت",
                    ),
                ),
                (
                    "is_current",
                    models.BooleanField(
                        db_index=True, default=False, verbose_name="نسخه جاری"
                    ),
                ),
                (
                    "effective_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="تاریخ اجرا"
                    ),
                ),
                (
                    "published_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="تاریخ انتشار"
                    ),
                ),
                (
                    "legacy_url_name",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=180,
                        verbose_name="نام URL قدیمی",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="ایجاد"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="بروزرسانی"),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_help_legal_documents",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="سازنده",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="updated_help_legal_documents",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="آخرین ویرایشگر",
                    ),
                ),
            ],
            options={
                "verbose_name": "سند حقوقی",
                "verbose_name_plural": "اسناد حقوقی",
                "db_table": "HC_LegalDocuments",
                "ordering": ["slug", "-is_current", "-published_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="HelpArticle",
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
                    "key",
                    models.CharField(
                        db_index=True,
                        help_text="مثال: manager.team یا customer.addresses",
                        max_length=140,
                        unique=True,
                        verbose_name="کلید صفحه/مقاله",
                    ),
                ),
                (
                    "slug",
                    models.SlugField(max_length=180, unique=True, verbose_name="اسلاگ"),
                ),
                ("title", models.CharField(max_length=220, verbose_name="عنوان")),
                (
                    "audience",
                    models.CharField(
                        choices=[
                            ("all", "همه"),
                            ("customer", "مشتری"),
                            ("manager", "مدیر مجموعه"),
                            ("stylist", "متخصص"),
                        ],
                        db_index=True,
                        default="all",
                        max_length=20,
                        verbose_name="مخاطب",
                    ),
                ),
                ("summary", models.TextField(verbose_name="خلاصه")),
                (
                    "body",
                    models.TextField(blank=True, default="", verbose_name="متن تکمیلی"),
                ),
                (
                    "steps",
                    models.JSONField(blank=True, default=list, verbose_name="مراحل"),
                ),
                (
                    "tips",
                    models.JSONField(blank=True, default=list, verbose_name="نکته‌ها"),
                ),
                (
                    "keywords",
                    models.TextField(
                        blank=True, default="", verbose_name="کلیدواژه‌ها"
                    ),
                ),
                (
                    "sort_order",
                    models.PositiveIntegerField(
                        db_index=True, default=100, verbose_name="ترتیب"
                    ),
                ),
                (
                    "is_published",
                    models.BooleanField(
                        db_index=True, default=True, verbose_name="منتشر شده"
                    ),
                ),
                (
                    "published_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="زمان انتشار"
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="ایجاد"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True, db_index=True, verbose_name="بروزرسانی"
                    ),
                ),
                (
                    "category",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="articles",
                        to="help_center.helpcategory",
                        verbose_name="دسته",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_help_articles",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="سازنده",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="updated_help_articles",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="آخرین ویرایشگر",
                    ),
                ),
            ],
            options={
                "verbose_name": "مقاله راهنما",
                "verbose_name_plural": "مقالات راهنما",
                "db_table": "HC_Articles",
                "ordering": ["category__sort_order", "sort_order", "title", "id"],
            },
        ),
        migrations.CreateModel(
            name="HelpConversation",
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
                    "public_id",
                    models.UUIDField(
                        db_index=True, default=uuid.uuid4, editable=False, unique=True
                    ),
                ),
                (
                    "session_key_hash",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        default="",
                        max_length=64,
                        verbose_name="هش نشست",
                    ),
                ),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("guest", "مهمان"),
                            ("customer", "مشتری"),
                            ("manager", "مدیر مجموعه"),
                            ("stylist", "متخصص"),
                        ],
                        db_index=True,
                        default="guest",
                        max_length=20,
                        verbose_name="نقش",
                    ),
                ),
                (
                    "page_key",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        default="",
                        max_length=140,
                        verbose_name="کلید صفحه",
                    ),
                ),
                (
                    "page_path",
                    models.CharField(
                        blank=True, default="", max_length=500, verbose_name="مسیر صفحه"
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "فعال"),
                            ("escalated", "ارجاع به پشتیبانی"),
                            ("closed", "بسته"),
                        ],
                        db_index=True,
                        default="active",
                        max_length=20,
                        verbose_name="وضعیت",
                    ),
                ),
                (
                    "metadata",
                    models.JSONField(blank=True, default=dict, verbose_name="متادیتا"),
                ),
                (
                    "last_message_at",
                    models.DateTimeField(
                        blank=True, db_index=True, null=True, verbose_name="آخرین پیام"
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, db_index=True, verbose_name="ایجاد"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="بروزرسانی"),
                ),
                (
                    "support_ticket",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="help_conversations",
                        to="main.supportticket",
                        verbose_name="تیکت پشتیبانی",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="help_conversations",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="کاربر",
                    ),
                ),
            ],
            options={
                "verbose_name": "گفتگوی دستیار",
                "verbose_name_plural": "گفتگوهای دستیار",
                "db_table": "HC_Conversations",
                "ordering": ["-last_message_at", "-created_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="HelpPageContext",
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
                    "page_key",
                    models.CharField(
                        db_index=True, max_length=140, verbose_name="کلید صفحه"
                    ),
                ),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("all", "همه"),
                            ("customer", "مشتری"),
                            ("manager", "مدیر مجموعه"),
                            ("stylist", "متخصص"),
                        ],
                        db_index=True,
                        default="all",
                        max_length=20,
                        verbose_name="نقش",
                    ),
                ),
                (
                    "path_pattern",
                    models.CharField(max_length=500, verbose_name="Regex مسیر"),
                ),
                (
                    "quick_prompts",
                    models.JSONField(
                        blank=True, default=list, verbose_name="سؤال‌های پیشنهادی"
                    ),
                ),
                (
                    "priority",
                    models.PositiveIntegerField(
                        db_index=True, default=100, verbose_name="اولویت تطبیق"
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        db_index=True, default=True, verbose_name="فعال"
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="ایجاد"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="بروزرسانی"),
                ),
                (
                    "article",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="page_contexts",
                        to="help_center.helparticle",
                        verbose_name="مقاله مرتبط",
                    ),
                ),
            ],
            options={
                "verbose_name": "زمینه صفحه",
                "verbose_name_plural": "زمینه‌های صفحات",
                "db_table": "HC_PageContexts",
                "ordering": ["-priority", "id"],
            },
        ),
        migrations.CreateModel(
            name="HelpMessage",
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
                    "public_id",
                    models.UUIDField(
                        db_index=True, default=uuid.uuid4, editable=False, unique=True
                    ),
                ),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("user", "کاربر"),
                            ("assistant", "دستیار"),
                            ("system", "سیستم"),
                        ],
                        db_index=True,
                        max_length=20,
                        verbose_name="نقش پیام",
                    ),
                ),
                ("content", models.TextField(verbose_name="متن پاک‌سازی‌شده")),
                ("used_ai", models.BooleanField(default=False, verbose_name="با AI")),
                (
                    "model_name",
                    models.CharField(
                        blank=True, default="", max_length=120, verbose_name="مدل"
                    ),
                ),
                (
                    "sources",
                    models.JSONField(blank=True, default=list, verbose_name="منابع"),
                ),
                (
                    "metadata",
                    models.JSONField(blank=True, default=dict, verbose_name="متادیتا"),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, db_index=True, verbose_name="ایجاد"
                    ),
                ),
                (
                    "conversation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="messages",
                        to="help_center.helpconversation",
                        verbose_name="گفتگو",
                    ),
                ),
            ],
            options={
                "verbose_name": "پیام دستیار",
                "verbose_name_plural": "پیام‌های دستیار",
                "db_table": "HC_Messages",
                "ordering": ["created_at", "id"],
            },
        ),
        migrations.CreateModel(
            name="HelpFeedback",
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
                    "rating",
                    models.CharField(
                        choices=[("helpful", "مفید"), ("not_helpful", "مفید نبود")],
                        db_index=True,
                        max_length=20,
                        verbose_name="امتیاز",
                    ),
                ),
                (
                    "note",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=500,
                        verbose_name="توضیح اختیاری",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="ایجاد"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="بروزرسانی"),
                ),
                (
                    "message",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="feedback",
                        to="help_center.helpmessage",
                        verbose_name="پاسخ دستیار",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="help_feedback",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="کاربر",
                    ),
                ),
            ],
            options={
                "verbose_name": "بازخورد دستیار",
                "verbose_name_plural": "بازخوردهای دستیار",
                "db_table": "HC_Feedback",
                "ordering": ["-updated_at", "-id"],
            },
        ),
        migrations.AddConstraint(
            model_name="helplegaldocument",
            constraint=models.UniqueConstraint(
                fields=("slug", "version"), name="hc_unique_legal_slug_version"
            ),
        ),
        migrations.AddConstraint(
            model_name="helppagecontext",
            constraint=models.UniqueConstraint(
                fields=("role", "path_pattern"), name="hc_unique_role_path_pattern"
            ),
        ),
        migrations.AddIndex(
            model_name="helpcategory",
            index=models.Index(
                fields=["audience", "is_published", "sort_order"],
                name="hc_cat_aud_pub_sort",
            ),
        ),
        migrations.AddIndex(
            model_name="helparticle",
            index=models.Index(
                fields=["audience", "is_published", "sort_order"],
                name="hc_art_aud_pub_sort",
            ),
        ),
        migrations.AddIndex(
            model_name="helparticle",
            index=models.Index(
                fields=["category", "is_published", "sort_order"],
                name="hc_art_cat_pub_sort",
            ),
        ),
        migrations.AddIndex(
            model_name="helppagecontext",
            index=models.Index(
                fields=["role", "is_active", "-priority"],
                name="hc_ctx_role_active_prio",
            ),
        ),
        migrations.AddIndex(
            model_name="helppagecontext",
            index=models.Index(
                fields=["page_key", "is_active"], name="hc_ctx_key_active"
            ),
        ),
        migrations.AddIndex(
            model_name="helplegaldocument",
            index=models.Index(
                fields=["slug", "status", "is_current"],
                name="hc_legal_slug_status_current",
            ),
        ),
        migrations.AddIndex(
            model_name="helpconversation",
            index=models.Index(
                fields=["user", "status", "-created_at"],
                name="hc_conv_user_status_time",
            ),
        ),
        migrations.AddIndex(
            model_name="helpconversation",
            index=models.Index(
                fields=["role", "status", "-created_at"],
                name="hc_conv_role_status_time",
            ),
        ),
        migrations.AddIndex(
            model_name="helpconversation",
            index=models.Index(
                fields=["page_key", "-created_at"], name="hc_conv_page_time"
            ),
        ),
        migrations.AddIndex(
            model_name="helpmessage",
            index=models.Index(
                fields=["conversation", "created_at"], name="hc_msg_conv_time"
            ),
        ),
        migrations.AddIndex(
            model_name="helpmessage",
            index=models.Index(fields=["role", "-created_at"], name="hc_msg_role_time"),
        ),
        migrations.AddIndex(
            model_name="helpfeedback",
            index=models.Index(
                fields=["rating", "-created_at"], name="hc_feedback_rating_time"
            ),
        ),
    ]
