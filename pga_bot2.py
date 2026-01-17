import tweepy
import requests
import time
import os
import json
from datetime import datetime
import pytz  # For accurate ET time; pip install pytz if not present

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
CHECK_INTERVAL_MINUTES = 5
TEST_MODE = False  # <--- Set to True for testing (prints instead of tweeting)
                  # Set to False when ready to post real tweets

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
    """Fetch golfer status from ESPN leaderboard with improved tweet formatting."""
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
                position = pos_obj.get('displayName', 'N/A')
                
                status_obj = player.get('status', {})
                thru = status_obj.get('thru', 'N/A')
                
                # Get current date in ET
                et_now = datetime.now(pytz.timezone('America/New_York'))
                date_str = et_now.strftime('%B %d, %Y')  # e.g., "January 17, 2026"
                
                # Handle N/A cases
                if position == 'N/A':
                    # Missed the cut - don't include thru info
                    update_msg = (
                        f"At the {tournament_name} today ({date_str}), "
                        f"{GOLFER_FULL_NAME} is currently {total_score} "
                        f"and missed the cut"
                    )
                elif thru == 'N/A':
                    # Has not teed off
                    update_msg = (
                        f"At the {tournament_name} today ({date_str}), "
                        f"{GOLFER_FULL_NAME} is currently {total_score} "
                        f"and has not teed off and is currently in {position}"
                    )
                else:
                    # Normal case - has position and thru info
                    update_msg = (
                        f"At the {tournament_name} today ({date_str}), "
                        f"{GOLFER_FULL_NAME} is currently {total_score} thru {thru} "
                        f"and is currently in {position}"
                    )
                return update_msg, None
        
        return None, f"{GOLFER_FULL_NAME} not found in current leaderboard."
    
    except Exception as e:
        return None, f"ESPN fetch error: {str(e)}"

print("PGA Golfer Bot (livegolfapi for events + ESPN for scores) starting...")
print(f"TEST_MODE = {TEST_MODE} → {'Will ONLY PRINT (no tweets)' if TEST_MODE else 'Will POST real tweets!'}")

# Load previous status to avoid duplicate tweets
last_known_status = load_last_status()

et_now = datetime.now(pytz.timezone('America/New_York'))
hour = et_now.hour

if 6 <= hour <= 22:  # Reasonable golf hours ET
    active_event = get_active_pga_event()
    if active_event:
        print(f"[{et_now.strftime('%Y-%m-%d %H:%M:%S ET')}] Active event: {active_event['name']} ({active_event['status']})")
        
        update_text, error = get_golfer_update_from_espn(active_event['name'])
        
        if error:
            print(f"  Error: {error}")
        elif update_text and update_text != last_known_status:
            try:
                if TEST_MODE:
                    print(f"  WOULD TWEET: {update_text}")
                else:
                    response = client.create_tweet(text=update_text[:280])
                    print(f"  TWEETED: {update_text}")
                    print(f"  Link: https://x.com/i/status/{response.data['id']}")
                
                # Save the new status
                save_last_status(update_text)
                
            except tweepy.TweepyException as e:
                print(f"  Tweet error: {e}")
        elif update_text == last_known_status:
            print(f"  Status unchanged - no tweet needed")
    else:
        print(f"[{et_now.strftime('%H:%M ET')}] No active PGA event detected.")
else:
    print(f"[{et_now.strftime('%H:%M ET')}] Outside golf hours – skipping check.")

print("Bot run complete.")
