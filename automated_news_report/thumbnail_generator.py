#!/usr/bin/env python3
# thumbnail_generator.py -- PREMIUM News thumbnail compositor (v3)
#
# UPGRADED to produce Firstpost / NDTV Profit-level professional thumbnails:
#   - Cinematic background with heavy vignette + colour-grade
#   - Giant 2–3 word punchy headline in a solid colour-blocked bar (bottom 30%)
#   - Anchor cutout on RIGHT with a semi-transparent dark side panel + brand logo
#   - "4K ULTRA HD" badge top-left for authority signal
#   - Red/yellow accent typography: first line white, impact word line gold/yellow
#   - Thin coloured rule under headline bar to separate from background
#   - Portrait (9:16) and Landscape (16:9) variants share the same DNA

import os
import numpy as _np
from PIL import (
    Image as _PI,
    ImageDraw as _PID,
    ImageFont as _PIF,
    ImageFilter as _PIFilt,
    ImageEnhance as _PIE,
)
from config import (
    BASE_DIR,
    BRAND_LOGO_PATH, BRAND_FONT_PATH,
)

# ── Colour palette (Firstpost-inspired) ──────────────────────────────────────
_HEADLINE_BG       = (10, 14, 26)           # Very dark navy
_HEADLINE_ACCENT   = (220, 30,  30)         # Bright red
_HEADLINE_YELLOW   = (255, 210,  0)         # High-vis yellow / gold
_HEADLINE_WHITE    = (255, 255, 255)
_PANEL_DARK        = (8,  10,  18, 200)     # Right-panel backing (RGBA)
_VIGNETTE_DARK     = (0,  0,   0)


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_font(size: int, bold: bool = True, font_path: str = None) -> _PIF.FreeTypeFont:
    """Load brand font with cross-platform fallback."""
    candidates_bold = [
        font_path,
        BRAND_FONT_PATH,
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/calibrib.ttf",
        "C:/Windows/Fonts/impact.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
    ]
    candidates_reg = [
        BRAND_FONT_PATH,
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibri.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/Library/Fonts/Arial.ttf",
    ]
    for path in (candidates_bold if bold else candidates_reg):
        if path and os.path.isfile(path):
            try:
                return _PIF.truetype(path, size)
            except Exception:
                pass
    return _PIF.load_default()


def _load_anchor_keyed(target_h: int, target_w: int = None) -> _PI.Image | None:
    return None


def _load_logo_image(size: int) -> _PI.Image | None:
    """Load News Cup logo, key black bg, resize to `size` px square."""
    if not os.path.isfile(BRAND_LOGO_PATH):
        return None
    try:
        logo = _PI.open(BRAND_LOGO_PATH).convert("RGB")
        logo = logo.resize((size, size), _PI.Resampling.LANCZOS)
        arr  = _np.array(logo).astype(_np.float32)
        lum  = arr[:, :, 0] * 0.299 + arr[:, :, 1] * 0.587 + arr[:, :, 2] * 0.114
        alpha = _np.clip((lum - 15) / 50.0, 0.0, 1.0)
        alpha = (alpha * 255).astype(_np.uint8)
        rgba  = _np.dstack([arr.astype(_np.uint8), alpha])
        return _PI.fromarray(rgba, "RGBA")
    except Exception as e:
        print(f"[ThumbnailGen] Logo load failed: {e}")
        return None


def _scale_and_crop(img: _PI.Image, target_w: int, target_h: int) -> _PI.Image:
    """Cover-scale and center-crop to exact dimensions."""
    bg_w, bg_h = img.size
    scale = max(target_w / bg_w, target_h / bg_h)
    new_w = int(bg_w * scale)
    new_h = int(bg_h * scale)
    img   = img.resize((new_w, new_h), _PI.Resampling.LANCZOS)
    left  = (new_w - target_w) // 2
    top   = (new_h - target_h) // 2
    return img.crop((left, top, left + target_w, top + target_h))


def _cinematic_grade(img: _PI.Image) -> _PI.Image:
    """
    Boost saturation, contrast & warmth — makes any news photo look
    dramatic and cinematic (like broadcast thumbnails).
    """
    img = _PIE.Color(img).enhance(1.45)       # vivid colour
    img = _PIE.Contrast(img).enhance(1.30)    # punchy blacks
    img = _PIE.Brightness(img).enhance(0.92)  # slightly darker overall
    img = _PIE.Sharpness(img).enhance(1.20)   # crisp details
    return img


def _apply_vignette(img: _PI.Image, strength: float = 0.80) -> _PI.Image:
    """Apply a radial dark vignette around the edges."""
    w, h = img.size
    # Build a radial gradient mask
    cx, cy = w / 2, h / 2
    radius = max(w, h) * 0.72
    mask_arr = _np.zeros((h, w), dtype=_np.float32)
    ys, xs = _np.mgrid[0:h, 0:w]
    dist = _np.sqrt(((xs - cx) / (w * 0.5)) ** 2 + ((ys - cy) / (h * 0.5)) ** 2)
    mask_arr = _np.clip((dist - 0.55) / 0.65, 0.0, 1.0) ** 1.8 * strength
    vignette = (mask_arr * 255).astype(_np.uint8)
    vign_img = _PI.fromarray(vignette, "L").resize((w, h), _PI.Resampling.BILINEAR)
    dark = _PI.new("RGB", (w, h), (0, 0, 0))
    img  = _PI.composite(dark, img, vign_img)
    return img


def _draw_text_shadow(
    draw: _PID.ImageDraw,
    pos: tuple,
    text: str,
    font,
    fill: tuple,
    shadow_color: tuple = (0, 0, 0),
    shadow_offset: int = 4,
    anchor: str = None,
) -> None:
    """Draw text with a soft drop-shadow."""
    x, y = pos
    kw = dict(font=font)
    if anchor:
        kw["anchor"] = anchor
    # Shadow
    for ox in range(-shadow_offset, shadow_offset + 1, 2):
        for oy in range(-shadow_offset, shadow_offset + 1, 2):
            draw.text((x + ox, y + oy), text, fill=shadow_color + (180,), **kw)
    draw.text((x, y), text, fill=fill, **kw)


def _draw_text_with_outline(
    draw, pos, text, font, fill,
    outline_color=(0, 0, 0), outline_width=5, anchor=None,
) -> None:
    """Thick outline for maximum legibility on any background."""
    x, y = pos
    kw = dict(font=font)
    if anchor:
        kw["anchor"] = anchor
    for dx in range(-outline_width, outline_width + 1):
        for dy in range(-outline_width, outline_width + 1):
            if dx == 0 and dy == 0:
                continue
            draw.text((x + dx, y + dy), text, fill=outline_color, **kw)
    draw.text((x, y), text, fill=fill, **kw)


def _pick_best_thumbnail_image(
    scenes: list,
    main_image_path: str | None,
    prefer_index: int = 1,
) -> str | None:
    """Pick the strongest news image for a thumbnail."""
    def _is_anchor_image(path: str) -> bool:
        if not path:
            return True
        basename = os.path.basename(path).lower()
        return "anchor" in basename or "virtual_anchor" in basename

    def _image_score(path: str) -> int:
        if not path or not os.path.isfile(path) or _is_anchor_image(path):
            return -1
        try:
            return os.path.getsize(path) // 1024
        except Exception:
            return 0

    candidates = []
    if scenes:
        for idx, scene in enumerate(scenes):
            img = scene.get("image_path", "")
            if img and os.path.isfile(img) and not _is_anchor_image(img):
                candidates.append((idx, img, _image_score(img)))

    if not candidates:
        if main_image_path and os.path.isfile(main_image_path) and not _is_anchor_image(main_image_path):
            return main_image_path
        placeholder = os.path.join(BASE_DIR, "assets", "placeholder.jpg")
        return placeholder if os.path.isfile(placeholder) else None

    for idx, img, score in candidates:
        if idx == prefer_index and score > 0:
            return img

    candidates.sort(key=lambda x: x[2], reverse=True)
    return candidates[0][1] if candidates else None


def _smart_headline_split(headline: str) -> tuple[str, str]:
    """
    Intelligently splits the headline into (context_line, impact_line)
    so that high-impact words/phrases are kept together on the impact line.
    """
    # Clean headline and split into words
    clean_headline = headline.replace("'", "").replace('"', "").replace("`", "")
    words = clean_headline.upper().split()
    total = len(words)
    
    if total <= 4:
        return ("", " ".join(words))
    
    # Define impact weights
    _HIGH_IMPACT = {
        "STRIKES", "ATTACKS", "WAR", "KILLS", "DEAD", "EXPLOSION", "BOMB", "DRONE",
        "MISSILE", "AIRSTRIKE", "FIGHTING", "CLASHES", "VIOLENCE", "CRISIS", "DISASTER",
        "FIRE", "CRASH", "CEASEFIRE", "BREACH", "VIOLATION", "CONDEMNS", "WARNING",
        "WARNS", "ALERT", "THREATENS", "THREAT", "ATTACKED", "KILLED", "MURDER",
        "ABDUCTION", "BREACHING", "DEATHS", "BOMBING", "EXPLODED", "FIGHT", "FIGHTERS",
        "MILITARY", "FORCES", "TROOPS", "SOLDIERS", "COMMANDER", "RESIST", "RESISTANCE",
        "IRAN", "US", "RUSSIA", "UKRAINE", "ISRAEL", "GAZA", "HAMAS", "CHINA", "TAIWAN",
        "USA", "UK", "UN", "NATO", "PENTAGON", "YEMEN", "SYRIA", "IRAQ", "LEBANON",
    }
    
    _MODIFIERS = {
        "GROSS", "MASSIVE", "SEVERE", "BRUTAL", "SHOCKING", "ILLEGAL", "CRITICAL",
        "DEADLY", "MAJOR", "HISTORIC", "UNPRECEDENTED", "EXTREME", "TOTAL", "DIRECT",
        "SUDDEN", "NEW", "LATEST", "URGENT", "SERIOUS", "HEAVY", "VIOLENT", "LARGE",
    }
    
    _IMPACT_BIGRAMS = {
        ("GROSS", "VIOLATION"),
        ("US", "STRIKES"),
        ("AIR", "STRIKES"),
        ("DRONE", "ATTACK"),
        ("DRONE", "STRIKES"),
        ("MISSILE", "ATTACK"),
        ("MISSILE", "STRIKES"),
        ("CEASEFIRE", "VIOLATION"),
        ("WAR", "ZONE"),
        ("WHITE", "HOUSE"),
        ("NUCLEAR", "PLANT"),
        ("MILITARY", "WING"),
        ("GAZA", "CITY"),
        ("DEATH", "TOLL"),
        ("WAR", "UPDATE"),
        ("BREAKING", "NEWS"),
    }

    # Evaluate all possible split points k where the suffix has between 2 and 5 words
    best_k = total // 2
    best_score = -999999
    
    min_suffix_len = max(2, total // 4)
    max_suffix_len = min(5, max(3, total // 2 + 1))
    
    for k in range(total - max_suffix_len, total - min_suffix_len + 1):
        if k <= 0 or k >= total:
            continue
        
        suffix = words[k:]
        
        # Calculate impact score of the suffix
        score = 0
        for w in suffix:
            w_clean = w.rstrip(",.;:!?")
            if w_clean in _HIGH_IMPACT:
                score += 15
            elif w_clean in _MODIFIERS:
                score += 10
            elif w_clean in {"AS", "OF", "THE", "AND", "IN", "A", "AN", "TO", "IS", "ARE", "FOR", "AT", "ON", "WITH", "BY", "FROM"}:
                score -= 5
            else:
                score += 2  # generic word
        
        # Penalty for splitting a bigram
        prev_word = words[k-1].rstrip(",.;:!?")
        curr_word = words[k].rstrip(",.;:!?")
        if (prev_word, curr_word) in _IMPACT_BIGRAMS:
            score -= 150
            
        # Penalty for splitting after a modifier
        if prev_word in _MODIFIERS:
            score -= 100
            
        # Preference for splitting after prepositions or conjunctions
        if prev_word in {"AS", "OF", "FOR", "IN", "ON", "AT", "TO", "WITH", "BY", "AND", "BUT", "OR"}:
            score += 20
            
        # Balanced length preference
        pref_len = 3.5
        len_diff = abs(len(suffix) - pref_len)
        score -= len_diff * 10
        
        if score > best_score:
            best_score = score
            best_k = k
            
    return (" ".join(words[:best_k]), " ".join(words[best_k:]))


_HIGHLIGHT_WORDS = {
    # High impact nouns/verbs
    "STRIKES", "ATTACKS", "WAR", "KILLS", "DEAD", "EXPLOSION", "BOMB", "DRONE",
    "MISSILE", "AIRSTRIKE", "FIGHTING", "CLASHES", "VIOLENCE", "CRISIS", "DISASTER",
    "FIRE", "CRASH", "CEASEFIRE", "BREACH", "VIOLATION", "CONDEMNS", "WARNING",
    "WARNS", "ALERT", "THREATENS", "THREAT", "ATTACKED", "KILLED", "MURDER",
    "ABDUCTION", "BREACHING", "DEATHS", "BOMBING", "EXPLODED", "FIGHT", "FIGHTERS",
    "MILITARY", "FORCES", "TROOPS", "SOLDIERS", "COMMANDER", "RESIST", "RESISTANCE",
    # Countries and entities
    "IRAN", "US", "RUSSIA", "UKRAINE", "ISRAEL", "GAZA", "HAMAS", "CHINA", "TAIWAN",
    "USA", "UK", "UN", "NATO", "PENTAGON", "YEMEN", "SYRIA", "IRAQ", "LEBANON",
    # Modifiers
    "GROSS", "MASSIVE", "SEVERE", "BRUTAL", "SHOCKING", "ILLEGAL", "CRITICAL",
    "DEADLY", "MAJOR", "HISTORIC", "UNPRECEDENTED", "EXTREME", "TOTAL", "DIRECT",
    "SUDDEN", "NEW", "LATEST", "URGENT", "SERIOUS", "HEAVY", "VIOLENT", "LARGE",
    # More common news and business terms
    "WORLD", "GLOBAL", "POLITICS", "ELECTION", "PRESIDENT", "MINISTER", "GOVERNMENT",
    "COURT", "SUPREME", "POLICE", "ARRESTED", "ARREST", "ACCUSED", "CLASH", "RIOT",
    "RIOTS", "PROTEST", "PROTESTS", "TERROR", "TERRORIST", "TERRORISM", "ATTACKER",
    "ATTACKERS", "SANCTIONS", "TALKS", "DEAL", "SUMMIT", "TREATY", "BORDER", "SECURITY",
    "SPY", "SPYING", "INTELLIGENCE", "NAVY", "ARMY", "AIRFORCE", "NUCLEAR", "WEAPONS",
    "WEAPON", "BILLION", "MILLION", "MARKET", "STOCKS", "FALLS", "SURGES", "CRASHES",
    "RISE", "DROP", "BOOST", "PROFIT", "LOSS", "ECONOMY", "INFLATION", "RATE", "REVENUE",
    "DEBT", "TAX", "TRADE", "TARIFF", "TECH", "AI", "CHIPS", "SEMICONDUCTOR", "APPLE",
    "GOOGLE", "MICROSOFT", "NVIDIA", "TESLA", "CEO", "FOUNDER", "LAUNCH", "LAUNCHES",
    "REVEALS", "UNVEILS"
}


def _find_optimal_font_size_uniform(
    draw,
    headline: str,
    max_w: int,
    max_h: int,
    height: int,
) -> tuple[int, list[str]]:
    """
    Find the largest uniform font size that fits the entire headline within max_w and max_h.
    Returns (font_size, wrapped_lines).
    """
    max_sz = int(height * 0.14)  # Large size cap
    min_sz = int(height * 0.055) # Minimum size limit
    
    optimal_sz = min_sz
    best_lines = []

    # Try font sizes from largest to smallest
    for sz in range(max_sz, min_sz - 1, -2):
        font = _load_font(sz)
        
        # Wrap the full headline as a single block
        wrapped = _wrap_text(draw, headline, font, max_w, max_lines=3)
        
        # Calculate height
        lh = sz + 8
        total_text_h = len(wrapped) * lh + 10
        
        # Check if it fits within max_h
        if total_text_h <= max_h:
            # Verify no individual line overflows max_w
            fits = True
            for line in wrapped:
                if draw.textlength(line, font=font) > max_w:
                    fits = False
                    break
            
            if fits:
                optimal_sz = sz
                best_lines = wrapped
                break
    else:
        # Fallback to minimum size
        font = _load_font(min_sz)
        best_lines = _wrap_text(draw, headline, font, max_w, max_lines=3)

    return optimal_sz, best_lines


def _draw_colored_line(
    draw,
    pos: tuple[int, int],
    line_text: str,
    font,
    default_color: tuple[int, int, int],
    highlight_color: tuple[int, int, int],
    highlight_words: set[str],
    anchor: str = "mt",
    outline_color: tuple[int, int, int] = (0, 0, 0),
    outline_width: int = 4,
):
    """Draw text word-by-word with specific highlights and outline."""
    words = line_text.split()
    if not words:
        return
    word_data = []
    total_w = 0
    space_w = draw.textlength(" ", font=font)
    for i, w in enumerate(words):
        w_clean = w.strip(",.;:!?\"'").upper()
        color = highlight_color if w_clean in highlight_words else default_color
        w_width = draw.textlength(w, font=font)
        word_data.append((w, color, w_width))
        total_w += w_width
        if i < len(words) - 1:
            total_w += space_w
            
    x, y = pos
    if anchor == "mt":
        curr_x = x - total_w / 2
    else:
        curr_x = x
        
    for w, color, w_width in word_data:
        # Draw outline
        for dx in range(-outline_width, outline_width + 1):
            for dy in range(-outline_width, outline_width + 1):
                if dx == 0 and dy == 0:
                    continue
                draw.text((curr_x + dx, y + dy), w, fill=outline_color, font=font)
        # Draw text
        draw.text((curr_x, y), w, fill=color, font=font)
        curr_x += w_width + space_w



def _wrap_text(draw, text: str, font, max_width: int, max_lines: int = 3) -> list[str]:
    """Word-wrap text to fit within max_width pixels."""
    words = text.upper().split()
    lines, current = [], []
    for word in words:
        test = " ".join(current + [word])
        try:
            w = draw.textlength(test, font=font)
        except Exception:
            w = len(test) * 14
        if w > max_width and current:
            lines.append(" ".join(current))
            current = [word]
            if len(lines) >= max_lines - 1:
                remaining = " ".join([word] + words[words.index(word) + 1:])
                if len(remaining) > 38:
                    remaining = remaining[:35] + "…"
                lines.append(remaining)
                return lines[:max_lines]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return lines[:max_lines]


def _find_optimal_font_sizes(
    draw,
    context_line: str,
    impact_line: str,
    max_w: int,
    max_h: int,
    height: int,
) -> tuple[int, int, list[str], list[str]]:
    """
    Dynamically find the largest font sizes that fit the text within max_w and max_h.
    Returns (impact_sz, context_sz, wrapped_impact_lines, wrapped_context_lines).
    """
    max_impact_sz = int(height * 0.13)  # Large size cap
    min_impact_sz = int(height * 0.055) # Minimum size limit
    
    optimal_impact_sz = min_impact_sz
    optimal_context_sz = int(min_impact_sz * 0.55)
    best_impact_lines = []
    best_context_lines = []

    # Try font sizes from largest to smallest
    for impact_sz in range(max_impact_sz, min_impact_sz - 1, -2):
        context_sz = int(impact_sz * 0.55)
        
        # Load temporary fonts
        imp_font = _load_font(impact_sz)
        ctx_font = _load_font(context_sz)
        
        # Wrap the lines
        imp_wrapped = _wrap_text(draw, impact_line, imp_font, max_w, max_lines=2)
        ctx_wrapped = _wrap_text(draw, context_line, ctx_font, max_w, max_lines=2)
        
        # Calculate height
        imp_lh = impact_sz + 8
        ctx_lh = context_sz + 6
        total_text_h = len(imp_wrapped) * imp_lh + len(ctx_wrapped) * ctx_lh + 14
        
        # Check if it fits within max_h
        if total_text_h <= max_h:
            # Verify no individual line overflows max_w
            fits = True
            for line in imp_wrapped:
                if draw.textlength(line, font=imp_font) > max_w:
                    fits = False
                    break
            if fits:
                for line in ctx_wrapped:
                    if draw.textlength(line, font=ctx_font) > max_w:
                        fits = False
                        break
            
            if fits:
                optimal_impact_sz = impact_sz
                optimal_context_sz = context_sz
                best_impact_lines = imp_wrapped
                best_context_lines = ctx_wrapped
                break
    else:
        # Fallback to minimum sizes
        imp_font = _load_font(min_impact_sz)
        ctx_font = _load_font(optimal_context_sz)
        best_impact_lines = _wrap_text(draw, impact_line, imp_font, max_w, max_lines=2)
        best_context_lines = _wrap_text(draw, context_line, ctx_font, max_w, max_lines=2)

    return optimal_impact_sz, optimal_context_sz, best_impact_lines, best_context_lines


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def generate_thumbnails(
    headline: str,
    main_image_path: str,
    output_dir: str,
    scenes: list = None,
    format_mode: str = "both",
    context: str = "neutral",
    primary_color: str = None,
    accent_color: str = None,
    badge_color: str = None,
    font_family: str = None,
    video_style: str = "briefing",
    episode_number: int = 1,
) -> dict[str, str]:
    """
    Generate portrait (1080×1920) and landscape (1920×1080) premium thumbnails.

    Returns dict with keys "portrait" and/or "landscape".
    """
    os.makedirs(output_dir, exist_ok=True)
    results = {}
    scenes  = scenes or []

    portrait_path  = os.path.join(output_dir, "thumbnail_portrait.jpg")
    landscape_path = os.path.join(output_dir, "thumbnail_landscape.jpg")

    # ── Pick background images ─────────────────────────────────────────────
    portrait_bg_path  = _pick_best_thumbnail_image(scenes, main_image_path, prefer_index=2)
    landscape_bg_path = _pick_best_thumbnail_image(scenes, main_image_path, prefer_index=3)

    def _load_bg(path: str, w: int, h: int) -> _PI.Image:
        img = None
        if path and os.path.isfile(path):
            try:
                img = _PI.open(path).convert("RGB")
            except Exception:
                img = None
        if not img:
            placeholder = os.path.join(BASE_DIR, "assets", "placeholder.jpg")
            if os.path.isfile(placeholder):
                try:
                    img = _PI.open(placeholder).convert("RGB")
                except Exception:
                    pass
        if not img:
            img = _PI.new("RGB", (w, h), (13, 17, 35))
        return img

    if format_mode in ("short", "both"):
        portrait_bg  = _load_bg(portrait_bg_path, 1080, 1920)
        portrait_img = _compose_portrait(portrait_bg, headline, 1080, 1920, context,
                                         primary_color_hex=primary_color, accent_color_hex=accent_color,
                                         badge_color_hex=badge_color, font_family_path=font_family,
                                         video_style=video_style, episode_number=episode_number)
        portrait_img.save(portrait_path, "JPEG", quality=95, optimize=True)
        results["portrait"] = portrait_path
        print(f"[ThumbnailGen] OK Portrait -> {portrait_path}")

    if format_mode in ("long", "both"):
        landscape_bg  = _load_bg(landscape_bg_path, 1920, 1080)
        include_anchor = False
        landscape_img = _compose_landscape(landscape_bg, headline, 1920, 1080, include_anchor, context,
                                          primary_color_hex=primary_color, accent_color_hex=accent_color,
                                          badge_color_hex=badge_color, font_family_path=font_family,
                                          video_style=video_style, episode_number=episode_number)
        landscape_img.save(landscape_path, "JPEG", quality=95, optimize=True)
        results["landscape"] = landscape_path
        print(f"[ThumbnailGen] OK Landscape -> {landscape_path}")

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Portrait compositor  (1080 × 1920 — Shorts / mobile thumbnail)
# ─────────────────────────────────────────────────────────────────────────────

def hex_to_rgb(hex_str: str) -> tuple[int, int, int] | None:
    if not hex_str:
        return None
    hex_str = hex_str.lstrip('#')
    try:
        return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))
    except Exception:
        return None

def _compose_portrait(
    bg_image: _PI.Image,
    headline: str,
    width: int,
    height: int,
    context: str = "neutral",
    primary_color_hex: str = None,
    accent_color_hex: str = None,
    badge_color_hex: str = None,
    font_family_path: str = None,
    video_style: str = "briefing",
    episode_number: int = 1,
) -> _PI.Image:
    """
    Layout — Firstpost/CNN-style split portrait thumbnail:
      ┌────────────────────────────────────┐
      │ [LOGO]  [BADGE]          [● LIVE] │  ← dark top bar
      ├──────────────────────────────────┤
      │                   │ DARK STUDIO  │
      │   NEWS PHOTO       │   PANEL      │
      │   (left 60%)      │  (right 40%) │
      │   vignetted        │  ANCHOR      │
      │                   │  PHOTO       │
      ├───────────────────────────────────┤
      │ ██ CONTEXT LINE  (white)        ██│  ← headline band
      │ ██ IMPACT WORDS  (gold/yellow)  ██│
      ├── red rule ────────────────────────┤
      │ [LOGO]   THE NEWS CUP             │  ← brand strip
      └───────────────────────────────────┘
    """
    # ── Dimensions ───────────────────────────────────────────────────────
    top_bar_h      = int(height * 0.058)
    if video_style == "context":
        headline_band_h = int(height * 0.38)
    else:
        headline_band_h = int(height * 0.33)
    brand_h        = 0                          # Removed black brand strip
    brand_top      = height
    headline_top   = height - headline_band_h
    photo_h        = headline_top - top_bar_h   # usable photo area height
    split_x        = int(width * 0.58)          # where left/right panels split
    margin         = 18

    # ── Build canvas (dark navy base) ────────────────────────────────────
    base = _PI.new("RGB", (width, height), (8, 10, 18))

    # ── news photo (full width) ───────────────────────────────────────────
    photo = _scale_and_crop(bg_image, width, photo_h)
    photo = _cinematic_grade(photo)
    photo = _apply_vignette(photo, strength=0.55)
    base.paste(photo, (0, top_bar_h))

    draw = _PID.Draw(base, "RGBA")

    # ── TOP BAR ───────────────────────────────────────────────────────────
    top_bar = _PI.new("RGBA", (width, top_bar_h), (8, 10, 18, 240))
    base_rgba = base.convert("RGBA")
    base_rgba.paste(top_bar, (0, 0), top_bar)
    base = base_rgba.convert("RGB")
    draw = _PID.Draw(base, "RGBA")

    # ── LOGO (top-left) ───────────────────────────────────────────────────
    y_center = top_bar_h // 2
    logo_sz  = int(top_bar_h * 0.70)
    logo_img = _load_logo_image(logo_sz)
    if logo_img:
        logo_y = y_center - logo_sz // 2
        base.paste(logo_img, (margin, logo_y), logo_img)
    draw = _PID.Draw(base, "RGBA")

    # ── BADGE ─────────────────────────────────────────────────────────────
    if video_style == "context":
        badge_text = "EXPLAINED"
        badge_rgb = (245, 158, 11)
    elif video_style == "tracker":
        badge_text = f"DAY {episode_number}"
        badge_rgb = (59, 130, 246)
    else:
        _BADGE_STYLES = {
            "tense":       ("BREAKING NEWS",  (220, 30, 30)),
            "war":         ("WAR UPDATE",     (220, 30, 30)),
            "serious":     ("URGENT NEWS",    (180, 60, 0)),
            "disaster":    ("DISASTER ALERT", (180, 60, 0)),
            "politics":    ("POLITICS",       (20, 60, 160)),
            "positive":    ("MAJOR UPDATE",   (0, 120, 60)),
            "informative": ("TECH NEWS",      (20, 100, 140)),
            "neutral":     ("NEWS UPDATE",    (80, 80, 80)),
        }
        badge_text, badge_rgb = _BADGE_STYLES.get(context, ("NEWS UPDATE", (80, 80, 80)))
        if badge_color_hex:
            parsed_badge = hex_to_rgb(badge_color_hex)
            if parsed_badge:
                badge_rgb = parsed_badge

    badge_font = _load_font(24, font_path=font_family_path)
    bx = (logo_sz + margin * 2) if logo_img else (margin + 4)
    bh = int(top_bar_h * 0.58)
    by = y_center - bh // 2
    try:
        bb = draw.textbbox((0, 0), badge_text, badge_font)
        bw = bb[2] - bb[0]
    except Exception:
        bw = len(badge_text) * 13
    draw.rounded_rectangle(
        [(bx, by), (bx + bw + 30, by + bh)],
        radius=6, fill=badge_rgb + (255,),
    )
    draw.text((bx + (bw + 30) // 2, by + bh // 2), badge_text,
              font=badge_font, fill=(255, 255, 255, 255), anchor="mm")

    # ── LIVE badge (top-right) ────────────────────────────────────────────
    live_font = _load_font(24, font_path=font_family_path)
    live_w = 92
    live_h = bh
    live_y = by
    lx = width - margin - live_w
    draw.rounded_rectangle(
        [(lx, live_y), (lx + live_w, live_y + live_h)],
        radius=6, fill=(220, 30, 30, 255), outline=(255, 255, 255, 200), width=2,
    )
    draw.text((lx + live_w // 2, live_y + live_h // 2), "● LIVE",
              font=live_font, fill=(255, 255, 255), anchor="mm")

    # ── HEADLINE BAND ─────────────────────────────────────────────────────
    # Dark solid band at bottom
    hband_rgba = _PI.new("RGBA", (width, headline_band_h), (10, 14, 26, 248))
    base_rgba = base.convert("RGBA")
    base_rgba.paste(hband_rgba, (0, headline_top), hband_rgba)
    
    # Accent rule at top of band
    if video_style == "context":
        headline_accent_rgb = (245, 158, 11)
    elif video_style == "tracker":
        headline_accent_rgb = (59, 130, 246)
    else:
        headline_accent_rgb = hex_to_rgb(accent_color_hex) or hex_to_rgb(primary_color_hex) or _HEADLINE_ACCENT
    base_rgba.paste(_PI.new("RGBA", (width, 8), headline_accent_rgb + (255,)),
                    (0, headline_top), _PI.new("RGBA", (width, 8), headline_accent_rgb + (255,)))
    base = base_rgba.convert("RGB")

    draw = _PID.Draw(base, "RGBA")

    # ── HEADLINE TEXT ─────────────────────────────────────────────────────
    text_max_w = int(width * 0.94)
    text_band_top    = headline_top + 14
    text_band_bottom = brand_top - 10
    max_h = text_band_bottom - text_band_top - 10

    # Dynamically scale font size to perfectly fit available width and height
    optimal_sz, wrapped_lines = _find_optimal_font_size_uniform(
        draw, headline, text_max_w, max_h, height
    )

    font = _load_font(optimal_sz, font_path=font_family_path)
    line_h = optimal_sz + 10
    total_text_h = len(wrapped_lines) * line_h - 10

    mid_y   = (text_band_top + text_band_bottom) // 2
    start_y = mid_y - total_text_h // 2

    cy = start_y
    text_x = width // 2
    outline_w = max(3, int(optimal_sz * 0.05))

    for line in wrapped_lines:
        _draw_colored_line(
            draw, (text_x, cy), line, font,
            default_color=_HEADLINE_WHITE,
            highlight_color=_HEADLINE_YELLOW,
            highlight_words=_HIGHLIGHT_WORDS,
            anchor="mt",
            outline_color=(0, 0, 0),
            outline_width=outline_w
        )
        cy += line_h

    return base



# ─────────────────────────────────────────────────────────────────────────────
# Landscape compositor  (1920 × 1080 — YouTube long-form)
# ─────────────────────────────────────────────────────────────────────────────

def _compose_landscape(
    bg_image: _PI.Image,
    headline: str,
    width: int,
    height: int,
    include_anchor: bool = False,
    context: str = "neutral",
    primary_color_hex: str = None,
    accent_color_hex: str = None,
    badge_color_hex: str = None,
    font_family_path: str = None,
    video_style: str = "briefing",
    episode_number: int = 1,
) -> _PI.Image:
    """
    Layout (Firstpost / NDTV Profit style):

    ┌──────────────────────────────────────────────────────────┐
    │ [LOGO + BADGE]              [anchor cutout panel]       │
    │                                                          │
    │   CINEMATIC BG (vignetted bottom-left)                  │
    │                                                          │
    ├──────────────────────────────────────────────────────────┤
    │██  CONTEXT LINE (white, medium)                       ██ │
    │██  IMPACT WORDS IN YELLOW (BIG)                       ██ │
    ├── red rule ──────────────────────────────────────────────┤
    │ [LOGO]  The News Cup • sip the world. stay informed.     │
    └──────────────────────────────────────────────────────────┘
    """
    # 1. Background
    img = _scale_and_crop(bg_image, width, height)
    img = _cinematic_grade(img)
    img = _apply_vignette(img, strength=0.65)
    img = img.convert("RGBA")

    # 2. Determine anchor sizing and layout details first
    anchor_panel_w = 0
    anchor_rgba = None
    ax, ay = 0, 0
    brand_h = 0
    brand_top = height

    if include_anchor:
        anc_target_h = int((height - brand_h) * 1.02)
        anchor_rgba  = _load_anchor_keyed(anc_target_h)
        if anchor_rgba:
            anc_w    = anchor_rgba.width
            anchor_panel_w = int(anc_w * 0.65)
            ax = width - anc_w + 40
            ay = height - brand_h - anc_target_h + 10

            # Fade left edge of anchor to blend
            blend = _PI.new("L", anchor_rgba.size, 255)
            bd    = _PID.Draw(blend)
            fade  = min(150, anc_w)
            for bx in range(fade):
                bd.line([(bx, 0), (bx, anc_target_h)],
                        fill=int(255 * (bx / fade) ** 1.9))
            orig_a   = anchor_rgba.split()[3]
            combined = _PI.fromarray(
                (_np.array(orig_a).astype(_np.float32) *
                 _np.array(blend).astype(_np.float32) / 255).clip(0, 255).astype(_np.uint8), "L"
            )
            anchor_rgba.putalpha(combined)

    # 3. Paste anchor drop shadow and anchor (RGB) on top of the background image
    if include_anchor and anchor_rgba:
        # Create a soft silhouette shadow
        shadow_blur = 30
        shadow_mask = anchor_rgba.split()[3].filter(_PIFilt.GaussianBlur(radius=shadow_blur))
        shadow = _PI.new("RGBA", anchor_rgba.size, (0, 0, 0, 180))
        
        # Paste shadow onto background first (with a slight leftwards offset)
        img.paste(shadow, (ax - 10, ay), shadow_mask)

        # Paste anchor
        base = img.convert("RGB")
        base.paste(anchor_rgba.convert("RGB"), (ax, ay), anchor_rgba)
        img = base.convert("RGBA")

    # 4. Headline band — bottom 34% (solid dark), full width
    if video_style == "context":
        headline_band_h   = int(height * 0.39)
    else:
        headline_band_h   = int(height * 0.34)
    headline_band_top = height - headline_band_h
    h_band = _PI.new("RGBA", (width, headline_band_h), (10, 14, 26, 245))
    img.paste(h_band, (0, headline_band_top), h_band)
    
    # Accent rule at top of band
    if video_style == "context":
        headline_accent_rgb = (245, 158, 11)
    elif video_style == "tracker":
        headline_accent_rgb = (59, 130, 246)
    else:
        headline_accent_rgb = hex_to_rgb(accent_color_hex) or hex_to_rgb(primary_color_hex) or _HEADLINE_ACCENT
    accent = _PI.new("RGBA", (width, 7), headline_accent_rgb + (255,))
    img.paste(accent, (0, headline_band_top), accent)

    base = img.convert("RGB")
    draw = _PID.Draw(base, "RGBA")

    # Text available width (leave room for anchor)
    text_margin   = 50
    text_max_w    = (width - anchor_panel_w) - text_margin * 2 - (50 if include_anchor else 0)

    # ── TOP-LEFT: Logo + BREAKING NEWS badge ─────────────────────────────
    top_pad  = 20
    logo_sz  = int(height * 0.08)
    logo_img = _load_logo_image(logo_sz)
    
    bh       = int(height * 0.055)
    y_center = top_pad + max(logo_sz, bh) // 2
    
    if logo_img:
        logo_y = y_center - logo_sz // 2
        base.paste(logo_img, (top_pad, logo_y), logo_img)
    draw = _PID.Draw(base, "RGBA")

    if video_style == "context":
        badge_text = "EXPLAINED"
        badge_rgb = (245, 158, 11)
    elif video_style == "tracker":
        badge_text = f"DAY {episode_number}"
        badge_rgb = (59, 130, 246)
    else:
        _BADGE_STYLES = {
            "tense":       ("BREAKING NEWS",  (220, 30, 30)),
            "war":         ("WAR UPDATE",     (220, 30, 30)),
            "serious":     ("URGENT NEWS",    (180, 60, 0)),
            "disaster":    ("DISASTER ALERT", (180, 60, 0)),
            "politics":    ("POLITICS",       (20, 60, 160)),
            "positive":    ("MAJOR UPDATE",   (0, 120, 60)),
            "informative": ("TECH NEWS",      (20, 100, 140)),
            "neutral":     ("NEWS UPDATE",    (80, 80, 80)),
        }
        badge_text, badge_rgb = _BADGE_STYLES.get(context, ("NEWS UPDATE", (80, 80, 80)))
        if badge_color_hex:
            parsed_badge = hex_to_rgb(badge_color_hex)
            if parsed_badge:
                badge_rgb = parsed_badge

    badge_font = _load_font(int(height * 0.037), font_path=font_family_path)
    bx_start   = (logo_sz + top_pad + 14) if logo_img else (top_pad + 4)
    by         = y_center - bh // 2
    try:
        bb = draw.textbbox((0, 0), badge_text, badge_font)
        bw = bb[2] - bb[0]
    except Exception:
        bw = len(badge_text) * 22
    draw.rounded_rectangle(
        [(bx_start, by), (bx_start + bw + 36, by + bh)],
        radius=8, fill=badge_rgb + (255,),
    )
    draw.text((bx_start + (bw + 36) // 2, by + bh // 2), badge_text,
              font=badge_font, fill=(255, 255, 255), anchor="mm")

    # ── LIVE badge (top-right, only without anchor) ───────────────────────
    if not include_anchor:
        live_font = _load_font(int(height * 0.033), font_path=font_family_path)
        lbw = int(height * 0.115)
        lbh = bh
        lbx = width - lbw - top_pad
        lby = y_center - lbh // 2
        draw.rounded_rectangle(
            [(lbx, lby), (lbx + lbw, lby + lbh)],
            radius=8, fill=(220, 30, 30, 255), outline=(255, 255, 255, 200), width=2,
        )
        draw.text((lbx + lbw // 2, lby + lbh // 2), "● LIVE",
                  font=live_font, fill=(255, 255, 255), anchor="mm")

    # ── HEADLINE TEXT ─────────────────────────────────────────────────────
    text_band_top    = headline_band_top + 14
    text_band_bottom = brand_top - 12
    max_h = text_band_bottom - text_band_top - 10

    # Dynamically scale font size to perfectly fit available width and height
    optimal_sz, wrapped_lines = _find_optimal_font_size_uniform(
        draw, headline, text_max_w, max_h, height
    )

    font = _load_font(optimal_sz, font_path=font_family_path)
    line_h = optimal_sz + 10
    total_text_h = len(wrapped_lines) * line_h - 10

    mid_y   = (text_band_top + text_band_bottom) // 2
    start_y = mid_y - total_text_h // 2

    cy = start_y
    text_x = (width - anchor_panel_w) // 2
    outline_w = max(3, int(optimal_sz * 0.05))

    for line in wrapped_lines:
        _draw_colored_line(
            draw, (text_x, cy), line, font,
            default_color=_HEADLINE_WHITE,
            highlight_color=_HEADLINE_YELLOW,
            highlight_words=_HIGHLIGHT_WORDS,
            anchor="mt",
            outline_color=(0, 0, 0),
            outline_width=outline_w
        )
        cy += line_h





    return base
