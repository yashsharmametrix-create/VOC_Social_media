# LinkedIn Comments Extraction - Feature Summary

## **What This Script Can Do:**

### ✅ **1. Extract Comments**
- Fetches comments from LinkedIn posts using SocialCrawl Prism endpoint
- Stores comments with full metadata (ID, author, text, likes, timestamp)

### ✅ **2. Extract User IDs**
- Extracts native platform user IDs from author data
- Stores `author_id` for both posts and comments
- Supports multiple field name variations: `id`, `user_id`, `pk`, `author_id`, etc.

### ✅ **3. Date Range Filtering (Period-wise Data)**
- Configurable `DATE_FROM` and `DATE_TO` parameters
- Filters posts and comments based on timestamps
- Format: "YYYY-MM-DD" (e.g., "2026-07-01")
- Set to `None` to capture all time periods

**Example:**
```python
DATE_FROM = "2026-07-01"
DATE_TO = "2026-07-31"
```

### ✅ **4. Geographic Information (India Region Detection)**
- Automatically detects Indian states and major cities from post/comment text
- Stores `geo_region` in database for both posts and comments
- Uses comprehensive list of 40+ Indian states and 50+ major cities

**Detects:**
- States: Maharashtra, Tamil Nadu, Karnataka, Delhi, etc.
- Major Cities: Mumbai, Bengaluru, Chennai, Kolkata, Hyderabad, etc.

### ✅ **5. Database Features**
- **Posts Table:** Stores LinkedIn posts with all metadata
- **Comments Table:** Stores comments with references to parent posts
- **Indexes:** Optimized queries on post_id, author, timestamp, and geo_region
- **Upsert Logic:** Updates existing records instead of duplicates

## **Configuration Options:**

```python
# Search queries
TEST_QUERIES = [
    "LG AC",
    "LG Air Conditioner",
]

# Results per query
LIMIT = 10

# Period filter (set to None for all time)
DATE_FROM = None     # "2026-07-01"
DATE_TO = None       # "2026-07-31"

# Comment fetching settings
MAX_COMMENT_PAGES = 5
```

## **Database Schema:**

### **posts Table:**
- `post_id` (primary key)
- `title` - Post title
- `text` - Post content
- `author` - Author name
- `author_id` - Native platform user ID
- `url` - Post URL
- `timestamp` - When post was created
- `likes` - Engagement metric
- `comments_count` - Total comments
- `reposts` - Repost count
- `location` - Author's location
- `geo_region` - Detected Indian state/city
- `raw_json` - Full API response
- `fetched_at` - When data was stored

### **comments Table:**
- `comment_id` (primary key)
- `post_id` (foreign key)
- `author` - Commenter name
- `author_id` - Native platform user ID
- `text` - Comment content
- `likes` - Engagement metric
- `timestamp` - When comment was created
- `geo_region` - Detected Indian state/city
- `raw_json` - Full API response
- `fetched_at` - When data was stored

## **How to Use:**

### **Basic Usage:**
```bash
python platform_linkedin_comments.py
```

### **With Date Range:**
```python
DATE_FROM = "2026-07-01"
DATE_TO = "2026-07-31"
```

### **With Specific Queries:**
```python
TEST_QUERIES = [
    "Blue Star",
    "Blue Star Conditioner",
    "LG AC",
]
```

### **With Geographic Filtering:**
The script automatically detects and stores Indian regions. You can query the database:
```sql
SELECT geo_region, COUNT(*) as count
FROM posts
WHERE geo_region != ''
GROUP BY geo_region;
```

## **Output:**

- **Database:** `linkedin_comments.db` (SQLite)
- **Log File:** `linkedin_comments_YYYYMMDD.log`
- **Statistics:** Shows items stored (new/updated/unchanged/skipped)

## **Key Features Summary:**

| Feature | Status | Description |
|---------|--------|-------------|
| Comment Extraction | ✅ | Fetches comments from LinkedIn posts |
| User ID Extraction | ✅ | Extracts native platform user IDs |
| Date Range Filtering | ✅ | Filter by specific date periods |
| Geographic Detection | ✅ | Auto-detects Indian states/cities |
| Database Storage | ✅ | SQLite with posts and comments tables |
| Upsert Logic | ✅ | Updates existing records |
| Logging | ✅ | Detailed logging to file and console |

## **API Endpoints Used:**

1. **Search:** `https://www.socialcrawl.dev/v1/search/everywhere`
   - Parameters: query, platforms, gl, limit, from_date, to_date

2. **Comments:** `https://www.socialcrawl.dev/v1/prism/comments`
   - Parameters: url, cursor (for pagination)

## **Troubleshooting:**

### **No comments fetched?**
- Check if `post_url` is available in the API response
- Verify API key and credits
- Check log file for error messages

### **Date filtering not working?**
- Ensure timestamps are in correct format
- Check that DATE_FROM and DATE_TO are properly formatted
- Verify timestamps exist in the API response

### **Geographic detection not working?**
- Ensure Indian state/city names appear in post text
- Check that `geo_region` column is populated in database
- Verify the `INDIA_GEO_KEYWORDS` list is complete

## **Next Steps:**

1. Run the script with your desired configuration
2. Check the log file for progress and errors
3. Query the database to analyze extracted data
4. Use SQL queries to filter by date, geo_region, author, etc.
