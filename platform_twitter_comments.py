import json
import logging
import time
from datetime import datetime, timezone
import requests

# ============================================================
# CONFIGURATION
# ============================================================

API_KEY = "sc_QPRRy3AT7j5xb5T5EuztzntY0rjsQynv9CEZpTarh2k"
BASE_URL = "https://www.socialcrawl.dev"

# Target Twitter handle (without @)
TWITTER_HANDLE = "DaikinIndia"          # Replace with the actual handle

# Date range for filtering
START_DATE = "2026-01-01"
END_DATE   = "2026-08-18"

# Choose which method to run (set to 1 or 2)
METHOD = 2   # 1 = AI Search, 2 = User Tweets (recent, filtered locally)

# AI Search specific settings
AI_SEARCH_QUERY = f"What has @{TWITTER_HANDLE} posted about recently?"

# User Tweets pagination (no native pagination, only one page)
REQUEST_DELAY = 1.0

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ============================================================
# HELPER: Parse Twitter date
# ============================================================

def parse_twitter_date(value):
    """Convert a Twitter published_at string to a datetime object."""
    if not value:
        return None
    try:
        # Twitter uses ISO 8601, often with Z
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    except Exception:
        return None


def filter_tweets_by_date(tweets, start_date_str, end_date_str):
    """Filter a list of tweets that fall within the given date range."""
    start = datetime.strptime(start_date_str, "%Y-%m-%d")
    end   = datetime.strptime(end_date_str,   "%Y-%m-%d")
    filtered = []
    for tweet in tweets:
        dt_str = tweet.get("published_at") or tweet.get("created_at")
        dt = parse_twitter_date(dt_str)
        if dt and start <= dt <= end:
            filtered.append(tweet)
    return filtered


# ============================================================
# OPTION 1: AI SEARCH (native date filtering)
# ============================================================

def fetch_ai_search():
    """Fetch AI search results with from_date and to_date parameters."""
    endpoint = f"{BASE_URL}/v1/twitter/ai-search"
    session = requests.Session()
    session.headers.update({
        "x-api-key": API_KEY,
        "Accept": "application/json",
    })

    params = {
        "query": AI_SEARCH_QUERY,
        "from_handles": TWITTER_HANDLE,
        "from_date": START_DATE,
        "to_date": END_DATE,
    }

    logger.info(f"[AI SEARCH] Query: {AI_SEARCH_QUERY}")
    logger.info(f"[AI SEARCH] Date range: {START_DATE} -> {END_DATE}")

    try:
        response = session.get(endpoint, params=params, timeout=90)
    except requests.RequestException as e:
        logger.error(f"Request failed: {e}")
        return None

    logger.info(f"[AI SEARCH] HTTP Status: {response.status_code}")

    if response.status_code != 200:
        logger.error(f"Error response: {response.text[:3000]}")
        return None

    try:
        payload = response.json()
    except ValueError:
        logger.error(f"Invalid JSON: {response.text[:2000]}")
        return None

    return payload


def process_ai_search_result(payload):
    """Extract tweets from AI search sources and return a list of tweet objects."""
    data = payload.get("data", {})
    sources = data.get("sources", [])
    tweets = []
    for src in sources:
        post = src.get("post")
        if post:
            tweets.append(post)
    return tweets


# ============================================================
# OPTION 2: USER TWEETS (no native date filtering, fetch recent)
# ============================================================

def fetch_user_tweets():
    """
    Fetch the most recent tweets for a user.
    This endpoint returns only one page (no pagination cursor).
    """
    endpoint = f"{BASE_URL}/v1/twitter/user/tweets"
    session = requests.Session()
    session.headers.update({
        "x-api-key": API_KEY,
        "Accept": "application/json",
    })

    params = {
        "handle": TWITTER_HANDLE,   # without @
    }

    logger.info(f"[USER TWEETS] Fetching recent tweets for @{TWITTER_HANDLE}")

    try:
        response = session.get(endpoint, params=params, timeout=90)
    except requests.RequestException as e:
        logger.error(f"Request failed: {e}")
        return None

    logger.info(f"[USER TWEETS] HTTP Status: {response.status_code}")

    if response.status_code != 200:
        logger.error(f"Error response: {response.text[:3000]}")
        return None

    try:
        payload = response.json()
    except ValueError:
        logger.error(f"Invalid JSON: {response.text[:2000]}")
        return None

    # The response usually has data.items as a list of tweets
    data = payload.get("data", {})
    items = data.get("items", [])
    return items


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 80)
    print("TWITTER/X EXTRACTION")
    print("=" * 80)
    print(f"Handle: @{TWITTER_HANDLE}")
    print(f"Date range: {START_DATE} -> {END_DATE}")

    if METHOD == 1:
        print("Method: AI Search (native date filtering)")
        print("=" * 80)

        payload = fetch_ai_search()
        if not payload:
            print("Failed to fetch AI search results.")
            return

        # Save full response
        output_file = "twitter_ai_search_full.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

        # Extract tweets from sources
        tweets = process_ai_search_result(payload)
        answer = payload.get("data", {}).get("answer", "")

        print("=" * 80)
        print("AI SEARCH RESULTS")
        print("=" * 80)
        print(f"AI Answer: {answer[:300]}..." if answer else "No answer generated")
        print(f"Number of cited tweets: {len(tweets)}")
        print(f"Credits used: {payload.get('credits_used', 0)}")
        print(f"Credits remaining: {payload.get('credits_remaining', 0)}")
        print(f"Full response saved to: {output_file}")

        # Optionally, save just the tweets
        tweets_file = "twitter_ai_search_tweets.json"
        with open(tweets_file, "w", encoding="utf-8") as f:
            json.dump(tweets, f, indent=2, ensure_ascii=False)
        print(f"Extracted tweets saved to: {tweets_file}")

    elif METHOD == 2:
        print("Method: User Tweets (fetch recent, filter locally)")
        print("=" * 80)

        all_tweets = fetch_user_tweets()
        if all_tweets is None:
            print("Failed to fetch user tweets.")
            return

        print(f"Total tweets received (before filtering): {len(all_tweets)}")

        # Apply local date filter
        filtered = filter_tweets_by_date(all_tweets, START_DATE, END_DATE)
        print(f"Tweets within date range: {len(filtered)}")

        # Save both raw and filtered
        raw_file = "twitter_user_tweets_raw.json"
        with open(raw_file, "w", encoding="utf-8") as f:
            json.dump(all_tweets, f, indent=2, ensure_ascii=False)

        filtered_file = "twitter_user_tweets_filtered.json"
        with open(filtered_file, "w", encoding="utf-8") as f:
            json.dump({
                "handle": TWITTER_HANDLE,
                "date_range": {"start": START_DATE, "end": END_DATE},
                "total_fetched": len(all_tweets),
                "filtered_count": len(filtered),
                "tweets": filtered
            }, f, indent=2, ensure_ascii=False)

        print(f"Raw tweets saved to: {raw_file}")
        print(f"Filtered tweets saved to: {filtered_file}")

    else:
        print("Invalid METHOD. Choose 1 (AI Search) or 2 (User Tweets).")

    print("=" * 80)
    print("EXTRACTION COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()