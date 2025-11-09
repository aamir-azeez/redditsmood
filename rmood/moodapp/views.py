import praw
from django.shortcuts import render
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db.models import Count
import json
from pathlib import Path
from datetime import timedelta, datetime
import pytz
from .models import Country, RedditPost, FetchQueue

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

def globe_countries(request):
    # Load GeoJSON to get all countries
    geojson_path = Path(__file__).resolve().parent / 'templates' / 'ne_110m_admin_0_countries.geojson'
    with open(geojson_path, 'r', encoding='utf-8') as f:
        geojson_data = json.load(f)
    
    # Map country names to subreddit names
    country_to_subreddit = {
        'United States of America': 'UnitedStates',
        'United Kingdom': 'UnitedKingdom',
        'United Arab Emirates': 'dubai',
        'Australia': 'australia',
        'Canada': 'canada',
        'Germany': 'germany',
        'France': 'france',
        'India': 'india',
        'Japan': 'japan',
        'China': 'china',
        'Brazil': 'brazil',
        'Mexico': 'mexico',
        'Italy': 'italy',
        'Spain': 'spain',
        'South Korea': 'korea',
        'Netherlands': 'thenetherlands',
        'Switzerland': 'switzerland',
        'Sweden': 'sweden',
        'Norway': 'norway',
        'Denmark': 'denmark',
        'Finland': 'finland',
        'Poland': 'poland',
        'Belgium': 'belgium',
        'Austria': 'austria',
        'Greece': 'greece',
        'Portugal': 'portugal',
        'Ireland': 'ireland',
        'New Zealand': 'newzealand',
        'Singapore': 'singapore',
        'Thailand': 'thailand',
        'Vietnam': 'vietnam',
        'Philippines': 'philippines',
        'Indonesia': 'indonesia',
        'Malaysia': 'malaysia',
        'Turkey': 'turkey',
        'Russia': 'russia',
        'South Africa': 'southafrica',
        'Egypt': 'egypt',
        'Argentina': 'argentina',
        'Chile': 'chile',
        'Colombia': 'colombia',
        'Peru': 'peru',
        'Pakistan': 'pakistan',
        'Bangladesh': 'bangladesh',
        'Israel': 'israel',
        'Saudi Arabia': 'saudiarabia',
    }
    
    # Initialize countries in database if they don't exist
    for feature in geojson_data['features']:
        country_name = feature['properties']['ADMIN']
        iso_a2 = feature['properties']['ISO_A2']
        
        if iso_a2 == 'AQ':  # Skip Antarctica
            continue
        
        subreddit_name = country_to_subreddit.get(country_name, country_name.replace(' ', '').lower())
        
        Country.objects.get_or_create(
            name=country_name,
            defaults={'subreddit': subreddit_name}
        )
    
    # Initialize FetchQueue if it doesn't exist
    fetch_queue, created = FetchQueue.objects.get_or_create(id=1)
    if created or fetch_queue.is_fetching:
        # Reset if stuck
        fetch_queue.is_fetching = False
        fetch_queue.last_fetch_time = timezone.now() - timedelta(seconds=2)
        fetch_queue.save()
    
    # Send country to subreddit mapping to frontend
    country_subreddit_mapping = {}
    for feature in geojson_data['features']:
        country_name = feature['properties']['ADMIN']
        iso_a2 = feature['properties']['ISO_A2']
        
        if iso_a2 == 'AQ':
            continue
        
        subreddit_name = country_to_subreddit.get(country_name, country_name.replace(' ', '').lower())
        country_subreddit_mapping[country_name] = subreddit_name
    
    return render(request, 'globe_countries.html', {
        'country_subreddit_mapping': json.dumps(country_subreddit_mapping)
    })

def get_country_data(request):
    """Get cached country data from database"""
    country_name = request.GET.get('country')
    
    if not country_name:
        return JsonResponse({'error': 'Missing country parameter'}, status=400)
    
    try:
        country = Country.objects.get(name=country_name)
        posts = country.posts.all()[:50]  # Get all posts (max 50)
        
        return JsonResponse({
            'country': country.name,
            'subreddit': country.subreddit,
            'posts': [{
                'title': post.title,
                'score': post.score,
                'permalink': post.permalink,
                'num_comments': post.num_comments,
                'author': post.author,
            } for post in posts],
            'count': posts.count(),
            'last_updated': country.last_updated.isoformat() if country.last_updated else None,
        })
    except Country.DoesNotExist:
        return JsonResponse({
            'country': country_name,
            'subreddit': '',
            'posts': [],
            'count': 0,
            'last_updated': None
        })

@require_http_methods(["GET"])
def get_fetch_status(request):
    """Return the current fetch status (which country is being fetched next)"""
    from .models import FetchStatus  # Assuming you have a FetchStatus model
    
    try:
        status = FetchStatus.objects.first()
        if status:
            return JsonResponse({
                'next_country': status.current_country,
                'next_subreddit': status.current_subreddit,
                'is_fetching': status.is_fetching
            })
        else:
            return JsonResponse({
                'next_country': 'Waiting...',
                'next_subreddit': '',
                'is_fetching': False
            })
    except Exception as e:
        return JsonResponse({
            'next_country': 'Error',
            'next_subreddit': '',
            'is_fetching': False
        })

def fetch_next_country(request):
    """Fetch Reddit data for the next country in queue (rate limited to 1 per second)"""
    from django.db import transaction
    
    try:
        # Use select_for_update to prevent race conditions
        with transaction.atomic():
            fetch_queue = FetchQueue.objects.select_for_update().get(id=1)
            
            now = timezone.now()
            time_since_last_fetch = (now - fetch_queue.last_fetch_time).total_seconds()
            
            # Rate limit check
            if time_since_last_fetch < 1.0:
                return JsonResponse({
                    'status': 'rate_limited',
                    'wait_time': round(1.0 - time_since_last_fetch, 2)
                })
            
            # Check if another process is fetching
            if fetch_queue.is_fetching:
                # Check if it's been stuck for more than 30 seconds
                if time_since_last_fetch > 30:
                    fetch_queue.is_fetching = False
                    fetch_queue.save()
                else:
                    return JsonResponse({'status': 'already_fetching'})
            
            # Mark as fetching
            fetch_queue.is_fetching = True
            fetch_queue.last_fetch_time = now
            fetch_queue.save()
        
        try:
            # Get the country that was updated least recently (continuously cycle)
            country = Country.objects.order_by('last_updated', 'name').first()
            
            if not country:
                return JsonResponse({'status': 'no_countries'})
            
            print(f"Fetching data for {country.name} (r/{country.subreddit})...")
            
            # Initialize Reddit
            reddit = praw.Reddit(
                client_id=settings.REDDIT_CLIENT_ID,
                client_secret=settings.REDDIT_CLIENT_SECRET,
                user_agent=settings.REDDIT_USER_AGENT,
                check_for_async=False,
            )
            
            posts_data = []
            error_msg = None
            
            try:
                subreddit = reddit.subreddit(country.subreddit)
                
                # Fetch 50 newest posts
                for submission in subreddit.new(limit=50):
                    # Convert Unix timestamp to timezone-aware datetime
                    created_dt = datetime.fromtimestamp(submission.created_utc, tz=pytz.UTC)
                    
                    posts_data.append({
                        'reddit_id': submission.id,
                        'title': submission.title,
                        'score': submission.score,
                        'permalink': f"https://reddit.com{submission.permalink}",
                        'num_comments': submission.num_comments,
                        'author': str(submission.author),
                        'created_utc': created_dt,
                    })
                
                print(f"Found {len(posts_data)} posts for {country.name}")
                
                # Replace all posts for this country with new ones
                with transaction.atomic():
                    # Delete all existing posts for this country
                    country.posts.all().delete()
                    
                    # Add new posts
                    for post_data in posts_data:
                        RedditPost.objects.create(
                            country=country,
                            reddit_id=post_data['reddit_id'],
                            title=post_data['title'],
                            score=post_data['score'],
                            permalink=post_data['permalink'],
                            num_comments=post_data['num_comments'],
                            author=post_data['author'],
                            created_utc=post_data['created_utc'],
                        )
                    
                    # Update country metadata
                    country.last_updated = timezone.now()
                    country.post_count = len(posts_data)
                    country.save()
                    
                    print(f"Replaced with {len(posts_data)} new posts. Total: {country.post_count}")
                
                return JsonResponse({
                    'status': 'success',
                    'country': country.name,
                    'subreddit': country.subreddit,
                    'posts_fetched': len(posts_data),
                    'total_posts': country.post_count,
                })
            
            except Exception as e:
                error_msg = str(e)
                print(f"Error fetching r/{country.subreddit}: {error_msg}")
                
                # Still update the country so we don't keep retrying failed ones immediately
                country.last_updated = timezone.now()
                country.save()
                
                return JsonResponse({
                    'status': 'error',
                    'country': country.name,
                    'subreddit': country.subreddit,
                    'error': error_msg
                })
        
        finally:
            # Always release the lock
            fetch_queue = FetchQueue.objects.get(id=1)
            fetch_queue.is_fetching = False
            fetch_queue.save()
    
    except Exception as e:
        print(f"Critical error in fetch_next_country: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'error': str(e)
        })