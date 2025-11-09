from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from moodapp.models import FetchQueue, FetchStatus

class Command(BaseCommand):
    help = 'Reset the rate limiter to allow immediate fetching'

    def handle(self, *args, **kwargs):
        # Reset FetchQueue
        fetch_queue, created = FetchQueue.objects.get_or_create(id=1)
        fetch_queue.is_fetching = False
        fetch_queue.last_fetch_time = timezone.now() - timedelta(seconds=10)
        fetch_queue.save()
        
        # Reset FetchStatus
        fetch_status, created = FetchStatus.objects.get_or_create(pk=1)
        fetch_status.is_fetching = False
        fetch_status.current_country = 'Ready'
        fetch_status.current_subreddit = ''
        fetch_status.save()
        
        self.stdout.write(self.style.SUCCESS('Successfully reset rate limiter'))
        self.stdout.write(f'Last fetch time set to: {fetch_queue.last_fetch_time}')
        self.stdout.write('System is ready to fetch immediately')
