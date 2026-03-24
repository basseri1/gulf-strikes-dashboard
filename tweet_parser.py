"""Parse tweet text to extract strike/interception data (drones, missiles, locations).

Supports multiple parse modes:
- arabic_per_incident: Saudi-style "اعتراض وتدمير N مسيّرات" per-tweet
- uae_bilingual: UAE-style bilingual with daily numbers in first line (ignore cumulative)
- count_posts: Bahrain-style where each post = 1 interception event (numbers in images only)
- keyword_filter: Filter tweets by keywords (for Israel/Iran from @TheStudyofWar)
- general_news: General news account, count posts only
"""

import re
import unicodedata
from datetime import datetime


def strip_arabic_diacritics(text: str) -> str:
    """Remove Arabic diacritics (tashkeel) for easier matching."""
    return re.sub(r'[\u0610-\u061A\u064B-\u065F\u0670]', '', text)


# ─── Drone extraction ───────────────────────────────────────────────

def extract_drone_count(text: str, first_line_only: bool = False) -> int:
    """Extract drone counts from Arabic/English tweet text."""
    src = text.split('\n')[0] if first_line_only else text
    clean = strip_arabic_diacritics(src)
    total = 0

    # Arabic: N مسيرات (plural) — also handles عدد (N) طائرات مسيرة
    for m in re.findall(r'(\d+)\s*(?:طائر[ةات]\s*)?مسير[اة]ت', clean):
        total += int(m)

    # Arabic: عدد (N) طائرات مسيرة — Kuwait-style "number (N) drones"
    if total == 0:
        for m in re.findall(r'عدد\s*\(?\s*(\d+)\s*\)?\s*طائر[ةات]', clean):
            total += int(m)

    # Arabic: N طائرة مسيرة / طائرات مسيرة
    if total == 0:
        for m in re.findall(r'(\d+)\s*طائر[ةات](?:\s+مسير)?', clean):
            total += int(m)

    # Arabic: مسيرتين (dual = 2)
    if total == 0 and re.search(r'مسيرتين', clean):
        total = 2

    # Arabic: مسيرة (singular = 1)
    if total == 0 and re.search(r'مسيرة(?!\w)', clean):
        total = 1

    # English: N UAVs / N drones
    for m in re.findall(r'(\d+)\s*UAV[s]?', src, re.IGNORECASE):
        total += int(m)
    if total == 0:
        for m in re.findall(r'(\d+)\s*drone[s]?', src, re.IGNORECASE):
            total += int(m)

    return total


# ─── Missile extraction ─────────────────────────────────────────────

def extract_missile_count(text: str, first_line_only: bool = False) -> int:
    """Extract missile counts from Arabic/English tweet text."""
    src = text.split('\n')[0] if first_line_only else text
    clean = strip_arabic_diacritics(src)
    total = 0

    # Arabic: N صواريخ (plural missiles)
    for m in re.findall(r'(\d+)\s*صوار[يى]خ', clean):
        total += int(m)

    # Arabic: عدد (N) صاروخ/صواريخ — Kuwait-style
    if total == 0:
        for m in re.findall(r'عدد\s*\(?\s*(\d+)\s*\)?\s*ص(?:اروخ|وار[يى]خ)', clean):
            total += int(m)

    # Arabic: N صاروخ (N + missile)
    if total == 0:
        for m in re.findall(r'(\d+)\s*صاروخ', clean):
            total += int(m)

    # Arabic: صاروخين (dual = 2)
    if total == 0 and re.search(r'صاروخين', clean):
        total = 2

    # Arabic: صاروخ (singular = 1) only if preceded by interception keyword
    if total == 0 and re.search(r'(?:اعتراض|تدمير).*صاروخ(?!\w)', clean):
        total = 1

    # English: N ballistic missiles / N missiles
    for m in re.findall(r'(\d+)\s*(?:ballistic\s*)?missile[s]?', src, re.IGNORECASE):
        total += int(m)
    for m in re.findall(r'(\d+)\s*cruise\s*missile[s]?', src, re.IGNORECASE):
        total += int(m)

    return total


# ─── Location extraction ────────────────────────────────────────────

LOCATION_MAP = {
    'Eastern Province': ['المنطقة الشرقية', 'Eastern Province', 'الشرقية'],
    'Riyadh': ['الرياض', 'Riyadh'],
    'Shaybah': ['شيبة', 'Shaybah', 'الربع الخالي'],
    'Prince Sultan AB': ['الأمير سلطان', 'Prince Sultan', 'الخرج', 'Al-Kharj'],
    'Diplomatic Quarter': ['الحي الدبلوماسي', 'Diplomatic Quarter'],
    'Al-Jawf': ['الجوف', 'Al-Jawf'],
    'Northern Borders': ['الحدود الشمالية', 'Northern Borders'],
    'Hafar Al-Batin': ['حفر الباطن', 'Hafar Al-Batin'],
    'Bahrain': ['البحرين', 'Bahrain'],
    'Kuwait': ['الكويت', 'Kuwait'],
    'Abu Dhabi': ['أبو ظبي', 'Abu Dhabi'],
    'Dubai': ['دبي', 'Dubai'],
    'Tehran': ['طهران', 'Tehran'],
    'Isfahan': ['أصفهان', 'Isfahan'],
    'Israel': ['إسرائيل', 'Israel'],
    'Iran': ['إيران', 'Iran'],
    'Gaza': ['غزة', 'Gaza'],
    'Lebanon': ['لبنان', 'Lebanon'],
    'Yemen': ['اليمن', 'Yemen'],
    'Houthi': ['الحوثي', 'Houthi'],
}

INTERCEPTION_KEYWORDS = [
    'اعتراض', 'تدمير', 'intercept', 'destroy', 'engaged', 'neutralize',
    'إسقاط', 'أسقط', 'تعاملت', 'الدفاع الجوي', 'air defence',
]

STRIKE_KEYWORDS = [
    'strike', 'attack', 'hit', 'bomb', 'airstrike',
    'ضرب', 'هجوم', 'غارة', 'قصف', 'استهداف', 'targeted',
]


def extract_locations(text):
    found = []
    for canonical, variants in LOCATION_MAP.items():
        for v in variants:
            if v.lower() in text.lower() or v in text:
                if canonical not in found:
                    found.append(canonical)
                break
    return found


def is_interception_tweet(text):
    text_lower = text.lower()
    return any(kw in text_lower or kw in text for kw in INTERCEPTION_KEYWORDS)


def is_strike_tweet(text):
    text_lower = text.lower()
    return any(kw in text_lower or kw in text for kw in STRIKE_KEYWORDS)


def matches_keywords(text, keywords):
    """Check if text contains any of the given keywords (case-insensitive)."""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


# ─── Parse modes ────────────────────────────────────────────────────

def parse_tweet_arabic_per_incident(tweet: dict) -> dict:
    """Saudi-style: each tweet reports one interception with specific numbers."""
    text = tweet.get("text", "")
    return {
        "drones": extract_drone_count(text),
        "missiles": extract_missile_count(text),
        "locations": extract_locations(text),
        "is_interception": is_interception_tweet(text),
        "is_strike": is_strike_tweet(text),
    }


def parse_tweet_uae_bilingual(tweet: dict) -> dict:
    """UAE-style: bilingual, daily numbers in first line, cumulative below.

    UAE posts 3 tweets per cycle: header (no nums), English detail, Arabic detail.
    To avoid double-counting, ONLY parse English tweets that start with "UAE air".
    Use first_line_only to skip cumulative totals in the body.
    """
    text = tweet.get("text", "")
    first_line = text.split('\n')[0].strip()

    # Only parse English-language detail tweets to avoid double-counting
    # These start with "UAE air defences engaged/engage..."
    if first_line.lower().startswith("uae air defence"):
        drones = extract_drone_count(text, first_line_only=True)
        missiles = extract_missile_count(text, first_line_only=True)
    else:
        # Skip Arabic duplicates and header tweets — count as 0
        drones = 0
        missiles = 0

    return {
        "drones": drones,
        "missiles": missiles,
        "locations": extract_locations(text),
        "is_interception": is_interception_tweet(text),
        "is_strike": is_strike_tweet(text),
    }


def parse_tweet_count_posts(tweet: dict) -> dict:
    """Bahrain-style: no numbers in text. Each interception post = 1 event."""
    text = tweet.get("text", "")
    is_interception = is_interception_tweet(text)
    return {
        "drones": 0,
        "missiles": 0,
        "interception_events": 1 if is_interception else 0,
        "locations": extract_locations(text),
        "is_interception": is_interception,
        "is_strike": is_strike_tweet(text),
    }


def parse_tweet_general(tweet: dict) -> dict:
    """General news — extract what we can."""
    text = tweet.get("text", "")
    return {
        "drones": extract_drone_count(text),
        "missiles": extract_missile_count(text),
        "locations": extract_locations(text),
        "is_interception": is_interception_tweet(text),
        "is_strike": is_strike_tweet(text),
    }


# ─── Main parse function ───────────────────────────────────────────

def parse_tweet(tweet: dict, parse_mode: str = "arabic_per_incident") -> dict:
    """Parse a single tweet based on the source's parse mode."""
    text = tweet.get("text", "")
    created_at = tweet.get("created_at", "")

    # Parse date
    date_str = ""
    if created_at:
        try:
            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            date_str = dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            date_str = created_at[:10] if len(created_at) >= 10 else ""

    # Dispatch to parse mode
    if parse_mode == "uae_bilingual":
        parsed = parse_tweet_uae_bilingual(tweet)
    elif parse_mode == "count_posts":
        parsed = parse_tweet_count_posts(tweet)
    elif parse_mode == "general_news":
        parsed = parse_tweet_general(tweet)
    else:  # arabic_per_incident or keyword_filter
        parsed = parse_tweet_arabic_per_incident(tweet)

    return {
        "date": date_str,
        "raw_text": text,
        "tweet_id": tweet.get("id", ""),
        "likes": tweet.get("likes", 0),
        "retweets": tweet.get("retweets", 0),
        **parsed,
    }


def filter_tweets_by_keywords(tweets: list, keywords: list) -> list:
    """Filter tweets to only those matching any of the given keywords."""
    return [t for t in tweets if matches_keywords(t.get("text", ""), keywords)]


def aggregate_daily(parsed_tweets: list, parse_mode: str = "arabic_per_incident") -> list:
    """Aggregate parsed tweets into daily summaries."""
    daily = {}

    for t in parsed_tweets:
        date = t["date"]
        if not date:
            continue

        if date not in daily:
            daily[date] = {
                "date": date,
                "drones": 0,
                "missiles": 0,
                "posts": 0,
                "interception_events": 0,
                "locations": [],
                "interceptions": 0,
                "strikes": 0,
            }

        daily[date]["drones"] += t.get("drones", 0)
        daily[date]["missiles"] += t.get("missiles", 0)
        daily[date]["posts"] += 1
        daily[date]["interception_events"] += t.get("interception_events", 0)
        if t.get("is_interception"):
            daily[date]["interceptions"] += 1
        if t.get("is_strike"):
            daily[date]["strikes"] += 1

        for loc in t.get("locations", []):
            if loc not in daily[date]["locations"]:
                daily[date]["locations"].append(loc)

    return sorted(daily.values(), key=lambda d: d["date"])


def compute_summary(daily_data: list, parse_mode: str = "arabic_per_incident") -> dict:
    """Compute overall summary statistics from daily aggregated data."""
    total_drones = sum(d["drones"] for d in daily_data)
    total_missiles = sum(d["missiles"] for d in daily_data)
    total_launched = total_drones + total_missiles
    total_posts = sum(d["posts"] for d in daily_data)
    total_interception_events = sum(d.get("interception_events", 0) for d in daily_data)
    active_days = len(daily_data)

    peak_drones = max((d["drones"] for d in daily_data), default=0)
    peak_missiles = max((d["missiles"] for d in daily_data), default=0)
    peak_day = ""
    for d in daily_data:
        if d["drones"] == peak_drones and peak_drones > 0:
            peak_day = d["date"]

    location_counts = {}
    for d in daily_data:
        for loc in d["locations"]:
            location_counts[loc] = location_counts.get(loc, 0) + 1

    date_range = ""
    if daily_data:
        date_range = f"{daily_data[0]['date']} to {daily_data[-1]['date']}"

    return {
        "total_drones": total_drones,
        "total_missiles": total_missiles,
        "total_launched": total_launched,
        "total_posts": total_posts,
        "total_interception_events": total_interception_events,
        "active_days": active_days,
        "peak_drones_day": peak_drones,
        "peak_missiles_day": peak_missiles,
        "peak_day": peak_day,
        "location_frequency": location_counts,
        "date_range": date_range,
        "parse_mode": parse_mode,
    }
