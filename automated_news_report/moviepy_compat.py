# moviepy_compat.py -- MoviePy compatibility shims and progress logger

import sys


def apply_compat_patches():
    """Public alias kept for backward compatibility with video_builder.py.
    Monkeypatches are applied automatically at module import time below."""
    pass  # already applied at import
import os

# ---------------------------------------------------------------------------
# Monkeypatches applied once at import time
# ---------------------------------------------------------------------------

def _apply_monkeypatches():
    """Apply compatibility fixes for MoviePy on Windows / newer Python."""
    try:
        # MoviePy 1.x uses 'proglog' for progress bars. On Windows the default
        # tqdm-based bar uses carriage returns that confuse PowerShell buffers.
        # We replace the default logger factory so our ConsoleProgressBarLogger
        # is used whenever MoviePy calls proglog.default_bar_logger().
        import proglog
        _orig_default = proglog.default_bar_logger

        def _patched_default(logger, **kw):
            if logger is None or logger == "bar":
                return ConsoleProgressBarLogger()
            return _orig_default(logger, **kw)

        proglog.default_bar_logger = _patched_default
    except Exception as e:
        print(f"[MoviePyCompat] proglog patch skipped: {e}")

    # MoviePy 2.x method shims for MoviePy 1.x compatibility
    try:
        from moviepy.Clip import Clip
        from moviepy.video.VideoClip import VideoClip
        from moviepy.audio.AudioClip import AudioClip
        from moviepy.editor import ImageClip, AudioFileClip, CompositeVideoClip
        import moviepy.video.fx as vfx
        import moviepy.video.fx.all as vfx_all
        import moviepy.audio.fx as afx
        import moviepy.audio.fx.all as afx_all

        classes_to_patch = [Clip, VideoClip, AudioClip, ImageClip, AudioFileClip, CompositeVideoClip]

        for cls in classes_to_patch:
            for attr in dir(cls):
                if attr.startswith("set_"):
                    with_name = attr.replace("set_", "with_", 1)
                    if not hasattr(cls, with_name):
                        setattr(cls, with_name, getattr(cls, attr))
            if hasattr(cls, "subclip") and not hasattr(cls, "subclipped"):
                setattr(cls, "subclipped", getattr(cls, "subclip"))
            elif hasattr(cls, "subclipped") and not hasattr(cls, "subclip"):
                setattr(cls, "subclip", getattr(cls, "subclipped"))

        if not hasattr(Clip, "with_effects"):
            def with_effects(self, effects):
                c = self
                for effect in effects:
                    c = effect(c)
                return c
            Clip.with_effects = with_effects

        class FadeInClass:
            def __init__(self, duration):
                self.duration = duration
            def __call__(self, clip):
                return clip.fx(vfx_all.fadein, self.duration)

        vfx.FadeIn = FadeInClass
        vfx_all.FadeIn = FadeInClass

        class MultiplyVolumeClass:
            def __init__(self, factor):
                self.factor = factor
            def __call__(self, clip):
                return clip.fx(afx_all.volumex, self.factor)

        afx.MultiplyVolume = MultiplyVolumeClass
        afx_all.MultiplyVolume = MultiplyVolumeClass

        print("[MoviePyCompat] Successfully patched MoviePy 2.x method shims.")
    except Exception as e:
        print(f"[MoviePyCompat] Shims patch failed: {e}")


print("[MoviePyCompat] Applying compatibility monkeypatches...")
_apply_monkeypatches()
print("[MoviePyCompat] Monkeypatches applied successfully.")


# ---------------------------------------------------------------------------
# ConsoleProgressBarLogger
# ---------------------------------------------------------------------------

class ConsoleProgressBarLogger:
    """
    A simple MoviePy / proglog-compatible logger that prints progress on
    separate lines (using \\n) instead of carriage returns (\\r), which avoids
    stdout buffering issues in Windows PowerShell terminals.
    """

    def __init__(self, name: str = "MoviePy"):
        self.name = name
        self._last_pct = -1

    # -- proglog interface ---------------------------------------------------

    def bars_callback(self, bar, attr, value, old_value=None):
        """Called by proglog on each bar update."""
        if attr == "value" and bar == "t":
            try:
                total = self.bars[bar].get("total", None)
                if total and total > 0:
                    pct = int(100 * value / total)
                    if pct != self._last_pct and pct % 5 == 0:
                        self._last_pct = pct
                        print(f"[{self.name}] Rendering progress: {pct}%")
            except Exception:
                pass

    def callback(self, **kw):
        pass  # no-op for non-bar callbacks

    # proglog stores bar state in self.bars
    @property
    def bars(self):
        if not hasattr(self, "_bars"):
            self._bars = {}
        return self._bars

    @bars.setter
    def bars(self, value):
        self._bars = value

    # -- MoviePy 2.x interface (write_videofile passes logger= directly) -----

    def __call__(self, *args, **kwargs):
        return self

    def iter_bar(self, **kw):
        """Yield items from a named iterator, printing progress."""
        for name, iterable in kw.items():
            items = list(iterable)
            total = len(items)
            for i, item in enumerate(items):
                pct = int(100 * (i + 1) / total) if total else 100
                if pct != self._last_pct and pct % 5 == 0:
                    self._last_pct = pct
                    print(f"[{self.name}] Rendering progress: {pct}%")
                yield item
