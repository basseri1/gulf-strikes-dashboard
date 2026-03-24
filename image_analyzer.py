"""Extract strike data from tweet images using Claude Vision API."""

import base64
import json
import logging
import os
import re
from io import BytesIO
from urllib.request import urlopen

import anthropic

logger = logging.getLogger(__name__)

EXTRACT_PROMPT = """Analyze this image from a military/defense tweet. Extract the following numbers if visible:

1. Total drones intercepted/destroyed (look for "مسيرة" or "drone" or "Downed UAV")
2. Total missiles intercepted/destroyed (look for "صاروخ" or "missile" or "Missile")
3. Any other strike counts visible

Return ONLY a JSON object like this, with integer values (0 if not found):
{"drones": 0, "missiles": 0}

If the image contains cumulative totals, return those totals.
If the image shows no strike data at all, return {"drones": 0, "missiles": 0}.
Return ONLY the JSON, no other text."""


def get_claude_client():
    """Initialize Anthropic client."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None
    return anthropic.Anthropic(api_key=api_key)


def download_image_as_base64(url: str) -> tuple[str, str]:
    """Download an image URL and return (base64_data, media_type)."""
    try:
        with urlopen(url, timeout=10) as response:
            data = response.read()
            content_type = response.headers.get("Content-Type", "image/jpeg")
            media_type = content_type.split(";")[0].strip()
            if media_type not in ("image/jpeg", "image/png", "image/gif", "image/webp"):
                media_type = "image/jpeg"
            return base64.standard_b64encode(data).decode("utf-8"), media_type
    except Exception as e:
        logger.error(f"Failed to download image {url}: {e}")
        return None, None


def extract_from_image(client: anthropic.Anthropic, image_url: str) -> dict:
    """Send an image to Claude Vision and extract drone/missile counts."""
    b64_data, media_type = download_image_as_base64(image_url)
    if not b64_data:
        return {"drones": 0, "missiles": 0}

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64_data,
                        },
                    },
                    {
                        "type": "text",
                        "text": EXTRACT_PROMPT,
                    },
                ],
            }],
        )

        result_text = response.content[0].text.strip()

        # Extract JSON from response
        json_match = re.search(r'\{[^}]+\}', result_text)
        if json_match:
            data = json.loads(json_match.group())
            drones = int(data.get("drones", 0))
            missiles = int(data.get("missiles", 0))
            logger.info(f"  Image analysis: drones={drones}, missiles={missiles}")
            return {"drones": drones, "missiles": missiles}

        logger.warning(f"No JSON in Claude response: {result_text[:100]}")
        return {"drones": 0, "missiles": 0}

    except Exception as e:
        logger.error(f"Claude Vision API error: {e}")
        return {"drones": 0, "missiles": 0}


def extract_from_tweet_images(client: anthropic.Anthropic, tweet: dict) -> dict:
    """Extract strike data from all images in a tweet.

    Takes the highest values found across all images (cumulative infographics).
    """
    media_urls = tweet.get("media_urls", [])
    if not media_urls:
        return {"drones": 0, "missiles": 0}

    best = {"drones": 0, "missiles": 0}

    for url in media_urls:
        result = extract_from_image(client, url)
        # Take the max — images may show cumulative totals
        best["drones"] = max(best["drones"], result["drones"])
        best["missiles"] = max(best["missiles"], result["missiles"])

    return best
