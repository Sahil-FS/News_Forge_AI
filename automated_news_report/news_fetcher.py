# news_fetcher.py -- Fetch the latest BBC news article via RSS
#
# FIX (2026-05-05):
#   feedparser.parse(url) does its own HTTP internally with no timeout
#   and no retry -- a partial TCP response causes IncompleteRead and crashes
#   the pipeline.  Solution: fetch RSS bytes ourselves with requests
#   (timeout + retry + browser User-Agent), then pass raw bytes to
#   feedparser.parse() which only does XML parsing when given bytes/string.

import re
import time
import feedparser
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import RSS_FEED_URL


# ── Feeds scored together for high-impact headline selection ────────────────
_ALL_FEEDS = [
    # BBC
    "https://feeds.bbci.co.uk/news/rss.xml",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://feeds.bbci.co.uk/news/world/asia/india/rss.xml",
    # Reuters
    "https://feeds.skynews.com/feeds/rss/world.xml",
    "https://rss.dw.com/rdf/rss-en-world",
    # Times of India
    "https://timesofindia.indiatimes.com/rssfeeds/296589292.cms",
    # NDTV
    "https://feeds.feedburner.com/ndtvnews-top-stories",
    # Al Jazeera
    "https://www.aljazeera.com/xml/rss/all.xml",
]

# Phase 9 ─ Category-specific feed pools
_CATEGORY_FEEDS = {
    "general": _ALL_FEEDS,

    "sports": [
        "https://feeds.bbci.co.uk/sport/rss.xml",
        "https://www.espn.com/espn/rss/news",
        "https://timesofindia.indiatimes.com/rssfeeds/4719161.cms",  # TOI Sports
        "https://rss.dw.com/rdf/rss-en-sport",
        "https://feeds.skynews.com/feeds/rss/sports.xml",
    ],

    "entertainment": [
        "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml",
        "https://www.hollywoodreporter.com/feed",
        "https://variety.com/feed/",
        "https://timesofindia.indiatimes.com/rssfeeds/1081479906.cms",  # TOI Entertainment
        "https://feeds.skynews.com/feeds/rss/entertainment.xml",
    ],

    "business": [
        "https://feeds.bbci.co.uk/news/business/rss.xml",
        "https://rss.dw.com/rdf/rss-en-business",
        "https://timesofindia.indiatimes.com/rssfeeds/1898055.cms",   # TOI Business
        "https://feeds.skynews.com/feeds/rss/business.xml",
        "https://feeds.feedburner.com/ndtvnews-business",
    ],

    "tech": [
        "https://feeds.bbci.co.uk/news/technology/rss.xml",
        "https://rss.dw.com/rdf/rss-en-technology",
        "https://timesofindia.indiatimes.com/rssfeeds/66949542.cms",  # TOI Tech
        "https://feeds.skynews.com/feeds/rss/technology.xml",
        "https://feeds.feedburner.com/ndtvnews-tech-media-gadgets",
    ],

    "world": [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://rss.dw.com/rdf/rss-en-world",
        "https://feeds.skynews.com/feeds/rss/world.xml",
        "https://www.aljazeera.com/xml/rss/all.xml",
    ],

    "politics": [
        "https://feeds.bbci.co.uk/news/politics/rss.xml",
        "https://feeds.skynews.com/feeds/rss/politics.xml",
    ],

    "war": [
        "https://www.aljazeera.com/xml/rss/all.xml", # Focuses on conflict
        "https://rss.dw.com/rdf/rss-en-world",
    ],

    "space": [
        "https://www.nasa.gov/rss/dyn/breaking_news.rss",
        "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
    ],
}


# ── HTTP session with automatic retry ────────────────────────────────────────
def _make_session() -> requests.Session:
    """
    Return a requests Session with:
      - 3 retries on connection/read errors (exponential back-off)
      - Browser-like User-Agent so BBC does not throttle Python clients
    """
    session = requests.Session()

    retry = Retry(
        total=3,
        backoff_factor=1.0,           # waits 1s, 2s, 4s between retries
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://",  adapter)

    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept":          "application/rss+xml, application/xml, text/xml, */*",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control":   "no-cache",
    })
    return session


def _fetch_feed_bytes(url: str, timeout: int = 12) -> bytes | None:
    """
    Download RSS bytes via requests.
    Returns raw bytes on success, None on any failure.

    Using requests instead of feedparser's built-in HTTP means:
      - We control the timeout (feedparser has none by default)
      - Retries happen automatically via HTTPAdapter
      - IncompleteRead from http.client is caught and handled
      - We get a clear error message instead of a silent hang
    """
    session = _make_session()
    try:
        print(f"[NewsFetcher] GET {url}  (timeout={timeout}s)")
        resp = session.get(url, timeout=timeout)
        resp.raise_for_status()

        content = resp.content
        if len(content) < 100:
            print(f"[NewsFetcher] Response too short ({len(content)} bytes) -- skipping")
            return None

        print(f"[NewsFetcher] Feed fetched OK: {len(content):,} bytes")
        return content

    except requests.exceptions.Timeout:
        print(f"[NewsFetcher] ✗ Timeout after {timeout}s -> {url}")
        return None
    except requests.exceptions.ConnectionError as exc:
        print(f"[NewsFetcher] ✗ Connection error -> {url}: {exc}")
        return None
    except requests.exceptions.HTTPError as exc:
        print(f"[NewsFetcher] ✗ HTTP error -> {url}: {exc}")
        return None
    except Exception as exc:
        # Catches http.client.IncompleteRead and anything else
        print(f"[NewsFetcher] ✗ Unexpected error -> {url}: {type(exc).__name__}: {exc}")
        return None
    finally:
        session.close()


def _parse_entry(entry) -> dict:
    """Extract title, link, summary, and publication timestamp from a feedparser entry."""
    title   = getattr(entry, "title",   "No title")
    link    = getattr(entry, "link",    "")
    summary = getattr(entry, "summary", "")

    # Strip HTML tags from summary
    summary = re.sub(r"<[^>]+>", " ", summary)
    summary = re.sub(r"\s+", " ", summary).strip()

    # Fall back to title when summary is missing
    if not summary:
        summary = title

    # Extract publication date as epoch timestamp
    import calendar
    import time
    pub_timestamp = time.time()
    parsed = getattr(entry, "published_parsed", getattr(entry, "updated_parsed", None))
    if parsed:
        try:
            pub_timestamp = float(calendar.timegm(parsed))
        except Exception:
            pass

    return {
        "title": title,
        "link": link,
        "summary": summary,
        "pub_timestamp": pub_timestamp
    }


def _get_timezone_boost(title: str) -> int:
    """Calculate a soft score boost based on the running time timezone and keywords."""
    import datetime
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    title_lower = (title or "").lower()
    
    # 1. Asia peak hours (05:30 UTC to 14:30 UTC / 11:00 AM to 8:00 PM IST)
    if datetime.time(5, 30) <= now_utc.time() <= datetime.time(14, 30):
        asia_keywords = {"india", "modi", "delhi", "mumbai", "bengaluru", "china", "pakistan", "asia"}
        if any(w in title_lower for w in asia_keywords):
            return 4  # Soft boost for Asian relevance
            
    # 2. Western peak hours (Daytime in the West / Outside Asia Peak)
    else:
        west_keywords = {"us", "usa", "uk", "london", "washington", "biden", "trump", "europe", "nato"}
        if any(w in title_lower for w in west_keywords):
            return 4  # Soft boost for Western relevance
            
    return 0


_GOOGLE_TRENDS_CACHE = {"timestamp": 0.0, "keywords": []}


def _fetch_google_trends_keywords() -> list[str]:
    """
    Pillar 4: Query Google Trends Daily RSS (geo=US and geo=IN).
    Cached locally (1-hour TTL) for zero network overhead on repeated calls.
    Returns a list of trending search keyword strings (lowercase).
    """
    global _GOOGLE_TRENDS_CACHE
    import time
    import pathlib
    import json
    import xml.etree.ElementTree as ET

    now = time.time()
    cache_ttl = 3600.0  # 1 hour

    # 1. In-memory cache check
    if _GOOGLE_TRENDS_CACHE["keywords"] and (now - _GOOGLE_TRENDS_CACHE["timestamp"] < cache_ttl):
        return _GOOGLE_TRENDS_CACHE["keywords"]

    # 2. Local disk cache check
    cache_file = pathlib.Path(__file__).parent / "output" / "google_trends_cache.json"
    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            if (now - data.get("timestamp", 0) < cache_ttl) and data.get("keywords"):
                _GOOGLE_TRENDS_CACHE["timestamp"] = data["timestamp"]
                _GOOGLE_TRENDS_CACHE["keywords"] = data["keywords"]
                return _GOOGLE_TRENDS_CACHE["keywords"]
        except Exception:
            pass

    trends_urls = [
        "https://trends.google.com/trending/rss?geo=US",
        "https://trends.google.com/trending/rss?geo=IN",
    ]
    extracted = []
    for t_url in trends_urls:
        try:
            resp = requests.get(t_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                for item in root.findall(".//item"):
                    t_elem = item.find("title")
                    if t_elem is not None and t_elem.text:
                        kw = t_elem.text.strip().lower()
                        if kw and kw not in extracted:
                            extracted.append(kw)
        except Exception:
            pass

    if extracted:
        _GOOGLE_TRENDS_CACHE["timestamp"] = now
        _GOOGLE_TRENDS_CACHE["keywords"] = extracted
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps({"timestamp": now, "keywords": extracted}, indent=2), encoding="utf-8")
        except Exception:
            pass
        return extracted

    return _GOOGLE_TRENDS_CACHE.get("keywords", [])


def score_viral_potential(title: str, category: str = "general") -> int:
    """
    Score a headline on a calibrated 0-100 Viral Predictor scale:
      - Superpower Entities (up to 35 pts): US, Russia, China, Israel, Gaza, Ukraine, Iran, Trump, Putin, Modi, etc.
      - Emotional Urgency & Crisis (up to 30 pts): Airstrike, nuclear, war, strike, emergency, collapse, killed, etc.
      - Historical Category / Context Performance from video_analytics (up to 20 pts).
      - Pillar 4: Real-Time Search Trend / Velocity Boost (up to 25 pts).
    """
    title_lower = (title or "").lower()
    if not title_lower:
        return 0

    score = 0

    # 1. Superpower Entities (up to 35 pts)
    tier1_entities = {"trump": 18, "putin": 16, "biden": 14, "modi": 14, "xi jinping": 14, "netanyahu": 14, "zelensky": 14}
    tier2_nations = {"russia": 14, "ukraine": 14, "israel": 15, "gaza": 16, "palestine": 16, "iran": 14, "china": 12, "taiwan": 12, "us": 10, "usa": 10, "america": 10, "india": 10}
    
    entity_pts = 0
    for entity, pts in tier1_entities.items():
        if entity in title_lower:
            entity_pts += pts
            break
    import re as _v_re
    for nation, pts in tier2_nations.items():
        if _v_re.search(rf"\b{nation}\b", title_lower):
            entity_pts += pts
            if entity_pts >= 35:
                break
    score += min(entity_pts, 35)

    # 2. Emotional Urgency & High-Stakes Disruption (up to 30 pts)
    urgency_tokens = {
        "airstrike": 18, "air strike": 18, "missile": 16, "nuclear": 18, "bombs": 15, "bombing": 15,
        "invasion": 16, "war": 14, "strikes": 14, "strike": 12, "attack": 12, "troops": 10, "clash": 10,
        "killed": 12, "deadly": 12, "dead": 10, "massacre": 15, "assassination": 16, "hostage": 12,
        "collapse": 12, "emergency": 12, "catastrophe": 14, "disaster": 10, "earthquake": 12,
        "sanctions": 10, "crisis": 10, "coup": 14, "warns": 8, "threatens": 10, "ultimatum": 12,
        "breaking": 10, "urgent": 10, "alert": 10, "live": 8, "tanks": 12, "tank": 12,
        "military": 10, "ceasefire": 12, "standoff": 12, "escalate": 12, "escalates": 12,
        "offensive": 14, "drone": 12, "drones": 12, "frontline": 12, "conflict": 12,
        "turning point": 10, "critical": 8, "deploy": 8, "deployed": 10
    }
    urgency_pts = 0
    for token, pts in urgency_tokens.items():
        if token in title_lower:
            urgency_pts += pts
            if urgency_pts >= 30:
                break
    score += min(urgency_pts, 30)

    # 3. Historical Category & Context Win Rates (up to 20 pts)
    # Analytics data shows 'tense', 'war', and 'politics' produce 430-820 views
    cat_lower = (category or "general").lower()
    if any(w in title_lower for w in ["war", "strike", "attack", "conflict", "killed", "missile", "drone", "gaza", "military", "tanks", "ceasefire", "standoff", "escalat"]):
        score += 20  # Matches 'tense' / 'war' top-performing context
    elif any(w in title_lower for w in ["trump", "modi", "election", "brics", "summit", "sanctions"]):
        score += 16  # Matches 'politics'
    elif cat_lower in ["world", "general"]:
        score += 12
    else:
        score += 8

    # 4. Search Trend & Timezone Velocity Boost (Pillar 4: +15 to +25 pts)
    trend_boost = 0
    try:
        trending_kws = _fetch_google_trends_keywords()
        if trending_kws:
            for kw in trending_kws:
                if not kw or len(kw) < 3:
                    continue
                # Exact phrase match
                if kw in title_lower:
                    trend_boost = 25
                    break
                # Significant keyword token overlap
                kw_tokens = [w for w in kw.split() if len(w) >= 4]
                if len(kw_tokens) >= 2 and all(w in title_lower for w in kw_tokens):
                    trend_boost = 22
                    break
                elif len(kw_tokens) == 1 and kw_tokens[0] in title_lower:
                    trend_boost = 18
                    break
    except Exception:
        trend_boost = 0

    tz_boost = min(15, _get_timezone_boost(title) * 2)
    score += max(trend_boost, tz_boost)

    return min(score, 100)


def _score_headline(title: str) -> int:
    """Backward-compatible alias for viral prediction scoring."""
    return score_viral_potential(title, "general")


def _fetch_og_image_url(article_url: str) -> str:
    """
    Visit the article page and extract the og:image meta tag URL.
    Returns the image URL string, or "" on any failure.
    Never raises -- pipeline must not crash here.
    """
    if not article_url or not article_url.startswith("http"):
        return ""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return ""   # bs4 not installed -- skip silently

    try:
        r = requests.get(
            article_url,
            timeout=8,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            },
        )
        if r.status_code != 200:
            return ""
        soup = BeautifulSoup(r.text, "html.parser")
        tag  = (
            soup.find("meta", property="og:image")
            or soup.find("meta", attrs={"name": "twitter:image"})
        )
        if tag and tag.get("content"):
            url = tag["content"].strip()
            if url.startswith("//"):
                url = "https:" + url
            print(f"[NewsFetcher] og:image: {url[:80]}")
            return url
    except Exception as exc:
        print(f"[NewsFetcher] og:image fetch failed: {exc}")
    return ""


def _scrape_article_body(url: str, max_chars: int = 3000) -> str:
    """
    Scrape the full text body from a news article URL.
    Returns the article text (up to max_chars characters) or empty string on failure.

    Extraction strategy (ordered by quality):
      1. <article> tag content -- most news sites use semantic HTML
      2. Largest <div> with article-like class names
      3. All <p> tags inside main content area
      4. All <p> tags on page (fallback)

    Filters:
      - Skip navigation, footer, sidebar, ad paragraphs
      - Skip paragraphs under 40 characters (headlines, labels, bylines)
      - Stop at "Related" / "Also Read" / "Advertisement" sections
    """
    if not url or not url.startswith("http"):
        return ""

    try:
        from bs4 import BeautifulSoup
        import requests as _req
    except ImportError:
        return ""

    try:
        r = _req.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=12,
        )
        if r.status_code != 200:
            return ""

        soup = BeautifulSoup(r.text, "html.parser")

        # Remove noise: scripts, styles, nav, ads, footers, sidebars
        for _tag in soup.find_all(["script", "style", "nav", "footer",
                                    "aside", "header", "form", "button",
                                    "noscript", "iframe", "figure"]):
            _tag.decompose()

        # Strategy 1: semantic <article> tag
        _article_tag = soup.find("article")
        if _article_tag:
            _paragraphs = _article_tag.find_all("p")
        else:
            # Strategy 2: divs with article-like class names
            _ARTICLE_CLASSES = [
                # Generic
                "article-body", "story-body", "article__body",
                "article-content", "story-content", "post-content",
                "entry-content", "content-body", "article-text",
                "newstext", "news-body", "storyBody", "body-content",
                "articleBody", "article_content",
                # PHASE 19: Site-specific classes
                "sp-cn",              # NDTV article content
                "story__content",     # NDTV
                "article__body",      # Times of India
                "artText",            # Times of India
                "Normal",             # Times of India (paragraph class)
                "_s30J",              # Al Jazeera (may vary)
                "wysiwyg",            # DW
                "longText",           # Sky News
                "article-paragraph",  # BBC
                "ssrcss",             # BBC (dynamic class prefix)
            ]
            _content_div = None
            for _cls in _ARTICLE_CLASSES:
                _content_div = (
                    soup.find("div", class_=lambda c: c and _cls in " ".join(c))
                    or soup.find("div", id=lambda i: i and _cls in i)
                )
                if _content_div:
                    break

            if _content_div:
                _paragraphs = _content_div.find_all("p")
            else:
                # Strategy 2b: section or div using structured article body metadata
                _article_body = (
                    soup.find("div", attrs={"itemprop": "articleBody"})
                    or soup.find("section", attrs={"itemprop": "articleBody"})
                    or soup.find("div", class_=lambda c: c and "article-body" in c)
                    or soup.find("div", class_=lambda c: c and "story-body" in c)
                    or soup.find("div", class_=lambda c: c and "story-content" in c)
                    or soup.find("div", class_=lambda c: c and "content-body" in c)
                )
                if _article_body:
                    _paragraphs = _article_body.find_all("p")
                else:
                    # Strategy 2.5: JSON-LD structured data (many news sites use this)
                    import json as _json_ld
                    _ld_scripts = soup.find_all("script", type="application/ld+json")
                    for _ld in _ld_scripts:
                        try:
                            _ld_data = _json_ld.loads(_ld.string or "")
                            # Handle both dict and list format
                            if isinstance(_ld_data, list):
                                _ld_data = _ld_data[0] if _ld_data else {}
                            _article_body = _ld_data.get("articleBody", "")
                            if _article_body and len(_article_body) > 200:
                                # Found article body in structured data
                                _paragraphs = [type('p', (), {'get_text': lambda self, **kw: _article_body})()]
                                print(f"[ArticleScraper] Found article body in JSON-LD "
                                      f"({len(_article_body)} chars)")
                                break
                        except Exception:
                            continue
                    else:
                        # Strategy 3: all <p> tags on the page (last resort)
                        _paragraphs = soup.find_all("p")

        # Filter and collect text
        _STOP_PHRASES = [
            "related news", "also read", "read also", "advertisement",
            "follow us on", "subscribe to", "get the latest",
            "watch live", "live updates", "breaking news",
            "click here", "read more", "continue reading",
            "sponsored", "partner content",
        ]

        lines = []
        total_chars = 0

        for p in _paragraphs:
            text = p.get_text(separator=" ").strip()

            # Skip short fragments (bylines, labels, captions)
            if len(text) < 40:
                continue

            # Stop at "related/also read" sections
            if any(stop in text.lower() for stop in _STOP_PHRASES):
                break

            lines.append(text)
            total_chars += len(text)

            if total_chars >= max_chars:
                break

        result = " ".join(lines).strip()
        if result:
            print(f"[ArticleScraper] Extracted {len(result)} chars from {url[:60]}")
        return result[:max_chars]

    except Exception as exc:
        print(f"[ArticleScraper] Failed for {url[:60]}: {exc}")
        return ""


def _ddg_article_search(title: str, article_url: str, max_chars: int = 2000) -> str:
    """
    When BeautifulSoup fails (JS-rendered pages like NDTV/TOI), use DuckDuckGo
    to find related article content via text search.

    Strategy:
    1. Search DuckDuckGo for the article title
    2. Try to fetch the TOP result that matches the same domain or topic
    3. Extract text from that page

    This is a fallback -- quality may be lower than direct scraping.
    Returns extracted text or "" on failure.
    """
    if not title:
        return ""

    try:
        from ddgs import DDGS
    except ImportError:
        print("[ArticleScraper] ddgs not installed -- cannot use DuckDuckGo fallback")
        return ""

    try:
        # Clean title for search (remove site name suffixes like "| NDTV")
        import re as _re
        _clean_title = _re.sub(r'\s*[\|–—]\s*\w+[\w\s]*$', '', title).strip()
        _clean_title = _clean_title[:120]  # cap query length

        # Build search query: title + extract key nouns for specificity
        _query = f"{_clean_title} news"

        print(f"[ArticleScraper] DuckDuckGo search: '{_query[:80]}'")

        _results = []
        with DDGS() as ddgs:
            for r in ddgs.text(_query, max_results=5):
                _results.append(r)

        # Extract text snippets from results and combine
        _combined = []
        _total = 0
        for r in _results:
            _snippet = r.get("body", "").strip()
            if _snippet and len(_snippet) > 50:
                _combined.append(_snippet)
                _total += len(_snippet)
                if _total >= max_chars:
                    break

        result_text = " ".join(_combined)[:max_chars]

        # PHASE 20: Strip common web metadata artifacts from DuckDuckGo snippets
        import re as _ddg_re

        # Remove timestamps ("Published at 22:56 BST 20 April", "22:56 IST", etc.)
        result_text = _ddg_re.sub(
            r'\b(?:published|updated|modified)\s+(?:at\s+)?\d{1,2}:\d{2}\s*[A-Z]{2,4}[^.]*\.',
            '', result_text, flags=_ddg_re.IGNORECASE
        )
        # Remove standalone timestamps ("22:56 BST 20 April")
        result_text = _ddg_re.sub(
            r'\b\d{1,2}:\d{2}\s+[A-Z]{2,4}\s+\d{1,2}\s+\w+', '', result_text
        )
        # Remove "loomspublished" type merged words (word + "published")
        result_text = _ddg_re.sub(r'(\w+)published\b', r'\1. ', result_text)
        result_text = _ddg_re.sub(r'(\w+)updated\b', r'\1. ', result_text)
        # Remove "Live Updates:" type navigation labels
        result_text = _ddg_re.sub(
            r'\b(?:Live Updates?|Breaking News|Latest|Watch Live|'
            r'Read More|Follow Live|Get Live|News Live)[:\s]+',
            '', result_text, flags=_ddg_re.IGNORECASE
        )
        # Clean up double spaces and punctuation artifacts
        result_text = _ddg_re.sub(r'\s{2,}', ' ', result_text).strip()

        return result_text[:max_chars]

    except Exception as exc:
        print(f"[ArticleScraper] DuckDuckGo fallback failed: {exc}")
        return ""


def _cross_verify_article(article: dict, max_sources: int = 3) -> dict:
    """
    Cross-check key facts from the main article against other sources.
    Adds verification metadata without modifying article text.
    """
    try:
        from ddgs import DDGS
        import re as _cv_re
    except ImportError:
        article["verification_score"] = 50
        return article

    headline = article.get("title", "")
    main_text = article.get("full_article_text", "")
    if not headline or not main_text:
        article["verification_score"] = 0
        return article

    _facts = set()
    for _num in _cv_re.findall(r'\b\d[\d,]*(?:\.\d+)?(?:\s*%|km|miles?)?\b', main_text):
        if len(_num) >= 2:
            _facts.add(_num.lower())

    _proper_nouns = _cv_re.findall(r'\b[A-Z][a-z]{3,}(?:\s+[A-Z][a-z]{3,})?\b', main_text)
    _SKIP_PROPER = {"According", "However", "Meanwhile", "Despite", "Breaking"}
    for _pn in _proper_nouns[:15]:
        if _pn not in _SKIP_PROPER:
            _facts.add(_pn.lower())

    _verify_query = _cv_re.sub(r'[^\w\s]', '', headline)[:100]
    _confirmed_facts = set()
    _cross_sources = []

    try:
        with DDGS() as ddgs:
            _search_results = list(ddgs.text(_verify_query + " news", max_results=6))
    except Exception as _ddg_exc:
        print(f"[VERIFY] DuckDuckGo search failed: {_ddg_exc}")
        article["verification_score"] = 40
        return article

    _main_source = article.get("link", "").split("/")[2] if article.get("link") else ""
    for _result in _search_results[:5]:
        _result_url = _result.get("href", "")
        _result_body = (_result.get("body", "") or "").lower()
        _result_title = (_result.get("title", "") or "").lower()
        _result_text = _result_title + " " + _result_body

        if _main_source and _main_source in _result_url:
            continue

        _hits = sum(1 for fact in _facts if fact in _result_text)
        if _hits >= 3:
            _source_name = _result_url.split("/")[2] if "/" in _result_url else _result_url
            _cross_sources.append(_source_name)
            for fact in _facts:
                if fact in _result_text:
                    _confirmed_facts.add(fact)
            if len(_cross_sources) >= max_sources:
                break

    if not _facts:
        _score = 50
    else:
        _fact_confidence = len(_confirmed_facts) / max(len(_facts), 1)
        _source_confidence = min(len(_cross_sources) / 2, 1.0)
        _score = int((_fact_confidence * 0.6 + _source_confidence * 0.4) * 100)

    _unverified = _facts - _confirmed_facts
    article["verified_facts"] = list(_confirmed_facts)[:10]
    article["unverified_facts"] = list(_unverified)[:10]
    article["verification_score"] = _score
    article["cross_sources"] = _cross_sources[:max_sources]

    print(f"[VERIFY] Score={_score}/100 | "
          f"Confirmed={len(_confirmed_facts)}/{len(_facts)} facts | "
          f"Cross-sources: {', '.join(_cross_sources[:3]) or 'none found'}")
    if _score < 30:
        print(f"[VERIFY] WARNING: Low confidence ({_score}/100) - "
              f"unverified facts: {list(_unverified)[:5]}")

    return article


def get_dynamic_lookback_hours(channel: str | None, category: str | None = None) -> float:
    """Calculate elapsed hours since the last successful run ended, plus a 1-hour buffer."""
    import sqlite3
    import time
    from pathlib import Path
    
    db_path = Path(__file__).resolve().parent / "db.sqlite"
    if not db_path.exists():
        return 18.0  # default fallback if DB does not exist

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Check if runs table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='runs'")
        if not cursor.fetchone():
            conn.close()
            return 18.0

        row = None
        if channel:
            if category:
                cursor.execute("""
                    SELECT finished_at FROM runs 
                    WHERE channel_key=? AND category=? AND status='success' AND stage='complete'
                    ORDER BY finished_at DESC LIMIT 1
                """, (channel, category))
                row = cursor.fetchone()
            if not row or not row["finished_at"]:
                cursor.execute("""
                    SELECT finished_at FROM runs 
                    WHERE channel_key=? AND status='success' AND stage='complete'
                    ORDER BY finished_at DESC LIMIT 1
                """, (channel,))
                row = cursor.fetchone()
        else:
            if category:
                cursor.execute("""
                    SELECT finished_at FROM runs 
                    WHERE category=? AND status='success' AND stage='complete'
                    ORDER BY finished_at DESC LIMIT 1
                """, (category,))
                row = cursor.fetchone()
            if not row or not row["finished_at"]:
                cursor.execute("""
                    SELECT finished_at FROM runs 
                    WHERE status='success' AND stage='complete'
                    ORDER BY finished_at DESC LIMIT 1
                """)
                row = cursor.fetchone()
        conn.close()
        
        if row and row["finished_at"]:
            last_finished = row["finished_at"]
            now_epoch = time.time()
            elapsed_seconds = now_epoch - last_finished
            elapsed_hours = elapsed_seconds / 3600.0
            # Return elapsed hours plus 1 hour safety buffer, capped at 24 hours
            return min(max(4.0, elapsed_hours + 1.0), 24.0)
    except Exception as e:
        print(f"[NewsFetcher] Failed to query dynamic lookback hours: {e}")
        
    return 18.0  # default fallback


def fetch_latest_article(feed_url: str = RSS_FEED_URL, category: str = "general", channel: str = None) -> dict:
    """
    Scrape all feeds in the selected category pool simultaneously, score every
    headline using _score_headline(), and return the single highest-scoring article.
    Falls back to the primary feed if all others fail.

    Args:
        feed_url: primary RSS URL (used as first candidate in every category)
        category: one of "general", "sports", "entertainment", "business", "technology"
        channel: optional channel key to fetch feeds dynamically from the database
    """
    import concurrent.futures
    import time

    lookback_hours = get_dynamic_lookback_hours(channel, category)
    print(f"[NewsFetcher] Dynamic lookback window set to: {lookback_hours:.1f} hours")
    lookback_seconds = lookback_hours * 3600.0

    def _fetch_single(url):
        raw = _fetch_feed_bytes(url, timeout=10)
        if not raw:
            return []
        try:
            d = feedparser.parse(raw)
        except Exception:
            return []
        results = []
        for entry in d.entries[:15]:   # top 15 per feed
            article = _parse_entry(entry)
            article["_feed"]  = url
            results.append(article)
        return results

    all_raw_articles = []
    
    # Query channel-specific feeds from the database if channel is provided
    feeds = []
    if channel:
        try:
            from db_manager import get_db_connection
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT url FROM feeds WHERE channel_key=? AND category=? AND health='healthy' ORDER BY priority_rank ASC",
                (channel, category)
            )
            rows = cursor.fetchall()
            feeds = [row["url"] for row in rows]
            conn.close()
            if feeds:
                print(f"[NewsFetcher] Loaded {len(feeds)} feeds from DB for channel '{channel}' and category '{category}'")
        except Exception as e:
            print(f"[NewsFetcher] Error fetching feeds from DB: {e}")

    if not feeds:
        _cat_feeds = _CATEGORY_FEEDS.get(category, _ALL_FEEDS)
        feeds = list(dict.fromkeys([feed_url] + _cat_feeds))

    print(f"[NewsFetcher] Category: '{category}' -- scoring from {len(feeds)} feeds...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(_fetch_single, url): url for url in feeds}
        done, _ = concurrent.futures.wait(futures.keys(), timeout=12, return_when=concurrent.futures.ALL_COMPLETED)
        for future in done:
            try:
                all_raw_articles.extend(future.result())
            except Exception:
                pass

    if not all_raw_articles:
        raise RuntimeError(
            "[NewsFetcher] All feeds failed. Check internet connection."
        )

    # Progressive age filtering fallback
    now = time.time()
    all_articles = []

    # Step 1: Dynamic lookback window
    print(f"[NewsFetcher] Filtering articles with dynamic lookback of {lookback_hours:.1f} hours...")
    for art in all_raw_articles:
        age_seconds = now - art["pub_timestamp"]
        if age_seconds <= lookback_seconds:
            art["_score"] = score_viral_potential(art["title"], category)
            all_articles.append(art)

    # Step 2: Fallback to 48.0 hours
    if not all_articles:
        print(f"[NewsFetcher] No articles found within {lookback_hours:.1f} hours. Relaxing lookback to 48.0 hours...")
        for art in all_raw_articles:
            age_seconds = now - art["pub_timestamp"]
            if age_seconds <= 48.0 * 3600.0:
                art["_score"] = score_viral_potential(art["title"], category)
                all_articles.append(art)

    # Step 3: Fallback to 168.0 hours (7 days)
    if not all_articles:
        print(f"[NewsFetcher] No articles found within 48.0 hours. Relaxing lookback to 168.0 hours (7 days)...")
        for art in all_raw_articles:
            age_seconds = now - art["pub_timestamp"]
            if age_seconds <= 168.0 * 3600.0:
                art["_score"] = score_viral_potential(art["title"], category)
                all_articles.append(art)

    # Step 4: Fallback to all parsed articles
    if not all_articles:
        print(f"[NewsFetcher] No articles found within 7 days. Using all available parsed articles regardless of age...")
        for art in all_raw_articles:
            art["_score"] = score_viral_potential(art["title"], category)
            all_articles.append(art)

    # Sort by score descending
    all_articles.sort(key=lambda a: a["_score"], reverse=True)
    best = all_articles[0]

    # Dynamic Milestone Pace Gatekeeper (Pillar 1)
    try:
        from db_manager import get_milestone_pace_status
        _pace_info = get_milestone_pace_status()
        _viral_gate_threshold = _pace_info.get("adaptive_viral_threshold", 70)
        print(f"[ViralPredictor] Milestone status: '{_pace_info.get('pace_status')}' | Gatekeeper Threshold: {_viral_gate_threshold}/100")
    except Exception:
        _viral_gate_threshold = 70

    print(f"[NewsFetcher] {len(all_articles)} headlines scored across all feeds (Top score: {best['_score']}/100)")

    # Pillar 1 Gatekeeper: Filter candidates meeting threshold
    gatekeeper_candidates = [a for a in all_articles if a.get("_score", 0) >= _viral_gate_threshold]
    if gatekeeper_candidates:
        print(f"[ViralGatekeeper] {len(gatekeeper_candidates)} of {len(all_articles)} candidates passed threshold (>= {_viral_gate_threshold}/100).")
        candidates_to_eval = gatekeeper_candidates
    else:
        print(f"[ViralGatekeeper] All {len(all_articles)} candidates scored below threshold ({_viral_gate_threshold}). "
              f"Safely falling back to highest available candidate (top score={best.get('_score', 0)}/100) to ensure production never halts.")
        candidates_to_eval = all_articles

    # Topic memory: skip recently used headlines.
    # Stores the last 10 winning headlines to prevent repeat videos.
    # Memory file: output/used_topics.json (persists across runs).
    import json as _json
    import pathlib as _pathlib

    _memory_file = _pathlib.Path(__file__).parent / "output" / "used_topics.json"
    _memory_file.parent.mkdir(exist_ok=True)

    _used_topics = []
    if _memory_file.exists():
        try:
            _used_topics = _json.loads(_memory_file.read_text(encoding="utf-8"))
        except Exception:
            _used_topics = []

    def _title_fingerprint(title: str) -> str:
        """Short normalized fingerprint for deduplication."""
        import re as _re
        _t = _re.sub(r"[^a-zA-Z0-9]", "", title.lower())
        return _t[:80]   # PHASE 22: extended from 60 -> 80 for better coverage

    def _title_keyset(title: str) -> set:
        """Extract top-N significant words from a title for overlap detection."""
        import re as _re
        _TITLE_STOPS = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at",
            "to", "for", "of", "with", "from", "by", "as", "is", "are",
            "was", "were", "be", "been", "has", "have", "had", "will",
            "says", "said", "over", "after", "amid", "kills",
        }
        words = _re.findall(r"[a-z]{4,}", title.lower())
        return {w for w in words if w not in _TITLE_STOPS}

    _used_fps = set(_used_topics)
    # PHASE 22: Also store keysets of recently used headlines for overlap check
    _used_keysets = [_title_keyset(fp) for fp in _used_topics if len(fp) >= 10]

    selected_candidate = None
    for _candidate in candidates_to_eval:
        _fp = _title_fingerprint(_candidate["title"])
        if _fp in _used_fps:
            continue
        # PHASE 22: Skip if 3+ keywords overlap with ANY recently-used headline
        _cand_keys = _title_keyset(_candidate["title"])
        _overlap_count = max(
            (len(_cand_keys & _used_ks) for _used_ks in _used_keysets),
            default=0
        )
        if _overlap_count >= 3:
            print(f"[DEDUP] Skipping '{_candidate['title'][:60]}' "
                  f"-- {_overlap_count} keyword overlap with recent headline")
            continue
        selected_candidate = _candidate
        best = _candidate
        print(f"[NewsFetcher] Selected (score={best.get('_score', '?')}): {best['title']}")
        break

    if not selected_candidate:
        print("[NewsFetcher] All candidate headlines used or deduped - falling back to highest available candidate")
        _used_topics = []
        _used_fps = set()
        best = candidates_to_eval[0] if candidates_to_eval else all_articles[0]
        print(f"[NewsFetcher] Selected (score={best.get('_score', '?')}): {best['title']}")

    print(f"[NewsFetcher] Source feed: {best['_feed']}")

    best.pop("_score", None)
    best.pop("_feed", None)

    _fp_winner = _title_fingerprint(best["title"])
    if _fp_winner not in _used_fps:
        _used_topics.append(_fp_winner)
    _used_topics = _used_topics[-10:]
    try:
        _memory_file.write_text(_json.dumps(_used_topics, indent=2), encoding="utf-8")
    except Exception as _me:
        print(f"[NewsFetcher] Could not save topic memory: {_me}")

    # Fetch editorial press photo from the article page.
    best["og_image_url"] = _fetch_og_image_url(best.get("link", ""))

    # PHASE 14: Scrape full article body for script generation
    _article_url = best.get("link", "")
    if _article_url:
        _full_text = _scrape_article_body(_article_url, max_chars=3000)

        # PHASE 19: If scrape returned too little, try DuckDuckGo web search
        # NDTV, TOI, and some Indian news sites use JS rendering that blocks bs4
        if not _full_text or len(_full_text) < 200:
            print(f"[ArticleScraper] Short result ({len(_full_text or '')} chars) -- "
                  f"trying DuckDuckGo search fallback.")
            _full_text = _ddg_article_search(
                best.get("title", ""),
                best.get("link", ""),
                max_chars=2000
            )
            if _full_text:
                print(f"[ArticleScraper] DuckDuckGo fallback: {len(_full_text)} chars")

        if _full_text and len(_full_text) > 100:
            _rss_desc = best.get("description", "") or best.get("summary", "") or ""
            # PHASE 20: Do NOT include structural labels in the article text.
            # "TITLE:", "SUMMARY:", "FULL ARTICLE:" end up in extractive fallback
            # sentences and are literally spoken by the narrator.
            # Instead: put title and summary as PLAIN TEXT (no labels),
            # and separate them from the body with a newline only.
            _rss_desc_clean = (_rss_desc or "").strip()
            _title_clean = (best.get("title", "") or "").strip()
            # Combine: title sentence + RSS summary + full article body
            # No labels, all plain prose — safe for extractive NLP
            _parts = []
            if _title_clean:
                _parts.append(_title_clean + ".")
            if _rss_desc_clean and _rss_desc_clean != _title_clean:
                _parts.append(_rss_desc_clean)
            if _full_text:
                _parts.append(_full_text)
            best["full_article_text"] = " ".join(_parts)
            print(f"[ArticleScraper] Full text ready: {len(_full_text)} chars")
        else:
            # Fallback: combine title + RSS description + related headline context
            _rss_desc = best.get("description", "") or best.get("summary", "") or ""
            _t = (best.get("title", "") or "").strip()
            _d = (best.get("description", "") or best.get("summary", "") or "").strip()
            best["full_article_text"] = f"{_t}. {_d}".strip()
            print(f"[ArticleScraper] WARNING: Only RSS snippet available "
                  f"({len(best['full_article_text'])} chars). Script will be limited.")

    best = _cross_verify_article(best, max_sources=3)
    return best


def check_story_continuity(headline: str, channel_key: str) -> dict | None:
    """
    Check if the new headline matches an active tracked story for this channel.
    Matches if there is at least a 3-keyword overlap (case-insensitive).
    Returns the story row as a dict if matched, otherwise None.
    """
    import sqlite3
    import re
    from pathlib import Path
    
    db_path = Path(__file__).resolve().parent / "db.sqlite"
    if not db_path.exists():
        return None

    def _extract_keywords(text: str) -> set:
        _STOPS = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at",
            "to", "for", "of", "with", "from", "by", "as", "is", "are",
            "was", "were", "be", "been", "has", "have", "had", "will",
            "says", "said", "over", "after", "amid", "new", "reports", "on", "developments"
        }
        words = re.findall(r"[a-zA-Z]{4,}", text.lower())
        return {w for w in words if w not in _STOPS}

    new_keys = _extract_keywords(headline)
    if not new_keys:
        return None

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, story_key, headline, episode_count FROM tracked_stories WHERE channel_key=? AND status='active'",
            (channel_key,)
        )
        rows = cursor.fetchall()
        conn.close()

        for row in rows:
            tracked_headline = row["headline"]
            tracked_keys = _extract_keywords(tracked_headline)
            overlap = new_keys & tracked_keys
            if len(overlap) >= 3:
                return dict(row)
    except Exception as e:
        print(f"[NewsFetcher] Error in check_story_continuity: {e}")

    return None


# ── Smoke test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    art = fetch_latest_article()
    print("\n--- Result ---")
    for k, v in art.items():
        print(f"  {k}: {v[:160]}")
