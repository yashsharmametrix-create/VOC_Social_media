"""
REDDIT COMMENTS EXTRACTION
Extracts comments and reviews from Reddit posts
"""

import requests
import json
import logging
from datetime import datetime

# ============================================================
# CONFIGURATION
# ============================================================
API_KEY = "sc_QPRRy3AT7j5xb5T5EuztzntY0rjsQynv9CEZpTarh2k"
BASE_URL = "https://www.socialcrawl.dev"

# Search queries
TEST_QUERIES = [
    "Blue Star",
    "Blue Star Conditioner",
]

# Results per query
LIMIT = 10

# Database settings
DB_FILE = "reddit_comments.db"
LOG_FILE = f"reddit_comments_{datetime.now().strftime('%Y%m%d')}.log"

# Comment fetching settings
MAX_COMMENT_PAGES = 5

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
# DATABASE
# ============================================================
import sqlite3

class RedditCommentsDB:
    def __init__(self, db_path):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        """Initialize database schema for Reddit comments."""
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS posts (
                post_id TEXT PRIMARY KEY,
                title TEXT,
                text TEXT,
                author TEXT,
                author_id TEXT,
                url TEXT,
                subreddit TEXT,
                timestamp TEXT,
                upvotes INTEGER,
                comment_count INTEGER,
                raw_json TEXT,
                fetched_at TEXT
            );

            CREATE TABLE IF NOT EXISTS comments (
                comment_id TEXT PRIMARY KEY,
                post_id TEXT,
                author TEXT,
                author_id TEXT,
                text TEXT,
                upvotes INTEGER,
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
        """Insert or update Reddit post."""
        now = datetime.now().isoformat()
        post_id = post.get("id") or post.get("post_id") or post.get("reddit_id", "")

        if not post_id:
            logger.warning("No post ID found, skipping")
            return

        row = self.conn.execute(
            "SELECT * FROM posts WHERE post_id = ?", (post_id,)
        ).fetchone()

        raw_json = json.dumps(post, ensure_ascii=False)

        if row is None:
            self.conn.execute(
                """
                INSERT INTO posts
                (post_id, title, text, author, author_id, url, subreddit,
                 timestamp, upvotes, comment_count, raw_json, fetched_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    post_id,
                    post.get("title", ""),
                    post.get("text", ""),
                    post.get("author", ""),
                    post.get("author_id", ""),
                    post.get("url", ""),
                    post.get("subreddit", ""),
                    post.get("timestamp", ""),
                    post.get("upvotes", 0),
                    post.get("comment_count", 0),
                    raw_json,
                    now,
                ),
            )
            self.conn.commit()
            return "new"

        # Update post
        self.conn.execute(
            """
            UPDATE posts SET
                title=?, text=?, author=?, author_id=?, url=?, subreddit=?,
                timestamp=?, upvotes=?, comment_count=?, raw_json=?, fetched_at=?
            WHERE post_id=?
            """,
            (
                post.get("title", ""),
                post.get("text", ""),
                post.get("author", ""),
                post.get("author_id", ""),
                post.get("url", ""),
                post.get("subreddit", ""),
                post.get("timestamp", ""),
                post.get("upvotes", 0),
                post.get("comment_count", 0),
                raw_json,
                now,
                post_id,
            ),
        )
        self.conn.commit()
        return "updated"

    def upsert_comment(self, comment, post_id):
        """Insert or update comment."""
        now = datetime.now().isoformat()
        comment_id = comment.get("id") or comment.get("comment_id") or comment.get("review_id", "")

        if not comment_id:
            return

        row = self.conn.execute(
            "SELECT comment_id FROM comments WHERE comment_id = ?", (comment_id,)
        ).fetchone()

        raw_json = json.dumps(comment, ensure_ascii=False)

        if row is None:
            self.conn.execute(
                """
                INSERT INTO comments
                (comment_id, post_id, author, author_id, text, upvotes,
                 timestamp, raw_json, fetched_at)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    comment_id,
                    post_id,
                    comment.get("author", ""),
                    comment.get("author_id", ""),
                    comment.get("text", ""),
                    comment.get("upvotes", 0),
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
# REDDIT CLIENT
# ============================================================
class RedditClient:
    def __init__(self, api_key, base_url):
        self.api_key = api_key
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            "x-api-key": api_key,
            "Content-Type": "application/json"
        })

    def search_posts(self, query, limit=10):
        """
        Search Reddit posts using native Reddit endpoint.
        Target Indian subreddits specifically.
        """
        endpoint = f"{self.base_url}/v1/reddit/search"

        # Target Indian subreddits
        indian_query = f"{query} (subreddit:india OR subreddit:indiasocial OR subreddit:AskIndia OR subreddit:IndiaNews)"

        params = {
            "query": indian_query,
            "limit": limit,
            "sort": "relevance"
        }

        logger.info(f"Searching Reddit: {query}")
        logger.info(f"Query: {indian_query}")

        try:
            resp = self.session.get(endpoint, params=params, timeout=60)
            if resp.status_code != 200:
                logger.error(f"Reddit search error: {resp.status_code} {resp.text[:200]}")
                return []

            data = resp.json()
            raw_items = data.get("data", {}).get("items") or data.get("data") or []

            if not isinstance(raw_items, list):
                raw_items = []

            logger.info(f"Found {len(raw_items)} Reddit posts")
            return raw_items

        except Exception as e:
            logger.error(f"Reddit search exception: {e}")
            return []

    def fetch_comments(self, post_url, max_pages=MAX_COMMENT_PAGES):
        """
        Fetch comments for a Reddit post using SocialCrawl Prism.
        """
        endpoint = f"{self.base_url}/v1/prism/comments"

        all_comments = []
        cursor = None

        for page in range(max_pages):
            params = {"url": post_url}
            if cursor:
                params["cursor"] = cursor

            try:
                resp = self.session.get(endpoint, params=params, timeout=30)
                if resp.status_code != 200:
                    logger.warning(f"Comments fetch error: {resp.status_code} for {post_url}")
                    break

                data = resp.json()
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
def main():
    logger.info("=" * 80)
    logger.info("REDDIT COMMENTS EXTRACTION")
    logger.info("=" * 80)

    db = RedditCommentsDB(DB_FILE)
    reddit = RedditClient(API_KEY, BASE_URL)

    for query in TEST_QUERIES:
        logger.info(f"\n{'='*60}")
        logger.info(f"Query: {query}")
        logger.info(f"{'='*60}")

        # Search for Reddit posts
        posts = reddit.search_posts(query, limit=LIMIT)

        for post in posts:
            # Normalize post data
            post_id = post.get("id") or post.get("post_id", "")
            if not post_id:
                continue

            logger.info(f"\nProcessing post: {post.get('title', '')[:80]}...")

            # Upsert post to database
            status = db.upsert_post(post)
            logger.info(f"  Post stored: {status}")

            # Fetch comments
            post_url = post.get("url", "")
            if post_url:
                logger.info(f"  Fetching comments from: {post_url}")
                comments = reddit.fetch_comments(post_url, max_pages=MAX_COMMENT_PAGES)

                for comment in comments:
                    comment_id = comment.get("id") or comment.get("comment_id", "")
                    if comment_id:
                        status = db.upsert_comment(comment, post_id)
                        logger.info(f"    Comment stored: {status}")

                logger.info(f"  Total comments fetched: {len(comments)}")

            time.sleep(0.5)

    logger.info("\n" + "=" * 80)
    logger.info("REDDIT EXTRACTION COMPLETE")
    logger.info("=" * 80)
    db.close()

if __name__ == "__main__":
    main()
