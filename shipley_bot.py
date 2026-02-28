#!/usr/bin/env python3
"""
Neal Shipley PGA Tour Bot — Free Twitter posting via twikit.

HOW POSTING WORKS:
  twikit uses X's internal web API (the same GraphQL endpoints your browser
  uses at x.com). No paid API plan needed. Authenticates once with your
  account username + email + password, then persists session cookies in
  twikit_cookies.json. Every subsequent run just loads the cookie file —
  no login round-trip required until cookies expire, at which point the
  bot re-authenticates automatically.

  twikit_cookies.json is committed back to the repo alongside bot_state.json
  so cookies survive between GitHub Actions runs.
"""

import asyncio
import json
import os
import random
import time
from datetime import datetime
from pathlib import Path

import pytz
import requests
from twikit import Client as TwikitClient

# ── Credentials ───────────────────────────────────────────────────────────────
TWITTER_USERNAME = os.environ.get("TWITTER_USERNAME")   # e.g. NealShipleyTrak
TWITTER_EMAIL    = os.environ.get("TWITTER_EMAIL")      # account email
TWITTER_PASSWORD = os.environ.get("TWITTER_PASSWORD")   # account password

# ── Config ────────────────────────────────────────────────────────────────────
GOLFER_NAME   = "Neal Shipley"
TEST_MODE     = os.environ.get("TEST_MODE", "false").lower() == "true"
STATE_FILE    = "bot_state.json"
COOKIES_FILE  = "twikit_cookies.json"

ESPN_URL      = "https://site.api.espn.com/apis/site/v2/sports/golf/leaderboard"

UPDATE_MILESTONES = {6, 12}
HASHTAGS          = "#PGATour #Golf #NealShipley"
ET                = pytz.timezone("America/New_York")

# ── twikit client (module-level, initialised once per run) ────────────────────
_twikit: TwikitClient | None = None


async def _get_twikit() -> TwikitClient | None:
    """
    Returns an authenticated twikit client.
      • Fast path: loads cookies from twikit_cookies.json (no login needed)
      • Slow path: full login if cookies are missing or expired, then saves
        fresh cookies so the next run is fast again.
    """
    global _twikit
    if _twikit is not None:
        return _twikit

    client = TwikitClient("en-US")

    if Path(COOKIES_FILE).exists():
        try:
            client.load_cookies(COOKIES_FILE)
            print("  🍪 twikit: cookies loaded.")
            _twikit = client
            return _twikit
        except Exception as e:
            print(f"  ⚠️  twikit: cookie load failed ({e}) — re-logging in.")

    if not all([TWITTER_USERNAME, TWITTER_EMAIL, TWITTER_PASSWORD]):
        print("  ❌ twikit: TWITTER_USERNAME / TWITTER_EMAIL / TWITTER_PASSWORD not set in secrets.")
        return None

    try:
        print("  🔐 twikit: logging in…")
        await client.login(
            auth_info_1=TWITTER_USERNAME,
            auth_info_2=TWITTER_EMAIL,
            password=TWITTER_PASSWORD,
        )
        client.save_cookies(COOKIES_FILE)
        print("  ✅ twikit: login successful, cookies saved.")
        _twikit = client
        return _twikit
    except Exception as e:
        print(f"  ❌ twikit: login failed: {e}")
        return None


async def _post_async(text: str) -> bool:
    """
    Core async post.
    - Logs full exception type + message so blank errors are diagnosable.
    - On ANY failure, wipes cookies and retries once with a fresh login.
      (Not just Unauthorized/Forbidden — twikit raises various types on
      stale sessions depending on version.)
    """
    client = await _get_twikit()
    if client is None:
        return False

    try:
        tweet = await client.create_tweet(text=text)
        print(f"  ✅ Tweeted: {text}")
        print(f"  🔗 https://x.com/i/status/{tweet.id}")
        return True

    except Exception as e:
        # Log type AND repr so blank-message exceptions are visible
        print(f"  ⚠️  twikit error [{type(e).__name__}]: {repr(e)}")
        print(f"  🔄 Clearing cookies and retrying with fresh login…")

        # Wipe stale session regardless of error type
        global _twikit
        _twikit = None
        Path(COOKIES_FILE).unlink(missing_ok=True)

        # Re-authenticate and retry once
        client = await _get_twikit()
        if client is None:
            print(f"  ❌ Re-auth failed — no client.")
            return False
        try:
            tweet = await client.create_tweet(text=text)
            print(f"  ✅ Tweeted (after re-auth): {text}")
            print(f"  🔗 https://x.com/i/status/{tweet.id}")
            return True
        except Exception as e2:
            print(f"  ❌ Post failed after re-auth [{type(e2).__name__}]: {repr(e2)}")
            return False

# ── Default State Schema ──────────────────────────────────────────────────────
DEFAULT_STATE: dict = {
    "tournament":              None,   # str  – current tournament name
    "round":                   None,   # int  – current round number
    "thru":                    None,   # int  – holes completed (0–18)
    "today_score":             None,   # int  – today's score relative to par
    "total_score":             None,   # int  – tournament total relative to par
    "position":                None,   # str  – e.g. "T5", "1"
    "missed_cut":              False,  # bool
    "tee_time_tweeted_round":  None,   # int  – last round we sent a tee-time tweet for
    "round_finish_tweeted":    None,   # int  – last round we sent a finish tweet for
    "last_hole_milestone":     None,   # int  – last hole milestone (6/12) we tweeted
    "last_alert_hole":         None,   # int  – last hole we sent a score-alert tweet for
}

# ── State I/O ─────────────────────────────────────────────────────────────────

def load_state() -> dict:
    try:
        with open(STATE_FILE, "r") as f:
            saved = json.load(f)
        return {**DEFAULT_STATE, **saved}
    except (FileNotFoundError, json.JSONDecodeError):
        return DEFAULT_STATE.copy()


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ── Score Helpers ─────────────────────────────────────────────────────────────

def parse_score(raw) -> int | None:
    """
    Converts ESPN display strings to signed integers.
    'E' / 'Even' → 0 | '+3' → 3 | '-2' → -2 | None/'--' → None
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if s in ("E", "Even", "--", ""):
        return 0
    try:
        return int(s.replace("+", ""))
    except ValueError:
        return None


def fmt(score: int | None) -> str:
    """Format an int score for display: -3 → '-3', 0 → 'E', 4 → '+4'."""
    if score is None:
        return "E"
    if score == 0:
        return "E"
    return f"+{score}" if score > 0 else str(score)


def parse_position_num(pos: str | None) -> int | None:
    """'T5' → 5, '1st' → 1, 'T-12' → 12, None → None."""
    if not pos:
        return None
    cleaned = (
        pos.upper()
        .replace("T", "").replace("-", "")
        .replace("ST", "").replace("ND", "")
        .replace("RD", "").replace("TH", "")
        .strip()
    )
    try:
        return int(cleaned)
    except ValueError:
        return None


# ── API Helpers ───────────────────────────────────────────────────────────────

def fetch(url: str, params: dict | None = None, retries: int = 3, delay: float = 2.0) -> dict | None:
    """GET with exponential-ish back-off and JSON parsing."""
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            wait = delay * (attempt + 1)
            if attempt < retries - 1:
                print(f"  ⚠️  Attempt {attempt+1} failed ({exc}). Retrying in {wait:.0f}s…")
                time.sleep(wait)
            else:
                print(f"  ❌ All {retries} attempts failed: {exc}")
    return None


# ── Event Detection ───────────────────────────────────────────────────────────

def get_active_pga_event() -> dict | None:
    """
    Gets the current PGA Tour event directly from ESPN.
    LiveGolf API removed from event detection — it was timing out every single
    run and wasting 16+ seconds. ESPN returns the tournament name reliably and
    is already the source for all player data anyway.
    """
    data = fetch(ESPN_URL)
    if not data:
        return None

    events_list = data.get("events", [])
    if not events_list:
        return None

    event  = events_list[0]
    name   = event.get("name", "the tournament")

    # ESPN status can be a dict or a plain string depending on endpoint version
    raw_status = event.get("status", {})
    if isinstance(raw_status, dict):
        status_str = raw_status.get("type", {}).get("name", "unknown")
    else:
        status_str = str(raw_status)

    # Only return if competitors are present — tournament is actually running
    competitions = event.get("competitions", [])
    if not competitions or not competitions[0].get("competitors"):
        print(f"  ⚠️  ESPN shows '{name}' but no competitors yet — tournament may not have started.")
        return None

    return {"name": name, "status": status_str}


# ── ESPN Player Data ──────────────────────────────────────────────────────────

def get_player_data(tournament_name: str) -> dict | None:
    """
    Fetches and normalises all live data for GOLFER_NAME from ESPN's leaderboard.

    Returned dict fields:
        name, tournament, round (int), thru (int|None), is_live (bool),
        is_done (bool), today_score (int|None), total_score (int|None),
        position (str), tee_time (str), missed_cut (bool)
    """
    data = fetch(ESPN_URL)
    if not data:
        return None

    # ESPN returns either { events: [...] } or a flat competition; handle both.
    competitors: list = []
    for ev in data.get("events", [data]):
        for comp in ev.get("competitions", []):
            competitors.extend(comp.get("competitors", []))

    if not competitors:
        print("  ⚠️  ESPN returned no competitors")
        return None

    for player in competitors:
        athlete = player.get("athlete", {})
        name    = athlete.get("displayName", "") or athlete.get("fullName", "")
        if GOLFER_NAME.lower() not in name.lower():
            continue

        # ── Scores ────────────────────────────────────────────────────────────
        total_score = parse_score(player.get("score", {}).get("displayValue"))

        # ── Position ──────────────────────────────────────────────────────────
        position = player.get("position", {}).get("displayName", "") or ""

        # ── Status block ──────────────────────────────────────────────────────
        status_obj = player.get("status", {})
        thru_raw   = status_obj.get("thru", "")
        thru_str   = str(thru_raw).strip() if thru_raw else ""
        period     = int(status_obj.get("period", 1) or 1)
        tee_time   = status_obj.get("displayValue", "")

        # ── Today's score from linescores ─────────────────────────────────────
        linescores  = player.get("linescores", [])
        today_score = None
        if linescores and len(linescores) >= period:
            today_score = parse_score(linescores[period - 1].get("displayValue"))

        # ── Missed-cut detection ──────────────────────────────────────────────
        # ESPN signals missed cut via: status.type.name, position string, OR
        # tee_time/displayValue field containing "CUT" (seen in live output).
        CUT_SIGNALS = {"CUT", "MC", "WD", "DQ", "RTD", "MDF"}
        status_type = ""
        raw_type    = status_obj.get("type", {})
        if isinstance(raw_type, dict):
            status_type = raw_type.get("name", "").lower()
        elif isinstance(raw_type, str):
            status_type = raw_type.lower()

        missed_cut = (
            "cut" in status_type
            or position.upper() in CUT_SIGNALS
            or str(tee_time).upper().strip() in CUT_SIGNALS
        )

        # Normalise position: if ESPN sent a cut signal there, clear it so
        # tweet text doesn't say "position: CUT" awkwardly
        if position.upper() in CUT_SIGNALS:
            position = ""

        # ── Hole / live state parsing ──────────────────────────────────────────
        # thru: digit string → actively playing or just starting
        # 'F'  → round complete
        # ''   → hasn't teed off yet
        thru_int = None
        is_live  = False
        is_done  = False

        if thru_str.upper() == "F":
            thru_int = 18
            is_done  = True
        elif thru_str.isdigit():
            thru_int = int(thru_str)
            if thru_int == 18:
                is_done = True
            elif thru_int > 0:
                is_live = True
            # thru_int == 0 → on the tee / just started, treat as pre-play

        result = {
            "name":        name,
            "tournament":  tournament_name,
            "round":       period,
            "thru":        thru_int,
            "is_live":     is_live,
            "is_done":     is_done,
            "today_score": today_score,
            "total_score": total_score,
            "position":    position,
            "tee_time":    tee_time,
            "missed_cut":  missed_cut,
        }

        print(f"  📡 Player data: {result}")
        return result

    print(f"  ⚠️  {GOLFER_NAME} not found on ESPN leaderboard")
    return None


# ── Score-Change Analysis ─────────────────────────────────────────────────────

def detect_score_event(
    old_today: int | None, new_today: int | None,
    old_thru:  int | None, new_thru:  int | None,
) -> str | None:
    """
    Infer what happened on the most recently completed hole(s).
    Returns 'eagle', 'birdie_run', 'bogey', 'double+', or None.

    We only alert on eagle (≤ -2 per hole) or double+ (≥ +2 per hole) to
    avoid spamming a tweet every birdie.  A "birdie run" alert fires when
    the player goes -3 or better across two consecutive holes.
    """
    if None in (old_today, new_today, old_thru, new_thru):
        return None
    holes_played = new_thru - old_thru
    if holes_played <= 0:
        return None

    delta     = new_today - old_today          # negative = under par
    per_hole  = delta / holes_played

    if per_hole <= -2:
        return "eagle"
    if delta <= -3 and holes_played <= 2:
        return "birdie_run"
    if per_hole >= 2:
        return "double+"
    return None


# ── Tweet Templates ───────────────────────────────────────────────────────────

def _pos_flavor(pos: str | None) -> str:
    """Short momentum phrase based on current position."""
    n = parse_position_num(pos)
    if n is None:
        return "Working! 💪"
    if n == 1:
        return random.choice(["👑 Top of the leaderboard!", "🔥 Sitting in FIRST!", "⛳ Number 1 baby!", "🏆 Leading the way!"])
    if n <= 3:
        return random.choice(["🔥 Right in the mix!", "💪 Inside the top 3!", "🎯 Podium territory!"])
    if n <= 5:
        return random.choice(["🔥 Top 5 and hunting!", "⚡ Charging up the board!", "💼 Top 5 – big things loading…"])
    if n <= 10:
        return random.choice(["📈 Top 10 and climbing!", "💪 Hanging in the top 10!", "⛳ Well positioned!"])
    if n <= 20:
        return random.choice(["⚙️ Grinding into contention!", "📊 Plenty of golf left!", "💼 Room to move!"])
    return random.choice(["🔨 Never stop grinding!", "💪 Keep building!", "⛳ Stay patient – lots left!"])


def tweet_tee_time(p: dict) -> str:
    rd    = p["round"]
    tt    = p["tee_time"]
    pos   = p["position"] or ""
    total = fmt(p["total_score"])
    t     = p["tournament"]

    if rd == 1:
        opts = [
            f"⛳ Neal Shipley tees off at {tt} for Round 1 of the {t}. Let's get it! {HASHTAGS}",
            f"🏌️ It's go time. Neal Shipley starts R1 at {tt} at the {t}. {HASHTAGS}",
            f"📍 {tt} tee time for Neal Shipley – Round 1 of the {t}. Game on! {HASHTAGS}",
        ]
    elif pos:
        opts = [
            f"⏰ Round {rd} tee time: {tt}. Neal Shipley {pos} ({total}) at the {t}. {_pos_flavor(pos)} {HASHTAGS}",
            f"⛳ Neal Shipley off at {tt} in R{rd}. Sitting {pos} at {total} – {t}. {_pos_flavor(pos)} {HASHTAGS}",
            f"🏌️ {tt} start for R{rd}. Neal Shipley {pos}, {total} overall at the {t}. {HASHTAGS}",
            f"📍 R{rd} tee time locked in: {tt}. Neal Shipley {pos} ({total}) at the {t}. {HASHTAGS}",
        ]
    else:
        opts = [
            f"⛳ Round {rd} tee time: {tt} for Neal Shipley at the {t}. Currently {total}. {HASHTAGS}",
            f"🏌️ Neal Shipley tees off at {tt} in R{rd} of the {t}. Sitting at {total}. {HASHTAGS}",
        ]
    return random.choice(opts)


def tweet_score_alert(p: dict, event: str) -> str:
    """Immediate alert for eagle, birdie run, or double-bogey+."""
    hole  = p["thru"]
    today = fmt(p["today_score"])
    total = fmt(p["total_score"])
    pos   = p["position"] or "the field"
    t     = p["tournament"]

    if event == "eagle":
        opts = [
            f"🦅 EAGLE! Neal Shipley makes eagle at hole {hole}! {today} today, {total} overall. {pos} at the {t}. {HASHTAGS}",
            f"💥 EAGLE on #{hole}! Neal Shipley goes {today} today and sits at {total} total. {pos}. {t} {HASHTAGS}",
            f"🦅 Neal Shipley EAGLES hole {hole}! Moves to {today} today / {total} overall. {pos} at the {t}. {HASHTAGS}",
        ]
    elif event == "birdie_run":
        opts = [
            f"🔥 Birdie run! Neal Shipley on fire — {today} today through {hole}, {total} overall. {pos} at the {t}. {HASHTAGS}",
            f"🐦🐦 Neal Shipley is ROLLING. {today} through {hole} holes today, {total} total. {pos}. {t} {HASHTAGS}",
            f"⚡ Can't miss right now! Neal Shipley {today} today thru {hole} ({total} overall). {pos} – {t}. {HASHTAGS}",
        ]
    else:  # double+
        opts = [
            f"😤 Tough hole for Neal Shipley at #{hole}. Still hanging in at {today} today, {total} overall. {pos} – {t}. {HASHTAGS}",
            f"💪 Adversity on #{hole}. Neal Shipley {today} today, {total} total. {pos}. Plenty of golf left. {t} {HASHTAGS}",
            f"⛳ Rough patch at #{hole}, but Neal Shipley keeps fighting. {today} today / {total} overall. {pos} – {t}. {HASHTAGS}",
        ]
    return random.choice(opts)


def tweet_milestone_update(p: dict) -> str:
    """Regular update at hole 6 and 12."""
    hole  = p["thru"]
    rd    = p["round"]
    today = fmt(p["today_score"])
    total = fmt(p["total_score"])
    pos   = p["position"] or ""
    t     = p["tournament"]

    pos_tag = f"{pos} " if pos else ""

    opts = [
        f"📊 Thru {hole} | R{rd}: Neal Shipley {today} today, {total} overall. {pos_tag}at the {t}. {_pos_flavor(p['position'])} {HASHTAGS}",
        f"⛳ Through {hole} holes (R{rd}): Neal Shipley {today} today / {total} total. {pos_tag}{t}. {HASHTAGS}",
        f"🔄 R{rd} check-in – hole {hole}: {today} today | {total} overall | {pos_tag}{t}. {_pos_flavor(p['position'])} {HASHTAGS}",
        f"📍 {t} R{rd} | Thru {hole} | Neal Shipley {today} today, {total} total. {pos_tag}{HASHTAGS}",
        f"🏌️ Hole {hole} update: Neal Shipley {today} today, {total} overall. {pos_tag}– {t} R{rd}. {HASHTAGS}",
    ]
    return random.choice(opts)


def tweet_round_finish(p: dict) -> str:
    rd    = p["round"]
    today = fmt(p["today_score"])
    total = fmt(p["total_score"])
    pos   = p["position"] or ""
    t     = p["tournament"]

    # Contextual closing line based on today's score
    sc = p["today_score"] or 0
    if   sc <= -6: coda = "🔥🔥 WHAT A ROUND!"
    elif sc <= -4: coda = "🔥 Absolutely firing!"
    elif sc <= -2: coda = "✅ Solid round of golf."
    elif sc ==  0: coda = "Steady day. Let's build."
    elif sc <=  2: coda = "Grind continues. Heads up. 💪"
    else:          coda = "Tough day — reset and go. 🔨"

    pos_tag = f"{pos} " if pos else ""

    opts = [
        f"🏁 Round {rd} DONE. Neal Shipley cards {today} today. {pos_tag}{total} overall at the {t}. {coda} {HASHTAGS}",
        f"✅ R{rd} in the books. Neal Shipley: {today} today | {total} total | {pos_tag}{t}. {coda} {HASHTAGS}",
        f"📋 R{rd} wrap: Neal Shipley shoots {today}. Moves to {total} overall. {pos_tag}{t}. {coda} {HASHTAGS}",
        f"⛳ Neal Shipley posts {today} in Round {rd}. {total} overall, {pos_tag}at the {t}. {coda} {HASHTAGS}",
    ]
    return random.choice(opts)


def tweet_missed_cut(p: dict) -> str:
    total = fmt(p["total_score"])
    t     = p["tournament"]
    opts  = [
        f"⛳ Neal Shipley misses the cut at the {t} ({total}). Regroup and reload — next one is right around the corner. 💪 {HASHTAGS}",
        f"No weekend for Neal Shipley at the {t} after finishing at {total}. Head up, grind never stops. 🔨 {HASHTAGS}",
        f"Cut line gets us at the {t} ({total}). We'll be back. Neal Shipley next week! ⛳ {HASHTAGS}",
        f"Neal Shipley's week ends at the {t} ({total}). Reset, refocus, reload. Bigger things ahead. 💪 {HASHTAGS}",
    ]
    return random.choice(opts)


# ── Tweet Posting ─────────────────────────────────────────────────────────────

def post_tweet(text: str) -> bool:
    """
    Post via twikit (X's internal web API). Free, no API plan required.
    Returns True only when confirmed posted — state is never marked done
    on failure, so the next cron run retries automatically.
    """
    text = text[:280]

    if TEST_MODE:
        print(f"  🧪 [TEST] {text}")
        return True

    success = asyncio.run(_post_async(text))
    if not success:
        print("  ❌ Post failed — will retry next cron run.")
    return success


# ── Decision Engine ───────────────────────────────────────────────────────────

def decide_and_tweet(p: dict, state: dict) -> dict:
    """
    Compares live player data against persisted state and fires tweets on changes.
    Returns the updated state (caller must save it).

    Decision priority (highest → lowest):
        1. Missed cut           → tweet once
        2. Tee time             → tweet once per round when not yet started
        3. Round finish         → tweet once per round
        4. Score-change alert   → eagle / birdie run / double+ (immediate)
        5. Milestone update     → holes 6, 12 (once per milestone per round)
    """
    s = state.copy()

    # ── 1. Missed cut ─────────────────────────────────────────────────────────
    if p["missed_cut"]:
        if not s.get("missed_cut"):
            if post_tweet(tweet_missed_cut(p)):
                s["missed_cut"] = True
        return s

    # ── 2. Tee time (not yet started this round) ──────────────────────────────
    has_tee_time = p["tee_time"] and any(c.isdigit() for c in p["tee_time"])
    if has_tee_time and not p["is_live"] and not p["is_done"]:
        if s.get("tee_time_tweeted_round") != p["round"]:
            if post_tweet(tweet_tee_time(p)):
                s["tee_time_tweeted_round"] = p["round"]
        return s

    # Reset per-round counters when we enter a new round
    if s.get("round") != p["round"]:
        s["last_hole_milestone"] = None
        s["last_alert_hole"]     = None
        # Don't reset missed_cut or tee_time_tweeted_round here

    # ── 3. Round finish ───────────────────────────────────────────────────────
    if p["is_done"]:
        if s.get("round_finish_tweeted") != p["round"]:
            if post_tweet(tweet_round_finish(p)):
                s["round_finish_tweeted"]    = p["round"]
                s["last_hole_milestone"]     = 18
        # Update state to reflect finished round
        s.update({k: p.get(k) for k in ("round", "thru", "today_score", "total_score", "position", "tournament")})
        return s

    # ── 4 & 5. Actively playing ───────────────────────────────────────────────
    if p["is_live"]:
        cur_hole = p["thru"]

        # ── Score-change alert ─────────────────────────────────────────────
        event = detect_score_event(
            s.get("today_score"), p["today_score"],
            s.get("thru"),        cur_hole,
        )
        last_alert = s.get("last_alert_hole") or 0
        if event and cur_hole > last_alert:
            if post_tweet(tweet_score_alert(p, event)):
                s["last_alert_hole"] = cur_hole

        # ── Milestone update (holes 6, 12) ─────────────────────────────────
        last_milestone = s.get("last_hole_milestone") or 0
        for milestone in sorted(UPDATE_MILESTONES):
            if cur_hole >= milestone > last_milestone:
                # Avoid double-tweeting if we already sent a score alert for this exact hole
                if s.get("last_alert_hole") == cur_hole:
                    s["last_hole_milestone"] = milestone  # still mark it done
                else:
                    if post_tweet(tweet_milestone_update(p)):
                        s["last_hole_milestone"] = milestone
                break  # only one milestone tweet per cron run

    # ── Persist latest player data ────────────────────────────────────────────
    s.update({
        "tournament":  p["tournament"],
        "round":       p["round"],
        "thru":        p["thru"],
        "today_score": p["today_score"],
        "total_score": p["total_score"],
        "position":    p["position"],
    })
    return s


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 70)
    print(f"PGA TOUR BOT  |  Tracking: {GOLFER_NAME}  |  TEST_MODE={TEST_MODE}")
    print("=" * 70)

    et_now = datetime.now(ET)
    hour   = et_now.hour

    if not (6 <= hour <= 22):
        print(f"[{et_now.strftime('%H:%M ET')}] Outside golf hours (6 AM–10 PM ET) — skipping.")
        return

    state = load_state()

    event = get_active_pga_event()
    if not event:
        print(f"[{et_now.strftime('%H:%M ET')}] No active PGA event found.")
        return

    print(f"[{et_now.strftime('%Y-%m-%d %H:%M ET')}] Event: {event['name']} ({event['status']})")

    # Hard-reset state when tournament changes (new week)
    if state.get("tournament") and state["tournament"] != event["name"]:
        print(f"  🔄 New tournament detected ({event['name']}) — resetting state.")
        state = DEFAULT_STATE.copy()

    player = get_player_data(event["name"])
    if not player:
        print("  ⚠️  Could not retrieve player data. Exiting.")
        return

    new_state = decide_and_tweet(player, state)
    save_state(new_state)
    print(f"  💾 State saved.")

    print("=" * 70)
    print("Run complete.")
    print("=" * 70)


if __name__ == "__main__":
    main()
