import tweepy
import requests
import os
import json
import random
from datetime import datetime
import pytz

# === Your X API credentials from environment variables ===
consumer_key = os.environ.get('TWITTER_CONSUMER_KEY')
consumer_secret = os.environ.get('TWITTER_CONSUMER_SECRET')
access_token = os.environ.get('TWITTER_ACCESS_TOKEN')
access_token_secret = os.environ.get('TWITTER_ACCESS_SECRET')
LIVEGOLF_API_KEY = os.environ.get('LIVEGOLF_API_KEY')

client = tweepy.Client(
    consumer_key=consumer_key,
    consumer_secret=consumer_secret,
    access_token=access_token,
    access_token_secret=access_token_secret
)

# === Customize ===
GOLFER_FULL_NAME = "Neal Shipley"
TEST_MODE = True  # Set to True for testing (prints instead of tweeting)

STATE_FILE = 'last_status.json'
BASE_LIVEGOLF = "https://use.livegolfapi.com/v1"
BASE_ESPN = "http://site.api.espn.com/apis/site/v2/sports/golf/leaderboard"

def load_last_status():
    """Load last known status from file (persisted via git)."""
    try:
        with open(STATE_FILE, 'r') as f:
            return json.load(f).get('last_status')
    except FileNotFoundError:
        return None

def save_last_status(status):
    """Save current status to file."""
    with open(STATE_FILE, 'w') as f:
        json.dump({'last_status': status}, f)

def generate_smart_tweet(tournament_info):
    """Generate contextual tweets with smart templates - completely free."""
    
    tournament = tournament_info['tournament_name']
    score = tournament_info['score']
    position = tournament_info['position']
    thru = tournament_info['thru']
    status = tournament_info['status']
    
    # Parse score to determine tone
    score_value = 0
    if score != 'E':
        try:
            score_str = score.replace('+', '').replace('-', '')
            score_value = int(score_str)
            if score.startswith('-'):
                score_value = -score_value
        except:
            pass
    
    # Missed cut templates
    if status == 'missed_cut':
        templates = [
            f"Neal Shipley didn't make the cut at the {tournament}. Next week.",
            f"Tough week for Neal Shipley - missed the cut at the {tournament}.",
            f"Neal Shipley's {tournament} ends early after missing the weekend.",
            f"No weekend golf for Neal Shipley at the {tournament}.",
            f"Neal Shipley misses the cut at the {tournament}. On to the next one.",
        ]
        return random.choice(templates)
    
    # Not started or not teed off templates
    if status in ['not_started', 'not_teed_off']:
        templates = [
            f"Neal Shipley competing at the {tournament} this week.",
            f"Neal Shipley in the field at the {tournament}.",
            f"Following Neal Shipley at the {tournament}.",
            f"Neal Shipley tees it up at the {tournament}.",
            f"Tracking Neal Shipley's progress at the {tournament}.",
        ]
        return random.choice(templates)
    
    # Active play - vary by score performance
    if score_value <= -5:  # Playing very well
        starters = [
            "Excellent showing",
            "Strong performance",
            "Neal Shipley rolling",
            "Hot start",
            "Looking sharp"
        ]
    elif score_value <= -2:  # Playing well
        starters = [
            "Solid round",
            "Looking good",
            "Nice play",
            "Good showing",
            "Playing well"
        ]
    elif score_value >= 5:  # Struggling significantly
        starters = [
            "Tough day",
            "Grinding through it",
            "Challenging round",
            "Working through struggles",
            "Difficult conditions"
        ]
    elif score_value >= 2:  # Struggling
        starters = [
            "Battle mode",
            "Grinding",
            "Tough going",
            "Working through it",
            "Challenging day"
        ]
    else:  # Even or close to even
        starters = [
            "Update",
            "Status check",
            "Current standing",
            "Progress report",
            ""
        ]
    
    starter = random.choice(starters)
    
    # Build the tweet based on available info
    if thru and thru != 'N/A':
        # Has hole count
        if starter:
            tweet = f"{starter}: Neal Shipley {score} ({position}) through {thru} at the {tournament}."
        else:
            formats = [
                f"Neal Shipley {score} ({position}) through {thru} holes at the {tournament}.",
                f"Neal Shipley: {score}, {position} after {thru} holes at the {tournament}.",
                f"At the {tournament}: Neal Shipley {score} ({position}), {thru} holes complete.",
                f"{score}, {position} for Neal Shipley through {thru} at the {tournament}.",
            ]
            tweet = random.choice(formats)
    else:
        # No hole count
        if starter:
            tweet = f"{starter}: Neal Shipley {score}, {position} at the {tournament}."
        else:
            formats = [
                f"Neal Shipley {score}, {position} at the {tournament}.",
                f"Neal Shipley: {score} ({position}) at the {tournament}.",
                f"At the {tournament}: Neal Shipley {score}, sitting {position}.",
                f"{score}, {position} for Neal Shipley at the {tournament}.",
            ]
            tweet = random.choice(formats)
    
    return tweet

def get_active_pga_event():
    """Use livegolfapi to find current PGA event ID/name/status."""
    try:
        url = f"{BASE_LIVEGOLF}/events?api_key={LIVEGOLF_API_KEY}&tour=pga-tour"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        events = response.json()
        
        now = datetime.utcnow().isoformat() + "Z"
        
        for event in events:
            start = event.get("startDatetime")
            end = event.get("endDatetime")
            status = event.get("status", "Scheduled")
            
            if status in ["In Progress", "Paused"] or (start and end and start <= now <= end):
                return {
                    "id": event["id"],
                    "name": event["name"],
                    "status": status,
                    "course": event.get("course", "N/A")
                }
        return None
    except Exception as e:
        print(f"livegolfapi error: {e}")
        return None

def get_golfer_update_from_espn(tournament_name):
    """Fetch golfer status from ESPN leaderboard."""
    try:
        response = requests.get(BASE_ESPN, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Prefer events[0].competitions[0].competitors (most common structure)
        competitors = []
        if 'events' in data and data['events']:
            event = data['events'][0]
            if 'competitions' in event and event['competitions']:
                competitors = event['competitions'][0].get('competitors', [])
        
        if not competitors and 'competitions' in data and data['competitions']:
            competitors = data['competitions'][0].get('competitors', [])
        
        if not competitors:
            return None, "No competitors or active event found in ESPN data."
        
        for player in competitors:
            athlete = player.get('athlete', {})
            full_name = athlete.get('displayName', '') or athlete.get('fullName', '')
            if GOLFER_FULL_NAME.lower() in full_name.lower():
                score_obj = player.get('score', {})
                total_score = score_obj.get('displayValue', 'E')
                
                pos_obj = player.get('position', {})
                position = pos_obj.get('displayName', '')
                
                status_obj = player.get('status', {})
                thru = status_obj.get('thru', '')
                
                # Get current date in ET
                et_now = datetime.now(pytz.timezone('America/New_York'))
                day_of_week = et_now.weekday()  # 0=Monday, 6=Sunday
                
                # Prepare tournament info
                tournament_info = {
                    'tournament_name': tournament_name,
                    'score': total_score,
                    'position': position if position else 'N/A',
                    'thru': thru if thru else 'N/A',
                    'status': 'playing',
                    'day_of_week': day_of_week
                }
                
                # Determine what status to communicate
                if not position or position == 'N/A' or position == '':
                    # No position available
                    if day_of_week in [5, 6]:  # Saturday or Sunday (weekend rounds)
                        tournament_info['status'] = 'missed_cut'
                    else:  # Monday-Friday
                        tournament_info['status'] = 'not_started'
                elif not thru or thru == 'N/A' or thru == '':
                    tournament_info['status'] = 'not_teed_off'
                else:
                    tournament_info['status'] = 'playing'
                
                return tournament_info, None
        
        return None, f"{GOLFER_FULL_NAME} not found in current leaderboard."
    
    except Exception as e:
        return None, f"ESPN fetch error: {str(e)}"

# === Main execution ===
print("PGA Golfer Bot (Free Template Version) starting...")
print(f"TEST_MODE = {TEST_MODE} → {'Will ONLY PRINT (no tweets)' if TEST_MODE else 'Will POST real tweets!'}")

# Load previous status to avoid duplicate tweets
last_known_status = load_last_status()

et_now = datetime.now(pytz.timezone('America/New_York'))
hour = et_now.hour

if 6 <= hour <= 22:  # Reasonable golf hours ET
    active_event = get_active_pga_event()
    if active_event:
        print(f"[{et_now.strftime('%Y-%m-%d %H:%M:%S ET')}] Active event: {active_event['name']} ({active_event['status']})")
        
        tournament_info, error = get_golfer_update_from_espn(active_event['name'])
        
        if error:
            print(f"  Error: {error}")
        elif tournament_info:
            # Generate the tweet text using smart templates
            tweet_text = generate_smart_tweet(tournament_info)
            
            # Only tweet if status has changed
            if tweet_text != last_known_status:
                try:
                    if TEST_MODE:
                        print(f"  WOULD TWEET: {tweet_text}")
                    else:
                        response = client.create_tweet(text=tweet_text[:280])
                        print(f"  TWEETED: {tweet_text}")
                        print(f"  Link: https://x.com/i/status/{response.data['id']}")
                    
                    # Save the new status
                    save_last_status(tweet_text)
                    
                except tweepy.TweepyException as e:
                    print(f"  Tweet error: {e}")
            else:
                print(f"  Status unchanged - no tweet needed")
    else:
        print(f"[{et_now.strftime('%H:%M ET')}] No active PGA event detected.")
else:
    print(f"[{et_now.strftime('%H:%M ET')}] Outside golf hours – skipping check.")

print("Bot run complete.")

