import praw
from django.shortcuts import render
from django.conf import settings

# list of (country, region)
COUNTRIES = [
    ("Afghanistan", "Asia"),
    ("Albania", "Europe"),
    ("Algeria", "Africa"),
    ("American Samoa", "Oceania"),
    ("Andorra", "Europe"),
    ("Angola", "Africa"),
    ("Anguilla", "Caribbean"),
    ("Antigua and Barbuda", "Caribbean"),
    ("Argentina", "South America"),
    ("Armenia", "Asia"),
    ("Aruba", "Caribbean"),
    ("Australia", "Oceania"),
    ("Austria", "Europe"),
    ("Azerbaijan", "Asia"),
]

def countries_posts(request):
    reddit = praw.Reddit(
        client_id=settings.REDDIT_CLIENT_ID,
        client_secret=settings.REDDIT_CLIENT_SECRET,
        user_agent=settings.REDDIT_USER_AGENT,
        check_for_async=False,
    )

    results = []
    for country, region in COUNTRIES:
        # normalize subreddit name: remove spaces, replace & with 'and', remove commas
        sub_name = country.replace(" & ", "and").replace("&", "and").replace(",", "").replace(" ", "")
        try:
            subreddit = reddit.subreddit(sub_name)
            posts = []
            for submission in subreddit.new(limit=50):
                posts.append({
                    "title": submission.title,
                    "author": str(submission.author),
                    "score": submission.score,
                    "url": submission.url,
                    "permalink": f"https://reddit.com{submission.permalink}",
                    "created_utc": submission.created_utc,
                    "num_comments": submission.num_comments,
                })
            results.append({
                "country": country,
                "region": region,
                "subreddit": sub_name,
                "posts": posts,
            })
        except Exception as e:
            # store minimal error info; continue with others
            results.append({
                "country": country,
                "region": region,
                "subreddit": sub_name,
                "posts": [],
                "error": "subreddit not available or access denied",
            })

    return render(request, "countries_posts.html", {"results": results})

def dubai_posts(request):
    reddit = praw.Reddit(
        client_id=settings.REDDIT_CLIENT_ID,
        client_secret=settings.REDDIT_CLIENT_SECRET,
        user_agent=settings.REDDIT_USER_AGENT,
        check_for_async=False,
    )

    posts = []
    try:
        subreddit = reddit.subreddit("dubai")
        for submission in subreddit.new(limit=10):
            posts.append({
                "title": submission.title,
                "author": str(submission.author),
                "score": submission.score,
                "url": submission.url,
                "permalink": f"https://reddit.com{submission.permalink}",
                "created_utc": submission.created_utc,
                "num_comments": submission.num_comments,
            })
    except Exception:
        # fail quietly and show empty list in template
        posts = []

    return render(request, "dubai_posts.html", {"posts": posts})