from django.core.management.base import BaseCommand
from moodapp.models import Country, RedditPost, FetchQueue, FetchStatus

class Command(BaseCommand):
    help = 'Reset all data in the database'

    def handle(self, *args, **kwargs):
        RedditPost.objects.all().delete()
        Country.objects.all().delete()
        FetchQueue.objects.all().delete()
        FetchStatus.objects.all().delete()
        self.stdout.write(self.style.SUCCESS('Successfully reset all data'))