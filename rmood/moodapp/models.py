from django.db import models
from django.utils import timezone

class Country(models.Model):
    name = models.CharField(max_length=200, unique=True)
    subreddit = models.CharField(max_length=100)
    last_updated = models.DateTimeField(null=True, blank=True)
    post_count = models.IntegerField(default=0)
    emotion_score = models.IntegerField(default=5)
    
    class Meta:
        ordering = ['last_updated']
        verbose_name_plural = "Countries"
    
    def __str__(self):
        return f"{self.name} (r/{self.subreddit})"

class RedditPost(models.Model):
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name='posts')
    title = models.TextField()
    permalink = models.URLField(max_length=500)
    score = models.IntegerField(default=0)
    num_comments = models.IntegerField(default=0)
    author = models.CharField(max_length=100)
    created_utc = models.DateTimeField()
    reddit_id = models.CharField(max_length=50, unique=True)
    fetched_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_utc']
        indexes = [
            models.Index(fields=['country', '-created_utc']),
        ]
    
    def __str__(self):
        return f"{self.title[:50]} - {self.country.name}"

class FetchQueue(models.Model):
    last_fetch_time = models.DateTimeField(default=timezone.now)
    is_fetching = models.BooleanField(default=False)
    
    class Meta:
        verbose_name_plural = "Fetch Queue"

class FetchStatus(models.Model):
    current_country = models.CharField(max_length=100, blank=True)
    current_subreddit = models.CharField(max_length=50, blank=True)
    is_fetching = models.BooleanField(default=False)
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Fetch statuses"

class UserMood(models.Model):
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name='user_moods')
    mood_score = models.IntegerField()  # 1-10
    ip_address = models.GenericIPAddressField()  # To prevent duplicate submissions
    submitted_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-submitted_at']
        indexes = [
            models.Index(fields=['country', '-submitted_at']),
            models.Index(fields=['ip_address', 'country', '-submitted_at']),
        ]
    
    def __str__(self):
        return f"{self.country.name} - Mood: {self.mood_score}/10"
