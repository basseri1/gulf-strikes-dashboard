"""Twitter/X API v2 client wrapper using Tweepy."""

import logging
from datetime import datetime, timezone

import tweepy

logger = logging.getLogger(__name__)

# War start date
WAR_START = datetime(2026, 2, 28, tzinfo=timezone.utc)


class TwitterClient:
    def __init__(self, bearer_token: str):
        self.client = tweepy.Client(bearer_token=bearer_token, wait_on_rate_limit=True)

    def fetch_user_tweets(self, username: str, max_results: int = 10) -> dict:
        """Fetch recent tweets from a user by username."""
        try:
            user = self.client.get_user(username=username, user_fields=["profile_image_url", "description"])
            if not user.data:
                logger.warning(f"User @{username} not found")
                return {"username": username, "error": "User not found", "tweets": []}

            user_id = user.data.id
            user_name = user.data.name
            profile_image = getattr(user.data, "profile_image_url", "")

            tweets_response = self.client.get_users_tweets(
                id=user_id,
                max_results=max(max_results, 5),
                tweet_fields=["created_at", "public_metrics", "lang", "source"],
                expansions=["attachments.media_keys"],
                media_fields=["url", "preview_image_url", "type"],
                exclude=["retweets"],
            )

            tweets = self._process_tweets(tweets_response, username)

            return {
                "username": username,
                "display_name": user_name,
                "profile_image": profile_image,
                "tweet_count": len(tweets),
                "tweets": tweets,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }

        except tweepy.TooManyRequests:
            logger.error(f"Rate limit hit for @{username}")
            return {"username": username, "error": "Rate limit exceeded.", "tweets": []}
        except tweepy.Unauthorized:
            logger.error("Invalid Twitter Bearer Token")
            return {"username": username, "error": "Invalid API credentials.", "tweets": []}
        except Exception as e:
            logger.error(f"Error fetching tweets for @{username}: {e}")
            return {"username": username, "error": str(e), "tweets": []}

    def fetch_historical_tweets(self, username: str, since: datetime = None, max_tweets: int = 200) -> dict:
        """Fetch tweets from a user going back to a specific date.

        Uses pagination to get more than 100 tweets.
        """
        if since is None:
            since = WAR_START

        try:
            user = self.client.get_user(username=username, user_fields=["profile_image_url", "description"])
            if not user.data:
                logger.warning(f"User @{username} not found")
                return {"username": username, "error": "User not found", "tweets": []}

            user_id = user.data.id
            user_name = user.data.name
            profile_image = getattr(user.data, "profile_image_url", "")

            all_tweets = []
            pagination_token = None
            fetched = 0

            while fetched < max_tweets:
                batch_size = min(100, max_tweets - fetched)
                if batch_size < 5:
                    batch_size = 5

                kwargs = {
                    "id": user_id,
                    "max_results": batch_size,
                    "tweet_fields": ["created_at", "public_metrics", "lang"],
                    "expansions": ["attachments.media_keys"],
                    "media_fields": ["url", "preview_image_url", "type"],
                    "start_time": since,
                    "exclude": ["retweets"],
                }
                if pagination_token:
                    kwargs["pagination_token"] = pagination_token

                tweets_response = self.client.get_users_tweets(**kwargs)

                if not tweets_response.data:
                    break

                batch = self._process_tweets(tweets_response, username)
                all_tweets.extend(batch)
                fetched += len(batch)

                if not tweets_response.meta or "next_token" not in tweets_response.meta:
                    break
                pagination_token = tweets_response.meta["next_token"]

                logger.info(f"  @{username}: fetched {fetched} tweets so far...")

            return {
                "username": username,
                "display_name": user_name,
                "profile_image": profile_image,
                "tweet_count": len(all_tweets),
                "tweets": all_tweets,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }

        except tweepy.TooManyRequests:
            logger.error(f"Rate limit hit for @{username}")
            return {"username": username, "error": "Rate limit exceeded.", "tweets": []}
        except tweepy.Unauthorized:
            logger.error("Invalid Twitter Bearer Token")
            return {"username": username, "error": "Invalid API credentials.", "tweets": []}
        except Exception as e:
            logger.error(f"Error fetching historical tweets for @{username}: {e}")
            return {"username": username, "error": str(e), "tweets": []}

    def fetch_recent_tweets(self, username: str, since_id: int = None, max_results: int = 100) -> dict:
        """Fetch only new tweets since a given tweet ID (delta fetch)."""
        try:
            user = self.client.get_user(username=username, user_fields=["profile_image_url", "description"])
            if not user.data:
                return {"username": username, "error": "User not found", "tweets": []}

            user_id = user.data.id

            kwargs = {
                "id": user_id,
                "max_results": max(min(max_results, 100), 5),
                "tweet_fields": ["created_at", "public_metrics", "lang"],
                "expansions": ["attachments.media_keys"],
                "media_fields": ["url", "preview_image_url", "type"],
                "exclude": ["retweets"],
            }
            if since_id:
                kwargs["since_id"] = since_id

            tweets_response = self.client.get_users_tweets(**kwargs)
            tweets = self._process_tweets(tweets_response, username)

            return {
                "username": username,
                "display_name": user.data.name,
                "profile_image": getattr(user.data, "profile_image_url", ""),
                "tweet_count": len(tweets),
                "tweets": tweets,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }

        except tweepy.TooManyRequests:
            logger.error(f"Rate limit hit for @{username}")
            return {"username": username, "error": "Rate limit exceeded.", "tweets": []}
        except tweepy.Unauthorized:
            logger.error("Invalid Twitter Bearer Token")
            return {"username": username, "error": "Invalid API credentials.", "tweets": []}
        except Exception as e:
            logger.error(f"Error fetching recent tweets for @{username}: {e}")
            return {"username": username, "error": str(e), "tweets": []}

    def _process_tweets(self, tweets_response, username: str) -> list:
        """Process a Tweepy response into a list of tweet dicts."""
        tweets = []
        if not tweets_response.data:
            return tweets

        # Build media lookup from includes
        media_map = {}
        if tweets_response.includes and "media" in tweets_response.includes:
            for media in tweets_response.includes["media"]:
                url = getattr(media, "url", None) or getattr(media, "preview_image_url", None)
                if url:
                    media_map[media.media_key] = url

        for tweet in tweets_response.data:
            metrics = tweet.public_metrics or {}

            # Collect media URLs for this tweet
            media_urls = []
            if hasattr(tweet, "attachments") and tweet.attachments:
                for key in tweet.attachments.get("media_keys", []):
                    if key in media_map:
                        media_urls.append(media_map[key])

            tweet_data = {
                "id": tweet.id,
                "text": tweet.text,
                "created_at": tweet.created_at.isoformat() if tweet.created_at else None,
                "likes": metrics.get("like_count", 0),
                "retweets": metrics.get("retweet_count", 0),
                "replies": metrics.get("reply_count", 0),
                "url": f"https://x.com/{username}/status/{tweet.id}",
                "media_urls": media_urls,
            }
            tweets.append(tweet_data)

        return tweets
