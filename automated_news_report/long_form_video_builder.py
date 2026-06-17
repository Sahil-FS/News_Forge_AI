#!/usr/bin/env python3
"""
long_form_video_builder.py -- Widescreen (16:9) video builder for news report pipeline.
Produces 1920x1080 video with anchor overlay, Ken Burns, lower thirds, progress bar.

FIX (Phase 31): Pipeline hang resolved.
  - All intermediate clips are explicitly closed before write_videofile()
  - CompositeAudioClip.duration is always set explicitly
  - write_videofile() uses logger=None to avoid stdout blocking
  - Final cleanup runs in try/finally to guarantee execution
  - music AudioFileClip is closed after mixing
"""

import os
import gc
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from moviepy.video.VideoClip import VideoClip, ImageClip
from moviepy.audio.io.AudioFileClip import AudioFileClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
from moviepy.audio.AudioClip import CompositeAudioClip, AudioArrayClip
import moviepy.video.fx as vfx
from moviepy.editor import concatenate_videoclips as _mpy_concatenate

# ─── MoviePy v1 to v2 Compatibility Monkeypatch ─────────────────────────────
from moviepy.Clip import Clip as _MpyClip
from moviepy.video.VideoClip import VideoClip as _MpyVideoClip
import moviepy.editor as _mpy_edit
import moviepy.video.fx as _vfx
import moviepy.audio.fx as _afx

# Patch Clip methods
_MpyClip.with_duration = _MpyClip.set_duration
_MpyClip.with_start = _MpyClip.set_start
_MpyClip.with_end = _MpyClip.set_end
_MpyClip.with_fps = _MpyClip.set_fps
_MpyClip.with_ismask = _MpyClip.set_ismask
_MpyClip.with_memoize = _MpyClip.set_memoize
_MpyClip.with_make_frame = _MpyClip.set_make_frame

# Patch VideoClip methods
_MpyVideoClip.with_position = _MpyVideoClip.set_position
_MpyVideoClip.with_audio = _MpyVideoClip.set_audio
_MpyVideoClip.with_mask = _MpyVideoClip.set_mask

# Overwrite VideoClip.__init__ to support 'is_mask' parameter from MoviePy v2
_orig_VideoClip_init = _MpyVideoClip.__init__
def _patched_VideoClip_init(self, *args, **kwargs):
    if "is_mask" in kwargs:
        kwargs["ismask"] = kwargs.pop("is_mask")
    _orig_VideoClip_init(self, *args, **kwargs)
_MpyVideoClip.__init__ = _patched_VideoClip_init

# Overwrite ImageClip.__init__ to support RGBA arrays (MoviePy v1 compatibility)
from moviepy.video.VideoClip import ImageClip as _MpyImageClip
_orig_ImageClip_init = _MpyImageClip.__init__
def _patched_ImageClip_init(self, img, *args, **kwargs):
    import numpy as _np
    if isinstance(img, _np.ndarray) and len(img.shape) == 3 and img.shape[2] == 4:
        rgb = img[:, :, :3]
        alpha = img[:, :, 3] / 255.0
        _orig_ImageClip_init(self, rgb, *args, **kwargs)
        mask = _MpyImageClip(alpha, ismask=True)
        self.mask = mask
    else:
        _orig_ImageClip_init(self, img, *args, **kwargs)
_MpyImageClip.__init__ = _patched_ImageClip_init

# Overwrite VideoClip.get_frame to automatically split RGBA frames into RGB and a mask (MoviePy v1 compatibility)
_orig_VideoClip_get_frame = _MpyVideoClip.get_frame
def _patched_VideoClip_get_frame(self, t):
    frame = _orig_VideoClip_get_frame(self, t)
    import numpy as _np
    if isinstance(frame, _np.ndarray) and len(frame.shape) == 3 and frame.shape[2] == 4:
        rgb = frame[:, :, :3]
        alpha = frame[:, :, 3] / 255.0
        
        # Dynamically set mask if not present and this is not a mask itself
        if not getattr(self, "ismask", False) and not getattr(self, "mask", None):
            self._last_alpha_t = t
            self._last_alpha_val = alpha
            
            def mask_make_frame(mt):
                if hasattr(self, "_last_alpha_val"):
                    return self._last_alpha_val
                return alpha
                
            from moviepy.video.VideoClip import VideoClip as _MpyVideoClip
            self.mask = _MpyVideoClip(ismask=True, make_frame=mask_make_frame)
            if getattr(self, "duration", None) is not None:
                self.mask.duration = self.duration
        else:
            self._last_alpha_t = t
            self._last_alpha_val = alpha
            
        return rgb
    return frame
_MpyVideoClip.get_frame = _patched_VideoClip_get_frame

# Patch with_effects support
def _with_effects(self, effects):
    clip = self
    for effect in effects:
        clip = effect(clip)
    return clip
_MpyClip.with_effects = _with_effects

# Add capitalized compatibility aliases for effects
_vfx.FadeIn = lambda duration: lambda clip: clip.fx(_mpy_edit.vfx.fadein, duration)
_vfx.FadeOut = lambda duration: lambda clip: clip.fx(_mpy_edit.vfx.fadeout, duration)
_afx.MultiplyVolume = lambda factor: lambda clip: clip.fx(_mpy_edit.afx.volumex, factor)


from config import (
    LONG_VIDEO_WIDTH  as W,
    LONG_VIDEO_HEIGHT as H,
    VIDEO_FPS,
    BRAND_NAME,
    BRAND_COLOR_PRIMARY,
    BRAND_COLOR_SECONDARY,
    BRAND_COLOR_ACCENT,
    BRAND_COLOR_WHITE,
    LONG_VIDEO_OUTPUT,
)
from video_builder import (
    distribute_word_timings,
    clean_caption_text,
    _generate_news_music,
    _generate_whoosh,
    _generate_outro_audio,
    _font,
)


# Module-level blur safety-net
_last_valid_bg_arr = None


# ─── Background helpers ────────────────────────────────────────────────────────

def _make_background_landscape(image_path: str | None) -> np.ndarray:
    """
    Return a (H, W, 3) uint8 array.
    If image_path is unavailable, fall back to blurred previous or dark solid.
    """
    global _last_valid_bg_arr

    if image_path and os.path.isfile(image_path):
        try:
            img   = Image.open(image_path).convert("RGB")
            scale = max(H / img.height, W / img.width)
            nw    = max(int(img.width  * scale), W)
            nh    = max(int(img.height * scale), H)
            img   = img.resize((nw, nh), Image.LANCZOS)
            left  = (nw - W) // 2
            top   = (nh - H) // 2
            img   = img.crop((left, top, left + W, top + H))
            img   = img.filter(ImageFilter.GaussianBlur(radius=0.5))
            arr   = np.array(img)
            _last_valid_bg_arr = arr
            return arr
        except Exception as exc:
            print(f"[LongVideoBuilder] Background load failed: {exc}")

    if _last_valid_bg_arr is not None:
        prev    = Image.fromarray(_last_valid_bg_arr).convert("RGB")
        blurred = prev.filter(ImageFilter.GaussianBlur(radius=25))
        base    = Image.new("RGB", (W, H), (13, 17, 23))
        comp    = Image.blend(base, blurred, 0.5)
        return np.array(comp)

    base = np.zeros((H, W, 3), dtype=np.uint8)
    base[:, :] = [13, 17, 30]
    return base


def _apply_ken_burns_landscape(bg_arr: np.ndarray, clip_duration: float) -> VideoClip:
    """Smooth Ken Burns zoom 1.0x → 1.08x for widescreen."""
    fps          = VIDEO_FPS
    total_frames = max(1, int(round(clip_duration * fps)))
    frames       = []

    h, w     = bg_arr.shape[:2]
    resample = getattr(Image, "Resampling", Image).LANCZOS

    for i in range(total_frames):
        t_norm = i / max(1, total_frames - 1)
        scale  = 1.0 + 0.08 * t_norm
        nw     = max(1, int(w / scale))
        nh     = max(1, int(h / scale))
        x      = (w - nw) // 2
        y      = (h - nh) // 2
        crop   = bg_arr[y:y + nh, x:x + nw]
        frame  = np.array(Image.fromarray(crop).resize((w, h), resample))
        frames.append(frame)

    def make_frame(t):
        idx = min(int(round(t * fps)), len(frames) - 1)
        return frames[idx]

    clip     = VideoClip(make_frame, duration=clip_duration)
    clip.fps = fps
    return clip


# ─── Overlay helpers ───────────────────────────────────────────────────────────

def _make_gradient_landscape() -> np.ndarray:
    """RGBA gradient covering bottom 40 % of the 16:9 frame."""
    overlay = np.zeros((H, W, 4), dtype=np.uint8)
    start_y = int(H * 0.60)
    for y in range(start_y, H):
        t     = (y - start_y) / (H - start_y)
        alpha = int(180 * (t ** 1.5))
        overlay[y, :, 3] = min(alpha, 180)
    return overlay


def _make_category_banner_landscape(label: str) -> np.ndarray:
    """Top-left category banner + top-right LIVE badge."""
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw   = ImageDraw.Draw(canvas)

    bw, bh = 300, 50
    bx, by = 40, 40
    draw.rectangle([(bx, by), (bx + bw, by + bh)], fill=BRAND_COLOR_PRIMARY + (240,))
    draw.rectangle([(bx, by + bh - 3), (bx + bw, by + bh)], fill=BRAND_COLOR_ACCENT + (255,))

    font_lbl = _font(22, bold=True)
    draw.text((bx + bw // 2, by + bh // 2), label.upper(),
              font=font_lbl, fill=(255, 255, 255), anchor="mm")

    draw.rectangle([(W - 150, 40), (W - 40, 90)], fill=BRAND_COLOR_SECONDARY + (220,))
    draw.text((W - 95, 65), "LIVE",
              font=font_lbl, fill=BRAND_COLOR_WHITE + (255,), anchor="mm")

    return np.array(canvas)


def _make_lower_third_landscape(headline: str, source: str, location: str) -> np.ndarray:
    """Professional lower-third strap for 1920x1080."""
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw   = ImageDraw.Draw(canvas)

    lh_w = 1200
    lh_h = 100
    lx   = 60
    ly   = H - lh_h - 100

    draw.rectangle([(lx, ly), (lx + lh_w, ly + lh_h)],
                   fill=BRAND_COLOR_SECONDARY + (220,))
    draw.rectangle([(lx, ly), (lx + 10, ly + lh_h)],
                   fill=BRAND_COLOR_ACCENT + (255,))

    font_hl = _font(28, bold=True)
    hl_display = headline.upper()
    if len(hl_display) > 65:
        hl_display = hl_display[:62] + "..."
    draw.text((lx + 30, ly + 20), hl_display, font=font_hl, fill=(255, 255, 255))

    font_details = _font(20, bold=False)
    loc_display  = f"LOCATION: {location.upper()}" if location else "BREAKING NEWS DIRECT"
    draw.text((lx + 30, ly + 60), loc_display,
              font=font_details, fill=BRAND_COLOR_ACCENT + (255,))

    source_tag = f"SOURCE: {source.upper()}"
    draw.text((lx + lh_w - 200, ly + 60), source_tag,
              font=font_details, fill=(180, 180, 180), anchor="la")

    return np.array(canvas)


# ─── Caption helpers ───────────────────────────────────────────────────────────

def _make_text_card_landscape(text: str,
                               highlight_word: str = "",
                               is_anchor: bool = False) -> np.ndarray:
    """Subtitle card for the landscape format."""
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if not text.strip():
        return np.array(canvas)

    draw   = ImageDraw.Draw(canvas)
    font   = _font(36, bold=True)
    SAFE_W = 1400

    words   = text.split()
    lines   = []
    cur_ln  = []

    for word in words:
        cur_ln.append(word)
        try:
            ln_w = draw.textlength(" ".join(cur_ln), font=font)
        except Exception:
            ln_w = len(" ".join(cur_ln)) * 20
        if ln_w > SAFE_W:
            if len(cur_ln) > 1:
                cur_ln.pop()
                lines.append(" ".join(cur_ln))
                cur_ln = [word]
            else:
                lines.append(" ".join(cur_ln))
                cur_ln = []
    if cur_ln:
        lines.append(" ".join(cur_ln))

    card_h = len(lines) * 50 + 40
    try:
        card_w = min(1480, max(draw.textlength(ln, font=font) for ln in lines) + 60)
    except Exception:
        card_w = 1200

    cx = (W - int(card_w)) // 2
    cy = H - card_h - (260 if is_anchor else 220)

    draw.rounded_rectangle([(cx, cy), (cx + int(card_w), cy + card_h)],
                            radius=15, fill=(10, 10, 15, 175))

    line_y = cy + 20
    for line in lines:
        line_words = line.split()
        try:
            lw    = draw.textlength(line, font=font)
            word_x = cx + (int(card_w) - int(lw)) // 2
        except Exception:
            word_x = cx + 30

        for w in line_words:
            is_hl  = w.lower().rstrip(".,;:!?") == highlight_word.lower().rstrip(".,;:!?")
            color  = (255, 215, 0, 255) if is_hl else (255, 255, 255, 255)
            draw.text((word_x, line_y), w, font=font, fill=color)
            try:
                word_x += int(draw.textlength(w + " ", font=font))
            except Exception:
                word_x += len(w) * 20 + 8
        line_y += 50

    return np.array(canvas)


def _make_progressive_caption_landscape(
    text: str,
    timing_duration: float,
    clip_duration: float,
    is_anchor: bool = False,
) -> VideoClip | None:
    """Frame-based progressive caption for 16:9."""
    text_clean  = clean_caption_text(text)
    words       = [w.strip() for w in text_clean.split() if w.strip()]

    clean_words: list[str] = []
    prev: str | None = None
    for w in words:
        if w != prev:
            clean_words.append(w)
            prev = w
    words       = clean_words
    total_words = len(words)

    if total_words == 0:
        return None

    timings = distribute_word_timings(words, timing_duration)
    if len(timings) < total_words:
        timings += [(timing_duration, timing_duration)] * (total_words - len(timings))
    elif len(timings) > total_words:
        timings = timings[:total_words]

    _frame_cache: dict = {}

    def make_frame(t: float) -> np.ndarray:
        word_idx = 0
        for i, (start, _) in enumerate(timings):
            if t >= start:
                word_idx = i
            else:
                break

        if word_idx >= total_words:
            word_idx = total_words - 1

        if t > timings[-1][1]:
            key = "__HOLD__"
            if key not in _frame_cache:
                _frame_cache[key] = _make_text_card_landscape(
                    " ".join(words), highlight_word="", is_anchor=is_anchor
                )
            return _frame_cache[key]

        if word_idx not in _frame_cache:
            visible  = words[:word_idx + 1][-12:]
            hl_word  = visible[-1] if visible else ""
            _frame_cache[word_idx] = _make_text_card_landscape(
                " ".join(visible), highlight_word=hl_word, is_anchor=is_anchor
            )
        return _frame_cache[word_idx]

    clip_dur    = max(clip_duration, timing_duration)
    clip        = VideoClip(make_frame, duration=clip_dur)
    clip.fps    = VIDEO_FPS
    return clip


# ─── Scene builder ─────────────────────────────────────────────────────────────

def _build_scene_clip_landscape(
    scene: dict,
    scene_idx: int,
    final_duration: float,
    headline: str,
    visual_cut_threshold: float = 2.8,
) -> CompositeVideoClip:
    """
    Composite one landscape scene.
    Uses VideoClip() wrapper — no .fl() needed (removed in MoviePy 2.x).
    """
    is_anchor    = scene.get("is_anchor", False)
    image_path   = scene.get("image_path")
    audio_path   = scene.get("audio_path")
    text         = scene.get("text", "")
    scene_type   = scene.get("type", "general")
    alt_img_path = scene.get("alt_image_path")

    # ── Background ────────────────────────────────────────────────────────────
    effective_img = image_path
    if not effective_img or not os.path.isfile(effective_img):
        placeholder = os.path.abspath(
            os.path.join(os.path.dirname(LONG_VIDEO_OUTPUT), "..", "assets", "placeholder.jpg")
        )
        if os.path.isfile(placeholder):
            effective_img = placeholder
        else:
            effective_img = None

    # ── Audio ─────────────────────────────────────────────────────────────────
    audio_clip     = None
    pure_voice_dur = 0.0

    if audio_path and os.path.isfile(audio_path):
        try:
            audio_clip     = AudioFileClip(audio_path)
            pure_voice_dur = audio_clip.duration

            whoosh_data = _generate_whoosh(duration=0.18)
            if whoosh_data is not None:
                try:
                    whoosh_clip = AudioArrayClip(whoosh_data, fps=44100)
                    mixed_audio = CompositeAudioClip(
                        [whoosh_clip, audio_clip]
                    )
                    mixed_audio.duration = final_duration
                    audio_clip  = mixed_audio
                except Exception:
                    pass
        except Exception as exc:
            print(f"[LongVideoBuilder] Audio load failed scene {scene_idx}: {exc}")
            audio_clip     = None
            pure_voice_dur = 0.0

    # ── Build BG clip ─────────────────────────────────────────────────────────
    bg_arr = _make_background_landscape(effective_img)

    if final_duration > visual_cut_threshold and effective_img and not is_anchor:
        cut_point = final_duration / 2
        bg_a      = _apply_ken_burns_landscape(bg_arr, cut_point)
        bg_b_arr  = _make_background_landscape(
            alt_img_path if alt_img_path else effective_img
        )
        bg_b      = _apply_ken_burns_landscape(bg_b_arr, final_duration - cut_point)
        bg        = _mpy_concatenate([bg_a, bg_b], method="compose")
    else:
        bg = _apply_ken_burns_landscape(bg_arr, final_duration)



    # ── Caption ───────────────────────────────────────────────────────────────
    caption_timing = pure_voice_dur if pure_voice_dur > 0 else max(1.5, len(text.split()) / 2.5)
    caption_clip   = _make_progressive_caption_landscape(
        text=text,
        timing_duration=caption_timing,
        clip_duration=final_duration,
        is_anchor=is_anchor,
    )

    # ── Layer stack ───────────────────────────────────────────────────────────
    layers: list = [bg.with_position("center")]

    if caption_clip:
        layers.append(caption_clip)

    if not is_anchor:
        grad_clip   = ImageClip(_make_gradient_landscape()).with_duration(final_duration)
        layers.append(grad_clip)

        location   = (scene.get("entities") or {}).get("location", "")
        source     = scene.get("news_source", "World News")
        lower_clip = ImageClip(
            _make_lower_third_landscape(headline, source, location)
        ).with_duration(final_duration)
        layers.append(lower_clip)

        cat_labels = {
            "war": "WAR IN FOCUS", "politics": "POLITICAL REPORT",
            "technology": "TECH & SCIENCE", "business": "BUSINESS OUTLOOK",
            "disaster": "BREAKING REPORT", "general": "WORLD NEWS",
            "serious": "URGENT REPORT",
        }
        label      = cat_labels.get(scene_type, "WORLD NEWS")
        banner     = ImageClip(
            _make_category_banner_landscape(label)
        ).with_duration(final_duration)
        layers.append(banner)

    scene_clip = CompositeVideoClip(layers, size=(W, H)).with_duration(final_duration)
    if audio_clip:
        scene_clip = scene_clip.with_audio(audio_clip)

    print(
        f"[LongVideoBuilder] Scene {scene_idx:02d} ({scene_type}) | "
        f"dur={final_duration:.1f}s | anchor={is_anchor} | "
        f"audio={'Y' if audio_clip else 'N'} | image={'Y' if effective_img else 'N'}"
    )
    return scene_clip


# ─── Map stinger ───────────────────────────────────────────────────────────────

def _build_map_stinger_landscape(
    map_image_path: str,
    location: str,
    headline: str,
    hook_text: str = "",
    audio_path: str = None,
) -> CompositeVideoClip:
    """Landscape map intro scene."""
    duration  = 5.0
    map_audio = None

    if audio_path and os.path.isfile(audio_path):
        try:
            map_audio = AudioFileClip(audio_path)
            duration  = max(4.0, min(7.5, map_audio.duration + 0.5))
        except Exception as exc:
            print(f"[LongVideoBuilder] Map audio load failed: {exc}")

    bg_arr = _make_background_landscape(map_image_path)
    bg     = _apply_ken_burns_landscape(bg_arr, duration)
    grad   = ImageClip(_make_gradient_landscape()).with_duration(duration)

    def _make_map_overlay() -> np.ndarray:
        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw   = ImageDraw.Draw(canvas)

        font_title = _font(48, bold=True)
        font_loc   = _font(34, bold=False)

        _SHORT_MAP = {
            "democratic republic of congo": "DR CONGO",
            "the democratic republic of congo": "DR CONGO",
            "united states of america": "UNITED STATES",
            "united arab emirates": "UAE",
        }
        _display_loc = _SHORT_MAP.get(location.lower(), location.upper())
        if len(_display_loc) > 25:
            _display_loc = _display_loc[:22] + "..."

        loc_str = f"\U0001F4CD {_display_loc}"
        try:
            lb     = draw.textbbox((0, 0), loc_str, font=font_loc)
            lw, lh = lb[2] - lb[0], lb[3] - lb[1]
        except Exception:
            lw, lh = len(loc_str) * 20, 40

        lx = (W - lw) // 2
        ly = int(H * 0.40)
        px, py = 40, 18
        draw.rounded_rectangle(
            [(lx - px, ly - py), (lx + lw + px, ly + lh + py)],
            radius=14, fill=(13, 17, 23, 220),
        )
        draw.rounded_rectangle(
            [(lx - px, ly - py), (lx - px + 6, ly + lh + py)],
            radius=14, fill=(*BRAND_COLOR_ACCENT, 255),
        )
        draw.text((lx, ly), loc_str, font=font_loc, fill=(255, 255, 255, 255))

        hl = headline[:60] + "..." if len(headline) > 60 else headline
        try:
            hb = draw.textbbox((0, 0), hl, font=_font(26, bold=False))
            hw = hb[2] - hb[0]
        except Exception:
            hw = len(hl) * 16
        draw.text(
            ((W - hw) // 2, ly + lh + py + 18),
            hl,
            font=_font(26, bold=False),
            fill=(210, 210, 210, 180),
        )
        return np.array(canvas)

    text_clip   = ImageClip(_make_map_overlay()).with_duration(duration)
    banner_clip = ImageClip(
        _make_category_banner_landscape("MAP REPORT")
    ).with_duration(duration)

    layers = [bg.with_position("center"), grad, text_clip, banner_clip]

    if hook_text and hook_text.strip():
        pure_narr = map_audio.duration if map_audio else max(1.0, duration - 0.5)
        cap_clip  = _make_progressive_caption_landscape(
            text=hook_text,
            timing_duration=max(1.0, pure_narr - 0.12),
            clip_duration=duration,
        )
        if cap_clip:
            layers.insert(-1, cap_clip)

    stinger = CompositeVideoClip(layers, size=(W, H)).with_duration(duration)
    if map_audio:
        stinger = stinger.with_audio(map_audio)

    print(f"[LongVideoBuilder] Map stinger: {duration:.1f}s for '{location}'")
    return stinger


# ─── Outro ─────────────────────────────────────────────────────────────────────

def _build_outro_scene_landscape(
    audio_duration: float,
    audio_path: str,
    cta: dict,
    scene0_image: str,
) -> CompositeVideoClip:
    """Landscape outro with CTA, subscribe button, and blurred background."""
    duration    = 5.0
    outro_audio = None

    if audio_path and os.path.isfile(audio_path):
        try:
            outro_audio = AudioFileClip(audio_path)
            duration    = max(3.5, min(8.0, outro_audio.duration + 0.5))
        except Exception as exc:
            print(f"[LongVideoBuilder] Outro audio load failed: {exc}")

    DARK_NAVY = (13, 17, 23)
    bg_pil    = Image.new("RGB", (W, H), DARK_NAVY)

    if scene0_image and os.path.isfile(scene0_image):
        try:
            img    = Image.open(scene0_image).convert("RGB")
            scale  = max(H / img.height, W / img.width)
            nw, nh = int(img.width * scale), int(img.height * scale)
            img    = img.resize((nw, nh), Image.LANCZOS)
            left   = (nw - W) // 2
            top    = (nh - H) // 2
            img    = img.crop((left, top, left + W, top + H))
            img    = img.filter(ImageFilter.GaussianBlur(radius=35))
            base   = Image.new("RGB", (W, H), DARK_NAVY)
            bg_pil = Image.blend(base, img, 0.4)
        except Exception:
            pass

    def _outro_bg_frame(t: float) -> np.ndarray:
        prog    = t / max(duration, 0.01)
        scale   = 1.0 + 0.12 * prog
        nw, nh  = int(W * scale), int(H * scale)
        resized = bg_pil.resize((nw, nh), Image.LANCZOS)
        left    = (nw - W) // 2
        top     = (nh - H) // 2
        return np.array(resized.crop((left, top, left + W, top + H)))

    bg_clip = VideoClip(_outro_bg_frame, duration=duration)

    def _make_outro_text() -> np.ndarray:
        canvas    = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw      = ImageDraw.Draw(canvas)
        font_main = _font(44, bold=True)
        font_sub  = _font(28, bold=False)
        font_cred = _font(22, bold=False)

        main_line = cta.get("main_line",   "What do you think about this?")
        sub_line  = cta.get("sub_line",    "Share your thoughts in the comments.")

        draw.text((W // 2, H // 2 - 40), main_line,
                  font=font_main, fill=(255, 255, 255), anchor="mm")
        draw.text((W // 2, H // 2 + 20), sub_line,
                  font=font_sub,  fill=(200, 200, 200), anchor="mm")
        draw.text((W // 2, H - 80),
                  f"{BRAND_NAME} | THE NEWS CUP BROADCASTING SYSTEM",
                  font=font_cred, fill=(130, 130, 150), anchor="mm")
        return np.array(canvas)

    def _make_subscribe_btn(alpha_factor: float) -> np.ndarray:
        canvas  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw    = ImageDraw.Draw(canvas)
        btn_w, btn_h = 320, 70
        bx      = (W - btn_w) // 2
        by      = H // 2 + 90
        opacity = int(255 * alpha_factor)
        draw.rounded_rectangle(
            [(bx, by), (bx + btn_w, by + btn_h)],
            radius=35, fill=(220, 30, 30, opacity),
        )
        font_btn = _font(26, bold=True)
        draw.text((bx + btn_w // 2, by + btn_h // 2), "SUBSCRIBE",
                  font=font_btn, fill=(255, 255, 255, opacity), anchor="mm")
        return np.array(canvas)

    def _sub_frame(t: float) -> np.ndarray:
        return _make_subscribe_btn(1.0)[:, :, :3]

    def _sub_mask(t: float) -> np.ndarray:
        alpha    = min(1.0, max(0.0, (t - 1.2) / 0.8)) if t >= 1.2 else 0.0
        btn_rgba = _make_subscribe_btn(1.0)
        return (btn_rgba[:, :, 3] / 255.0) * alpha

    text_clip  = ImageClip(_make_outro_text()).with_duration(duration)
    sub_clip   = VideoClip(_sub_frame, duration=duration)
    sub_mask   = VideoClip(_sub_mask,  ismask=True, duration=duration)
    sub_clip   = sub_clip.with_mask(sub_mask)
    banner     = ImageClip(
        _make_category_banner_landscape("STAY CONNECTED")
    ).with_duration(duration)

    outro = CompositeVideoClip(
        [bg_clip, text_clip, sub_clip, banner], size=(W, H)
    ).with_duration(duration)
    outro = outro.with_effects([vfx.FadeIn(0.4)])

    if outro_audio:
        outro = outro.with_audio(outro_audio)

    print(f"[LongVideoBuilder] Outro: {duration:.1f}s | audio={'Y' if outro_audio else 'N'}")
    return outro


# ─── Progress bar ──────────────────────────────────────────────────────────────

def _build_progress_bar(total_duration: float) -> VideoClip:
    """6 px red progress bar that fills left → right over full video duration."""
    BAR_H = 6
    BAR_Y = H - BAR_H

    def make_bar_frame(t: float) -> np.ndarray:
        bar        = np.zeros((BAR_H, W, 3), dtype=np.uint8)
        bar[:, :, 0] = BRAND_COLOR_ACCENT[0] // 4
        bar[:, :, 1] = BRAND_COLOR_ACCENT[1] // 4
        bar[:, :, 2] = BRAND_COLOR_ACCENT[2] // 4
        filled     = max(0, min(W, int(W * (t / max(total_duration, 1.0)))))
        if filled > 0:
            bar[:, :filled, 0] = BRAND_COLOR_ACCENT[0]
            bar[:, :filled, 1] = BRAND_COLOR_ACCENT[1]
            bar[:, :filled, 2] = BRAND_COLOR_ACCENT[2]
        return bar

    bar_clip     = VideoClip(make_bar_frame, duration=total_duration)
    bar_clip.fps = VIDEO_FPS
    return bar_clip.with_position((0, BAR_Y))


# ─── Main entry point ──────────────────────────────────────────────────────────

def build_long_video(scenes: list[dict], pipeline_meta: dict = None, visual_cut_threshold: float = 2.8) -> str:
    """
    Build and export the 1920x1080 long-form video.
    Returns the output file path.

    FIX: All clips are tracked and explicitly closed after write_videofile()
    in a try/finally block so the pipeline never hangs.
    """
    global _last_valid_bg_arr
    _last_valid_bg_arr = None

    if not scenes:
        raise ValueError("[LongVideoBuilder] No scenes provided.")

    MAX_LONG_TOTAL = 300.0

    scene_durations: list[float] = []
    for scene in scenes:
        ap = scene.get("audio_path")
        if ap and os.path.isfile(ap):
            try:
                ac  = AudioFileClip(ap)
                dur = ac.duration
                ac.close()
            except Exception:
                dur = len(scene.get("text", "").split()) * 0.55
        else:
            dur = len(scene.get("text", "").split()) * 0.55

        scene_durations.append(max(2.5, min(dur + 0.30, 10.5)))

    total_duration = sum(scene_durations)
    print(
        f"[LongVideoBuilder] {len(scenes)} scenes | "
        f"raw duration: {total_duration:.1f}s ({total_duration / 60:.1f} min)"
    )

    if total_duration > MAX_LONG_TOTAL:
        scale          = MAX_LONG_TOTAL / total_duration
        scene_durations = [d * scale for d in scene_durations]
        print(f"[LongVideoBuilder] Compressed to 5-min cap: x{scale:.2f}")

    # Pre-render audit
    for i, (scene, dur) in enumerate(zip(scenes, scene_durations)):
        ap  = scene.get("audio_path")
        raw = 0.0
        if ap and os.path.isfile(ap):
            try:
                ac  = AudioFileClip(ap)
                raw = ac.duration
                ac.close()
            except Exception:
                pass
        print(
            f"[LongVideoBuilder] Scene {i:02d} | audio={raw:.2f}s | "
            f"clip={dur:.2f}s | anchor={scene.get('is_anchor', False)}"
        )

    # Track ALL clips so we can close them all in finally
    _all_clips_to_close: list = []

    # ── Chapter timestamps ────────────────────────────────────────────────────
    # Calculate before building (non-fatal)
    _lf_chapters = ""
    try:
        from chapter_generator import calculate_section_durations, generate_chapters
        sec_durs = calculate_section_durations(scenes)
        _lf_chapters = generate_chapters(sec_durs)
        if pipeline_meta is not None:
            pipeline_meta["long_form_chapters"] = _lf_chapters
        print(f"[LongVideoBuilder] Chapters generated OK")
    except Exception as exc:
        print(f"[LongVideoBuilder] Chapter generation failed (non-fatal): {exc}")

    try:
        clips: list = []

        # ── Map stinger ───────────────────────────────────────────────────────
        if pipeline_meta:
            map_path       = pipeline_meta.get("map_image_path")
            location       = pipeline_meta.get("primary_location", "")
            headline       = pipeline_meta.get("headline", "")
            map_audio_path = pipeline_meta.get("map_audio_path")

            if map_path and os.path.isfile(map_path) and location:
                try:
                    stinger = _build_map_stinger_landscape(
                        map_image_path=map_path,
                        location=location,
                        headline=headline,
                        hook_text=pipeline_meta.get("map_hook_text", ""),
                        audio_path=map_audio_path,
                    )
                    clips.append(stinger)
                    _all_clips_to_close.append(stinger)
                    print("[LongVideoBuilder] Map stinger prepended.")
                except Exception as exc:
                    print(f"[LongVideoBuilder] Map stinger failed: {exc}")
                    import traceback; traceback.print_exc()

        headline_str = (pipeline_meta.get("headline", "") if pipeline_meta else "")
        for idx, (scene, dur) in enumerate(zip(scenes, scene_durations)):
            clip = _build_scene_clip_landscape(
                scene=scene,
                scene_idx=idx,
                final_duration=dur,
                headline=headline_str,
                visual_cut_threshold=visual_cut_threshold,
            )
            clips.append(clip)
            _all_clips_to_close.append(clip)

        # ── Outro ─────────────────────────────────────────────────────────────
        try:
            from script_generator import generate_dynamic_cta as _gen_cta
            cta_ctx = (pipeline_meta.get("story_context", "neutral") if pipeline_meta else "neutral")
            cta     = _gen_cta(headline_str, cta_ctx)
        except Exception:
            cta_ctx = "neutral"
            cta     = {}

        outro_audio_path = _generate_outro_audio(cta=cta, story_context=cta_ctx)
        scene0_img       = scenes[0].get("image_path") if scenes else None

        try:
            main_audio_dur = sum(c.duration for c in clips if c.audio is not None)
        except Exception:
            main_audio_dur = 60.0

        outro_clip = _build_outro_scene_landscape(
            audio_duration=main_audio_dur,
            audio_path=outro_audio_path,
            cta=cta,
            scene0_image=scene0_img,
        )
        clips.append(outro_clip)
        _all_clips_to_close.append(outro_clip)

        # ── Concatenate ───────────────────────────────────────────────────────
        print(f"[LongVideoBuilder] Concatenating {len(clips)} clips...")
        final = _mpy_concatenate(clips, method="compose")
        _all_clips_to_close.append(final)

        # ── Progress bar overlay ──────────────────────────────────────────────
        try:
            progress_bar = _build_progress_bar(final.duration)
            _all_clips_to_close.append(progress_bar)
            final        = CompositeVideoClip(
                [final, progress_bar], size=(W, H)
            ).with_duration(final.duration)
            _all_clips_to_close.append(final)
        except Exception as exc:
            print(f"[LongVideoBuilder] Progress bar failed (non-fatal): {exc}")

        # Calculate time intervals for all quote/tweet/document overlay scenes during video assembly
        current_time = 0.0
        duck_intervals = []
        
        clip_idx = 0
        if pipeline_meta:
            map_path       = pipeline_meta.get("map_image_path")
            location       = pipeline_meta.get("primary_location", "")
            if map_path and os.path.isfile(map_path) and location:
                current_time += clips[clip_idx].duration
                clip_idx += 1
                
        for idx, scene in enumerate(scenes):
            scene_clip = clips[clip_idx]
            scene_type = scene.get("type", "general")
            if scene_type in ("quote_card", "tweet_overlay", "evidence_graphic"):
                duck_intervals.append((current_time, current_time + scene_clip.duration))
                print(f"[LongForm DUCK INTERVAL] Added: {current_time:.2f}s to {current_time + scene_clip.duration:.2f}s (scene {idx})")
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

        # ── Background music ──────────────────────────────────────────────────
        music_ctx   = (pipeline_meta.get("story_context", "neutral") if pipeline_meta else "neutral")
        music_path  = LONG_VIDEO_OUTPUT.replace(".mp4", "_bgmusic.mp3")
        music_file  = _generate_news_music(final.duration + 2.0, music_ctx, music_path)

        _music_clip = None
        if music_file and os.path.isfile(music_file):
            try:
                _music_clip = AudioFileClip(music_file)
                if final.audio is not None:
                    if duck_intervals:
                        print(f"[LongVideoBuilder] Applying dynamic volume ducking for {len(duck_intervals)} intervals")
                        _music_clip = _music_clip.fl(make_duck_filter(duck_intervals))
                    mixed               = CompositeAudioClip([final.audio, _music_clip])
                    mixed.duration      = final.duration
                    final               = final.with_audio(mixed)
                print(f"[LongVideoBuilder] Music mixed: {music_ctx}, {final.duration:.1f}s")
            except Exception as exc:
                print(f"[LongVideoBuilder] Music mix failed (non-fatal): {exc}")

        # ── Render ────────────────────────────────────────────────────────────
        print(f"[LongVideoBuilder] Rendering -> {LONG_VIDEO_OUTPUT}")
        final.write_videofile(
            LONG_VIDEO_OUTPUT,
            fps=VIDEO_FPS,
            codec="libx264",
            audio_codec="aac",
            audio_fps=44100,
            threads=4,
            preset="veryfast",
            ffmpeg_params=[
                "-crf", "23",
                "-movflags", "+faststart",
                "-force_key_frames", "0",
                "-g", "48",
                "-keyint_min", "24",
            ],
            temp_audiofile=LONG_VIDEO_OUTPUT.replace(".mp4", "_tmp_audio.m4a"),
            remove_temp=True,
            logger=None,   # FIX: logger=None prevents stdout blocking
        )
        print(f"[LongVideoBuilder] Done -> {LONG_VIDEO_OUTPUT}")

    finally:
        # FIX: Explicit cleanup of every clip — prevents resource/thread hang
        print("[LongVideoBuilder] Closing all clips...")
        for c in _all_clips_to_close:
            try:
                c.close()
            except Exception:
                pass
        if '_music_clip' in dir() and _music_clip is not None:
            try:
                _music_clip.close()
            except Exception:
                pass
        # Force garbage collection to release file handles
        gc.collect()
        print("[LongVideoBuilder] Cleanup complete.")

    return LONG_VIDEO_OUTPUT