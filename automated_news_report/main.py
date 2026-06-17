#!/usr/bin/env python3
"""
main.py -- AI News-to-Video Generator
Orchestrates: News -> Script -> Scenes -> Images + Audio -> Video

FIX: Thumbnail call now passes scenes list so anchor image is never used
     for short-form thumbnails.
FIX: Hook sentence quality guard added — incomplete hooks are caught
     before audio generation.
FIX: Pipeline properly exits after long-form video is written.
FIX: format_mode passed to generate_thumbnails so landscape knows
     when to include anchor.
"""

import sys
import os
import re

# Force UTF-8 stdout on Windows
if sys.platform == "win32":
    try:
        import io
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer,
            encoding="utf-8",
            errors="replace",
            line_buffering=True
        )
        sys.stderr = io.TextIOWrapper(
            sys.stderr.buffer,
            encoding="utf-8",
            errors="replace",
            line_buffering=True
        )
    except Exception:
        pass

import shutil
import uuid
import warnings
import argparse
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

from news_fetcher     import fetch_latest_article
from script_generator import summarise, generate_compilation_script
from scene_planner    import plan_scenes
from image_fetcher    import fetch_image, generate_location_map
from voice_generator  import generate_audio
from video_builder    import build_video
from config import OUTPUT_DIR, AUDIO_DIR, IMAGE_DIR, AUTO_UPLOAD, AUTO_UPLOAD_PRIVACY, AUTO_UPLOAD_CATEGORY_ID
from long_form_script_generator import generate_long_form_script, generate_context_explainer_script
from long_form_video_builder import build_long_video
from thumbnail_generator import generate_thumbnails
from chapter_generator import generate_chapters_and_metadata
from channel_profiles import get_channel_profile


def _update_run_stage(run_id: str, channel_key: str, category: str, format_mode: str, stage: str, status: str = "running"):
    """Update SQLite runs table with current pipeline progress."""
    try:
        import sqlite3
        from pathlib import Path
        db_path = Path(__file__).resolve().parent / "db.sqlite"
        
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Check if run exists
        cursor.execute("SELECT id FROM runs WHERE id=?", (run_id,))
        row = cursor.fetchone()
        
        if not row:
            # Insert new run
            cursor.execute(
                "INSERT INTO runs (id, channel_key, category, format, stage, status, started_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_id, channel_key, category, format_mode, stage, status, time.time())
            )
        else:
            # Update existing run
            if status in ("success", "failed"):
                cursor.execute(
                    "UPDATE runs SET stage=?, status=?, finished_at=? WHERE id=?",
                    (stage, status, time.time(), run_id)
                )
            else:
                cursor.execute(
                    "UPDATE runs SET stage=?, status=? WHERE id=?",
                    (stage, status, run_id)
                )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[DB runs update error]: {e}")


def _normalize_numbers_for_tts(text: str) -> str:
    """Convert numeric expressions to spoken-word equivalents for TTS."""
    if not text:
        return text

    import re as _re

    # Fix "1, 000" style numbers (Ollama sometimes inserts space after comma)
    import re as _sp_re
    text = _sp_re.sub(r'\b(\d{1,3}),\s+(\d{3})\b', r'\1\2', text)
    text = _sp_re.sub(r'\b(\d{1,3}),\s+(\d{3}),\s+(\d{3})\b', r'\1\2\3', text)

    def _int_to_words(n: int) -> str:
        if n == 0:
            return "zero"
        ones = ["", "one", "two", "three", "four", "five", "six", "seven",
                "eight", "nine", "ten", "eleven", "twelve", "thirteen",
                "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
        tens = ["", "", "twenty", "thirty", "forty", "fifty",
                "sixty", "seventy", "eighty", "ninety"]

        def _below_1000(num: int) -> str:
            if num == 0:
                return ""
            if num < 20:
                return ones[num]
            if num < 100:
                return tens[num // 10] + ("-" + ones[num % 10] if num % 10 else "")
            remainder = num % 100
            return ones[num // 100] + " hundred" + (" and " + _below_1000(remainder) if remainder else "")

        if n < 0:
            return "minus " + _int_to_words(-n)
        if n < 1000:
            return _below_1000(n)
        if n < 1_000_000:
            thousands = n // 1000
            remainder = n % 1000
            result = _below_1000(thousands) + " thousand"
            if remainder > 0:
                result += " " + _below_1000(remainder)
            return result
        if n < 1_000_000_000:
            millions = n // 1_000_000
            remainder = n % 1_000_000
            result = _below_1000(millions) + " million"
            if remainder >= 1000:
                result += " " + _int_to_words(remainder)
            elif remainder > 0:
                result += " and " + _below_1000(remainder)
            return result
        billions  = n // 1_000_000_000
        remainder = n % 1_000_000_000
        result = _below_1000(billions) + " billion"
        if remainder > 0:
            result += " " + _int_to_words(remainder)
        return result

    def _replace_currency(m):
        symbol   = m.group(1)
        amount   = m.group(2)
        suffix   = m.group(3) or ""
        currency_name = {"$": "dollars", "£": "pounds", "€": "euros"}.get(symbol, "")
        if "." in amount:
            whole, frac = amount.replace(",", "").split(".", 1)
            spoken = _int_to_words(int(whole)) + " point " + " ".join(
                _int_to_words(int(d)) for d in frac if d.isdigit()
            )
        else:
            spoken = _int_to_words(int(amount.replace(",", "")))
        result = spoken
        if suffix.strip():
            result += " " + suffix.strip()
        if currency_name:
            result += " " + currency_name
        return result

    text = _re.sub(
        r'([$£€])(\d[\d,]*(?:\.\d+)?)(\s*(?:billion|million|trillion|thousand))?',
        _replace_currency,
        text,
        flags=_re.IGNORECASE,
    )

    def _replace_percent(m):
        num_str = m.group(1).replace(",", "")
        if "." in num_str:
            whole, frac = num_str.split(".", 1)
            return (_int_to_words(int(whole)) + " point " +
                    " ".join(_int_to_words(int(d)) for d in frac if d.isdigit()) +
                    " percent")
        return _int_to_words(int(num_str)) + " percent"

    text = _re.sub(r'(\d[\d,]*(?:\.\d+)?)\s*%', _replace_percent, text)

    def _replace_large_number(m):
        try:
            n = int(m.group(0).replace(",", ""))
            if n >= 1000:
                return _int_to_words(n)
        except ValueError:
            pass
        return m.group(0)

    text = _re.sub(r'\b\d{1,3}(?:,\d{3})+\b', _replace_large_number, text)

    def _replace_year(m):
        year = int(m.group(0))
        if 1900 <= year <= 2099:
            century = year // 100
            decade  = year % 100
            if decade == 0:
                return _int_to_words(century * 100)
            century_word = _int_to_words(century)
            decade_word  = _int_to_words(decade) if decade >= 10 else "oh " + _int_to_words(decade)
            return century_word + " " + decade_word
        return m.group(0)

    text = _re.sub(r'\b(19|20)\d{2}\b(?!\s*,\d)', _replace_year, text)

    _ORDINALS = {
        "1st": "first", "2nd": "second", "3rd": "third", "4th": "fourth",
        "5th": "fifth", "6th": "sixth", "7th": "seventh", "8th": "eighth",
        "9th": "ninth", "10th": "tenth",
    }
    for num, word in _ORDINALS.items():
        text = _re.sub(r'\b' + _re.escape(num) + r'\b', word, text, flags=_re.IGNORECASE)

    return text


def _clean_hook_sentence(hook: str) -> str:
    """
    FIX: Clean and validate map hook sentences.
    Removes incomplete endings like 'is being actively.' and ensures
    the hook is a complete, natural sentence suitable for TTS.
    """
    if not hook:
        return hook

    hook = hook.strip()

    # Bad endings that indicate the sentence was cut off
    _BAD_ENDINGS = {
        "a", "an", "the", "of", "in", "on", "at", "to", "for", "by",
        "with", "from", "and", "or", "but", "is", "are", "was", "were",
        "has", "have", "had", "will", "would", "should", "could",
        "being", "having", "doing", "going", "coming", "actively",
        "currently", "already", "still", "also", "just", "now",
    }

    # Strip trailing punctuation to check last word
    _text_clean = hook.rstrip(".!?,; ")
    _words      = _text_clean.split()
    if not _words:
        return hook

    _last = _words[-1].lower().rstrip(".,;:!?")
    if _last in _BAD_ENDINGS:
        # Try to truncate at the last clean sentence boundary
        import re as _re
        # Find the last sentence-ending period before the bad ending
        _sentences = _re.split(r'(?<=[.!?])\s+', hook.strip())
        if len(_sentences) > 1:
            # Use only the first complete sentence
            hook = _sentences[0].strip()
            if hook and not hook[-1] in ".!?":
                hook += "."
        else:
            # Try to cut back to a clean word
            for _i in range(len(_words) - 1, max(0, len(_words) - 6), -1):
                _w = _words[_i - 1].lower().rstrip(".,;:!?")
                if _w not in _BAD_ENDINGS and not _w.isdigit():
                    hook = " ".join(_words[:_i]) + "."
                    break
            else:
                # Can't salvage — use a generic hook
                hook = ""

    # Ensure it ends with terminal punctuation
    if hook and hook[-1] not in ".!?":
        hook += "."

    return hook


def _should_show_map(article: dict, primary_location: str, context: str, scenes: list) -> bool:
    """Return True when a map stinger adds clear geographic context."""
    headline = (article.get("title", "") or "").lower()

    if not primary_location:
        print("[MAP DECISION] SKIP - no primary location")
        return False

    _COMPANY_LOCATIONS = {
        "bbc", "cnn", "reuters", "ap", "fedex", "amazon", "google", "microsoft",
        "apple", "meta", "twitter", "facebook", "instagram", "tiktok", "youtube",
        "tesla", "spacex", "nasa", "who", "un", "eu", "nato", "imf",
    }
    if primary_location.lower() in _COMPANY_LOCATIONS:
        print(f"[MAP DECISION] SKIP - location is company/org name: '{primary_location}'")
        return False

    _NO_MAP_CONTEXTS = {"informative", "positive"}
    _NO_MAP_TOPIC_WORDS = {
        "scam", "fraud", "cybercrime", "hack", "comedian", "actor", "celebrity",
        "award", "film", "movie", "song", "music", "album", "sports", "cricket",
        "football", "technology", "ai", "artificial intelligence", "startup",
        "science", "research", "discovery", "space", "nasa", "satellite",
        "stock", "market", "earnings", "quarterly", "ipo", "company",
    }
    _COUNTRIES = [
        "ukraine", "russia", "iran", "israel", "india", "china", "pakistan",
        "north korea", "south korea", "gaza", "taiwan",
    ]

    if context in _NO_MAP_CONTEXTS and not any(country in headline for country in _COUNTRIES):
        print(f"[MAP DECISION] SKIP - context '{context}' with no country-specific event")
        return False

    if any(word in headline for word in _NO_MAP_TOPIC_WORDS):
        _geo_events = {
            "killed", "dead", "attack", "war", "conflict", "strike", "bomb",
            "earthquake", "flood", "disaster", "election", "coup", "arrest",
            "sanctions", "protest", "explosion", "missile", "drone",
        }
        if not any(w in headline for w in _geo_events):
            print("[MAP DECISION] SKIP - feature/profile story with no geo-event")
            return False

    _SHOW_MAP_TRIGGERS = {
        "killed", "dead", "attack", "war", "conflict", "strike", "bomb",
        "airstrike", "missile", "drone", "ceasefire", "invasion", "troops",
        "earthquake", "flood", "disaster", "hurricane", "tsunami",
        "election", "coup", "arrested", "sanctions", "protest", "rally",
        "nuclear", "hostage", "siege", "offensive",
    }
    _has_geo_event    = any(w in headline for w in _SHOW_MAP_TRIGGERS)
    _has_real_location = len(primary_location) > 2

    if _has_geo_event and _has_real_location:
        print(f"[LOCATION] map stinger is eligible for '{primary_location}'")
        return True
    if context in {"tense", "war", "serious", "disaster", "politics"} and _has_real_location:
        print(f"[LOCATION] map stinger eligible due to context '{context}'")
        return True

    print("[MAP DECISION] SKIP - no clear geographic event trigger found")
    return False


def save_cache(data, filename):
    with open(os.path.join(OUTPUT_DIR, filename), 'w') as f:
        json.dump(data, f, indent=4)


def load_cache(filename):
    path = os.path.join(OUTPUT_DIR, filename)
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f)
    return None


def _sanitize_scene_text_for_tts(text: str) -> str:
    """Final cleanup of scene text before passing to TTS."""
    if not text:
        return text

    import re as _html_re
    import html as _html_entities

    text = _html_re.sub(r'<[^>]+>', ' ', text, flags=_html_re.DOTALL)
    text = _html_entities.unescape(text)
    text = _html_re.sub(r'https?://\S+', ' ', text)
    text = _html_re.sub(r'www\.\S+', ' ', text)
    text = _html_re.sub(r'\b[a-z]+-[a-z]+-[a-z]+-[a-z]+(?:-[a-z]+)*\b', ' ', text)
    text = _html_re.sub(r'\s+', ' ', text).strip()

    # FIX: Detect and drop meta-commentary first lines that leaked through
    _META_PATTERNS = [
        r'(?i)^here are \d+ short',
        r'(?i)^here is the script',
        r'(?i)^here are \d+ news',
        r'(?i)^here are \d+ sentences',
        r'(?i)^below (?:is|are)',
        r'(?i)^the following',
        r'(?i)^i have written',
    ]
    for _pat in _META_PATTERNS:
        if re.search(_pat, text):
            _colon_pos = text.find(":")
            if _colon_pos != -1 and len(text) > _colon_pos + 5:
                _after = text[_colon_pos + 1:].strip()
                if len(_after.split()) >= 5:
                    text = _after
                    if text and text[0].islower():
                        text = text[0].upper() + text[1:]
            else:
                return ""

    text = _normalize_numbers_for_tts(text)

    if text and text[0].islower():
        text = text[0].upper() + text[1:]

    if text and text[-1] not in ".!?।":
        text += "."

    import re as _tts_re
    # For QUOTE: strip tag and keep the text
    text = _tts_re.sub(r'\[QUOTE:\s*["\'“‘]?(.*?)["\'”’]?\]', r'\1', text)
    # For TWEET: convert "[TWEET: '@user: text']" to "According to @user, text"
    def _clean_tweet_tts(m):
        val = m.group(1).strip()
        if ":" in val:
            parts = val.split(":", 1)
            return f"According to {parts[0].strip()}, {parts[1].strip()}"
        return val
    text = _tts_re.sub(r'\[TWEET:\s*["\'“‘]?(.*?)["\'”’]?\]', _clean_tweet_tts, text)
    # For DOCUMENT: strip tag and keep the text
    text = _tts_re.sub(r'\[DOCUMENT:\s*["\'“‘]?(.*?)["\'”’]?\]', r'\1', text)

    text = _tts_re.sub(r'["\u201c\u201d\u2018\u2019]+', '', text)
    text = _tts_re.sub(r'\s{2,}', ' ', text).strip()

    _POSSESSIVE_FIXES = {
        " Trumps ":    " Trump's ",
        " Bidens ":    " Biden's ",
        " Putins ":    " Putin's ",
        " Irans ":     " Iran's ",
        " Israels ":   " Israel's ",
        " Russias ":   " Russia's ",
        " Chinas ":    " China's ",
        " Indias ":    " India's ",
        "Zelenskyys":  "Zelenskyy's",
    }
    for _bad, _good in _POSSESSIVE_FIXES.items():
        text = text.replace(_bad, _good)

    # Acronym/ALL CAPS casing normalization for Kokoro TTS
    # Converts all-caps words to lowercase, unless they are in the whitelist of acronyms.
    # This avoids Kokoro spelling out words like FANS, TERMS, BY, etc. letter-by-letter.
    _SPELLED_OUT_ACRONYMS = {
        "USA", "US", "UK", "UN", "EU", "BBC", "CNN", "FBI", "CIA", 
        "IPL", "ICC", "BCCI", "WHO", "IMF", "G20", "TV", "AI", "TTS",
    }
    def _casing_repl(m):
        w = m.group(0)
        # Strip trailing 's or 'S if present for lookup
        lookup = w
        if lookup.endswith("'S") or lookup.endswith("'s"):
            lookup = lookup[:-2]
        if lookup in _SPELLED_OUT_ACRONYMS:
            return w
        return w.lower()
    
    text = re.sub(r'\b[A-Z\']{2,}\b', _casing_repl, text)

    text = re.sub(r"\s+", " ", text).strip()
    return text


def generate_youtube_metadata(article: dict, scenes: list, context: str, script: str, channel_profile=None) -> dict:
    """Generate YouTube-ready metadata for the created video."""
    channel_profile = channel_profile or get_channel_profile(article.get("_channel_key", "newscup"))
    headline = article.get("title", "Breaking News")

    import re as _metadata_re
    import html as _metadata_html
    headline = _metadata_re.sub(r'<[^>]+>', ' ', headline, flags=_metadata_re.DOTALL)
    headline = _metadata_html.unescape(headline)
    headline = _metadata_re.sub(r'https?://\S+', ' ', headline)
    headline = _metadata_re.sub(r'www\.\S+', ' ', headline)
    headline = _metadata_re.sub(r'\b[a-z]+-[a-z]+-[a-z]+-[a-z]+(?:-[a-z]+)*\b', ' ', headline)
    headline = _metadata_re.sub(r'\s+', ' ', headline).strip()

    article_url = article.get("link", "")

    TITLE_PREFIXES = {
        "tense":       "🔴 BREAKING:",
        "war":         "⚡ WAR UPDATE:",
        "politics":    "🏛️ POLITICAL ALERT:",
        "serious":     "🚨 URGENT NEWS:",
        "positive":    "✅ MAJOR WIN:",
        "informative": "📡 TECH ALERT:",
        "business":    "💹 MARKET NEWS:",
        "disaster":    "🌪️ DISASTER ALERT:",
        "neutral":     "📰 NEWS UPDATE:",
        "sports":      "🏆 SPORTS:",
        "football":    "⚽ FOOTBALL:",
    }
    prefix   = TITLE_PREFIXES.get(context, "📰 NEWS UPDATE:")
    yt_title = f"{prefix} {headline}"
    max_title_len = 59 if context in ("sports", "football") or article.get("category") == "football" else 100
    if len(yt_title) > max_title_len:
        yt_title = yt_title[:max_title_len - 3] + "..."

    scene_texts  = [s.get("text", "") for s in scenes if s.get("text", "").strip()]
    full_summary = " ".join(scene_texts) or script.strip()

    entities    = scenes[0].get("entities", {}) if scenes else {}
    country     = entities.get("country_context", "")
    person      = entities.get("person", "")
    all_locs    = entities.get("all_locations", [])

    CONTEXT_HASHTAGS = {
        "tense":       ["#BreakingNews", "#WorldNews", "#Conflict", "#NewsAlert"],
        "war":         ["#WarNews", "#BreakingNews", "#WorldNews", "#Military"],
        "politics":    ["#Politics", "#WorldNews", "#Government", "#Breaking"],
        "serious":     ["#Breaking", "#EmergencyAlert", "#WorldNews", "#Crisis"],
        "positive":    ["#GoodNews", "#Achievement", "#WorldNews", "#Historic"],
        "informative": ["#TechNews", "#Innovation", "#Science", "#WorldNews"],
        "business":    ["#EconomyNews", "#Markets", "#Business", "#WorldNews"],
        "disaster":    ["#EmergencyAlert", "#DisasterNews", "#Breaking", "#Crisis"],
        "neutral":     ["#News", "#WorldNews", "#Today", "#Breaking"],
        "sports":      ["#SportsNews", "#Sports", "#Athletes", "#GameDay"],
        "football":    ["#FootballNews", "#Football", "#Soccer", "#MatchDay", "#PremierLeague", "#FifaWorldCup"],
    }
    hashtags = list(CONTEXT_HASHTAGS.get(context, ["#News", "#WorldNews"]))

    if country:
        hashtags.append(f"#{country.replace(' ', '')}")
    if person:
        hashtags.append(f"#{person.split()[-1]}")
    for loc in all_locs[:2]:
        clean_loc = loc.replace(" ", "").replace("'", "")
        if len(clean_loc) > 2:
            hashtags.append(f"#{clean_loc}")

    seen_ht   = set()
    deduped   = []
    for h in hashtags:
        hk = h.lower()
        if hk not in seen_ht:
            seen_ht.add(hk)
            deduped.append(h)
    hashtags       = deduped[:15]
    hashtag_string = " ".join(hashtags)

    subscribe_line = (
        "Subscribe for daily breaking news videos"
        if channel_profile.language == "en"
        else "Subscribe for daily Hindi news videos"
    )
    description = (
        f"{headline}\n\n"
        f"{full_summary}\n\n"
        f"Channel: {channel_profile.display_name}\n"
        f"{subscribe_line}\n"
        f"{'─' * 40}\n"
        f"🔔 Subscribe for daily breaking news videos\n"
        f"👍 Like if this was informative\n"
        f"💬 Share your thoughts in the comments\n"
        f"{'─' * 40}\n\n"
    )
    if article_url:
        description += f"📰 Original source: {article_url}\n\n"
    description += f"{hashtag_string}\n\n"
    if channel_profile.language == "hi":
        description += f"#{channel_profile.channel_handle} #NewsVideo #HindiNews #IndiaNews #BreakingNews"
    else:
        description += f"#{channel_profile.channel_handle} #NewsVideo #WorldNews #BreakingNews"

    metadata = {
        "title":          yt_title,
        "description":    description,
        "hashtags":       hashtags,
        "hashtag_string": hashtag_string,
        "context":        context,
        "source_url":     article_url,
        "channel":        channel_profile.display_name,
        "language":       channel_profile.language,
    }

    def _safe_print(message: str) -> None:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        print(message.encode(encoding, errors="replace").decode(encoding, errors="replace"))

    meta_path = os.path.join(OUTPUT_DIR, "youtube_metadata.txt")
    try:
        with open(meta_path, "w", encoding="utf-8") as f:
            f.write(f"YOUTUBE TITLE:\n{yt_title}\n\n")
            f.write(f"{'═' * 60}\n\n")
            f.write(f"YOUTUBE DESCRIPTION:\n{description}\n\n")
            f.write(f"{'═' * 60}\n\n")
            f.write(f"HASHTAGS:\n{hashtag_string}\n\n")
            f.write(f"{'═' * 60}\n\n")
            f.write("TAGS FOR YOUTUBE TAG BOX (comma-separated):\n")
            tags = [h.lstrip("#") for h in hashtags]
            tags += ["news", "breaking news", channel_profile.display_name.lower(), "news video"]
            if channel_profile.language == "hi":
                tags += ["hindi news", "india news", "bharat news"]
            else:
                tags += ["world news", "international news"]
            f.write(", ".join(tags[:30]) + "\n")
    except Exception as e:
        _safe_print(f"[METADATA] Could not save metadata: {e}")
    else:
        _safe_print(f"\n[METADATA] YouTube metadata saved: {meta_path}")
        _safe_print(f"[METADATA] Title: {yt_title}")
        _safe_print(f"[METADATA] Hashtags: {hashtag_string}")

    return metadata


def _generate_map_hook(article: dict, primary_location: str, pipeline_context: str) -> str:
    """Generate a broadcast-quality hook sentence for the map stinger."""
    import re as _hook_re
    import html as _hook_html

    def _clean_text(t: str) -> str:
        if not t:
            return ""
        t = _hook_re.sub(r'<[^>]+>', ' ', t, flags=_hook_re.DOTALL)
        t = _hook_html.unescape(t)
        t = _hook_re.sub(r'https?://\S+', ' ', t)
        t = _hook_re.sub(r'www\.\S+', ' ', t)
        t = _hook_re.sub(r'\b[a-z]+-[a-z]+-[a-z]+-[a-z]+(?:-[a-z]+)*\b', ' ', t)
        return _hook_re.sub(r'\s+', ' ', t).strip()

    full_text = _clean_text(
        article.get("full_article_text", "")
        or article.get("description", "")
        or article.get("summary", "")
        or article.get("title", "")
    )
    headline = _clean_text(article.get("title", ""))

    _CONTEXT_LABELS = {
        "tense":       "BREAKING NEWS",
        "war":         "BREAKING NEWS",
        "serious":     "URGENT NEWS",
        "disaster":    "URGENT NEWS",
        "politics":    "DEVELOPING NEWS",
        "positive":    "MAJOR UPDATE",
        "informative": "NEWS UPDATE",
        "neutral":     "NEWS UPDATE",
    }
    news_label = _CONTEXT_LABELS.get(pipeline_context, "BREAKING NEWS")

    _SHORT_MAP = {
        "democratic republic of congo": "DR Congo",
        "the democratic republic of congo": "DR Congo",
        "united states": "the US",
        "united states of america": "the US",
        "united kingdom": "the UK",
        "united arab emirates": "UAE",
        "north korea": "North Korea",
        "south korea": "South Korea",
    }
    short_loc = _SHORT_MAP.get(primary_location.lower(), primary_location)

    hook = f"{news_label} from {short_loc}."
    print(f"[HOOK] Fast Map Intro: '{hook}'")
    return hook


def run_format_pipeline(fmt, article, args, RUN_ID, _pipeline_context):
    channel_profile = get_channel_profile(getattr(args, "channel", "newscup"))
    script_file = "script_long.txt" if fmt == "long" else "script.txt"
    scenes_file = "scenes_long.json" if fmt == "long" else "scenes.json"
    meta_file   = "pipeline_meta_long.json" if fmt == "long" else "pipeline_meta.json"

    video_style = getattr(args, "video_style", "briefing")
    if article.get("_tracked_story"):
        video_style = "tracker"
        print(f"[PIPELINE] Tracked story detected. Automatically using '{video_style}' style.")

    if fmt == "short" and video_style == "compilation":
        compilation_list = article.get("_compilation_articles", [])
        if compilation_list:
            print("[PIPELINE] Short format with compilation style: overriding article to use only the first story (single story).")
            article = compilation_list[0]
            video_style = "briefing"

    episode_number = 1
    if video_style == "tracker":
        tracked_story = article.get("_tracked_story")
        if tracked_story:
            episode_number = tracked_story["episode_count"] + 1

    from correlation_engine import CorrelationEngine
    pacing_style = CorrelationEngine.get_optimized_pacing_and_style(channel_profile.key, fmt)
    top_scripts = CorrelationEngine.get_top_performing_script_contexts(
        channel_key=channel_profile.key,
        category=args.category,
        format_mode=fmt,
        limit=3
    )

    # ── Stage 2: Script ──────────────────────────────────────────────────────
    script      = None
    script_path = os.path.join(OUTPUT_DIR, script_file)
    if args.skip_to in ["scenes", "assets", "video"]:
        if os.path.exists(script_path):
            with open(script_path, 'r', encoding='utf-8') as f:
                script = f.read()
            print(f"\n[SKIP] Loading cached {fmt}-form script...")

    if not script:
        _update_run_stage(RUN_ID, channel_profile.key, args.category, args.format, "script")
        print(f"\n[2/5] Generating {fmt}-form script...")
        full_text = (
            article.get("full_article_text")
            or article.get("description", "")
            or article.get("summary", "")
            or article.get("title", "")
        )
        if not full_text or not full_text.strip():
            full_text = article.get("title", "Breaking news")

        if fmt == "long":
            if video_style == "compilation":
                print("[PIPELINE] Compilation video style detected. Using multi-story script compiler for long-form...")
                compilation_list = article.get("_compilation_articles", [])
                script = generate_compilation_script(compilation_list, channel_profile=channel_profile)
            elif video_style == "context":
                print(f"[PIPELINE] Context Explainer style selected. Generating deep-dive context script...")
                script = generate_context_explainer_script(
                    article,
                    context=_pipeline_context,
                    channel_profile=channel_profile
                )
                if not script:
                    print(f"[WARN] Context Explainer script generation returned empty. Falling back to default long-form script.")
            if not script:
                script = generate_long_form_script(
                    full_text,
                    target_scenes=15,
                    context=_pipeline_context,
                    channel_profile=channel_profile,
                    top_performing_templates=top_scripts,
                )
        else:
            if video_style == "compilation":
                print("[PIPELINE] Compilation video style detected. Using multi-story script compiler...")
                compilation_list = article.get("_compilation_articles", [])
                script = generate_compilation_script(compilation_list, channel_profile=channel_profile)
            else:
                _is_full_article = len(full_text) > 500
                print(f"[Stage 2] Script input: {len(full_text)} chars "
                      f"({'full article' if _is_full_article else 'RSS snippet'})")
                script = summarise(full_text, channel_profile=channel_profile, top_performing_templates=top_scripts)
                
                if len(script.split()) < 60 and fmt == "short":
                    print(f"[PIPELINE] Script too short ({len(script.split())} words) -- attempting DDG expansion")
                    try:
                        from news_fetcher import _ddg_article_search
                        _extra = _ddg_article_search(article.get("title", ""), article.get("link", ""), max_chars=2000)
                        if _extra and len(_extra) > 200:
                            _expanded_text = full_text.strip() + " " + _extra
                            print(f"[PIPELINE] DDG expansion added {len(_extra)} chars -- regenerating script")
                            script = summarise(_expanded_text, channel_profile=channel_profile, top_performing_templates=top_scripts)
                    except Exception as _exp_err:
                        print(f"[PIPELINE] DDG expansion failed: {_exp_err}")

        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(script)

    try:
        from script_generator import detect_context as _detect_ctx, nlp as _sg_nlp
        full_text = (
            article.get("full_article_text")
            or article.get("description", "")
            or article.get("summary", "")
            or article.get("title", "")
        )
        if not full_text or not full_text.strip():
            full_text = article.get("title", "Breaking news")
        _ctx_text = full_text if len(script.split()) < 40 else script
        _ctx_doc  = _sg_nlp(_ctx_text)
        _detected = _detect_ctx(_ctx_doc)
        if _detected and _detected not in ("", None):
            _pipeline_context = _detected
        print(f"[{fmt.upper()}-PIPELINE] Story context: '{_pipeline_context}'")
    except Exception as _ctx_err:
        _headline_lower = article.get("title", "").lower()
        if any(w in _headline_lower for w in ["kill", "dead", "attack", "strike", "war", "bomb", "shot", "conflict"]):
            _pipeline_context = "tense"
        elif any(w in _headline_lower for w in ["crash", "disaster", "earthquake", "flood", "fire", "crisis"]):
            _pipeline_context = "serious"
        print(f"[{fmt.upper()}-PIPELINE] Context fallback: '{_pipeline_context}'")

    _script_word_count = len(script.split()) if script else 0
    print(f"[HEALTH] Script: {_script_word_count} words | Context: '{_pipeline_context}'")
    _verify_score = article.get("verification_score", 50)
    print(f"[VERIFY] Article confidence: {_verify_score}/100 | Sources: {article.get('cross_sources', [])}")

    if args.stage == "script":
        return _pipeline_context

    # ── Stage 3: Scenes ──────────────────────────────────────────────────────
    scenes        = None
    pipeline_meta = None
    if args.skip_to in ["assets", "video"]:
        scenes        = load_cache(scenes_file)
        pipeline_meta = load_cache(meta_file)
        if scenes:
            print(f"\n[SKIP] Loading cached {fmt}-form scenes...")
            for scene in scenes:
                scene["orientation"] = "landscape" if fmt == "long" else "portrait"
                for path_key in ("image_path", "audio_path", "alt_image_path"):
                    p = scene.get(path_key)
                    if p and not os.path.isfile(p):
                        scene[path_key] = None

    if not scenes:
        _update_run_stage(RUN_ID, channel_profile.key, args.category, args.format, "scenes")
        print(f"\n[3/5] Planning {fmt}-form scenes...")
        if fmt == "long" and video_style == "context":
            print(f"[PIPELINE] Context Explainer style selected. Planning scenes paragraph-by-paragraph...")
            # Split paragraph by paragraph, plan scenes, and annotate paragraph ends
            paragraphs = [p.strip() for p in script.split("\n\n") if p.strip()]
            all_scenes = []
            for p_idx, p in enumerate(paragraphs):
                # Clean paragraph header if any, supporting bolding asterisks, colons, dashes, etc.
                p_clean = re.sub(
                    r'^[\s\*\#_`"]*(Paragraph \d+(\s*\([^)]+\))?|HOOK|THE NEWS|THE HISTORY|THE PLAYERS|THE STAKES|THE VERDICT)[\s\*\#_`":\-]*',
                    '',
                    p,
                    flags=re.IGNORECASE
                ).strip()
                if not p_clean:
                    continue
                p_scenes = plan_scenes(p_clean, pacing_style=pacing_style)
                if p_scenes:
                    if p_idx < len(paragraphs) - 1:
                        p_scenes[-1]["is_paragraph_end"] = True
                    if p_idx == len(paragraphs) - 1 or "assessment:" in p_clean.lower():
                        for s in p_scenes:
                            s["is_verdict"] = True
                    all_scenes.extend(p_scenes)
            scenes = all_scenes
        else:
            print(f"[PIPELINE DEBUG] Calling plan_scenes(script)")
            print(f"[PIPELINE DEBUG] script type: {type(script)}")
            print(f"[PIPELINE DEBUG] script length: {len(script) if script else 0}")
            print(f"[PIPELINE DEBUG] script preview: {repr(script[:300]) if script else 'None'}")
            scenes = plan_scenes(script, pacing_style=pacing_style)
            print(f"[PIPELINE DEBUG] plan_scenes returned: {len(scenes) if scenes else 0} scenes")

        if not scenes:
            print(f"[PIPELINE] CRITICAL: plan_scenes() returned 0 scenes — emergency fallback.")
            _emergency_text = article.get("title", "Breaking news.") + "."
            from scene_planner import extract_keywords
            scenes = [{
                "text":        _emergency_text,
                "keyword":     extract_keywords(_emergency_text),
                "type":        "general",
                "context":     "general",
                "entities":    {
                    "location": "", "person": "", "org": "",
                    "all_persons": [], "all_locations": [], "all_orgs": [],
                    "all_events": [], "country_context": "",
                },
                "headline":    article.get("title", ""),
                "news_source": article.get("_source_name", "World News"),
                "article_url": article.get("link", ""),
                "og_image_url": article.get("og_image_url", ""),
            }]

        def _is_meta_scene(text: str) -> bool:
            _META = [r'(?i)^here are \d+', r'(?i)^here is the', r'(?i)^below (?:is|are)', r'(?i)^the following']
            for _p in _META:
                if re.search(_p, text.strip()):
                    return True
            return False

        scenes  = [s for s in scenes if not _is_meta_scene(s.get("text", ""))]

        # ── Resolve primary location ──────────────────────────────────────────
        primary_location = ""
        _CONFLICT_OVERRIDE = {
            "ukraine": "Ukraine", "russia": "Russia", "gaza": "Gaza", "iran": "Iran",
            "israel": "Israel", "taiwan": "Taiwan", "myanmar": "Myanmar",
        }
        _HEADLINE_LOCATIONS = {
            "iran": "Iran", "israel": "Israel", "gaza": "Gaza", "ukraine": "Ukraine",
            "russia": "Russia", "china": "China", "india": "India", "pakistan": "Pakistan",
            "lebanon": "Lebanon", "syria": "Syria", "iraq": "Iraq", "yemen": "Yemen",
            "afghanistan": "Afghanistan", "turkey": "Turkey", "taiwan": "Taiwan",
            "north korea": "North Korea", "united states": "United States", "uk": "United Kingdom",
            "france": "France", "germany": "Germany", "japan": "Japan", "brazil": "Brazil",
            "australia": "Australia", "canada": "Canada", "delhi": "New Delhi", "mumbai": "Mumbai",
        }

        _headline_lower = article.get("title", "").lower()
        headline_loc    = ""
        for _conflict_key, _conflict_loc in _CONFLICT_OVERRIDE.items():
            if re.search(r'\b' + re.escape(_conflict_key) + r'\b', _headline_lower):
                headline_loc = _conflict_loc
                break

        if not headline_loc:
            for _loc_key in sorted(_HEADLINE_LOCATIONS.keys(), key=len, reverse=True):
                if re.search(r'\b' + re.escape(_loc_key) + r'\b', _headline_lower):
                    headline_loc = _HEADLINE_LOCATIONS[_loc_key]
                    break

        scene_gpe         = ""
        scene_country_ctx = ""
        if scenes:
            entities   = scenes[0].get("entities", {})
            all_locs   = entities.get("all_locations", [])
            geo_locs   = [loc for loc in all_locs if loc.lower() not in ["bbc", "news", "reuters", "ap"]]
            if geo_locs:
                scene_gpe = max(geo_locs, key=len)
            scene_country_ctx = entities.get("country_context", "")

        if headline_loc:
            primary_location = headline_loc
        elif scene_gpe:
            primary_location = scene_gpe
        else:
            primary_location = scene_country_ctx

        primary_location = primary_location.replace("'s", "").strip()
        for _article in ("the ", "The ", "a ", "A ", "an ", "An "):
            if primary_location.startswith(_article):
                primary_location = primary_location[len(_article):]
                break

        print(f"[LOCATION] Resolved primary location: '{primary_location}'")

        COUNTRY_COORDS_OVERRIDE = {
            "united states": (38.8954, -77.0369), "united kingdom": (51.5074, -0.1278),
            "india": (28.6139, 77.2090), "china": (39.9042, 116.4074), "russia": (55.7558, 37.6173),
            "ukraine": (50.4501, 30.5234), "france": (48.8566, 2.3522), "germany": (52.5200, 13.4050),
            "iran": (35.6892, 51.3890), "israel": (31.7683, 35.2137), "gaza": (31.3547, 34.3088),
            "lebanon": (33.8938, 35.5018), "syria": (33.5102, 36.2913), "taiwan": (25.0330, 121.5654),
            "new delhi": (28.6139, 77.2090), "mumbai": (19.0760, 72.8777),
        }
        _loc_key       = primary_location.lower().strip()
        _coord_override = COUNTRY_COORDS_OVERRIDE.get(_loc_key)

        map_image_path = None
        _show_map      = _should_show_map(article, primary_location, _pipeline_context, scenes)
        if primary_location and _show_map:
            map_out        = os.path.join(IMAGE_DIR, f"map_stinger_{fmt}.jpg")
            map_image_path = generate_location_map(primary_location, map_out, coord_override=_coord_override)

        map_audio_path = None
        map_narration  = ""
        if map_image_path and primary_location:
            map_narration = _generate_map_hook(article, primary_location, _pipeline_context)
            map_narration = _clean_hook_sentence(map_narration)
            if not map_narration:
                map_narration = f"News update from {primary_location}. Details are emerging."
            map_idx        = 1997 if fmt == "long" else 997
            map_audio_path = generate_audio(
                map_narration, index=map_idx, context=_pipeline_context, language=channel_profile.language,
                pause_after_sentence=pacing_style.get("pause_after_sentence"),
                video_style=video_style
            )

        for scene in scenes:
            scene["headline"]      = article["title"]
            scene["news_source"]   = article.get("_source_name", "World News")
            scene["article_url"]   = article.get("link", "")
            scene["og_image_url"]  = article.get("og_image_url", "")
            scene["orientation"]   = "landscape" if fmt == "long" else "portrait"

        pipeline_meta = {
            "map_image_path":   map_image_path,
            "map_audio_path":   map_audio_path,
            "map_hook_text":    map_narration,
            "primary_location": primary_location,
            "headline":         article.get("title", "Breaking News") or "Breaking News",
            "story_context":    _pipeline_context,
            "article_url":      article.get("link", ""),
            "show_map":         _show_map,
            "channel":          channel_profile.display_name,
            "channel_key":      channel_profile.key,
            "language":         channel_profile.language,
            "source_policy":    channel_profile.source_policy,
        }
        save_cache(scenes, scenes_file)
        save_cache(pipeline_meta, meta_file)

    if args.stage == "scenes":
        return _pipeline_context

    # ── Stage 4: Assets ──────────────────────────────────────────────────────
    if args.stage == "assets" or args.skip_to != "video":
        _update_run_stage(RUN_ID, channel_profile.key, args.category, args.format, "assets")
        print(f"\n[4/5] Fetching images and generating audio for {fmt}-form...")
        from concurrent.futures import ThreadPoolExecutor

        orientation = "landscape" if fmt == "long" else "portrait"
        def _fetch_image_task(args_tuple):
            scene, idx = args_tuple
            scene["image_path"] = fetch_image(scene=scene, index=idx)
            return scene

        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(_fetch_image_task, [(scene, idx) for idx, scene in enumerate(scenes)]))
        scenes = results

        from voice_generator import KOKORO_AVAILABLE as _kokoro_ok
        def _audio_task(args_tuple):
            scene, idx = args_tuple
            if scene.get("type") == "transition" or scene.get("is_transition"):
                scene["audio_path"] = None
                return scene
            _raw_text  = scene.get("text", "")
            _tts_text  = _sanitize_scene_text_for_tts(_raw_text)
            if not _tts_text or not _tts_text.strip():
                scene["audio_path"] = None
                return scene
            _ctx      = pipeline_meta.get("story_context", "neutral") if pipeline_meta else "neutral"
            scene_idx = idx + 100 if fmt == "long" else idx
            scene["audio_path"] = generate_audio(
                _tts_text, scene_idx, context=_ctx, language=channel_profile.language,
                pause_after_sentence=pacing_style.get("pause_after_sentence"),
                video_style=video_style,
                is_paragraph_end=scene.get("is_paragraph_end", False),
                is_verdict=scene.get("is_verdict", False)
            )
            return scene

        if _kokoro_ok:
            with ThreadPoolExecutor(max_workers=3) as audio_executor:
                audio_results = list(audio_executor.map(_audio_task, [(scene, idx) for idx, scene in enumerate(scenes)]))
            scenes = audio_results
        else:
            for idx, scene in enumerate(scenes):
                scenes[idx] = _audio_task((scene, idx))

        # Compute durations
        for scene in scenes:
            if scene.get("type") == "transition":
                scene["duration"] = 1.5
                continue
            ap = scene.get("audio_path")
            if ap and os.path.isfile(ap):
                try:
                    from moviepy.audio.io.AudioFileClip import AudioFileClip as _AFC
                    _ac         = _AFC(ap)
                    _scene_dur  = _ac.duration
                    _ac.close()
                    scene["duration"] = min(max(2.5, min(_scene_dur, 10.0)) + 0.30, 10.5)
                except Exception:
                    scene["duration"] = min(max(2.5, len(scene["text"].split()) * 0.6) + 0.30, 10.5)
            else:
                scene["duration"] = min(max(2.5, len(scene["text"].split()) * 0.6) + 0.30, 10.5)

        # Pre-fetch visual cuts for short form
        if fmt == "short":
            print("[4/5] Pre-fetching visual cut alt-images...")
            from image_fetcher import _build_query, fetch_with_retry, clean_query, IMAGE_DIR as _IMG_DIR, PEXELS_API_KEY as _PEXELS_KEY
            if _PEXELS_KEY:
                import hashlib as _hs
                for idx, scene in enumerate(scenes):
                    if scene.get("is_anchor", False):
                        continue
                    audio_path = scene.get("audio_path")
                    scene["alt_image_path"] = None
                    if audio_path and os.path.isfile(audio_path):
                        from moviepy.audio.io.AudioFileClip import AudioFileClip as _AFC
                        try:
                            _ac = _AFC(audio_path)
                            _scene_dur = _ac.duration
                            _ac.close()
                            if _scene_dur > 2.8 and scene.get("image_path"):
                                _alt_queries = _build_query(scene)
                                for _aq in _alt_queries[1:4]:
                                    _aq = clean_query(_aq)
                                    _alt_url = fetch_with_retry(_aq, idx + 1000)
                                    if _alt_url:
                                        _alt_dest = os.path.join(
                                            _IMG_DIR, f"scene_{idx:02d}_b_{_hs.md5(_aq.encode()).hexdigest()[:8]}.jpg"
                                        )
                                        import requests as _req
                                        _r = _req.get(_alt_url, timeout=10)
                                        if _r.status_code == 200:
                                            with open(_alt_dest, "wb") as _f:
                                                _f.write(_r.content)
                                            if os.path.getsize(_alt_dest) > 2048:
                                                scene["alt_image_path"] = _alt_dest
                                                break
                        except Exception as _alt_exc:
                            print(f"[ALT IMAGE] Scene {idx} failed: {_alt_exc}")

        # Purge meta/empty scenes
        _PURGE_PATTERNS = [
            r'(?i)^here are \d+', r'(?i)^here is the', r'(?i)^here are the', r'(?i)^below (?:is|are)',
            r'(?i)^the following', r'(?i)^i have written', r'(?i)^as requested', r'(?i)^sure,?\s+here',
            r'(?i)^okay,?\s+here',
        ]
        def _is_meta_scene(text: str) -> bool:
            import re as _mr
            t = (text or "").strip()
            if not t or len(t.split()) < 4:
                return True
            for _p in _PURGE_PATTERNS:
                if _mr.search(_p, t):
                    return True
            return False

        scenes = [
            s for s in scenes if (s.get("type") == "transition" or s.get("is_transition")) or (
                not _is_meta_scene(s.get("text", ""))
                and s.get("audio_path") and os.path.isfile(s.get("audio_path", ""))
            )
        ]
        if scenes:
            for _s in scenes:
                _s.pop("is_anchor", None)

        save_cache(scenes, scenes_file)

    if args.stage == "assets":
        return _pipeline_context

    # ── Stage 5: Video ───────────────────────────────────────────────────────
    _update_run_stage(RUN_ID, channel_profile.key, args.category, args.format, "video")
    print(f"\n[5/5] Building {fmt}-form video...")
    try:
        if fmt == "long":
            output_path = build_long_video(
                scenes, pipeline_meta=pipeline_meta,
                visual_cut_threshold=pacing_style.get("visual_cut_threshold", 2.8)
            )
            print("\n" + "=" * 60)
            print(f"[SUCCESS] Widescreen video created: {output_path}")
            metadata_path = generate_chapters_and_metadata(scenes, pipeline_meta.get("headline", "Breaking News"), OUTPUT_DIR)
            print(f"[SUCCESS] YouTube Chapters & Metadata: {metadata_path}")
        else:
            output_path = build_video(
                scenes, pipeline_meta=pipeline_meta,
                visual_cut_threshold=pacing_style.get("visual_cut_threshold", 2.8)
            )
            print("\n" + "=" * 60)
            print(f"[SUCCESS] Portrait video created: {output_path}")
            generate_youtube_metadata(article, scenes, _pipeline_context, script, channel_profile=channel_profile)

        # Thumbnails
        main_img = None
        for _s in scenes:
            _ip = _s.get("image_path", "")
            if _ip and "anchor" not in os.path.basename(_ip).lower() and os.path.isfile(_ip):
                main_img = _ip
                break

        generate_thumbnails(
            headline=pipeline_meta.get("headline", "Breaking News"),
            main_image_path=main_img,
            output_dir=OUTPUT_DIR,
            scenes=scenes,
            format_mode=fmt,
            context=pipeline_meta.get("story_context", "neutral"),
            primary_color=pacing_style.get("primary_color"),
            accent_color=pacing_style.get("accent_color"),
            badge_color=pacing_style.get("badge_color"),
            font_family=pacing_style.get("font_family"),
            video_style=video_style,
            episode_number=episode_number,
        )
        print("=" * 60)

        # Save video configurations to database
        try:
            import sqlite3
            from pathlib import Path
            db_path = Path(__file__).resolve().parent / "db.sqlite"
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            
            pause_val = pacing_style.get("pause_after_sentence", 0.20)
            cut_val = pacing_style.get("visual_cut_threshold", 2.8)
            
            cursor.execute("""
                INSERT OR REPLACE INTO video_configurations (
                    run_id, channel_key, format, category, script_text, script_word_count,
                    verification_score, detected_context, hook_text,
                    pause_after_sentence, visual_cut_threshold, scene_count,
                    primary_color, accent_color, badge_color, font_family,
                    has_anchor, has_map_stinger, primary_location, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                RUN_ID,
                channel_profile.key,
                fmt,
                args.category,
                script,
                len(script.split()) if script else 0,
                article.get("verification_score", 50),
                _pipeline_context,
                pipeline_meta.get("map_hook_text") or (scenes[0].get("text") if scenes else ""),
                pause_val,
                cut_val,
                len(scenes) if scenes else 0,
                channel_profile.primary_color,
                channel_profile.accent_color,
                channel_profile.primary_color,
                pacing_style.get("font_family", "C:/Windows/Fonts/arialbd.ttf"),
                1 if any(s.get("is_anchor", False) for s in scenes) else 0,
                1 if pipeline_meta.get("show_map", False) else 0,
                pipeline_meta.get("primary_location", ""),
                time.time()
            ))
            if video_style == "tracker":
                tracked_story = article.get("_tracked_story")
                if tracked_story:
                    cursor.execute("""
                        UPDATE tracked_stories 
                        SET last_updated=?, episode_count=episode_count+1, story_summary=?
                        WHERE id=?
                    """, (time.time(), script[:500], tracked_story["id"]))
                else:
                    story_key = f"story_{uuid.uuid4().hex[:8]}"
                    cursor.execute("""
                        INSERT INTO tracked_stories (
                            story_key, headline, first_seen, last_updated, episode_count, story_summary, channel_key, status
                        ) VALUES (?, ?, ?, ?, 1, ?, ?, 'active')
                    """, (story_key, article.get("title", ""), time.time(), time.time(), script[:500], channel_profile.key))

            conn.commit()
            conn.close()
            print(f"[DB Config] Configuration saved successfully for run {RUN_ID} ({fmt})")
        except Exception as db_err:
            print(f"[DB Config Error]: {db_err}")

    except Exception as e:
        print(f"\n[ERROR] Video build failed: {e}")
        _update_run_stage(RUN_ID, channel_profile.key, args.category, args.format, "failed", "failed")
        sys.exit(1)

    # ── Auto-Upload to YouTube ────────────────────────────────────────────────
    if AUTO_UPLOAD and output_path and os.path.isfile(output_path):
        print(f"\n[Auto-Upload] AUTO_UPLOAD is enabled — preparing upload for {channel_profile.key}...")
        try:
            from youtube_uploader import upload_video as _yt_upload, get_geo_scheduled_upload_time
            safe_pub_time = None
            try:
                # Resolve primary country code for scheduling
                prim_loc = pipeline_meta.get("primary_location", "")
                
                def resolve_country_code(location: str) -> str | None:
                    if not location:
                        return None
                    loc = location.lower().strip()
                    if any(x in loc for x in ["india", "delhi", "mumbai", "bengaluru", "kolkata", "chennai"]):
                        return "IN"
                    if any(x in loc for x in ["united states", "us", "u.s.", "washington", "new york", "america"]):
                        return "US"
                    if any(x in loc for x in ["united kingdom", "uk", "u.k.", "london", "great britain", "gb"]):
                        return "GB"
                    if any(x in loc for x in ["canada", "toronto", "vancouver", "ottawa"]):
                        return "CA"
                    if any(x in loc for x in ["australia", "sydney", "melbourne", "canberra"]):
                        return "AU"
                    if any(x in loc for x in ["france", "paris"]):
                        return "GB"
                    return None

                country_code = resolve_country_code(prim_loc)
                if not country_code:
                    if "india" in channel_profile.key:
                        country_code = "IN"
                    else:
                        country_code = "US"

                safe_pub_time = get_geo_scheduled_upload_time(channel_profile.key, country=country_code)
                print(f"[Auto-Upload] Calculated geo-targeted scheduled publish time for country '{country_code}': {safe_pub_time}")
            except Exception as sched_err:
                print(f"[Auto-Upload] Safe scheduling check failed: {sched_err}. Uploading as private immediately.")

            _yt_meta = generate_youtube_metadata(article, scenes, _pipeline_context, script, channel_profile=channel_profile)
            _yt_tags = ", ".join([h.lstrip("#") for h in _yt_meta.get("hashtags", [])])
            _yt_tags += f", news, {channel_profile.display_name.lower()}, breaking news"
            _yt_upload(
                run_id        = RUN_ID,
                channel_key   = channel_profile.key,
                video_path    = output_path,
                title         = _yt_meta["title"],
                description   = _yt_meta["description"],
                tags          = _yt_tags,
                category_id   = AUTO_UPLOAD_CATEGORY_ID,
                privacy_status= AUTO_UPLOAD_PRIVACY,
                publish_time  = safe_pub_time,
            )
        except Exception as _yt_err:
            print(f"[Auto-Upload] ❌ Upload failed: {_yt_err}")
    elif AUTO_UPLOAD:
        print("[Auto-Upload] Skipped — no output video file found.")
    else:
        print("[Auto-Upload] Disabled. Set AUTO_UPLOAD=true (env) or edit config.py to enable.")

    return _pipeline_context


def main():
    parser = argparse.ArgumentParser(description="AI News-to-Video Generator")
    parser.add_argument("--stage",   choices=["news", "script", "scenes", "assets", "video"])
    parser.add_argument("--skip-to", choices=["script", "scenes", "assets", "video"])
    parser.add_argument("--test-mode",     action="store_true")
    parser.add_argument("--no-clean",      action="store_true")
    parser.add_argument("--reset-memory",  action="store_true")
    parser.add_argument("--channel",      choices=["newscup", "newscup_india"], default="newscup")
    parser.add_argument("--category",     default="general")
    parser.add_argument("--format",       choices=["short", "long", "both"], default="both")
    parser.add_argument(
        "--video-style",
        choices=["briefing", "context", "tracker", "compilation"],
        default="briefing",
        help="Video format style override"
    )
    parser.add_argument("--upload-spacing", type=int, help="Upload spacing between videos in minutes")
    parser.add_argument("--upload-jitter-min", type=int, help="Minimum upload scheduling jitter in minutes")
    parser.add_argument("--upload-jitter-max", type=int, help="Maximum upload scheduling jitter in minutes")
    args = parser.parse_args()

    if args.upload_spacing is not None:
        import config
        config.UPLOAD_SPACING_MINUTES = args.upload_spacing
    if args.upload_jitter_min is not None:
        import config
        config.UPLOAD_JITTER_MIN = args.upload_jitter_min
    if args.upload_jitter_max is not None:
        import config
        config.UPLOAD_JITTER_MAX = args.upload_jitter_max

    if args.video_style == "compilation" and args.format == "short":
        print("[PIPELINE] WARNING: Compilation style is not supported for short format (shorts must be single-story). Switching video-style to 'briefing'.")
        args.video_style = "briefing"

    _pipeline_context = "neutral"
    channel_profile = get_channel_profile(args.channel)

    _memory_path  = os.path.join(OUTPUT_DIR, "used_topics.json")
    _topic_memory = None
    if not args.reset_memory and os.path.exists(_memory_path):
        try:
            with open(_memory_path, "r", encoding="utf-8") as _mf:
                _topic_memory = _mf.read()
        except Exception:
            _topic_memory = None

    if not args.no_clean and not args.skip_to:
        if os.path.exists(OUTPUT_DIR):
            import stat
            def _safe_rm(action, path, exc):
                try:
                    os.chmod(path, stat.S_IWRITE)
                    action(path)
                except Exception:
                    pass
            try:
                shutil.rmtree(OUTPUT_DIR, onerror=_safe_rm)
            except Exception:
                pass
        os.makedirs(AUDIO_DIR, exist_ok=True)
        os.makedirs(IMAGE_DIR, exist_ok=True)
        if _topic_memory:
            with open(_memory_path, "w", encoding="utf-8") as _mf:
                _mf.write(_topic_memory)
        print("[SYSTEM] Output directory reset -- fresh run enabled")
    else:
        os.makedirs(AUDIO_DIR, exist_ok=True)
        os.makedirs(IMAGE_DIR, exist_ok=True)
        print("[SYSTEM] Using existing output directory")

    RUN_ID = str(uuid.uuid4())[:8]
    _update_run_stage(RUN_ID, channel_profile.key, args.category, args.format, "news", "running")
    print(f"[RUN ID]: {RUN_ID}")
    print("=" * 60)
    print("  AI News-to-Video Generator")
    print("=" * 60)
    print(f"[PIPELINE] Initializing run {RUN_ID}")
    print(f"[CHANNEL] {channel_profile.display_name} | Language: {channel_profile.language_label}")

    # ── Stage 1: News ────────────────────────────────────────────────────────
    article = None
    if args.skip_to in ["script", "scenes", "assets", "video"]:
        article = load_cache("article.json")
        if article:
            print("\n[SKIP] Loading cached article...")

    if not article:
        if args.video_style == "compilation":
            if args.test_mode:
                print("\n[1/5] Using mock compilation news data...")
                mock_path = os.path.join(os.path.dirname(__file__), "tests", "mock_article.json")
                with open(mock_path, "r") as f:
                    article_data = json.load(f)
                compilation_articles = [article_data] * 3
            else:
                print("\n[1/5] Fetching top 3 news stories for compilation...")
                from news_fetcher import fetch_top_articles
                compilation_articles = fetch_top_articles(category=args.category, channel=channel_profile.key, limit=3)
            
            # Create a synthetic article dictionary to cache
            article = {
                "title": f"Compilation: {', '.join([a.get('title', '') for a in compilation_articles])}",
                "link": compilation_articles[0].get("link") if compilation_articles else "",
                "summary": "Multi-story compilation video.",
                "full_article_text": "\n\n".join([a.get("full_article_text") or "" for a in compilation_articles]),
                "_compilation_articles": compilation_articles,
                "verification_score": 100,
                "cross_sources": []
            }
        else:
            if args.test_mode:
                print("\n[1/5] Using mock news data...")
                mock_path = os.path.join(os.path.dirname(__file__), "tests", "mock_article.json")
                with open(mock_path, "r") as f:
                    article = json.load(f)
            else:
                print("\n[1/5] Fetching latest news...")
                article = fetch_latest_article(category=args.category, channel=channel_profile.key)

        if "_source_name" not in article:
            article["_source_name"] = "World News"
        article["_channel_key"] = channel_profile.key
        article["_channel_name"] = channel_profile.display_name
        article["_language"] = channel_profile.language
        save_cache(article, "article.json")

    if args.stage == "news":
        return

    # ── Stages 2–5 ───────────────────────────────────────────────────────────
    _formats_to_run = ["short", "long"] if args.format == "both" else [args.format]
    for _fmt in _formats_to_run:
        _pipeline_context = run_format_pipeline(_fmt, article, args, RUN_ID, _pipeline_context)

    _update_run_stage(RUN_ID, channel_profile.key, args.category, args.format, "complete", "success")
    print("\n[PIPELINE] All formats complete. Exiting.")


if __name__ == "__main__":
    main()
