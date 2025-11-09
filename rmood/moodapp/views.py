import praw
from django.shortcuts import render
from django.conf import settings

def dubai_posts(request):
    # Initialize Reddit instance
    reddit = praw.Reddit(
        client_id=settings.REDDIT_CLIENT_ID,
        client_secret=settings.REDDIT_CLIENT_SECRET,
        user_agent=settings.REDDIT_USER_AGENT
    )
    
    # Get last 10 posts from r/dubai
    subreddit = reddit.subreddit('dubai')
    posts = []
    
    for submission in subreddit.new(limit=10):
        posts.append({
            'title': submission.title,
            'author': str(submission.author),
            'score': submission.score,
            'url': submission.url,
            'permalink': f"https://reddit.com{submission.permalink}",
            'created_utc': submission.created_utc,
            'num_comments': submission.num_comments
        })
    
    return render(request, 'dubai_posts.html', {'posts': posts})