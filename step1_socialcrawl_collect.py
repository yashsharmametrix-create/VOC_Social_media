# """
# INDIAN SOCIAL LISTENING - SOCIAL PLATFORMS ONLY, DATE + GEO AWARE
# Platforms: reddit, twitter (X), instagram, facebook, linkedin

# KEY FEATURES:
# 1. STRICT PLATFORM FILTER - Only these 5 platforms are allowed
# 2. PERIOD WISE - Captures exact timestamp of when posts/comments were made
# 3. GEOGRAPHY WISE - Tags posts/comments with Indian state/region
# 4. USER ID EXTRACTION - Extracts native platform user IDs from author data
# 5. IMPROVED QUERY TARGETING - Optimized for Indian social media content
# """

# import json
# import time
# import logging
# import hashlib
# import sqlite3
# import requests
# from datetime import datetime
# from pathlib import Path

# # ============================================================
# # CONFIGURATION
# # ============================================================
# API_KEY = "sc_QPRRy3AT7j5xb5T5EuztzntY0rjsQynv9CEZpTarh2k"
# BASE_URL = "https://www.socialcrawl.dev"

# # Search queries - optimized for Indian market
# TEST_QUERIES = [
#     "LG AC",
#     "LG Air Conditioner",
    
# ]

# # Results per query per platform - increased for better coverage
# LIMIT = 10

# # STRICT PLATFORM ALLOWLIST - ONLY THESE PLATFORMS ARE ALLOWED
# ALLOWED_PLATFORMS = {"reddit", "twitter", "instagram", "facebook", "linkedin"}

# # Native search platforms (have their own endpoints)
# NATIVE_SEARCH_PLATFORMS = ["reddit", "twitter"]
# # Instagram, Facebook, LinkedIn use the everywhere endpoint
# EVERYWHERE_SCOPED_PLATFORMS = ["instagram", "facebook", "linkedin"]

# # Period filter - set to None to capture all time periods
# # Format: "YYYY-MM-DD"
# DATE_FROM = None     # e.g., "2026-07-01"
# DATE_TO = None       # e.g., "2026-07-31"

# DB_FILE = "social_listening.db"
# RUN_EXPORT_DIR = "runs"
# LOG_FILE = f"social_crawl_{datetime.now().strftime('%Y%m%d')}.log"

# # Comment fetching settings
# FETCH_FULL_COMMENTS = True
# ALWAYS_REFRESH_COMMENTS = True
# COMMENT_FETCH_DAYS = 7
# MAX_COMMENT_PAGES = 20

# # ============================================================
# # LOGGING
# # ============================================================
# file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
# file_handler.setLevel(logging.INFO)
# stream_handler = logging.StreamHandler()
# stream_handler.setLevel(logging.INFO)
# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s - %(levelname)s - %(message)s",
#     handlers=[file_handler, stream_handler],
# )
# logger = logging.getLogger(__name__)

# # ============================================================
# # GEOGRAPHY DATA - ALL INDIAN STATES AND MAJOR CITIES
# # ============================================================
# INDIA_GEO_KEYWORDS = [
#     # States & UTs
#     "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh",
#     "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka",
#     "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya",
#     "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim",
#     "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand",
#     "West Bengal", "Delhi", "Jammu and Kashmir", "Ladakh", "Puducherry",
#     "Chandigarh", "Andaman and Nicobar", "Dadra and Nagar Haveli",
#     "Lakshadweep",
#     # Major cities (helps identify region when state name not mentioned)
#     "Mumbai", "Bengaluru", "Bangalore", "Chennai", "Kolkata", "Hyderabad",
#     "Pune", "Ahmedabad", "Jaipur", "Lucknow", "Surat", "Kanpur", "Nagpur",
#     "Indore", "Bhopal", "Patna", "Vadodara", "Ludhiana", "Agra", "Nashik",
#     "Coimbatore", "Kochi", "Thiruvananthapuram", "Guwahati", "Noida",
#     "Gurugram", "Gurgaon", "Faridabad", "Meerut", "Rajkot", "Vijayawada",
#     "Jodhpur", "Laxmi Nagar", "Whitefield", "Electronic City", "Koramangala",
#     "Saket", "Connaught Place", "Rajpath", "Karol Bagh", "Chandni Chowk",
#     "Santacruz", "Andheri", "Borivali", "Dahisar", "Bandra",
# ]

# def detect_geo_region(*text_blobs):
#     """
#     Best-effort India region tag from free text.
#     Searches for Indian state names, cities, and regions.
#     Returns the matched region name or empty string.
#     """
#     combined = " ".join([t for t in text_blobs if t]).lower()
#     for region in INDIA_GEO_KEYWORDS:
#         if region.lower() in combined:
#             return region
#     return ""

# # ============================================================
# # TIMESTAMP HELPERS
# # ============================================================
# def parse_timestamp(ts):
#     """Parse timestamp from various formats to datetime object."""
#     if not ts:
#         return None
#     try:
#         return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
#     except Exception:
#         return None

# def within_date_window(ts_str):
#     """
#     Check if timestamp falls within the specified date window.
#     Returns True if no date window is set, or if timestamp is valid and within range.
#     Missing/unparseable timestamps are kept (not dropped).
#     """
#     if not DATE_FROM and not DATE_TO:
#         return True

#     dt = parse_timestamp(ts_str)
#     if dt is None:
#         return True

#     dt_naive = dt.replace(tzinfo=None)

#     if DATE_FROM and dt_naive < datetime.fromisoformat(DATE_FROM):
#         return False

#     if DATE_TO:
#         try:
#             dt_end = datetime.fromisoformat(DATE_TO).replace(hour=23, minute=59, second=59)
#             if dt_naive > dt_end:
#                 return False
#         except ValueError:
#             pass

#     return True

# # ============================================================
# # USER ID EXTRACTION HELPERS
# # ============================================================
# def extract_author_id(author_obj):
#     """
#     Extract native platform user ID from author object.
#     Checks multiple field names used by different platforms.
#     Returns empty string if no ID found.
#     """
#     if not isinstance(author_obj, dict):
#         return ""

#     # Common field names across platforms
#     for key in ("id", "user_id", "pk", "author_id", "id_str", "uid", "user_id_str"):
#         val = author_obj.get(key)
#         if val:
#             return str(val)

#     return ""

# # ============================================================
# # ITEM IDENTIFICATION HELPERS
# # ============================================================
# def make_mention_id(platform, item):
#     """Create a unique identifier for each mention."""
#     native_id = (item.get("id") or "").strip()
#     if native_id:
#         return f"{platform}:{native_id}"

#     # Fallback: use URL and author as basis
#     basis = item.get("url") or f"{item.get('title', '')}|{item.get('author', '')}"
#     digest = hashlib.sha256(f"{platform}|{basis}".encode("utf-8")).hexdigest()[:20]
#     return f"{platform}:h{digest}"

# def make_fingerprint(item):
#     """Create a fingerprint for change detection."""
#     engagement = item.get("engagement", {}) or {}
#     basis = {
#         "text": item.get("text", ""),
#         "title": item.get("title", ""),
#         "likes": engagement.get("likes"),
#         "comments": engagement.get("comments") or engagement.get("commentCount"),
#         "shares": engagement.get("shares"),
#         "views": engagement.get("views"),
#     }
#     return hashlib.sha256(
#         json.dumps(basis, sort_keys=True, ensure_ascii=False).encode("utf-8")
#     ).hexdigest()

# def make_comment_id(mention_id, raw_comment):
#     """Create a unique identifier for each comment."""
#     native_id = (
#         raw_comment.get("id")
#         or raw_comment.get("comment_id")
#         or raw_comment.get("review_id")
#         or ""
#     )
#     if native_id:
#         return str(native_id)

#     # Fallback: use author name, text, and timestamp
#     author = raw_comment.get("author", {})
#     author_name = author.get("username") if isinstance(author, dict) else str(author)
#     text = raw_comment.get("text") or (raw_comment.get("content", {}) or {}).get("text", "")
#     ts = raw_comment.get("published_at") or raw_comment.get("created_at") or ""
#     basis = f"{mention_id}|{author_name}|{text}|{ts}"
#     return f"h{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:20]}"

# # ============================================================
# # ITEM NORMALIZATION
# # ============================================================
# def normalize_item(raw_item, platform_hint, query):
#     """
#     Normalize raw API response into a consistent format.
#     Includes platform, timestamp, geo_region, and author_id.
#     """
#     if not isinstance(raw_item, dict):
#         return None

#     # Handle both 'platform' and 'source' field names from different API endpoints
#     # Everywhere endpoint uses 'source', native endpoints use 'platform'
#     source_platform = (
#         raw_item.get("platform") or
#         raw_item.get("source") or
#         platform_hint or
#         ""
#     ).lower()

#     # For everywhere endpoint, the 'source' field contains the actual platform
#     # but we need to map it to our allowed platforms list
#     if source_platform and source_platform not in ALLOWED_PLATFORMS:
#         # Map known source names to our platform names
#         source_map = {
#             "instagram": "instagram",
#             "facebook": "facebook",
#             "linkedin": "linkedin",
#             "twitter": "twitter",
#             "reddit": "reddit",
#         }
#         source_platform = source_map.get(source_platform, source_platform)

#     post = raw_item.get("post", raw_item) if isinstance(raw_item.get("post", raw_item), dict) else raw_item

#     content = post.get("content", {})
#     content = content if isinstance(content, dict) else {}
#     author = post.get("author", {})
#     author = author if isinstance(author, dict) else {}

#     # Extract text content
#     text = (
#         content.get("text")
#         or post.get("title")
#         or post.get("snippet")
#         or post.get("description")
#         or "No text"
#     )

#     # Extract author information
#     author_name = (
#         author.get("username")
#         or author.get("display_name")
#         or author.get("name")
#         or "Unknown"
#     )
#     author_id = extract_author_id(author)
#     author_location = author.get("location") or author.get("bio_location") or ""

#     # Extract engagement data
#     engagement = post.get("engagement", {})
#     engagement = engagement if isinstance(engagement, dict) else {}

#     # Extract timestamp
#     timestamp = post.get("published_at") or post.get("created_at") or ""

#     # Detect Indian region from text and location
#     geo_region = detect_geo_region(text, author_location)

#     return {
#         "_platform": source_platform,
#         "_query": query,
#         "title": post.get("title", text[:100] if text else ""),
#         "text": text,
#         "author": author_name,
#         "author_id": author_id,  # Native platform user ID
#         "url": post.get("url", ""),
#         "id": post.get("id", ""),
#         "timestamp": timestamp,  # Period-wise data
#         "engagement": engagement,
#         "geo_region": geo_region,  # Geography-wise data
#         "_raw": post,
#     }

# # ============================================================
# # DATABASE
# # ============================================================
# class MentionStore:
#     def __init__(self, db_path):
#         self.conn = sqlite3.connect(db_path)
#         self.conn.row_factory = sqlite3.Row
#         self._init_schema()

#     def _init_schema(self):
#         """Initialize database schema with all required tables and indexes."""
#         self.conn.executescript(
#             """
#             CREATE TABLE IF NOT EXISTS mentions (
#                 mention_id           TEXT PRIMARY KEY,
#                 platform             TEXT,
#                 query                TEXT,
#                 title                TEXT,
#                 text                 TEXT,
#                 author               TEXT,
#                 author_id            TEXT,           -- Native platform user ID
#                 url                  TEXT,
#                 timestamp            TEXT,           -- Period-wise data
#                 geo_region           TEXT,           -- Geography-wise data
#                 engagement_json      TEXT,
#                 raw_json             TEXT,
#                 first_seen           TEXT,
#                 last_seen            TEXT,
#                 last_updated         TEXT
#             );

#             CREATE TABLE IF NOT EXISTS mention_history (
#                 id              INTEGER PRIMARY KEY AUTOINCREMENT,
#                 mention_id      TEXT,
#                 snapshot_json   TEXT,
#                 recorded_at     TEXT
#             );

#             CREATE TABLE IF NOT EXISTS comments (
#                 comment_id      TEXT PRIMARY KEY,
#                 mention_id      TEXT,
#                 platform        TEXT,
#                 author          TEXT,
#                 author_id       TEXT,           -- Native platform user ID
#                 text            TEXT,
#                 timestamp       TEXT,           -- Period-wise data
#                 geo_region      TEXT,           -- Geography-wise data
#                 engagement_json TEXT,
#                 raw_json        TEXT,
#                 first_seen      TEXT,
#                 last_seen       TEXT
#             );

#             CREATE TABLE IF NOT EXISTS meta (
#                 key   TEXT PRIMARY KEY,
#                 value TEXT
#             );
#             """
#         )

#         # Schema migration for newer columns
#         required_columns = {
#             "author_id": "TEXT DEFAULT ''",
#             "geo_region": "TEXT DEFAULT ''",
#             "fingerprint": "TEXT DEFAULT ''",
#             "last_comment_fetch": "TEXT",
#         }
#         existing_columns = [
#             row[1] for row in self.conn.execute("PRAGMA table_info(mentions)").fetchall()
#         ]
#         for col, col_def in required_columns.items():
#             if col not in existing_columns:
#                 self.conn.execute(f"ALTER TABLE mentions ADD COLUMN {col} {col_def}")
#                 logger.info(f"Added missing column '{col}' to mentions table")

#         # Create indexes for efficient querying
#         self.conn.executescript(
#             """
#             CREATE INDEX IF NOT EXISTS idx_comments_mention_id ON comments(mention_id);
#             CREATE INDEX IF NOT EXISTS idx_mentions_platform ON mentions(platform);
#             CREATE INDEX IF NOT EXISTS idx_mentions_timestamp ON mentions(timestamp);
#             CREATE INDEX IF NOT EXISTS idx_mentions_geo ON mentions(geo_region);
#             CREATE INDEX IF NOT EXISTS idx_mentions_author_id ON mentions(author_id);
#             CREATE INDEX IF NOT EXISTS idx_comments_author_id ON comments(author_id);
#             """
#         )
#         self.conn.commit()

#     def upsert_mention(self, item):
#         """Insert or update mention in database. Returns 'new', 'updated', or 'unchanged'."""
#         now = datetime.now().isoformat()
#         mention_id = item["mention_id"]
#         fingerprint = item["fingerprint"]

#         row = self.conn.execute(
#             "SELECT * FROM mentions WHERE mention_id = ?", (mention_id,)
#         ).fetchone()

#         engagement_json = json.dumps(item.get("engagement", {}), ensure_ascii=False)
#         raw_json = json.dumps(item.get("_raw", {}), ensure_ascii=False)

#         if row is None:
#             self.conn.execute(
#                 """
#                 INSERT INTO mentions
#                 (mention_id, platform, query, title, text, author, author_id, url,
#                  timestamp, geo_region, engagement_json, fingerprint, raw_json,
#                  first_seen, last_seen, last_updated, last_comment_fetch)
#                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
#                 """,
#                 (
#                     mention_id, item.get("_platform", ""), item.get("_query", ""),
#                     item.get("title", ""), item.get("text", ""), item.get("author", ""),
#                     item.get("author_id", ""), item.get("url", ""), item.get("timestamp", ""),
#                     item.get("geo_region", ""), engagement_json, fingerprint, raw_json,
#                     now, now, now, None,
#                 ),
#             )
#             self.conn.commit()
#             return "new"

#         if row["fingerprint"] == fingerprint:
#             self.conn.execute(
#                 "UPDATE mentions SET last_seen = ? WHERE mention_id = ?", (now, mention_id)
#             )
#             self.conn.commit()
#             return "unchanged"

#         # Record history for changes
#         self.conn.execute(
#             "INSERT INTO mention_history (mention_id, snapshot_json, recorded_at) VALUES (?,?,?)",
#             (mention_id, json.dumps(dict(row), ensure_ascii=False), now),
#         )

#         # Update the mention
#         self.conn.execute(
#             """
#             UPDATE mentions SET
#                 title=?, text=?, author=?, author_id=?, url=?, timestamp=?, geo_region=?,
#                 engagement_json=?, fingerprint=?, raw_json=?, last_seen=?, last_updated=?
#             WHERE mention_id=?
#             """,
#             (
#                 item.get("title", ""), item.get("text", ""), item.get("author", ""),
#                 item.get("author_id", ""), item.get("url", ""), item.get("timestamp", ""),
#                 item.get("geo_region", ""), engagement_json, fingerprint, raw_json,
#                 now, now, mention_id,
#             ),
#         )
#         self.conn.commit()
#         return "updated"

#     def get_last_comment_fetch(self, mention_id):
#         """Get the last comment fetch timestamp for a mention."""
#         row = self.conn.execute(
#             "SELECT last_comment_fetch FROM mentions WHERE mention_id = ?", (mention_id,)
#         ).fetchone()
#         return row["last_comment_fetch"] if row else None

#     def update_last_comment_fetch(self, mention_id, timestamp):
#         """Update the last comment fetch timestamp for a mention."""
#         self.conn.execute(
#             "UPDATE mentions SET last_comment_fetch = ? WHERE mention_id = ?",
#             (timestamp, mention_id),
#         )
#         self.conn.commit()

#     def upsert_comment(self, comment):
#         """Insert or update comment in database."""
#         now = datetime.now().isoformat()
#         comment_id = comment["comment_id"]
#         row = self.conn.execute(
#             "SELECT comment_id FROM comments WHERE comment_id = ?", (comment_id,)
#         ).fetchone()

#         if row is None:
#             self.conn.execute(
#                 """
#                 INSERT INTO comments
#                 (comment_id, mention_id, platform, author, author_id, text, timestamp,
#                  geo_region, engagement_json, raw_json, first_seen, last_seen)
#                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
#                 """,
#                 (
#                     comment_id, comment["mention_id"], comment.get("_platform", ""),
#                     comment.get("author", ""), comment.get("author_id", ""),
#                     comment.get("text", ""), comment.get("timestamp", ""),
#                     comment.get("geo_region", ""),
#                     json.dumps(comment.get("engagement", {}), ensure_ascii=False),
#                     json.dumps(comment.get("_raw", {}), ensure_ascii=False),
#                     now, now,
#                 ),
#             )
#             self.conn.commit()
#             return "new"

#         self.conn.execute("UPDATE comments SET last_seen = ? WHERE comment_id = ?", (now, comment_id))
#         self.conn.commit()
#         return "unchanged"

#     def set_meta(self, key, value):
#         """Set or update metadata."""
#         self.conn.execute(
#             "INSERT INTO meta (key, value) VALUES (?, ?) "
#             "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
#             (key, value),
#         )
#         self.conn.commit()

#     def close(self):
#         """Close database connection."""
#         self.conn.close()

# # ============================================================
# # SOCIALCRAWL CLIENT
# # ============================================================
# class SocialCrawlClient:
#     def __init__(self, api_key, base_url):
#         self.api_key = api_key
#         self.base_url = base_url
#         self.session = requests.Session()
#         self.session.headers.update({"x-api-key": api_key, "Content-Type": "application/json"})

#     def check_balance(self):
#         """Check API credit balance."""
#         try:
#             resp = self.session.get(f"{self.base_url}/v1/credits/balance", timeout=10)
#             data = resp.json()
#             balance = (
#                 data.get("data", {}).get("balance")
#                 or data.get("credits_remaining")
#                 or data.get("balance")
#             )
#             if balance is not None:
#                 logger.info(f"Current credit balance: {balance}")
#                 return balance
#             logger.warning(f"Balance not found: {data}")
#             return -1
#         except Exception as e:
#             logger.error(f"Balance check failed: {e}")
#             return -1

#     def _run_search(self, endpoint, params, platform_hint, query, timeout=30, drop_counter=None):
#         """Execute search and apply strict platform filtering."""
#         logger.info(f"Search: {platform_hint.upper()} | Query: {query}")
#         logger.info(f"Endpoint: {endpoint}")
#         logger.info(f"Params: {params}")

#         try:
#             resp = self.session.get(endpoint, params=params, timeout=timeout)
#             if resp.status_code != 200:
#                 logger.error(f"Search error [{platform_hint}]: {resp.status_code} {resp.text[:200]}")
#                 return []

#             data = resp.json()
#             raw_items = (
#                 data.get("data", {}).get("items")
#                 or data.get("data")
#                 or data.get("items")
#                 or data.get("results")
#                 or []
#             )
#             if not isinstance(raw_items, list):
#                 raw_items = []

#             normalized = []
#             dropped_count = 0

#             for raw in raw_items:
#                 item = normalize_item(raw, platform_hint, query)
#                 if item is None:
#                     continue

#                 # STRICT PLATFORM FILTER - Only allow the 5 platforms
#                 if item["_platform"] not in ALLOWED_PLATFORMS:
#                     dropped_count += 1
#                     if drop_counter:
#                         drop_counter[item["_platform"]] = drop_counter.get(item["_platform"], 0) + 1
#                     continue

#                 # Apply date window filter
#                 if within_date_window(item["timestamp"]):
#                     normalized.append(item)

#             logger.info(f"[{platform_hint.upper()}] Returned: {len(normalized)} items (dropped: {dropped_count})")
#             return normalized

#         except requests.exceptions.ReadTimeout:
#             logger.warning(f"Timeout on {platform_hint}")
#             return []
#         except Exception as e:
#             logger.error(f"Exception on {platform_hint}: {e}")
#             return []

#     def fetch_reddit(self, query, limit=10, drop_counter=None):
#         """Fetch Reddit posts with Indian subreddit targeting."""
#         endpoint = f"{self.base_url}/v1/reddit/search"
#         # Target Indian subreddits specifically
#         indian_query = f"{query} (subreddit:india OR subreddit:indiasocial OR subreddit:AskIndia OR subreddit:IndiaNews)"
#         params = {"query": indian_query, "limit": limit, "sort": "relevance"}
#         return self._run_search(endpoint, params, "reddit", query, timeout=60, drop_counter=drop_counter)

#     def fetch_twitter(self, query, limit=10, drop_counter=None):
#         """Fetch Twitter/X posts with India targeting using everywhere endpoint."""
#         # Use everywhere endpoint for Twitter (native endpoint doesn't exist)
#         endpoint = f"{self.base_url}/v1/search/everywhere"
#         params = {
#             "query": query,
#             "platforms": "twitter",
#             "gl": "in",  # Target India
#             "limit": limit
#         }
#         return self._run_search(endpoint, params, "twitter", query, timeout=30, drop_counter=drop_counter)

#     def fetch_everywhere_scoped(self, query, platforms, limit=10, drop_counter=None):
#         """
#         Fetch from Instagram, Facebook, LinkedIn using the everywhere endpoint.
#         Scopes to India with gl=IN parameter.
#         """
#         endpoint = f"{self.base_url}/v1/search/everywhere"
#         params = {
#             "query": query,
#             "platforms": ",".join(platforms),
#             "gl": "in",  # Target India geographically
#             "limit": limit,
#         }
#         return self._run_search(endpoint, params, "everywhere", query, timeout=45, drop_counter=drop_counter)

#     def fetch_comments_prism(self, post_url, max_pages=MAX_COMMENT_PAGES):
#         """Fetch all comments for a post using SocialCrawl Prism."""
#         endpoint = f"{self.base_url}/v1/prism/comments"
#         all_comments = []
#         cursor = None

#         for page in range(max_pages):
#             params = {"url": post_url}
#             if cursor:
#                 params["cursor"] = cursor

#             try:
#                 resp = self.session.get(endpoint, params=params, timeout=30)
#             except Exception as e:
#                 logger.error(f"Prism comments fetch error: {e}")
#                 break

#             if resp.status_code != 200:
#                 logger.warning(f"Prism comments {resp.status_code} for {post_url}")
#                 break

#             data = resp.json()
#             payload = data.get("data", {}) if isinstance(data.get("data"), dict) else {}
#             items = payload.get("items") or data.get("data") or []
#             if not isinstance(items, list):
#                 items = []
#             all_comments.extend(items)

#             cursor = payload.get("next_cursor")
#             has_more = payload.get("has_more")
#             if not cursor or not has_more:
#                 break
#             time.sleep(0.3)

#         return all_comments

# # ============================================================
# # MAIN WORKFLOW
# # ============================================================
# def main():
#     logger.info("=" * 80)
#     logger.info("INDIAN SOCIAL LISTENING - FB / IG / X / REDDIT / LINKEDIN ONLY")
#     logger.info("=" * 80)
#     logger.info(f"Allowed Platforms (Strict Filter): {', '.join(sorted(ALLOWED_PLATFORMS))}")
#     logger.info(f"Native Search: {', '.join(NATIVE_SEARCH_PLATFORMS)}")
#     logger.info(f"Everywhere Scoped: {', '.join(EVERYWHERE_SCOPED_PLATFORMS)}")
#     logger.info(f"Queries: {', '.join(TEST_QUERIES)}")
#     logger.info(f"Date Window: {DATE_FROM or '(all time)'} to {DATE_TO or '(all time)'}")
#     logger.info(f"Results per query: {LIMIT}")
#     logger.info(f"Comments: {'ALWAYS refreshed every run' if ALWAYS_REFRESH_COMMENTS else f'throttled to every {COMMENT_FETCH_DAYS}d'}")
#     logger.info("=" * 80)

#     Path(RUN_EXPORT_DIR).mkdir(exist_ok=True)
#     store = MentionStore(DB_FILE)
#     client = SocialCrawlClient(API_KEY, BASE_URL)

#     balance = client.check_balance()
#     if balance == 0:
#         logger.critical("No credits. Aborting.")
#         store.close()
#         return

#     # Check if we have enough credits for everywhere endpoint
#     include_everywhere = True
#     if balance is not None and balance != -1 and balance < 20:
#         logger.warning("Skipping Instagram/Facebook/LinkedIn (everywhere call needs ~20 credits)")
#         include_everywhere = False

#     new_items, updated_items, unchanged_items = [], [], []
#     comments_fetched = 0
#     platform_stats = {}
#     dropped_offplatform = {}

#     for query in TEST_QUERIES:
#         logger.info(f"\n{'='*60}")
#         logger.info(f"Processing Query: {query}")
#         logger.info(f"{'='*60}")

#         all_items = []

#         # Fetch from Reddit
#         logger.info(f"\nFetching from Reddit...")
#         reddit_items = client.fetch_reddit(query, limit=LIMIT, drop_counter=dropped_offplatform)
#         all_items.extend(reddit_items)
#         logger.info(f"Reddit: {len(reddit_items)} items")

#         # Fetch from Twitter/X
#         logger.info(f"\nFetching from Twitter/X...")
#         twitter_items = client.fetch_twitter(query, limit=LIMIT, drop_counter=dropped_offplatform)
#         all_items.extend(twitter_items)
#         logger.info(f"Twitter/X: {len(twitter_items)} items")

#         # Fetch from Instagram, Facebook, LinkedIn
#         if include_everywhere:
#             logger.info(f"\nFetching from Instagram, Facebook, LinkedIn...")
#             everywhere_items = client.fetch_everywhere_scoped(
#                 query, EVERYWHERE_SCOPED_PLATFORMS, limit=LIMIT, drop_counter=dropped_offplatform
#             )
#             all_items.extend(everywhere_items)
#             logger.info(f"Instagram/FB/LinkedIn: {len(everywhere_items)} items")

#         # Process each item
#         for item in all_items:
#             # Double-check platform is in allowlist
#             assert item["_platform"] in ALLOWED_PLATFORMS, f"Platform {item['_platform']} not in allowlist!"

#             platform_stats[item["_platform"]] = platform_stats.get(item["_platform"], 0) + 1

#             # Create unique identifiers
#             item["mention_id"] = make_mention_id(item["_platform"], item)
#             item["fingerprint"] = make_fingerprint(item)

#             # Store in database
#             status = store.upsert_mention(item)
#             if status == "new":
#                 new_items.append(item)
#             elif status == "updated":
#                 updated_items.append(item)
#             else:
#                 unchanged_items.append(item)

#             # Fetch comments if enabled
#             if FETCH_FULL_COMMENTS and item.get("url"):
#                 comment_count = (item.get("engagement") or {}).get("comments") or 0
#                 if comment_count:
#                     # Decide whether to fetch comments
#                     should_fetch = False
#                     if ALWAYS_REFRESH_COMMENTS:
#                         should_fetch = True
#                     elif status in ("new", "updated"):
#                         should_fetch = True
#                     else:
#                         last_fetch = store.get_last_comment_fetch(item["mention_id"])
#                         if last_fetch is None:
#                             should_fetch = True
#                         else:
#                             try:
#                                 days_ago = (datetime.now() - datetime.fromisoformat(last_fetch)).days
#                             except ValueError:
#                                 days_ago = 999
#                             should_fetch = days_ago >= COMMENT_FETCH_DAYS

#                     if should_fetch:
#                         logger.info(f"  Fetching {comment_count} comments for {item['mention_id'][:50]}...")
#                         raw_comments = client.fetch_comments_prism(item["url"])
#                         for rc in raw_comments:
#                             comment_obj = rc.get("comment", rc) if isinstance(rc, dict) else {}
#                             content = comment_obj.get("content", {})
#                             content = content if isinstance(content, dict) else {}
#                             author = comment_obj.get("author", {})
#                             author = author if isinstance(author, dict) else {}

#                             author_name = author.get("username") or author.get("display_name") or author.get("name") or ""
#                             author_id = extract_author_id(author)
#                             text = content.get("text") or comment_obj.get("text") or ""
#                             ts = comment_obj.get("published_at") or comment_obj.get("created_at") or ""
#                             geo_region = detect_geo_region(text, author.get("location", ""))

#                             comment_entry = {
#                                 "comment_id": make_comment_id(item["mention_id"], comment_obj),
#                                 "mention_id": item["mention_id"],
#                                 "_platform": item["_platform"],
#                                 "author": author_name,
#                                 "author_id": author_id,
#                                 "text": text,
#                                 "timestamp": ts,
#                                 "geo_region": geo_region,
#                                 "engagement": comment_obj.get("engagement", {}),
#                                 "_raw": comment_obj,
#                             }
#                             store.upsert_comment(comment_entry)
#                             comments_fetched += 1

#                         store.update_last_comment_fetch(item["mention_id"], datetime.now().isoformat())
#                         logger.info(f"  Fetched {len(raw_comments)} comments")

#             time.sleep(0.2)

#     # Save metadata
#     store.set_meta("last_run", datetime.now().isoformat())

#     # Log summary
#     logger.info("\n" + "=" * 80)
#     logger.info("RUN SUMMARY")
#     logger.info("=" * 80)
#     logger.info(f"New mentions:       {len(new_items)}")
#     logger.info(f"Updated mentions:   {len(updated_items)}")
#     logger.info(f"Unchanged:          {len(unchanged_items)}")
#     logger.info(f"Comments fetched:   {comments_fetched}")
#     logger.info("\nBy Platform:")
#     for platform, count in sorted(platform_stats.items()):
#         logger.info(f"  {platform.upper():15s}: {count:5d} items")
#     if dropped_offplatform:
#         logger.info(f"\nDropped (off-platform): {dropped_offplatform}")
#     logger.info("=" * 80)

#     # Export results
#     export = {
#         "run_at": datetime.now().isoformat(),
#         "queries": TEST_QUERIES,
#         "allowed_platforms": sorted(ALLOWED_PLATFORMS),
#         "date_window": {"from": DATE_FROM, "to": DATE_TO},
#         "stats": {
#             "new": len(new_items),
#             "updated": len(updated_items),
#             "unchanged": len(unchanged_items),
#             "comments_new": comments_fetched,
#             "by_platform": platform_stats,
#             "dropped_offplatform": dropped_offplatform,
#         },
#         "new_mentions": new_items,
#         "updated_mentions": updated_items,
#     }

#     export_file = f"{RUN_EXPORT_DIR}/run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
#     with open(export_file, "w", encoding="utf-8") as f:
#         json.dump(export, f, indent=2, ensure_ascii=False)

#     logger.info(f"\nRun results saved to: {export_file}")
#     logger.info(f"Full database: {DB_FILE}")
#     logger.info(f"Log file: {LOG_FILE}")
#     logger.info("=" * 80)

#     store.close()

# if __name__ == "__main__":
#     main()



# """
# INDIAN SOCIAL LISTENING - FACEBOOK / INSTAGRAM / X (TWITTER) / REDDIT / LINKEDIN
# Full comments, period (timestamp), and geography on every mention - fixed
# to correctly parse BOTH response shapes SocialCrawl actually sends back.

# THE BUG THIS VERSION FIXES
# ----------------------------
# /v1/reddit/search and /v1/twitter/ai-search return a simple {"post": {...}}
# wrapper - author, published_at, and engagement sit right where the old
# parser expected them.

# /v1/search/everywhere (which Instagram, Facebook, and LinkedIn have to go
# through, since none of them expose an open keyword-search endpoint) returns
# a completely different, RERANKED envelope shape instead:
#   { candidate_id, item_id, rrf_score, final_score, cluster_id,
#     engagement: 13,                <- a blended relevance NUMBER, not a dict
#     source_items: [ { author, published_at, engagement: {...}, url, ... } ]
#   }
# The real per-post data lives inside source_items[], one level down. The
# previous version read fields off the top of this envelope, got nothing
# useful, and silently produced empty author/timestamp/engagement - which
# in turn meant the comment-count gate always saw 0 and never fetched
# comments, even when the raw data clearly showed some (e.g. 7 on the
# Instagram reel you flagged).

# WHAT CHANGED
# ------------
# 1. normalize_item() now detects which shape it's looking at (presence of
#    `source_items`) and extracts from the right place for each.
# 2. Comment count is read from the corrected engagement dict, so the
#    comment-fetch gate now actually sees real numbers for FB/IG/LinkedIn/X,
#    not just Reddit.
# 3. `-1` is SocialCrawl's "not available" sentinel on some engagement
#    fields (seen on `likes` in your sample) - it's now converted to None
#    instead of being stored as a literal, misleading number.
# 4. Twitter/X is back on its own native endpoint (/v1/twitter/ai-search)
#    instead of going through /everywhere - cheaper, and it returns the
#    simple post shape, sidestepping this whole class of bug for X data.
# 5. timestamp_confidence is captured and stored alongside timestamp -
#    SocialCrawl itself flags some everywhere-sourced dates as low
#    confidence (estimated, not authoritative); that flag is now kept
#    rather than discarded.
# 6. "Reviews": there is no separate review concept on any of these 5
#    platforms - comments/replies ARE the review-equivalent content on a
#    post, and are fetched the same way for all of them via Prism. The one
#    platform-native exception, Facebook Page star ratings, is a distinct
#    feature tied to a Page (not a post) - it's included here as an
#    explicitly off-by-default, unverified stub (see fetch_facebook_page_ratings)
#    rather than guessed at silently.
# 7. Author IDs: /everywhere's author field is a bare string (a handle),
#    with no numeric ID at that layer - that's a real data limitation, not
#    a parsing bug. An optional, off-by-default profile lookup
#    (FETCH_AUTHOR_PROFILES) is included to resolve a real ID via Prism's
#    profile endpoint, but the profile-URL guess it builds per platform is
#    marked clearly as best-effort (particularly unreliable for LinkedIn,
#    where person vs company profile URLs differ).
# """

# import json
# import time
# import logging
# import hashlib
# import sqlite3
# import requests
# from datetime import datetime
# from pathlib import Path

# # ============================================================
# # CONFIGURATION
# # ============================================================
# API_KEY = "sc_QPRRy3AT7j5xb5T5EuztzntY0rjsQynv9CEZpTarh2k"
# BASE_URL = "https://www.socialcrawl.dev"

# TEST_QUERIES = [
#     "LG AC",
#     "LG Air Conditioner",
# ]

# LIMIT = 10  # results per query per platform

# # Platforms with a real native keyword-search endpoint (simple post shape)
# NATIVE_SEARCH_PLATFORMS = ["reddit", "twitter"]
# # Platforms with NO open keyword search - routed through /v1/search/everywhere
# # (reranked-envelope shape - handled separately in normalize_item)
# EVERYWHERE_SCOPED_PLATFORMS = ["instagram", "facebook", "linkedin"]

# # Hard allowlist - the ONLY platforms that are ever allowed into the DB
# ALLOWED_PLATFORMS = {"reddit", "twitter", "instagram", "facebook", "linkedin"}

# # Period filter - set either to None to leave that side open. "YYYY-MM-DD"
# DATE_FROM = None
# DATE_TO = None

# DB_FILE = "social_listening.db"
# RUN_EXPORT_DIR = "runs"
# LOG_FILE = f"social_crawl_{datetime.now().strftime('%Y%m%d')}.log"

# # Comments - fetched for every mention with a URL and a comment_count that
# # isn't confirmed-zero (unknown counts are treated as "try anyway", not
# # "skip") on every run.
# FETCH_FULL_COMMENTS = True
# ALWAYS_REFRESH_COMMENTS = True
# COMMENT_FETCH_DAYS = 7          # only used if ALWAYS_REFRESH_COMMENTS is False
# MAX_COMMENT_PAGES = 20

# # Optional, OFF by default: resolve a real numeric author ID for
# # everywhere-sourced items via a Prism profile lookup. Adds one extra call
# # per UNIQUE author per run (cached within the run). The profile URL this
# # builds is a best-effort guess per platform - verify against your
# # dashboard before trusting it, especially for LinkedIn.
# FETCH_AUTHOR_PROFILES = False

# # Optional, OFF by default and UNVERIFIED: Facebook Page-level star
# # ratings. This is a distinct feature from post comments and needs its
# # own endpoint - path below is a guess, confirm in your dashboard first.
# FETCH_FACEBOOK_PAGE_RATINGS = False

# # ============================================================
# # LOGGING
# # ============================================================
# file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
# file_handler.setLevel(logging.INFO)
# stream_handler = logging.StreamHandler()
# stream_handler.setLevel(logging.INFO)
# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s - %(levelname)s - %(message)s",
#     handlers=[file_handler, stream_handler],
# )
# logger = logging.getLogger(__name__)

# # ============================================================
# # GEOGRAPHY (best-effort keyword match, not verified geolocation)
# # ============================================================
# INDIA_GEO_KEYWORDS = [
#     "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh",
#     "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka",
#     "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya",
#     "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim",
#     "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand",
#     "West Bengal", "Delhi", "Jammu and Kashmir", "Ladakh", "Puducherry",
#     "Chandigarh", "Andaman and Nicobar", "Dadra and Nagar Haveli",
#     "Lakshadweep",
#     "Mumbai", "Bengaluru", "Bangalore", "Chennai", "Kolkata", "Hyderabad",
#     "Pune", "Ahmedabad", "Jaipur", "Lucknow", "Surat", "Kanpur", "Nagpur",
#     "Indore", "Bhopal", "Patna", "Vadodara", "Ludhiana", "Agra", "Nashik",
#     "Coimbatore", "Kochi", "Thiruvananthapuram", "Guwahati", "Noida",
#     "Gurugram", "Gurgaon", "Faridabad", "Meerut", "Rajkot", "Vijayawada",
#     "Jodhpur",
# ]


# def detect_geo_region(*text_blobs):
#     combined = " ".join([t for t in text_blobs if t]).lower()
#     for region in INDIA_GEO_KEYWORDS:
#         if region.lower() in combined:
#             return region
#     return ""


# # ============================================================
# # TIMESTAMP / DATE-WINDOW HELPERS
# # ============================================================
# def parse_timestamp(ts):
#     if not ts:
#         return None
#     try:
#         return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
#     except Exception:
#         return None


# def within_date_window(ts_str):
#     if not DATE_FROM and not DATE_TO:
#         return True
#     dt = parse_timestamp(ts_str)
#     if dt is None:
#         return True
#     dt_naive = dt.replace(tzinfo=None)
#     if DATE_FROM and dt_naive < datetime.fromisoformat(DATE_FROM):
#         return False
#     if DATE_TO and dt_naive > datetime.fromisoformat(DATE_TO).replace(hour=23, minute=59, second=59):
#         return False
#     return True


# # ============================================================
# # ENGAGEMENT CLEANUP (-1 sentinel -> None, not a literal number)
# # ============================================================
# def clean_engagement(raw_engagement):
#     if not isinstance(raw_engagement, dict):
#         return {}
#     cleaned = {}
#     for key in ("views", "likes", "comments", "shares", "saves"):
#         val = raw_engagement.get(key)
#         if val is None:
#             cleaned[key] = None
#         elif isinstance(val, (int, float)) and val < 0:
#             cleaned[key] = None  # -1 == "not available", not zero
#         else:
#             cleaned[key] = val
#     return cleaned


# # ============================================================
# # ID / AUTHOR / CHANGE-DETECTION HELPERS
# # ============================================================
# def extract_author_id(author_obj):
#     if not isinstance(author_obj, dict):
#         return ""
#     for key in ("id", "user_id", "pk", "author_id", "id_str", "uid"):
#         val = author_obj.get(key)
#         if val:
#             return str(val)
#     return ""


# def make_mention_id(platform, item):
#     native_id = (item.get("id") or "").strip()
#     if native_id:
#         return f"{platform}:{native_id}"
#     basis = item.get("url") or f"{item.get('title', '')}|{item.get('author', '')}"
#     digest = hashlib.sha256(f"{platform}|{basis}".encode("utf-8")).hexdigest()[:20]
#     return f"{platform}:h{digest}"


# def make_fingerprint(item):
#     engagement = item.get("engagement", {}) or {}
#     basis = {
#         "text": item.get("text", ""),
#         "title": item.get("title", ""),
#         "likes": engagement.get("likes"),
#         "comments": engagement.get("comments"),
#         "shares": engagement.get("shares"),
#         "views": engagement.get("views"),
#     }
#     return hashlib.sha256(
#         json.dumps(basis, sort_keys=True, ensure_ascii=False).encode("utf-8")
#     ).hexdigest()


# def make_comment_id(mention_id, raw_comment):
#     native_id = (
#         raw_comment.get("id")
#         or raw_comment.get("comment_id")
#         or raw_comment.get("review_id")
#         or ""
#     )
#     if native_id:
#         return str(native_id)
#     author = raw_comment.get("author", {})
#     author_name = author.get("username") if isinstance(author, dict) else str(author)
#     text = raw_comment.get("text") or (raw_comment.get("content", {}) or {}).get("text", "")
#     ts = raw_comment.get("published_at") or raw_comment.get("created_at") or ""
#     basis = f"{mention_id}|{author_name}|{text}|{ts}"
#     return f"h{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:20]}"


# def _extract_source_detail(raw_item, target_platform):
#     """
#     For an /everywhere envelope, find the source_items[] entry that
#     actually matches target_platform (an envelope can carry more than one
#     if the same content was picked up via multiple crawl paths). Falls
#     back to the first dict entry if no exact match.
#     """
#     source_items = raw_item.get("source_items")
#     if not isinstance(source_items, list) or not source_items:
#         return {}
#     for si in source_items:
#         if isinstance(si, dict) and (si.get("source") or si.get("platform") or "").lower() == target_platform:
#             return si
#     for si in source_items:
#         if isinstance(si, dict):
#             return si
#     return {}


# def normalize_item(raw_item, platform_hint, query):
#     """
#     Normalizes a raw SocialCrawl item, handling BOTH response shapes:
#       - native post shape: {"post": {...}} or a flat post dict
#         (reddit, twitter via its own endpoint)
#       - everywhere envelope shape: {"source_items": [...], ...}
#         (instagram, facebook, linkedin, or twitter if routed through
#         /everywhere)
#     """
#     if not isinstance(raw_item, dict):
#         return None

#     envelope_platform = (raw_item.get("source") or raw_item.get("platform") or "").lower()
#     source_platform = envelope_platform or (platform_hint or "").lower()

#     if isinstance(raw_item.get("source_items"), list):
#         # ---- EVERYWHERE ENVELOPE SHAPE ----
#         detail = _extract_source_detail(raw_item, source_platform)

#         text = (
#             detail.get("body")
#             or detail.get("title")
#             or raw_item.get("title")
#             or raw_item.get("snippet")
#             or "No text"
#         )

#         author_raw = detail.get("author")
#         if isinstance(author_raw, dict):
#             author_name = (
#                 author_raw.get("username")
#                 or author_raw.get("display_name")
#                 or author_raw.get("name")
#                 or "Unknown"
#             )
#             author_obj = author_raw
#         else:
#             # everywhere commonly gives just a bare handle string here -
#             # no numeric id available at this layer (see FETCH_AUTHOR_PROFILES)
#             author_name = author_raw or "Unknown"
#             author_obj = {}

#         author_id = extract_author_id(author_obj)
#         author_location = author_obj.get("location") or author_obj.get("bio_location") or ""

#         engagement = clean_engagement(detail.get("engagement", {}))
#         timestamp = detail.get("published_at") or detail.get("created_at") or ""
#         timestamp_confidence = detail.get("date_confidence", "")

#         url = detail.get("url") or raw_item.get("url") or raw_item.get("candidate_id") or ""
#         native_id = detail.get("item_id") or detail.get("id") or ""
#         title = detail.get("title") or raw_item.get("title") or (text[:100] if text else "")
#         raw_for_storage = detail if detail else raw_item

#     else:
#         # ---- NATIVE POST SHAPE ----
#         post = raw_item.get("post", raw_item) if isinstance(raw_item.get("post", raw_item), dict) else raw_item
#         content = post.get("content", {})
#         content = content if isinstance(content, dict) else {}
#         author = post.get("author", {})
#         author = author if isinstance(author, dict) else {}

#         text = (
#             content.get("text")
#             or post.get("title")
#             or post.get("snippet")
#             or post.get("description")
#             or "No text"
#         )
#         author_name = author.get("username") or author.get("display_name") or author.get("name") or "Unknown"
#         author_id = extract_author_id(author)
#         author_location = author.get("location") or author.get("bio_location") or ""

#         engagement = clean_engagement(post.get("engagement", {}))
#         timestamp = post.get("published_at") or post.get("created_at") or ""
#         timestamp_confidence = post.get("date_confidence", "")

#         url = post.get("url", "")
#         native_id = post.get("id", "")
#         title = post.get("title", text[:100] if text else "")
#         raw_for_storage = post

#     geo_region = detect_geo_region(text or "", author_location or "")

#     return {
#         "_platform": source_platform,
#         "_query": query,
#         "title": title,
#         "text": text,
#         "author": author_name,
#         "author_id": author_id,
#         "url": url,
#         "id": native_id,
#         "timestamp": timestamp,
#         "timestamp_confidence": timestamp_confidence,
#         "engagement": engagement,
#         "geo_region": geo_region,
#         "_raw": raw_for_storage,
#     }


# def guess_profile_url(platform, handle):
#     """
#     Best-effort profile URL builder for the optional author-profile
#     lookup. VERIFY before relying on this, especially for LinkedIn, where
#     person (/in/<handle>) vs company (/company/<handle>) URLs differ and
#     this always guesses the personal-profile pattern.
#     """
#     handle = (handle or "").lstrip("@").strip()
#     if not handle:
#         return ""
#     if platform == "instagram":
#         return f"https://www.instagram.com/{handle}/"
#     if platform == "twitter":
#         return f"https://twitter.com/{handle}"
#     if platform == "facebook":
#         return f"https://www.facebook.com/{handle}"
#     if platform == "linkedin":
#         return f"https://www.linkedin.com/in/{handle}"  # guess only - see docstring
#     return ""


# # ============================================================
# # PERSISTENT STORE (SQLite)
# # ============================================================
# class MentionStore:
#     def __init__(self, db_path):
#         self.conn = sqlite3.connect(db_path)
#         self.conn.row_factory = sqlite3.Row
#         self._init_schema()

#     def _init_schema(self):
#         self.conn.executescript(
#             """
#             CREATE TABLE IF NOT EXISTS mentions (
#                 mention_id           TEXT PRIMARY KEY,
#                 platform             TEXT,
#                 query                TEXT,
#                 title                TEXT,
#                 text                 TEXT,
#                 author               TEXT,
#                 url                  TEXT,
#                 timestamp            TEXT,
#                 engagement_json      TEXT,
#                 raw_json             TEXT,
#                 first_seen           TEXT,
#                 last_seen            TEXT,
#                 last_updated         TEXT
#             );

#             CREATE TABLE IF NOT EXISTS mention_history (
#                 id              INTEGER PRIMARY KEY AUTOINCREMENT,
#                 mention_id      TEXT,
#                 snapshot_json   TEXT,
#                 recorded_at     TEXT
#             );

#             CREATE TABLE IF NOT EXISTS comments (
#                 comment_id      TEXT PRIMARY KEY,
#                 mention_id      TEXT,
#                 platform        TEXT,
#                 author          TEXT,
#                 text            TEXT,
#                 timestamp       TEXT,
#                 engagement_json TEXT,
#                 raw_json        TEXT,
#                 first_seen      TEXT,
#                 last_seen       TEXT
#             );

#             CREATE TABLE IF NOT EXISTS meta (
#                 key   TEXT PRIMARY KEY,
#                 value TEXT
#             );
#             """
#         )

#         required_mention_columns = {
#             "author_id":            "TEXT DEFAULT ''",
#             "geo_region":           "TEXT DEFAULT ''",
#             "fingerprint":          "TEXT DEFAULT ''",
#             "last_comment_fetch":   "TEXT",
#             "timestamp_confidence": "TEXT DEFAULT ''",
#         }
#         existing_mention_columns = [
#             row[1] for row in self.conn.execute("PRAGMA table_info(mentions)").fetchall()
#         ]
#         for col, col_def in required_mention_columns.items():
#             if col not in existing_mention_columns:
#                 self.conn.execute(f"ALTER TABLE mentions ADD COLUMN {col} {col_def}")
#                 logger.info(f"Added missing column '{col}' to mentions table")

#         required_comment_columns = {
#             "author_id":            "TEXT DEFAULT ''",
#             "geo_region":           "TEXT DEFAULT ''",
#             "timestamp_confidence": "TEXT DEFAULT ''",
#         }
#         existing_comment_columns = [
#             row[1] for row in self.conn.execute("PRAGMA table_info(comments)").fetchall()
#         ]
#         for col, col_def in required_comment_columns.items():
#             if col not in existing_comment_columns:
#                 self.conn.execute(f"ALTER TABLE comments ADD COLUMN {col} {col_def}")
#                 logger.info(f"Added missing column '{col}' to comments table")

#         self.conn.executescript(
#             """
#             CREATE INDEX IF NOT EXISTS idx_comments_mention_id ON comments(mention_id);
#             CREATE INDEX IF NOT EXISTS idx_mentions_platform ON mentions(platform);
#             CREATE INDEX IF NOT EXISTS idx_mentions_timestamp ON mentions(timestamp);
#             CREATE INDEX IF NOT EXISTS idx_mentions_geo ON mentions(geo_region);
#             CREATE INDEX IF NOT EXISTS idx_mentions_author_id ON mentions(author_id);
#             CREATE INDEX IF NOT EXISTS idx_comments_author_id ON comments(author_id);
#             """
#         )
#         self.conn.commit()

#     def upsert_mention(self, item):
#         now = datetime.now().isoformat()
#         mention_id = item["mention_id"]
#         fingerprint = item["fingerprint"]

#         row = self.conn.execute(
#             "SELECT * FROM mentions WHERE mention_id = ?", (mention_id,)
#         ).fetchone()

#         engagement_json = json.dumps(item.get("engagement", {}), ensure_ascii=False)
#         raw_json = json.dumps(item.get("_raw", {}), ensure_ascii=False)

#         if row is None:
#             self.conn.execute(
#                 """
#                 INSERT INTO mentions
#                 (mention_id, platform, query, title, text, author, author_id, url,
#                  timestamp, timestamp_confidence, geo_region, engagement_json,
#                  fingerprint, raw_json, first_seen, last_seen, last_updated,
#                  last_comment_fetch)
#                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
#                 """,
#                 (
#                     mention_id, item.get("_platform", ""), item.get("_query", ""),
#                     item.get("title", ""), item.get("text", ""), item.get("author", ""),
#                     item.get("author_id", ""), item.get("url", ""), item.get("timestamp", ""),
#                     item.get("timestamp_confidence", ""), item.get("geo_region", ""),
#                     engagement_json, fingerprint, raw_json, now, now, now, None,
#                 ),
#             )
#             self.conn.commit()
#             return "new"

#         if row["fingerprint"] == fingerprint:
#             self.conn.execute(
#                 "UPDATE mentions SET last_seen = ? WHERE mention_id = ?", (now, mention_id)
#             )
#             self.conn.commit()
#             return "unchanged"

#         self.conn.execute(
#             "INSERT INTO mention_history (mention_id, snapshot_json, recorded_at) VALUES (?,?,?)",
#             (mention_id, json.dumps(dict(row), ensure_ascii=False), now),
#         )
#         self.conn.execute(
#             """
#             UPDATE mentions SET
#                 title=?, text=?, author=?, author_id=?, url=?, timestamp=?,
#                 timestamp_confidence=?, geo_region=?, engagement_json=?,
#                 fingerprint=?, raw_json=?, last_seen=?, last_updated=?
#             WHERE mention_id=?
#             """,
#             (
#                 item.get("title", ""), item.get("text", ""), item.get("author", ""),
#                 item.get("author_id", ""), item.get("url", ""), item.get("timestamp", ""),
#                 item.get("timestamp_confidence", ""), item.get("geo_region", ""),
#                 engagement_json, fingerprint, raw_json, now, now, mention_id,
#             ),
#         )
#         self.conn.commit()
#         return "updated"

#     def get_last_comment_fetch(self, mention_id):
#         row = self.conn.execute(
#             "SELECT last_comment_fetch FROM mentions WHERE mention_id = ?", (mention_id,)
#         ).fetchone()
#         return row["last_comment_fetch"] if row else None

#     def update_last_comment_fetch(self, mention_id, timestamp):
#         self.conn.execute(
#             "UPDATE mentions SET last_comment_fetch = ? WHERE mention_id = ?",
#             (timestamp, mention_id),
#         )
#         self.conn.commit()

#     def upsert_comment(self, comment):
#         now = datetime.now().isoformat()
#         comment_id = comment["comment_id"]
#         row = self.conn.execute(
#             "SELECT comment_id FROM comments WHERE comment_id = ?", (comment_id,)
#         ).fetchone()

#         if row is None:
#             self.conn.execute(
#                 """
#                 INSERT INTO comments
#                 (comment_id, mention_id, platform, author, author_id, text, timestamp,
#                  timestamp_confidence, geo_region, engagement_json, raw_json,
#                  first_seen, last_seen)
#                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
#                 """,
#                 (
#                     comment_id, comment["mention_id"], comment.get("_platform", ""),
#                     comment.get("author", ""), comment.get("author_id", ""),
#                     comment.get("text", ""), comment.get("timestamp", ""),
#                     comment.get("timestamp_confidence", ""), comment.get("geo_region", ""),
#                     json.dumps(comment.get("engagement", {}), ensure_ascii=False),
#                     json.dumps(comment.get("_raw", {}), ensure_ascii=False),
#                     now, now,
#                 ),
#             )
#             self.conn.commit()
#             return "new"

#         self.conn.execute("UPDATE comments SET last_seen = ? WHERE comment_id = ?", (now, comment_id))
#         self.conn.commit()
#         return "unchanged"

#     def set_meta(self, key, value):
#         self.conn.execute(
#             "INSERT INTO meta (key, value) VALUES (?, ?) "
#             "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
#             (key, value),
#         )
#         self.conn.commit()

#     def close(self):
#         self.conn.close()


# # ============================================================
# # SOCIALCRAWL CLIENT
# # ============================================================
# class SocialCrawlClient:
#     def __init__(self, api_key, base_url):
#         self.api_key = api_key
#         self.base_url = base_url
#         self.session = requests.Session()
#         self.session.headers.update({"x-api-key": api_key, "Content-Type": "application/json"})

#     def check_balance(self):
#         try:
#             resp = self.session.get(f"{self.base_url}/v1/credits/balance", timeout=10)
#             data = resp.json()
#             balance = (
#                 data.get("data", {}).get("balance")
#                 or data.get("credits_remaining")
#                 or data.get("balance")
#             )
#             if balance is not None:
#                 logger.info(f"Current credit balance: {balance}")
#                 return balance
#             logger.warning(f"Balance not found: {data}")
#             return -1
#         except Exception as e:
#             logger.error(f"Balance check failed: {e}")
#             return -1

#     def _run_search(self, endpoint, params, platform_hint, query, timeout=30, drop_counter=None):
#         logger.info(f"Search: {platform_hint.upper()} | Query: {query} | Params: {params}")
#         try:
#             resp = self.session.get(endpoint, params=params, timeout=timeout)
#             if resp.status_code != 200:
#                 logger.error(f"Search error [{platform_hint}]: {resp.status_code} {resp.text[:200]}")
#                 return []

#             data = resp.json()
#             raw_items = (
#                 data.get("data", {}).get("items")
#                 or data.get("data")
#                 or data.get("items")
#                 or data.get("results")
#                 or []
#             )
#             if not isinstance(raw_items, list):
#                 raw_items = []

#             normalized = []
#             dropped_count = 0
#             for raw in raw_items:
#                 item = normalize_item(raw, platform_hint, query)
#                 if item is None:
#                     continue
#                 if item["_platform"] not in ALLOWED_PLATFORMS:
#                     dropped_count += 1
#                     if drop_counter is not None:
#                         drop_counter[item["_platform"]] = drop_counter.get(item["_platform"], 0) + 1
#                     continue
#                 if within_date_window(item["timestamp"]):
#                     normalized.append(item)

#             logger.info(f"[{platform_hint.upper()}] {len(normalized)} in-scope items (dropped {dropped_count})")
#             return normalized

#         except requests.exceptions.ReadTimeout:
#             logger.warning(f"Timeout on {platform_hint}")
#             return []
#         except Exception as e:
#             logger.error(f"Exception on {platform_hint}: {e}")
#             return []

#     def fetch_reddit(self, query, limit=10, drop_counter=None):
#         endpoint = f"{self.base_url}/v1/reddit/search"
#         indian_query = f"{query} (subreddit:india OR subreddit:indiasocial OR subreddit:AskIndia)"
#         params = {"query": indian_query, "limit": limit, "sort": "relevance"}
#         return self._run_search(endpoint, params, "reddit", query, timeout=60, drop_counter=drop_counter)

#     def fetch_twitter(self, query, limit=10, drop_counter=None):
#         """Back on its own native endpoint - simple post shape, no envelope bug, cheaper than /everywhere."""
#         endpoint = f"{self.base_url}/v1/twitter/ai-search"
#         params = {"query": f"{query} India", "limit": limit}
#         return self._run_search(endpoint, params, "twitter", query, timeout=30, drop_counter=drop_counter)

#     def fetch_everywhere_scoped(self, query, platforms, limit=10, drop_counter=None):
#         endpoint = f"{self.base_url}/v1/search/everywhere"
#         params = {"query": query, "platforms": ",".join(platforms), "gl": "in", "limit": limit}
#         return self._run_search(endpoint, params, "everywhere", query, timeout=45, drop_counter=drop_counter)

#     def fetch_comments_prism(self, post_url, max_pages=MAX_COMMENT_PAGES):
#         endpoint = f"{self.base_url}/v1/prism/comments"
#         all_comments = []
#         cursor = None
#         for _ in range(max_pages):
#             params = {"url": post_url}
#             if cursor:
#                 params["cursor"] = cursor
#             try:
#                 resp = self.session.get(endpoint, params=params, timeout=30)
#             except Exception as e:
#                 logger.error(f"Prism comments fetch error: {e}")
#                 break
#             if resp.status_code != 200:
#                 logger.warning(f"Prism comments {resp.status_code} for {post_url}: {resp.text[:200]}")
#                 break
#             data = resp.json()
#             payload = data.get("data", {}) if isinstance(data.get("data"), dict) else {}
#             items = payload.get("items") or data.get("data") or []
#             if not isinstance(items, list):
#                 items = []
#             all_comments.extend(items)
#             cursor = payload.get("next_cursor")
#             has_more = payload.get("has_more")
#             if not cursor or not has_more:
#                 break
#             time.sleep(0.3)
#         return all_comments

#     def fetch_author_profile(self, profile_url):
#         """
#         Optional (FETCH_AUTHOR_PROFILES). Prism profile lookup to resolve a
#         real native ID when everywhere only gave a bare handle. Path/params
#         unverified against your dashboard - confirm before relying on it.
#         """
#         if not profile_url:
#             return {}
#         endpoint = f"{self.base_url}/v1/prism/profiles"
#         try:
#             resp = self.session.get(endpoint, params={"url": profile_url}, timeout=20)
#             if resp.status_code != 200:
#                 logger.debug(f"Profile lookup {resp.status_code} for {profile_url}")
#                 return {}
#             data = resp.json()
#             return data.get("data", {}) if isinstance(data.get("data"), dict) else {}
#         except Exception as e:
#             logger.debug(f"Profile lookup failed for {profile_url}: {e}")
#             return {}

#     def fetch_facebook_page_ratings(self, page_url):
#         """
#         OFF by default, UNVERIFIED. Facebook Page star ratings are a
#         Page-level feature distinct from post comments. Path below is a
#         guess - confirm the real endpoint in your dashboard before use.
#         """
#         endpoint = f"{self.base_url}/v1/facebook/page/ratings"  # <-- VERIFY
#         try:
#             resp = self.session.get(endpoint, params={"url": page_url}, timeout=20)
#             if resp.status_code != 200:
#                 logger.warning(f"FB ratings {resp.status_code}: {resp.text[:200]} - verify endpoint path")
#                 return []
#             data = resp.json()
#             items = data.get("data", {}).get("items") or data.get("data") or []
#             return items if isinstance(items, list) else []
#         except Exception as e:
#             logger.error(f"FB ratings fetch failed: {e}")
#             return []


# # ============================================================
# # MAIN WORKFLOW
# # ============================================================
# def main():
#     logger.info("=" * 80)
#     logger.info("INDIAN SOCIAL LISTENING - FB / IG / X / REDDIT / LINKEDIN")
#     logger.info(f"Allowed platforms (hard filter): {', '.join(sorted(ALLOWED_PLATFORMS))}")
#     logger.info(f"Native search: {', '.join(NATIVE_SEARCH_PLATFORMS)}")
#     logger.info(f"Everywhere-scoped: {', '.join(EVERYWHERE_SCOPED_PLATFORMS)}")
#     logger.info(f"Queries: {', '.join(TEST_QUERIES)}")
#     logger.info(f"Date window: {DATE_FROM or '(open)'} to {DATE_TO or '(open)'}")
#     logger.info(f"Comments: {'ALWAYS refreshed every run' if ALWAYS_REFRESH_COMMENTS else f'throttled to every {COMMENT_FETCH_DAYS}d'}")
#     logger.info(f"Author profile lookups: {'ON' if FETCH_AUTHOR_PROFILES else 'OFF'}")
#     logger.info("=" * 80)

#     Path(RUN_EXPORT_DIR).mkdir(exist_ok=True)
#     store = MentionStore(DB_FILE)
#     client = SocialCrawlClient(API_KEY, BASE_URL)

#     balance = client.check_balance()
#     if balance == 0:
#         logger.critical("No credits. Aborting.")
#         store.close()
#         return

#     include_everywhere = True
#     if balance is not None and balance != -1 and balance < 20:
#         logger.warning("Skipping Instagram/Facebook/LinkedIn this run (everywhere call needs ~20 credits).")
#         include_everywhere = False

#     new_items, updated_items, unchanged_items = [], [], []
#     comments_fetched = 0
#     platform_stats = {}
#     dropped_offplatform = {}
#     profile_cache = {}  # author handle -> resolved profile dict, per-run cache

#     for query in TEST_QUERIES:
#         logger.info(f"--- Query: {query} ---")

#         all_items = []
#         all_items.extend(client.fetch_reddit(query, limit=LIMIT, drop_counter=dropped_offplatform))
#         all_items.extend(client.fetch_twitter(query, limit=LIMIT, drop_counter=dropped_offplatform))
#         if include_everywhere:
#             all_items.extend(
#                 client.fetch_everywhere_scoped(query, EVERYWHERE_SCOPED_PLATFORMS, limit=LIMIT, drop_counter=dropped_offplatform)
#             )

#         for item in all_items:
#             assert item["_platform"] in ALLOWED_PLATFORMS

#             platform_stats[item["_platform"]] = platform_stats.get(item["_platform"], 0) + 1

#             # Optional: resolve a real author id for everywhere-sourced
#             # items that only gave us a bare handle
#             if FETCH_AUTHOR_PROFILES and not item.get("author_id") and item.get("author") not in ("", "Unknown"):
#                 cache_key = f"{item['_platform']}:{item['author']}"
#                 if cache_key not in profile_cache:
#                     guess_url = guess_profile_url(item["_platform"], item["author"])
#                     profile_cache[cache_key] = client.fetch_author_profile(guess_url) if guess_url else {}
#                 profile = profile_cache[cache_key]
#                 resolved_id = extract_author_id(profile)
#                 if resolved_id:
#                     item["author_id"] = resolved_id

#             item["mention_id"] = make_mention_id(item["_platform"], item)
#             item["fingerprint"] = make_fingerprint(item)

#             status = store.upsert_mention(item)
#             if status == "new":
#                 new_items.append(item)
#             elif status == "updated":
#                 updated_items.append(item)
#             else:
#                 unchanged_items.append(item)

#             # ---- FULL COMMENT FETCH ----
#             # comment_count of None means "unknown" (not confirmed zero) -
#             # we still try in that case rather than skip.
#             should_fetch = False
#             if FETCH_FULL_COMMENTS and item.get("url"):
#                 comment_count = (item.get("engagement") or {}).get("comments")
#                 not_confirmed_zero = comment_count is None or comment_count > 0
#                 if not_confirmed_zero:
#                     if ALWAYS_REFRESH_COMMENTS:
#                         should_fetch = True
#                     elif status in ("new", "updated"):
#                         should_fetch = True
#                     else:
#                         last_fetch = store.get_last_comment_fetch(item["mention_id"])
#                         if last_fetch is None:
#                             should_fetch = True
#                         else:
#                             try:
#                                 days_ago = (datetime.now() - datetime.fromisoformat(last_fetch)).days
#                             except ValueError:
#                                 days_ago = 999
#                             should_fetch = days_ago >= COMMENT_FETCH_DAYS

#             if should_fetch:
#                 raw_comments = client.fetch_comments_prism(item["url"])
#                 for rc in raw_comments:
#                     comment_obj = rc.get("comment", rc) if isinstance(rc, dict) else {}
#                     content = comment_obj.get("content", {})
#                     content = content if isinstance(content, dict) else {}
#                     author = comment_obj.get("author", {})
#                     author = author if isinstance(author, dict) else {}

#                     author_name = author.get("username") or author.get("display_name") or author.get("name") or ""
#                     author_id = extract_author_id(author)
#                     text = content.get("text") or comment_obj.get("text") or ""
#                     ts = comment_obj.get("published_at") or comment_obj.get("created_at") or ""
#                     ts_confidence = comment_obj.get("date_confidence", "")
#                     geo_region = detect_geo_region(text, author.get("location", ""))
#                     engagement = clean_engagement(comment_obj.get("engagement", {}))

#                     comment_entry = {
#                         "comment_id": make_comment_id(item["mention_id"], comment_obj),
#                         "mention_id": item["mention_id"],
#                         "_platform": item["_platform"],
#                         "author": author_name,
#                         "author_id": author_id,
#                         "text": text,
#                         "timestamp": ts,
#                         "timestamp_confidence": ts_confidence,
#                         "geo_region": geo_region,
#                         "engagement": engagement,
#                         "_raw": comment_obj,
#                     }
#                     store.upsert_comment(comment_entry)
#                     comments_fetched += 1

#                 store.update_last_comment_fetch(item["mention_id"], datetime.now().isoformat())
#                 logger.info(f"  Comments fetched for {item['mention_id']}: {len(raw_comments)}")

#             # Optional, unverified: Facebook Page ratings
#             if FETCH_FACEBOOK_PAGE_RATINGS and item["_platform"] == "facebook" and item.get("url"):
#                 client.fetch_facebook_page_ratings(item["url"])  # wire up storage once endpoint is confirmed

#             time.sleep(0.2)

#     store.set_meta("last_run", datetime.now().isoformat())

#     logger.info("=" * 80)
#     logger.info("RUN SUMMARY")
#     logger.info("=" * 80)
#     for platform, count in sorted(platform_stats.items()):
#         logger.info(f"[{platform.upper()}] fetched: {count}")
#     if dropped_offplatform:
#         logger.info(f"Dropped (outside allowlist): {dropped_offplatform}")
#     logger.info(f"NEW mentions:       {len(new_items)}")
#     logger.info(f"UPDATED mentions:   {len(updated_items)}")
#     logger.info(f"UNCHANGED (skipped):{len(unchanged_items)}")
#     logger.info(f"Comments fetched:   {comments_fetched}")

#     export = {
#         "run_at": datetime.now().isoformat(),
#         "queries": TEST_QUERIES,
#         "allowed_platforms": sorted(ALLOWED_PLATFORMS),
#         "date_window": {"from": DATE_FROM, "to": DATE_TO},
#         "stats": {
#             "new": len(new_items),
#             "updated": len(updated_items),
#             "unchanged": len(unchanged_items),
#             "comments_new": comments_fetched,
#             "by_platform": platform_stats,
#             "dropped_offplatform": dropped_offplatform,
#         },
#         "new_mentions": new_items,
#         "updated_mentions": updated_items,
#     }
#     export_file = f"{RUN_EXPORT_DIR}/run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
#     with open(export_file, "w", encoding="utf-8") as f:
#         json.dump(export, f, indent=2, ensure_ascii=False)

#     logger.info(f"Run delta saved to: {export_file}")
#     logger.info(f"Full database: {DB_FILE}")
#     logger.info(f"Log file: {LOG_FILE}")
#     logger.info("=" * 80)

#     store.close()


# if __name__ == "__main__":
#     main()








"""
INDIAN SOCIAL LISTENING - FACEBOOK / INSTAGRAM / X (TWITTER) / REDDIT / LINKEDIN
Comments gated by Prism's ACTUAL supported platform list, diagnostics added
for the twitter/facebook empty-result issue.

WHAT CHANGED VS THE PREVIOUS VERSION
--------------------------------------
1. Comments are no longer attempted on LinkedIn or Twitter/X.
   Prism's own error response says it plainly: "Supported: TikTok, YouTube,
   Facebook, Reddit, Hacker News, or Instagram." That's confirmed directly
   from the API, not assumed from docs copy. Intersected with our 5
   platforms, Prism comments only works for facebook, reddit, instagram.
   Calling it for linkedin/twitter always 400s - so it's skipped for those
   two now, with a clear log line saying WHY, instead of an error per post.

2. Platform alias normalization.
   Real API responses sometimes tag platforms differently than the request
   param used (e.g. "fb" instead of "facebook"). A small alias map now
   normalizes these before matching against ALLOWED_PLATFORMS, so a
   naming mismatch can't silently make a platform's data disappear.

3. Diagnostics for the "twitter/facebook return nothing" problem.
   - Native calls (twitter): if a 200 response yields 0 extracted items,
     the response's top-level JSON keys are now logged. If the real
     data lives under a key our extraction doesn't check yet, this
     shows it immediately instead of failing silently.
   - Everywhere calls (facebook/instagram/linkedin): a platform tally of
     every raw item's source tag is logged BEFORE the allowlist filter
     runs, so you can see directly whether Facebook content is simply
     absent upstream, or present under an unexpected tag.

4. Everything from the previous version is unchanged: envelope-vs-native
   shape detection, -1 sentinel handling, timestamp_confidence, the hard
   platform allowlist, optional author-profile lookup, optional
   (unverified) Facebook Page ratings stub.
"""

import json
import time
import logging
import hashlib
import sqlite3
import requests
from datetime import datetime
from pathlib import Path

# ============================================================
# CONFIGURATION
# ============================================================
API_KEY = "sc_QPRRy3AT7j5xb5T5EuztzntY0rjsQynv9CEZpTarh2k"
BASE_URL = "https://www.socialcrawl.dev"

TEST_QUERIES = [
    "LG AC",
    "LG Air Conditioner",
]

LIMIT = 10

NATIVE_SEARCH_PLATFORMS = ["reddit", "twitter"]
EVERYWHERE_SCOPED_PLATFORMS = ["instagram", "facebook", "linkedin"]
ALLOWED_PLATFORMS = {"reddit", "twitter", "instagram", "facebook", "linkedin"}





# Confirmed directly from Prism's own error response (not assumed):
# "Supported: TikTok, YouTube, Facebook, Reddit, Hacker News, or Instagram"
# Intersected with our 5 target platforms.
PRISM_COMMENTS_SUPPORTED_PLATFORMS = {"facebook", "reddit", "instagram"}

# Handles cases where an API response tags a platform differently than
# the slug we requested it with.
PLATFORM_ALIASES = {
    "fb": "facebook",
    "meta": "facebook",
    "ig": "instagram",
    "insta": "instagram",
    "x": "twitter",
    "x.com": "twitter",
    "twitter.com": "twitter",
    "li": "linkedin",
}


def normalize_platform_tag(raw_tag):
    tag = (raw_tag or "").strip().lower()
    return PLATFORM_ALIASES.get(tag, tag)


DATE_FROM = None
DATE_TO = None

DB_FILE = "social_listening.db"
RUN_EXPORT_DIR = "runs"
LOG_FILE = f"social_crawl_{datetime.now().strftime('%Y%m%d')}.log"

FETCH_FULL_COMMENTS = True
ALWAYS_REFRESH_COMMENTS = True
COMMENT_FETCH_DAYS = 7
MAX_COMMENT_PAGES = 20

FETCH_AUTHOR_PROFILES = False
FETCH_FACEBOOK_PAGE_RATINGS = False

# ============================================================
# LOGGING
# ============================================================
file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
file_handler.setLevel(logging.INFO)
stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.INFO)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[file_handler, stream_handler],
)
logger = logging.getLogger(__name__)

# ============================================================
# GEOGRAPHY (best-effort keyword match, not verified geolocation)
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
    "Jodhpur",
]


def detect_geo_region(*text_blobs):
    combined = " ".join([t for t in text_blobs if t]).lower()
    for region in INDIA_GEO_KEYWORDS:
        if region.lower() in combined:
            return region
    return ""


# ============================================================
# TIMESTAMP / DATE-WINDOW HELPERS
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
    if DATE_TO and dt_naive > datetime.fromisoformat(DATE_TO).replace(hour=23, minute=59, second=59):
        return False
    return True


# ============================================================
# ENGAGEMENT CLEANUP (-1 sentinel -> None)
# ============================================================
def clean_engagement(raw_engagement):
    if not isinstance(raw_engagement, dict):
        return {}
    cleaned = {}
    for key in ("views", "likes", "comments", "shares", "saves"):
        val = raw_engagement.get(key)
        if val is None:
            cleaned[key] = None
        elif isinstance(val, (int, float)) and val < 0:
            cleaned[key] = None
        else:
            cleaned[key] = val
    return cleaned


# ============================================================
# ID / AUTHOR / CHANGE-DETECTION HELPERS
# ============================================================
def extract_author_id(author_obj):
    if not isinstance(author_obj, dict):
        return ""
    for key in ("id", "user_id", "pk", "author_id", "id_str", "uid"):
        val = author_obj.get(key)
        if val:
            return str(val)
    return ""


def make_mention_id(platform, item):
    native_id = (item.get("id") or "").strip()
    if native_id:
        return f"{platform}:{native_id}"
    basis = item.get("url") or f"{item.get('title', '')}|{item.get('author', '')}"
    digest = hashlib.sha256(f"{platform}|{basis}".encode("utf-8")).hexdigest()[:20]
    return f"{platform}:h{digest}"


def make_fingerprint(item):
    engagement = item.get("engagement", {}) or {}
    basis = {
        "text": item.get("text", ""),
        "title": item.get("title", ""),
        "likes": engagement.get("likes"),
        "comments": engagement.get("comments"),
        "shares": engagement.get("shares"),
        "views": engagement.get("views"),
    }
    return hashlib.sha256(
        json.dumps(basis, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def make_comment_id(mention_id, raw_comment):
    native_id = (
        raw_comment.get("id")
        or raw_comment.get("comment_id")
        or raw_comment.get("review_id")
        or ""
    )
    if native_id:
        return str(native_id)
    author = raw_comment.get("author", {})
    author_name = author.get("username") if isinstance(author, dict) else str(author)
    text = raw_comment.get("text") or (raw_comment.get("content", {}) or {}).get("text", "")
    ts = raw_comment.get("published_at") or raw_comment.get("created_at") or ""
    basis = f"{mention_id}|{author_name}|{text}|{ts}"
    return f"h{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:20]}"


def _extract_source_detail(raw_item, target_platform):
    """
    For an /everywhere envelope, find the source_items[] entry matching
    target_platform (alias-normalized). Falls back to the first dict entry
    if no exact match.
    """
    source_items = raw_item.get("source_items")
    if not isinstance(source_items, list) or not source_items:
        return {}
    for si in source_items:
        if isinstance(si, dict):
            tag = normalize_platform_tag(si.get("source") or si.get("platform") or "")
            if tag == target_platform:
                return si
    for si in source_items:
        if isinstance(si, dict):
            return si
    return {}


def normalize_item(raw_item, platform_hint, query):
    if not isinstance(raw_item, dict):
        return None

    envelope_platform = normalize_platform_tag(raw_item.get("source") or raw_item.get("platform") or "")
    source_platform = envelope_platform or normalize_platform_tag(platform_hint)

    if isinstance(raw_item.get("source_items"), list):
        # ---- EVERYWHERE ENVELOPE SHAPE ----
        detail = _extract_source_detail(raw_item, source_platform)

        text = (
            detail.get("body")
            or detail.get("title")
            or raw_item.get("title")
            or raw_item.get("snippet")
            or "No text"
        )

        author_raw = detail.get("author")
        if isinstance(author_raw, dict):
            author_name = (
                author_raw.get("username")
                or author_raw.get("display_name")
                or author_raw.get("name")
                or "Unknown"
            )
            author_obj = author_raw
        else:
            author_name = author_raw or "Unknown"
            author_obj = {}

        author_id = extract_author_id(author_obj)
        author_location = author_obj.get("location") or author_obj.get("bio_location") or ""

        engagement = clean_engagement(detail.get("engagement", {}))
        timestamp = detail.get("published_at") or detail.get("created_at") or ""
        timestamp_confidence = detail.get("date_confidence", "")

        url = detail.get("url") or raw_item.get("url") or raw_item.get("candidate_id") or ""
        native_id = detail.get("item_id") or detail.get("id") or ""
        title = detail.get("title") or raw_item.get("title") or (text[:100] if text else "")
        raw_for_storage = detail if detail else raw_item

    else:
        # ---- NATIVE POST SHAPE ----
        post = raw_item.get("post", raw_item) if isinstance(raw_item.get("post", raw_item), dict) else raw_item
        content = post.get("content", {})
        content = content if isinstance(content, dict) else {}
        author = post.get("author", {})
        author = author if isinstance(author, dict) else {}

        text = (
            content.get("text")
            or post.get("title")
            or post.get("snippet")
            or post.get("description")
            or "No text"
        )
        author_name = author.get("username") or author.get("display_name") or author.get("name") or "Unknown"
        author_id = extract_author_id(author)
        author_location = author.get("location") or author.get("bio_location") or ""

        engagement = clean_engagement(post.get("engagement", {}))
        timestamp = post.get("published_at") or post.get("created_at") or ""
        timestamp_confidence = post.get("date_confidence", "")

        url = post.get("url", "")
        native_id = post.get("id", "")
        title = post.get("title", text[:100] if text else "")
        raw_for_storage = post

    geo_region = detect_geo_region(text or "", author_location or "")

    return {
        "_platform": source_platform,
        "_query": query,
        "title": title,
        "text": text,
        "author": author_name,
        "author_id": author_id,
        "url": url,
        "id": native_id,
        "timestamp": timestamp,
        "timestamp_confidence": timestamp_confidence,
        "engagement": engagement,
        "geo_region": geo_region,
        "_raw": raw_for_storage,
    }


def guess_profile_url(platform, handle):
    handle = (handle or "").lstrip("@").strip()
    if not handle:
        return ""
    if platform == "instagram":
        return f"https://www.instagram.com/{handle}/"
    if platform == "twitter":
        return f"https://twitter.com/{handle}"
    if platform == "facebook":
        return f"https://www.facebook.com/{handle}"
    if platform == "linkedin":
        return f"https://www.linkedin.com/in/{handle}"  # guess only - verify
    return ""


# ============================================================
# PERSISTENT STORE (SQLite)
# ============================================================
class MentionStore:
    def __init__(self, db_path):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS mentions (
                mention_id           TEXT PRIMARY KEY,
                platform             TEXT,
                query                TEXT,
                title                TEXT,
                text                 TEXT,
                author               TEXT,
                url                  TEXT,
                timestamp            TEXT,
                engagement_json      TEXT,
                raw_json             TEXT,
                first_seen           TEXT,
                last_seen            TEXT,
                last_updated         TEXT
            );

            CREATE TABLE IF NOT EXISTS mention_history (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                mention_id      TEXT,
                snapshot_json   TEXT,
                recorded_at     TEXT
            );

            CREATE TABLE IF NOT EXISTS comments (
                comment_id      TEXT PRIMARY KEY,
                mention_id      TEXT,
                platform        TEXT,
                author          TEXT,
                text            TEXT,
                timestamp       TEXT,
                engagement_json TEXT,
                raw_json        TEXT,
                first_seen      TEXT,
                last_seen       TEXT
            );

            CREATE TABLE IF NOT EXISTS meta (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
            """
        )

        required_mention_columns = {
            "author_id":            "TEXT DEFAULT ''",
            "geo_region":           "TEXT DEFAULT ''",
            "fingerprint":          "TEXT DEFAULT ''",
            "last_comment_fetch":   "TEXT",
            "timestamp_confidence": "TEXT DEFAULT ''",
        }
        existing_mention_columns = [
            row[1] for row in self.conn.execute("PRAGMA table_info(mentions)").fetchall()
        ]
        for col, col_def in required_mention_columns.items():
            if col not in existing_mention_columns:
                self.conn.execute(f"ALTER TABLE mentions ADD COLUMN {col} {col_def}")
                logger.info(f"Added missing column '{col}' to mentions table")

        required_comment_columns = {
            "author_id":            "TEXT DEFAULT ''",
            "geo_region":           "TEXT DEFAULT ''",
            "timestamp_confidence": "TEXT DEFAULT ''",
        }
        existing_comment_columns = [
            row[1] for row in self.conn.execute("PRAGMA table_info(comments)").fetchall()
        ]
        for col, col_def in required_comment_columns.items():
            if col not in existing_comment_columns:
                self.conn.execute(f"ALTER TABLE comments ADD COLUMN {col} {col_def}")
                logger.info(f"Added missing column '{col}' to comments table")

        self.conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_comments_mention_id ON comments(mention_id);
            CREATE INDEX IF NOT EXISTS idx_mentions_platform ON mentions(platform);
            CREATE INDEX IF NOT EXISTS idx_mentions_timestamp ON mentions(timestamp);
            CREATE INDEX IF NOT EXISTS idx_mentions_geo ON mentions(geo_region);
            CREATE INDEX IF NOT EXISTS idx_mentions_author_id ON mentions(author_id);
            CREATE INDEX IF NOT EXISTS idx_comments_author_id ON comments(author_id);
            """
        )
        self.conn.commit()

    def upsert_mention(self, item):
        now = datetime.now().isoformat()
        mention_id = item["mention_id"]
        fingerprint = item["fingerprint"]

        row = self.conn.execute(
            "SELECT * FROM mentions WHERE mention_id = ?", (mention_id,)
        ).fetchone()

        engagement_json = json.dumps(item.get("engagement", {}), ensure_ascii=False)
        raw_json = json.dumps(item.get("_raw", {}), ensure_ascii=False)

        if row is None:
            self.conn.execute(
                """
                INSERT INTO mentions
                (mention_id, platform, query, title, text, author, author_id, url,
                 timestamp, timestamp_confidence, geo_region, engagement_json,
                 fingerprint, raw_json, first_seen, last_seen, last_updated,
                 last_comment_fetch)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    mention_id, item.get("_platform", ""), item.get("_query", ""),
                    item.get("title", ""), item.get("text", ""), item.get("author", ""),
                    item.get("author_id", ""), item.get("url", ""), item.get("timestamp", ""),
                    item.get("timestamp_confidence", ""), item.get("geo_region", ""),
                    engagement_json, fingerprint, raw_json, now, now, now, None,
                ),
            )
            self.conn.commit()
            return "new"

        if row["fingerprint"] == fingerprint:
            self.conn.execute(
                "UPDATE mentions SET last_seen = ? WHERE mention_id = ?", (now, mention_id)
            )
            self.conn.commit()
            return "unchanged"

        self.conn.execute(
            "INSERT INTO mention_history (mention_id, snapshot_json, recorded_at) VALUES (?,?,?)",
            (mention_id, json.dumps(dict(row), ensure_ascii=False), now),
        )
        self.conn.execute(
            """
            UPDATE mentions SET
                title=?, text=?, author=?, author_id=?, url=?, timestamp=?,
                timestamp_confidence=?, geo_region=?, engagement_json=?,
                fingerprint=?, raw_json=?, last_seen=?, last_updated=?
            WHERE mention_id=?
            """,
            (
                item.get("title", ""), item.get("text", ""), item.get("author", ""),
                item.get("author_id", ""), item.get("url", ""), item.get("timestamp", ""),
                item.get("timestamp_confidence", ""), item.get("geo_region", ""),
                engagement_json, fingerprint, raw_json, now, now, mention_id,
            ),
        )
        self.conn.commit()
        return "updated"

    def get_last_comment_fetch(self, mention_id):
        row = self.conn.execute(
            "SELECT last_comment_fetch FROM mentions WHERE mention_id = ?", (mention_id,)
        ).fetchone()
        return row["last_comment_fetch"] if row else None

    def update_last_comment_fetch(self, mention_id, timestamp):
        self.conn.execute(
            "UPDATE mentions SET last_comment_fetch = ? WHERE mention_id = ?",
            (timestamp, mention_id),
        )
        self.conn.commit()

    def upsert_comment(self, comment):
        now = datetime.now().isoformat()
        comment_id = comment["comment_id"]
        row = self.conn.execute(
            "SELECT comment_id FROM comments WHERE comment_id = ?", (comment_id,)
        ).fetchone()

        if row is None:
            self.conn.execute(
                """
                INSERT INTO comments
                (comment_id, mention_id, platform, author, author_id, text, timestamp,
                 timestamp_confidence, geo_region, engagement_json, raw_json,
                 first_seen, last_seen)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    comment_id, comment["mention_id"], comment.get("_platform", ""),
                    comment.get("author", ""), comment.get("author_id", ""),
                    comment.get("text", ""), comment.get("timestamp", ""),
                    comment.get("timestamp_confidence", ""), comment.get("geo_region", ""),
                    json.dumps(comment.get("engagement", {}), ensure_ascii=False),
                    json.dumps(comment.get("_raw", {}), ensure_ascii=False),
                    now, now,
                ),
            )
            self.conn.commit()
            return "new"

        self.conn.execute("UPDATE comments SET last_seen = ? WHERE comment_id = ?", (now, comment_id))
        self.conn.commit()
        return "unchanged"

    def set_meta(self, key, value):
        self.conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self.conn.commit()

    def close(self):
        self.conn.close()


# ============================================================
# SOCIALCRAWL CLIENT
# ============================================================
class SocialCrawlClient:
    def __init__(self, api_key, base_url):
        self.api_key = api_key
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({"x-api-key": api_key, "Content-Type": "application/json"})

    def check_balance(self):
        try:
            resp = self.session.get(f"{self.base_url}/v1/credits/balance", timeout=10)
            data = resp.json()
            balance = (
                data.get("data", {}).get("balance")
                or data.get("credits_remaining")
                or data.get("balance")
            )
            if balance is not None:
                logger.info(f"Current credit balance: {balance}")
                return balance
            logger.warning(f"Balance not found: {data}")
            return -1
        except Exception as e:
            logger.error(f"Balance check failed: {e}")
            return -1

    def _run_search(self, endpoint, params, platform_hint, query, timeout=30, drop_counter=None):
        logger.info(f"Search: {platform_hint.upper()} | Query: {query} | Params: {params}")
        try:
            resp = self.session.get(endpoint, params=params, timeout=timeout)
            if resp.status_code != 200:
                logger.error(f"Search error [{platform_hint}]: {resp.status_code} {resp.text[:300]}")
                return []

            data = resp.json()
            raw_items = (
                data.get("data", {}).get("items")
                or data.get("data")
                or data.get("items")
                or data.get("results")
                or []
            )
            if not isinstance(raw_items, list):
                raw_items = []

            # DIAGNOSTIC: 200 OK but nothing extracted - show response shape
            if not raw_items:
                logger.warning(
                    f"[{platform_hint.upper()}] 200 OK but 0 raw items extracted. "
                    f"Top-level response keys: {list(data.keys()) if isinstance(data, dict) else type(data)}. "
                    f"Response snippet: {json.dumps(data, ensure_ascii=True)[:400]}"
                )

            # DIAGNOSTIC: platform tally BEFORE the allowlist filter runs -
            # tells you if e.g. facebook content exists upstream at all,
            # and under what tag, before anything gets dropped.
            if raw_items:
                tally = {}
                for raw in raw_items:
                    if isinstance(raw, dict):
                        tag = normalize_platform_tag(raw.get("source") or raw.get("platform") or "unknown")
                        tally[tag] = tally.get(tag, 0) + 1
                logger.info(f"[{platform_hint.upper()}] raw platform tally (pre-filter): {tally}")

            normalized = []
            dropped_count = 0
            for raw in raw_items:
                item = normalize_item(raw, platform_hint, query)
                if item is None:
                    continue
                if item["_platform"] not in ALLOWED_PLATFORMS:
                    dropped_count += 1
                    if drop_counter is not None:
                        drop_counter[item["_platform"]] = drop_counter.get(item["_platform"], 0) + 1
                    continue
                if within_date_window(item["timestamp"]):
                    normalized.append(item)

            logger.info(f"[{platform_hint.upper()}] {len(normalized)} in-scope items (dropped {dropped_count})")
            return normalized

        except requests.exceptions.ReadTimeout:
            logger.warning(f"Timeout on {platform_hint}")
            return []
        except Exception as e:
            logger.error(f"Exception on {platform_hint}: {e}")
            return []

    def fetch_reddit(self, query, limit=10, drop_counter=None):
        endpoint = f"{self.base_url}/v1/reddit/search"
        indian_query = f"{query} (subreddit:india OR subreddit:indiasocial OR subreddit:AskIndia)"
        params = {"query": indian_query, "limit": limit, "sort": "relevance"}
        return self._run_search(endpoint, params, "reddit", query, timeout=60, drop_counter=drop_counter)

    def fetch_twitter(self, query, limit=10, drop_counter=None):
        endpoint = f"{self.base_url}/v1/twitter/ai-search"
        params = {"query": f"{query} India", "limit": limit}
        return self._run_search(endpoint, params, "twitter", query, timeout=30, drop_counter=drop_counter)

    def fetch_everywhere_scoped(self, query, platforms, limit=10, drop_counter=None):
        endpoint = f"{self.base_url}/v1/search/everywhere"
        params = {"query": query, "platforms": ",".join(platforms), "gl": "in", "limit": limit}
        return self._run_search(endpoint, params, "everywhere", query, timeout=45, drop_counter=drop_counter)

    def fetch_comments_prism(self, post_url, max_pages=MAX_COMMENT_PAGES):
        endpoint = f"{self.base_url}/v1/prism/comments"
        all_comments = []
        cursor = None
        for _ in range(max_pages):
            params = {"url": post_url}
            if cursor:
                params["cursor"] = cursor
            try:
                resp = self.session.get(endpoint, params=params, timeout=30)
            except Exception as e:
                logger.error(f"Prism comments fetch error: {e}")
                break
            if resp.status_code != 200:
                logger.warning(f"Prism comments {resp.status_code} for {post_url}: {resp.text[:200]}")
                break
            data = resp.json()
            payload = data.get("data", {}) if isinstance(data.get("data"), dict) else {}
            items = payload.get("items") or data.get("data") or []
            if not isinstance(items, list):
                items = []
            all_comments.extend(items)
            cursor = payload.get("next_cursor")
            has_more = payload.get("has_more")
            if not cursor or not has_more:
                break
            time.sleep(0.3)
        return all_comments

    def fetch_author_profile(self, profile_url):
        if not profile_url:
            return {}
        endpoint = f"{self.base_url}/v1/prism/profiles"
        try:
            resp = self.session.get(endpoint, params={"url": profile_url}, timeout=20)
            if resp.status_code != 200:
                logger.debug(f"Profile lookup {resp.status_code} for {profile_url}")
                return {}
            data = resp.json()
            return data.get("data", {}) if isinstance(data.get("data"), dict) else {}
        except Exception as e:
            logger.debug(f"Profile lookup failed for {profile_url}: {e}")
            return {}

    def fetch_facebook_page_ratings(self, page_url):
        endpoint = f"{self.base_url}/v1/facebook/page/ratings"  # <-- VERIFY
        try:
            resp = self.session.get(endpoint, params={"url": page_url}, timeout=20)
            if resp.status_code != 200:
                logger.warning(f"FB ratings {resp.status_code}: {resp.text[:200]} - verify endpoint path")
                return []
            data = resp.json()
            items = data.get("data", {}).get("items") or data.get("data") or []
            return items if isinstance(items, list) else []
        except Exception as e:
            logger.error(f"FB ratings fetch failed: {e}")
            return []


# ============================================================
# MAIN WORKFLOW
# ============================================================
def main():
    logger.info("=" * 80)
    logger.info("INDIAN SOCIAL LISTENING - FB / IG / X / REDDIT / LINKEDIN")
    logger.info(f"Allowed platforms (hard filter): {', '.join(sorted(ALLOWED_PLATFORMS))}")
    logger.info(f"Comments supported by Prism (confirmed): {', '.join(sorted(PRISM_COMMENTS_SUPPORTED_PLATFORMS))}")
    logger.info(f"Native search: {', '.join(NATIVE_SEARCH_PLATFORMS)}")
    logger.info(f"Everywhere-scoped: {', '.join(EVERYWHERE_SCOPED_PLATFORMS)}")
    logger.info(f"Queries: {', '.join(TEST_QUERIES)}")
    logger.info(f"Date window: {DATE_FROM or '(open)'} to {DATE_TO or '(open)'}")
    logger.info("=" * 80)

    Path(RUN_EXPORT_DIR).mkdir(exist_ok=True)
    store = MentionStore(DB_FILE)
    client = SocialCrawlClient(API_KEY, BASE_URL)

    balance = client.check_balance()
    if balance == 0:
        logger.critical("No credits. Aborting.")
        store.close()
        return

    include_everywhere = True
    if balance is not None and balance != -1 and balance < 20:
        logger.warning("Skipping Instagram/Facebook/LinkedIn this run (everywhere call needs ~20 credits).")
        include_everywhere = False

    new_items, updated_items, unchanged_items = [], [], []
    comments_fetched = 0
    comments_skipped_unsupported = 0
    platform_stats = {}
    dropped_offplatform = {}
    profile_cache = {}

    for query in TEST_QUERIES:
        logger.info(f"--- Query: {query} ---")

        all_items = []
        all_items.extend(client.fetch_reddit(query, limit=LIMIT, drop_counter=dropped_offplatform))
        all_items.extend(client.fetch_twitter(query, limit=LIMIT, drop_counter=dropped_offplatform))
        if include_everywhere:
            all_items.extend(
                client.fetch_everywhere_scoped(query, EVERYWHERE_SCOPED_PLATFORMS, limit=LIMIT, drop_counter=dropped_offplatform)
            )

        for item in all_items:
            assert item["_platform"] in ALLOWED_PLATFORMS

            platform_stats[item["_platform"]] = platform_stats.get(item["_platform"], 0) + 1

            if FETCH_AUTHOR_PROFILES and not item.get("author_id") and item.get("author") not in ("", "Unknown"):
                cache_key = f"{item['_platform']}:{item['author']}"
                if cache_key not in profile_cache:
                    guess_url = guess_profile_url(item["_platform"], item["author"])
                    profile_cache[cache_key] = client.fetch_author_profile(guess_url) if guess_url else {}
                profile = profile_cache[cache_key]
                resolved_id = extract_author_id(profile)
                if resolved_id:
                    item["author_id"] = resolved_id

            item["mention_id"] = make_mention_id(item["_platform"], item)
            item["fingerprint"] = make_fingerprint(item)

            status = store.upsert_mention(item)
            if status == "new":
                new_items.append(item)
            elif status == "updated":
                updated_items.append(item)
            else:
                unchanged_items.append(item)

            # ---- FULL COMMENT FETCH - only on Prism-confirmed platforms ----
            if item["_platform"] not in PRISM_COMMENTS_SUPPORTED_PLATFORMS:
                if item.get("url"):
                    comments_skipped_unsupported += 1
                    logger.debug(
                        f"  Skipping comments for {item['mention_id']} - "
                        f"Prism doesn't support comments on {item['_platform']}"
                    )
            else:
                should_fetch = False
                if FETCH_FULL_COMMENTS and item.get("url"):
                    comment_count = (item.get("engagement") or {}).get("comments")
                    not_confirmed_zero = comment_count is None or comment_count > 0
                    if not_confirmed_zero:
                        if ALWAYS_REFRESH_COMMENTS:
                            should_fetch = True
                        elif status in ("new", "updated"):
                            should_fetch = True
                        else:
                            last_fetch = store.get_last_comment_fetch(item["mention_id"])
                            if last_fetch is None:
                                should_fetch = True
                            else:
                                try:
                                    days_ago = (datetime.now() - datetime.fromisoformat(last_fetch)).days
                                except ValueError:
                                    days_ago = 999
                                should_fetch = days_ago >= COMMENT_FETCH_DAYS

                if should_fetch:
                    raw_comments = client.fetch_comments_prism(item["url"])
                    for rc in raw_comments:
                        comment_obj = rc.get("comment", rc) if isinstance(rc, dict) else {}
                        content = comment_obj.get("content", {})
                        content = content if isinstance(content, dict) else {}
                        author = comment_obj.get("author", {})
                        author = author if isinstance(author, dict) else {}

                        author_name = author.get("username") or author.get("display_name") or author.get("name") or ""
                        author_id = extract_author_id(author)
                        text = content.get("text") or comment_obj.get("text") or ""
                        ts = comment_obj.get("published_at") or comment_obj.get("created_at") or ""
                        ts_confidence = comment_obj.get("date_confidence", "")
                        geo_region = detect_geo_region(text, author.get("location", ""))
                        engagement = clean_engagement(comment_obj.get("engagement", {}))

                        comment_entry = {
                            "comment_id": make_comment_id(item["mention_id"], comment_obj),
                            "mention_id": item["mention_id"],
                            "_platform": item["_platform"],
                            "author": author_name,
                            "author_id": author_id,
                            "text": text,
                            "timestamp": ts,
                            "timestamp_confidence": ts_confidence,
                            "geo_region": geo_region,
                            "engagement": engagement,
                            "_raw": comment_obj,
                        }
                        store.upsert_comment(comment_entry)
                        comments_fetched += 1

                    store.update_last_comment_fetch(item["mention_id"], datetime.now().isoformat())
                    logger.info(f"  Comments fetched for {item['mention_id']}: {len(raw_comments)}")

            if FETCH_FACEBOOK_PAGE_RATINGS and item["_platform"] == "facebook" and item.get("url"):
                client.fetch_facebook_page_ratings(item["url"])

            time.sleep(0.2)

    store.set_meta("last_run", datetime.now().isoformat())

    logger.info("=" * 80)
    logger.info("RUN SUMMARY")
    logger.info("=" * 80)
    for platform, count in sorted(platform_stats.items()):
        logger.info(f"[{platform.upper()}] fetched: {count}")
    if dropped_offplatform:
        logger.info(f"Dropped (outside allowlist): {dropped_offplatform}")
    logger.info(f"NEW mentions:              {len(new_items)}")
    logger.info(f"UPDATED mentions:          {len(updated_items)}")
    logger.info(f"UNCHANGED (skipped):       {len(unchanged_items)}")
    logger.info(f"Comments fetched:          {comments_fetched}")
    logger.info(f"Comments skipped (platform not supported by Prism): {comments_skipped_unsupported}")

    export = {
        "run_at": datetime.now().isoformat(),
        "queries": TEST_QUERIES,
        "allowed_platforms": sorted(ALLOWED_PLATFORMS),
        "comments_supported_platforms": sorted(PRISM_COMMENTS_SUPPORTED_PLATFORMS),
        "date_window": {"from": DATE_FROM, "to": DATE_TO},
        "stats": {
            "new": len(new_items),
            "updated": len(updated_items),
            "unchanged": len(unchanged_items),
            "comments_new": comments_fetched,
            "comments_skipped_unsupported_platform": comments_skipped_unsupported,
            "by_platform": platform_stats,
            "dropped_offplatform": dropped_offplatform,
        },
        "new_mentions": new_items,
        "updated_mentions": updated_items,
    }
    export_file = f"{RUN_EXPORT_DIR}/run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(export_file, "w", encoding="utf-8") as f:
        json.dump(export, f, indent=2, ensure_ascii=False)

    logger.info(f"Run delta saved to: {export_file}")
    logger.info(f"Full database: {DB_FILE}")
    logger.info(f"Log file: {LOG_FILE}")
    logger.info("=" * 80)

    store.close()


if __name__ == "__main__":
    main()