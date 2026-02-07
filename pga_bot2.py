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
TEST_MODE = False  # Set to False when ready to post real tweets

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

def get_fun_commentary(position, total_score, today_score, round_num):
    """Generate fun commentary based on performance."""
    commentary = []
    
    # Extract numeric position if possible
    position_num = None
    if position and position != "in the field":
        # Handle formats like "T5", "1st", "T-12", etc.
        pos_str = position.replace('T', '').replace('-', '').replace('st', '').replace('nd', '').replace('rd', '').replace('th', '')
        try:
            position_num = int(pos_str)
        except:
            pass
    
    # Parse score (remove +/- for comparison)
    score_value = 0
    if total_score and total_score != 'E':
        try:
            score_value = int(total_score.replace('+', '').replace('-', ''))
            if '-' in total_score:
                score_value = -score_value
        except:
            pass
    
    # Position-based commentary
    if position_num:
        if position_num == 1:
            commentary.extend([
                "🏆 Leading the way!",
                "👑 Top of the leaderboard!",
                "🔥 In first place!",
                "⛳ Summit secured!",
                "💪 Holding down #1!",
                "🎯 That's how you do it!",
                "🔝 Can't get better than this!",
                "⭐ Number 1 baby!"
            ])
        elif position_num <= 5:
            commentary.extend([
                "🔥 In the mix!",
                "👀 Hunting for the lead!",
                "💪 Top 5 territory!",
                "⚡ Charging up the board!",
                "🎯 Right in contention!",
                "🚀 Making a run!",
                "💼 Business is good!",
                "👊 Sunday charge loading..."
            ])
        elif position_num <= 10:
            commentary.extend([
                "📈 Solid position!",
                "💼 Right where we want to be!",
                "🎯 Top 10 watch!",
                "⛳ Making moves!",
                "👊 Hanging around the top!",
                "🔨 Building momentum!",
                "💪 Steady climbing!",
                "📊 Looking good out there!"
            ])
        elif position_num <= 20:
            commentary.extend([
                "📊 Steady climbing!",
                "⛳ Building something here!",
                "🔨 Grinding!",
                "💪 Working into position!",
                "👀 Room to move!",
                "⚙️ Lots of golf left!",
                "🎯 Patience is key!",
                "💼 Putting in the work!"
            ])
        elif position_num <= 30:
            commentary.extend([
                "⚙️ Putting in work!",
                "🛠️ Building a round!",
                "📈 Plenty of holes left!",
                "⛳ Staying patient!",
                "💼 Battle mode engaged!",
                "🔧 Working through it!",
                "💪 Grind don't stop!",
                "⚡ Making it happen!"
            ])
        else:
            commentary.extend([
                "⛳ Keep fighting!",
                "💪 Never give up!",
                "🔨 Grinding through!",
                "🎯 Finding the rhythm!",
                "⚙️ Building blocks!",
                "💼 Working on it!",
                "🔧 Staying positive!"
            ])
    
    # Score-based commentary
    if score_value < 0:  # Under par
        if score_value <= -8:
            commentary.extend([
                "🔥🔥🔥 UNCONSCIOUS!",
                "🚨 BIRDIE FEST! 🚨",
                "📢 SOMEBODY STOP HIM!",
                "🎰 Everything's dropping!",
                "⛳ Can't miss right now!"
            ])
        elif score_value <= -5:
            commentary.extend([
                "🔥🔥🔥",
                "Birdie machine mode!",
                "The putter is HOT! 🔥",
                "Going LOW!",
                "Red numbers all day!",
                "🐦🐦🐦 Birdie party!",
                "⛳ Dialed in!",
                "🎯 Locked in!"
            ])
        elif score_value <= -2:
            commentary.extend([
                "Making birdies! 🐦",
                "Rolling in putts! ⛳",
                "Under par and moving! 📉",
                "Red numbers! 🔴",
                "Clean golf! 💯",
                "🎯 Steady rounds!",
                "💪 Solid play!",
                "⛳ Finding greens!"
            ])
    elif score_value > 0:  # Over par
        if score_value >= 5:
            commentary.extend([
                "Tough day at the office 😤",
                "Battle mode! 💪",
                "Grinding it out!",
                "Character building round!",
                "Not giving up! 🔨",
                "⛳ Stay patient!",
                "💼 Work to do!",
                "🔧 Fixing things!"
            ])
        elif score_value >= 2:
            commentary.extend([
                "Finding his way back! 🎯",
                "Stay patient! ⛳",
                "Recovery mode! 🔧",
                "Plenty of golf left!",
                "The comeback is ON! 💪",
                "🔨 Building back!",
                "💼 Staying focused!",
                "⚡ Working through it!"
            ])
    
    # Today's round specific commentary
    if today_score and today_score != 'E':
        try:
            today_val = int(today_score.replace('+', '').replace('-', ''))
            if '-' in today_score:
                if today_val >= 5:
                    commentary.extend([
                        "🔥 Hot round today!",
                        "🚀 Going deep today!",
                        "⛳ On FIRE today!",
                        "💥 Explosive round!",
                        "📢 LIGHTS OUT today!"
                    ])
                elif today_val >= 3:
                    commentary.extend([
                        "🔥 Heating up!",
                        "🎯 Dialing it in!",
                        "⛳ Rolling today!",
                        "💪 Great rhythm today!"
                    ])
            elif '+' in today_score:
                if today_val >= 4:
                    commentary.extend([
                        "💪 Battling hard today!",
                        "🔨 Tough grind today!",
                        "⛳ Shake it off!",
                        "💼 Adversity check!"
                    ])
                elif today_val >= 2:
                    commentary.extend([
                        "⚙️ Grinding today!",
                        "💪 Working through it!",
                        "🔧 Finding it!",
                        "⛳ Stay patient!"
                    ])
        except:
            pass
    
    # Weekend/Round specific commentary
    if round_num == 4:
        commentary.extend([
            "🏁 Final round!",
            "💼 Sunday funday!",
            "🎯 Finish strong!",
            "⛳ Last push!"
        ])
    elif round_num == 3:
        commentary.extend([
            "📊 Moving day!",
            "💪 Saturday charge!",
            "🔥 Make a move!"
        ])
    
    return random.choice(commentary) if commentary else ""

def generate_active_play_tweet(tournament_info):
    """Generate varied tweets for active play with all key stats AND fun commentary."""
    
    tournament = tournament_info['tournament_name']
    today_score = tournament_info['today_score']
    total_score = tournament_info['total_score']
    position = tournament_info['position']
    hole = tournament_info['hole']
    round_num = tournament_info['round']
    
    # Get fun commentary
    commentary = get_fun_commentary(position, total_score, today_score, round_num)
    
    # Check if we have a real position or placeholder
    has_position = position and position != "in the field"
    
    if has_position:
        # Core stat message
        core_templates = [
            f"Neal Shipley {position} at the {tournament}. {today_score} today through {hole} ({total_score} overall).",
            f"{position} through {hole} holes! Neal: {today_score} today, {total_score} overall at the {tournament}.",
            f"Round {round_num} update: Neal Shipley {position}, {today_score} through {hole} ({total_score} total) at the {tournament}.",
            f"Neal Shipley sits {position} at {total_score} overall. {today_score} today through {hole} at the {tournament}.",
            f"{tournament}: Neal Shipley {position} at {total_score}. Through {hole} holes at {today_score} today.",
            f"Currently {position}: Neal {today_score} through {hole} today, {total_score} overall at the {tournament}.",
            f"Neal Shipley {today_score} today through {hole} holes. {position} ({total_score}) at the {tournament}.",
            f"{position}! Neal Shipley at {total_score} total, {today_score} through {hole} today at the {tournament}.",
            f"Neal sits {position} at the {tournament} ({total_score}). {today_score} today through {hole} in R{round_num}.",
        ]
    else:
        # Core stat message without position
        core_templates = [
            f"Neal Shipley {today_score} today ({total_score} overall) through {hole} holes at the {tournament}.",
            f"Through {hole} holes: Neal Shipley {today_score} today, {total_score} total at the {tournament}.",
            f"Round {round_num}: Neal {today_score} through {hole} ({total_score} overall) at the {tournament}.",
            f"Neal Shipley at {total_score} overall. {today_score} today through {hole} at the {tournament}.",
            f"{tournament}: Neal Shipley through {hole} holes. {today_score} today, {total_score} total.",
            f"Neal: {today_score} through {hole} today at the {tournament}. {total_score} total in R{round_num}.",
        ]
    
    base_tweet = random.choice(core_templates)
    
    # Add commentary if we have it
    if commentary:
        return f"{base_tweet} {commentary}"
    else:
        return base_tweet

def generate_tee_time_tweet(tournament_info):
    """Generate tweet for upcoming tee time with excitement."""
    tournament = tournament_info['tournament_name']
    total_score = tournament_info['total_score']
    position = tournament_info['position']
    tee_time = tournament_info['tee_time']
    round_num = tournament_info['round']
    
    # Get some contextual flair
    flair = []
    
    # Parse position for context
    position_num = None
    if position and position != "in the field":
        pos_str = position.replace('T', '').replace('-', '').replace('st', '').replace('nd', '').replace('rd', '').replace('th', '')
        try:
            position_num = int(pos_str)
        except:
            pass
    
    if position_num:
        if position_num <= 5:
            flair.extend(["Let's get it! 🔥", "Time to make a move! ⛳", "Here we go! 💪", "Game time! 🎯"])
        elif position_num <= 10:
            flair.extend(["Let's climb! 📈", "Moving day! 🚀", "Time to work! 💼", "Let's go! ⛳"])
        else:
            flair.extend(["Let's make something happen! 💪", "Time to grind! 🔨", "Here we go! ⛳", "Let's work! 💼"])
    
    if round_num == 4:
        flair.extend(["Final round! 🏁", "Sunday vibes! ☀️", "Finish strong! 💪"])
    elif round_num == 3:
        flair.extend(["Moving day! 📊", "Saturday charge! ⚡", "Make a move! 🚀"])
    elif round_num == 1:
        flair.extend(["Let's go! ⛳", "Here we go! 🔥", "Tournament time! 🎯", "Game on! 💪"])
    
    # Handle different scenarios
    if round_num == 1:
        # Round 1 - no position yet
        templates = [
            f"Neal Shipley tees off at {tee_time} for Round 1 of the {tournament}.",
            f"Round 1 tee time: {tee_time} for Neal Shipley at the {tournament}.",
            f"Neal Shipley starts his week at {tee_time} in Round 1. {tournament}.",
            f"{tee_time} tee time for Neal Shipley! Round 1 of the {tournament}.",
            f"⛳ {tee_time} start for Neal Shipley at the {tournament}. Round 1!",
        ]
    elif position == "in the field" or not position:
        # Has played but position not showing
        templates = [
            f"Neal Shipley tees off at {tee_time} for Round {round_num} of the {tournament}. Currently at {total_score}.",
            f"Round {round_num} tee time: {tee_time} for Neal Shipley ({total_score}) at the {tournament}.",
            f"Neal Shipley starts Round {round_num} at {tee_time}. Sits at {total_score} at the {tournament}.",
            f"{tee_time} tee time for Neal Shipley in Round {round_num} ({total_score}) at the {tournament}.",
        ]
    else:
        # Has position and prior score
        templates = [
            f"Neal Shipley tees off at {tee_time} for Round {round_num} of the {tournament}. Currently {position} at {total_score}.",
            f"Round {round_num} tee time: {tee_time} for Neal Shipley. {position} ({total_score}) at the {tournament}.",
            f"Neal Shipley starts Round {round_num} at {tee_time}. Sits {position} at {total_score} heading into today at the {tournament}.",
            f"{tee_time} tee time for Neal Shipley in Round {round_num}. Currently {position}, {total_score} at the {tournament}.",
            f"Neal Shipley {position} at {total_score} going into Round {round_num}. Tees off at {tee_time} at the {tournament}.",
            f"⛳ {tee_time} start for Neal Shipley! Round {round_num} at the {tournament}. {position}, {total_score}.",
        ]
    
    base_tweet = random.choice(templates)
    
    if flair:
        return f"{base_tweet} {random.choice(flair)}"
    else:
        return base_tweet

def generate_missed_cut_tweet(tournament_info):
    """Generate tweet for missed cut with grace and forward-looking attitude."""
    tournament = tournament_info['tournament_name']
    total_score = tournament_info.get('total_score', '')
    
    if total_score and total_score != 'E':
        templates = [
            f"Neal Shipley missed the cut at the {tournament}. Finished at {total_score}. On to the next one! ⛳",
            f"No weekend at the {tournament} for Neal Shipley after finishing at {total_score}. We'll get 'em next week! 💪",
            f"Neal Shipley's {tournament} ends after missing the cut at {total_score}. Regroup and reload! 🎯",
            f"Cut line claimed Neal Shipley at the {tournament} ({total_score}). Back to work! 🔨",
            f"{tournament} ends early for Neal Shipley ({total_score}). Next week is a new opportunity! ⛳",
        ]
    else:
        templates = [
            f"Neal Shipley missed the cut at the {tournament}. On to the next! ⛳",
            f"No weekend golf for Neal Shipley at the {tournament}. We'll be back! 💪",
            f"Neal Shipley's {tournament} ends after missing the cut. Reset and reload! 🔨",
            f"Cut line got us at the {tournament}. Next one up! 🎯",
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
                thru_raw = status_obj.get('thru', '')  # Holes completed or "F" for finished
                thru = str(thru_raw) if thru_raw else ''  # Convert to string for consistency
                period = status_obj.get('period', 1)  # Current round number
                
                # Get today's round score (if available in linescores)
                linescores = player.get('linescores', [])
                today_score = 'E'
                if linescores and len(linescores) >= period:
                    today_round = linescores[period - 1]
                    today_score = today_round.get('displayValue', 'E')
                
                # Get tee time if available
                tee_time = status_obj.get('displayValue', '')  # Often shows tee time like "10:30 AM"
                
                print(f"  DEBUG - Position: '{position}', Thru: '{thru}', Period: {period}, Today: {today_score}, Total: {total_score}")
                print(f"  DEBUG - Tee time/status: '{tee_time}', Day: {day_of_week} (0=Mon, 3=Thu, 4=Fri, 5=Sat, 6=Sun)")
                print(f"  DEBUG - Linescores available: {len(linescores) if linescores else 0}")
                
                # SCENARIO 1: Actively playing (has thru holes, thru is not "F")
                # Position might be temporarily missing during live play
                if thru and thru != 'F' and thru.isdigit():
                    # Use position if available, otherwise use a placeholder
                    display_position = position if position else "in the field"
                    
                    tournament_info = {
                        'tournament_name': tournament_name,
                        'today_score': today_score,
                        'total_score': total_score,
                        'position': display_position,
                        'hole': thru,
                        'round': period,
                        'status': 'playing'
                    }
                    tweet = generate_active_play_tweet(tournament_info)
                    return tweet, None
                
                # SCENARIO 2: Has tee time showing (not started yet or between rounds)
                # This covers Thu/Fri/Sat/Sun morning before they tee off
                elif tee_time and any(char.isdigit() for char in tee_time) and thru != 'F':
                    # Determine what round they're about to play
                    next_round = period
                    
                    # If they finished previous round (thru == 'F' from previous check would have caught it)
                    # and have a tee time, they're starting next round
                    
                    # For Round 1 (Thursday), total_score might be 'E' and position might be empty
                    display_total = total_score if total_score and total_score != 'E' else 'E'
                    display_position = position if position else "in the field"
                    
                    tournament_info = {
                        'tournament_name': tournament_name,
                        'total_score': display_total,
                        'position': display_position,
                        'tee_time': tee_time,
                        'round': next_round,
                        'status': 'upcoming_tee_time'
                    }
                    tweet = generate_tee_time_tweet(tournament_info)
                    return tweet, None
                
                # SCENARIO 3: Finished a round (thru == 'F')
                elif thru == 'F':
                    # Finished the round - use active play template with commentary
                    tournament_info = {
                        'tournament_name': tournament_name,
                        'today_score': today_score,
                        'total_score': total_score,
                        'position': position,
                        'hole': '18',  # Finished
                        'round': period,
                        'status': 'round_complete'
                    }
                    
                    commentary = get_fun_commentary(position, total_score, today_score, period)
                    base_tweet = f"Neal Shipley finishes Round {period} at {today_score} ({total_score} overall). {position} at the {tournament_name}."
                    
                    if commentary:
                        tweet = f"{base_tweet} {commentary}"
                    else:
                        tweet = base_tweet
                    
                    return tweet, None
                
                # SCENARIO 4: Sat/Sun with no position or tee time = missed cut
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
print("PGA Golfer Bot (Enhanced Edition) starting...")
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
            print(f"  Generated tweet: {tweet_text}")
            print(f"  Last known status: {last_known_status}")
            
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
                print(f"  Tweet would be: {tweet_text}")
        else:
            print(f"  No tweet generated - tweet_text is None or empty")
    else:
        print(f"[{et_now.strftime('%H:%M ET')}] No active PGA event detected.")
else:
    print(f"[{et_now.strftime('%H:%M ET')}] Outside golf hours – skipping check.")

print("Bot run complete.")
