from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.analytics.services import build_daily_metrics

class Command(BaseCommand):
    help='Build daily analytics metric snapshots.'
    def add_arguments(self, parser):
        parser.add_argument('--date'); parser.add_argument('--days',type=int,default=1); parser.add_argument('--today',action='store_true')
    def handle(self,*args,**opts):
        end=datetime.strptime(opts['date'],'%Y-%m-%d').date() if opts.get('date') else (timezone.localdate() if opts.get('today') else timezone.localdate()-timedelta(days=1))
        for off in range(max(1,opts['days'])-1,-1,-1):
            day=end-timedelta(days=off); r=build_daily_metrics(day); self.stdout.write(self.style.SUCCESS(f"Built analytics metrics for {day}: salons={len(r['salons'])}, staff={len(r['staff'])}, content={len(r['content'])}, search={len(r['search'])}"))
