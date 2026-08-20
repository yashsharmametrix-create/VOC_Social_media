# -*- coding: utf-8 -*-
"""
LinkedIn Ads extraction using SocialCrawl.

Searches LinkedIn Ads, handles pagination, fetches detailed data for
each unique ad URL, and saves everything into ONE JSON file:
    json_responses/all_linkedin_ads.json
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

import requests


# ============================================================
# CONFIGURATION
# ============================================================

API_KEY = "sc_QPRRy3AT7j5xb5T5EuztzntY0rjsQynv9CEZpTarh2k"

BASE_URL = "https://www.socialcrawl.dev"
SEARCH_ENDPOINT = f"{BASE_URL}/v1/linkedin/ads/search"
DETAIL_ENDPOINT = f"{BASE_URL}/v1/linkedin/ad"

# Change/add searches as required.
SEARCHES = [
    {
        "company": "LG",
        "keyword": "AC",
        "countries": "IN",
        "startDate": "2026-01-01",
        "endDate": "2026-03-31",
    },
    {
        "company": "LG",
        "keyword": "Air Conditioner",
        "countries": "IN",
        "startDate": "2026-01-01",
        "endDate": "2026-03-31",
    },
]

# None = all available pages.
# For testing, you can set this to 1 or 2.
MAX_SEARCH_PAGES: Optional[int] = 2

REQUEST_DELAY_SECONDS = 1.0
REQUEST_TIMEOUT_SECONDS = 60

OUTPUT_DIR = "json_responses"
OUTPUT_FILE = os.path.join(
    OUTPUT_DIR,
    "all_linkedin_ads.json",
)


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger("linkedin_ads")


# ============================================================
# HELPERS
# ============================================================

def validate_api_key() -> None:
    if not API_KEY:
        logger.error(
            "SOCIALCRAWL_API_KEY is not set."
        )
        logger.error(
            "CMD: set SOCIALCRAWL_API_KEY=YOUR_API_KEY"
        )
        logger.error(
            "PowerShell: $env:SOCIALCRAWL_API_KEY='YOUR_API_KEY'"
        )
        sys.exit(1)


def request_json(
    endpoint: str,
    params: Dict[str, Any],
    label: str,
) -> Optional[Dict[str, Any]]:
    headers = {
        "x-api-key": API_KEY,
        "Accept": "application/json",
        "User-Agent": "linkedin-ads-extractor/1.0",
    }

    logger.info("[%s] Endpoint: %s", label, endpoint)
    logger.info("[%s] Params: %s", label, params)

    try:
        response = requests.get(
            endpoint,
            params=params,
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )

        logger.info(
            "[%s] status=%s",
            label,
            response.status_code,
        )

        if response.status_code != 200:
            logger.error(
                "[%s] HTTP error: %s",
                label,
                response.text[:2000],
            )
            return None

        data = response.json()

        if not isinstance(data, dict):
            logger.error(
                "[%s] Expected JSON object, got %s",
                label,
                type(data).__name__,
            )
            return None

        if data.get("success") is False:
            logger.error(
                "[%s] API returned success=false: %s",
                label,
                json.dumps(data, ensure_ascii=False)[:3000],
            )
            return None

        return data

    except requests.RequestException as exc:
        logger.error("[%s] Request failed: %s", label, exc)
        return None

    except ValueError as exc:
        logger.error(
            "[%s] Invalid JSON response: %s",
            label,
            exc,
        )
        return None


def get_items(data: Dict[str, Any]) -> List[Any]:
    payload = data.get("data")

    if not isinstance(payload, dict):
        return []

    items = payload.get("items")

    return items if isinstance(items, list) else []


def get_next_token(data: Dict[str, Any]) -> Optional[str]:
    payload = data.get("data")

    if not isinstance(payload, dict):
        return None

    candidates = [
        payload.get("paginationToken"),
        payload.get("next_cursor"),
        payload.get("nextCursor"),
    ]

    pagination = payload.get("pagination")

    if isinstance(pagination, dict):
        candidates.extend(
            [
                pagination.get("paginationToken"),
                pagination.get("next_cursor"),
                pagination.get("nextCursor"),
            ]
        )

    for token in candidates:
        if token:
            return str(token)

    return None


def recursive_find_url(obj: Any) -> Optional[str]:
    """
    Finds a LinkedIn URL anywhere inside a search item.
    """

    if isinstance(obj, dict):
        preferred_keys = [
            "url",
            "ad_url",
            "adUrl",
            "linkedin_url",
            "linkedinUrl",
        ]

        for key in preferred_keys:
            value = obj.get(key)

            if (
                isinstance(value, str)
                and value.startswith("http")
                and "linkedin.com" in value.lower()
            ):
                return value

        for value in obj.values():
            result = recursive_find_url(value)

            if result:
                return result

    elif isinstance(obj, list):
        for value in obj:
            result = recursive_find_url(value)

            if result:
                return result

    elif isinstance(obj, str):
        if (
            obj.startswith("http")
            and "linkedin.com" in obj.lower()
        ):
            return obj

    return None


def recursive_find_id(obj: Any) -> Optional[str]:
    """
    Finds a likely advertisement ID anywhere inside a search item.
    """

    if isinstance(obj, dict):
        preferred_keys = [
            "ad_id",
            "adId",
            "id",
            "item_id",
            "itemId",
            "candidate_id",
            "candidateId",
        ]

        for key in preferred_keys:
            value = obj.get(key)

            if isinstance(value, (str, int)):
                return str(value)

        for value in obj.values():
            result = recursive_find_id(value)

            if result:
                return result

    elif isinstance(obj, list):
        for value in obj:
            result = recursive_find_id(value)

            if result:
                return result

    return None


def normalize_url(url: str) -> str:
    try:
        parsed = urlparse(url)

        return (
            f"{parsed.scheme.lower()}://"
            f"{parsed.netloc.lower()}"
            f"{parsed.path.rstrip('/')}"
        )

    except Exception:
        return url.rstrip("/")


# ============================================================
# LINKEDIN ADS CLIENT
# ============================================================

class LinkedInAdsClient:

    def __init__(self) -> None:
        self.search_requests = 0
        self.search_items = 0
        self.detail_requests = 0
        self.detail_success = 0
        self.detail_failed = 0

    def search_ads(
        self,
        search_config: Dict[str, Any],
    ) -> List[Dict[str, Any]]:

        results: List[Dict[str, Any]] = []

        pagination_token: Optional[str] = None
        page_number = 0

        while True:

            page_number += 1

            if (
                MAX_SEARCH_PAGES is not None
                and page_number > MAX_SEARCH_PAGES
            ):
                logger.info(
                    "Reached MAX_SEARCH_PAGES=%s",
                    MAX_SEARCH_PAGES,
                )
                break

            params = dict(search_config)

            if pagination_token:
                params["paginationToken"] = pagination_token

            data = request_json(
                SEARCH_ENDPOINT,
                params,
                f"SEARCH page {page_number}",
            )

            self.search_requests += 1

            if data is None:
                break

            items = get_items(data)

            self.search_items += len(items)

            logger.info(
                "[SEARCH] page=%s items=%s",
                page_number,
                len(items),
            )

            for item in items:

                ad_url = recursive_find_url(item)
                ad_id = recursive_find_id(item)

                results.append(
                    {
                        "search_config": dict(search_config),
                        "page_number": page_number,
                        "search_item": item,
                        "ad_url": ad_url,
                        "ad_id": ad_id,
                    }
                )

            next_token = get_next_token(data)

            if not next_token:
                logger.info(
                    "[SEARCH] No next pagination token."
                )
                break

            if next_token == pagination_token:
                logger.warning(
                    "[SEARCH] Pagination token did not change."
                )
                break

            pagination_token = next_token

            time.sleep(REQUEST_DELAY_SECONDS)

        return results

    def get_ad_details(
        self,
        ad_url: str,
    ) -> Optional[Dict[str, Any]]:

        self.detail_requests += 1

        data = request_json(
            DETAIL_ENDPOINT,
            {"url": ad_url},
            "AD DETAILS",
        )

        if data is None:
            self.detail_failed += 1
            return None

        self.detail_success += 1

        return data


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    validate_api_key()

    logger.info("=" * 80)
    logger.info("LINKEDIN ADS EXTRACTION")
    logger.info("=" * 80)

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True,
    )

    client = LinkedInAdsClient()

    all_records: List[Dict[str, Any]] = []

    processed_ads: Set[str] = set()

    for search_number, search_config in enumerate(
        SEARCHES,
        start=1,
    ):

        logger.info("")
        logger.info("=" * 60)
        logger.info(
            "SEARCH %s/%s: %s",
            search_number,
            len(SEARCHES),
            search_config,
        )
        logger.info("=" * 60)

        search_results = client.search_ads(
            search_config
        )

        logger.info(
            "Search returned %s items.",
            len(search_results),
        )

        for index, result in enumerate(
            search_results,
            start=1,
        ):

            ad_url = result.get("ad_url")
            ad_id = result.get("ad_id")

            if ad_url:
                unique_key = normalize_url(ad_url)
            elif ad_id:
                unique_key = f"id:{ad_id}"
            else:
                unique_key = ""

            if not unique_key:

                logger.warning(
                    "[AD %s/%s] No ad URL or ID found.",
                    index,
                    len(search_results),
                )

                all_records.append(
                    {
                        "query": search_config,
                        "ad_url": None,
                        "ad_id": None,
                        "search_result": result.get(
                            "search_item"
                        ),
                        "ad_details": None,
                        "detail_status": "no_ad_identifier",
                    }
                )

                continue

            if unique_key in processed_ads:

                logger.info(
                    "[AD %s/%s] Duplicate - skipped.",
                    index,
                    len(search_results),
                )

                continue

            processed_ads.add(unique_key)

            logger.info(
                "[AD %s/%s] URL=%s",
                index,
                len(search_results),
                ad_url,
            )

            details = None

            if ad_url:
                details = client.get_ad_details(
                    ad_url
                )

            all_records.append(
                {
                    "query": search_config,
                    "ad_url": ad_url,
                    "ad_id": ad_id,
                    "search_result": result.get(
                        "search_item"
                    ),
                    "ad_details": details,
                    "detail_status": (
                        "success"
                        if details is not None
                        else "failed"
                    ),
                }
            )

            time.sleep(
                REQUEST_DELAY_SECONDS
            )

    # ========================================================
    # SAVE ONE JSON
    # ========================================================

    output = {
        "metadata": {
            "platform": "linkedin",
            "data_type": "ads",
            "generated_at": (
                datetime.utcnow().isoformat() + "Z"
            ),
            "search_endpoint": SEARCH_ENDPOINT,
            "detail_endpoint": DETAIL_ENDPOINT,
            "searches": SEARCHES,
            "search_requests": client.search_requests,
            "search_items": client.search_items,
            "unique_ads": len(processed_ads),
            "detail_requests": client.detail_requests,
            "detail_success": client.detail_success,
            "detail_failed": client.detail_failed,
            "total_records": len(all_records),
        },
        "items": all_records,
    }

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            output,
            f,
            indent=2,
            ensure_ascii=False,
        )

    logger.info("")
    logger.info("=" * 80)
    logger.info("LINKEDIN ADS EXTRACTION COMPLETE")
    logger.info("=" * 80)
    logger.info(
        "Search requests: %s",
        client.search_requests,
    )
    logger.info(
        "Search items: %s",
        client.search_items,
    )
    logger.info(
        "Unique ads: %s",
        len(processed_ads),
    )
    logger.info(
        "Detail requests: %s",
        client.detail_requests,
    )
    logger.info(
        "Detail success: %s",
        client.detail_success,
    )
    logger.info(
        "Detail failed: %s",
        client.detail_failed,
    )
    logger.info(
        "JSON records: %s",
        len(all_records),
    )
    logger.info(
        "Output: %s",
        OUTPUT_FILE,
    )


if __name__ == "__main__":
    main()