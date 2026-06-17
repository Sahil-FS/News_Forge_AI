"""
utils.py — Shared utility functions for the AI News-to-Video Generator pipeline.
"""

import re
import html as _html_entities

def clean_caption_text(text: str) -> str:
    """
    Cleans raw caption/script text:
    - Strips HTML tags (FIRST)
    - Unescapes HTML entities
    - Strips bare URLs (http/https) and www. URLs
    - Strips URL slug artifacts (hyphenated lowercase chains)
    - Removes ANSI escape codes
    - Removes dimension artifacts (digits followed by uppercase letters)
    - Preserves Devanagari and non-ASCII scripts (does NOT strip non-ASCII)
    - Normalizes whitespace
    - Returns cleaned string
    """
    if not text:
        return ""

    # STEP 0: Strip HTML tags (must be FIRST — before other patterns)
    text = re.sub(r'<[^>]+>', ' ', text, flags=re.DOTALL)
    text = _html_entities.unescape(text)

    # STEP 1: Strip bare URLs
    text = re.sub(r'https?://\S+', ' ', text)
    text = re.sub(r'www\.\S+', ' ', text)

    # STEP 2: Strip URL slug artifacts
    text = re.sub(r'\b[a-z]+-[a-z]+-[a-z]+-[a-z]+(?:-[a-z]+)*\b', ' ', text)

    # STEP 3: Remove ANSI escape codes
    text = re.sub(r'\x1B\[[0-?]*[ -/]*[@-~]', '', text)

    # STEP 4: Remove dimension artifacts (digits followed by uppercase letters, e.g. 1080P, 4K)
    text = re.sub(r'\b\d+[A-Z]\b', '', text)

    # STEP 5: Normalize whitespace and strip (keeps Devanagari/Hindi scripts)
    text = re.sub(r'\s+', ' ', text).strip()

    return text
