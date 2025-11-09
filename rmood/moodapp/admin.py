from django.contrib import admin
from .models import Country, RedditPost, FetchQueue, FetchStatus, UserMood, UserComment

# Register your models here.
admin.site.register(Country)
admin.site.register(RedditPost)
admin.site.register(FetchQueue)
admin.site.register(FetchStatus)
admin.site.register(UserMood)
admin.site.register(UserComment)
