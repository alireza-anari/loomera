from django.db import models
from utils import File_Uploader


# --------------------------------------------------------------------------------------
class GroupBlog(models.Model):
    group_title = models.CharField(max_length=255, verbose_name="عنوان گروه مقاله ")

    def __str__(self):
        return self.group_title

    class Meta:
        verbose_name = "گروه مقاله "
        verbose_name_plural = "گروه های مقالات "


# --------------------------------------------------------------------------------------
class Blogs(models.Model):
    title = models.CharField(max_length=255, verbose_name="عنوان مقاله ")
    summary = models.TextField(verbose_name="توضیحات  کوتاه ")
    description = models.TextField(
        blank=True,
    )
    author = models.CharField(max_length=255, verbose_name="نویسنده")
    file_upload = File_Uploader("images", "blog")
    image = models.ImageField(
        upload_to=file_upload, verbose_name="تصویر", default="images/Blogs/default.jfif"
    )
    register_date = models.DateField(auto_now=True, verbose_name="تاریخ درج ")
    view_number = models.PositiveIntegerField(default=0, verbose_name="تعداد بازدید")
    is_active = models.BooleanField(default=False, verbose_name="وضعیت")
    group_blog = models.ForeignKey(
        GroupBlog,
        on_delete=models.CASCADE,
        verbose_name="گروه مقالات",
        related_name="groups",
        null=True,
    )
    slug = models.SlugField(max_length=255, verbose_name="اسلاگ")

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = "مقاله "
        verbose_name_plural = "مقالات "
        db_table = "B_blogs"


# ---------------------------------------------------------------------------------------
class BlogsGallery(models.Model):
    blog = models.ForeignKey(
        Blogs, on_delete=models.CASCADE, verbose_name="مقاله ", related_name="Galleries"
    )
    file_upload = File_Uploader("images", "Blogs")
    image = models.ImageField(upload_to=file_upload, verbose_name="تصویر")

    def __str__(self):
        return self.blog.title

    class Meta:
        verbose_name = "گالری مقاله "
        verbose_name_plural = "گالری مقالات"
