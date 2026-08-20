import json, logging, os, time
from datetime import datetime, timezone
from pathlib import Path
import requests

API_KEY = "sc_QPRRy3AT7j5xb5T5EuztzntY0rjsQynv9CEZpTarh2k"
BASE_URL = "https://www.socialcrawl.dev"
FACEBOOK_PAGE_URL = "https://www.facebook.com/DaikinIndia/"
START_DATE = "2026-01-01"
END_DATE = "2026-08-18"
MAX_POST_PAGES = 10
MAX_COMMENT_PAGES = 10
REQUEST_DELAY = 1.0
OUTPUT_DIR = Path("json_responses")
OUTPUT_FILE = OUTPUT_DIR / "all_facebook_data.json"
DEBUG_DIR = Path("debug_raw_responses")
POSTS_ENDPOINT = f"{BASE_URL}/v1/facebook/profile/posts"
COMMENTS_ENDPOINT = f"{BASE_URL}/v1/facebook/post/comments"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def first_value(*values):
    for v in values:
        if v is not None and v != "": return v
    return None

def parse_date(value):
    if value is None: return None
    if isinstance(value, (int,float)):
        try:
            ts=float(value); ts /= 1000 if ts > 10_000_000_000 else 1
            return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
        except Exception: return None
    text=str(value).strip()
    if not text: return None
    try:
        dt=datetime.fromisoformat(text.replace("Z","+00:00"))
        return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt
    except Exception: pass
    for fmt in ("%Y-%m-%d","%Y/%m/%d","%d-%m-%Y","%d/%m/%Y","%Y-%m-%d %H:%M:%S","%Y/%m/%d %H:%M:%S","%d-%m-%Y %H:%M:%S","%d/%m/%Y %H:%M:%S","%B %d, %Y","%b %d, %Y"):
        try: return datetime.strptime(text,fmt)
        except Exception: pass
    return None

def post_node(item): return item.get("post") if isinstance(item.get("post"),dict) else {}
def get_post_date(item):
    p=post_node(item); m=item.get("metadata") if isinstance(item.get("metadata"),dict) else {}
    for v in [p.get("timestamp"),p.get("created_at"),p.get("published_at"),p.get("date"),item.get("timestamp"),item.get("created_at"),item.get("published_at"),item.get("date"),item.get("datetime"),item.get("created_time"),m.get("timestamp"),m.get("created_at"),m.get("published_at"),m.get("date")]:
        d=parse_date(v)
        if d: return d
    return None

def get_post_id(item):
    p=post_node(item); return first_value(p.get("id"),item.get("id"),item.get("post_id"))
def get_post_url(item):
    p=post_node(item); return first_value(p.get("url"),item.get("url"),item.get("post_url"),item.get("permalink"))
def get_post_text(item):
    p=post_node(item); c=p.get("content") if isinstance(p.get("content"),dict) else {}
    return first_value(c.get("text"),p.get("text"),p.get("caption"),item.get("text"),item.get("caption"),item.get("content")) or ""

def save_debug(name,payload):
    try:
        DEBUG_DIR.mkdir(parents=True,exist_ok=True)
        with (DEBUG_DIR/f"{name}.json").open("w",encoding="utf-8") as f: json.dump(payload,f,indent=2,ensure_ascii=False)
    except Exception as e: logger.warning("Could not save debug response: %s",e)

def extract_items(payload):
    data=payload.get("data")
    if isinstance(data,dict): return data.get("items") or [],data
    if isinstance(data,list): return data,payload
    return payload.get("items") or [],payload

class FacebookClient:
    def __init__(self,key):
        if not key: raise RuntimeError("Set SOCIALCRAWL_API_KEY environment variable before running.")
        self.session=requests.Session(); self.session.headers.update({"x-api-key":key,"Accept":"application/json"})

    def fetch_posts(self):
        start=datetime.strptime(START_DATE,"%Y-%m-%d"); end=datetime.strptime(END_DATE,"%Y-%m-%d")
        all_posts=[]; cursor=None
        for page in range(1,MAX_POST_PAGES+1):
            params={"url":FACEBOOK_PAGE_URL};
            if cursor: params["cursor"]=cursor
            logger.info("[FACEBOOK PROFILE POSTS] Page %s Params: %s",page,params)
            try: r=self.session.get(POSTS_ENDPOINT,params=params,timeout=90)
            except requests.RequestException as e: logger.error("Posts request failed: %s",e); break
            logger.info("[FACEBOOK PROFILE POSTS] HTTP %s",r.status_code)
            if r.status_code!=200: logger.error(r.text[:3000]); break
            try: payload=r.json()
            except ValueError: logger.error("Invalid JSON: %s",r.text[:2000]); break
            save_debug(f"facebook_posts_page_{page}",payload)
            items,pagination=extract_items(payload)
            logger.info("[FACEBOOK POSTS] Page %s -> %s posts",page,len(items))
            if not items: logger.warning("Raw response: %s",json.dumps(payload,indent=2)[:10000]); break
            all_posts.extend(items)
            dates=[d for d in (get_post_date(x) for x in items) if d]
            if dates:
                oldest=min(dates); logger.info("Oldest date on page: %s",oldest.date())
                if oldest < start:
                    logger.info("Reached START_DATE boundary; stopping post pagination."); break
            cursor=pagination.get("next_cursor")
            if not cursor or not pagination.get("has_more"):
                logger.info("No more post pages."); break
            time.sleep(REQUEST_DELAY)
        unique={str(get_post_id(x) or get_post_url(x)):x for x in all_posts if get_post_id(x) or get_post_url(x)}
        filtered=[x for x in unique.values() if (lambda d: d is not None and start<=d<=end)(get_post_date(x))]
        logger.info("Total unique posts received: %s",len(unique)); logger.info("Posts in range: %s",len(filtered))
        return filtered,list(unique.values())

    def fetch_comments(self,url):
        if not url: return []
        comments=[]; cursor=None
        for page in range(1,MAX_COMMENT_PAGES+1):
            params={"url":url};
            if cursor: params["cursor"]=cursor
            logger.info("[FACEBOOK COMMENTS] Page %s Params: %s",page,params)
            try: r=self.session.get(COMMENTS_ENDPOINT,params=params,timeout=90)
            except requests.RequestException as e: logger.error("Comments request failed: %s",e); break
            logger.info("[FACEBOOK COMMENTS] HTTP %s",r.status_code)
            if r.status_code!=200: logger.error(r.text[:3000]); break
            try: payload=r.json()
            except ValueError: break
            save_debug(f"facebook_comments_{page}",payload)
            items,pagination=extract_items(payload); comments.extend(items)
            logger.info("[COMMENTS] Page %s -> %s comments",page,len(items))
            cursor=pagination.get("next_cursor")
            if not cursor or not pagination.get("has_more"): break
            time.sleep(REQUEST_DELAY)
        return comments

def main():
    logger.info("="*80); logger.info("FACEBOOK-ONLY POSTS + COMMENTS EXTRACTION"); logger.info("="*80)
    logger.info("Page: %s",FACEBOOK_PAGE_URL); logger.info("Date range: %s -> %s",START_DATE,END_DATE)
    client=FacebookClient(API_KEY)
    filtered,received=client.fetch_posts(); output=[]; total_comments=0
    for i,raw in enumerate(filtered,1):
        dt=get_post_date(raw); url=get_post_url(raw); comments=client.fetch_comments(url)
        total_comments+=len(comments)
        output.append({"platform":"facebook","post_id":get_post_id(raw),"post_url":url,"post_date":dt.isoformat() if dt else None,"post_text":get_post_text(raw),"comments_count_extracted":len(comments),"comments":comments,"raw_post":raw})
        logger.info("[%s/%s] %s comments",i,len(filtered),len(comments))
    OUTPUT_DIR.mkdir(parents=True,exist_ok=True)
    result={"platform":"facebook","facebook_page":FACEBOOK_PAGE_URL,"requested_date_range":{"start_date":START_DATE,"end_date":END_DATE},"summary":{"facebook_posts_received":len(received),"posts_in_date_range":len(filtered),"posts_saved":len(output),"comments_extracted":total_comments},"posts":output}
    with OUTPUT_FILE.open("w",encoding="utf-8") as f: json.dump(result,f,indent=2,ensure_ascii=False)
    logger.info("="*80); logger.info("FACEBOOK EXTRACTION COMPLETE"); logger.info("Posts received: %s",len(received)); logger.info("Posts in range: %s",len(filtered)); logger.info("Comments: %s",total_comments); logger.info("Output: %s",OUTPUT_FILE); logger.info("="*80)

if __name__=="__main__": main()








