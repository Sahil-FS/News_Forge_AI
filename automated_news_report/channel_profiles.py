"""Channel profiles for the multi-channel AI news production workflow."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class ChannelProfile:
    key: str
    display_name: str
    audience: str
    language: str
    language_label: str
    default_category: str
    supported_formats: tuple[str, ...]
    source_policy: str
    brand_name: str
    channel_handle: str
    thumbnail_language: str
    primary_color: str
    accent_color: str
    categories: tuple[str, ...]
    feeds: dict[str, tuple[str, ...]] = field(default_factory=dict)
    prompt_rules: tuple[str, ...] = field(default_factory=tuple)
    production_notes: tuple[str, ...] = field(default_factory=tuple)

    def to_public_dict(self) -> dict:
        data = asdict(self)
        data["supported_formats"] = list(self.supported_formats)
        data["categories"] = list(self.categories)
        data["prompt_rules"] = list(self.prompt_rules)
        data["production_notes"] = list(self.production_notes)
        data["feeds"] = {k: list(v) for k, v in self.feeds.items()}
        return data


NEWSCUP_FEEDS = {
    "general": (
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://feeds.bbci.co.uk/news/rss.xml",
        "https://www.aljazeera.com/xml/rss/all.xml",
        "https://rss.dw.com/rdf/rss-en-world",
        "https://feeds.skynews.com/feeds/rss/world.xml",
    ),
    "world": (
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://rss.dw.com/rdf/rss-en-world",
        "https://www.aljazeera.com/xml/rss/all.xml",
        "https://feeds.skynews.com/feeds/rss/world.xml",
    ),
    "politics": (
        "https://feeds.bbci.co.uk/news/politics/rss.xml",
        "https://feeds.skynews.com/feeds/rss/politics.xml",
        "https://rss.dw.com/rdf/rss-en-world",
    ),
    "business": (
        "https://feeds.bbci.co.uk/news/business/rss.xml",
        "https://rss.dw.com/rdf/rss-en-business",
        "https://feeds.skynews.com/feeds/rss/business.xml",
    ),
    "technology": (
        "https://feeds.bbci.co.uk/news/technology/rss.xml",
        "https://rss.dw.com/rdf/rss-en-technology",
        "https://feeds.skynews.com/feeds/rss/technology.xml",
    ),
    "science": (
        "https://www.nasa.gov/rss/dyn/breaking_news.rss",
        "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
    ),
    "environment": (
        "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
        "https://rss.dw.com/rdf/rss-en-environment",
    ),
    "sports": (
        "https://feeds.bbci.co.uk/sport/rss.xml",
        "https://www.espn.com/espn/rss/news",
        "https://rss.dw.com/rdf/rss-en-sport",
    ),
    "crime": (
        "https://feeds.skynews.com/feeds/rss/world.xml",
        "https://feeds.bbci.co.uk/news/world/rss.xml",
    ),
    "war": (
        "https://www.aljazeera.com/xml/rss/all.xml",
        "https://rss.dw.com/rdf/rss-en-world",
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://feeds.skynews.com/feeds/rss/world.xml",
    ),
}


NEWSCUP_INDIA_FEEDS = {
    "general": (
        "https://www.aninews.in/rss/feed/category/national/",
        "https://www.thehindu.com/news/national/feeder/default.rss",
        "https://indianexpress.com/section/india/feed/",
        "https://economictimes.indiatimes.com/rssfeedsdefault.cms",
        "https://www.livemint.com/rss/news",
        "https://feeds.feedburner.com/ndtvnews-top-stories",
        "https://www.indiatoday.in/rss/home",
        "https://www.hindustantimes.com/rss/topnews/rssfeed.xml",
        "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",
        "https://www.news18.com/rss/india.xml",
        "https://theprint.in/feed/",
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://www.aljazeera.com/xml/rss/all.xml",
    ),
    "india": (
        "https://www.aninews.in/rss/feed/category/national/",
        "https://www.thehindu.com/news/national/feeder/default.rss",
        "https://indianexpress.com/section/india/feed/",
        "https://economictimes.indiatimes.com/rssfeedsdefault.cms",
        "https://www.livemint.com/rss/news",
        "https://feeds.feedburner.com/ndtvnews-india-news",
        "https://www.indiatoday.in/rss/home",
        "https://www.hindustantimes.com/rss/topnews/rssfeed.xml",
        "https://timesofindia.indiatimes.com/rssfeeds/-2128936835.cms",
        "https://www.news18.com/rss/india.xml",
        "https://theprint.in/feed/",
    ),
    "politics": (
        "https://www.aninews.in/rss/feed/category/national/",
        "https://www.thehindu.com/news/national/feeder/default.rss",
        "https://indianexpress.com/section/political-pulse/feed/",
        "https://feeds.feedburner.com/ndtvnews-india-news",
        "https://www.indiatoday.in/rss/home",
        "https://timesofindia.indiatimes.com/rssfeeds/-2128936835.cms",
        "https://theprint.in/feed/",
    ),
    "business": (
        "https://www.aninews.in/rss/feed/category/business/",
        "https://economictimes.indiatimes.com/rssfeedsdefault.cms",
        "https://www.livemint.com/rss/news",
        "https://feeds.feedburner.com/ndtvnews-business",
        "https://timesofindia.indiatimes.com/rssfeeds/1898055.cms",
        "https://www.thehindu.com/business/feeder/default.rss",
        "https://theprint.in/feed/",
    ),
    "sports": (
        "https://www.aninews.in/rss/feed/category/sports/",
        "https://timesofindia.indiatimes.com/rssfeeds/4719161.cms",
        "https://feeds.feedburner.com/ndtvsports-latest",
        "https://www.thehindu.com/sport/feeder/default.rss",
        "https://www.indiatoday.in/rss/home",
    ),
    "crime": (
        "https://www.aninews.in/rss/feed/category/national/",
        "https://feeds.feedburner.com/ndtvnews-india-news",
        "https://timesofindia.indiatimes.com/rssfeeds/-2128838597.cms",
        "https://indianexpress.com/section/cities/feed/",
        "https://www.indiatoday.in/rss/home",
    ),
    "technology": (
        "https://www.aninews.in/rss/feed/category/tech/",
        "https://timesofindia.indiatimes.com/rssfeeds/66949542.cms",
        "https://www.thehindu.com/sci-tech/technology/feeder/default.rss",
        "https://economictimes.indiatimes.com/rssfeedsdefault.cms",
    ),
    "environment": (
        "https://www.thehindu.com/sci-tech/energy-and-environment/feeder/default.rss",
        "https://indianexpress.com/section/india/feed/",
        "https://www.livemint.com/rss/news",
    ),
    "state": (
        "https://indianexpress.com/section/cities/feed/",
        "https://www.thehindu.com/news/cities/feeder/default.rss",
        "https://timesofindia.indiatimes.com/rssfeeds/-2128838597.cms",
    ),
    "world-affairs": (
        "https://www.aninews.in/rss/feed/category/world/",
        "https://feeds.feedburner.com/ndtvnews-world-news",
        "https://www.thehindu.com/news/international/feeder/default.rss",
        "https://indianexpress.com/section/world/feed/",
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://www.aljazeera.com/xml/rss/all.xml",
    ),
}


CHANNEL_PROFILES = {
    "newscup": ChannelProfile(
        key="newscup",
        display_name="The_News_Cup",
        audience="International viewers who want clear, fast global news.",
        language="en",
        language_label="English",
        default_category="world",
        supported_formats=("short", "long", "both"),
        source_policy="Use global and international news sources only.",
        brand_name="The_News_Cup",
        channel_handle="The_News_Cup",
        thumbnail_language="English",
        primary_color="#b91c1c",
        accent_color="#0f766e",
        categories=(
            "general", "world", "politics", "sports", "business",
            "technology", "environment", "science", "crime", "war",
        ),
        feeds=NEWSCUP_FEEDS,
        prompt_rules=(
            "Write in English for an international audience.",
            "Avoid local assumptions and explain country-specific context briefly.",
            "Use a professional broadcast tone with clear source attribution.",
        ),
        production_notes=(
            "Best for global news, geopolitics, business, science, and international affairs.",
            "Shorts should prioritize the newest visual hook; long videos should add context and timeline.",
        ),
    ),
    "newscup_india": ChannelProfile(
        key="newscup_india",
        display_name="The_News_Cup_India",
        audience="Indian viewers who want national news in Hindi.",
        language="hi",
        language_label="Hindi",
        default_category="india",
        supported_formats=("short", "long", "both"),
        source_policy="Use Indian news sources only.",
        brand_name="The_News_Cup_India",
        channel_handle="The_News_Cup_India",
        thumbnail_language="English",
        primary_color="#0f766e",
        accent_color="#b91c1c",
        categories=(
            "general", "india", "politics", "sports", "crime",
            "business", "environment", "technology", "state",
            "world-affairs",
        ),
        feeds=NEWSCUP_INDIA_FEEDS,
        prompt_rules=(
            "Write the script and voiceover text in Hindi using Devanagari.",
            "Keep thumbnails and upload titles in English unless changed in settings.",
            "Explain policy, state, and national impact for Indian viewers.",
        ),
        production_notes=(
            "Install a Hindi TTS model before production voice generation.",
            "Use Shorts for breaking updates and long videos for policy, crime, politics, and explainers.",
        ),
    ),
}


def load_custom_feeds() -> dict[str, dict[str, list[str]]]:
    """Load customized feeds from the SQLite database feeds table."""
    import sqlite3
    from pathlib import Path
    db_path = Path(__file__).resolve().parent / "db.sqlite"
    if not db_path.exists():
        return {}
    
    feeds_map = {}
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT channel_key, category, url FROM feeds ORDER BY priority_rank")
        rows = cursor.fetchall()
        for row in rows:
            ck = row["channel_key"]
            cat = row["category"]
            url = row["url"]
            if ck not in feeds_map:
                feeds_map[ck] = {}
            if cat not in feeds_map[ck]:
                feeds_map[ck][cat] = []
            feeds_map[ck][cat].append(url)
        conn.close()
    except Exception as e:
        print(f"[Profiles] Failed to load feeds from DB: {e}")
    return feeds_map


def get_channel_profile(channel_key: str | None) -> ChannelProfile:
    if not channel_key:
        return CHANNEL_PROFILES["newscup"]
    normalized = channel_key.strip().lower().replace("-", "_")
    if normalized in {"news_tub_india", "newstubindia", "newstub_india", "newstub-india"}:
        normalized = "newscup_india"
    if normalized in {"news_cup_india", "newscupindia", "newscup_india", "newscup-india"}:
        normalized = "newscup_india"
    
    profile = CHANNEL_PROFILES.get(normalized, CHANNEL_PROFILES["newscup"])
    
    # Load custom overrides from SQLite
    custom_feeds = load_custom_feeds()
    if profile.key in custom_feeds:
        from dataclasses import replace
        # Convert list back to tuple for compatibility with frozen dataclass
        feeds_tuple = {k: tuple(v) for k, v in custom_feeds[profile.key].items()}
        profile = replace(profile, feeds=feeds_tuple)
        
    return profile


def get_channel_feeds(channel_key: str | None, category: str | None) -> tuple[str, ...]:
    profile = get_channel_profile(channel_key)
    category_key = (category or profile.default_category).strip().lower()
    return profile.feeds.get(category_key) or profile.feeds.get("general") or ()


def public_channel_profiles() -> list[dict]:
    return [profile.to_public_dict() for profile in CHANNEL_PROFILES.values()]
