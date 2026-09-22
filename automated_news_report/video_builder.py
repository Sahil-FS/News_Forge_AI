# video_builder.py - 1080x1920 vertical video with styled visuals
# Upgrades: bottom gradient, pill text card, branding bar

import sys
import os
# Environment lock
import os as _os_env_check
if "VIRTUAL_ENV" not in _os_env_check.environ and ".venv" not in sys.executable and "venv" not in sys.executable:
    print(f"[WARN] Running outside a virtual environment: {sys.executable}")

import numpy as np
from utils import clean_caption_text
from moviepy_compat import ConsoleProgressBarLogger

_last_valid_bg_arr = None   # blur-safety-net: stores last good background
CAPTION_LEAD_S = 0.10   # 0.10s: caption appears slightly before word is spoken


def distribute_word_timings(words, total_duration):
    """
    Return a list of (start, end) float pairs - one per word.

    Each pair is shifted CAPTION_LEAD_S seconds earlier than the raw
    proportional position so captions arrive just before the spoken word,
    preventing the 'lazy text' lag that occurs with Piper TTS output.

    Word weight rules:
      short  (<=3 chars) -> 0.8 weight  (spoken faster)
      medium (4-6 chars) -> 1.0 weight
      long   (>6 chars)  -> 1.2 weight
    Minimum per-word display window: 0.10 seconds (floor).
    Maximum per-word display window: 0.40 seconds (cap).
    Lead-time clamped so no start time goes below 0.
    """
    if not words:
        return []

    weights = []
    for w in words:
        if len(w) <= 3:
            weights.append(SCENE_WORD_MIN_WEIGHT)
        elif len(w) <= 6:
            weights.append(1.0)
        else:
            weights.append(SCENE_WORD_MAX_WEIGHT)

    weights   = np.array(weights, dtype=float)
    weights  /= weights.sum()
    durations = weights * total_duration

    # Protect timings using config values
    durations = np.maximum(durations, WORD_DISPLAY_MIN_SECS)
    durations = np.minimum(durations, WORD_DISPLAY_MAX_SECS)
    
    # Re-normalize to fit total_duration
    total_new = durations.sum()
    if total_new > 0:
        durations = durations * (total_duration / total_new)

    # RE-APPLY FLOOR after normalization
    durations = np.maximum(durations, 0.08)

    # Final re-normalize to restore total_duration after floor re-application
    total_final = durations.sum()
    if total_final > 0 and total_final != total_duration:
        durations = durations * (total_duration / total_final)

    # Build raw (start, end) pairs
    raw_timings = []
    current = 0.0
    for d in durations:
        raw_timings.append((current, current + d))
        current += d

    # Apply lead-time
    offset_timings = []
    for start, end in raw_timings:
        s = max(0.0, start - CAPTION_LEAD_S)
        # Ensure end doesn't shrink below floor
        e = max(s + WORD_DISPLAY_MIN_SECS, end - CAPTION_LEAD_S)
        offset_timings.append((s, e))

    return offset_timings


from PIL import Image, ImageDraw, ImageFont, ImageFilter
from moviepy.video.VideoClip import ImageClip
from moviepy.audio.io.AudioFileClip import AudioFileClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
from moviepy.audio.AudioClip import CompositeAudioClip
import moviepy.video.fx as vfx
import moviepy.audio.fx as afx
from moviepy.editor import concatenate_videoclips as _mpy_concatenate
from moviepy.video.VideoClip import VideoClip
from moviepy.audio.AudioClip import AudioArrayClip

from moviepy_compat import apply_compat_patches
apply_compat_patches()


from config import (
    VIDEO_WIDTH,
    VIDEO_HEIGHT,
    VIDEO_FPS,
    OUTPUT_VIDEO,
    MAP_STINGER_DURATION,
    MAP_STINGER_MAX,
    MAP_STINGER_MIN,
    BRAND_NAME,
    KEN_BURNS_ZOOM_FACTOR,
    OUTRO_MIN_DURATION,
    OUTRO_MAX_DURATION,
    CAPTION_MAX_VISIBLE_WORDS,
    CAPTION_LEAD_SECS,
    AUDIO_TAIL_BUFFER_SECS,
    SCENE_COMPRESSION_MIN_SCALE,
    SCENE_WORD_MIN_WEIGHT,
    SCENE_WORD_MAX_WEIGHT,
    WORD_DISPLAY_MIN_SECS,
    WORD_DISPLAY_MAX_SECS,
)
 

# -- Branding ------------------------------------------------------------------
_last_valid_bg_arr = None   # blur-safety-net: stores last good background
CAPTION_LEAD_S = CAPTION_LEAD_SECS   # caption appears slightly before word is spoken
ACCENT_COLOR = (220, 50, 50)      # red accent  (R, G, B)
BAR_HEIGHT   = 90                 # px - branding bar at very bottom
 
# -- Font loader ---------------------------------------------------------------
def _font(size: int, bold: bool = True):
    candidates_bold = [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/calibrib.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
    ]
    candidates_reg = [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibri.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/Library/Fonts/Arial.ttf",
    ]
    for path in (candidates_bold if bold else candidates_reg):
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()
 
 
# -- Layer 1 - Background image ------------------------------------------------
def _make_background(image_path: str | None, W: int, H: int, heavy_blur: bool = False) -> np.ndarray:
    """
    Return a (H, W, 3) uint8 array.
    Priority:
      1. Load image_path if it exists and is valid - store it in
         _last_valid_bg_arr for future blur-safety-net use.
      2. If image_path is missing/broken AND a previous background
         exists, apply GaussianBlur(radius=30) to that stored array
         and return it. This maintains visual continuity across scenes
         instead of going black.
      3. If no previous background exists at all, return a dark solid.
    """
    global _last_valid_bg_arr

    if image_path and os.path.isfile(image_path):
        try:
            img = Image.open(image_path).convert("RGB")

            scale = max(H / img.height, W / img.width)
            new_w = max(int(img.width  * scale), W)
            new_h = max(int(img.height * scale), H)
            img   = img.resize((new_w, new_h), Image.LANCZOS)
            left  = (new_w - W) // 2
            top   = (new_h - H) // 2
            img   = img.crop((left, top, left + W, top + H))
            blur_radius = 30.0 if heavy_blur else 0.8
            img   = img.filter(ImageFilter.GaussianBlur(radius=blur_radius))

            arr = np.array(img)
            _last_valid_bg_arr = arr   # save for blur-safety-net
            return arr

        except Exception as exc:
            print(f"[VideoBuilder] Image load failed: {exc}")
            try:
                import time as _retry_time
                _retry_time.sleep(0.1)
                img = Image.open(image_path).convert("RGB")

                scale = max(H / img.height, W / img.width)
                new_w = max(int(img.width  * scale), W)
                new_h = max(int(img.height * scale), H)
                img   = img.resize((new_w, new_h), Image.LANCZOS)
                left  = (new_w - W) // 2
                top   = (new_h - H) // 2
                img   = img.crop((left, top, left + W, top + H))
                blur_radius = 30.0 if heavy_blur else 0.8
                img   = img.filter(ImageFilter.GaussianBlur(radius=blur_radius))

                arr = np.array(img)
                _last_valid_bg_arr = arr
                print(f"[VideoBuilder] Image retry succeeded: {image_path}")
                return arr
            except Exception:
                pass

    # -- High-contrast blur-safety-net ---------------------------------
    # Problem: raw GaussianBlur on bright frames causes white smears
    # that make caption text unreadable.
    # Fix: composite the blurred frame at 50% opacity over a solid
    # dark-navy canvas (#0d1117) to guarantee caption contrast.
    if _last_valid_bg_arr is not None:
        print("[BG] No image -- using blurred previous frame")

        DARK_NAVY = (13, 17, 23)   # hex #0d1117

        # Step 1: build solid dark-navy base
        base = Image.new("RGB", (W, H), DARK_NAVY)

        # Step 2: blur the previous frame heavily
        prev_img = Image.fromarray(_last_valid_bg_arr).convert("RGB")
        blurred  = prev_img.filter(ImageFilter.GaussianBlur(radius=30))

        # Step 3: composite blurred frame at 50% opacity over dark base
        # PIL has no direct opacity blend for RGB - convert to RGBA,
        # set alpha to 128 (50%), then alpha_composite onto dark base.
        blurred_rgba = blurred.convert("RGBA")
        r, g, b, a   = blurred_rgba.split()
        a            = a.point(lambda x: 128)   # force 50% alpha
        blurred_rgba = Image.merge("RGBA", (r, g, b, a))

        base_rgba = base.convert("RGBA")
        composite = Image.alpha_composite(base_rgba, blurred_rgba)
        result    = composite.convert("RGB")

        return np.array(result)

    # -- Hard fallback - only if no frame has ever been loaded ---------
    print("[BG] No image and no prior frame -- using dark blue fallback")
    base = np.zeros((H, W, 3), dtype=np.uint8)
    base[:, :] = [15, 35, 65]
    return base
 
 
# -- Layer 2 - Bottom gradient overlay ----------------------------------------
def _make_gradient_overlay(W: int, H: int) -> np.ndarray:
    """
    RGBA layer: fully transparent at top --> 85 % opaque black at bottom.
    Covers the lower 55 % of the frame so the image breathes at the top.
    """
    overlay = np.zeros((H, W, 4), dtype=np.uint8)
    grad_start = int(H * 0.35)          # gradient begins 35 % from top
    grad_pixels = H - grad_start
 
    for y in range(grad_start, H):
        t = (y - grad_start) / grad_pixels   # 0 --> 1
        # Ease-in curve: slow start, strong finish
        alpha = int(215 * (t ** 1.6))
        overlay[y, :, 3] = min(alpha, 215)
 
    return overlay
 
 
# -- Layer 3 - Styled text card ------------------------------------------------
def _make_text_card(text: str, W: int, H: int, highlight_word: str = "") -> np.ndarray:
    """
    Renders:
      * A semi-transparent rounded-rect pill behind the text
      * Main scene text (2-line max, bold, white)
      * Current word highlighted in yellow for cinematic feel
    Positioned in the lower-third of the frame.
    """
    if not text or not text.strip():
        return np.zeros((H, W, 4), dtype=np.uint8)   # transparent, correct dtype
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if not text.strip():
        return np.array(canvas)

    draw   = ImageDraw.Draw(canvas)
 
    font_size = 48
    font      = _font(font_size, bold=True)
 
    # -- Pixel-aware word wrap with 70px safe margins -------------------
    # Safe zone is VIDEO_WIDTH minus 140px (70px each side).
    SAFE_W     = W - 140           # 940 px for 1080 canvas
    font_size  = 48
    font       = _font(font_size, bold=True)

    # Measure each word's pixel width using a scratch draw surface
    _probe_img  = Image.new("RGBA", (1, 1))
    _probe_draw = ImageDraw.Draw(_probe_img)

    def _word_px(word):
        try:
            bb = _probe_draw.textbbox((0, 0), word + " ", font=font)
            return bb[2] - bb[0]
        except AttributeError:
            return _probe_draw.textsize(word + " ", font=font)[0]

    # Build lines that never exceed SAFE_W pixels
    words_list = text.split()
    lines      = []
    cur_line   = []
    cur_width  = 0

    for word in words_list:
        w_px = _word_px(word)
        if cur_line and cur_width + w_px > SAFE_W:
            lines.append(" ".join(cur_line))
            cur_line  = [word]
            cur_width = w_px
        else:
            cur_line.append(word)
            cur_width += w_px

    if cur_line:
        lines.append(" ".join(cur_line))

    # Cap at 3 visible lines to stay within frame
    lines     = lines[:3]
    wrapped   = "\n".join(lines)
    line_text = wrapped
 
    # Measure
    try:
        bbox = draw.multiline_textbbox((0, 0), line_text, font=font, spacing=14)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
    except AttributeError:
        tw, th = draw.multiline_textsize(line_text, font=font, spacing=14)
 
    pad_x, pad_y = 48, 28
    card_w = tw + pad_x * 2
    card_h = th + pad_y * 2
 
    # Horizontal centre; positioned in lower-third
    cx = (W - card_w) // 2
    cy = int(H * 0.68)
 
    # Pill background  (dark, 75 % opacity)
    pill = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
    pdraw = ImageDraw.Draw(pill)
    radius = 22
    pdraw.rounded_rectangle(
        [(0, 0), (card_w - 1, card_h - 1)],
        radius=radius,
        fill=(10, 10, 10, 190),
    )
    # Accent left border stripe
    pdraw.rounded_rectangle(
        [(0, 0), (8, card_h - 1)],
        radius=radius,
        fill=(*ACCENT_COLOR, 255),
    )
    canvas.alpha_composite(pill, (cx, cy))
 
    # Text drawing
    tx = cx + pad_x
    ty = cy + pad_y
 
    # NO shadows, NO duplicate layers, NO overlay.
    # Draw word by word with clean highlight logic.
    lines = line_text.split("\n")
    line_y = ty
    
    for line in lines:
        line_words = line.split()
        word_x = tx
        for w in line_words:
            # CLEAN HIGHLIGHT LOGIC
            color = "yellow" if w == highlight_word else "white"
            fill_color = (255, 215, 0, 255) if color == "yellow" else (255, 255, 255, 255)
            
            draw.text((word_x, line_y), w, font=font, fill=fill_color)
            
            try:
                space_bb = draw.textbbox((0, 0), w + " ", font=font)
                word_x += space_bb[2] - space_bb[0]
            except AttributeError:
                word_x += draw.textsize(w + " ", font=font)[0]
        
        try:
            lh = draw.textbbox((0, 0), "A", font=font)
            line_y += (lh[3] - lh[1]) + 20
        except AttributeError:
            line_y += draw.textsize("A", font=font)[1] + 14
 
    return np.array(canvas)
 
 
 
# -- Progressive caption renderer (frame-based, no TextClip stacking) ----------
def _make_progressive_caption(text, timing_duration, W, H, clip_duration=None):
    """
    Frame-based progressive caption (NO stacking).
    Shows words gradually based on timing_duration (usually audio length),
    but the clip itself lasts clip_duration (usually scene length).
    """
    if clip_duration is None:
        clip_duration = timing_duration

    original_text = text
    text = clean_caption_text(original_text)

    print("[RAW TEXT]:", repr(original_text))
    print("[CLEAN TEXT]:", text)

    words = text.split()
    words = [w.strip() for w in words if w.strip()]

    clean_words = []
    prev_word = None

    for w in words:
        if w != prev_word:
            clean_words.append(w)
            prev_word = w

    words = clean_words

    print(f"[WORDS]: {words}")

    total_words = len(words)

    if total_words == 0:
        return None

    print(f"[CLEAN CAPTION TEXT]: {text}")
    print(f"[Caption] words={len(words)}, timing_dur={timing_duration:.2f}, clip_dur={clip_duration:.2f}")
    
    timings = distribute_word_timings(words, timing_duration)
    assert len(words) == len(timings), "Mismatch: words vs timings"

    _frame_cache = {}

    def make_frame(t):
        nonlocal _frame_cache
        # Step 1 - accurate word index using timings
        word_index = 0
        for i, (start, end) in enumerate(timings):
            if t >= start:
                word_index = i
            else:
                break

        if word_index >= total_words:
            word_index = total_words - 1

        # After voice ends, HOLD the final complete caption frame
        # This is intentional -- viewer can still read while scene fades out
        # Never return transparent here -- that causes a visual pop/flicker
        if t > timings[-1][1]:
            _hold_key = "__HOLD__"
            if _hold_key in _frame_cache:
                return _frame_cache[_hold_key]
            # Build complete caption frame (all words, no highlight)
            _all_visible = words[-min(CAPTION_MAX_VISIBLE_WORDS, len(words)):]
            _hold_frame = _make_text_card(" ".join(_all_visible), W, H, highlight_word="")
            _frame_cache[_hold_key] = _hold_frame
            return _hold_frame

        if word_index in _frame_cache:
            return _frame_cache[word_index]
                
        visible_words = words[:word_index + 1]
 
        # Step 2 - limit to last N words for readable display
        mobile = True
        max_words = CAPTION_MAX_VISIBLE_WORDS if mobile else 12
        visible_words = visible_words[-max_words:]
 
        # Cinematic highlight - current (last) word shown in yellow
        highlight_word = visible_words[-1] if visible_words else ""
 
        caption_text = " ".join(visible_words)

        frame = _make_text_card(caption_text, W, H, highlight_word=highlight_word)
        _frame_cache[word_index] = frame
        return frame
 
    def make_rgb_frame(t):
        rgba = make_frame(t)
        return rgba[:, :, :3]

    def make_mask_frame(t):
        rgba = make_frame(t)
        return rgba[:, :, 3] / 255.0

    # Caption Clip Duration Minimum Guard
    _safe_duration = max(clip_duration, timing_duration)
    clip = VideoClip(make_rgb_frame, duration=_safe_duration)
    mask = VideoClip(make_mask_frame, ismask=True, duration=_safe_duration)
    clip = clip.with_mask(mask)
    clip.fps = VIDEO_FPS

    return clip
 
 
# -- Scene clip assembler ------------------------------------------------------
def _make_breaking_news_banner(
    W: int, H: int,
    label: str = "BREAKING NEWS",
    bar_color: tuple = (220, 30, 30),
) -> np.ndarray:
    """
    Renders a 'BREAKING NEWS' red banner strip at the top of the frame.
    Only used for scene index 0.
    Height: 72px. Style: red background, white bold text, pulsing dot.
    Returns RGBA numpy array.
    """
    BAR_H = 72
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw   = ImageDraw.Draw(canvas)
 
    # Red background strip (full width, top of frame)
    draw.rectangle([(0, 0), (W, BAR_H)], fill=(*bar_color, 240))
 
    # White divider line at bottom of bar
    draw.rectangle([(0, BAR_H - 2), (W, BAR_H)], fill=(255, 255, 255, 180))
 
    # "BREAKING NEWS" text
    font_breaking = _font(30, bold=True)
    try:
        tb = draw.textbbox((0, 0), label, font_breaking)
        tw = tb[2] - tb[0]
        th = tb[3] - tb[1]
    except AttributeError:
        tw, th = draw.textsize(label, font_breaking)
 
    text_y = (BAR_H - th) // 2
    # Draw text shadow
    draw.text(
        (22, text_y + 2),
        label,
        font=font_breaking,
        fill=(0, 0, 0, 100)
    )
    # Draw text
    draw.text(
        (20, text_y),
        label,
        font=font_breaking,
        fill=(255, 255, 255, 255)
    )
 
    # "LIVE" badge on the right
    font_live = _font(22, bold=True)
    live_label = "LIVE"
    try:
        lb = draw.textbbox((0, 0), live_label, font_live)
        lw, lh = lb[2] - lb[0], lb[3] - lb[1]
    except AttributeError:
        lw, lh = draw.textsize(live_label, font_live)
 
    live_x = W - lw - 30
    live_y = (BAR_H - lh) // 2
    # Badge background
    draw.rounded_rectangle(
        [(live_x - 12, live_y - 6), (live_x + lw + 12, live_y + lh + 4)],
        radius=6,
        fill=(255, 255, 255, 255)
    )
    draw.text(
        (live_x, live_y),
        live_label,
        font=font_live,
        fill=(*bar_color, 255)
    )
 
    return np.array(canvas)
 
 
def _make_lower_third(headline: str, source: str, location: str,
                      W: int, H: int) -> np.ndarray:
    """
    Renders a professional news lower-third overlay.
    Positioned in the bottom 18% of the frame, above the brand bar area.
 
    Layout:
      +------------------------------------------+
      | [RED BAR] HEADLINE TEXT          SOURCE  |
      |           Location / Context             |
      +------------------------------------------+
 
    Returns RGBA numpy array.
    """
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw   = ImageDraw.Draw(canvas)
 
    STRIP_H   = 110
    STRIP_Y   = H - STRIP_H - BAR_HEIGHT - 10   # just above brand bar
    ACCENT_W  = 10
 
    # Dark semi-transparent background strip
    draw.rectangle(
        [(0, STRIP_Y), (W, STRIP_Y + STRIP_H)],
        fill=(8, 8, 18, 210)
    )
 
    # Red left accent bar
    draw.rectangle(
        [(0, STRIP_Y), (ACCENT_W, STRIP_Y + STRIP_H)],
        fill=(*ACCENT_COLOR, 255)
    )
 
    # White top border line
    draw.rectangle(
        [(0, STRIP_Y), (W, STRIP_Y + 2)],
        fill=(255, 255, 255, 60)
    )
 
    # Headline text - truncate to fit width
    font_headline = _font(34, bold=True)
    max_headline_chars = 38
    display_headline = (headline[:max_headline_chars] + "..."
                        if len(headline) > max_headline_chars else headline)
    display_headline = display_headline.upper()
 
    text_x  = ACCENT_W + 18
    text_y1 = STRIP_Y + 14
 
    # Headline
    draw.text((text_x, text_y1), display_headline,
              font=font_headline, fill=(255, 255, 255, 255))
 
    # Location / context line below headline
    font_location = _font(24, bold=False)
    display_location = location if location else source
    draw.text((text_x, text_y1 + 46), display_location,
              font=font_location, fill=(200, 200, 200, 210))
 
    # Source label - right-aligned
    font_source = _font(22, bold=False)
    source_label = f"Source: {source}"
    try:
        sb = draw.textbbox((0, 0), source_label, font=font_source)
        sw = sb[2] - sb[0]
    except AttributeError:
        sw, _ = draw.textsize(source_label, font=font_source)
 
    draw.text((W - sw - 20, text_y1 + 50), source_label,
              font=font_source, fill=(160, 160, 160, 200))
 
    return np.array(canvas)
 
 
def _generate_whoosh(duration: float = 0.18) -> np.ndarray | None:
    """
    Generate a 0.18s whoosh sound effect using numpy.
    Technique: exponential frequency sweep from 800Hz down to 120Hz
    with rapid volume fade-out. Sounds like a fast camera cut swoosh.
    Returns stereo float32 array shaped (samples, 2) for MoviePy,
    or None on failure.
    """
    try:
        SAMPLE_RATE = 44100
        n = int(SAMPLE_RATE * duration)
        t = np.linspace(0, duration, n, endpoint=False)
 
        # Exponential frequency sweep: 800Hz -> 120Hz
        f_start, f_end = 800.0, 120.0
        freq = f_start * (f_end / f_start) ** (t / duration)
        phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
        wave = np.sin(phase)
 
        # Amplitude envelope: fast attack, rapid exponential decay
        envelope = np.exp(-t * 18.0)
        wave = wave * envelope * 0.04   # 4% volume -- barely audible, professional
 
        # Stereo
        stereo = np.stack([wave, wave], axis=1).astype(np.float32)
        return stereo
    except Exception as exc:
        print(f"[WHOOSH] Generation failed: {exc}")
        return None
 
 
from PIL import Image
import numpy as np
from moviepy.video.VideoClip import VideoClip
 
 
def _apply_ken_burns(bg_arr, clip_duration):
    """Custom Ken Burns effect bypassing MoviePy's broken dynamic resize."""
    # Force array to uint8 format to prevent Pillow from rendering floats as pitch black
    import numpy as np
    if bg_arr.dtype != np.uint8:
        if bg_arr.max() <= 1.0:
            bg_arr = (bg_arr * 255).astype(np.uint8)
        else:
            bg_arr = bg_arr.astype(np.uint8)
 
    h, w = bg_arr.shape[:2]
    if bg_arr.shape[2] == 4:
        bg_arr = bg_arr[:, :, :3]
 
    resample_method = getattr(Image, 'Resampling', Image).BILINEAR if hasattr(Image, 'Resampling') else getattr(Image, 'BILINEAR', 2)
 
    fps = 24
    _cache = {}

    def make_zoom_frame(t):
        frame_idx = int(round(t * fps))
        if frame_idx in _cache:
            return _cache[frame_idx]

        t_safe = max(0.0, min(float(t), float(clip_duration)))
        scale = 1.0 + KEN_BURNS_ZOOM_FACTOR * (t_safe / max(1.0, clip_duration))
 
        new_w = int(w / scale)
        new_h = int(h / scale)
        x1 = (w - new_w) // 2
        y1 = (h - new_h) // 2
 
        cropped = bg_arr[y1:y1+new_h, x1:x1+new_w]
        pil_img = Image.fromarray(cropped)
        res = np.array(pil_img.resize((w, h), resample_method))
        _cache[frame_idx] = res
        return res
 
    clip = VideoClip(make_zoom_frame, duration=clip_duration)
    clip.fps = fps
    return clip
 
 
def _make_transition_card(text: str, W: int, H: int) -> np.ndarray:
    """
    Renders a dynamic full-screen transition card.
    Uses HSL-derived high-energy gradient background (e.g. red to deep purple).
    Large bold typography centered in the frame.
    """
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    draw = ImageDraw.Draw(canvas)
    
    # Draw a vibrant diagonal gradient
    for y in range(H):
        t = y / H
        r = int(180 * (1 - t) + 80 * t)
        g = int(20 * (1 - t) + 20 * t)
        b = int(50 * (1 - t) + 120 * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b, 255))
        
    # Add subtle geometric background overlay details (diagonal lines/slats) for high energy
    for i in range(-500, W + 500, 120):
        draw.line([(i, 0), (i + 500, H)], fill=(255, 255, 255, 8), width=30)

    # Wrap text if needed and draw it
    font_large = _font(64, bold=True)
    
    lines = []
    if ":" in text:
        parts = text.split(":", 1)
        lines.append(parts[0].strip().upper())
        lines.append(parts[1].strip().upper())
    else:
        words = text.split()
        if len(words) > 2:
            lines.append(" ".join(words[:2]).upper())
            lines.append(" ".join(words[2:]).upper())
        else:
            lines.append(text.upper())
            
    line_y = H // 2 - 120
    for line in lines:
        try:
            tb = draw.textbbox((0, 0), line, font_large)
            tw = tb[2] - tb[0]
            th = tb[3] - tb[1]
        except AttributeError:
            tw, th = draw.textsize(line, font_large)
            
        text_x = (W - tw) // 2
        draw.text((text_x + 4, line_y + 4), line, font=font_large, fill=(0, 0, 0, 150))
        draw.text((text_x, line_y), line, font=font_large, fill=(255, 255, 255, 255))
        line_y += th + 40
        
    return np.array(canvas.convert("RGB"))


def _make_social_mockup(entity: str, text: str, W: int, H: int) -> np.ndarray:
    """
    Renders a beautiful semi-transparent X/Twitter post overlay card.
    Positioned in the center of the frame.
    """
    import re as _local_re
    import random
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    
    card_w = W - 100  # 980px
    font_body = _font(30, bold=False)
    
    safe_text_w = card_w - 80
    probe_img = Image.new("RGBA", (1, 1))
    probe_draw = ImageDraw.Draw(probe_img)
    
    def _text_w(t):
        try:
            bb = probe_draw.textbbox((0, 0), t, font=font_body)
            return bb[2] - bb[0]
        except AttributeError:
            return probe_draw.textsize(t, font=font_body)[0]
            
    words = text.split()
    lines = []
    cur_line = []
    cur_w = 0
    for w in words:
        w_px = _text_w(w + " ")
        if cur_line and cur_w + w_px > safe_text_w:
            lines.append(" ".join(cur_line))
            cur_line = [w]
            cur_w = w_px
        else:
            cur_line.append(w)
            cur_w += w_px
    if cur_line:
        lines.append(" ".join(cur_line))
        
    wrapped_text = "\n".join(lines)
    
    font_name = _font(32, bold=True)
    font_handle = _font(26, bold=False)
    
    try:
        bb = draw.multiline_textbbox((0, 0), wrapped_text, font=font_body, spacing=10)
        th = bb[3] - bb[1]
    except AttributeError:
        th = draw.multiline_textsize(wrapped_text, font=font_body, spacing=10)[1]
        
    card_h = 120 + 30 + th + 40 + 60 + 40
    
    card_x = (W - card_w) // 2
    card_y = (H - card_h) // 2
    
    draw.rounded_rectangle(
        [(card_x, card_y), (card_x + card_w, card_y + card_h)],
        radius=24,
        fill=(21, 32, 43, 240),
        outline=(255, 255, 255, 30),
        width=2
    )
    
    avatar_r = 35
    avatar_cx = card_x + 40 + avatar_r
    avatar_cy = card_y + 40 + avatar_r
    
    first_char = entity[0].upper() if entity else "N"
    color_map = {
        "A": (230, 50, 50), "B": (50, 180, 50), "C": (50, 100, 230),
        "D": (230, 150, 20), "E": (150, 50, 200), "F": (20, 180, 180),
        "G": (200, 20, 150), "H": (80, 200, 120), "I": (120, 80, 200),
        "J": (220, 80, 50), "K": (50, 150, 100), "L": (100, 50, 180),
        "M": (180, 120, 50), "N": (50, 80, 180), "O": (200, 180, 20),
        "P": (210, 50, 150), "Q": (50, 210, 80), "R": (150, 50, 210),
        "S": (220, 120, 20), "T": (20, 180, 100), "U": (120, 50, 120),
        "V": (100, 200, 50), "W": (50, 120, 200), "X": (180, 50, 50),
        "Y": (50, 180, 120), "Z": (120, 180, 50)
    }
    avatar_color = color_map.get(first_char, (100, 100, 100))
    draw.ellipse(
        [(avatar_cx - avatar_r, avatar_cy - avatar_r),
         (avatar_cx + avatar_r, avatar_cy + avatar_r)],
        fill=avatar_color
    )
    
    font_initial = _font(36, bold=True)
    try:
        ib = draw.textbbox((0, 0), first_char, font_initial)
        iw = ib[2] - ib[0]
        ih = ib[3] - ib[1]
    except AttributeError:
        iw, ih = draw.textsize(first_char, font_initial)
    draw.text((avatar_cx - iw // 2, avatar_cy - ih // 2 - 2), first_char, font=font_initial, fill=(255, 255, 255, 255))
    
    name_x = card_x + 130
    name_y = card_y + 42
    draw.text((name_x, name_y), entity, font=font_name, fill=(255, 255, 255, 255))
    
    try:
        nb = draw.textbbox((0, 0), entity, font_name)
        nw = nb[2] - nb[0]
    except AttributeError:
        nw = draw.textsize(entity, font_name)[0]
    
    badge_x = name_x + nw + 10
    badge_y = name_y + 6
    draw.ellipse([(badge_x, badge_y), (badge_x + 24, badge_y + 24)], fill=(29, 155, 240))
    draw.line([(badge_x + 7, badge_y + 12), (badge_x + 11, badge_y + 16)], fill=(255, 255, 255), width=3)
    draw.line([(badge_x + 11, badge_y + 16), (badge_x + 17, badge_y + 8)], fill=(255, 255, 255), width=3)
    
    handle = "@" + _local_re.sub(r'\W+', '', entity.lower())
    handle_y = name_y + 40
    draw.text((name_x, handle_y), handle, font=font_handle, fill=(136, 153, 166, 255))
    
    body_x = card_x + 40
    body_y = card_y + 135
    draw.multiline_text((body_x, body_y), wrapped_text, font=font_body, fill=(255, 255, 255, 255), spacing=10)
    
    footer_y = body_y + th + 40
    draw.line([(card_x + 40, footer_y), (card_x + card_w - 40, footer_y)], fill=(56, 68, 77, 255), width=1)
    
    stats_y = footer_y + 20
    font_stats = _font(22, bold=False)
    
    random.seed(len(text))
    retweets = f"{random.randint(100, 999)}K"
    likes = f"{random.randint(1, 99)}.{random.randint(1, 9)}K"
    views = f"{random.randint(10, 999)}K"
    
    comm_x = card_x + 60
    draw.ellipse([(comm_x, stats_y + 4), (comm_x + 16, stats_y + 20)], outline=(136, 153, 166), width=2)
    draw.text((comm_x + 28, stats_y), "284", font=font_stats, fill=(136, 153, 166))
    
    rt_x = card_x + 220
    draw.rectangle([(rt_x, stats_y + 4), (rt_x + 16, stats_y + 20)], outline=(136, 153, 166), width=2)
    draw.text((rt_x + 28, stats_y), retweets, font=font_stats, fill=(136, 153, 166))
    
    like_x = card_x + 380
    draw.ellipse([(like_x, stats_y + 4), (like_x + 10, stats_y + 14)], fill=(249, 24, 128))
    draw.ellipse([(like_x + 8, stats_y + 4), (like_x + 18, stats_y + 14)], fill=(249, 24, 128))
    draw.polygon([(like_x, stats_y + 10), (like_x + 18, stats_y + 10), (like_x + 9, stats_y + 22)], fill=(249, 24, 128))
    draw.text((like_x + 28, stats_y), likes, font=font_stats, fill=(249, 24, 128))
    
    views_x = card_x + 550
    draw.rectangle([(views_x, stats_y + 10), (views_x + 4, stats_y + 20)], fill=(136, 153, 166))
    draw.rectangle([(views_x + 6, stats_y + 4), (views_x + 10, stats_y + 20)], fill=(136, 153, 166))
    draw.rectangle([(views_x + 12, stats_y + 14), (views_x + 16, stats_y + 20)], fill=(136, 153, 166))
    draw.text((views_x + 28, stats_y), views, font=font_stats, fill=(136, 153, 166))
    
    return np.array(canvas)


def _build_scene_clip(
    image_path: str | None,
    audio_path: str | None,
    text: str,
    scene_idx: int,
    final_duration: float,
    headline: str = "",
    news_source: str = "BBC News",
    location: str = "",
    scene_type: str = "general",
    alt_image_path: str | None = None,
    visual_cut_threshold: float = 2.8,
    is_social_mockup: bool = False,
    social_entity: str = "",
    social_text: str = "",
    is_transition: bool = False,
) -> CompositeVideoClip:
    W, H = VIDEO_WIDTH, VIDEO_HEIGHT
    import moviepy.audio.fx as afx

    if is_transition or scene_type == "transition":
        duration = final_duration
        card_arr = _make_transition_card(text, W, H)
        card_clip = ImageClip(card_arr).with_duration(duration)
        
        # Audio stinger: whoosh sound effect
        whoosh_data = _generate_whoosh(duration=duration)
        if whoosh_data is not None:
            try:
                whoosh_clip = AudioArrayClip(whoosh_data, fps=44100)
                whoosh_clip = whoosh_clip.with_effects([afx.MultiplyVolume(2.0)])
                card_clip = card_clip.with_audio(whoosh_clip)
            except Exception as exc:
                print(f"[WHOOSH] Transition stinger SFX failed: {exc}")
                
        return CompositeVideoClip([card_clip], size=(W, H)).with_duration(duration)

    _effective_image_path = image_path
    if not _effective_image_path or not os.path.isfile(_effective_image_path):
        _placeholder = os.path.join(os.path.dirname(OUTPUT_VIDEO), "..", "assets", "placeholder.jpg")
        _placeholder = os.path.abspath(_placeholder)
        if os.path.isfile(_placeholder):
            _effective_image_path = _placeholder
            print(f"[SCENE {scene_idx:02d}] Using placeholder image (no image found)")
 
    # Capture PURE voice duration FIRST before any mixing
    _pure_voice_duration = 0.0   # this is what caption timing must match

    if audio_path and os.path.isfile(audio_path):
        audio_clip = AudioFileClip(audio_path)
        _pure_voice_duration = audio_clip.duration   # pure voice, saved before any mixing
        # 0.30s buffer (reduced from 0.50) -- prevents clipping without dead air
        duration = audio_clip.duration + AUDIO_TAIL_BUFFER_SECS
 
        # -- Whoosh SFX prepend --------------------------------------------
        # Generate a short swoosh and prepend to scene audio for a
        # professional transition feel (12% volume, 0.18s).
        whoosh_data = _generate_whoosh(duration=0.18)
        if whoosh_data is not None:
            try:
                whoosh_clip = AudioArrayClip(whoosh_data, fps=44100)
                whoosh_clip = whoosh_clip.with_effects([afx.MultiplyVolume(1.0)])
                # Mix whoosh with voiceover - whoosh at start, voice throughout
                audio_clip = CompositeAudioClip([
                    whoosh_clip,
                    audio_clip
                ]).with_duration(duration)
            except Exception as exc:
                print(f"[WHOOSH] Mix failed: {exc} - skipping whoosh")
    else:
        audio_clip = None
        duration = final_duration
 
    duration = final_duration  # keep final_duration as master (already includes buffer via build_video)
  
    def make_frame(_t):
        return _make_background(_effective_image_path, W, H, heavy_blur=is_social_mockup)
  
    CUT_THRESHOLD = visual_cut_threshold  # seconds
 
    if duration > CUT_THRESHOLD and _effective_image_path:
        cut_point = duration / 2  # cut at midpoint
 
        # Primary image - first half
        bg_arr_a = _make_background(_effective_image_path, W, H, heavy_blur=is_social_mockup)
        bg_a = _apply_ken_burns(bg_arr_a, cut_point)
 
        # Fetch a second image for the visual cut second half
        # Build background for second half
        bg_arr_b = _make_background(
            alt_image_path if alt_image_path else _effective_image_path, W, H, heavy_blur=is_social_mockup
        )
        bg_b = _apply_ken_burns(bg_arr_b, duration - cut_point)
 
        # Concatenate the two visual halves
        bg = _mpy_concatenate([bg_a, bg_b], method="compose")
 
    else:
        # Short scene - single image with Ken Burns zoom
        bg_arr = _make_background(_effective_image_path, W, H, heavy_blur=is_social_mockup)
        bg = _apply_ken_burns(bg_arr, duration)
 
    # Anti-black screen: if image failed to load, use fallback
    if _effective_image_path is None or not os.path.exists(_effective_image_path):
        fallback_path = os.path.join(os.path.dirname(_effective_image_path or os.path.join(os.getcwd(), "output", "images")), "fallback.jpg")
        if os.path.exists(fallback_path):
            print(f"[ANTI-BLACK] Using fallback image: {fallback_path}")
            _effective_image_path = fallback_path
            bg_arr = _make_background(_effective_image_path, W, H, heavy_blur=is_social_mockup)
            bg = _apply_ken_burns(bg_arr, duration)
  
    # Layer 2 - gradient
    grad_arr = _make_gradient_overlay(W, H)
    grad = ImageClip(grad_arr).with_duration(duration)
  
    # Layer 3 - progressive caption (word-by-word)
    # Timing should match the actual audio duration (if available)
    # but the clip must last the full scene duration.
    # Use PURE voice duration for caption timing
    # _pure_voice_duration = actual speech time (no buffer, no whoosh)
    # clip_duration = full scene duration (background stays alive)
    if _pure_voice_duration <= 0:
        # No audio: estimate from word count at natural speech rate
        _pure_voice_duration = max(1.5, len(text.split()) / 2.5)

    # Guard against clip_duration < timing_duration (causes caption cutoff)
    # This happens when audio was compressed to fit MAX_SCENE_TOTAL
    _caption_timing = _pure_voice_duration
    _caption_clip_dur = max(duration, _pure_voice_duration)

    caption_clip = _make_progressive_caption(
        text,
        timing_duration=_caption_timing,
        W=W, H=H,
        clip_duration=_caption_clip_dur
    )
    _sync_status = "OK" if _caption_clip_dur >= _caption_timing else "CLIPPED"
    print(f"[CAPTION SYNC] voice={_caption_timing:.2f}s | "
          f"scene={duration:.2f}s | clip={_caption_clip_dur:.2f}s | {_sync_status}")
  
    # Layer 4 - Lower third (all scenes)
    lower_arr = _make_lower_third(headline, news_source, location, W, H)
    lower_clip = ImageClip(lower_arr).with_duration(duration)
 
    # Layer 5 - Category banner (BREAKING on scene 0, type tag on others)
    CATEGORY_STYLES = {
        "war":        ("WAR",        (180, 30,  30)),
        "politics":   ("POLITICS",   (20,  60,  160)),
        "technology": ("TECH",       (20,  120, 80)),
        "business":   ("ECONOMY",    (150, 80,  20)),
        "disaster":   ("DISASTER",   (160, 60,  20)),
        "general":    ("NEWS",       (40,  40,  100)),
        "hook":       ("BREAKING",   (220, 30,  30)),
        "context":    ("CONTEXT",    (40,  40,  100)),
        "event":      ("DEVELOPING", (100, 40,  120)),
    }
 
    # Create social clip overlay
    social_clip = None
    if is_social_mockup and social_entity:
        _social_text_content = social_text if social_text else text
        social_arr = _make_social_mockup(social_entity, _social_text_content, W, H)
        social_clip = ImageClip(social_arr).with_duration(duration)

    layers = [bg.with_position("center"), grad]
    if social_clip:
        layers.append(social_clip)
    layers.extend([caption_clip, lower_clip])
 
    if scene_idx == 0:
        # Always BREAKING NEWS red on first scene
        banner_arr  = _make_breaking_news_banner(W, H)
    else:
        cat_label, cat_color = CATEGORY_STYLES.get(
            scene_type if scene_type else "general",
            ("NEWS", (40, 40, 100))
        )
        banner_arr = _make_breaking_news_banner(
            W, H, label=cat_label, bar_color=cat_color
        )
 
    banner_clip = ImageClip(banner_arr).with_duration(duration)
    layers.append(banner_clip)
 
    scene = CompositeVideoClip(layers, size=(W, H)).with_duration(duration)
    if audio_clip:
        scene = scene.with_audio(audio_clip)
  
    print(
        f"[VideoBuilder] Scene {scene_idx:02d} - {duration:.1f}s | "
        f"audio={'Y' if audio_clip else 'N'} | "
        f"image={'Y' if _effective_image_path else 'N'}"
    )
    return scene
 
 
def _fetch_second_image(scene: dict, index: int) -> str | None:
    """
    Fetch an alternative image for a scene's second visual sub-clip.
    Uses the second-ranked query from _build_query() to ensure
    visual variety - different query, different image.
    Returns image path or None.
    """
    try:
        from image_fetcher import _build_query, fetch_with_retry, \
                                  clean_query, IMAGE_DIR
        import hashlib, os
 
        ranked = _build_query(scene)
        # Skip the first query (already used for primary image)
        # Try queries 2, 3, 4 for a fresh image
        for alt_query in ranked[1:4]:
            alt_query = clean_query(alt_query)
            if not alt_query:
                continue
            alt_url = fetch_with_retry(alt_query, index + 1000)
            if alt_url:
                cache_key = hashlib.md5(alt_query.encode()).hexdigest()[:10]
                dest = os.path.join(
                    IMAGE_DIR,
                    f"scene_{index:02d}_b_{cache_key}.jpg"
                )
                import requests
                try:
                    r = requests.get(alt_url, timeout=10)
                    if r.status_code == 200:
                        with open(dest, "wb") as f:
                            f.write(r.content)
                        if os.path.getsize(dest) > 2048:
                            print(f"[VISUAL CUT] Alt image fetched for scene {index}")
                            return dest
                except Exception:
                    continue
    except Exception as exc:
        print(f"[VISUAL CUT] Alt image fetch failed: {exc}")
    return None
 
 
def remove_exact_duplicates(text: str) -> str:
    if not text:
        return text
    words = text.split()
    cleaned = []
    for w in words:
        if not cleaned or w.lower().rstrip(".,;!?") != cleaned[-1].lower().rstrip(".,;!?"):
            cleaned.append(w)
    return " ".join(cleaned)


def _generate_outro_audio(cta: dict = None, story_context: str = "neutral") -> str | None:
    """
    Generate short Piper TTS for the outro screen, or load human voice outro if available.
    """
    try:
        from config import BASE_DIR
        human_outro_path = os.path.join(BASE_DIR, "assets", "human_outro.wav")
        if os.path.isfile(human_outro_path):
            print(f"[OUTRO AUDIO] Found human outro file at {human_outro_path} -- using it instead of TTS!")
            return human_outro_path

        from voice_generator import generate_audio
        if cta:
            # Speak only the Call to Action line to keep it brief under 3s
            engage = remove_exact_duplicates(cta.get("engage_line", "Follow for daily news updates."))
            outro_text = engage
        else:
            outro_text = "Subscribe for daily news updates."

        print(f"[OUTRO AUDIO] Speaking: '{outro_text}'")
        # Use story_context so outro voice matches main narration
        print(f"[OUTRO AUDIO] Context: '{story_context}' (matches main narration)")
        return generate_audio(outro_text, index=998, context=story_context)
    except Exception as exc:
        print(f"[OUTRO AUDIO] TTS failed: {exc}")
        return None
 
 
# -- Public entry-point --------------------------------------------------------
def _build_outro_scene(
    audio_duration: float,
    audio_path: str = None,
    cta: dict = None,
    scene0_image: str = None,
) -> CompositeVideoClip:
    """
    Premium news-style outro scene - no image needed.

    Layout (top to bottom):
      +----------------------------------+
      |  [RED BAR]  AI NEWS       LIVE  |  - top branding (72px)
      |                                  |
      |         [WORLD MAP ICON]         |  - decorative circle
      |                                  |
      |   Stay Updated on World Affairs  |  - main headline
      |   Follow for daily news reels    |  - subtitle
      |                                  |
      |   [ SUBSCRIBE ]                  |  - fades in at t=1.5s
      |                                  |
      |   AI NEWS - Source: BBC News     |  - bottom credit
      +----------------------------------+
    """
    if cta is None:
        cta = {}
    main_line   = remove_exact_duplicates(cta.get("main_line",   "What do you think about this?"))
    sub_line    = remove_exact_duplicates(cta.get("sub_line",    "Share your thoughts below."))
    engage_line = remove_exact_duplicates(cta.get("engage_line", "Follow for daily news updates."))

    W, H = VIDEO_WIDTH, VIDEO_HEIGHT

    # ── Dynamic Duration Control ──────────────────────────────────────────
    # Enforce strict 1.0s - 1.5s maximum outro duration to prevent viewer drop-off
    OUTRO_MIN = OUTRO_MIN_DURATION
    OUTRO_MAX = OUTRO_MAX_DURATION
    if audio_path and os.path.isfile(audio_path):
        _outro_audio     = AudioFileClip(audio_path)
        _outro_narr_dur  = _outro_audio.duration   # this WAV file only
        duration = max(OUTRO_MIN, min(OUTRO_MAX, _outro_narr_dur + 0.1))
        # Ensure narration does not exceed clip duration
        if _outro_narr_dur > duration:
            if hasattr(_outro_audio, "subclipped"):
                _outro_audio = _outro_audio.subclipped(0, duration)
            elif hasattr(_outro_audio, "subclip"):
                _outro_audio = _outro_audio.subclip(0, duration)
        print(f"[OUTRO] Duration: {_outro_narr_dur:.2f}s narration -> {duration:.2f}s clip")
    else:
        _outro_audio    = None
        _outro_narr_dur = 0.0
        duration        = OUTRO_MAX
        print(f"[OUTRO] Duration: {duration:.2f}s clip (no narration)")
 
    def _make_outro_bg() -> np.ndarray:
        """
        Dynamic outro background:
          - If scene0_image is available: blur it at 35% opacity over
            dark navy (#0d1117) and apply a slow 1.0x->1.2x Ken Burns
            zoom across the outro duration for a premium newsroom look.
          - If not available: fall back to the original dark gradient.
        """
        DARK_NAVY = (13, 17, 23)

        if scene0_image and os.path.isfile(scene0_image):
            try:
                img = Image.open(scene0_image).convert("RGB")
                # Cover-scale to 1080x1920
                scale = max(1920 / img.height, 1080 / img.width)
                nw = max(int(img.width  * scale), 1080)
                nh = max(int(img.height * scale), 1920)
                img = img.resize((nw, nh), Image.LANCZOS)
                left = (nw - 1080) // 2
                top  = (nh - 1920) // 2
                img  = img.crop((left, top, left + 1080, top + 1920))

                # Apply 45px blur
                blurred = img.filter(ImageFilter.GaussianBlur(radius=45))

                # Composite at 35% opacity over dark navy
                base        = Image.new("RGB", (1080, 1920), DARK_NAVY)
                blurred_rgb = blurred.convert("RGBA")
                r, g, b, a  = blurred_rgb.split()
                a           = a.point(lambda x: int(255 * 0.35))
                blurred_rgb = Image.merge("RGBA", (r, g, b, a))
                composite   = Image.alpha_composite(
                    base.convert("RGBA"), blurred_rgb
                ).convert("RGB")
                return np.array(composite)

            except Exception as exc:
                print(f"[OUTRO BG] Scene0 image failed: {exc} - using gradient")

        # â”€â”€ Original dark gradient fallback â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        canvas = Image.new("RGB", (1080, 1920), DARK_NAVY)
        draw   = ImageDraw.Draw(canvas)
        for y in range(1920):
            t = y / 1920
            r = int(13 + (28 - 13) * (1 - t))
            g = int(17 + (35 - 17) * (1 - t))
            b = int(23 + (55 - 23) * (1 - t))
            draw.line([(0, y), (1080, y)], fill=(r, g, b))
        return np.array(canvas)
 
    # -- Subscribe button frame (PIL - no external assets) -----------------
    def _make_subscribe_btn(alpha: float) -> np.ndarray:
        """
        Renders the subscribe button as RGBA with given opacity (0.0 to 1.0).
        alpha is used to animate fade-in.
        """
        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw   = ImageDraw.Draw(canvas)

        btn_w, btn_h = 420, 90
        btn_x = (W - btn_w) // 2
        btn_y = int(H * 0.67)

        opacity = int(255 * min(max(alpha, 0.0), 1.0))

        # Button background - red pill
        draw.rounded_rectangle(
            [(btn_x, btn_y), (btn_x + btn_w, btn_y + btn_h)],
            radius=45,
            fill=(220, 30, 30, opacity)
        )

        # Bell icon drawn with PIL shapes (left side of button)
        bell_cx = btn_x + 60
        bell_cy = btn_y + btn_h // 2
        bell_r  = 18
        # Bell dome
        draw.ellipse(
            [(bell_cx - bell_r, bell_cy - bell_r),
             (bell_cx + bell_r, bell_cy + bell_r // 2)],
            fill=(255, 255, 255, opacity)
        )
        # Bell handle
        draw.rectangle(
            [(bell_cx - 5, bell_cy + bell_r // 2),
             (bell_cx + 5, bell_cy + bell_r)],
            fill=(255, 255, 255, opacity)
        )
        # Bell clapper (small dot below)
        draw.ellipse(
            [(bell_cx - 5, bell_cy + bell_r),
             (bell_cx + 5, bell_cy + bell_r + 8)],
            fill=(255, 255, 255, opacity)
        )

        # SUBSCRIBE text
        font_btn = _font(36, bold=True)
        btn_label = "SUBSCRIBE"
        try:
            tb = draw.textbbox((0, 0), btn_label, font_btn)
            tw = tb[2] - tb[0]
            th = tb[3] - tb[1]
        except AttributeError:
            tw, th = draw.textsize(btn_label, font_btn)

        text_x = btn_x + 95
        text_y = btn_y + (btn_h - th) // 2
        draw.text((text_x, text_y), btn_label,
                  font=font_btn, fill=(255, 255, 255, opacity))

        return np.array(canvas)

    # -- Static text layer -------------------------------------------------
    def _make_outro_text() -> np.ndarray:
        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw   = ImageDraw.Draw(canvas)

        # Main headline
        # Word-wrap the main CTA text to prevent clipping
        font_size = 46    # reduced from 52 -- safer default
        if len(main_line) > 60:
            font_size = 36
        elif len(main_line) > 45:
            font_size = 40
        elif len(main_line) > 30:
            font_size = 43

        font_main = _font(font_size, bold=True)
        main_text = main_line
        
        SAFE_W = W - 120   # 60px margin on each side
        _probe = Image.new("RGBA", (1, 1))
        _pd = ImageDraw.Draw(_probe)

        def _txt_w(t):
            try:
                bb = _pd.textbbox((0, 0), t, font=font_main)
                return bb[2] - bb[0]
            except AttributeError:
                return _pd.textsize(t, font=font_main)[0]

        # Check if text fits on one line
        if _txt_w(main_text) <= SAFE_W:
            # Single line -- center normally
            mw = _txt_w(main_text)
            draw.text(((W - mw) // 2, int(H * 0.54)),
                      main_text, font=font_main,
                      fill=(255, 255, 255, 255))
        else:
            # WRAP: split into two lines at nearest space to midpoint
            words = main_text.split()
            best_split = len(words) // 2
            for _off in range(len(words) // 2 + 1):
                for _idx in [len(words) // 2 + _off, len(words) // 2 - _off]:
                    if 0 < _idx < len(words):
                        l1 = " ".join(words[:_idx])
                        l2 = " ".join(words[_idx:])
                        if _txt_w(l1) <= SAFE_W and _txt_w(l2) <= SAFE_W:
                            best_split = _idx
                            break
                else:
                    continue
                break

            l1 = " ".join(words[:best_split])
            l2 = " ".join(words[best_split:])

            _lh = font_size + 8   # line height
            _y1 = int(H * 0.50)
            _y2 = _y1 + _lh

            mw1 = _txt_w(l1)
            mw2 = _txt_w(l2)
            draw.text(((W - mw1) // 2, _y1), l1, font=font_main,
                      fill=(255, 255, 255, 255))
            draw.text(((W - mw2) // 2, _y2), l2, font=font_main,
                      fill=(255, 255, 255, 255))

        # Sub headline
        font_sub = _font(38, bold=False)
        sub_text = sub_line
        try:
            sb = draw.textbbox((0, 0), sub_text, font_sub)
            sw = sb[2] - sb[0]
        except AttributeError:
            sw, _ = draw.textsize(sub_text, font=font_sub)
        draw.text(((W - sw) // 2, int(H * 0.54) + 62),
                  sub_text, font=font_sub,
                  fill=(200, 200, 200, 220))

        # Subtitle
        font_caption = _font(28, bold=False)
        cap_text = engage_line
        try:
            cb = draw.textbbox((0, 0), cap_text, font_caption)
            cw = cb[2] - cb[0]
        except AttributeError:
            cw, _ = draw.textsize(cap_text, font=font_caption)
        draw.text(((W - cw) // 2, int(H * 0.62)),
                  cap_text, font=font_caption,
                  fill=(140, 140, 160, 200))

        # Bottom credit line
        font_credit = _font(24, bold=False)
        credit_text = f"{BRAND_NAME}  -  Powered by AI"
        try:
            crb = draw.textbbox((0, 0), credit_text, font_credit)
            crw = crb[2] - crb[0]
        except AttributeError:
            crw, _ = draw.textsize(credit_text, font=font_credit)
        draw.text(((W - crw) // 2, int(H * 0.88)),
                  credit_text, font=font_credit,
                  fill=(100, 100, 120, 180))

        return np.array(canvas)
 
    # -- Breaking banner for outro -----------------------------------------
    outro_banner_arr = _make_breaking_news_banner(W, H)
 
    # -- Assemble layers ---------------------------------------------------
    bg_arr   = _make_outro_bg()
    text_arr = _make_outro_text()
 
    # Ken Burns: slow zoom 1.0x -> 1.2x across outro duration
    _bg_pil = Image.fromarray(bg_arr)

    def _outro_zoom_frame(t):
        progress = t / max(duration, 0.01)
        scale    = 1.0 + 0.20 * progress   # 1.0 -> 1.2
        new_w    = int(1080 * scale)
        new_h    = int(1920 * scale)
        resized  = _bg_pil.resize((new_w, new_h), Image.LANCZOS)
        left     = (new_w - 1080) // 2
        top      = (new_h - 1920) // 2
        cropped  = resized.crop((left, top, left + 1080, top + 1920))
        return np.array(cropped)

    bg_clip = VideoClip(_outro_zoom_frame, duration=duration)
    text_clip = ImageClip(text_arr).with_duration(duration)
    banner_clip = ImageClip(outro_banner_arr).with_duration(duration)
 
    # Animated subscribe button - fades in immediately from t=0.0s over 0.25s
    FADE_START = 0.0
    FADE_DUR   = 0.25

    def make_subscribe_frame(t):
        # Returns 3-channel RGB array
        btn_rgba = _make_subscribe_btn(1.0)  # always fully opaque RGB base
        return btn_rgba[:, :, :3]

    def make_subscribe_mask(t):
        # Returns 1-channel float array (0.0 to 1.0) for transparency fade
        if t < FADE_START:
            alpha = 0.0
        elif t < FADE_START + FADE_DUR:
            alpha = (t - FADE_START) / FADE_DUR
        else:
            alpha = 1.0
        
        # Extract the alpha channel from fully opaque base and multiply by fade progress
        btn_rgba = _make_subscribe_btn(1.0)
        alpha_channel = btn_rgba[:, :, 3] / 255.0
        return alpha_channel * alpha

    subscribe_clip = VideoClip(make_subscribe_frame, duration=duration)
    subscribe_mask = VideoClip(make_subscribe_mask, ismask=True, duration=duration)
    subscribe_clip = subscribe_clip.with_mask(subscribe_mask)
 
    if audio_path and os.path.isfile(audio_path) and _outro_audio is None:
        _outro_audio = AudioFileClip(audio_path)
    elif not (audio_path and os.path.isfile(audio_path)):
        _outro_audio = None
 
    outro = CompositeVideoClip(
        [bg_clip, text_clip, subscribe_clip, banner_clip],
        size=(W, H)
    ).with_duration(duration)
 
    outro = outro.with_effects([vfx.FadeIn(0.3)])
 
    if _outro_audio:
        outro = outro.with_audio(_outro_audio)
 
    print(f"[OUTRO] Built outro scene - {duration:.2f}s | "
          f"audio={'Y' if _outro_audio else 'N'}")
    return outro
 
 
def _generate_ambient_tone(duration: float, output_path: str) -> str | None:
    """
    Generate a subtle ambient atmosphere tone using numpy - no external
    audio files needed.
 
    Technique:
      - Low sub-bass rumble at 45Hz (tension/seriousness feel)
      - Very faint high-frequency air at 8000Hz (room presence)
      - Both mixed at extremely low volume (0.04 = 4%)
      - Output: WAV file at 44100 Hz mono
 
    The result is a barely-audible background texture that adds depth
    without distracting from the voiceover.
    """
    try:
        import wave
 
        SAMPLE_RATE  = 44100
        VOLUME_BASS  = 0.03   # 3% - sub-bass rumble
        VOLUME_AIR   = 0.015  # 1.5% - high-frequency air presence
        FREQ_BASS    = 45     # Hz - low tension rumble
        FREQ_AIR     = 6000   # Hz - room presence / air
 
        num_samples = int(SAMPLE_RATE * duration)
        t_arr = np.linspace(0, duration, num_samples, endpoint=False)
 
        # Bass rumble - pure sine at very low volume
        bass = VOLUME_BASS * np.sin(2 * np.pi * FREQ_BASS * t_arr)
 
        # Air presence - sine at high frequency, even quieter
        air  = VOLUME_AIR * np.sin(2 * np.pi * FREQ_AIR * t_arr)
 
        # Add very subtle noise floor (room ambience)
        noise = 0.008 * np.random.normal(0, 1, num_samples)
 
        # Mix all layers
        mixed = bass + air + noise
 
        # Soft fade-in and fade-out (0.5s each) to avoid clicks
        fade_samples = int(SAMPLE_RATE * 0.5)
        fade_in  = np.linspace(0, 1, fade_samples)
        fade_out = np.linspace(1, 0, fade_samples)
        mixed[:fade_samples]  *= fade_in
        mixed[-fade_samples:] *= fade_out
 
        # Clamp to [-1, 1] and convert to 16-bit PCM
        mixed = np.clip(mixed, -1.0, 1.0)
        pcm   = (mixed * 32767).astype(np.int16)
 
        # Write WAV file
        with wave.open(output_path, 'w') as wf:
            wf.setnchannels(1)       # mono
            wf.setsampwidth(2)       # 16-bit
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(pcm.tobytes())
 
        print(f"[AMBIENT] Generated tone - {duration:.1f}s -> {output_path}")
        return output_path
 
    except Exception as exc:
        print(f"[AMBIENT] Generation failed: {exc} - skipping ambient audio")
        return None
 
 
def _generate_news_music(duration: float, context: str, output_path: str) -> str | None:
    """
    Generate context-appropriate background music using ffmpeg.
    PHASE 13: Simplified filter chain -- reliable at all durations.
    """
    import subprocess
    import shutil
    import os

    if not shutil.which("ffmpeg"):
        print("[MUSIC] ffmpeg not found -- skipping")
        return None

    # Map context to frequency pairs (bass, harmony) and master volume
    PROFILES = {
        "tense":       (55,  110, 0.055),
        "war":         (55,  82,  0.055),
        "serious":     (82,  110, 0.045),
        "politics":    (165, 220, 0.060),
        "neutral":     (220, 330, 0.055),
        "informative": (330, 440, 0.060),
        "business":    (165, 220, 0.060),
        "positive":    (330, 440, 0.070),
        "disaster":    (55,  82,  0.055),
    }
    f1, f2, vol = PROFILES.get(context, PROFILES["neutral"])

    # Simple reliable filter -- two sine waves mixed, faded in/out
    # No concat, no ident burst -- just clean ambient bed
    fade_in  = 1.5
    fade_out_start = max(duration - 2.5, duration * 0.80)
    fade_out = 2.0

    filter_complex = (
        f"sine=frequency={f1}:duration={duration:.3f}[a];"
        f"sine=frequency={f2}:duration={duration:.3f}[b];"
        f"[a][b]amix=inputs=2:duration=first:dropout_transition=0,"
        f"volume={vol},"
        f"afade=t=in:st=0:d={fade_in},"
        f"afade=t=out:st={fade_out_start:.3f}:d={fade_out}"
    )

    cmd = [
        "ffmpeg", "-y",
        "-filter_complex", filter_complex,
        "-t", f"{duration:.3f}",   # explicit duration cap prevents truncation
        "-ar", "44100",
        "-ac", "2",
        "-acodec", "libmp3lame",
        "-b:a", "96k",             # fixed bitrate -- more predictable than -q:a
        output_path,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=60)
        if result.returncode == 0 and os.path.isfile(output_path):
            size_kb = os.path.getsize(output_path) // 1024
            # Validate: at 96kbps, 1s â‰ˆ 12KB. File should be >= duration*8 KB
            expected_min_kb = int(duration * 8)
            if size_kb < expected_min_kb:
                print(f"[MUSIC] WARNING:ï¸  File too small ({size_kb}KB for {duration:.1f}s) "
                      f"-- expected â‰¥{expected_min_kb}KB. Music may be truncated.")
            else:
                print(f"[MUSIC] Generated {context} music: {size_kb}KB, {duration:.1f}s OK")
            return output_path
        stderr = result.stderr.decode("utf-8", errors="replace")[-300:]
        print(f"[MUSIC] ffmpeg failed (rc={result.returncode}): {stderr}")
        return None
    except Exception as exc:
        print(f"[MUSIC] Error: {exc}")
        return None



def _build_map_stinger(
    map_image_path: str,
    location: str,
    headline: str,
    hook_text: str = "",               # hook narration sentence for progressive captions
    audio_path: str = None,
    duration: float = MAP_STINGER_DURATION,   # default; overridden by hook audio when available
) -> CompositeVideoClip:
    """Opening map scene with location pin and headline text. Duration matches hook audio."""
    W, H = VIDEO_WIDTH, VIDEO_HEIGHT

    MAP_MAX_DURATION = MAP_STINGER_MAX   # read from config (change to 7.0)
    MAP_MIN_DURATION = MAP_STINGER_MIN   # keep at 3.5

    _map_audio = None
    _actual_audio_dur = 0.0

    if audio_path and os.path.isfile(audio_path):
        _map_audio = AudioFileClip(audio_path)
        _actual_audio_dur = _map_audio.duration
        
        # NEW: If hook audio is longer than 7.5 seconds, the hook sentence is too long.
        # Cap at 7.0 and truncate the audio to match — don't play excess silence/audio.
        if _actual_audio_dur > 7.5:
            print(f"[MAP STINGER] Audio {_actual_audio_dur:.2f}s exceeds 7.5s cap "
                  f"— hook sentence was too long, capping to 7.0s")
            _actual_audio_dur = min(_actual_audio_dur, 7.0)
            # Subclip the audio to avoid narrating past the cap
            if hasattr(_map_audio, "subclipped"):
                _map_audio = _map_audio.subclipped(0, min(7.0, _map_audio.duration))
            elif hasattr(_map_audio, "subclip"):
                _map_audio = _map_audio.subclip(0, min(7.0, _map_audio.duration))
        
        # High-retention fast cut: clip finishes right as hook ends (0.10s pad instead of 0.5s dead silence)
        duration = max(2.0, min(MAP_MAX_DURATION, _actual_audio_dur + 0.10))
        print(f"[MAP STINGER] Audio={_actual_audio_dur:.2f}s -> clip={duration:.2f}s")
    else:
        duration = min(2.5, MAP_MIN_DURATION)
 
    bg_arr = _make_background(map_image_path, W, H)

    # Lazy Ken Burns for map stinger — no pre-rendering
    _bg_pil_map = Image.fromarray(bg_arr)
    _h_map, _w_map = bg_arr.shape[:2]
    _map_resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS", 1)
    _map_frame_cache = {}

    def _map_zoom_frame(t):
        frame_idx = int(round(t * VIDEO_FPS))
        if frame_idx in _map_frame_cache:
            return _map_frame_cache[frame_idx]
        t_norm = min(max(t / max(duration, 0.01), 0.0), 1.0)
        scale = 1.0 + KEN_BURNS_ZOOM_FACTOR * t_norm
        nw = max(1, int(_w_map / scale))
        nh = max(1, int(_h_map / scale))
        x1 = (_w_map - nw) // 2
        y1 = (_h_map - nh) // 2
        frame = np.array(
            _bg_pil_map.crop((x1, y1, x1 + nw, y1 + nh)).resize(
                (_w_map, _h_map), _map_resample
            )
        )
        # Bound cache to last 48 frames (2 seconds) to limit memory
        if len(_map_frame_cache) > 48:
            oldest = min(_map_frame_cache.keys())
            del _map_frame_cache[oldest]
        _map_frame_cache[frame_idx] = frame
        return frame

    bg = VideoClip(_map_zoom_frame, duration=duration)
    bg.fps = VIDEO_FPS
    print(f"[MAP ANIMATION] Lazy Ken Burns configured for {duration:.1f}s")
 
    grad_arr  = _make_gradient_overlay(W, H)
    grad_clip = ImageClip(grad_arr).with_duration(duration)
 
    def _make_map_text() -> np.ndarray:
        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw   = ImageDraw.Draw(canvas)
        font_loc = _font(40, bold=True)

        # Shorten long location names for clean display
        _DISPLAY_LOCS = {
            "democratic republic of congo": "DR CONGO",
            "the democratic republic of congo": "DR CONGO",
            "united states of america": "UNITED STATES",
            "united arab emirates": "UAE",
        }
        _display_loc = _DISPLAY_LOCS.get(location.lower(), location.upper())
        # Cap at 25 chars to prevent text overflow
        if len(_display_loc) > 25:
            _display_loc = _display_loc[:22] + "..."

        loc_label = f"\U0001F4CD {_display_loc}"   # 📍 pin emoji
        try:
            lb = draw.textbbox((0, 0), loc_label, font=font_loc)
            lw, lh = lb[2]-lb[0], lb[3]-lb[1]
        except AttributeError:
            lw, lh = len(loc_label)*24, 50
        px, py = 40, 22
        lx = (W - lw) // 2
        ly = int(H * 0.52)   # slightly higher to not overlap caption at 68%
        # Dark pill background
        draw.rounded_rectangle(
            [(lx-px, ly-py), (lx+lw+px, ly+lh+py)],
            radius=14, fill=(13, 17, 23, 220)
        )
        # Red left accent bar
        draw.rounded_rectangle(
            [(lx-px, ly-py), (lx-px+6, ly+lh+py)],
            radius=14, fill=(*ACCENT_COLOR, 255)
        )
        draw.text((lx, ly), loc_label, font=font_loc, fill=(255, 255, 255, 255))

        # Dynamically position sub-headline based on actual rendered height
        font_hl = _font(26, bold=False)
        hl = headline[:55]+"..." if len(headline)>55 else headline
        try:
            hb = draw.textbbox((0, 0), hl, font=font_hl)
            hw = hb[2] - hb[0]
        except AttributeError:
            hw, _ = draw.textsize(hl, font=font_hl)
        _sub_y = ly + lh + py + 18   # dynamic Y based on actual pill height
        draw.text(
            ((W - hw) // 2, _sub_y),
            hl,
            font=font_hl,
            fill=(210, 210, 210, 180)
        )
        return np.array(canvas)
 
    text_clip   = ImageClip(_make_map_text()).with_duration(duration)
    banner_clip = ImageClip(_make_breaking_news_banner(W, H)).with_duration(duration)
    _pure_map_narr_dur = _actual_audio_dur if _actual_audio_dur > 0 else max(1.0, duration - 0.10)

    # Progressive caption for hook narration (same system as all other scenes)
    map_caption_clip = None
    if hook_text and hook_text.strip():
        _hook_timing = max(1.0, _pure_map_narr_dur)
        _caption_clip_dur = duration

        map_caption_clip = _make_progressive_caption(
            hook_text,
            timing_duration=_hook_timing,
            W=W, H=H,
            clip_duration=_caption_clip_dur,
        )
        print(f"[MAP CAPTION] hook_timing={_hook_timing:.2f}s, clip={_caption_clip_dur:.2f}s")

    _map_layers = [bg.with_position("center"), grad_clip, text_clip]
    if map_caption_clip is not None:
        _map_layers.append(map_caption_clip)   # caption before banner so it's visible
    _map_layers.append(banner_clip)

    stinger = CompositeVideoClip(
        _map_layers,
        size=(W, H)
    ).with_duration(duration)
 
    if _map_audio:
        stinger = stinger.with_audio(_map_audio)
 
    print(f"[MAP STINGER] Built {duration}s map scene for '{location}' | "
          f"audio={'Y' if _map_audio else 'N'}")
    return stinger
 
 
def build_video(scenes: list[dict], pipeline_meta: dict = None, visual_cut_threshold: float = 2.8) -> str:
    global _last_valid_bg_arr
    _last_valid_bg_arr = None   # reset so first scene never inherits stale frame
    if not scenes:
        raise ValueError("[VideoBuilder] No scenes provided.")
  
    scene_durations = []
    WORDS_PER_SECOND = 2.0
    for idx, scene in enumerate(scenes):
        audio_path = scene.get("audio_path")
        words = scene["text"].split()
        if audio_path and os.path.isfile(audio_path):
            audio_clip = AudioFileClip(audio_path)
            duration = audio_clip.duration
            audio_clip.close()
        else:
            duration = len(words) * 0.6
        duration = max(2.0, min(duration, 9.5))   # raised cap from 9.0 to 9.5 for tail buffer room
        scene_durations.append(duration)
 
    total_duration = sum(scene_durations)
 
    # 85s ceiling prevents audio overlap.
    # Previous 49s caused compression, so audio bled across scene boundaries.
    # With 85s ceiling, a 9-scene x 5.75s video fits without compression.
    MAX_SCENE_TOTAL  = 85.0   # raised from 49.0
    MIN_SCENE_TOTAL  = 35.0
    MAX_SCALE_UP     = 1.15   # gentle; primary fix is better scripting, not stretching

    if total_duration > MAX_SCENE_TOTAL:
        scale = MAX_SCENE_TOTAL / total_duration

        # If compression is > 5%, drop excess middle scenes
        # rather than compressing all scenes and causing audio overlap.
        # A 0.90x compression means every scene's audio bleeds 10% into the next.
        MIN_SCALE = SCENE_COMPRESSION_MIN_SCALE
        if scale < MIN_SCALE:
            # Drop scenes from the MIDDLE (preserve hook scene 0 and last scene)
            _scenes_needed = int(MAX_SCENE_TOTAL / (total_duration / len(scenes)))
            _scenes_needed = max(6, min(_scenes_needed, len(scenes) - 1))
            print(f"[VIDEO] Compression would be {scale:.2f}x -- too aggressive. "
                  f"Dropping {len(scenes) - _scenes_needed} middle scene(s) to avoid overlap.")
            _hook  = scenes[0]
            _close = scenes[-1]
            _mid   = scenes[1:-1]
            # Keep the shortest-audio middle scenes (less overflow risk)
            _mid_sorted = sorted(_mid, key=lambda s: len(s.get("text","").split()))
            _keep = _mid_sorted[:_scenes_needed - 2]
            # Restore original order
            _keep_ordered = sorted(_keep, key=lambda s: scenes.index(s))
            scenes = [_hook] + _keep_ordered + [_close]
            scene_durations = [scene_durations[scenes.index(s)] if s in scenes
                               else 0 for s in scenes]
            # Recompute durations from scratch for the trimmed scenes
            scene_durations = []
            for _s in scenes:
                _ap = _s.get("audio_path")
                if _ap and os.path.isfile(_ap):
                    _ac = AudioFileClip(_ap)
                    scene_durations.append(max(2.0, min(_ac.duration, 9.5)))
                    _ac.close()
                else:
                    scene_durations.append(5.0)
            total_duration = sum(scene_durations)
            scale = min(MAX_SCENE_TOTAL / total_duration, 1.0)
            print(f"[VIDEO] After scene drop: {len(scenes)} scenes, "
                  f"new duration {total_duration:.1f}s, scale {scale:.2f}x")

        scene_durations = [d * scale for d in scene_durations]
        print(f"[VIDEO] Compressed to fit: x{scale:.2f}")
    elif total_duration < MIN_SCENE_TOTAL:
        scale = min(MIN_SCENE_TOTAL / total_duration, MAX_SCALE_UP)
        scene_durations = [d * scale for d in scene_durations]
        print(f"[VIDEO] Expanded gently: x{scale:.2f} (cap={MAX_SCALE_UP}x)")


    # Per-scene clamp with raised cap + minimum 0.20s tail buffer applied to ALL scenes
    scene_durations = [max(2.0, min(d, 9.5)) for d in scene_durations]
    # Apply 0.20s tail buffer to every scene (not just the last one)
    # This prevents audio overlap when scenes hit the 9.0s natural cap
    scene_durations = [
        min(d + 0.20, 9.5)
        for d in scene_durations
    ]
    print(f"[VIDEO] Scene total: {sum(scene_durations):.1f}s")

    # -- Final scene audio padding --------------------------------------
    # Add 0.5s to the last content scene so Piper's final phoneme is
    # never clipped by MoviePy's frame-exact concatenation boundary.
    # This does not affect the outro - the outro is appended separately.
    if scene_durations:
        scene_durations[-1] = min(
            scene_durations[-1] + 0.30,   # extra 0.30s on last scene (in addition to the 0.20s all-scene buffer)
            9.5
        )
        print(f"[PADDING] Final scene extended to {scene_durations[-1]:.2f}s (+0.30s audio buffer)")

    # Per-scene overlap audit - warn if scene clip is shorter than audio
    _overlap_detected = False
    for _ai, (_scene, _dur) in enumerate(zip(scenes, scene_durations)):
        _ap = _scene.get("audio_path")
        if _ap and os.path.isfile(_ap):
            _ac = AudioFileClip(_ap)
            _raw = _ac.duration
            _ac.close()
            _tail = _dur - _raw
            _flag = ""
            if _tail < 0.15:
                _flag = "  !! OVERLAP RISK !!"
                _overlap_detected = True
            elif _tail < 0.25:
                _flag = "  (tight)"
            print(f"[SCENE {_ai:02d}] audio={_raw:.2f}s | clip={_dur:.2f}s | tail={_tail:.2f}s{_flag}")
    if _overlap_detected:
        print("[VIDEO] !! Audio overlap risk detected - increase MAX_SCENE_TOTAL or shorten script !!")

    print(f"[PIPELINE] Total scenes planned: {len(scenes)}")
    print(f"[CONTEXT] Story type: {pipeline_meta.get('story_context', 'unknown') if pipeline_meta else 'unknown'}")
    print(f"[VIDEO] Scene total: {sum(scene_durations):.1f}s (target <={MAX_SCENE_TOTAL}s)")
 
    # Pre-flight scene validation — catch issues before rendering
    _scene_issues = []
    for _vi, _vs in enumerate(scenes):
        _vt = _vs.get("text", "")
        _vwords = _vt.split()
        if not _vwords:
            continue

        # Check for orphan starters (sentence fragments from bad splits)
        _ORPHAN_STARTERS_CHECK = {"symptoms", "down", "about", "up", "out", "off", "via", "however", "also"}
        if _vwords[0].lower().rstrip(".,") in _ORPHAN_STARTERS_CHECK:
            _scene_issues.append(f"Scene {_vi:02d}: Orphan starter '{_vwords[0]}'")

        # Check for bare number endings
        import re as _vr
        _last_clean = _vwords[-1].rstrip('.!?,;')
        if _vr.match(r'^\d+$', _last_clean):
            _scene_issues.append(f"Scene {_vi:02d}: Bare number ending '{_vwords[-1]}'")

        # Check for truncated sentences (ends with dangling adjective)
        _last_lc = _vt.rstrip(".!?,;: ").split()[-1].lower() if _vwords else ""
        _SOFT_BAD = {"healthcare", "military", "social", "political", "economic",
                     "national", "international", "local", "global", "federal"}
        if _last_lc in _SOFT_BAD:
            _scene_issues.append(f"Scene {_vi:02d}: Truncated at '{_last_lc}'")

    if _scene_issues:
        print(f"[PRE-FLIGHT] {len(_scene_issues)} scene issue(s) detected:")
        for _issue in _scene_issues:
            print(f"  \u26a0 {_issue}")
    else:
        print("[PRE-FLIGHT] All scenes passed validation")

    clips = []
 
    # -- Location map stinger -----------------------------------------
    # Map stinger is eliminated for short-format videos (fmt == 'short' or pipeline_meta show_map is False)
    # Videos start immediately at 0.0s on Scene 0 with full-bleed action visual and headline overlay.
    has_map_stinger = False
    _is_short = True
    if pipeline_meta:
        if pipeline_meta.get("fmt") == "long" or pipeline_meta.get("format") == "long":
            _is_short = False
        if not pipeline_meta.get("show_map", False):
            _is_short = True

    if not _is_short and pipeline_meta:
        map_path = pipeline_meta.get("map_image_path")
        location = pipeline_meta.get("primary_location", "")
        headline = pipeline_meta.get("headline", "")
        if map_path and os.path.isfile(map_path) and location:
            try:
                stinger = _build_map_stinger(
                    map_image_path=map_path,
                    location=location,
                    headline=headline,
                    hook_text=pipeline_meta.get("map_hook_text", ""),    # pass hook text for captions
                    duration=MAP_STINGER_DURATION,
                    audio_path=pipeline_meta.get("map_audio_path"),
                )
                clips.append(stinger)
                has_map_stinger = True
                print("[MAP STINGER] Prepended to video")
            except Exception as exc:
                print(f"[MAP STINGER] Failed: {exc} - skipping")
        else:
            print("[MAP STINGER] No map available - skipping")
    else:
        print("[MAP STINGER] Bypassed for short-format video (starts immediately at 0.0s on Scene 0)")
 
    for idx, scene in enumerate(scenes):
        clip = _build_scene_clip(
            image_path=scene.get("image_path"),
            audio_path=scene.get("audio_path"),
            text=scene["text"],
            scene_idx=idx,
            final_duration=scene_durations[idx],
            headline=scene.get("headline", ""),
            news_source=scene.get("news_source", "BBC News"),
            location=scene.get("entities", {}).get("location", ""),
            scene_type=scene.get("type", "general"),
            alt_image_path=scene.get("alt_image_path"),
            visual_cut_threshold=visual_cut_threshold,
            is_social_mockup=scene.get("is_social_mockup", False),
            social_entity=scene.get("social_entity", ""),
            social_text=scene.get("social_text", ""),
            is_transition=scene.get("is_transition", False) or scene.get("type") == "transition",
        )
        clips.append(clip)
  
    # -- Append outro scene ------------------------------------------------
    print("[VideoBuilder] Building outro scene...")

    # Generate story-specific CTA for this video's outro
    try:
        from script_generator import generate_dynamic_cta as _gen_cta
        _headline = (pipeline_meta.get("headline", "")
                     if pipeline_meta else "")
        _channel_name = (pipeline_meta.get("channel", "newscup")
                         if pipeline_meta else "newscup")
        _cta_ctx = (pipeline_meta.get("story_context", "neutral")
                    if pipeline_meta else "neutral")
        _cta = _gen_cta(_headline, _cta_ctx, channel_name=_channel_name)
        print(f"[CTA] Generated for context='{_cta_ctx}' on channel='{_channel_name}'")
        print(f"[CTA] main='{_cta.get('main_line', '')}'")
        print(f"[CTA] sub='{_cta.get('sub_line', '')}'")
        print(f"[CTA] engage='{_cta.get('engage_line', '')}'")
    except Exception as _exc:
        print(f"[CTA] Generation failed: {_exc} - using defaults")
        _cta = {}

    _outro_ctx = (
        pipeline_meta.get("story_context", "neutral")
        if pipeline_meta else "neutral"
    )
    outro_audio = _generate_outro_audio(cta=_cta, story_context=_outro_ctx)

    # Pass scene 0 image path for the dynamic outro background
    _scene0_img = scenes[0].get("image_path") if scenes else None

    # Calculate main audio duration
    try:
        # Combine all scene audio durations to get main audio duration
        main_audio_duration = sum([c.duration for c in clips if c.audio is not None])
    except Exception:
        main_audio_duration = 30.0

    outro_clip = _build_outro_scene(
        audio_duration=main_audio_duration,
        audio_path=outro_audio,
        cta=_cta,
        scene0_image=_scene0_img,
    )
    clips.append(outro_clip)
 
    print(f"[VideoBuilder] Concatenating {len(clips)} scene(s) + outro...")
    final = _mpy_concatenate(clips, method="compose")
  
    # -- Background music generation and mixing ----------------------------
    total_duration = final.duration
    # Music context selection -- priority order:
    # 1. pipeline_meta["story_context"] IF it's a meaningful context (not neutral/general)
    # 2. Scene type voting (count which scene type appears most)
    # 3. "neutral" as last resort
    _pm_ctx = (pipeline_meta.get("story_context", "") or "") if pipeline_meta else ""

    _MEANINGFUL_CONTEXTS = {"tense", "war", "serious", "politics", "positive",
                             "informative", "business", "disaster"}

    if _pm_ctx in _MEANINGFUL_CONTEXTS:
        _context_for_music = _pm_ctx
        print(f"[MUSIC] Context from pipeline: '{_context_for_music}'")
    else:
        # Vote from scene types
        _type_votes = {}
        for _s in scenes:
            _t = _s.get("type", "general")
            _type_votes[_t] = _type_votes.get(_t, 0) + 1
        _dominant = max(_type_votes, key=_type_votes.get) if _type_votes else "general"
        _TYPE_MUSIC = {
            "war": "war", "politics": "politics",
            "disaster": "serious", "business": "business",
            "technology": "informative", "general": "neutral",
        }
        _context_for_music = _TYPE_MUSIC.get(_dominant, "neutral")
        # If pipeline gave us something useful (even if not in _MEANINGFUL_CONTEXTS)
        if _pm_ctx and _pm_ctx not in ("neutral", "general", ""):
            _context_for_music = _pm_ctx
        print(f"[MUSIC] Context: '{_context_for_music}' "
              f"(pipeline='{_pm_ctx}', dominant_scene='{_dominant}')")
    
    # Calculate time intervals for all quote/tweet/document overlay scenes during video assembly
    current_time = 0.0
    duck_intervals = []
    
    clip_idx = 0
    if has_map_stinger:
        current_time += clips[clip_idx].duration
        clip_idx += 1
            
    for idx, scene in enumerate(scenes):
        scene_clip = clips[clip_idx]
        scene_type = scene.get("type", "general")
        if scene_type in ("quote_card", "tweet_overlay", "evidence_graphic"):
            duck_intervals.append((current_time, current_time + scene_clip.duration))
            print(f"[DUCK INTERVAL] Added: {current_time:.2f}s to {current_time + scene_clip.duration:.2f}s (scene {idx})")
        current_time += scene_clip.duration
        clip_idx += 1

    def make_duck_filter(intervals):
        def filter_fn(gf, t):
            import numpy as np
            frame = gf(t)
            if isinstance(t, (int, float)):
                factor = 1.0
                for start, end in intervals:
                    if start <= t <= end:
                        factor = 0.2083 # 0.025 / 0.12
                        break
                return frame * factor
            else:
                factor = np.ones(len(t))
                for start, end in intervals:
                    factor = np.where((t >= start) & (t <= end), 0.2083, factor)
                if len(frame.shape) > 1:
                    return frame * factor[:, np.newaxis]
                return frame * factor
        return filter_fn

    _music_path = OUTPUT_VIDEO.replace(".mp4", "_bgmusic.mp3")
    _music_file = _generate_news_music(total_duration, _context_for_music, _music_path)

    if _music_file and os.path.isfile(_music_file):
        try:
            _music_audio = AudioFileClip(_music_file)
            # Validate music actually has content
            _min_music_dur = max(final.duration * 0.92, final.duration - 1.5)
            if _music_audio.duration < 5.0:
                print(f"[MUSIC] WARNING: Music only {_music_audio.duration:.1f}s - skipping")
                _music_audio = None
            elif _music_audio.duration < _min_music_dur:
                print(f"[MUSIC] WARNING: Music {_music_audio.duration:.1f}s < "
                      f"required {_min_music_dur:.1f}s - regenerating")
                _music_audio.close()
                # Retry music generation with extended duration
                _music_file2 = _generate_news_music(
                    final.duration + 2.0, _context_for_music,
                    _music_path.replace(".mp3", "_retry.mp3")
                )
                if _music_file2:
                    _music_audio = AudioFileClip(_music_file2)
                else:
                    _music_audio = None
            
            if final.audio is not None and _music_audio is not None:
                if duck_intervals:
                    print(f"[MUSIC] Applying dynamic volume ducking for {len(duck_intervals)} intervals")
                    _music_audio = _music_audio.fl(make_duck_filter(duck_intervals))
                # Mix at reduced volume to not overpower voice
                # Narration at 100%, music at ~15% via the music generator's volume setting
                _mixed = CompositeAudioClip([final.audio, _music_audio])
                _mixed.duration = final.duration
                final = final.with_audio(_mixed)
                print(f"[MUSIC] OK Mixed into video - context='{_context_for_music}', "
                      f"music_dur={_music_audio.duration:.1f}s, video_dur={final.duration:.1f}s")
            elif _music_audio is not None:
                if duck_intervals:
                    print(f"[MUSIC] Applying dynamic volume ducking for {len(duck_intervals)} intervals")
                    _music_audio = _music_audio.fl(make_duck_filter(duck_intervals))
                final = final.with_audio(_music_audio)
                print("[MUSIC] Background music set (no voice track to mix)")
        except Exception as _me:
            print(f"[MUSIC] Mix failed: {_me} - proceeding without music")

 
    # -- MoviePy 1.x audio duration fix ----------------------------------
    try:
        if final.audio is not None:
            actual_duration = sum(c.duration for c in clips if hasattr(c, 'duration'))
            final.audio.duration = actual_duration
            print(f"[VIDEO] Audio duration fixed: {actual_duration:.2f}s")
    except Exception as e:
        print(f"[VIDEO] Audio duration fix skipped: {e}")

    print(f"[VIDEO] Rendering started...")
    print(f"[VIDEO] Output path: {OUTPUT_VIDEO}")
    print(f"[VideoBuilder] Rendering -> {OUTPUT_VIDEO}")

    _tmp_audio_path = OUTPUT_VIDEO.replace(".mp4", "_tmp_audio.m4a")
    try:
        final.write_videofile(
            OUTPUT_VIDEO,
            fps=VIDEO_FPS,
            codec="libx264",
            audio_codec="aac",
            audio_fps=44100,
            threads=4,
            preset="veryfast",
            ffmpeg_params=[
                "-crf", "23",
                "-movflags", "+faststart",
                "-force_key_frames", "0",      # force keyframe at t=0 - eliminates black first frames
                "-g", "48",                    # keyframe every 2 seconds at 24fps
                "-keyint_min", "24",           # minimum keyframe interval
            ],
            temp_audiofile=_tmp_audio_path,
            remove_temp=False,  # We delete manually to avoid WinError 32 on Windows
            logger=ConsoleProgressBarLogger(name="VideoBuilder"),
        )
        print(f"[VIDEO] Rendering completed")
        print(f"[VideoBuilder] [DONE] -> {OUTPUT_VIDEO}")
    finally:
        print("[VideoBuilder] Closing all clips...")
        try:
            if hasattr(final, 'close'):
                final.close()
        except Exception as exc:
            print(f"[VideoBuilder] Error closing final clip: {exc}")
        if '_music_audio' in locals() and _music_audio:
            try:
                _music_audio.close()
            except Exception as exc:
                print(f"[VideoBuilder] Error closing music clip: {exc}")
        for c in clips:
            try:
                c.close()
            except Exception as exc:
                pass
        print("[VideoBuilder] Cleanup complete.")
        # Windows keeps file handles open briefly after FFmpeg exits.
        # Retry deletion with backoff to avoid WinError 32.
        import time as _time
        for _attempt in range(6):
            try:
                if os.path.exists(_tmp_audio_path):
                    os.remove(_tmp_audio_path)
                    print(f"[VideoBuilder] Temp audio deleted: {_tmp_audio_path}")
                break
            except OSError as _e:
                if _attempt < 5:
                    _time.sleep(0.5)
                else:
                    print(f"[VideoBuilder] Could not delete temp audio (non-fatal): {_e}")

    return OUTPUT_VIDEO
 
 
# -- Smoke test ----------------------------------------------------------------
if __name__ == "__main__":
    test_scenes = [
        {"text": "Global leaders gather for emergency climate summit.",
         "keyword": "climate", "image_path": None, "audio_path": None},
        {"text": "Scientists discover new treatment for rare disease.",
         "keyword": "science", "image_path": None, "audio_path": None},
    ]
    build_video(test_scenes)


