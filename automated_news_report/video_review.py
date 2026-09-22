#!/usr/bin/env python3
"""
video_review.py -- Strict AI Video Review System
================================================

PRIMARY RULE:
  Executes `.venv\\Scripts\\python.exe main.py` as a subprocess -- exactly
  matching terminal behaviour.  Reviews ONLY the video produced by that run.

Rules enforced:
  * Uses .venv Python exclusively -- no system Python
  * Runs main.py directly -- no module imports, no partial pipeline
  * FORCE_REFRESH=1 is injected into the subprocess environment
  * Duration is read from the output file via MoviePy
  * Execution-mismatch is detected and reported
  * No extra files created; only news_video.mp4 is the review target

Usage:
    .venv\\Scripts\\python.exe video_review.py
"""

import sys

# Force UTF-8 stdout/stderr on Windows to avoid charmap UnicodeEncodeErrors
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

# ENVIRONMENT CHECK
import os as _os_env_check
if "VIRTUAL_ENV" not in _os_env_check.environ and ".venv" not in sys.executable and "venv" not in sys.executable:
    print(f"[WARN] Running outside a virtual environment: {sys.executable}")

print(f"[ENV] Using Python: {sys.executable}")

import os
import re
import math
import time
import textwrap
import subprocess
from datetime import datetime

# feedback loop integration
try:
    from correlation_engine import CorrelationEngine
except ImportError:
    CorrelationEngine = None

try:
    import requests
except ImportError:
    requests = None

# ─────────────────────────────────────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────────────────────────────────────
ROOT         = os.path.dirname(os.path.abspath(__file__))
import sys
if sys.platform == "win32":
    VENV_PYTHON = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
else:
    VENV_PYTHON = os.path.join(ROOT, ".venv", "bin", "python")
MAIN_SCRIPT  = os.path.join(ROOT, "main.py")
OUTPUT_VIDEO = os.path.join(ROOT, "output", "news_video.mp4")

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
TARGET_DUR_LOW  = 40.0   # seconds -- minimum acceptable (scorer gives 10/10 at 40s+)
TARGET_DUR_HIGH = 55.0   # seconds -- maximum acceptable (expanded range)
MIN_SCENES      = 3
REPORT_PATH     = os.path.join(ROOT, "VIDEO_QUALITY_ANALYSIS_REPORT.md")

MAX_CAPTION_WORDS = 12   # words per scene before overflow risk


# ═════════════════════════════════════════════════════════════════════════════
# STEP 1 --  Pre-flight checks
# ═════════════════════════════════════════════════════════════════════════════

def preflight():
    ok = True

    if not os.path.isfile(VENV_PYTHON):
        print(f"[ERROR] venv Python not found: {VENV_PYTHON}")
        ok = False

    if not os.path.isfile(MAIN_SCRIPT):
        print(f"[ERROR] main.py not found: {MAIN_SCRIPT}")
        ok = False

    return ok


# ═════════════════════════════════════════════════════════════════════════════
# STEP 2 -- Run main.py via subprocess (terminal-identical execution)
# ═════════════════════════════════════════════════════════════════════════════

def run_main_pipeline():
    """
    Execute:  .venv\\Scripts\\python.exe main.py
    with FORCE_REFRESH=1 in the environment.

    Returns (stdout_lines, return_code, elapsed_seconds).
    All output is echoed to console in real-time AND captured.
    """

    env = os.environ.copy()
    env["FORCE_REFRESH"] = "1"         # force fresh images every run

    print("\n" + "═" * 60)
    print("  EXECUTING: .venv\\Scripts\\python.exe main.py")
    print("  FORCE_REFRESH=1")
    print("═" * 60 + "\n")

    t_start = time.time()

    proc = subprocess.Popen(
        [VENV_PYTHON, MAIN_SCRIPT],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,       # merge stderr -> stdout
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    captured_lines = []
    for line in proc.stdout:
        print(line, end="", flush=True)   # real-time echo
        captured_lines.append(line.rstrip("\n"))

    proc.wait()
    elapsed = time.time() - t_start

    print(f"\n[REVIEW] Pipeline finished in {elapsed:.1f}s -- exit code: {proc.returncode}")
    return captured_lines, proc.returncode, elapsed


# ═════════════════════════════════════════════════════════════════════════════
# STEP 3 -- Verify output file belongs to THIS run
# ═════════════════════════════════════════════════════════════════════════════

def verify_output(run_started_at: float) -> dict:
    """
    Confirm news_video.mp4 exists AND was modified after run_started_at.
    Returns a dict with is_valid, mtime, size_bytes.
    """
    result = {
        "is_valid":   False,
        "mtime":      None,
        "size_bytes": 0,
        "age_secs":   None,
    }

    if not os.path.isfile(OUTPUT_VIDEO):
        return result

    stat = os.stat(OUTPUT_VIDEO)
    result["mtime"]      = stat.st_mtime
    result["size_bytes"] = stat.st_size
    result["age_secs"]   = stat.st_mtime - run_started_at

    # File must have been written AFTER we started the run
    if stat.st_mtime >= run_started_at:
        result["is_valid"] = True

    return result


# ═════════════════════════════════════════════════════════════════════════════
# STEP 4 -- Read video duration via MoviePy (source of truth)
# ═════════════════════════════════════════════════════════════════════════════

def get_video_duration() -> float:
    """
    Use MoviePy (installed in .venv) to read the exact duration of
    output/news_video.mp4.

    Prints:  [DEBUG] Final video duration: XX.XX seconds
    Returns float duration, or 0.0 on error.
    """
    try:
        # Import from the already-running venv (this script IS running in venv)
        try:
            from moviepy.editor import VideoFileClip
        except ImportError:
            try:
                from moviepy.video.io.VideoFileClip import VideoFileClip
            except ImportError:
                from moviepy import VideoFileClip
        clip = VideoFileClip(OUTPUT_VIDEO)
        duration = clip.duration
        clip.close()
        print(f"\n[DEBUG] Final video duration: {duration:.2f} seconds")
        return duration
    except Exception as exc:
        print(f"[ERROR] MoviePy duration read failed: {exc}")
        return 0.0


# ═════════════════════════════════════════════════════════════════════════════
# STEP 5 -- Parse pipeline stdout for review data
# ═════════════════════════════════════════════════════════════════════════════

class ParsedRun:
    article_title: str = ""
    script:        str = ""
    context:       str = "unknown"
    scenes:        list = None   # list of {text, keyword, type, audio_dur}
    images_ok:     int  = 0
    images_fail:   int  = 0
    pipeline_ok:   bool = False
    channel_key:   str = "newscup"
    format_mode:   str = "short"

    def __init__(self):
        self.scenes = []


def parse_stdout(lines: list, exit_code: int) -> ParsedRun:
    """
    Extract structured data from main.py's printed output.
    Matches the actual print statements in each module.
    """
    run = ParsedRun()

    # Article title: "[NewsFetcher] Article: ..."
    for line in lines:
        m = re.search(r"\[NewsFetcher\] Article: (.+)", line)
        if m:
            run.article_title = m.group(1).strip()
            break

    # Context: "[ScriptGen] Context detected: '...'"
    for line in lines:
        m = re.search(r"\[ScriptGen\] Context detected: '([^']+)'", line)
        if m:
            run.context = m.group(1).strip()
            break

    # Script (between "Script preview:" line and next blank/header)
    for i, line in enumerate(lines):
        m = re.search(r"Script preview: (.+?)\.{3}$", line)
        if m:
            run.script = m.group(1).strip()
            break

    # Full script from ScriptGen final log: "[ScriptGen] Final -> N words ≈ Xs | M scenes | context='...'"
    for line in lines:
        m = re.search(r"\[ScriptGen\] Final -> (\d+) words.*?(\d+) scenes.*?context='([^']+)'", line)
        if m:
            run.context = m.group(3).strip()
            break

    # Scenes: Read from scenes.json (more reliable than stdout parsing)
    scenes_json_path = os.path.join(ROOT, "output", "scenes.json")
    if os.path.isfile(scenes_json_path):
        try:
            import json as _json
            with open(scenes_json_path, "r", encoding="utf-8") as _sf:
                _raw_scenes = _json.load(_sf)
            for _s in _raw_scenes:
                run.scenes.append({
                    "type":      _s.get("type", "general"),
                    "keyword":   _s.get("keyword", ""),
                    "text":      _s.get("text", ""),
                    "audio_dur": 0.0,
                    "has_image": bool(_s.get("image_path")),
                    "has_alt_image": bool(_s.get("alt_image_path")),
                })
            print(f"[REVIEW] Loaded {len(run.scenes)} scenes from scenes.json")
        except Exception as _je:
            print(f"[REVIEW] scenes.json load failed: {_je}")
    else:
        print("[REVIEW] scenes.json not found -- scene metrics will be limited")

    meta_json_path = os.path.join(ROOT, "output", "pipeline_meta.json")
    if os.path.isfile(meta_json_path):
        try:
            import json as _json
            with open(meta_json_path, "r", encoding="utf-8") as _mf:
                _meta = _json.load(_mf)
            run.channel_key = _meta.get("channel_key", "newscup")
            run.format_mode = _meta.get("format", "short")
            if _meta.get("story_context"):
                run.context = _meta.get("story_context")
            print(f"[REVIEW] Loaded channel_key='{run.channel_key}' and format='{run.format_mode}' from pipeline_meta.json")
        except Exception as _me:
            print(f"[REVIEW] pipeline_meta.json load failed: {_me}")

    # Audio: "[VoiceGen] Audio saved -> .../scene_XX_HASH.wav" or Cache hit
    audio_saved = {}
    for line in lines:
        m = re.search(r"\[VoiceGen\] (?:Audio saved|Cache hit) (?:->)? ?.*?scene_(\d+)_", line)
        if m:
            audio_saved[int(m.group(1))] = True

    # Video scenes: "[VideoBuilder] Scene XX -- Y.Zs | audio=Y | image=Y"
    video_scene_re = re.compile(
        r"\[VideoBuilder\] Scene (\d+)\s*(?:--|-)\s*([\d.]+)s\s*\|\s*audio=([YN])\s*\|\s*image=([YN])"
    )
    scene_durations = {}
    image_flags = {}
    for line in lines:
        m = video_scene_re.search(line)
        if m:
            idx     = int(m.group(1))
            dur     = float(m.group(2))
            audio_y = m.group(3) == "Y"
            image_y = m.group(4) == "Y"
            scene_durations[idx] = dur
            image_flags[idx]     = image_y
            if audio_y:
                run.images_ok += 1 if image_y else 0

    # Merge durations into scenes list
    for i, scene in enumerate(run.scenes):
        scene["audio_dur"] = scene_durations.get(i, 0.0)
        scene["has_image"] = image_flags.get(i, False)

    # If VideoBuilder lines weren't captured but we have scene count, fill from audio
    if scene_durations and not run.scenes:
        for idx, dur in sorted(scene_durations.items()):
            run.scenes.append({
                "type": "unknown", "keyword": "unknown",
                "text": f"[Scene {idx}]",
                "audio_dur": dur,
                "has_image": image_flags.get(idx, False),
            })

    # Images OK / fail
    run.images_ok   = sum(1 for v in image_flags.values() if v)
    run.images_fail = sum(1 for v in image_flags.values() if not v)

    # Pipeline success: "[SUCCESS] Video created: ..."
    for line in lines:
        if "[SUCCESS] Video created:" in line or "[VideoBuilder] [DONE]" in line:
            run.pipeline_ok = True
            break

    # If exit code == 0 and video exists, treat as ok
    if exit_code == 0 and os.path.isfile(OUTPUT_VIDEO):
        run.pipeline_ok = True

    return run


# ═════════════════════════════════════════════════════════════════════════════
# STEP 6 -- Mismatch detection
# ═════════════════════════════════════════════════════════════════════════════

def check_mismatch(duration: float, run: ParsedRun) -> list:
    """
    Print and return a list of mismatch events.
    Triggers "Execution mismatch detected" when thresholds breached.
    """
    mismatches = []

    if duration > 0 and not (TARGET_DUR_LOW <= duration <= TARGET_DUR_HIGH):
        mismatches.append(
            f"Duration {duration:.2f}s is outside expected range "
            f"({TARGET_DUR_LOW}–{TARGET_DUR_HIGH}s)"
        )

    if len(run.scenes) < MIN_SCENES:
        mismatches.append(
            f"Only {len(run.scenes)} scene(s) detected -- minimum is {MIN_SCENES}"
        )

    if not run.pipeline_ok:
        mismatches.append("Pipeline did not reach SUCCESS state")

    if mismatches:
        print("\n" + "!" * 60)
        print("  Execution mismatch detected")
        for m in mismatches:
            print(f"    * {m}")
        print("!" * 60 + "\n")

    return mismatches


# ═════════════════════════════════════════════════════════════════════════════
# STEP 7 -- Scoring engine (strict, 0–10)
# ═════════════════════════════════════════════════════════════════════════════

def _clamp(v, lo=0.0, hi=10.0):
    return max(lo, min(hi, float(v)))

def _wc(text):
    return len(text.split())

# Caption quality checks
def check_caption_sync(run: ParsedRun) -> tuple:
    """
    Check if captions (word count) are synchronized with scene durations.
    Returns (is_ok, issues_list)
    """
    issues = []
    
    for i, scene in enumerate(run.scenes):
        word_count = _wc(scene.get("text", ""))
        audio_dur = scene.get("audio_dur", 0.0)
        
        # Check: words should match audio duration (rough estimate: 150 wpm = 2.5 words/sec)
        expected_words = int(audio_dur * 2.5)
        actual_words = word_count
        
        # Allow 20% margin
        if actual_words > 0 and abs(actual_words - expected_words) > expected_words * 0.2:
            issues.append(
                f"Scene {i}: {actual_words} words vs {expected_words} expected "
                f"(audio {audio_dur:.1f}s) -- possible timing mismatch"
            )
    
    is_ok = len(issues) == 0
    return is_ok, issues

def check_scene_duration(run: ParsedRun) -> tuple:
    """
    Check if any scene exceeds 8 seconds (viewer fatigue threshold).
    Returns (is_ok, issues_list)
    """
    issues = []
    max_acceptable = 8.0
    
    for i, scene in enumerate(run.scenes):
        audio_dur = scene.get("audio_dur", 0.0)
        if audio_dur > max_acceptable:
            issues.append(
                f"Scene {i}: {audio_dur:.1f}s exceeds {max_acceptable}s -- "
                f"viewer fatigue risk"
            )
        if audio_dur > 10:
            issues.append(f"Scene {i}: too long (>10s) -- possible freeze")
    
    is_ok = len(issues) == 0
    return is_ok, issues

def check_caption_size(run: ParsedRun) -> tuple:
    """
    Check if any caption exceeds MAX_CAPTION_WORDS (12 words) for readability.
    Returns (is_ok, issues_list)
    """
    issues = []
    
    for i, scene in enumerate(run.scenes):
        text = scene.get("text", "")
        word_count = _wc(text)
        if word_count > MAX_CAPTION_WORDS:
            issues.append(
                f"Scene {i}: {word_count} words exceeds {MAX_CAPTION_WORDS} -- "
                f"readability overflow risk"
            )
    
    is_ok = len(issues) == 0
    return is_ok, issues

# ── Script quality ────────────────────────────────────────────────────────────

WEAK_OPENERS = [
    "here's what you need to know",
    "more updates are expected",
    "officials have yet to issue",
    "the public is being kept",
    "here's something important",
]
STRONG_SIGNALS = [
    "breaking", "urgent", "crisis", "warning", "historic", "record",
    "tensions", "conflict", "major", "emergency", "landmark", "victory",
]

def evaluate_hook_with_llama3(hook_text: str, channel_key: str) -> dict | None:
    if requests is None or CorrelationEngine is None:
        return None

    try:
        past_hooks = CorrelationEngine.get_hook_retention_traits(channel_key, limit=3)
    except Exception as e:
        print(f"[REVIEW] Hook scorer failed to fetch database hooks: {e}")
        past_hooks = []

    examples_str = ""
    if past_hooks:
        examples_str = "\nHere are examples of past HIGH-RETENTION hooks from this channel that succeeded:\n"
        for idx, h in enumerate(past_hooks):
            examples_str += f"- Hook: \"{h['hook_text']}\" (Retention Ratio: {h['hook_retention_ratio']*100:.1f}%)\n"

    prompt = f"""You are an expert short-form video optimization AI. Evaluate the following candidate video hook for the first 3-5 seconds of a news reel:
Candidate Hook: "{hook_text}"
{examples_str}
Evaluate the candidate hook on three criteria (each out of 10):
1. Curiosity Gap: Does it raise an immediate, compelling question or show a shocking detail that makes viewers want to keep watching?
2. Emotional Arousal: Does it use strong, active verbs and emotional/high-stimulus keywords?
3. Clarity / Information Delivery: Is it clean, concise, and easy to grasp in 3-5 seconds without generic cliches?

Provide your response in JSON format (and ONLY JSON, no markdown formatting outside the JSON, no extra text) with these keys:
{{
  "curiosity_gap_score": <float>,
  "emotional_arousal_score": <float>,
  "clarity_score": <float>,
  "explanation": "<string explaining the rating>",
  "suggestions": "<string with actionable recommendations to improve the hook>"
}}
"""
    payload = {
        "model": "llama3",
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.3,
            "top_p": 0.9,
            "num_predict": 400
        }
    }
    
    try:
        url = "http://localhost:11434/api/generate"
        response = requests.post(url, json=payload, timeout=12)
        if response.status_code == 200:
            resp_data = response.json()
            raw_text = resp_data.get("response", "").strip()
            
            # Find outer json bounds
            start = raw_text.find("{")
            end = raw_text.rfind("}")
            if start != -1 and end != -1:
                json_str = raw_text[start:end+1]
                import json
                data = json.loads(json_str)
                cg = float(data.get("curiosity_gap_score", 7.0))
                ea = float(data.get("emotional_arousal_score", 7.0))
                cl = float(data.get("clarity_score", 7.0))
                overall = round((cg + ea + cl) / 3.0, 1)
                
                return {
                    "overall_score": overall,
                    "explanation": data.get("explanation", ""),
                    "suggestions": data.get("suggestions", "")
                }
    except Exception as e:
        print(f"[REVIEW] Llama 3 hook evaluation request failed or timed out: {e}")
        
    return None

def score_hook(text: str, channel_key: str = "newscup") -> tuple:
    score, issues = 7.0, []
    
    llama_result = evaluate_hook_with_llama3(text, channel_key)
    if llama_result and "overall_score" in llama_result:
        score = llama_result["overall_score"]
        explanation = llama_result.get("explanation", "")
        suggestions = llama_result.get("suggestions", "")
        if explanation:
            issues.append(f"Llama 3 Scorer: {explanation}")
        if suggestions:
            issues.append(f"Llama 3 Suggestion: {suggestions}")
    else:
        tl = text.lower()
        for ph in WEAK_OPENERS:
            if ph in tl:
                score -= 2.5
                issues.append(f'Weak hook opener: "{ph}"')
                break
        strong = [w for w in STRONG_SIGNALS if w in tl]
        score += min(len(strong), 3) * 0.5
        if _wc(text) < 8:
            score -= 1.5
            issues.append("Hook < 8 words -- low engagement.")
        if _wc(text) > 30:
            score -= 1.0
            issues.append("Hook > 30 words -- too long.")
            
    return _clamp(score), issues

TONE_MAP = {
    "tense":       ["war","conflict","military","attack","ceasefire"],
    "positive":    ["win","success","victory","milestone","celebration"],
    "serious":     ["earthquake","flood","disaster","crisis","emergency"],
    "informative": ["technology","research","discovery","science","innovation","nasa","space"],
    "neutral":     [],
}

def score_tone(context: str, script: str) -> tuple:
    score, issues = 8.0, []
    sl = script.lower()
    expected = TONE_MAP.get(context, [])
    hits = sum(1 for kw in expected if kw in sl)
    if expected and hits == 0:
        score -= 3.0
        issues.append(
            f"Context '{context}' but no matching tone keywords in script."
        )
    elif expected and hits < 2:
        score -= 1.5
        issues.append(f"Context '{context}' weakly represented ({hits} keyword hits).")
    return _clamp(score), issues

FILLER = [
    "needless to say","it is worth noting","at this point in time",
    "due to the fact","as we can see",
]

def score_repetition(script: str) -> tuple:
    score, issues = 9.0, []
    sl = script.lower()
    for ph in FILLER:
        if ph in sl:
            score -= 1.5
            issues.append(f'Filler detected: "{ph}"')
    words = re.findall(r"\b\w{4,}\b", sl)
    tris  = [" ".join(words[i:i+3]) for i in range(len(words)-2)]
    seen  = {}
    for t in tris:
        seen[t] = seen.get(t, 0) + 1
    repeated = [(t,c) for t,c in seen.items() if c > 1]
    for t, c in repeated[:3]:
        score -= 0.8
        issues.append(f'Repeated 3-gram ({c}×): "{t}"')
    return _clamp(score), issues

def score_flow(scene_count: int, script: str) -> tuple:
    score, issues = 8.0, []
    if scene_count < 3:
        score -= 4.0; issues.append(f"Only {scene_count} scenes -- no narrative arc.")
    elif scene_count < 5:
        score -= 1.5; issues.append(f"Only {scene_count} scenes -- thin structure.")
    sents = re.split(r"(?<=[.!?])\s+", script.strip())
    if sents and not sents[-1].endswith((".", "!", "?")):
        score -= 1.5; issues.append("Ending sentence missing terminal punctuation.")
    return _clamp(score), issues

def score_script(run: ParsedRun) -> tuple:
    n = len(run.scenes)
    hook_text = run.scenes[0]["text"] if run.scenes else run.script
    h_s, h_i  = score_hook(hook_text, run.channel_key)
    t_s, t_i  = score_tone(run.context, run.script)
    r_s, r_i  = score_repetition(run.script)
    f_s, f_i  = score_flow(n, run.script)
    overall   = round((h_s + t_s + r_s + f_s) / 4, 1)
    return {"hook": round(h_s,1), "tone": round(t_s,1),
            "repetition": round(r_s,1), "flow": round(f_s,1),
            "overall": overall}, h_i + t_i + r_i + f_i

# ── Video length ──────────────────────────────────────────────────────────────

def score_length(dur: float) -> tuple:
    issues = []
    if dur <= 0:
        return 0.0, ["Cannot determine video duration."]
    if dur < 20:
        score = 1.0; issues.append(f"Video critically short ({dur:.1f}s) -- target 45–55s.")
    elif dur < 40:
        score = 4.5; issues.append(f"Video too short ({dur:.1f}s < 40s).")
    elif dur <= 55:
        score = 10.0
    elif dur <= 65:
        score = 7.5; issues.append(f"Video slightly over target ({dur:.1f}s > 55s).")
    else:
        score = 4.0; issues.append(f"Video too long ({dur:.1f}s > 65s).")
    return _clamp(score), issues

# ── Scene distribution ────────────────────────────────────────────────────────

def score_scenes(run: ParsedRun) -> tuple:
    n, issues = len(run.scenes), []
    if n < 3:    base = 2.0;  issues.append(f"Critically few scenes ({n}).")
    elif n < 6:  base = 6.0;  issues.append(f"Low scene count ({n}) -- consider splitting sentences.")
    elif n <= 10: base = 10.0
    elif n <= 14: base = 8.0;  issues.append(f"Many scenes ({n}) -- pacing may feel rushed.")
    else:         base = 5.0;  issues.append(f"Too many scenes ({n}).")
    long_s = [(i, _wc(s["text"])) for i, s in enumerate(run.scenes) if _wc(s["text"]) > 20]
    for i, w in long_s:
        issues.append(f"Scene {i+1}: {w} words -- very long; split recommended.")
    return _clamp(base - len(long_s) * 1.5), issues

# ── Captions ──────────────────────────────────────────────────────────────────

def score_captions(run: ParsedRun) -> tuple:
    score, issues = 10.0, []
    for i, s in enumerate(run.scenes):
        w = _wc(s["text"])
        if w > MAX_CAPTION_WORDS:
            score -= 1.2
            issues.append(f"Scene {i+1}: {w} words -- caption overflow risk.")
        lines = textwrap.wrap(s["text"], width=28)
        if len(lines) > 3:
            score -= 1.5
            issues.append(f"Scene {i+1}: wraps to {len(lines)} lines -- card overflow.")
    return _clamp(score), issues

# ── Timing ────────────────────────────────────────────────────────────────────

def score_timing(run: ParsedRun) -> tuple:
    score, issues = 10.0, []
    for i, s in enumerate(run.scenes):
        dur = s["audio_dur"]
        if dur == 0:
            score -= 1.0; issues.append(f"Scene {i+1}: no audio timing data."); continue
        wps = _wc(s["text"]) / dur
        if wps > 3.5:
            score -= 1.2; issues.append(f"Scene {i+1}: {wps:.1f} words/sec -- too fast.")
        elif wps < 0.8:
            score -= 0.5; issues.append(f"Scene {i+1}: {wps:.1f} words/sec -- too slow.")
    return _clamp(score), issues

# ── Image relevance ───────────────────────────────────────────────────────────

def score_images(run: ParsedRun, pacing_params: dict = None) -> tuple:
    score, issues = 10.0, []
    fail = run.images_fail
    if fail > 0:
        score -= fail * 1.5
        issues.append(f"{fail} scene(s) missing images -- fallback background used.")
        
    v_cut = 7.0
    if pacing_params:
        v_cut = pacing_params.get("visual_cut_threshold", 2.8)
        
    for i, s in enumerate(run.scenes):
        dur = s["audio_dur"]
        if dur > v_cut:
            if s.get("has_image") and not s.get("has_alt_image"):
                score -= 0.8
                issues.append(f"Scene {i+1}: {dur:.1f}s exceeds visual cut threshold ({v_cut:.1f}s) but lacks a B-roll cut -- static image fatigue risk.")
            elif dur > 7.0:
                score -= 0.5
                issues.append(f"Scene {i+1}: {dur:.1f}s on single image -- static.")
    return _clamp(score), issues

# ── Visual flow ───────────────────────────────────────────────────────────────

def score_flow_visual(run: ParsedRun, duration: float, pacing_params: dict = None) -> tuple:
    score, issues = 10.0, []
    v_cut = 7.0
    if pacing_params:
        v_cut = pacing_params.get("visual_cut_threshold", 2.8)
        
    for i, s in enumerate(run.scenes):
        if s["audio_dur"] > v_cut and not s.get("has_alt_image"):
            score -= 1.2; issues.append(f"Scene {i+1}: {s['audio_dur']:.1f}s exceeds visual cut threshold -- may bore viewers without B-roll.")
        elif s["audio_dur"] > 7.0:
            score -= 1.2; issues.append(f"Scene {i+1}: {s['audio_dur']:.1f}s -- may bore viewers.")
            
    if not any(s.get("has_image") for s in run.scenes):
        score -= 4.0; issues.append("No scenes have images -- entirely dark fallback.")
    return _clamp(score), issues

# ── Pacing ────────────────────────────────────────────────────────────────────

def score_pacing(run: ParsedRun, pacing_params: dict = None) -> tuple:
    durations = [s["audio_dur"] for s in run.scenes if s["audio_dur"] > 0]
    score, issues = 10.0, []
    if not durations:
        return 5.0, ["No audio data -- pacing cannot be evaluated."]
    avg = sum(durations) / len(durations)
    
    target_low = 4.0
    target_high = 6.0
    if pacing_params:
        pause = pacing_params.get("pause_after_sentence", 0.20)
        if pause < 0.15:
            target_low, target_high = 3.5, 5.5
        elif pause > 0.25:
            target_low, target_high = 4.5, 6.5
            
    if target_low <= avg <= target_high:
        issues.append(f"Pacing: GOOD (avg scene {avg:.1f}s)")
    else:
        score -= 2.0
        issues.append(f"Pacing: WEAK (avg scene {avg:.1f}s, target {target_low:.1f}-{target_high:.1f}s)")

    std = math.sqrt(sum((d-avg)**2 for d in durations) / len(durations))
    if std > 2.5:
        score -= 2.0; issues.append(f"Uneven pacing (σ={std:.1f}s).")
    for i, s in enumerate(run.scenes):
        if s["audio_dur"] > 7.0:
            score -= 0.8; issues.append(f"Scene {i+1}: {s['audio_dur']:.1f}s audio -- too slow.")
        elif 0 < s["audio_dur"] < 1.0:
            score -= 0.5; issues.append(f"Scene {i+1}: {s['audio_dur']:.1f}s -- too brief.")
    return _clamp(score), issues


# ═════════════════════════════════════════════════════════════════════════════
# STEP 8 -- Issue collector
# ═════════════════════════════════════════════════════════════════════════════

def collect_issues(run: ParsedRun, dur: float, scores: dict, mismatches: list) -> list:
    out = []

    # Mismatches first
    for m in mismatches:
        out.append(f"[EXECUTION MISMATCH] {m}")

    # Duration
    if dur > 0 and dur < 40:
        out.append(f"[VIDEO TOO SHORT] {dur:.2f}s -- target 45–55s.")
    if dur > 65:
        out.append(f"[VIDEO TOO LONG] {dur:.2f}s -- aim for under 60s.")

    # Scenes
    if len(run.scenes) < MIN_SCENES:
        out.append(f"[TOO FEW SCENES] {len(run.scenes)} scene(s) -- minimum {MIN_SCENES}.")

    # Per scene
    for i, s in enumerate(run.scenes):
        if _wc(s["text"]) > MAX_CAPTION_WORDS:
            out.append(f"[CAPTION TOO LONG] Scene {i+1}: {_wc(s['text'])} words -- will overflow.")
        if s["audio_dur"] > 6.0 and s.get("has_image"):
            out.append(f"[STATIC SCENE] Scene {i+1}: {s['audio_dur']:.1f}s single image -- boring.")
        if s["audio_dur"] > 7.0:
            out.append(f"[SCENE TOO LONG] Scene {i+1}: {s['audio_dur']:.1f}s -- loses attention.")
        if not s.get("has_image"):
            out.append(f"[IMAGE MISSING] Scene {i+1}: no image -- dark fallback used.")

    # Script
    if scores["script"]["hook"] < 5.0:
        out.append(f"[WEAK HOOK] Hook score {scores['script']['hook']}/10 -- needs stronger opener.")

    # Dedup
    seen, deduped = set(), []
    for item in out:
        k = item[:55]
        if k not in seen:
            seen.add(k); deduped.append(item)
    return deduped


# ═════════════════════════════════════════════════════════════════════════════
# STEP 9 -- Recommendations
# ═════════════════════════════════════════════════════════════════════════════

def recommendations(run: ParsedRun, dur: float, scores: dict) -> list:
    recs = []
    n = len(run.scenes)

    if dur > 0 and dur < 40:
        recs.append(
            "DURATION: Video is too short. Raise NUM_SENTENCES to 8 in config.py "
            "and lower MIN_WORDS to 50 in script_generator.py to force expansion."
        )

    if n < 6:
        recs.append(
            f"SCENES: Only {n} scenes. Increase NUM_SENTENCES=8 in config.py. "
            "Add a guard in main.py: if len(scenes) < 4: abort and re-run."
        )

    if scores["script"]["hook"] < 6:
        recs.append(
            "HOOK: Opening lacks engagement. The generate_hook() prefix should fire "
            "with context-matched opener (e.g., 'Here's something important…'). "
            "Verify script_generator.py is not trimming the hook prefix away."
        )

    if scores["script"]["flow"] < 7:
        recs.append(
            "FLOW: Narrow script. Ensure generate_ending() appends its closing line "
            "and _trim_script() does not remove it (uses pop(-2) -- should be safe)."
        )

    long_scenes = [i+1 for i, s in enumerate(run.scenes) if _wc(s["text"]) > 12]
    if long_scenes:
        recs.append(
            f"CAPTIONS: Scenes {long_scenes} exceed 12 words. "
            "Split each sentence at 'and'/'but'/'which' in the script before scene_planner."
        )

    if run.images_fail > 0:
        recs.append(
            f"IMAGES: {run.images_fail} scene(s) missing images. "
            "Broaden Pexels fallback queries or add local image pool in image_fetcher.py."
        )

    if scores["pacing"] < 7:
        recs.append(
            "PACING: Scene lengths are inconsistent. Split long-audio sentences "
            "and merge very-short ones for uniform rhythm."
        )

    if scores["visual_flow"] < 7:
        recs.append(
            "VISUAL: Some scenes exceed 6s on a single image -- static effect. "
            "Subdivide long sentences or add a second image query per scene."
        )

    return recs


# ═════════════════════════════════════════════════════════════════════════════
# STEP 10 -- Write report
# ═════════════════════════════════════════════════════════════════════════════

def _bar(s, w=20):
    f = int(round(s / 10 * w))
    return f"[{'█'*f}{'░'*(w-f)}] {s}/10"

def _grade(s, issues=None):
    if issues is None:
        issues = []
    
    duration_issue = any("short" in i.lower() or "long" in i.lower() for i in issues if "video" in i.lower())
    freeze_issue = any("freeze" in i.lower() or ">10s" in i.lower() for i in issues)
    pacing_weak = any("pacing: weak" in i.lower() for i in issues)
    
    if not duration_issue and not freeze_issue and not pacing_weak:
        return "✅ GOOD"
    else:
        return "🚨 BAD"

def overall_score(scores: dict) -> float:
    W = dict(script=0.22, length=0.18, scenes=0.13, captions=0.12,
             timing=0.10, images=0.10, visual_flow=0.08, pacing=0.07)
    return round(
        W["script"]      * scores["script"]["overall"]
        + W["length"]    * scores["length"]
        + W["scenes"]    * scores["scenes"]
        + W["captions"]  * scores["captions"]
        + W["timing"]    * scores["timing"]
        + W["images"]    * scores["images"]
        + W["visual_flow"]* scores["visual_flow"]
        + W["pacing"]    * scores["pacing"], 1)


def write_report(run: ParsedRun, dur: float, scores: dict,
                 issues: list, recs: list, file_meta: dict,
                 mismatches: list, elapsed: float) -> str:

    ov   = overall_score(scores)
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    L    = []
    A    = L.append

    A("# 🎬 AI Video Review Report")
    A("")
    A(f"> **Generated:** {ts}  ")
    A(f"> **Executed:** `.venv\\Scripts\\python.exe main.py`  ")
    A(f"> **FORCE_REFRESH:** 1 (new images fetched)  ")
    A(f"> **Pipeline status:** {'✅ SUCCESS' if run.pipeline_ok else '❌ FAILED'}  ")
    A(f"> **Pipeline runtime:** {elapsed:.1f}s  ")
    A(f"> **Article:** {run.article_title or 'N/A'}  ")
    A(f"> **Context detected:** `{run.context}`")
    A("")
    if mismatches:
        A("> WARNING:️ **EXECUTION MISMATCH DETECTED** -- see Issues section")
        A("")
    A("---")
    A("")

    # ── Summary ───────────────────────────────────────────────────────────
    A("## 🎯 Summary Score")
    A("")
    A(f"### Overall: **{ov}/10** -- {_grade(ov, issues)}")
    A("")
    A(f"{_bar(ov)}")
    A("")
    A("| Dimension | Score | Bar | Grade |")
    A("|-----------|-------|-----|-------|")
    A(f"| Script Quality | {scores['script']['overall']}/10 | {_bar(scores['script']['overall'],12)} | {_grade(scores['script']['overall'])} |")
    A(f"| Video Length | {scores['length']}/10 | {_bar(scores['length'],12)} | {_grade(scores['length'])} |")
    A(f"| Scene Distribution | {scores['scenes']}/10 | {_bar(scores['scenes'],12)} | {_grade(scores['scenes'])} |")
    A(f"| Caption Quality | {scores['captions']}/10 | {_bar(scores['captions'],12)} | {_grade(scores['captions'])} |")
    A(f"| Caption Timing | {scores['timing']}/10 | {_bar(scores['timing'],12)} | {_grade(scores['timing'])} |")
    A(f"| Image Relevance | {scores['images']}/10 | {_bar(scores['images'],12)} | {_grade(scores['images'])} |")
    A(f"| Visual Flow | {scores['visual_flow']}/10 | {_bar(scores['visual_flow'],12)} | {_grade(scores['visual_flow'])} |")
    A(f"| Pacing | {scores['pacing']}/10 | {_bar(scores['pacing'],12)} | {_grade(scores['pacing'])} |")
    A("")
    A("---")
    A("")

    # ── Video file ────────────────────────────────────────────────────────
    A("## 📁 Output File Verification")
    A("")
    A(f"| Property | Value |")
    A(f"|----------|-------|")
    A(f"| Path | `output/news_video.mp4` |")
    A(f"| Size | {file_meta['size_bytes'] / 1024 / 1024:.2f} MB |")
    A(f"| Modified | {datetime.fromtimestamp(file_meta['mtime']).strftime('%Y-%m-%d %H:%M:%S') if file_meta['mtime'] else 'N/A'} |")
    A(f"| Belongs to this run | {'✅ YES' if file_meta['is_valid'] else '❌ NO -- older file'} |")
    A(f"| **Duration (MoviePy)** | **{dur:.2f}s** |")
    A(f"| Target duration | 45–55s |")
    A(f"| Duration status | {'✅ On target' if 40 <= dur <= 60 else '🚨 OFF TARGET'} |")
    A("")
    A("---")
    A("")

    # ── Script ────────────────────────────────────────────────────────────
    A("## 📝 Script Review")
    A("")
    A(f"**Context / Tone detected:** `{run.context}`")
    A("")
    A("| Sub-dimension | Score | Bar |")
    A("|---------------|-------|-----|")
    A(f"| Hook strength | {scores['script']['hook']}/10 | {_bar(scores['script']['hook'],12)} |")
    A(f"| Story flow | {scores['script']['flow']}/10 | {_bar(scores['script']['flow'],12)} |")
    A(f"| Tone match | {scores['script']['tone']}/10 | {_bar(scores['script']['tone'],12)} |")
    A(f"| Repetition/filler | {scores['script']['repetition']}/10 | {_bar(scores['script']['repetition'],12)} |")
    A("")
    if run.script:
        A("### Script (captured from pipeline output)")
        A("")
        A("```")
        A(run.script)
        A("```")
        A("")
    A("---")
    A("")

    # ── Metrics ───────────────────────────────────────────────────────────
    A("## 📊 Video Metrics")
    A("")
    durations = [s["audio_dur"] for s in run.scenes if s["audio_dur"] > 0]
    avg_dur   = sum(durations)/len(durations) if durations else 0
    words_per = [_wc(s["text"]) for s in run.scenes]
    avg_words = sum(words_per)/len(words_per) if words_per else 0
    A(f"| Metric | Value |")
    A(f"|--------|-------|")
    A(f"| Video duration (MoviePy) | **{dur:.2f}s** |")
    A(f"| Total scenes | {len(run.scenes)} |")
    A(f"| Avg scene duration | {avg_dur:.1f}s |")
    A(f"| Avg words / scene | {avg_words:.1f} |")
    A(f"| Images OK | {run.images_ok} |")
    A(f"| Images missing | {run.images_fail} |")
    A("")
    A("### Per-Scene Breakdown")
    A("")
    A("| # | Type | Keyword | Words | Audio | Image | Text Preview |")
    A("|---|------|---------|-------|-------|-------|--------------|")
    for i, s in enumerate(run.scenes):
        preview = s["text"][:50]+"…" if len(s["text"])>50 else s["text"]
        img_ok  = "✅" if s.get("has_image") else "❌"
        dur_s   = f"{s['audio_dur']:.1f}s" if s["audio_dur"] else "N/A"
        A(f"| {i+1} | {s['type']} | {s['keyword']} | {_wc(s['text'])} | {dur_s} | {img_ok} | {preview} |")
    A("")
    A("---")
    A("")

    # ── Issues ────────────────────────────────────────────────────────────
    A("## 🚨 Issues Detected")
    A("")
    if issues:
        for iss in issues:
            A(f"- {iss}")
    else:
        A("✅ No critical issues detected.")
    A("")
    A("---")
    A("")

    # ── Recommendations ───────────────────────────────────────────────────
    A("## 💡 Recommendations (Actionable)")
    A("")
    if recs:
        for r in recs:
            A(f"- **{r}**")
    else:
        A("✅ No immediate improvements needed.")
    A("")
    A("---")
    A("")

    # ── Mismatch detail ───────────────────────────────────────────────────
    if mismatches:
        A("## WARNING:️ Execution Mismatch Detail")
        A("")
        for m in mismatches:
            A(f"- {m}")
        A("")
        A("---")
        A("")

    A("*Report generated by `video_review.py` -- Strict pipeline execution + review*")

    content = "\n".join(L)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(content)
    return REPORT_PATH


# ═════════════════════════════════════════════════════════════════════════════
# MAIN ORCHESTRATOR
# ═════════════════════════════════════════════════════════════════════════════

def main():
    print("\n" + "═" * 60)
    print("  AI VIDEO REVIEW SYSTEM -- Strict Execution Mode")
    print("  Venv: .venv\\Scripts\\python.exe")
    print("  Entry: main.py")
    print("═" * 60)

    # ── Pre-flight ────────────────────────────────────────────────────────
    if not preflight():
        print("[ABORT] Pre-flight checks failed.")
        sys.exit(1)

    # Record timestamp BEFORE run so we can verify the output file
    run_started_at = time.time()

    # ── Execute pipeline ──────────────────────────────────────────────────
    stdout_lines, exit_code, elapsed = run_main_pipeline()

    if exit_code != 0:
        print(f"[REVIEW] WARNING:️  main.py exited with code {exit_code} -- reviewing any output.")

    # ── Verify output file ────────────────────────────────────────────────
    print("\n[REVIEW] Verifying output file…")
    file_meta = verify_output(run_started_at)
    if not file_meta["is_valid"]:
        print("[REVIEW] ❌ news_video.mp4 was not produced by this run (missing or stale).")
    else:
        print(f"[REVIEW] ✅ news_video.mp4 confirmed -- {file_meta['size_bytes']//1024} KB")

    # ── Duration via MoviePy ──────────────────────────────────────────────
    print("\n[REVIEW] Reading video duration via MoviePy…")
    duration = get_video_duration() if file_meta["is_valid"] else 0.0

    # ── Parse stdout ──────────────────────────────────────────────────────
    print("\n[REVIEW] Parsing pipeline output…")
    run = parse_stdout(stdout_lines, exit_code)
    print(f"[REVIEW] Scenes captured: {len(run.scenes)}")
    print(f"[REVIEW] Context: {run.context}")
    print(f"[REVIEW] Pipeline OK: {run.pipeline_ok}")

    # ── Mismatch check ────────────────────────────────────────────────────
    mismatches = check_mismatch(duration, run)

    # ── Score ─────────────────────────────────────────────────────────────
    print("\n[REVIEW] Scoring…")
    pacing_params = None
    if CorrelationEngine is not None:
        try:
            pacing_params = CorrelationEngine.get_optimized_pacing_and_style(run.channel_key, run.format_mode)
            print(f"[REVIEW] Learned pacing benchmarks: visual_cut_threshold={pacing_params.get('visual_cut_threshold')}s, pause_after_sentence={pacing_params.get('pause_after_sentence')}s")
        except Exception as e:
            print(f"[REVIEW] Failed to load learned pacing benchmarks: {e}")

    s_script,  _ = score_script(run)
    s_length,  _ = score_length(duration)
    s_scenes,  _ = score_scenes(run)
    s_caps,    _ = score_captions(run)
    s_timing,  _ = score_timing(run)
    s_images,  _ = score_images(run, pacing_params)
    s_flow,    _ = score_flow_visual(run, duration, pacing_params)
    s_pacing,  _ = score_pacing(run, pacing_params)

    scores = {
        "script":      s_script,
        "length":      round(s_length, 1),
        "scenes":      round(s_scenes, 1),
        "captions":    round(s_caps, 1),
        "timing":      round(s_timing, 1),
        "images":      round(s_images, 1),
        "visual_flow": round(s_flow, 1),
        "pacing":      round(s_pacing, 1),
    }

    # ── Issues & Recommendations ──────────────────────────────────────────
    issues = collect_issues(run, duration, scores, mismatches)
    recs   = recommendations(run, duration, scores)

    # ── Write report ──────────────────────────────────────────────────────
    print("\n[REVIEW] Writing report…")
    report_path = write_report(
        run, duration, scores, issues, recs,
        file_meta, mismatches, elapsed
    )

    # ── Final summary ─────────────────────────────────────────────────────
    ov = overall_score(scores)
    print("\n" + "═" * 60)
    print(f"  REVIEW COMPLETE")
    print(f"  Overall Score : {ov}/10  {_grade(ov)}")
    print(f"  Duration      : {duration:.2f}s")
    print(f"  Scenes        : {len(run.scenes)}")
    print(f"  Issues        : {len(issues)}")
    print(f"  Mismatches    : {len(mismatches)}")
    print(f"  Report        : {report_path}")
    print("═" * 60 + "\n")


if __name__ == "__main__":
    main()
