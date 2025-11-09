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
import requests
from .models import Country, RedditPost, FetchQueue, FetchStatus

def check_emotion(titles, country):
    api_key = settings.GEMINI_API_KEY
    all_titles = " ".join(titles)
    prompt = f"Rate the emotion of these sentences on a scale of 1 to 10, 1 (immediate end of world) 5 (x is ok) 10 (immediate utopia), consider this on the scale of {country} and not an individual, only respond with the number: '{all_titles}'"

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent"

    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json"
    }

    data = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ]
    }

    response = requests.post(url, headers=headers, json=data)
    response_json = response.json()

    text_output = response_json["candidates"][0]["content"]["parts"][0]["text"]
    return int(text_output.strip())

def dubai_posts(request):
    reddit = praw.Reddit(
        client_id=settings.REDDIT_CLIENT_ID,
        client_secret=settings.REDDIT_CLIENT_SECRET,
        user_agent=settings.REDDIT_USER_AGENT
    )
    
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
    geojson_path = Path(__file__).resolve().parent / 'templates' / 'ne_110m_admin_0_countries.geojson'
    with open(geojson_path, 'r', encoding='utf-8') as f:
        geojson_data = json.load(f)
    
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
    
    country_coords = {}
    
    for feature in geojson_data['features']:
        country_name = feature['properties']['ADMIN']
        iso_a2 = feature['properties']['ISO_A2']
        
        if iso_a2 == 'AQ':
            continue
        
        geometry = feature['geometry']
        
        if geometry['type'] == 'Polygon':
            coords = geometry['coordinates'][0]
        elif geometry['type'] == 'MultiPolygon':
            coords = geometry['coordinates'][0][0]
        else:
            continue
        
        lats = [c[1] for c in coords]
        lngs = [c[0] for c in coords]
        
        centroid_lat = sum(lats) / len(lats)
        centroid_lng = sum(lngs) / len(lngs)
        
        country_coords[country_name] = {
            'lat': centroid_lat,
            'lng': centroid_lng
        }
        
        subreddit_name = country_to_subreddit.get(country_name, country_name.replace(' ', '').lower())
        
        Country.objects.get_or_create(
            name=country_name,
            defaults={'subreddit': subreddit_name}
        )
    
    fetch_queue, created = FetchQueue.objects.get_or_create(id=1)
    if created or fetch_queue.is_fetching:
        fetch_queue.is_fetching = False
        fetch_queue.last_fetch_time = timezone.now() - timedelta(seconds=2)
        fetch_queue.save()
    
    FetchStatus.objects.get_or_create(
        pk=1,
        defaults={
            'current_country': 'Waiting...',
            'current_subreddit': '',
            'is_fetching': False
        }
    )
    
    country_subreddit_mapping = {}
    for feature in geojson_data['features']:
        country_name = feature['properties']['ADMIN']
        iso_a2 = feature['properties']['ISO_A2']
        
        if iso_a2 == 'AQ':
            continue
        
        subreddit_name = country_to_subreddit.get(country_name, country_name.replace(' ', '').lower())
        country_subreddit_mapping[country_name] = subreddit_name
    
    return render(request, 'globe_countries.html', {
        'country_subreddit_mapping': json.dumps(country_subreddit_mapping),
        'country_coords': json.dumps(country_coords)
    })

def get_country_data(request):
    country_name = request.GET.get('country')
    
    if not country_name:
        return JsonResponse({'error': 'Missing country parameter'}, status=400)
    
    try:
        country = Country.objects.get(name=country_name)
        posts = country.posts.all()[:50]
        
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
            'emotion_score': country.emotion_score,
        })
    except Country.DoesNotExist:
        return JsonResponse({
            'country': country_name,
            'subreddit': '',
            'posts': [],
            'count': 0,
            'last_updated': None,
            'emotion_score': 5,
        })

@require_http_methods(["GET"])
def get_fetch_status(request):
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
    from django.db import transaction
    
    try:
        with transaction.atomic():
            fetch_queue = FetchQueue.objects.select_for_update().get(id=1)
            
            now = timezone.now()
            time_since_last_fetch = (now - fetch_queue.last_fetch_time).total_seconds()
            
            if time_since_last_fetch < 2.0:
                return JsonResponse({
                    'status': 'rate_limited',
                    'wait_time': round(2.0 - time_since_last_fetch, 2)
                })
            
            if fetch_queue.is_fetching:
                if time_since_last_fetch > 60:
                    fetch_queue.is_fetching = False
                    fetch_queue.save()
                else:
                    return JsonResponse({'status': 'already_fetching'})
            
            fetch_queue.is_fetching = True
            fetch_queue.last_fetch_time = now
            fetch_queue.save()
        
        fetch_status = FetchStatus.objects.get(pk=1)
        
        try:
            country = Country.objects.order_by('last_updated', 'name').first()
            
            if not country:
                return JsonResponse({'status': 'no_countries'})
            
            fetch_status.current_country = country.name
            fetch_status.current_subreddit = country.subreddit
            fetch_status.is_fetching = True
            fetch_status.save()
            
            print(f"Fetching data for {country.name} (r/{country.subreddit})...")
            
            reddit = praw.Reddit(
                client_id=settings.REDDIT_CLIENT_ID,
                client_secret=settings.REDDIT_CLIENT_SECRET,
                user_agent=settings.REDDIT_USER_AGENT,
                check_for_async=False,
            )
            
            posts_data = []
            titles = []
            error_msg = None
            
            try:
                subreddit = reddit.subreddit(country.subreddit)
                
                for submission in subreddit.hot(limit=50):
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
                    
                    titles.append(submission.title)
                
                print(f"Found {len(posts_data)} posts for {country.name}")
                
                emotion_score = check_emotion(titles, country.name)
                print(f"Emotion score for {country.name}: {emotion_score}")
                
                with transaction.atomic():
                    country.posts.all().delete()
                    
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
                    
                    country.last_updated = timezone.now()
                    country.post_count = len(posts_data)
                    country.emotion_score = emotion_score
                    country.save()
                    
                    print(f"Replaced with {len(posts_data)} new posts. Emotion: {emotion_score}/10")
                
                fetch_status.is_fetching = False
                fetch_status.save()
                
                return JsonResponse({
                    'status': 'success',
                    'country': country.name,
                    'subreddit': country.subreddit,
                    'posts_fetched': len(posts_data),
                    'total_posts': country.post_count,
                    'emotion_score': emotion_score,
                })
            
            except Exception as e:
                error_msg = str(e)
                print(f"Error fetching r/{country.subreddit}: {error_msg}")
                
                country.last_updated = timezone.now()
                country.save()
                
                fetch_status.is_fetching = False
                fetch_status.save()
                
                return JsonResponse({
                    'status': 'error',
                    'country': country.name,
                    'subreddit': country.subreddit,
                    'error': error_msg
                })
        
        finally:
            fetch_queue = FetchQueue.objects.get(id=1)
            fetch_queue.is_fetching = False
            fetch_queue.save()
    
    except Exception as e:
        print(f"Critical error in fetch_next_country: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'error': str(e)
        })