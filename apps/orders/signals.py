from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import AppointmentEvent, OrderDetail


@receiver(post_save, sender=OrderDetail)
def create_order_detail_created_event(sender, instance: OrderDetail, created: bool, **kwargs):
    if not created:
        return
    try:
        AppointmentEvent.objects.create(
            order=instance.order,
            order_detail=instance,
            salon=instance.salon,
            stylist=instance.stylist,
            event_type=AppointmentEvent.EventType.CREATED,
            new_status=instance.lifecycle_status or "",
            note="آیتم رزرو در سیستم ثبت شد.",
            metadata={
                "date": instance.date.isoformat() if instance.date else None,
                "time": instance.time.isoformat() if instance.time else None,
                "end_time": instance.end_time.isoformat() if instance.end_time else None,
                "occupied_until": instance.occupied_until.isoformat() if instance.occupied_until else None,
            },
        )
    except Exception:
        return
