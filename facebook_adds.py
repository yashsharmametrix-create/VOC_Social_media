import json
import logging
import time
import requests

# ============================================================
# CONFIGURATION
# ============================================================

API_KEY = "sc_QPRRy3AT7j5xb5T5EuztzntY0rjsQynv9CEZpTarh2k"
BASE_URL = "https://www.socialcrawl.dev"
COMPANY_ADS_ENDPOINT = f"{BASE_URL}/v1/facebook/adlibrary/company/ads"

# Choose ONE of the following (pageId is preferred if known)
PAGE_ID = None          # Example: Meta's page ID
COMPANY_NAME = "Daikin India"        # Alternative: use company name

# Optional filters
START_DATE = "2026-01-01"
END_DATE = "2026-08-18"
AD_STATUS = "ACTIVE"                 # "ALL", "ACTIVE", "INACTIVE"
COUNTRY = "IN"
MEDIA_TYPE = "ALL"
SORT_BY = "total_impressions"        # or "relevancy_monthly_grouped"

# Pagination settings
MAX_PAGES = 5
REQUEST_DELAY = 1.0   # seconds between requests

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ============================================================
# FETCH COMPANY ADS
# ============================================================

def fetch_company_ads():
    """
    Fetches all ads for a company/page using the SocialCrawl Ad Library API.
    Returns a list of ad items.
    """
    session = requests.Session()
    session.headers.update({
        "x-api-key": API_KEY,
        "Accept": "application/json",
    })

    all_ads = []
    cursor = None

    for page_num in range(1, MAX_PAGES + 1):
        # Build request parameters
        params = {
            "status": AD_STATUS,
            "sort_by": SORT_BY,
            "country": COUNTRY,
            "media_type": MEDIA_TYPE,
        }

        # Use either pageId or companyName
        if PAGE_ID:
            params["pageId"] = PAGE_ID
        elif COMPANY_NAME:
            params["companyName"] = COMPANY_NAME
        else:
            raise ValueError("You must provide either pageId or companyName")

        # Date filters (if provided)
        if START_DATE:
            params["start_date"] = START_DATE
        if END_DATE:
            params["end_date"] = END_DATE

        # Pagination cursor
        if cursor:
            params["cursor"] = cursor

        logger.info(f"[COMPANY ADS] Requesting page {page_num} with params: {params}")

        try:
            response = session.get(COMPANY_ADS_ENDPOINT, params=params, timeout=90)
        except requests.RequestException as e:
            logger.error(f"Request failed: {e}")
            break

        logger.info(f"[COMPANY ADS] HTTP Status: {response.status_code}")

        if response.status_code != 200:
            logger.error(f"Error response: {response.text[:3000]}")
            break

        try:
            payload = response.json()
        except ValueError:
            logger.error(f"Invalid JSON: {response.text[:2000]}")
            break

        # Extract ad items and pagination info
        data = payload.get("data", {})
        items = data.get("items", [])
        pagination = payload.get("pagination", {})

        logger.info(f"[COMPANY ADS] Page {page_num} returned {len(items)} ads")

        if not items:
            logger.info("No ads on this page; stopping.")
            break

        all_ads.extend(items)

        # Check if more pages exist
        next_cursor = pagination.get("next_cursor")
        has_more = pagination.get("has_more", False)

        if not next_cursor or not has_more:
            logger.info("No more pages available.")
            break

        cursor = next_cursor
        time.sleep(REQUEST_DELAY)

    logger.info(f"[COMPANY ADS] Total ads fetched: {len(all_ads)}")
    return all_ads

# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 80)
    print("FACEBOOK AD LIBRARY - COMPANY ADS EXTRACTION")
    print("=" * 80)
    print(f"Endpoint: {COMPANY_ADS_ENDPOINT}")
    print(f"Page ID: {PAGE_ID}")
    print(f"Company Name: {COMPANY_NAME}")
    print(f"Date Range: {START_DATE} -> {END_DATE}")
    print(f"Status: {AD_STATUS}")
    print("=" * 80)

    ads = fetch_company_ads()

    # Save the result
    output_file = "facebook_company_ads.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "platform": "facebook",
            "endpoint": "adlibrary/company/ads",
            "page_id": PAGE_ID,
            "company_name": COMPANY_NAME,
            "filters": {
                "start_date": START_DATE,
                "end_date": END_DATE,
                "status": AD_STATUS,
                "country": COUNTRY,
                "media_type": MEDIA_TYPE,
                "sort_by": SORT_BY
            },
            "total_ads": len(ads),
            "ads": ads
        }, f, indent=2, ensure_ascii=False)

    print("=" * 80)
    print("EXTRACTION COMPLETE")
    print(f"Total ads: {len(ads)}")
    print(f"Output saved to: {output_file}")
    print("=" * 80)

if __name__ == "__main__":
    main()