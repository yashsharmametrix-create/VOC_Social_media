"""
INSTAGRAM COMMENTS EXTRACTION (fixed)
Extracts posts and comments from Instagram via SocialCrawl.

Fixes applied vs. the original version (same bug family as the LinkedIn
script, plus one this version didn't guard against at all):

  1. `import time` was missing -> every run that processed at least one
     post crashed with NameError right after `db.upsert_post()`, before
     any real results ever showed up.

  2. `/v1/search/everywhere` was called with `"platforms": "instagram"`.
     That's not a real parameter -- the documented one is `sources`
     (e.g. sources=instagram) -- so the old code was searching ALL
     platforms and just keeping whatever came back.

  3. The old code had NO platform filter on the results at all -- every
     item /v1/search/everywhere returned (Reddit, YouTube, whatever)
     got stored straight into the Instagram DB. Added a filter that
     checks every plausible platform field/location, case-insensitively.

  4. Field extraction assumed a flat shape (post["caption"], post["author"],
     post["image_url"] ...). SocialCrawl's own published example response
     for a list endpoint shows items nested like:
         item["post"]["content"]["text"]
         item["post"]["content"]["media_urls"]
         item["post"]["id"] / item["post"]["url"]
     with author/engagement typically alongside as item["author"] /
     item["engagement"]. Extraction now tries that nested shape FIRST,
     then falls back to the old flat field names, so it works either way.

  5. `/v1/prism/comments` doesn't appear in SocialCrawl's published
     endpoint list. Since the real Instagram comments path is behind a
     login I don't have, the client now PROBES a list of plausible
     paths against your first real post URL and keeps whichever one
     returns 200 -- same approach that found the correct LinkedIn path
     for you. Watch the "trying ... -> status=..." log lines on your
     first run to see which one wins.

  6. Added a stable (hashlib-based) id fallback for posts/comments that
     don't expose a top-level id, and a 0-credit balance check at
     startup so a bad key fails loud instead of silently returning
     nothing.
"""

import requests
import json
import logging
import hashlib
import time
import os
from datetime import datetime
import os
import json
# ============================================================
# CONFIGURATION
# ============================================================
API_KEY = "sc_QPRRy3AT7j5xb5T5EuztzntY0rjsQynv9CEZpTarh2k"
BASE_URL = "https://www.socialcrawl.dev"

SEARCH_ENDPOINT_PATH = "/v1/search/everywhere"

# Tried in order on the first comments call of the run; whichever returns
# 200 first gets cached and reused for every call after that. Slash-nested
# form goes first because that's the pattern SocialCrawl uses elsewhere on
# their own site (e.g. /v1/linkedin/group/posts), "media" goes second
# because Instagram's own API calls posts "media".
COMMENTS_ENDPOINT_CANDIDATES = [
    "/v1/instagram/post/comments",
    "/v1/instagram/media/comments",
    "/v1/instagram/comments",
    "/v1/instagram/post-comments",
    "/v1/prism/comments",
]

# Search queries
TEST_QUERIES = [
    "LG AC",
    "LG Air Conditioner",
]

# Results per query
LIMIT = 5

# Database settings
DB_FILE = "instagram_comments.db"
LOG_FILE = f"instagram_comments_{datetime.now().strftime('%Y%m%d')}.log"

# Comment fetching settings
MAX_COMMENT_PAGES = 5

# Debug dumps -- first raw response per call type gets saved here so you
# can inspect the real field names SocialCrawl returns for your account.
DEBUG_DIR = "debug_raw_responses"

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
# DEBUG / ID HELPERS
# ============================================================
def dump_debug_json(name, payload):
    """Save a raw API response to disk so its real shape can be inspected."""
    try:
        os.makedirs(DEBUG_DIR, exist_ok=True)
        path = os.path.join(DEBUG_DIR, f"{name}.json")
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            logger.info(f"  [debug] saved raw response sample -> {path}")
    except Exception as e:
        logger.debug(f"  [debug] could not save debug dump: {e}")


def stable_id(prefix, obj):
    """Deterministic id fallback -- Python's hash() is randomized per
    process by default, so it would give a different fallback id (and
    therefore a duplicate row) on every single run."""
    digest = hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return f"{prefix}_{digest[:16]}"


def dig(d, *keys):
    """Safely walk a chain of nested dict keys, returning None if any
    level is missing or not a dict."""
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def first_truthy(*values):
    for v in values:
        if v:
            return v
    return None

# ============================================================
# DATABASE
# ============================================================
import sqlite3

class InstagramCommentsDB:
    def __init__(self, db_path):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        """Initialize database schema for Instagram comments."""
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS posts (
                post_id TEXT PRIMARY KEY,
                caption TEXT,
                author TEXT,
                author_id TEXT,
                image_url TEXT,
                video_url TEXT,
                url TEXT,
                timestamp TEXT,
                likes INTEGER,
                comments_count INTEGER,
                location TEXT,
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
                raw_json TEXT,
                fetched_at TEXT,
                FOREIGN KEY(post_id) REFERENCES posts(post_id)
            );

            CREATE INDEX IF NOT EXISTS idx_comments_post ON comments(post_id);
            CREATE INDEX IF NOT EXISTS idx_comments_author ON comments(author);
            CREATE INDEX IF NOT EXISTS idx_comments_timestamp ON comments(timestamp);
            """
        )
        self.conn.commit()

    def upsert_post(self, post):
        """Insert or update Instagram post. Expects an already-normalized
        dict (see normalize_post() in main), not a raw API item."""
        now = datetime.now().isoformat()
        post_id = post.get("post_id", "")

        if not post_id:
            logger.warning("No post ID found, skipping")
            return "skipped_no_id"

        row = self.conn.execute(
            "SELECT * FROM posts WHERE post_id = ?", (post_id,)
        ).fetchone()

        raw_json = json.dumps(post.get("raw_data", {}), ensure_ascii=False)

        if row is None:
            self.conn.execute(
                """
                INSERT INTO posts
                (post_id, caption, author, author_id, image_url, video_url,
                 url, timestamp, likes, comments_count, location, raw_json, fetched_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    post_id,
                    post.get("caption", ""),
                    post.get("author", ""),
                    post.get("author_id", ""),
                    post.get("image_url", ""),
                    post.get("video_url", ""),
                    post.get("url", ""),
                    post.get("timestamp", ""),
                    post.get("likes", 0),
                    post.get("comments_count", 0),
                    post.get("location", ""),
                    raw_json,
                    now,
                ),
            )
            self.conn.commit()
            return "new"

        self.conn.execute(
            """
            UPDATE posts SET
                caption=?, author=?, author_id=?, image_url=?, video_url=?,
                url=?, timestamp=?, likes=?, comments_count=?, location=?, raw_json=?, fetched_at=?
            WHERE post_id=?
            """,
            (
                post.get("caption", ""),
                post.get("author", ""),
                post.get("author_id", ""),
                post.get("image_url", ""),
                post.get("video_url", ""),
                post.get("url", ""),
                post.get("timestamp", ""),
                post.get("likes", 0),
                post.get("comments_count", 0),
                post.get("location", ""),
                raw_json,
                now,
                post_id,
            ),
        )
        self.conn.commit()
        return "updated"

    def upsert_comment(self, comment, post_id):
        """Insert or update comment. Expects an already-normalized dict."""
        now = datetime.now().isoformat()
        comment_id = comment.get("comment_id", "")

        if not comment_id:
            return "skipped_no_id"

        row = self.conn.execute(
            "SELECT comment_id FROM comments WHERE comment_id = ?", (comment_id,)
        ).fetchone()

        raw_json = json.dumps(comment.get("raw_data", {}), ensure_ascii=False)

        if row is None:
            self.conn.execute(
                """
                INSERT INTO comments
                (comment_id, post_id, author, author_id, text, likes,
                 timestamp, raw_json, fetched_at)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    comment_id,
                    post_id,
                    comment.get("author", ""),
                    comment.get("author_id", ""),
                    comment.get("text", ""),
                    comment.get("likes", 0),
                    comment.get("timestamp", ""),
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
# NORMALIZATION -- maps SocialCrawl's real (nested) response shape
# and the old flat shape, whichever is present, onto the DB's columns.
# ============================================================
def normalize_post(item):
    post_node = item.get("post") if isinstance(item.get("post"), dict) else {}
    # content = dig(post_node, "content") or dig(item, "content") or {}

    content = dig(post_node, "content") or dig(item, "content")

    if not isinstance(content, dict):
        content = {}

    # author_node = dig(post_node, "author") or dig(item, "author") or {}

    author_node = dig(post_node, "author") or dig(item, "author")

    if not isinstance(author_node, dict):
        author_node = {}
    # engagement = dig(post_node, "engagement") or dig(item, "engagement") or {}

    engagement = dig(post_node, "engagement") or dig(item, "engagement")

    if not isinstance(engagement, dict):
        engagement = {}

    post_id = first_truthy(
        post_node.get("id"), item.get("id"), item.get("post_id"), item.get("pk")
    ) or stable_id("instagram_post", item)

    caption = first_truthy(
        content.get("text"), item.get("caption"), item.get("text"),
        item.get("content"), item.get("snippet")
    ) or ""

    media_urls = content.get("media_urls")
    if isinstance(media_urls, list):
        image_url = media_urls[0] if media_urls else ""
    elif isinstance(media_urls, str):
        image_url = media_urls
    else:
        image_url = item.get("image_url", "")
    video_url = item.get("video_url", "") or (
        media_urls if isinstance(media_urls, str) and ".mp4" in media_urls else ""
    )

    author = first_truthy(
        author_node.get("username"), author_node.get("name"),
        item.get("author"), item.get("username")
    ) or "Unknown"
    author_id = first_truthy(author_node.get("id"), item.get("author_id")) or ""

    url = first_truthy(post_node.get("url"), item.get("url")) or ""

    timestamp = first_truthy(
        post_node.get("timestamp"), item.get("timestamp"),
        item.get("created_at"), item.get("published_at")
    ) or ""

    likes = first_truthy(engagement.get("likes"), item.get("likes")) or 0
    comments_count = first_truthy(
        engagement.get("comments"), engagement.get("comments_count"),
        item.get("comments_count")
    ) or 0

    return {
        "post_id": post_id,
        "caption": caption,
        "author": author,
        "author_id": author_id,
        "image_url": image_url,
        "video_url": video_url,
        "url": url,
        "timestamp": timestamp,
        "likes": likes,
        "comments_count": comments_count,
        "location": item.get("location", ""),
        "raw_data": item,
    }


def normalize_comment(raw_comment):
    author_node = raw_comment.get("author") if isinstance(raw_comment.get("author"), dict) else {}

    comment_id = first_truthy(
        raw_comment.get("id"), raw_comment.get("comment_id"), raw_comment.get("pk")
    ) or stable_id("instagram_comment", raw_comment)

    text = first_truthy(
        dig(raw_comment, "content", "text"), raw_comment.get("text"),
        raw_comment.get("content"), raw_comment.get("body")
    ) or ""

    author = first_truthy(
        author_node.get("username"), raw_comment.get("author")
    ) or "Unknown"
    author_id = first_truthy(author_node.get("id"), raw_comment.get("author_id")) or ""

    likes = first_truthy(
        dig(raw_comment, "engagement", "likes"), raw_comment.get("likes")
    ) or 0

    timestamp = first_truthy(
        raw_comment.get("timestamp"), raw_comment.get("created_at")
    ) or ""

    return {
        "comment_id": comment_id,
        "author": author,
        "author_id": author_id,
        "text": text,
        "likes": likes,
        "timestamp": timestamp,
        "raw_data": raw_comment,
    }

# ============================================================
# INSTAGRAM CLIENT
# ============================================================
class InstagramClient:
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
        Search Instagram posts using /v1/search/everywhere, scoped with
        `sources` (NOT `platforms`), then filtered client-side for items
        actually tagged as Instagram.
        """
        endpoint = f"{self.base_url}{SEARCH_ENDPOINT_PATH}"

        params = {
            "query": query,
            "sources": "instagram",   # documented param name, was "platforms" before
            "gl": "in",
            "limit": limit,
        }

        logger.info(f"Searching Instagram: {query}")
        logger.info(f"Endpoint: {endpoint}")
        logger.info(f"Params: {params}")

        try:
            resp = self.session.get(endpoint, params=params, timeout=60)
            logger.info(f"[SEARCH] status={resp.status_code}")

            if resp.status_code != 200:
                logger.error(f"Instagram search error: {resp.status_code} {resp.text[:500]}")
                return []

            data = resp.json()

            os.makedirs("json_responses", exist_ok=True)

            filename = f"json_responses/search_{query.replace(' ', '_')}.json"

            with open(filename, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            dump_debug_json("search_everywhere_raw", data)

            raw_items = None
            if isinstance(data.get("data"), dict):
                raw_items = data["data"].get("items")
            if raw_items is None:
                raw_items = data.get("results") or data.get("data") or []

            if not isinstance(raw_items, list):
                raw_items = []

            logger.info(f"[SEARCH] raw items returned: {len(raw_items)}")

            instagram_items = []
            for item in raw_items:
                candidates = [
                    item.get("platform"),
                    item.get("source"),
                    dig(item, "post", "platform"),
                    dig(item, "post", "source"),
                    dig(item, "metadata", "platform"),
                ]
                if any(str(c).lower() == "instagram" for c in candidates if c):
                    instagram_items.append(item)

            logger.info(
                f"[INSTAGRAM] Returned: {len(instagram_items)} items "
                f"(filtered from {len(raw_items)})"
            )

            if raw_items and not instagram_items:
                logger.warning(
                    "  Got results but none matched the Instagram filter -- "
                    f"check {DEBUG_DIR}/search_everywhere_raw.json to see the "
                    "real field names and adjust the filter in search_posts()."
                )

            return instagram_items

        except Exception as e:
            logger.error(f"Instagram search exception: {e}")
            return []

    def _discover_comments_endpoint(self, post_url):
        """
        Try each candidate path once with a real post URL and keep the
        first one that returns HTTP 200. Cached for the rest of the run.
        """
        if self._comments_endpoint:
            return self._comments_endpoint, None

        logger.info("  [COMMENTS] discovering the correct endpoint path...")
        for path in COMMENTS_ENDPOINT_CANDIDATES:
            endpoint = f"{self.base_url}{path}"
            try:
                resp = self.session.get(endpoint, params={"url": post_url}, timeout=30)
                logger.info(f"    trying {path} -> status={resp.status_code}")

                if resp.status_code == 200:
                    logger.info(f"  [COMMENTS] using endpoint: {path}")
                    self._comments_endpoint = path
                    data = resp.json()



                    dump_debug_json("post_comments_raw", data)
                    return path, data

                if resp.status_code != 404:
                    logger.info(f"      body: {resp.text[:300]}")

            except Exception as e:
                logger.warning(f"    {path} raised {e}")

        logger.error(
            "  None of the candidate comments endpoints returned 200. "
            f"Tried: {COMMENTS_ENDPOINT_CANDIDATES}. Log into your SocialCrawl "
            "dashboard -> API Reference -> Instagram -> 'Post Comments' to get "
            "the real path, then add it to COMMENTS_ENDPOINT_CANDIDATES at the "
            "top of this script (put it first in the list)."
        )
        return None, None

    def fetch_comments(self, post_url, max_pages=MAX_COMMENT_PAGES):
        """
        Fetch comments for an Instagram post. Probes candidate endpoints on
        the first call this run; every call after that reuses the winner.
        """
        all_comments = []
        cursor = None
        first_page_data = None

        if self._comments_endpoint is None:
            path, data = self._discover_comments_endpoint(post_url)
            if path is None:
                return []
            first_page_data = data

        endpoint = f"{self.base_url}{self._comments_endpoint}"

        for page in range(max_pages):
            try:
                if first_page_data is not None:
                    data = first_page_data
                    first_page_data = None
                else:
                    params = {"url": post_url}
                    if cursor:
                        params["cursor"] = cursor
                    resp = self.session.get(endpoint, params=params, timeout=30)
                    logger.info(f"  [COMMENTS] status={resp.status_code} (page {page + 1})")

                    if resp.status_code != 200:
                        logger.warning(f"Comments fetch error: {resp.status_code} {resp.text[:500]} for {post_url}")
                        break

                    data = resp.json()

                    post_id = post_url.rstrip("/").split("/")[-1]

                    filename = f"json_responses/comments_{post_id}_page{page+1}.json"

                    with open(filename, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
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
# MAIN
# ============================================================

ALL_DATA = []

def main():
    logger.info("=" * 80)
    logger.info("INSTAGRAM COMMENTS EXTRACTION")
    logger.info("=" * 80)

    db = InstagramCommentsDB(DB_FILE)
    instagram = InstagramClient(API_KEY, BASE_URL)

    if not instagram.check_credits():
        logger.error(
            "Could not confirm API key / credit balance -- check the "
            "[CREDITS] log line above before going further."
        )

    for query in TEST_QUERIES:
        logger.info(f"\n{'='*60}")
        logger.info(f"Query: {query}")
        logger.info(f"{'='*60}")

        posts = instagram.search_posts(query, limit=LIMIT)
        logger.info(f"Found {len(posts)} posts")

        for raw_post in posts:
            try:
                post = normalize_post(raw_post)

                logger.info(f"\nProcessing post: {post['caption'][:80]}...")
                logger.info(f"  Post ID: {post['post_id']}")
                logger.info(f"  Author: {post['author']}")
                logger.info(f"  URL: {post['url']}")

                status = db.upsert_post(post)
                if status == "skipped_no_id":
                    continue
                logger.info(f"  Post stored: {status}")

                if post["url"]:
                    logger.info(f"  Fetching comments from: {post['url']}")
                    raw_comments = instagram.fetch_comments(post["url"], max_pages=MAX_COMMENT_PAGES)

                    ALL_DATA.append({
                        "query": query,
                        "post": raw_post,
                        "comments": raw_comments
                    })

                    for raw_comment in raw_comments:
                        comment = normalize_comment(raw_comment)
                        c_status = db.upsert_comment(comment, post["post_id"])
                        logger.info(f"    Comment stored: {c_status}")

                    logger.info(f"  Total comments fetched: {len(raw_comments)}")

            except Exception as e:
                logger.error(f"  ERROR processing post: {e}")
                logger.error(f"  Post data: {json.dumps(raw_post, indent=2, ensure_ascii=False)[:500]}")
                continue

            time.sleep(0.5)

    logger.info("\n" + "=" * 80)
    logger.info("INSTAGRAM EXTRACTION COMPLETE")
    logger.info("=" * 80)
    os.makedirs("json_responses", exist_ok=True)
    with open("json_responses/all_instagram_data.json","w",encoding="utf-8") as f:
        json.dump(ALL_DATA,f,indent=2,ensure_ascii=False)
    logger.info(f"Saved {len(ALL_DATA)} posts to json_responses/all_instagram_data.json")
    db.close()

if __name__ == "__main__":
    main()