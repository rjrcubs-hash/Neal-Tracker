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
TEST_MODE = True  # Set to False when ready to post real tweets

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

def generate_active_play_tweet(tournament_info):
    """Generate varied tweets for active play with all key stats."""
    
    tournament = tournament_info['tournament_name']
    today_score = tournament_info['today_score']
    total_score = tournament_info['total_score']
    position = tournament_info['position']
    hole = tournament_info['hole']
    round_num = tournament_info['round']
    
    # 15 different templates for active play
    templates = [
        f"Neal Shipley is {today_score} today ({total_score} overall) through {hole} holes. Currently {position} at the {tournament}.",
        f"{today_score} through {hole} for Neal Shipley at the {tournament}. Sits {position} at {total_score} overall.",
        f"Neal Shipley: {today_score} today, {total_score} total. {position} through {hole} holes at the {tournament}.",
        f"Through {hole}: Neal Shipley {today_score} in Round {round_num}. {position} overall ({total_score}) at the {tournament}.",
        f"Neal Shipley {position} at the {tournament}. {today_score} today through {hole}, {total_score} overall.",
        f"Round {round_num} update: Neal Shipley {today_score} through {hole} holes. {position} at {total_score} overall. {tournament}.",
        f"{position} at the {tournament} for Neal Shipley. {today_score} today through {hole}, {total_score} for the tournament.",
        f"Neal Shipley through {hole} holes: {today_score} today, {total_score} overall, {position} at the {tournament}.",
        f"Currently {position}: Neal Shipley is {today_score} through {hole} holes today ({total_score} total) at the {tournament}.",
        f"{tournament} update: Neal Shipley {today_score} through {hole} in Round {round_num}. {position}, {total_score} overall.",
        f"Neal Shipley sits {position} at the {tournament} after {hole} holes. {today_score} today, {total_score} for the week.",
        f"Through {hole} today: Neal Shipley {today_score} in Round {round_num}. Overall: {total_score}, {position} at the {tournament}.",
        f"{position} and counting. Neal Shipley {today_score} through {hole} today, {total_score} total at the {tournament}.",
        f"Neal Shipley {today_score} today through {hole} holes at the {tournament}. {position} overall at {total_score}.",
        f"Round {round_num}: Neal Shipley through {hole} at {today_score} today. {position} ({total_score} overall) at the {tournament}.",
    ]
    
    return random.choice(templates)

def generate_tee_time_tweet(tournament_info):
    """Generate tweet for upcoming tee time."""
    tournament = tournament_info['tournament_name']
    total_score = tournament_info['total_score']
    position = tournament_info['position']
    tee_time = tournament_info['tee_time']
    round_num = tournament_info['round']
    
    templates = [
        f"Neal Shipley tees off at {tee_time} for Round {round_num} of the {tournament}. Currently {position} at {total_score}.",
        f"Round {round_num} tee time: {tee_time} for Neal Shipley. {position} ({total_score}) at the {tournament}.",
        f"Neal Shipley starts Round {round_num} at {tee_time}. Sits {position} at {total_score} heading into today at the {tournament}.",
        f"{tee_time} tee time for Neal Shipley in Round {round_num}. Currently {position}, {total_score} at the {tournament}.",
        f"Neal Shipley {position} at {total_score} going into Round {round_num}. Tees off at {tee_time} at the {tournament}.",
    ]
    
    return random.choice(templates)

def generate_missed_cut_tweet(tournament_info):
    """Generate tweet for missed cut."""
    tournament = tournament_info['tournament_name']
    total_score = tournament_info.get('total_score', '')
    
    if total_score and total_score != 'E':
        templates = [
            f"Neal Shipley missed the cut at the {tournament}. Finished at {total_score}.",
            f"No weekend at the {tournament} for Neal Shipley after finishing at {total_score}.",
            f"Neal Shipley's {tournament} ends after missing the cut at {total_score}.",
        ]
    else:
        templates = [
            f"Neal Shipley missed the cut at the {tournament}.",
            f"No weekend golf for Neal Shipley at the {tournament}.",
            f"Neal Shipley's {tournament} ends after missing the cut.",
        ]
    
    return random.choice(templates)

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
    """Fetch golfer status from ESPN leaderboard with proper data parsing."""
    try:
        response = requests.get(BASE_ESPN, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Get competitors
        competitors = []
        if 'events' in data and data['events']:
            event = data['events'][0]
            if 'competitions' in event and event['competitions']:
                competitors = event['competitions'][0].get('competitors', [])
        
        if not competitors and 'competitions' in data and data['competitions']:
            competitors = data['competitions'][0].get('competitors', [])
        
        if not competitors:
            return None, "No competitors or active event found in ESPN data."
        
        # Get current day of week (0=Monday, 3=Thursday, 4=Friday, 5=Saturday, 6=Sunday)
        et_now = datetime.now(pytz.timezone('America/New_York'))
        day_of_week = et_now.weekday()
        
        for player in competitors:
            athlete = player.get('athlete', {})
            full_name = athlete.get('displayName', '') or athlete.get('fullName', '')
            
            if GOLFER_FULL_NAME.lower() in full_name.lower():
                # Get scores
                score_obj = player.get('score', {})
                total_score = score_obj.get('displayValue', 'E')  # Overall tournament score
                
                # Get position
                pos_obj = player.get('position', {})
                position = pos_obj.get('displayName', '')
                
                # Get status info
                status_obj = player.get('status', {})
                thru = status_obj.get('thru', '')  # Holes completed or "F" for finished
                period = status_obj.get('period', 1)  # Current round number
                
                # Get today's round score (if available in linescores)
                linescores = player.get('linescores', [])
                today_score = 'E'
                if linescores and len(linescores) >= period:
                    today_round = linescores[period - 1]
                    today_score = today_round.get('displayValue', 'E')
                
                # Get tee time if available
                tee_time = status_obj.get('displayValue', '')  # Often shows tee time like "10:30 AM"
                
                print(f"  DEBUG - Position: {position}, Thru: {thru}, Period: {period}, Today: {today_score}, Total: {total_score}")
                print(f"  DEBUG - Tee time/status: {tee_time}, Day: {day_of_week}")
                
                # SCENARIO 1: Actively playing (has position, has thru holes, thru is not "F")
                if position and thru and thru != 'F' and thru.isdigit():
                    tournament_info = {
                        'tournament_name': tournament_name,
                        'today_score': today_score,
                        'total_score': total_score,
                        'position': position,
                        'hole': thru,
                        'round': period,
                        'status': 'playing'
                    }
                    tweet = generate_active_play_tweet(tournament_info)
                    return tweet, None
                
                # SCENARIO 2: Has score and position, Thu/Fri, not currently playing (check for tee time)
                elif position and total_score and day_of_week in [3, 4]:  # Thursday or Friday
                    if tee_time and any(char.isdigit() for char in tee_time):
                        # Has a tee time
                        tournament_info = {
                            'tournament_name': tournament_name,
                            'total_score': total_score,
                            'position': position,
                            'tee_time': tee_time,
                            'round': period if thru == 'F' else period,
                            'status': 'upcoming_tee_time'
                        }
                        tweet = generate_tee_time_tweet(tournament_info)
                        return tweet, None
                    elif thru == 'F':
                        # Finished the round
                        tournament_info = {
                            'tournament_name': tournament_name,
                            'today_score': today_score,
                            'total_score': total_score,
                            'position': position,
                            'round': period,
                            'status': 'round_complete'
                        }
                        tweet = f"Neal Shipley finishes Round {period} at {today_score} ({total_score} overall). {position} at the {tournament_name}."
                        return tweet, None
                
                # SCENARIO 3: Sat/Sun with no position or tee time = missed cut
                elif day_of_week in [5, 6] and (not position or not tee_time or not any(char.isdigit() for char in tee_time)):
                    tournament_info = {
                        'tournament_name': tournament_name,
                        'total_score': total_score,
                        'status': 'missed_cut'
                    }
                    tweet = generate_missed_cut_tweet(tournament_info)
                    return tweet, None
                
                # SCENARIO 4: In field but not started yet
                else:
                    return None, f"{GOLFER_FULL_NAME} in field but no active data yet."
        
        return None, f"{GOLFER_FULL_NAME} not found in current leaderboard."
    
    except Exception as e:
        return None, f"ESPN fetch error: {str(e)}"

# === Main execution ===
print("PGA Golfer Bot (Free Template Version) starting...")
print(f"TEST_MODE = {TEST_MODE} → {'Will ONLY PRINT (no tweets)' if TEST_MODE else 'Will POST real tweets!'}")

last_known_status = load_last_status()

et_now = datetime.now(pytz.timezone('America/New_York'))
hour = et_now.hour

if 6 <= hour <= 22:  # Reasonable golf hours ET
    active_event = get_active_pga_event()
    if active_event:
        print(f"[{et_now.strftime('%Y-%m-%d %H:%M:%S ET')}] Active event: {active_event['name']} ({active_event['status']})")
        
        tweet_text, error = get_golfer_update_from_espn(active_event['name'])
        
        if error:
            print(f"  Error: {error}")
        elif tweet_text:
            # Only tweet if status has changed
            if tweet_text != last_known_status:
                try:
                    if TEST_MODE:
                        print(f"  WOULD TWEET: {tweet_text}")
                    else:
                        response = client.create_tweet(text=tweet_text[:280])
                        print(f"  TWEETED: {tweet_text}")
                        print(f"  Link: https://x.com/i/status/{response.data['id']}")
                    
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
