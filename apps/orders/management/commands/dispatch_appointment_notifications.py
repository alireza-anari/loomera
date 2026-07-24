from django.core.management.base import BaseCommand

from apps.orders.lifecycle import dispatch_due_order_reminders
from apps.orders.notification_delivery import process_queued_notifications


class Command(BaseCommand):
    help = "ارسال اعلان‌های رزرو شامل ایمیل، پیامک و یادآوری‌های موعدرسیده"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="حداکثر تعداد اعلان‌های صف برای ارسال",
        )
        parser.add_argument(
            "--include-failed",
            action="store_true",
            help="اعلان‌های ناموفق قبلی را هم دوباره تلاش کند",
        )
        parser.add_argument(
            "--skip-reminders",
            action="store_true",
            help="یادآوری‌های موعدرسیده ارسال نشوند",
        )

    def handle(self, *args, **options):
        limit = int(options["limit"] or 50)

        reminder_result = {"processed": 0, "sent": 0}

        if not options["skip_reminders"]:
            reminder_result = dispatch_due_order_reminders(limit=limit)

        delivery_result = process_queued_notifications(
            limit=limit,
            include_failed=bool(options["include_failed"]),
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Appointment notifications dispatched | "
                f"reminders={reminder_result} | deliveries={delivery_result}"
            )
        )
