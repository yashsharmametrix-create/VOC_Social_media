
"""
LINKEDIN COMMENTS EXTRACTION (fixed)
Extracts posts and comments from LinkedIn via SocialCrawl.

Fixes applied vs. the original version:
  1. `import time` was missing entirely -> every run that processed at
     least one non-filtered post crashed with NameError right after
     `db.upsert_post()`, before the JSON export step ever ran.
  2. The `hash(json.dumps(...))[:16]` id fallback was broken two ways:
       - hash() returns an int, which isn't subscriptable -> TypeError
       - Python randomizes str hashes per-process by default, so even
         if it didn't crash, the same post would get a different
         fallback id on every run (breaks de-duplication).
     Replaced with a stable hashlib-based id.
  3. `/v1/search/everywhere` was called with `"platforms": "linkedin"`.
     That is not a real parameter on that endpoint -- the documented
     one is `sources` (comma-separated, e.g. sources=linkedin), so the
     old code was quietly searching ALL ~15+ platforms and then trying
     to filter LinkedIn out client-side.
  4. The client-side platform filter only checked `item["source"]` and
     `item["post"]["platform"]`, which don't reliably match the
     documented response shape. Widened it to check every plausible
     field/location and made it case-insensitive.
  5. `/v1/prism/comments` does not appear in SocialCrawl's published
     endpoint list, and `/v1/linkedin/post-comments` (tried in an earlier
     version of this script) 404s on a real post URL. Since the exact
     path is behind a login I don't have, the client now PROBES a list
     of plausible paths (COMMENTS_ENDPOINT_CANDIDATES below) against
     your first real post URL and keeps whichever one returns 200,
     logging the status of every candidate it tries. If none of them
     work, log into socialcrawl.dev/docs/api-reference -> LinkedIn ->
     "Post Comments" for the real path and add it to the top of that
     list.
  6. Added a credits-balance check and raw-response dumps so you can
     SEE the actual JSON shape SocialCrawl returns for your key/plan,
     instead of guessing blindly. This is the fastest way to fix any
     remaining field-name mismatches yourself.
"""

import requests
import json
import logging
import hashlib
import time
from datetime import datetime

# ============================================================
# CONFIGURATION
# ============================================================
API_KEY = "sc_QPRRy3AT7j5xb5T5EuztzntY0rjsQynv9CEZpTarh2k"
BASE_URL = "https://www.socialcrawl.dev"

# If your dashboard's API reference shows a different path for these,
# change them here -- nothing else in the script needs to change.
SEARCH_ENDPOINT_PATH = "/v1/search/everywhere"

# We confirmed /v1/linkedin/post-comments 404s. Rather than guess again blindly,
# the client tries each of these in order on the FIRST comments call of the run,
# keeps whichever one returns 200, and reuses it for every call after that.
# Order is based on SocialCrawl's own naming pattern for nested LinkedIn
# resources (they use /v1/linkedin/group/posts, i.e. resource/subresource
# with slashes, not hyphens -- so the slash form is tried first).
COMMENTS_ENDPOINT_CANDIDATES = [
    "/v1/linkedin/post/comments",
    "/v1/linkedin/post-comments",
    "/v1/linkedin/comments",
    "/v1/prism/comments",
]

# Search queries
TEST_QUERIES = [
    "LG AC",
    "LG Air Conditioner",
]

# Results per query
LIMIT = 10

# Period filter - set both to None to capture all time periods
DATE_FROM = "2026-01-01"
DATE_TO = "2026-07-31"

# Database settings
DB_FILE = "linkedin_comments.db"
LOG_FILE = f"linkedin_comments_{datetime.now().strftime('%Y%m%d')}.log"

# Comment fetching settings
MAX_COMMENT_PAGES = 5

# JSON export settings
JSON_EXPORT_FILE = f"linkedin_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

# Debug dumps -- first raw response per call type gets saved here so
# you can inspect the real field names SocialCrawl returns.
DEBUG_DIR = "debug_raw_responses"

# ============================================================
# GEOGRAPHY DATA - ALL INDIAN STATES AND MAJOR CITIES
# ============================================================
INDIA_GEO_KEYWORDS = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh",
    "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka",
    "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya",
    "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim",
    "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand",
    "West Bengal", "Delhi", "Jammu and Kashmir", "Ladakh", "Puducherry",
    "Chandigarh", "Andaman and Nicobar", "Dadra and Nagar Haveli",
    "Lakshadweep",
    "Mumbai", "Bengaluru", "Bangalore", "Chennai", "Kolkata", "Hyderabad",
    "Pune", "Ahmedabad", "Jaipur", "Lucknow", "Surat", "Kanpur", "Nagpur",
    "Indore", "Bhopal", "Patna", "Vadodara", "Ludhiana", "Agra", "Nashik",
    "Coimbatore", "Kochi", "Thiruvananthapuram", "Guwahati", "Noida",
    "Gurugram", "Gurgaon", "Faridabad", "Meerut", "Rajkot", "Vijayawada",
    "Jodhpur", "Laxmi Nagar", "Whitefield", "Electronic City", "Koramangala",
    "Saket", "Connaught Place", "Rajpath", "Karol Bagh", "Chandni Chowk",
    "Santacruz", "Andheri", "Borivali", "Dahisar", "Bandra",
]

# ============================================================
# LOGGING
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ============================================================
# DEBUG HELPERS
# ============================================================
import os


def dump_debug_json(name, payload):
    """Save a raw API response to disk so its real shape can be inspected."""
    try:
        os.makedirs(DEBUG_DIR, exist_ok=True)
        path = os.path.join(DEBUG_DIR, f"{name}.json")
        # Don't overwrite -- we only need one example per call type.
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            logger.info(f"  [debug] saved raw response sample -> {path}")
    except Exception as e:
        logger.debug(f"  [debug] could not save debug dump: {e}")


def stable_id(prefix, obj):
    """Deterministic id fallback (unlike Python's randomized hash())."""
    digest = hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return f"{prefix}_{digest[:16]}"


# ============================================================
# GEOGRAPHY DETECTION
# ============================================================
def detect_geo_region(*text_blobs):
    combined = " ".join([t for t in text_blobs if t]).lower()
    for region in INDIA_GEO_KEYWORDS:
        if region.lower() in combined:
            return region
    return ""

# ============================================================
# TIMESTAMP HELPERS
# ============================================================
def parse_timestamp(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except Exception:
        return None

def within_date_window(ts_str):
    if not DATE_FROM and not DATE_TO:
        return True

    dt = parse_timestamp(ts_str)
    if dt is None:
        return True

    dt_naive = dt.replace(tzinfo=None)

    if DATE_FROM and dt_naive < datetime.fromisoformat(DATE_FROM):
        return False

    if DATE_TO:
        try:
            dt_end = datetime.fromisoformat(DATE_TO).replace(hour=23, minute=59, second=59)
            if dt_naive > dt_end:
                return False
        except ValueError:
            pass

    return True

# ============================================================
# DATABASE
# ============================================================
import sqlite3

class LinkedInCommentsDB:
    def __init__(self, db_path):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS posts (
                post_id TEXT PRIMARY KEY,
                title TEXT,
                text TEXT,
                author TEXT,
                author_id TEXT,
                url TEXT,
                timestamp TEXT,
                likes INTEGER,
                comments_count INTEGER,
                reposts INTEGER,
                location TEXT,
                geo_region TEXT,
                raw_json TEXT,
                fetched_at TEXT
            );

            CREATE TABLE IF NOT EXISTS comments (
                comment_id TEXT PRIMARY KEY,
                post_id TEXT,
                author TEXT,
                author_id TEXT,
                text TEXT,
                likes INTEGER,
                timestamp TEXT,
                geo_region TEXT,
                raw_json TEXT,
                fetched_at TEXT,
                FOREIGN KEY(post_id) REFERENCES posts(post_id)
            );

            CREATE INDEX IF NOT EXISTS idx_comments_post ON comments(post_id);
            CREATE INDEX IF NOT EXISTS idx_comments_author ON comments(author);
            CREATE INDEX IF NOT EXISTS idx_comments_timestamp ON comments(timestamp);
            CREATE INDEX IF NOT EXISTS idx_comments_geo ON comments(geo_region);
            """
        )
        self.conn.commit()

    def upsert_post(self, post):
        now = datetime.now().isoformat()

        post_id = post.get("id") or post.get("post_id") or post.get("item_id", "")
        if not post_id:
            logger.warning("No post ID found, skipping")
            return "skipped_no_id"

        timestamp = post.get("timestamp") or post.get("created_at") or post.get("published_at", "")
        if not within_date_window(timestamp):
            logger.debug(f"Skipping post {post_id} - outside date window")
            return "skipped_date_filter"

        row = self.conn.execute(
            "SELECT * FROM posts WHERE post_id = ?", (post_id,)
        ).fetchone()

        raw_json = json.dumps(post, ensure_ascii=False)

        text = post.get("text") or post.get("content") or post.get("body") or post.get("snippet", "")
        location = post.get("location") or post.get("author_location", "")
        geo_region = detect_geo_region(text, location)

        if row is None:
            self.conn.execute(
                """
                INSERT INTO posts
                (post_id, title, text, author, author_id, url, timestamp,
                 likes, comments_count, reposts, location, geo_region, raw_json, fetched_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    post_id,
                    post.get("title", ""),
                    text,
                    post.get("author") or post.get("username", ""),
                    post.get("author_id") or post.get("user_id", ""),
                    post.get("url", ""),
                    timestamp,
                    post.get("likes", 0),
                    post.get("comments_count", 0),
                    post.get("reposts", 0),
                    location,
                    geo_region,
                    raw_json,
                    now,
                ),
            )
            self.conn.commit()
            return "new"

        self.conn.execute(
            """
            UPDATE posts SET
                title=?, text=?, author=?, author_id=?, url=?, timestamp=?,
                likes=?, comments_count=?, reposts=?, location=?, geo_region=?, raw_json=?, fetched_at=?
            WHERE post_id=?
            """,
            (
                post.get("title", ""),
                text,
                post.get("author") or post.get("username", ""),
                post.get("author_id") or post.get("user_id", ""),
                post.get("url", ""),
                timestamp,
                post.get("likes", 0),
                post.get("comments_count", 0),
                post.get("reposts", 0),
                location,
                geo_region,
                raw_json,
                now,
                post_id,
            ),
        )
        self.conn.commit()
        return "updated"

    def upsert_comment(self, comment, post_id, geo_region):
        now = datetime.now().isoformat()

        comment_id = (
            comment.get("id")
            or comment.get("comment_id")
            or comment.get("review_id")
            or comment.get("item_id", "")
        )
        if not comment_id:
            return "skipped_no_id"

        timestamp = comment.get("timestamp") or comment.get("created_at") or comment.get("published_at", "")
        if not within_date_window(timestamp):
            return "skipped_date_filter"

        row = self.conn.execute(
            "SELECT comment_id FROM comments WHERE comment_id = ?", (comment_id,)
        ).fetchone()

        raw_json = json.dumps(comment, ensure_ascii=False)
        text = comment.get("text") or comment.get("content") or comment.get("body") or comment.get("snippet", "")
        comment_geo_region = detect_geo_region(text)

        if row is None:
            self.conn.execute(
                """
                INSERT INTO comments
                (comment_id, post_id, author, author_id, text, likes,
                 timestamp, geo_region, raw_json, fetched_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    comment_id,
                    post_id,
                    comment.get("author") or comment.get("username", ""),
                    comment.get("author_id") or comment.get("user_id", ""),
                    text,
                    comment.get("likes", 0),
                    timestamp,
                    comment_geo_region or geo_region,
                    raw_json,
                    now,
                ),
            )
            self.conn.commit()
            return "new"

        self.conn.execute(
            "UPDATE comments SET fetched_at = ? WHERE comment_id = ?",
            (now, comment_id),
        )
        self.conn.commit()
        return "unchanged"

    def close(self):
        self.conn.close()

# ============================================================
# LINKEDIN CLIENT
# ============================================================
class LinkedInClient:
    def __init__(self, api_key, base_url):
        self.api_key = api_key
        self.base_url = base_url
        self._comments_endpoint = None  # discovered on first successful call
        self.session = requests.Session()
        self.session.headers.update({
            "x-api-key": api_key,
            "Content-Type": "application/json"
        })

    def check_credits(self):
        """0-credit call. Confirms the key is valid and shows remaining balance."""
        endpoint = f"{self.base_url}/v1/credits/balance"
        try:
            resp = self.session.get(endpoint, timeout=30)
            logger.info(f"[CREDITS] status={resp.status_code} body={resp.text[:300]}")
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"Credits check failed: {e}")
            return False

    def search_posts(self, query, limit=10):
        """
        Search LinkedIn posts using the /v1/search/everywhere endpoint,
        scoped to LinkedIn with the `sources` parameter (NOT `platforms`).
        """
        endpoint = f"{self.base_url}{SEARCH_ENDPOINT_PATH}"

        params = {
            "query": query,
            "sources": "linkedin",   # documented param name, was "platforms" before
            "gl": "in",
            "limit": limit,
        }

        logger.info(f"Searching LinkedIn: {query}")
        logger.info(f"Endpoint: {endpoint}")
        logger.info(f"Params: {params}")

        try:
            resp = self.session.get(endpoint, params=params, timeout=60)
            logger.info(f"[SEARCH] status={resp.status_code}")

            if resp.status_code != 200:
                logger.error(f"LinkedIn search error: {resp.status_code} {resp.text[:500]}")
                return []

            data = resp.json()
            dump_debug_json("search_everywhere_raw", data)

            # Response envelope: try the documented shape first, then fall back.
            raw_items = None
            if isinstance(data.get("data"), dict):
                raw_items = data["data"].get("items")
            if raw_items is None:
                raw_items = data.get("results") or data.get("data") or []

            if not isinstance(raw_items, list):
                raw_items = []

            logger.info(f"[SEARCH] raw items returned: {len(raw_items)}")

            # Widened platform filter -- checks every plausible field/location,
            # case-insensitively, instead of only item['source'].
            linkedin_items = []
            for item in raw_items:
                candidates = [
                    item.get("platform"),
                    item.get("source"),
                    (item.get("post") or {}).get("platform"),
                    (item.get("post") or {}).get("source"),
                    (item.get("metadata") or {}).get("platform"),
                ]
                if any(str(c).lower() == "linkedin" for c in candidates if c):
                    linkedin_items.append(item)

            logger.info(
                f"[LINKEDIN] Returned: {len(linkedin_items)} items "
                f"(filtered from {len(raw_items)})"
            )

            if raw_items and not linkedin_items:
                logger.warning(
                    "  Got results but none matched the LinkedIn filter -- "
                    f"check {DEBUG_DIR}/search_everywhere_raw.json to see the "
                    "real field names and adjust the filter in search_posts()."
                )

            return linkedin_items

        except Exception as e:
            logger.error(f"LinkedIn search exception: {e}")
            return []

    def _discover_comments_endpoint(self, post_url):
        """
        Try each candidate path once with this real post URL and keep the
        first one that returns HTTP 200. Logs status for every candidate so
        you can see exactly what each route did (404, 401, 200, etc).
        Result is cached on the client for the rest of the run.
        """
        if self._comments_endpoint:
            return self._comments_endpoint

        logger.info("  [COMMENTS] discovering the correct endpoint path...")
        for path in COMMENTS_ENDPOINT_CANDIDATES:
            endpoint = f"{self.base_url}{path}"
            try:
                resp = self.session.get(endpoint, params={"url": post_url}, timeout=30)
                logger.info(f"    trying {path} -> status={resp.status_code}")

                if resp.status_code == 200:
                    logger.info(f"  [COMMENTS] using endpoint: {path}")
                    self._comments_endpoint = path
                    # This first response is real data -- use it instead of
                    # discarding it and re-requesting page 1.
                    data = resp.json()
                    dump_debug_json("post_comments_raw", data)
                    return path, data

                if resp.status_code not in (404,):
                    # Something other than "route doesn't exist" -- worth
                    # seeing the body for (auth error, bad param, etc).
                    logger.info(f"      body: {resp.text[:300]}")

            except Exception as e:
                logger.warning(f"    {path} raised {e}")

        logger.error(
            "  None of the candidate comments endpoints returned 200. "
            f"Tried: {COMMENTS_ENDPOINT_CANDIDATES}. Log into your SocialCrawl "
            "dashboard -> API Reference -> LinkedIn -> 'Post Comments' to get "
            "the real path, then add it to COMMENTS_ENDPOINT_CANDIDATES at the "
            "top of this script (put it first in the list)."
        )
        return None, None

    def fetch_comments(self, post_url, max_pages=MAX_COMMENT_PAGES):
        """
        Fetch comments for a LinkedIn post. On the very first call this run,
        probes COMMENTS_ENDPOINT_CANDIDATES to find the real path; every call
        after that goes straight to the endpoint that worked.
        """
        all_comments = []
        cursor = None
        first_page_data = None

        if self._comments_endpoint is None:
            path, data = self._discover_comments_endpoint(post_url)
            if path is None:
                return []  # discovery failed, already logged why
            first_page_data = data  # don't waste a call re-fetching page 1

        endpoint = f"{self.base_url}{self._comments_endpoint}"

        for page in range(max_pages):
            try:
                if first_page_data is not None:
                    data = first_page_data
                    first_page_data = None
                    status_for_log = 200
                else:
                    params = {"url": post_url}
                    if cursor:
                        params["cursor"] = cursor
                    resp = self.session.get(endpoint, params=params, timeout=30)
                    status_for_log = resp.status_code
                    logger.info(f"  [COMMENTS] status={resp.status_code} (page {page + 1})")

                    if resp.status_code != 200:
                        logger.warning(f"Comments fetch error: {resp.status_code} {resp.text[:500]} for {post_url}")
                        break

                    data = resp.json()
                    dump_debug_json("post_comments_raw", data)

                payload = data.get("data", {}) if isinstance(data.get("data"), dict) else {}
                items = payload.get("items") or data.get("data") or []

                if not isinstance(items, list):
                    items = []

                all_comments.extend(items)
                logger.info(f"  Fetched {len(items)} comments (page {page + 1}/{max_pages})")

                cursor = payload.get("next_cursor")
                has_more = payload.get("has_more")

                if not cursor or not has_more:
                    break

                time.sleep(0.3)

            except Exception as e:
                logger.error(f"Comments fetch exception: {e}")
                break

        return all_comments

# ============================================================
# JSON EXPORT
# ============================================================
def export_to_json(posts, comments, filename):
    export_data = {
        "export_timestamp": datetime.now().isoformat(),
        "total_posts": len(posts),
        "total_comments": len(comments),
        "posts": posts,
        "comments": comments,
        "metadata": {
            "queries": TEST_QUERIES,
            "date_range": {
                "from": DATE_FROM,
                "to": DATE_TO
            },
            "platform": "linkedin"
        }
    }

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False)

    logger.info(f"Data exported to: {filename}")
    return filename

# ============================================================
# MAIN
# ============================================================
def main():
    logger.info("=" * 80)
    logger.info("LINKEDIN COMMENTS EXTRACTION")
    logger.info("=" * 80)

    db = LinkedInCommentsDB(DB_FILE)
    linkedin = LinkedInClient(API_KEY, BASE_URL)

    if not linkedin.check_credits():
        logger.error(
            "Could not confirm API key / credit balance. Check the [CREDITS] "
            "log line above for the actual status code and response body "
            "before going further -- a 401 here means everything downstream "
            "will fail too."
        )

    all_posts = []
    all_comments = []

    for query in TEST_QUERIES:
        logger.info(f"\n{'='*60}")
        logger.info(f"Query: {query}")
        logger.info(f"Date Window: {DATE_FROM or 'All Time'} to {DATE_TO or 'All Time'}")
        logger.info(f"{'='*60}")

        posts = linkedin.search_posts(query, limit=LIMIT)
        logger.info(f"Found {len(posts)} posts")

        for post in posts:
            try:
                post_id = (
                    post.get("id") or
                    post.get("post_id") or
                    post.get("item_id") or
                    post.get("candidate_id") or
                    (post.get("post") or {}).get("id") or
                    (post.get("post") or {}).get("post_id") or
                    stable_id("linkedin", post)
                )

                text = (
                    post.get("text") or
                    post.get("content") or
                    post.get("body") or
                    post.get("snippet") or
                    post.get("description") or
                    (post.get("post") or {}).get("text") or
                    (post.get("post") or {}).get("content") or
                    "No content available"
                )

                title = (
                    post.get("title") or
                    (post.get("post") or {}).get("title") or
                    ((text[:100] + "...") if text else "No title")
                )

                author = (
                    post.get("author") or
                    post.get("username") or
                    post.get("display_name") or
                    (post.get("post") or {}).get("author") or
                    (post.get("post") or {}).get("username") or
                    "Unknown"
                )

                url = (
                    post.get("url") or
                    (post.get("post") or {}).get("url") or
                    ""
                )

                timestamp = (
                    post.get("timestamp") or
                    post.get("created_at") or
                    post.get("published_at") or
                    (post.get("post") or {}).get("timestamp") or
                    (post.get("post") or {}).get("created_at") or
                    (post.get("post") or {}).get("published_at") or
                    ""
                )

                logger.info(f"\nProcessing post: {text[:80]}...")
                logger.info(f"  Post ID: {post_id}")
                logger.info(f"  Author: {author}")
                logger.info(f"  URL: {url}")

                normalized_post = {
                    "id": post_id,
                    "post_id": post_id,
                    "title": title,
                    "text": text,
                    "author": author,
                    "author_id": post.get("author_id") or post.get("user_id") or "",
                    "url": url,
                    "timestamp": timestamp,
                    "likes": post.get("likes", 0),
                    "comments_count": post.get("comments_count", 0),
                    "reposts": post.get("reposts", 0),
                    "location": post.get("location", ""),
                }

                status = db.upsert_post(normalized_post)
                if status == "skipped_date_filter":
                    logger.info("  Skipped - outside date window")
                    continue
                if status == "skipped_no_id":
                    logger.info("  Skipped - no usable post id")
                    continue

                logger.info(f"  Post stored: {status}")
                geo_region = detect_geo_region(text, normalized_post.get("location", ""))

                comments = []
                if url:
                    logger.info(f"  Fetching comments from: {url}")
                    comments = linkedin.fetch_comments(url, max_pages=MAX_COMMENT_PAGES)

                    for comment in comments:
                        c_id = (
                            comment.get("id")
                            or comment.get("comment_id")
                            or comment.get("review_id")
                            or comment.get("item_id")
                            or stable_id("comment", comment)
                        )
                        comment["id"] = c_id
                        c_status = db.upsert_comment(comment, post_id, geo_region=geo_region)
                        if c_status == "skipped_date_filter":
                            logger.debug("    Comment skipped - outside date window")
                        else:
                            logger.info(f"    Comment stored: {c_status}")

                    logger.info(f"  Total comments fetched: {len(comments)}")

                all_posts.append({
                    "post_id": post_id,
                    "title": title,
                    "text": text,
                    "author": author,
                    "author_id": normalized_post.get("author_id", ""),
                    "url": url,
                    "timestamp": timestamp,
                    "geo_region": geo_region,
                    "likes": normalized_post.get("likes", 0),
                    "comments_count": normalized_post.get("comments_count", 0),
                    "raw_data": post
                })

                for comment in comments:
                    all_comments.append({
                        "comment_id": comment.get("id", ""),
                        "post_id": post_id,
                        "author": comment.get("author", ""),
                        "author_id": comment.get("author_id", ""),
                        "text": comment.get("text", ""),
                        "likes": comment.get("likes", 0),
                        "timestamp": comment.get("timestamp", ""),
                        "geo_region": detect_geo_region(comment.get("text", "")) or geo_region,
                        "raw_data": comment
                    })

            except Exception as e:
                logger.error(f"  ERROR processing post: {e}")
                logger.error(f"  Post data: {json.dumps(post, indent=2, ensure_ascii=False)[:500]}")
                continue

            time.sleep(0.5)

    logger.info("\n" + "=" * 80)
    logger.info("LINKEDIN EXTRACTION COMPLETE")
    logger.info("=" * 80)

    if all_posts or all_comments:
        json_file = export_to_json(all_posts, all_comments, JSON_EXPORT_FILE)
        logger.info(f"JSON export completed: {json_file}")
    else:
        logger.warning(
            "No data to export to JSON. Check the [SEARCH] and [LINKEDIN] log "
            f"lines above, and inspect {DEBUG_DIR}/search_everywhere_raw.json "
            "if it was created -- that will show exactly what the API sent back."
        )

    db.close()

if __name__ == "__main__":
    main()