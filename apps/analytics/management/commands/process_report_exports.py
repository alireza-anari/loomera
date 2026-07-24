from django.core.management.base import BaseCommand
from apps.analytics.services import process_pending_report_exports
class Command(BaseCommand):
    help='Process pending analytics report export jobs.'
    def add_arguments(self, parser): parser.add_argument('--limit',type=int,default=10)
    def handle(self,*args,**opts):
        jobs=process_pending_report_exports(opts['limit']); self.stdout.write(self.style.SUCCESS(f'Processed {len(jobs)} report export job(s).'))
