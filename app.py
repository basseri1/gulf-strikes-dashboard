"""Flask application for the Gulf & Middle East Strikes Analytics Dashboard."""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template

import config
from image_analyzer import extract_from_tweet_images, get_claude_client
from tweet_parser import (
    aggregate_daily, compute_summary, filter_tweets_by_keywords, parse_tweet,
)
from twitter_client import TwitterClient

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)

ANALYTICS_CACHE = Path(__file__).parent / "cache" / "analytics.json"
RAW_TWEETS_CACHE = Path(__file__).parent / "cache" / "raw_tweets.json"
ANALYTICS_CACHE.parent.mkdir(exist_ok=True)

bearer_token = os.getenv("TWITTER_BEARER_TOKEN", "")
twitter = TwitterClient(bearer_token) if bearer_token and bearer_token != "your_bearer_token_here" else None
claude_client = get_claude_client()


def load_cache(filepath: Path) -> dict:
    if filepath.exists():
        with open(filepath, "r") as f:
            return json.load(f)
    return {}


def save_cache(filepath: Path, data: dict):
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2, default=str)


def _aggregate_cumulative(parsed_tweets: list) -> list:
    """Aggregate tweets with cumulative totals (like Bahrain).

    Each tweet's image shows the running total. We take the max per day,
    then compute daily deltas to get per-day counts.
    """
    daily_max = {}
    for t in parsed_tweets:
        date = t.get("date", "")
        if not date:
            continue
        if date not in daily_max:
            daily_max[date] = {
                "date": date, "cum_drones": 0, "cum_missiles": 0,
                "posts": 0, "locations": [], "interceptions": 0, "strikes": 0,
            }
        daily_max[date]["cum_drones"] = max(daily_max[date]["cum_drones"], t.get("drones", 0))
        daily_max[date]["cum_missiles"] = max(daily_max[date]["cum_missiles"], t.get("missiles", 0))
        daily_max[date]["posts"] += 1
        if t.get("is_interception"):
            daily_max[date]["interceptions"] += 1
        for loc in t.get("locations", []):
            if loc not in daily_max[date]["locations"]:
                daily_max[date]["locations"].append(loc)

    sorted_days = sorted(daily_max.values(), key=lambda d: d["date"])

    result = []
    prev_drones = 0
    prev_missiles = 0
    for d in sorted_days:
        daily_drones = max(0, d["cum_drones"] - prev_drones)
        daily_missiles = max(0, d["cum_missiles"] - prev_missiles)
        if d["cum_drones"] > 0:
            prev_drones = d["cum_drones"]
        if d["cum_missiles"] > 0:
            prev_missiles = d["cum_missiles"]
        result.append({
            "date": d["date"],
            "drones": daily_drones,
            "missiles": daily_missiles,
            "posts": d["posts"],
            "locations": d["locations"],
            "interceptions": d["interceptions"],
            "strikes": d["strikes"],
            "interception_events": d["interceptions"],
        })

    return result


def _get_newest_tweet_id(username: str) -> int | None:
    """Get the newest tweet ID we've already cached for a username."""
    raw_cache = load_cache(RAW_TWEETS_CACHE)
    tweets = raw_cache.get(username, {}).get("tweets", [])
    if tweets:
        return max(t["id"] for t in tweets)
    return None


def _merge_tweets(existing: list, new_tweets: list) -> list:
    """Merge new tweets into existing list, deduplicating by ID."""
    existing_ids = {t["id"] for t in existing}
    merged = list(existing)
    added = 0
    for t in new_tweets:
        if t["id"] not in existing_ids:
            merged.append(t)
            existing_ids.add(t["id"])
            added += 1
    return merged, added


def fetch_delta():
    """Fetch only NEW tweets since last update, merge with cached data."""
    if not twitter:
        logger.error("Twitter client not initialized.")
        return get_analytics()

    raw_cache = load_cache(RAW_TWEETS_CACHE)
    is_first_run = len(raw_cache) == 0

    if is_first_run:
        logger.info("First run — fetching full historical data...")
    else:
        logger.info("Delta update — fetching only new tweets...")

    # Track which usernames we've already fetched this cycle
    fetched_usernames = {}

    for account in config.ACCOUNTS:
        username = account["username"]
        parse_mode = account.get("parse_mode", "arabic_per_incident")

        # Skip if we already fetched this username this cycle (Israel/Iran share @TheStudyofWar)
        if username in fetched_usernames:
            continue

        if is_first_run:
            # Full historical fetch
            logger.info(f"Fetching full history from @{username}...")
            raw_data = twitter.fetch_historical_tweets(username, max_tweets=config.MAX_HISTORICAL_TWEETS)
            raw_cache[username] = {
                "tweets": raw_data.get("tweets", []),
                "display_name": raw_data.get("display_name", username),
                "profile_image": raw_data.get("profile_image", ""),
            }
        else:
            # Delta fetch — only new tweets since our newest cached one
            since_id = _get_newest_tweet_id(username)
            logger.info(f"Fetching new tweets from @{username} (since_id={since_id})...")
            raw_data = twitter.fetch_recent_tweets(username, since_id=since_id, max_results=100)
            new_tweets = raw_data.get("tweets", [])

            existing = raw_cache.get(username, {}).get("tweets", [])
            merged, added = _merge_tweets(existing, new_tweets)

            if username not in raw_cache:
                raw_cache[username] = {}
            raw_cache[username]["tweets"] = merged
            raw_cache[username]["display_name"] = raw_data.get("display_name", raw_cache[username].get("display_name", username))
            raw_cache[username]["profile_image"] = raw_data.get("profile_image", raw_cache[username].get("profile_image", ""))

            logger.info(f"  @{username}: {added} new tweets, {len(merged)} total cached")

        fetched_usernames[username] = True

    # Save raw tweet cache
    save_cache(RAW_TWEETS_CACHE, raw_cache)

    # Now re-analyze all cached tweets
    return _analyze_cached_tweets(raw_cache, is_first_run)


def _analyze_cached_tweets(raw_cache: dict, analyze_images_for_new_only: bool = False) -> dict:
    """Parse and analyze all cached tweets, produce analytics."""
    all_sources = []
    # Cache for already-analyzed image results
    image_cache_path = Path(__file__).parent / "cache" / "image_results.json"
    image_cache = load_cache(image_cache_path)

    for account in config.ACCOUNTS:
        username = account["username"]
        parse_mode = account.get("parse_mode", "arabic_per_incident")
        cached = raw_cache.get(username, {})
        tweets = cached.get("tweets", [])

        # Apply keyword filter if needed (Israel/Iran)
        if parse_mode == "keyword_filter":
            filter_kw = account.get("filter_keywords", [])
            tweets = filter_tweets_by_keywords(tweets, filter_kw)

        # Parse each tweet
        parsed = []
        for t in tweets:
            p = parse_tweet(t, parse_mode)

            # For image-based sources (Bahrain), use Claude Vision
            if parse_mode == "count_posts" and claude_client and t.get("media_urls"):
                tweet_id = str(t.get("id", ""))
                if tweet_id in image_cache:
                    # Reuse cached image analysis
                    img_data = image_cache[tweet_id]
                else:
                    # Analyze new image
                    img_data = extract_from_tweet_images(claude_client, t)
                    image_cache[tweet_id] = img_data

                p["drones"] = img_data.get("drones", 0)
                p["missiles"] = img_data.get("missiles", 0)

            parsed.append(p)

        if parse_mode == "count_posts":
            daily = _aggregate_cumulative(parsed)
        else:
            daily = aggregate_daily(parsed, parse_mode)

        summary = compute_summary(daily, parse_mode)

        source_analytics = {
            "country": account["country"],
            "flag": account["flag"],
            "color": account["color"],
            "description": account["description"],
            "username": username,
            "display_name": cached.get("display_name", username),
            "profile_image": cached.get("profile_image", ""),
            "total_tweets": len(tweets),
            "parse_mode": parse_mode,
            "daily_data": daily,
            "summary": summary,
        }
        all_sources.append(source_analytics)
        logger.info(f"  @{username} [{account['country']}]: {len(daily)} days, "
                     f"{summary['total_drones']} drones, {summary['total_missiles']} missiles")

    # Save image analysis cache
    save_cache(image_cache_path, image_cache)

    result = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "war_start": "2026-02-28",
        "sources": all_sources,
    }

    save_cache(ANALYTICS_CACHE, result)
    logger.info("Analytics data cached.")
    return result


def get_analytics() -> dict:
    """Get analytics from cache."""
    cache = load_cache(ANALYTICS_CACHE)
    if cache and "last_updated" in cache:
        return cache
    # No cache yet — return loading state (background thread is fetching)
    return {
        "last_updated": None,
        "war_start": "2026-02-28",
        "sources": [],
        "loading": True,
    }


# --- Routes ---

@app.route("/")
def index():
    data = get_analytics()
    return render_template("index.html", data=data)


@app.route("/api/analytics")
def api_analytics():
    return jsonify(get_analytics())


# --- Scheduler: run on the hour ---
scheduler = BackgroundScheduler()
scheduler.add_job(
    fetch_delta,
    CronTrigger(minute=0),  # Every hour on the hour
    id="hourly_delta_update",
    replace_existing=True,
)
scheduler.start()
logger.info("Scheduler started — delta updates every hour on the hour.")


def startup_fetch():
    """Run initial fetch in background so the server starts immediately."""
    import time
    time.sleep(2)  # Let gunicorn bind the port first
    fetch_delta()


# Run initial fetch in background thread (doesn't block server startup)
import threading
threading.Thread(target=startup_fetch, daemon=True).start()


if __name__ == "__main__":
    logger.info("Starting Gulf & Middle East Strikes Analytics Dashboard...")
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG, use_reloader=False)
