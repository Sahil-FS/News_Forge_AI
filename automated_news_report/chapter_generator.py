#!/usr/bin/env python3
"""
chapter_generator.py — YouTube chapter timestamps + metadata exporter.
Works for both short-form (scene-count-based) and long-form (section-label-based).

FIX: SECTION_LABELS is now defined locally — no longer imported from
long_form_script_generator (which never exported it), eliminating the
ImportError that silently skipped chapter generation every run.
"""

import os
import re
from moviepy.audio.io.AudioFileClip import AudioFileClip

try:
    from config import CHANNEL_NAME
except ImportError:
    CHANNEL_NAME = "AI News"

# Section labels in canonical order (used for long-form chapter ordering)
SECTION_LABELS = [
    "COLD_OPEN",
    "SITUATION",
    "BACKGROUND",
    "KEY_PLAYERS",
    "WHAT_NEXT",
    "OUTRO",
]

# Section → human-readable chapter title
SECTION_DISPLAY_NAMES = {
    "COLD_OPEN":   "Introduction",
    "SITUATION":   "What Happened",
    "BACKGROUND":  "Background & Context",
    "KEY_PLAYERS": "Key Players",
    "WHAT_NEXT":   "What Happens Next",
    "OUTRO":       "Follow This Story",
}


# ─── Helpers ────────────────────────────────────────────────────────────────

def _format_timestamp(seconds: float) -> str:
    """
    Format seconds as YouTube-compatible timestamp.
    YouTube requires M:SS format (no leading zero on minutes).
    '0:00', '1:23', '10:05' — NOT '00:00' or '01:23'.
    """
    total_s = max(0, int(seconds))
    mins    = total_s // 60
    secs    = total_s % 60
    return f"{mins}:{secs:02d}"


def _scene_audio_duration(scene: dict) -> float:
    """
    Get real audio duration for a scene.
    Falls back to word-count estimate if audio file is missing.
    """
    audio_path = scene.get("audio_path")
    if audio_path and os.path.isfile(audio_path):
        try:
            ac  = AudioFileClip(audio_path)
            dur = ac.duration
            ac.close()
            return max(1.0, dur + 0.20)
        except Exception:
            pass

    text  = scene.get("text", "")
    words = len(text.split()) if text else 5
    return max(2.0, words / 2.5)


def _clean_hashtag(token: str) -> str:
    """Remove spaces, apostrophes, dashes, 'The' prefix, possessive s."""
    token = re.sub(r"^[Tt]he\s+", "", token)
    token = re.sub(r"'s$", "", token)
    token = re.sub(r"['\s\-]+", "", token)
    return token.strip()


_SHORT_LOCATION_HASHTAGS = {
    "democratic republic of congo": "DRCongo",
    "the democratic republic of the congo": "DRCongo",
    "united states": "USA",
    "united states of america": "USA",
    "united kingdom": "UK",
    "united arab emirates": "UAE",
    "north korea": "NorthKorea",
    "south korea": "SouthKorea",
    "saudi arabia": "SaudiArabia",
    "south africa": "SouthAfrica",
    "new zealand": "NewZealand",
    "costa rica": "CostaRica",
    "sri lanka": "SriLanka",
}


# ─── Core API ────────────────────────────────────────────────────────────────

def calculate_section_durations(scenes: list) -> dict:
    """
    Calculate total audio duration per section.
    Used by long_form_video_builder to compute chapter timestamps.
    """
    durations: dict[str, float] = {}
    for scene in scenes:
        section = scene.get("section", "SITUATION")
        dur     = _scene_audio_duration(scene)
        durations[section] = durations.get(section, 0.0) + dur
    return durations


def generate_chapters(section_durations: dict) -> str:
    """
    Generate YouTube chapter markers string from section durations.
    Uses locally defined SECTION_LABELS — no external import needed.

    Returns formatted chapter string ready to paste into YouTube description.
    """
    lines        = []
    current_time = 0.0

    for section in SECTION_LABELS:
        dur = section_durations.get(section, 0.0)
        if dur <= 0.0:
            continue
        name = SECTION_DISPLAY_NAMES.get(section, section.title())
        lines.append(f"{_format_timestamp(current_time)} {name}")
        current_time += dur

    return "\n".join(lines)


def generate_chapters_and_metadata(
    scenes: list,
    headline: str,
    output_dir: str,
    mode: str = "auto",
    pipeline_meta: dict = None,
) -> str:
    """
    Generate YouTube chapters and write metadata to video_metadata.txt.

    Mode selection:
    - "auto"    → uses section labels if present, falls back to count-based
    - "section" → always use scene['section'] labels (long-form)
    - "count"   → always use scene-count ratio logic (short-form)

    Returns path to written metadata file.
    """
    os.makedirs(output_dir, exist_ok=True)
    metadata_path = os.path.join(output_dir, "video_metadata.txt")

    # ── 1. Detect mode ────────────────────────────────────────────────────────
    _has_sections = any(s.get("section") for s in scenes)

    if mode == "auto":
        use_sections = _has_sections
    elif mode == "section":
        use_sections = True
    else:
        use_sections = False

    # ── 2. Build chapter timestamps ───────────────────────────────────────────
    timestamps: list[str] = []
    cumulative_time       = 0.0

    if use_sections:
        last_section = None
        for scene in scenes:
            section = scene.get("section", "SITUATION")
            if section != last_section:
                name = SECTION_DISPLAY_NAMES.get(section, section.title())
                timestamps.append(f"{_format_timestamp(cumulative_time)} {name}")
                last_section = section
            cumulative_time += _scene_audio_duration(scene)

    else:
        num_scenes = len(scenes)

        for idx, scene in enumerate(scenes):
            chapter_title = None

            if idx == 0:
                chapter_title = "Introduction"
            elif num_scenes >= 12:
                if idx == int(num_scenes * 0.25):
                    chapter_title = "Background Context"
                elif idx == int(num_scenes * 0.50):
                    chapter_title = "Key Developments"
                elif idx == int(num_scenes * 0.75):
                    chapter_title = "Official Response"
                elif idx == num_scenes - 1:
                    chapter_title = "Future Outlook"
            else:
                if idx == int(num_scenes * 0.35):
                    chapter_title = "Detailed Story"
                elif idx == int(num_scenes * 0.70):
                    chapter_title = "Official Statements"
                elif idx == num_scenes - 1:
                    chapter_title = "Conclusion"

            if chapter_title:
                timestamps.append(f"{_format_timestamp(cumulative_time)} {chapter_title}")

            cumulative_time += _scene_audio_duration(scene)

    if timestamps and not timestamps[0].startswith("0:00"):
        timestamps.insert(0, "0:00 Introduction")

    # ── 3. Build hashtags ─────────────────────────────────────────────────────
    _channel_tag = "#" + _clean_hashtag(CHANNEL_NAME)
    hashtags     = {"#BreakingNews", "#News", _channel_tag}

    for scene in scenes:
        entities = scene.get("entities") or {}

        country = entities.get("country_context", "") or ""
        org     = entities.get("org", "") or ""
        person  = entities.get("primary_person", "") or ""

        if country:
            _key = country.lower().strip()
            _tag = _SHORT_LOCATION_HASHTAGS.get(_key, _clean_hashtag(country))
            if _tag and 2 <= len(_tag) <= 20:
                hashtags.add(f"#{_tag}")

        if org and len(org.split()) <= 2:
            _org_tag = _clean_hashtag(org)
            if _org_tag and 2 <= len(_org_tag) <= 20:
                hashtags.add(f"#{_org_tag}")

        if person:
            _surname = person.split()[-1] if person.split() else ""
            _surname = _clean_hashtag(_surname)
            if _surname and len(_surname) >= 3:
                hashtags.add(f"#{_surname}")

    hashtag_list = sorted(hashtags)[:10]

    # ── 4. Build description ──────────────────────────────────────────────────
    _summary_sentences = []
    for s in scenes[:3]:
        t = s.get("text", "").strip()
        if t and t not in _summary_sentences:
            _summary_sentences.append(t)
    summary_paragraph = " ".join(_summary_sentences)

    # ── 5. Append long-form chapters from pipeline_meta if available ──────────
    lf_chapters_block = ""
    if pipeline_meta and pipeline_meta.get("long_form_chapters"):
        lf_chapters_block = (
            "\n\n=== LONG-FORM VIDEO CHAPTERS ===\n"
            + pipeline_meta["long_form_chapters"]
        )

    # ── 6. Write metadata file ────────────────────────────────────────────────
    metadata_content = "\n".join([
        f"TITLE: {headline}",
        "",
        "=== DESCRIPTION ===",
        f"{headline}",
        "",
        summary_paragraph,
        "",
        "Stay informed — subscribe for daily breaking news coverage.",
        "",
        " ".join(hashtag_list),
        "",
        "=== CHAPTERS ===",
        "\n".join(timestamps) if timestamps else "(no chapters generated)",
        lf_chapters_block,
    ])

    with open(metadata_path, "w", encoding="utf-8") as f:
        f.write(metadata_content)

    print(f"[ChapterGen] Metadata exported -> {metadata_path}")
    print(f"[ChapterGen] {len(timestamps)} chapters | {len(hashtag_list)} hashtags | mode={'section' if use_sections else 'count'}")
    return metadata_path