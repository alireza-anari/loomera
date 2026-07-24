from django.contrib.gis.db import models


# --------------------------------------------------------------------
class Neighborhood(models.Model):
    name = models.CharField(max_length=100, verbose_name="نام محله")
    polygon = models.PolygonField()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "محله"
        verbose_name_plural = "محله ها "
        db_table = "Neighborhood"


# ----------------------------------------------------------------------
