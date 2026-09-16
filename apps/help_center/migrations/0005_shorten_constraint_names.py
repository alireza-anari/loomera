from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ("help_center", "0004_docs_first_rag"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="helparticlechunk",
            name="hc_unique_article_chunk_position",
        ),
        migrations.AddConstraint(
            model_name="helparticlechunk",
            constraint=models.UniqueConstraint(
                fields=("article", "position"),
                name="hc_uq_article_chunk_pos",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="helppagecontext",
            name="hc_unique_role_path_pattern_nonempty",
        ),
        migrations.AddConstraint(
            model_name="helppagecontext",
            constraint=models.UniqueConstraint(
                condition=~Q(path_pattern=""),
                fields=("role", "path_pattern"),
                name="hc_uq_role_path_nonempty",
            ),
        ),
    ]
