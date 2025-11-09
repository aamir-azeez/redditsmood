import praw
from django.shortcuts import render
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db.models import Count, Avg
import json
from pathlib import Path
from datetime import timedelta, datetime
import pytz
import requests
from .models import Country, RedditPost, FetchQueue, FetchStatus, UserMood

def check_emotion(titles, country):
    api_key = settings.OPENROUTER_API_KEY
    all_titles = " ".join(titles)
    prompt = f"ONLY GIVE ME ONE NUMBER BETWEEN 1 AND 10 THAT REPRESENTS THE OVERALL EMOTION OF THE FOLLOWING TEXTS: {all_titles}"

    url = "https://openrouter.ai/api/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8000",  # Optional: your site URL
        "X-Title": "Reddit Mood Analyzer",  # Optional: your app name
    }

    data = {
        "model": "google/gemini-2.5-flash-lite",  # Free Gemini model via OpenRouter
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.7,
        "max_tokens": 10,  # We only need a single number
    }

    try:
        response = requests.post(url, headers=headers, json=data)
        response_json = response.json()
        
        # Debug: print the full response
        print(f"OpenRouter API response for {country}: {response_json}")
        
        # Check for error in response
        if "error" in response_json:
            print(f"OpenRouter API error: {response_json['error']}")
            return 5  # Default neutral score
        
        # Check if choices exist
        if "choices" not in response_json or not response_json["choices"]:
            print(f"No choices in OpenRouter response for {country}")
            return 5  # Default neutral score
        
        # Extract the text
        text_output = response_json["choices"][0]["message"]["content"].strip()
        
        # Try to extract just the number
        import re
        numbers = re.findall(r'\d+', text_output)
        if numbers:
            score = int(numbers[0])
            # Clamp between 1 and 10
            return max(1, min(10, score))
        else:
            print(f"Could not parse number from: {text_output}")
            return 5
            
    except requests.exceptions.RequestException as e:
        print(f"Network error calling OpenRouter API: {e}")
        return 5
    except (KeyError, IndexError, ValueError) as e:
        print(f"Error parsing OpenRouter response: {e}")
        return 5
    except Exception as e:
        print(f"Unexpected error in check_emotion: {e}")
        return 5

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
    if created:
        # Initialize with a time that allows immediate fetching
        fetch_queue.is_fetching = False
        fetch_queue.last_fetch_time = timezone.now() - timedelta(seconds=10)
        fetch_queue.save()
    elif fetch_queue.is_fetching:
        # If it was stuck in fetching state, reset it
        time_since_last_fetch = (timezone.now() - fetch_queue.last_fetch_time).total_seconds()
        if time_since_last_fetch > 60:
            fetch_queue.is_fetching = False
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
        
        # Get user mood statistics
        user_moods = country.user_moods.all()
        user_mood_avg = user_moods.aggregate(Avg('mood_score'))['mood_score__avg']
        user_mood_count = user_moods.count()
        
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
            'user_mood_avg': round(user_mood_avg, 1) if user_mood_avg else None,
            'user_mood_count': user_mood_count,
        })
    except Country.DoesNotExist:
        return JsonResponse({
            'country': country_name,
            'subreddit': '',
            'posts': [],
            'count': 0,
            'last_updated': None,
            'emotion_score': 5,
            'user_mood_avg': None,
            'user_mood_count': 0,
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
            
            # Enforce minimum 3 second delay between fetches to avoid rate limits
            min_delay = 3.0
            if time_since_last_fetch < min_delay:
                return JsonResponse({
                    'status': 'rate_limited',
                    'wait_time': round(min_delay - time_since_last_fetch, 2),
                    'message': 'Rate limit protection active'
                })
            
            if fetch_queue.is_fetching:
                if time_since_last_fetch > 60:
                    fetch_queue.is_fetching = False
                    fetch_queue.save()
                else:
                    return JsonResponse({
                        'status': 'already_fetching',
                        'message': 'Another request is currently being processed'
                    })
            
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
@require_http_methods(["POST"])
def submit_user_mood(request):
    try:
        data = json.loads(request.body)
        country_name = data.get('country')
        mood_score = data.get('mood')
        
        if not country_name or not mood_score:
            return JsonResponse({'status': 'error', 'error': 'Missing country or mood'}, status=400)
        
        if not isinstance(mood_score, int) or mood_score < 1 or mood_score > 10:
            return JsonResponse({'status': 'error', 'error': 'Mood must be between 1 and 10'}, status=400)
        
        # Get user's IP address
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip_address = x_forwarded_for.split(',')[0]
        else:
            ip_address = request.META.get('REMOTE_ADDR')
        
        # Check for rate limiting - 5 seconds between ANY submissions from same IP
        last_submission = UserMood.objects.filter(
            ip_address=ip_address
        ).order_by('-submitted_at').first()
        
        if last_submission:
            time_since_last = (timezone.now() - last_submission.submitted_at).total_seconds()
            if time_since_last < 5:
                wait_time = 5 - time_since_last
                return JsonResponse({
                    'status': 'rate_limited',
                    'error': f'Please wait {wait_time:.1f} more seconds before submitting again',
                    'wait_time': wait_time
                }, status=429)
        
        country, created = Country.objects.get_or_create(
            name=country_name,
            defaults={'subreddit': country_name.replace(' ', '').lower()}
        )
        
        # Check if user has submitted mood for this country recently (within 24 hours)
        recent_submission = UserMood.objects.filter(
            country=country,
            ip_address=ip_address,
            submitted_at__gte=timezone.now() - timedelta(hours=24)
        ).first()
        
        if recent_submission:
            # Update existing submission
            recent_submission.mood_score = mood_score
            recent_submission.submitted_at = timezone.now()
            recent_submission.save()
        else:
            # Create new submission
            UserMood.objects.create(country=country, mood_score=mood_score, ip_address=ip_address)
        
        user_moods = country.user_moods.all()
        user_mood_avg = user_moods.aggregate(Avg('mood_score'))['mood_score__avg']
        user_mood_count = user_moods.count()
        
        return JsonResponse({
            'status': 'success',
            'country': country.name,
            'mood_score': mood_score,
            'user_mood_avg': round(user_mood_avg, 1) if user_mood_avg else None,
            'user_mood_count': user_mood_count,
        })
    except Exception as e:
        print(f"Error submitting user mood: {str(e)}")
        return JsonResponse({'status': 'error', 'error': str(e)}, status=500)
