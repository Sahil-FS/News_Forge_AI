# script_generator.py -- Dynamic context-aware news narrative generator
# Target voiceover: 25–35 seconds  (~65–90 words @ 150 wpm)
#
# Pipeline:
#   clean -> spaCy doc -> detect_context -> generate_hook (doc-driven)
#   -> build_story (scored body) -> generate_ending ->  regulate word count

import sys

# Environment lock
import os as _os_env_check
if "VIRTUAL_ENV" not in _os_env_check.environ and ".venv" not in sys.executable and "venv" not in sys.executable:
    print(f"[WARN] Running outside a virtual environment: {sys.executable}")

print(f"[ENV OK] {sys.executable}")

import heapq
import re
import spacy
import requests

from utils import clean_caption_text
from config import (
    OLLAMA_URL,
    OLLAMA_NUM_PREDICT,
    OLLAMA_TEMPERATURE,
    OLLAMA_TOP_P,
    OLLAMA_REPEAT_PENALTY,
    SCRIPT_MIN_INPUT_CHARS,
    SCRIPT_OOV_THRESHOLD,
    SCRIPT_MIN_VERBLESS_SENTENCES,
)

def remove_exact_duplicates(text):
    words = text.split()
    result = []
    prev = None
    
    for w in words:
        if w != prev:
            result.append(w)
        prev = w
        
    return " ".join(result)

def is_weak_hook(line):
    bad_starts = ("as ", "in ", "today", "what", "this", "recently")
    return line.lower().startswith(bad_starts)

def validate_script(script, target_words):
    words = script.split()
    if len(words) < int(target_words * 0.7):
        return False

    first_line = re.split(r'[.!।?]', script)[0]
    if len(first_line.split()) < 6:
        return False

    if first_line.lower().startswith(("today", "yesterday", "president")):
        return False

    has_devanagari = bool(re.search(r'[\u0900-\u097F]', first_line))
    if not has_devanagari:
        if not any(char.isupper() for char in first_line if char.isalpha()):
            return False

    # Reject scripts full of generic filler phrases
    _FILLER_PHRASES = [
        "global angle", "power of nature", "power of natural",
        "highlights the need", "serves as a reminder",
        "underscores the importance", "raising questions about",
        "experts warn", "analysts say", "the world watches",
        "as the situation", "it remains to be seen",
        "the coming days will", "the international community",
    ]
    _sentences = script.split(".")
    _filler_count = sum(
        1 for sent in _sentences
        if any(filler in sent.lower() for filler in _FILLER_PHRASES)
    )
    # If more than 2 sentences are generic filler, reject and regenerate
    if _filler_count >= 2:
        print(f"[ScriptGen] WARNING:️  Script has {_filler_count} generic filler sentences -- regenerating")
        return False

    if not has_devanagari:
        # Sentence completeness — reject scripts where >2 sentences lack a verb
        _COMMON_VERBS = {
            "is", "are", "was", "were", "has", "have", "had", "been",
            "killed", "died", "dead", "attacked", "struck", "destroyed",
            "said", "says", "warned", "announced", "confirmed", "reported",
            "arrested", "detained", "launched", "fired", "wounded", "injured",
            "signed", "passed", "blocked", "suspended", "imposed",
            "called", "urged", "demanded", "declared", "claimed",
            "hit", "left", "caused", "reached", "found", "made", "took",
            "came", "went", "saw", "told", "began", "led", "set", "cut",
            "broke", "fell", "rose", "grew", "ran", "sent", "put", "got",
            "brought", "held", "stood", "lost", "won", "met", "built",
            "shows", "remains", "continues", "threatens", "faces",
            "spreads", "warns", "kills", "destroys", "marks", "raises",
        }
        _raw_sentences = [s.strip() for s in script.split('.') if s.strip() and len(s.strip().split()) >= 3]
        _verbless = sum(1 for s in _raw_sentences if not any(
            tok.lower().rstrip(",.;:") in _COMMON_VERBS for tok in s.split()
        ))
        if _verbless > SCRIPT_MIN_VERBLESS_SENTENCES:
            print(f"[ScriptGen] WARNING: {_verbless} sentences lack verbs -- regenerating")
            return False

    return True


def _script_relevance_ok(script: str, original_text: str, doc) -> bool:
    """Basic relevance audit: ensure generated script is grounded in the source article."""
    if not script or not original_text:
        return False

    original_doc = doc
    article_tokens = {
        token.lemma_.lower()
        for token in original_doc
        if token.is_alpha and not token.is_stop and len(token.lemma_) > 3
    }
    article_tokens |= {
        ent.text.lower()
        for ent in original_doc.ents
        if len(ent.text) > 1
    }

    script_doc = nlp(script)
    script_tokens = [
        token.lemma_.lower()
        for token in script_doc
        if token.is_alpha and not token.is_stop and len(token.lemma_) > 3
    ]

    # Common news vocabulary words are never OOV -- they appear in
    # any news article regardless of topic (analysts, warn, risk, stark, etc.)
    _COMMON_NEWS_VOCAB = {
        "warn", "warned", "warning", "stark", "risk", "risks", "risky",
        "global", "local", "national", "international", "major", "key",
        "make", "made", "makes", "induce", "induced", "vulnerable",
        "affect", "impact", "crisis", "concern", "threat", "serious",
        "significant", "important", "critical", "potential", "possible",
        "report", "reports", "reported", "official", "officials",
        "government", "public", "policy", "economic", "financial",
        "people", "country", "world", "year", "years", "time", "week",
        "show", "shows", "expect", "expected", "include", "including",
        "increase", "decrease", "rise", "fall", "grow", "decline",
        "face", "faces", "facing", "follow", "following", "lead", "led",
        "need", "needs", "need", "help", "helped", "support", "supported",
        "call", "called", "calls", "move", "moved", "moves", "announce",
        "announced", "plan", "plans", "planned", "push", "pushed",
        "begin", "began", "start", "started", "continue", "continued",
        "come", "came", "bring", "brought", "take", "took", "give", "gave",
        "know", "known", "seen", "seen", "said", "says", "tell", "told",
        "high", "low", "large", "small", "long", "short", "new", "old",
        "first", "last", "next", "recent", "current", "previous",
        "over", "under", "more", "less", "much", "many", "some", "most",
    }
    # Add to _COMMON_NEWS_VOCAB inside _script_relevance_ok():
    _GEO_DEMONYMS = {
        # Demonyms (country → nationality adjective)
        "tunisian", "tunisians", "ukrainian", "ukrainians", "russian", "russians",
        "iranian", "iranians", "israeli", "israelis", "palestinian", "palestinians",
        "chinese", "american", "americans", "french", "german", "british",
        "indian", "indians", "pakistani", "pakistanis", "lebanese", "syrian",
        # Common news verbs and political vocabulary
        "rally", "rallied", "rallies", "protest", "protested", "protests",
        "march", "marched", "marches", "denounce", "denounced", "condemn",
        "arrested", "detain", "detained", "crackdown", "suppress", "suppressed",
        "demonstrate", "demonstration", "demonstrations", "demonstrators",
        "opposition", "dissent", "dissident", "regime", "authoritarian",
        "economic", "economy", "inflation", "unemployment", "poverty",
        "revolution", "democratic", "democracy", "constitution", "constitutional",
        # Scale/casualty words common in all articles
        "thousand", "hundreds", "dozens", "casualties", "injured", "injure",
        "destroy", "destruction", "devastate", "devastating", "damage",
        "extent", "stretch", "surround", "besiege", "blockade",
    }
    _COMMON_NEWS_VOCAB |= _GEO_DEMONYMS

    # Additional generic news words that Ollama commonly uses and are
    # legitimately present in any conflict/politics/disaster article. These were
    # confirmed OOV false-positives from the Ukraine/Russia log:
    # "30 out-of-article terms: spark, chaos, shot, city, hard, area, eyewitness, scene"
    _ADDITIONAL_NEWS_VOCAB = {
        # Sensory / scene description (universal in all news)
        "spark", "sparks", "sparked", "chaos", "scene", "scenes",
        "area", "zone", "region", "site", "city", "cities", "town", "towns",
        "shot", "shots", "fire", "fires", "hard", "heavy",
        "severe", "intense", "massive", "widespread",
        "eyewitness", "witness", "witnesses",
        "resident", "residents", "spokesperson", "spokesman", "spokeswoman",
        "source", "sources", "analyst", "analysts", "expert", "experts",
        # Conflict vocabulary
        "strike", "strikes", "drone", "drones", "missile", "missiles",
        "shelling", "bombardment", "evacuation", "casualty", "casualties",
        "ceasefire", "offensive", "counteroffensive", "frontline", "battlefront",
        "explosion", "blast", "detonation", "impact", "debris",
        # Political vocabulary
        "rally", "rallied", "protest", "protested", "march", "marched",
        "denounce", "denounced", "condemn", "condemned",
        "sanction", "sanctioned", "arrest", "arrested", "detain", "detained",
        "crackdown", "opposition", "dissent", "dissident", "regime", "authoritarian",
        "election", "ballot", "referendum", "parliament", "legislation",
        # Scale / quantity words
        "thousand", "thousands", "hundreds", "dozens", "several", "multiple",
        "least", "approximately", "roughly", "nearly", "almost",
        # Additional demonyms not in _GEO_DEMONYMS
        "belarusian", "azerbaijani", "armenian", "georgian", "moldovan",
        "yemeni", "libyan", "somali", "sudanese", "ethiopian", "nigerian",
    }
    _COMMON_NEWS_VOCAB |= _ADDITIONAL_NEWS_VOCAB

    oov = [token for token in script_tokens
           if token not in article_tokens and token not in _COMMON_NEWS_VOCAB]

    # Raised threshold from 28 to 32 — Ollama uses legitimate news
    # vocabulary not verbatim in article.
    if len(oov) > SCRIPT_OOV_THRESHOLD:
        print(f"[ScriptGen] Relevance fail: {len(oov)} out-of-article terms: "
              f"{', '.join(oov[:8])}")
        return False

    article_entities = [
        ent.text.lower() for ent in original_doc.ents
        if ent.label_ in ("PERSON", "ORG", "GPE", "NORP", "FAC", "LAW")
    ]
    if article_entities:
        hits = sum(1 for ent in set(article_entities) if ent in script.lower())

        # Count demonyms/nationality adjectives as valid entity hits.
        # Ollama writes "Ukrainian" instead of "Ukraine" for variety — that is valid.
        _DEMONYM_MAP = {
            "ukrainian": ["ukraine", "ukrainian"],
            "russian": ["russia", "russian"],
            "iranian": ["iran", "iranian"],
            "israeli": ["israel", "israeli"],
            "indian": ["india", "indian"],
            "american": ["united states", "america", "american"],
            "british": ["britain", "uk", "british"],
            "chinese": ["china", "chinese"],
        }
        _script_lower = script.lower()
        _orig_lower = original_text.lower()
        _demonym_hit = any(
            dem in _script_lower
            for dem_list in _DEMONYM_MAP.values()
            for dem in dem_list
            if dem in _orig_lower
        )
        if _demonym_hit:
            hits += 1  # demonym usage counts as a valid article entity match

        # Relax entity check constraint to 0 for shorter articles (< 150 words)
        min_hits = 0 if len(original_text.split()) < 150 else 1
        if hits < min_hits:
            print(f"[ScriptGen] Relevance fail: named entities in script ({hits}) < minimum required ({min_hits})")
            return False
        print(f"[ScriptGen] Relevance OK: {hits} article entities confirmed in script")

    return True

# ── Constants ─────────────────────────────────────────────────────────────────
SPEECH_RATE_WPS = 2.5  # slightly faster = more words needed to fill time

MAX_VIDEO_SEC = 55
MIN_VIDEO_SEC = 45

# ── spaCy model ───────────────────────────────────────────────────────────────
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    raise OSError(
        "[ScriptGen] spaCy model not found. Run:\n"
        "  python -m spacy download en_core_web_sm"
    )


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 -- Text utilities
# ══════════════════════════════════════════════════════════════════════════════

def _clean(text: str) -> str:
    """Normalise whitespace and remove duplicate punctuation."""
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\.{2,}", ".", text)                    # ellipsis -> single dot
    text = re.sub(r"([.!?])\s*([.!?])+", r"\1", text)    # !! / .! -> single
    text = re.sub(r"\s+([.,!?])", r"\1", text)            # space before punct
    return text.strip()


def _word_count(text: str) -> int:
    return len(text.split())


def _sentence_list(text: str) -> list[str]:
    """Split on sentence-ending punctuation; keep each sentence intact."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _dedupe_sentences(sentences: list[str]) -> list[str]:
    """Remove exact and near-duplicate sentences (first-10-word fingerprint)."""
    seen: set[str] = set()
    out: list[str] = []
    for s in sentences:
        key = " ".join(s.lower().split()[:10])
        if key not in seen:
            seen.add(key)
            out.append(s)
    return out


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 -- Context / emotion detection
# ══════════════════════════════════════════════════════════════════════════════

def detect_context(doc) -> str:
    """
    Score all context categories, return the highest-scoring one.
    Uses additive scoring so war stories with political figures
    are not misclassified as 'politics'.
    """
    text = doc.text.lower()

    # Violence override -- if active violence words are present,
    # tense detection is never suppressed
    VIOLENCE_OVERRIDE = {
        "violating", "violation", "violated", "breached", "breach",
        "attack", "attacked", "attacking", "fired", "firing", "shelling",
        "killed", "wounded", "casualties", "troops", "military",
        "invasion", "invaded", "airstrike", "bombardment", "artillery",
        "separatist", "offensive", "counteroffensive", "clash", "clashes",
        "conflict", "war", "hostage", "bomb", "explosion", "ceasefire",
        "gunfire", "shooting", "shooter", "assault", "siege",
    }
    has_violence = any(v in text for v in VIOLENCE_OVERRIDE)

    # Neutralisers -- only ceremony/commemoration suppress tense, NOT diplomacy
    TENSE_NEUTRALISERS = {
        "state visit", "ceremony", "ceremonial", "inauguration",
        "swearing-in", "commemorate", "memorial", "tribute",
        "trade deal", "trade agreement",
    }
    tense_neutralised = (not has_violence) and any(w in text for w in TENSE_NEUTRALISERS)

    # Scoring rules: {label: [(keywords, weight_per_hit)]}
    CONTEXT_SCORES = {
        "tense": [
            (["war", "conflict", "invasion", "airstrike", "bomb", "hostage",
              "ceasefire violation", "military action"], 3),
            (["attack", "attacked", "fired", "firing", "shelling", "troops",
              "casualties", "wounded", "killed", "clash", "clashes",
              "shooting", "armed", "offensive", "siege"], 2),
            (["terror", "terrorism", "security breach", "police", "arrest",
              "threat level", "separatist", "gunfire"], 1),
        ],
        "serious": [
            (["earthquake", "flood", "tsunami", "wildfire", "hurricane",
              "death toll", "disaster", "famine", "epidemic", "pandemic",
              "outbreak", "virus", "ebola", "mpox", "infection", "infections",
              "cases", "illness", "deaths", "sick", "patient", "patients"], 3),
            (["crisis", "rescue", "evacuation", "emergency", "storm",
              "tornado", "avalanche", "landslide",
              "health", "quarantine", "hospital", "hospitals", "medical",
              "clinics", "transmission", "vaccine", "vaccines", "who"], 2),
        ],
        "politics": [
            (["prime minister", "president", "election", "parliament",
              "congress", "senate", "legislation", "cabinet", "minister"], 2),
            (["policy", "vote", "ballot", "summit", "diplomatic",
              "sanctions", "treaty", "accord"], 1),
        ],
        "positive": [
            (["win", "victory", "record", "celebration", "award",
              "milestone", "breakthrough", "historic"], 2),
            (["success", "achievement", "champion", "triumph"], 1),
        ],
        "sports": [
            (["football", "soccer", "match", "goal", "goals", "transfer",
              "player", "champions league", "premier league", "world cup",
              "la liga", "stadium", "tournament", "defeat", "scoring", "scored",
              "injury", "signing", "fifa", "uefa"], 2),
            (["coach", "manager", "trophy", "league", "club", "team", "cup",
              "game", "referee", "striker", "midfielder", "defender", "goalkeeper"], 1),
        ],
        "informative": [
            (["artificial intelligence", "space", "nasa", "innovation",
              "discovery", "research", "quantum", "nuclear energy"], 2),
            (["technology", "ai", "robot", "software", "satellite",
              "launch", "cyber", "digital"], 1),
        ],
    }

    scores = {label: 0 for label in CONTEXT_SCORES}

    for label, rules in CONTEXT_SCORES.items():
        for keywords, weight in rules:
            for kw in keywords:
                if kw in text:
                    scores[label] += weight

    # Suppress tense if neutralised (and no violence)
    if tense_neutralised:
        scores["tense"] = 0

    # Tense always wins over politics if tied or close (war > diplomacy)
    if scores["tense"] > 0 and scores["tense"] >= scores["politics"] - 1:
        scores["politics"] = max(0, scores["politics"] - 2)

    best_label = max(scores, key=scores.get)
    best_score = scores[best_label]

    print(f"[ScriptGen] Context scores: {scores}")
    print(f"[ScriptGen] Context detected: '{best_label}' (score={best_score})")

    return best_label if best_score > 0 else "neutral"


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 -- Word-count regulators
# ══════════════════════════════════════════════════════════════════════════════

def estimate_duration_from_text(text):
    words = len(text.split())
    return words / SPEECH_RATE_WPS

def calculate_target_words(input_text: str) -> int:
    base_words = len(input_text.split())
    max_words = int(MAX_VIDEO_SEC * SPEECH_RATE_WPS)  # was hardcoded 65
    min_words = int(MIN_VIDEO_SEC * SPEECH_RATE_WPS)  # was hardcoded 48
    return max(min(base_words, max_words), min_words)

def _normalize_ollama_output(text: str) -> str:
    text = text.strip()
    if not text:
        return text

    # ── Strip known LLM meta-commentary prefixes ──────────────────────
    # These patterns appear when llama3 explains itself before the script.
    # We strip everything up to and including the colon on the same line.
    LEAK_PATTERNS = [
        r"(?i)^here[\s\S]*?(?:script|output|response)[:\s]+",
        r"(?i)^sure[\s\S]*?(?:script|output|response)[:\s]+",
        r"(?i)^okay[\s\S]*?(?:script|output|response)[:\s]+",
        r"(?i)^below is[\s\S]*?(?:script|output|response)[:\s]+",
        r"(?i)^this is[\s\S]*?(?:script|output|response)[:\s]+",
        r"(?i)^i(?:'ve| have) written[\s\S]*?[:\s]+",
        r"(?i)^(?:here|below)[^\n]*?[\d]+[- ]word[^\n]*\n",
    ]

    import re as _re
    for pattern in LEAK_PATTERNS:
        text = _re.sub(pattern, "", text, count=1).strip()

    # ── Strip existing markers ────────────────────────────────────────
    for marker in [
        "Thinking Process:", "Final Answer:", "Output:",
        "Answer:", "Response:", "Script:", "Note:"
    ]:
        if marker in text:
            text = text.split(marker)[-1].strip()

    # ── Strip any leading line that has no terminal punctuation
    # and is under 12 words -- these are always header/label lines ────
    lines = text.splitlines()
    # Replace the existing while lines: block with:
    _NEWS_SIGNAL_WORDS = {
        "killed", "dead", "died", "attack", "war", "crisis", "arrest",
        "protest", "march", "rally", "minister", "president", "official",
        "military", "strike", "explosion", "sanctions", "election", "vote",
    }

    while lines:
        first = lines[0].strip()
        if not first:
            lines.pop(0)
            continue
        # Keep the line if: has terminal punctuation, OR > 8 words, OR contains news signals
        _first_words = first.lower().split()
        _has_news_signal = any(w.rstrip(".,;:") in _NEWS_SIGNAL_WORDS for w in _first_words)
        _has_devanagari = bool(re.search(r'[\u0900-\u097F]', first))
        _looks_like_header = (
            not _has_devanagari
            and not first.endswith((".", "!", "?", '"', "'"))
            and len(_first_words) <= 8
            and not _has_news_signal
            and not any(w[0].isupper() for w in _first_words[1:])  # no mid-sentence capitals
        )
        if _looks_like_header:
            lines.pop(0)
        else:
            break
    text = "\n".join(lines).strip()

    # Strip structural labels Llama3 sometimes inserts despite instructions
    import re as _label_re
    
    # 1. Strip labels at the start of a line
    text = _label_re.sub(
        r'(?i)(?m)^(?:\[|\b)(?:Hook|Urgent Hook|Context|Scale|Location|Eyewitness|Impact|Response|'
        r'Ongoing|Close|Global angle|Background|Key fact|Reaction|Core News Event|'
        r'Official Statements(?: and Direct Quotes)?|Direct Quotes|'
        r'Geopolitical Fallout(?: and Contextual Backstory)?|Contextual Backstory|'
        r'Anchored Engagement(?: Call-To-Action)?|Call-To-Action|'
        r'Escalation|Closing|Summary|Narrative|Body|Intro|Outro)(?:\]|\b)'
        r'\s*(?:--|[-:])?\s*', '', text
    )
    
    # 2. Strip bracketed labels hiding mid-paragraph
    text = _label_re.sub(
        r'(?i)\[(?:Hook|Urgent Hook|Core News Event|Official Statements.*?|'
        r'Geopolitical Fallout.*?|Anchored Engagement.*?)\]\s*[-:]?\s*', '', text
    )

    # 3. Strip numbered prefixes: "1. " "2) " "1:" etc.
    text = _label_re.sub(r'(?m)^\s*\d{1,2}[.):\-]\s+', '', text)
    # Clean double spaces after stripping
    text = _label_re.sub(r'\s{2,}', ' ', text).strip()

    return text


def _run_ollama_model(prompt: str, model: str) -> tuple[str, str, int]:
    url = OLLAMA_URL
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": OLLAMA_NUM_PREDICT,
            "temperature": OLLAMA_TEMPERATURE,
            "top_p": OLLAMA_TOP_P,
            "repeat_penalty": OLLAMA_REPEAT_PENALTY,
            "stop": ["\n\n\n", "Note:", "Note that", "Remember:", "Disclaimer:"],
        }
    }

    try:
        print(f"[Ollama] Generating text with model '{model}' (this can take 1-3 minutes on CPU)...", flush=True)
        response = requests.post(url, json=payload, timeout=300)
        if response.status_code != 200:
            return "", f"HTTP {response.status_code}", response.status_code
        data = response.json()
        stdout = data.get("response", "").strip()
        return stdout, "", 0
    except Exception as e:
        return "", str(e), 1


def generate_script_with_ollama(input_text, target_words, context: str = "neutral", top_performing_templates: list = None, channel_key: str = "newscup"):
    # Force deep-dive word count (200-300 words) for premium news broadcast
    target_words = max(200, min(target_words, 260))

    template_block = ""
    if top_performing_templates:
        template_block = "SUCCESSFUL PAST SCRIPTS FOR REFERENCE:\n"
        for idx, item in enumerate(top_performing_templates, 1):
            template_block += f"Example {idx} (Retention Score: {item.get('retention', 0.0)}%):\n"
            template_block += f"Hook: {item.get('hook_text', '')}\n"
            template_block += f"Script: {item.get('script_text', '')}\n"
            template_block += "-" * 30 + "\n"
        template_block += "STUDY THE ABOVE EXAMPLES. Write your new script to mirror the pacing, structure, and direct styling that made them successful.\n\n"

    # Fetch hook retention traits for reference
    try:
        from correlation_engine import CorrelationEngine
        hook_traits = CorrelationEngine.get_hook_retention_traits(channel_key, limit=3)
        if hook_traits:
            hook_traits_block = "HIGH-RETENTION HOOK EXAMPLES FOR REFERENCE:\n"
            for idx, trait in enumerate(hook_traits, 1):
                hook_traits_block += f"Hook {idx} (Hook Retention Ratio: {trait.get('hook_retention_ratio', 0.0):.1%}):\n"
                hook_traits_block += f"  \"{trait.get('hook_text', '')}\"\n"
            hook_traits_block += "STUDY THE ABOVE HOOK EXAMPLES. Your new script's first sentence (the Urgent Hook) must mimic their style, pacing, and vocabulary to capture viewer attention immediately in the first 3 seconds.\n\n"
            template_block = hook_traits_block + template_block
    except Exception as e:
        print(f"[ScriptGen] Could not fetch hook retention traits: {e}")

    # -- Extract named entities from input_text for injection -------------
    import re as _re
    _ner_doc   = nlp(input_text)
    _persons   = [e.text for e in _ner_doc.ents if e.label_ == "PERSON"][:6]
    _orgs      = [e.text for e in _ner_doc.ents if e.label_ == "ORG"][:4]
    _gpes      = [e.text for e in _ner_doc.ents if e.label_ == "GPE"][:3]

    _entity_block = ""
    if _persons:
        _entity_block += f"NAMED INDIVIDUALS (must appear in script): {', '.join(_persons)}\n"
    if _orgs:
        _entity_block += f"KEY ORGANISATIONS (must appear in script): {', '.join(_orgs)}\n"
    if _gpes:
        _entity_block += f"LOCATIONS: {', '.join(_gpes)}\n"

    if context == "sports":
        style_prompt = (
            "You are writing a highly engaging, viral football/sports news narration script (200 to 300 words) for YT Shorts, Reels, and TikTok.\n"
            "Your style is fast-paced, high-retention, and captivating, focusing on spotlight players, key matches, transfers, or legendary moments.\n\n"
            "ONLY use facts from the ARTICLE below. Do NOT invent any new people, numbers, events, claims, or details.\n\n"
            "MANDATORY NARRATIVE STRUCTURE:\n"
            "You MUST structurally layer the script exactly into the following five parts, sequentially:\n"
            "1. [Urgent Hook]: Grab attention immediately in the first 3 seconds with a shocking or explosive headline fact, player stat, or transfer rumor.\n"
            "2. [Core News Event]: State the central news event, matches, teams, and players involved.\n"
            "3. [Official Statements/Direct Quotes]: Provide statements, social posts, or statistics. You MUST tag this evidence explicitly using string markers in the text output:\n"
            "   - Wrap direct quotes in: [QUOTE: \"exact quote text\"]\n"
            "   - Wrap social posts/tweets in: [TWEET: \"@username: post content\"]\n"
            "   - Wrap official report/statistics in: [DOCUMENT: \"exact fact or statistical data\"]\n"
            "4. [Geopolitical Fallout/Contextual Backstory]: Explain the significance, team standings, player records, or broader impact on the league.\n"
            "5. [Anchored Engagement Call-To-Action]: Provide a direct, sports-focused CTA inviting viewers to subscribe and comment on their prediction or favorite player.\n\n"
        )
    else:
        style_prompt = (
            "You are writing a comprehensive, deep-dive global news broadcast narration script (200 to 300 words).\n"
            "Your style is highly authoritative, premium, and professional -- like a BBC or Sky News anchor.\n\n"
            "ONLY use facts from the ARTICLE below. Do NOT invent any new people, numbers, events, claims, or details.\n\n"
            "MANDATORY NARRATIVE STRUCTURE:\n"
            "You MUST structurally layer the script exactly into the following five parts, sequentially:\n"
            "1. [Urgent Hook]: Grab attention immediately with an urgent, specific headline fact or major breaking development.\n"
            "2. [Core News Event]: State the central news event, locations, key actors, and core actions.\n"
            "3. [Official Statements/Direct Quotes]: Provide official statements, social media posts, or document evidence. You MUST tag this evidence explicitly using string markers in the text output:\n"
            "   - Wrap direct quotes in: [QUOTE: \"exact quote text\"]\n"
            "   - Wrap social posts/tweets in: [TWEET: \"@username: post content\"]\n"
            "   - Wrap official report/statistics in: [DOCUMENT: \"exact fact or statistical data\"]\n"
            "4. [Geopolitical Fallout/Contextual Backstory]: Explain the history, underlying tensions, debate, or broader significance of this event.\n"
            "5. [Anchored Engagement Call-To-Action]: Provide a direct CTA inviting viewers to subscribe and comment on the situation.\n\n"
        )

    prompt = (
        f"{style_prompt}"
        "MANDATORY ENTITY GROUNDING RULES:\n"
        "- Do not use any named entities that are not in the names/locations block below.\n"
        f"{_entity_block}\n\n"
        "STRICT RULES:\n"
        "- Every single sentence must be grammatically complete (subject + verb + specific object).\n"
        "- Never end a sentence on a preposition (to, of, in, on, by, for), a conjunction (and, but, or), or a loose adjective.\n"
        "- Do not output any meta-commentary, headers, section labels (such as '[Urgent Hook]' or '1.'), numbering, or notes. Output ONLY the raw script text with the source tags embedded.\n"
        "- Avoid passive voice. Speak with confident authority.\n\n"
        f"LENGTH: 200 to 300 words total.\n\n"
        f"{template_block}"
        f"ARTICLE:\n{input_text}"
    )

    model_candidates = ["llama3"]

    for model in model_candidates:
        stdout, stderr, rc = _run_ollama_model(prompt, model)
        if stdout:
            normalized = _normalize_ollama_output(stdout)
            if normalized:
                print(f"[Ollama] Using model: {model}")
                return normalized
    return ""

def generate_editorial_close(
    headline: str, 
    context: str, 
    script: str
) -> str:
    """
    Generate one original editorial closing sentence.
    This sentence must NOT be based on article facts.
    It must be original analysis or historical perspective.
    This is what separates The News Cup from AI slop.
    """
    prompt = (
        "You are a senior news editor writing a single closing sentence "
        "for a news broadcast. This sentence is editorial commentary — "
        "your channel's perspective on what this news means.\n\n"
        
        "RULES FOR THIS SENTENCE:\n"
        "- It must NOT restate any fact already in the script\n"
        "- It must offer an original perspective, historical parallel, "
        "or consequence prediction\n"
        "- It must be confident and direct — no hedging words like "
        "'perhaps', 'might', 'could be', 'some say'\n"
        "- It must be 12-18 words long\n"
        "- It must start with one of these structures:\n"
        "  'History suggests that...'\n"
        "  'For [affected group], this means...'\n"
        "  'This marks a turning point in...'\n"
        "  'What is clear is that...'\n"
        "  'The pattern is unmistakable:'\n"
        "- Do NOT use the words: complex, complicated, concerning, "
        "significant, importantly, notably\n\n"
        
        f"NEWS CONTEXT: {context}\n"
        f"HEADLINE: {headline}\n"
        f"EXISTING SCRIPT SUMMARY: {script[:300]}\n\n"
        "Write ONE editorial closing sentence only. "
        "No preamble. No explanation."
    )
    
    stdout, _, rc = _run_ollama_model(prompt, "llama3")
    if not stdout:
        # Fallback editorial closes by context
        _FALLBACK_CLOSES = {
            "war":      "The human cost of this conflict continues to "
                        "be measured not in statistics, but in communities.",
            "tense":    "History rarely rewards those who mistake "
                        "aggression for strength.",
            "politics": "The decisions made in the next 72 hours will "
                        "define the next chapter of this story.",
            "serious":  "What is clear is that the people bearing this "
                        "burden had no say in creating it.",
            "positive": "This marks the kind of turning point that "
                        "looks obvious only in hindsight.",
            "sports":   "In sports, the scoreboard changes, but the passion "
                        "of the game remains constant.",
        }
        return _FALLBACK_CLOSES.get(context, 
            "The story continues, and The News Cup will be watching.")
    
    result = _normalize_ollama_output(stdout).strip()
    # Ensure it is one sentence only
    first_sent = result.split(".")[0].strip()
    if len(first_sent.split()) >= 8:
        return first_sent + "."
    return result


def clean_tts_text(text):
    text = re.sub(r'\.{2,}', '.', text)
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\s*,\s*', ', ', text)
    text = re.sub(r'\s*\.\s*', '. ', text)
    return text.strip()

def enforce_context(script):
    first_line = script.split('.')[0]
    has_proper_noun = any(word[0].isupper() for word in first_line.split() if len(word) > 2 and word not in ("The", "A", "An", "In", "On", "At", "It", "This", "That"))
    if not has_proper_noun:
        print("[CONTEXT WARNING] First line may lack a clear subject or location.")
    return script

def _strip_incomplete_tail(script: str) -> str:
    sentences = _sentence_list(script)
    if len(sentences) <= 3: return script
    cleaned = list(sentences)
    while len(cleaned) > 3:
        last = cleaned[-1].strip()
        if not last.endswith((".", "!", "?")):
            cleaned.pop()
            continue
        break
    return " ".join(cleaned)


def _spacy_fallback_script(text: str, doc, context: str) -> str:
    """
    Extractive fallback when Ollama is unavailable.
    Uses frequency-scored sentence selection via spaCy.
    """
    import heapq

    _BOILERPLATE_STARTERS = {
        "sky news", "bbc news", "al jazeera", "ndtv", "times of india",
        "politics, entertainment", "subscribe", "watch live", "follow us",
        "download the", "for breaking news", "sign up",
    }
    sentences = [
        sent.text.strip() for sent in doc.sents
        if len(sent.text.split()) >= 6
        and not any(sent.text.lower().strip().startswith(bp) for bp in _BOILERPLATE_STARTERS)
    ]
    if not sentences:
        return text

    word_freq = {}
    stopwords = {
        "the", "a", "an", "is", "are", "was", "were", "and", "or", "but",
        "in", "on", "at", "to", "for", "of", "with", "by", "from", "as",
        "it", "this", "that", "be", "been", "being", "have", "has", "had",
    }
    for token in doc:
        word = token.text.lower()
        if word not in stopwords and token.is_alpha:
            word_freq[word] = word_freq.get(word, 0) + 1

    max_freq = max(word_freq.values()) if word_freq else 1
    for word in word_freq:
        word_freq[word] /= max_freq

    sent_scores = {}
    for sent in sentences:
        for word in sent.lower().split():
            if word in word_freq:
                sent_scores[sent] = sent_scores.get(sent, 0) + word_freq[word]

    top_sents = heapq.nlargest(8, sent_scores, key=sent_scores.get)

    # Preserve all sentences for short articles so key facts are not dropped.
    if len(sentences) <= 6:
        ordered = sentences
    else:
        ordered = [s for s in sentences if s in top_sents]

    # Keep only sentences that are reasonable length for TTS
    ordered = [s for s in ordered if 6 <= len(s.split()) <= 20][:7]

    # Ensure the first sentence is a good hook (not a fragment or question)
    # The first sentence must give full context: WHO did WHAT.
    if ordered:
        _hook_candidates = []
        _body_sentences = []

        # Classify: hook = sentence with subject + action + specific entity
        for _sent in ordered:
            _sw = _sent.split()
            _first = _sw[0].lower().rstrip(".,") if _sw else ""

            # Bad hook starters (question words, fragments, orphan pronouns)
            _BAD_HOOK_STARTERS = {
                "how", "what", "when", "where", "who", "why", "which",
                "it", "its", "this", "that", "these", "those", "there",
                "he", "she", "they", "we", "itself", "himself", "herself",
                "however", "but", "and", "or", "although", "while",
                "go", "let", "political", "most", "other",
            }

            if _first in _BAD_HOOK_STARTERS or len(_sw) < 8:
                _body_sentences.append(_sent)
            else:
                _hook_candidates.append(_sent)

        # Rebuild: best hook first, then body sentences
        if _hook_candidates:
            ordered = _hook_candidates + [s for s in _body_sentences
                                           if s not in _hook_candidates]
        # If no good hook found, prepend a context sentence built from entities
        else:
            _ents = [e.text for e in doc.ents
                     if e.label_ in ("GPE", "ORG", "PERSON", "NORP") and len(e.text) > 2][:3]
            if _ents:
                _ctx_hook = f"{', '.join(_ents)} is at the center of a major international development."
                ordered = [_ctx_hook] + ordered

    if not ordered:
        # Extract title as first sentence
        _title = ""
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("TITLE:"):
                _title = line.replace("TITLE:", "").strip()
                if not _title.endswith((".", "!", "?")):
                    _title += "."
                break
        _clean_sents = [s.strip() for s in text.split(".") if len(s.strip().split()) >= 6][:6]
        if _title and _clean_sents:
            return _clean(" ".join([_title] + _clean_sents))
        elif _clean_sents:
            return _clean(" ".join(_clean_sents))
        return _short_article_safe_script(text)

    # Skip generic CONTEXT_HOOKS boilerplate if we have real sentences.
    # "Developing story -- this is raising serious concerns." is useless filler.
    # Only use a generic hook as absolute last resort when ordered is truly empty.
    if ordered:
        # First ordered sentence is a good hook (at least 8 words with a clear subject)
        if len(ordered[0].split()) >= 8:
            script = " ".join(ordered)
            return _clean(script)

        # First sentence is short — but if article has named entities, content is grounded
        _ents = [e.text for e in doc.ents
                 if e.label_ in ("GPE", "ORG", "PERSON", "NORP") and len(e.text) > 2][:3]
        if _ents:
            script = " ".join(ordered)
            return _clean(script)

    # ABSOLUTE LAST RESORT: ordered is empty — use generic hook so video has something
    CONTEXT_HOOKS = {
        "tense":       "Developing story -- this is raising serious concerns.",
        "serious":     "A significant situation is unfolding.",
        "politics":    "Major political developments are emerging.",
        "positive":    "A notable achievement has been announced.",
        "informative": "Here is what you need to know.",
        "neutral":     "Here is the latest news.",
    }
    hook = CONTEXT_HOOKS.get(context, "Here is the latest news.")
    script = hook + " " + " ".join(ordered)
    return _clean(script)



def _fact_check_entities(script: str, original_text: str) -> str:
    """
    Verify named entities in the generated script appear in the original article.
    Removes sentences that contain hallucinated person names.
    """
    original_lower = original_text.lower()

    # Non-reverting fact checker.
    # Keep the valid sentences and only remove those that fail verification.
    valid_sentences = []
    removed_count = 0

    sentences = _sentence_list(script)
    for sent in sentences:
        is_hallucination = False
        
        # Check if any PERSON or long ORG from the script is NOT in the original
        sent_doc = nlp(sent)
        sent_entities = [e.text for e in sent_doc.ents if e.label_ in ("PERSON", "ORG") and len(e.text.split()) >= 2]
        
        for entity in sent_entities:
            # Expanded allowlist for humanitarian and geopolitical entities
            _ALWAYS_VALID = {
                # Geopolitical entities
                "iran", "israel", "gaza", "russia", "ukraine", "us", "china",
                "india", "pakistan", "taiwan", "united states", "united kingdom",
                "european union", "nato", "european",
                # Major news organizations
                "bbc", "reuters", "ap", "afp", "al jazeera", "ndtv", "cnn",
                "associated press", "agence france-presse",
                # UN system and humanitarian organizations -- NEVER hallucinations
                "united nations", "un", "unicef", "who", "wfp", "unhcr",
                "world food programme", "world health organization",
                "international committee", "red cross", "icrc",
                "international monetary fund", "imf", "world bank",
                "human rights watch", "amnesty international",
                "doctors without borders", "médecins sans frontières",
                "oxfam", "save the children", "care international",
                # Aviation
                "air india", "boeing", "airbus", "indigo",
                # Common Indian institutions
                "supreme court", "high court", "dgca",
                # Middle East entities
                "hamas", "hezbollah", "idf", "icc", "opec",
                # Major country leaders (likely real)
                "secretary-general", "prime minister", "president",
            }
            # Also allow if entity contains known valid words
            if any(v in entity.lower() for v in [
                "united", "international", "world", "global", "national",
                "minister", "secretary", "committee", "organization", "programme",
                "india", "air", "israel", "iran", "gaza", "red cross",
            ]) or entity.lower() in _ALWAYS_VALID:
                continue
            
            # Check if entity (or its main words) exists in original
            words_to_check = [w.lower() for w in entity.split() if len(w) > 3]
            if words_to_check:
                matches = sum(1 for w in words_to_check if w in original_lower)
                # Only flag as hallucination if NO words appear
                # in original. < 50% match is too aggressive for short articles.
                if matches == 0:
                    is_hallucination = True
                    break
        
        if is_hallucination:
            print(f"[FACT CHECK] Removed hallucinated sentence: '{sent[:50]}...'")
            removed_count += 1
        else:
            valid_sentences.append(sent)

    # Fact-checker threshold = 3 (was 6 -- too high, gutted short articles).
    # Never restore hallucinations just because few valid sentences remain.
    if len(valid_sentences) >= 3:
        print(f"[FACT CHECK] Keeping {len(valid_sentences)} clean sentences.")
        return " ".join(valid_sentences)

    if len(valid_sentences) >= 1:
        print(f"[FACT CHECK] Only {len(valid_sentences)} sentence(s) -- "
              f"keeping clean version anyway (hallucinations not restored).")
        return " ".join(valid_sentences)

    print(f"[FACT CHECK] Nothing survived -- keeping original (hallucinations present).")
    return script


def _find_article_sentence(doc, include_words, exclude_words=None):
    if exclude_words is None:
        exclude_words = []
    for sent in doc.sents:
        text = sent.text.strip()
        if len(text.split()) < 5:
            continue
        lower = text.lower()
        if all(word.lower() in lower for word in include_words) and all(word.lower() not in lower for word in exclude_words):
            return text
    return None


def _is_short_article(text: str, doc) -> bool:
    sentences = [sent for sent in doc.sents if len(sent.text.split()) >= 5]
    return len(text.split()) <= 110 or len(sentences) <= 5


def _ensure_key_facts(script: str, original_text: str, doc) -> str:
    original_lower = original_text.lower()
    script_lower   = script.lower()
    missing_sentences = []

    # General fact injection: any specific numbers or proper nouns in article but not script
    _article_numbers = re.findall(r'\b\d+[\,\.]?\d*\s*(?:percent|%|million|billion|thousand|people|dead|killed|injured|arrested)\b', original_lower)
    for _num_phrase in _article_numbers[:2]:
        if _num_phrase not in script_lower:
            _sent = _find_article_sentence(doc, _num_phrase.split()[:2])
            if _sent:
                missing_sentences.append(_sent)

    # Conflict-specific checks — only when article is clearly about conflict/crisis
    _IS_CONFLICT = any(w in original_lower for w in [
        "killed", "dead", "airstrike", "bombing", "shelling", "troops",
        "hamas", "hezbollah", "ceasefire", "hostage", "invasion"
    ])
    if _IS_CONFLICT:
        if re.search(r'\b(at least|\d+|seven)\b.*\b(killed|dead|died)\b', original_lower):
            if not re.search(r'\b(at least|\d+|seven)\b.*\b(killed|dead|died)\b', script_lower):
                sent = _find_article_sentence(doc, ["killed"], ["injured"])
                if sent:
                    missing_sentences.append(sent)
        if "not independently verified" in original_lower:
            if not any(p in script_lower for p in ["not independently verified", "unverified"]):
                sent = _find_article_sentence(doc, ["not", "independently", "verified"])
                if sent:
                    missing_sentences.append(sent)

    if missing_sentences:
        existing = {s.strip() for s in re.split(r"(?<=[.!?])\s+", script) if s.strip()}
        for sent in missing_sentences:
            if sent not in existing:
                script = f"{sent} {script}"
        script = _clean(script)
    return script


def _short_article_safe_script(text: str) -> str:
    """Return the raw short-article content with labels removed and normalized."""
    safe_text = re.sub(r"(?m)^(TITLE|SUMMARY):\s*", "", text)
    return _clean(safe_text)


def _generate_hindi_script_with_ollama(text: str, target_sentences: int = 8) -> str:
    prompt = (
        "You are a senior Hindi TV news script writer.\n"
        "Write a professional YouTube news narration in Hindi using Devanagari script.\n"
        "Use only facts from the source story. Do not invent people, numbers, places, claims, or quotes.\n"
        f"Write exactly {target_sentences} complete sentences. No labels, bullets, preamble, or explanation.\n"
        "Sentence 1 must start with the most important fact. Keep the tone clear, serious, and broadcast-ready.\n"
        "Make it understandable for Indian viewers and explain national or public impact when relevant.\n\n"
        f"SOURCE STORY:\n{text[:3500]}\n\n"
        "Hindi script:"
    )
    stdout, _, _ = _run_ollama_model(prompt, "llama3")
    if not stdout:
        return ""
    script = _normalize_ollama_output(stdout)
    script = re.sub(r"(?i)^(hindi script|script|output)\s*:\s*", "", script).strip()
    return script


def summarise(text: str, channel_profile=None, top_performing_templates: list = None) -> str:
    text = _clean(text)
    if not text: return ""

    channel_key = channel_profile.key if channel_profile else "newscup"

    if channel_profile and getattr(channel_profile, "language", "en") == "hi":
        script = ""
        for attempt in range(3):
            script = _generate_hindi_script_with_ollama(text, target_sentences=8)
            sentence_count = len([s for s in re.split(r"(?<=[.!?।])\s+", script) if s.strip()])
            if script and len(script.split()) >= 45 and sentence_count >= 5:
                print(f"[ScriptGen][Hindi] Generated {len(script.split())} words in {sentence_count} sentences")
                return clean_caption_text(script)
            print(f"[ScriptGen][Hindi] Attempt {attempt + 1} did not meet quality threshold")
        print("[ScriptGen][Hindi] Falling back to extractive English source text; install/verify LLM Hindi output for production.")
        return clean_caption_text(_short_article_safe_script(text))

    doc = nlp(text)
    context = detect_context(doc)

    target_words = calculate_target_words(text)

    # Minimum input length guard
    # If input < 300 chars, Ollama will hallucinate.
    # Instead: skip directly to extractive fallback on the available text,
    # with a warning that the video will be short.
    _input_chars = len(text.strip())
    if _input_chars < SCRIPT_MIN_INPUT_CHARS:
        print(f"[ScriptGen] Short input ({_input_chars} chars) — expanding via DDG search.")
        # Try to find supplementary content via web search
        _headline = ""
        for _line in text.split("\n"):
            _line = _line.strip()
            if _line and not _line.startswith("TITLE:") and len(_line) > 20:
                _headline = _line
                break
        _expanded = text
        try:
            from news_fetcher import _ddg_article_search
            _ddg_extra = _ddg_article_search(_headline, "", max_chars=1500)
            if _ddg_extra and len(_ddg_extra) > 100:
                _expanded = text.strip() + " " + _ddg_extra
                print(f"[ScriptGen] DDG expanded input to {len(_expanded)} chars")
        except Exception as _ddg_err:
            print(f"[ScriptGen] DDG expansion failed: {_ddg_err}")

        # Re-run Ollama once with the expanded text if > SCRIPT_MIN_INPUT_CHARS now
        if len(_expanded) > SCRIPT_MIN_INPUT_CHARS:
            _exp_doc = nlp(_expanded)
            script = generate_script_with_ollama(_expanded, calculate_target_words(_expanded), context, top_performing_templates=top_performing_templates, channel_key=channel_key)
            if not script or not _script_relevance_ok(script, _expanded, _exp_doc):
                script = _spacy_fallback_script(_expanded, _exp_doc, context)
        else:
            doc = nlp(text)
            script = _spacy_fallback_script(text, doc, context)

        if not script:
            script = text.strip()
        script = clean_caption_text(script)
        script = _scrub_artifacts(script)
        return script

    script = ""
    for attempt in range(3):
        try:
            script = generate_script_with_ollama(text, target_words, context=context, top_performing_templates=top_performing_templates, channel_key=channel_key)
            if validate_script(script, target_words) and _script_relevance_ok(script, text, doc):
                # ── Parrot detection: reject if script is mostly raw article ──
                _src_words  = set(text.lower().split())
                _scr_words  = script.lower().split()
                _overlap    = sum(1 for w in _scr_words if w in _src_words)
                _parrot_pct = _overlap / max(len(_scr_words), 1)
                if _parrot_pct > 0.80:
                    print(f"[ScriptGen] Parrot detected ({_parrot_pct:.0%} overlap) on attempt {attempt + 1} -- retrying")
                    script = ""
                    continue
                break
            print(f"[ScriptGen] WARNING: generated script failed structure/relevance check on attempt {attempt + 1}")
            script = ""
        except Exception as ollama_exc:
            print(f"[ScriptGen] Ollama attempt failed: {ollama_exc}")
            script = ""

    script = script.strip()
    # Only run relevance audit on Ollama-generated scripts.
    # Extractive scripts are by definition from the article -- no audit needed.
    _ollama_succeeded = bool(script)   # True if Ollama produced something
    if _ollama_succeeded and not _script_relevance_ok(script, text, doc):
        print("[ScriptGen] Final relevance audit failed; falling back to extractive script.")
        script = _spacy_fallback_script(text, doc, context)
        # DO NOT re-run relevance audit on extractive output
        print("[ScriptGen] Using extractive fallback -- skipping relevance audit.")

    # If all 3 structured Ollama attempts failed, try a simplified prompt.
    # The structured prompt is strict (8 labelled sections + entity rules) and sometimes
    # triggers the relevance check. A simpler prompt has no strict structure and is more
    # likely to produce groundable, usable output.
    if not script:
        print("[ScriptGen] Ollama produced nothing -- trying direct news prompt...")
        _direct_prompt = (
            f"Write a professional news broadcast script about the following story.\n"
            f"Rules:\n"
            f"- Write EXACTLY 8 complete sentences. No preamble. No labels.\n"
            f"- Each sentence must name a specific person, place, or number.\n"
            f"- Every sentence must start with a capital letter.\n"
            f"- Write in active voice. Past or present tense only.\n"
            f"- Start sentence 1 with the most important fact.\n"
            f"- NO meta-commentary. Start writing the script immediately.\n\n"
            f"NEWS STORY:\n{text[:2000]}\n\n"
            f"Script (8 sentences, start now):"
        )
        _simple_out, _, _ = _run_ollama_model(_direct_prompt, "llama3")
        if _simple_out:
            _simple_out = _normalize_ollama_output(_simple_out)
            # Extra guard: reject if first line is meta-commentary
            _first_line = _simple_out.strip().split(".")[0].strip().lower()
            _is_meta = any(
                _first_line.startswith(p) for p in [
                    "here are", "here is", "below", "the following",
                    "i have", "as requested", "sure", "okay",
                ]
            )
            if _is_meta:
                # Strip the meta line and use what's left
                _lines = [l.strip() for l in _simple_out.strip().split("\n") if l.strip()]
                _real_lines = [
                    l for l in _lines
                    if not any(l.lower().startswith(p) for p in [
                        "here are", "here is", "below", "the following",
                        "i have", "as requested", "sure", "okay",
                    ])
                ]
                _simple_out = " ".join(_real_lines)
            if _simple_out and len(_simple_out.split()) >= 30:
                print(f"[ScriptGen] Direct news prompt succeeded: {len(_simple_out.split())} words")
                script = _simple_out

    if not script:
        print("[ScriptGen] Ollama produced nothing -- using extractive fallback.")
        script = _spacy_fallback_script(text, doc, context)


    if not script:
        print("[ScriptGen] Extractive fallback empty -- using cleaned source text.")
        script = _short_article_safe_script(text)

    if not script:
        print("[ScriptGen] All fallbacks failed -- using article title.")
        _title_line = ""
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("TITLE:"):
                _title_line = line.replace("TITLE:", "").strip()
                break
        script = _title_line or text.split(".")[0].strip() + "."

    # Minimum script length guard -- 19 words cannot produce 8 scenes
    # If script is under 60 words, try to expand using all article sentences
    _script_words = len(script.split()) if script else 0
    if _script_words < 60:
        print(f"[ScriptGen] WARNING: Script only {_script_words} words -- "
              f"attempting full-article sentence extraction.")
        # Try extracting all viable sentences from article directly
        _all_sents = []
        for _sent in doc.sents:
            _s = _sent.text.strip()
            if len(_s.split()) >= 6 and len(_s.split()) <= 25:
                if not _s.lower().startswith(("follow us", "subscribe", "read more",
                                               "click here", "advertisement")):
                    _all_sents.append(_s)
        if len(_all_sents) >= 3:
            script = " ".join(_all_sents[:10])
            print(f"[ScriptGen] Expanded to {len(script.split())} words from article sentences.")
        elif not script:
            # Final emergency: just use whatever we have
            script = text[:500].strip()
            print(f"[ScriptGen] Emergency: using first 500 chars of article text.")

    script = _ensure_key_facts(script, text, doc)

    # Cleaners
    script = clean_caption_text(script)
    script = remove_exact_duplicates(script)
    script = enforce_context(script)
    script = clean_tts_text(script)
    script = _strip_incomplete_tail(script)
    script = _scrub_artifacts(script)
    script = _fact_check_entities(script, text)

    # Ensure every sentence ends with a period
    _sentences = _sentence_list(script)
    _sentences = [s.strip() + "." if not s.strip().endswith((".", "!", "?")) else s.strip() for s in _sentences]
    script = " ".join(_sentences)

    # Append the editorial opinion close
    headline = text.split(".")[0].strip()
    headline = re.sub(r"(?i)^(TITLE|SUMMARY)\s*:\s*", "", headline).strip()
    editorial_close = generate_editorial_close(headline, context, script)
    if editorial_close and editorial_close not in script:
        script = script.rstrip(" .!?") + " — " + editorial_close.strip()

    return script


def _call_ollama_api(prompt: str) -> str:
    """Helper to call Ollama via existing _run_ollama_model."""
    stdout, stderr, rc = _run_ollama_model(prompt, "llama3")
    return stdout

def generate_dynamic_cta(headline: str, context: str, channel_name: str = "newscup") -> dict:
    """
    Ask Ollama to write a news-specific 3-line outro CTA.

    Returns a dict with keys:
        main_line   - punchy 6-10 word question about THIS story
        sub_line    - 4-8 word engagement prompt
        engage_line - 5-8 word follow/subscribe CTA

    Falls back to context-matched defaults when Ollama is unavailable.
    """
    DEFAULTS = {
        "tense": {
            "main_line":   "Could this spark a global conflict?",
            "sub_line":    "Share your view in the comments.",
            "engage_line": f"Subscribe to {channel_name} for breaking news.",
        },
        "war": {
            "main_line":   "Is the world on the edge of all-out war?",
            "sub_line":    "Tell us what you think below.",
            "engage_line": f"Follow {channel_name} for live conflict updates.",
        },
        "politics": {
            "main_line":   "Will this decision change history?",
            "sub_line":    "Share your take in the comments.",
            "engage_line": f"Subscribe to {channel_name} for political coverage.",
        },
        "serious": {
            "main_line":   "Who is responsible for this tragedy?",
            "sub_line":    "Share this to raise awareness.",
            "engage_line": f"Follow {channel_name} for the latest developments.",
        },
        "positive": {
            "main_line":   "Is this the breakthrough we have been waiting for?",
            "sub_line":    "Tell us your thoughts below.",
            "engage_line": f"Subscribe to {channel_name} for more inspiring stories.",
        },
        "informative": {
            "main_line":   "How will this change your daily life?",
            "sub_line":    "Share your point of view below.",
            "engage_line": f"Follow {channel_name} for daily science and tech news.",
        },
        "business": {
            "main_line":   "Could this crash the global economy?",
            "sub_line":    "Drop your analysis in the comments.",
            "engage_line": f"Subscribe to {channel_name} for market updates.",
        },
        "disaster": {
            "main_line":   "How prepared are we for the next disaster?",
            "sub_line":    "Share this with your community.",
            "engage_line": f"Follow {channel_name} for emergency updates.",
        },
        "sports": {
            "main_line":   "Who is your pick to win the next match?",
            "sub_line":    "Drop your predictions in the comments below.",
            "engage_line": f"Subscribe to {channel_name} for daily sports updates.",
        },
    }
    default = dict(DEFAULTS.get(context, {
        "main_line":   "What do you think about this?",
        "sub_line":    "Share your thoughts below.",
        "engage_line": f"Follow {channel_name} for daily news updates.",
    }))
    HARD_CLOSE = f"Share your point of view or thoughts in the comments below, and subscribe to {channel_name} for daily news videos."
    default["hard_close"] = HARD_CLOSE

    if not headline:
        return default

    # Extract key entities from headline to anchor the CTA
    import re as _cta_re
    _hl_words = [w for w in _cta_re.findall(r"[A-Z][a-z]+", headline or "")][:4]
    _entity_anchor = ", ".join(_hl_words) if _hl_words else "this story"

    # Build a list of off-topic concepts to ban
    OFF_TOPIC_BAN = {
        "tense": "COVID, pandemic, climate change, sports, entertainment",
        "war": "COVID, pandemic, sports, economy, technology",
        "politics": "COVID, sports, entertainment, technology",
        "serious": "COVID, sports, entertainment, economy",
        "informative": "COVID, sports, entertainment",
        "positive": "COVID, pandemic, war, conflict",
        "neutral": "COVID, pandemic",
    }
    ban_list = OFF_TOPIC_BAN.get(context, "COVID, pandemic")

    prompt = (
        "You are a social media news editor writing the OUTRO for a vertical news video.\n\n"
        f"THIS VIDEO IS SPECIFICALLY ABOUT: {headline}\n"
        f"KEY PEOPLE/PLACES IN THIS STORY: {_entity_anchor}\n"
        f"STORY EMOTIONAL TONE: {context}\n\n"
        f"CHANNEL NAME: {channel_name}\n\n"
        "STRICT RULES:\n"
        "- Your question MUST reference the specific story above -- not a generic topic.\n"
        f"- BANNED TOPICS (do NOT mention): {ban_list}\n"
        "- Do NOT use the phrase 'Stay Updated', 'Stay Informed', or 'What do you think'.\n"
        "- The MAIN_LINE must name a specific element from THIS story.\n"
        f"- The ENGAGE_LINE must invite the user to subscribe to {channel_name}.\n"
        "- Never use pronouns like 'our team', 'we', 'us', or 'our channel'. Always use the channel name directly or say 'Subscribe'.\n"
        "- Keep every line under 12 words.\n\n"
        "Write exactly these three lines:\n"
        "MAIN_LINE: [punchy 6-10 word question or statement directly about THIS story]\n"
        "SUB_LINE: [4-8 word engagement prompt]\n"
        "ENGAGE_LINE: [5-8 word follow/subscribe CTA]\n\n"
        "Return ONLY those three lines. No preamble. No notes. No explanation."
    )

    try:
        raw = _call_ollama_api(prompt)
    except Exception:
        raw = ""

    if not raw:
        print("[CTA] Ollama unavailable - using default CTA")
        return default

    result = dict(default)
    for line in raw.strip().splitlines():
        line = line.strip()
        if line.startswith("MAIN_LINE:"):
            val = line.split(":", 1)[1].strip().strip('"').strip("'")
            if 4 < len(val) < 120:
                result["main_line"] = val
        elif line.startswith("SUB_LINE:"):
            val = line.split(":", 1)[1].strip().strip('"').strip("'")
            if 4 < len(val) < 80:
                result["sub_line"] = val
        elif line.startswith("ENGAGE_LINE:"):
            val = line.split(":", 1)[1].strip().strip('"').strip("'")
            if 4 < len(val) < 80:
                result["engage_line"] = val

    # Always append the hard engagement closer to engage_line
    result["hard_close"] = HARD_CLOSE

    print(f"[CTA] main='{result['main_line']}'")
    print(f"[CTA] sub='{result['sub_line']}'")
    print(f"[CTA] engage='{result['engage_line']}'")
    return result

def _scrub_artifacts(script: str) -> str:
    """
    Final cleanup pass on the generated script.
    Removes four categories of Ollama output artifacts:

    1. Sentences fused by merge artifacts
       e.g. "...to the According to sources,."
       Fix: detect ". [Capital]" or ", [Capital attribution]" boundaries
       inside a sentence and truncate at the first clean ending.

    2. Duplicate attribution phrases
       e.g. "According to sources" appearing more than once.
       Fix: keep only the first occurrence.

    3. Sentences ending on a bare country/org abbreviation
       e.g. "...instructed the US."
       Fix: remove such sentences entirely.

    4. Sentences under 5 words that start with a bare verb/preposition
       (orphaned fragments like "Military to pause" or "Is seeking").
       Fix: discard them.
    """
    import re as _re

    # Safety: never scrub a script under 80 words -- it is already too short
    # and aggressive scrubbing would leave nothing usable.
    if len(script.split()) < 35:
        print(f"[SCRUB] Script too short ({len(script.split())} words) -- skipping scrub")
        return script

    sentences = _sentence_list(script)
    if not sentences:
        return script

    # Attribution phrases -- deduplicated across the script
    ATTRIB_PHRASES = [
        "according to sources",
        "according to reports",
        "sources say",
        "sources indicate",
        "reports suggest",
        "officials say",
        "officials confirm",
        "according to",
    ]

    # Endings that signal a truncated sentence (country/org codes)
    BAD_ENDING_TOKENS = {
        "us", "uk", "eu", "un", "nato", "uae",
        "seeking", "to", "the", "a", "an", "of",
        "civilian", "military", "government", "official",
        "operation", "operations", "infrastructure",
        "situation", "development", "evidence",
    }

    # Orphan fragment starters (bare verb/preposition, no subject)
    ORPHAN_STARTERS = {
        "military", "forces", "to", "seeking", "citing",
        "indicating", "including", "following", "is", "are",
        "was", "were",
    }

    seen_attribs: set = set()
    cleaned: list = []

    for sent in sentences:
        sl = sent.lower().rstrip(" .!?,;:")

        # Rule 1 -- Detect and truncate internal merge boundary
        # Pattern: "...word. According" or "...word, According"
        _parts = _re.split(r'\.\s+(?=[A-Z])', sent)
        if len(_parts) > 1:
            # Keep only first clean part
            sent = _parts[0].strip()
            if not sent.endswith((".", "!", "?")):
                sent += "."
            print(f"[SCRUB] Merge artifact truncated: ...{sent[-30:]}")

        # Rule 2 -- Deduplicate attribution phrases
        _found_attrib = next(
            (a for a in ATTRIB_PHRASES if a in sent.lower()), None
        )
        if _found_attrib:
            if _found_attrib in seen_attribs:
                print(f"[SCRUB] Duplicate attribution removed: '{sent[:50]}'")
                continue
            seen_attribs.add(_found_attrib)

        # Rule 3 -- Reject sentences ending on bad token
        _last_tok = sent.rstrip(".!?\"' ").split()[-1].lower() if sent.split() else ""
        if _last_tok in BAD_ENDING_TOKENS:
            print(f"[SCRUB] Bad ending token '{_last_tok}' -- removed: '{sent[:50]}'")
            continue

        # Rule 4 -- Reject short orphan fragments
        _words = sent.split()
        if (len(_words) < 6
                and _words
                and _words[0].lower().rstrip(".,") in ORPHAN_STARTERS):
            print(f"[SCRUB] Orphan fragment removed: '{sent[:50]}'")
            continue

        # Rule 6 -- Remove generic filler / section-header sentences
        _FILLER_PATTERNS = [
            "global angle", "power of nature", "power of natural",
            "highlights the need for", "serves as a reminder",
            "serves as a stark reminder", "underscores the importance",
            "this serves to", "it serves as",
            "raises questions about", "it remains to be seen",
            "the coming days will", "the international community",
            "as a whole", "as we know", "as mentioned",
        ]
        _sent_lower = sent.lower()
        if any(fp in _sent_lower for fp in _FILLER_PATTERNS):
            print(f"[SCRUB] Generic filler removed: '{sent[:60]}'")
            continue

        # Rule 7 - Remove sentences that end on incomplete grammar
        _sent_clean = sent.rstrip(".!?,;:")
        if _sent_clean:
            _last_word = _sent_clean.split()[-1].lower() if _sent_clean.split() else ""
            _BAD_ENDINGS = {
                # Articles
                "a", "an", "the",
                # Prepositions
                "of", "in", "on", "at", "to", "for", "from", "by", "with",
                "into", "onto", "upon", "toward", "towards", "against",
                # Conjunctions
                "and", "or", "but", "nor", "so", "yet",
                # Bare modifiers
                "public", "private", "official", "local", "national",
                "international", "economic", "political", "social",
                # Dangling infinitive verbs (common Llama3 truncation pattern)
                "reduce", "increase", "prevent", "ensure", "address",
                "achieve", "maintain", "support", "promote", "improve",
                "provide", "establish", "develop", "protect", "allow",
                # Dangling past participles
                "driven", "given", "taken", "made", "built", "said",
                "reported", "confirmed", "stated", "announced",
                # Dangling relative pronouns
                "that", "which", "who", "whose",
            }
            if _last_word in _BAD_ENDINGS:
                print(f"[SCRUB] Incomplete ending '{_last_word}' removed: '{sent[:60]}'")
                continue

        # Rule 8 -- Remove sentences starting with unanchored pronouns
        # "Him/Her/They/He/She/It" as first word = mid-article reference, no context
        _ORPHAN_PRONOUN_STARTERS = {
            "him", "her", "them", "they", "he", "she", "it",
            "his", "its", "their", "whose",
        }
        _first_sent_word = sent.split()[0].lower().rstrip(".,;:") if sent.split() else ""
        if _first_sent_word in _ORPHAN_PRONOUN_STARTERS:
            print(f"[SCRUB] Orphan pronoun removed: '{sent[:60]}'")
            continue

        # Rule 9 -- Remove web headline labels and fix common news typos
        # Headlines like "US-Iran War News Live Updates: Israel, Lebanon..."
        # are page titles, not narration sentences
        _HEADLINE_LABEL_PATTERNS = [
            r'(?i)\b(?:live\s+updates?|news\s+highlights?|breaking\s+news|'
            r'news\s+live|live\s+blog|live\s+coverage)\s*:',
            r'(?i)\b(?:watch\s+live|follow\s+live|get\s+live)',
            r'(?i)^\s*(?:today\'s|this\s+week\'s|this\s+month\'s)\s+(?:news|update|recap)',
        ]
        import re as _hl_re
        _is_headline_label = any(
            _hl_re.search(p, sent) for p in _HEADLINE_LABEL_PATTERNS
        )
        if _is_headline_label:
            print(f"[SCRUB] Headline label removed: '{sent[:60]}'")
            continue

        # Fix common news typos before passing to TTS
        _TYPO_FIXES = {
            r'\bceasfire\b': 'ceasefire',
            r'\bCeasfire\b': 'Ceasefire',
            r'\bhamasfire\b': 'Hamas fire',
            r'\bIsreal\b': 'Israel',
            r'\bIsraeli\s+army\b': 'Israeli army',
            r'\bloomspublished\b': 'looms.',
        }
        for _bad, _good in _TYPO_FIXES.items():
            sent = _hl_re.sub(_bad, _good, sent)

        # Rule 5 - Replace informal/tabloid words with professional equivalents.
        INFORMAL_REPLACEMENTS = {
            " whopping ":       " significant ",
            " massive ":        " major ",
            " huge ":           " substantial ",
            " shocking ":       " significant ",
            " bombshell ":      " major development ",
            " jaw-dropping ":   " notable ",
            " eye-watering ":   " substantial ",
            " mind-blowing ":   " remarkable ",
            " skyrocketed ":    " increased sharply ",
            " plummeted ":      " fell sharply ",
            " slammed ":        " criticized ",
            " blasted ":        " strongly criticized ",
            " sparks fury ":    " draws criticism ",
            " outrage ":        " criticism ",
            "!":                ".",
        }
        for informal, formal in INFORMAL_REPLACEMENTS.items():
            if informal.lower() in sent.lower():
                sent = sent.replace(informal, formal)
                sent = sent.replace(informal.strip().capitalize(), formal.strip().capitalize())

        # Rule 10 -- Remove RSS/channel boilerplate sentences
        _BOILERPLATE_SENTENCES = {
            # Sky News / BBC channel descriptions that appear in RSS fallback
            "sky news delivers breaking news",
            "politics, entertainment and more in the uk",
            "headlines and top stories from business",
            "subscribe to sky news",
            "watch sky news live",
            "follow sky news",
            "download the sky news app",
            "bbc news delivers breaking news",
            "stay up to date with the latest",
            "sign up for breaking news alerts",
            "get the bbc news app",
            "al jazeera english | live news",
            "ndtv provides latest news",
            "times of india brings the latest",
            # Generic RSS boilerplate
            "for more information visit",
            "click here to read more",
            "read the full story at",
            "watch the latest video",
        }
        _sent_lower_bp = sent.lower().strip()
        _is_boilerplate_sent = any(bp in _sent_lower_bp for bp in _BOILERPLATE_SENTENCES)
        if _is_boilerplate_sent:
            print(f"[SCRUB] RSS boilerplate removed: '{sent[:60]}'")
            continue

    # --- PHASE 26: Post-process: merge quote-split sentence pairs ---
    # If sentence S ends with an odd number of " (unclosed quote) and sentence S+1
    # starts with a closing-quote word (e.g. 'Justified"'), merge them.
    _merged_cleaned = []
    _skip_next = False
    for _i, _sent in enumerate(cleaned):
        if _skip_next:
            _skip_next = False
            continue
        if _i + 1 < len(cleaned):
            _next = cleaned[_i + 1]
            # Count all double-quote characters (straight + curly open + curly close)
            _quote_count = _sent.count('"') + _sent.count('\u201c') + _sent.count('\u201d')
            _next_starts_quote = bool(_next) and _next[0] in ('"', '\u201d', '\u2019')
            _next_has_closing = _next.split()[0].endswith('"') if _next.split() else False
            if (_quote_count % 2 == 1) and (_next_has_closing or _next_starts_quote):
                _combined = _sent.rstrip(".!?") + " " + _next.lstrip()
                if not _combined.rstrip().endswith((".", "!", "?")):
                    _combined += "."
                print(f"[SCRUB] Quote-split merged: '{_combined[:80]}'")
                _merged_cleaned.append(_combined)
                _skip_next = True
                continue
        _merged_cleaned.append(_sent)

    result = " ".join(_merged_cleaned).strip()
    return result if result else script   # never return empty


def generate_compilation_script(articles: list[dict], channel_profile=None) -> str:
    """
    Generate a compiled multi-story script for compilation mode.
    Fetches up to 3 articles, generates a short 3-sentence script for each,
    and returns them combined with [STORY X: TITLE] transition markers.
    """
    from channel_profiles import get_channel_profile
    profile = channel_profile or get_channel_profile(None)
    lang = getattr(profile, "language", "en")
    
    script_segments = []
    
    for idx, article in enumerate(articles[:3], 1):
        headline = article.get("title", f"Story {idx}")
        full_text = article.get("full_article_text") or article.get("summary") or headline
        
        # Clean title for transition label
        clean_title = re.sub(r'[^\w\s\-\!\?]', '', headline).strip().upper()
        # Truncate clean title if too long
        if len(clean_title) > 35:
            clean_title = clean_title[:32] + "..."
            
        segment_script = ""
        
        # Determine story context for tone
        story_doc = nlp(full_text)
        story_context = detect_context(story_doc)
        
        # Prompt for English vs Hindi
        if lang == "hi":
            prompt = (
                "You are writing a short Hindi compilation news segment.\n"
                "Write EXACTLY 3 complete sentences in Devanagari Hindi using facts ONLY from the article below.\n"
                "Do not invent names, numbers, locations, quotes, or claims.\n"
                "Structure:\n"
                "Sentence 1: Headline hook detailing the event (must contain location, name, or number).\n"
                "Sentence 2: Essential details or background context.\n"
                "Sentence 3: Immediate outcome, reaction, or what comes next.\n"
                "Rules:\n"
                "- Write only in Devanagari Hindi.\n"
                "- Exactly 3 complete sentences.\n"
                "- No headers, bullets, or labels. Start writing immediately.\n\n"
                f"ARTICLE:\n{full_text[:3000]}\n\n"
                "Hindi segment script:"
            )
            # Run Ollama
            for attempt in range(3):
                stdout, _, _ = _run_ollama_model(prompt, "llama3")
                if stdout:
                    segment_script = _normalize_ollama_output(stdout)
                    segment_script = re.sub(r"(?i)^(hindi segment script|script|output)\s*:\s*", "", segment_script).strip()
                    sentence_count = len([s for s in re.split(r"(?<=[.!?।])\s+", segment_script) if s.strip()])
                    if segment_script and sentence_count >= 2:
                        break
            if not segment_script:
                print(f"[ScriptGen][Hindi] Segment {idx} fallback.")
                segment_script = _generate_hindi_script_with_ollama(full_text, target_sentences=3)
        else:
            prompt = (
                "You are writing a short compilation news segment for a broadcast news channel.\n"
                "Write EXACTLY 3 complete sentences based ONLY on the ARTICLE below. Do not invent any new details.\n"
                "Structure:\n"
                "Sentence 1: Headline hook detailing the event (must contain location, name, or number).\n"
                "Sentence 2: Essential details or background context.\n"
                "Sentence 3: Immediate outcome, reaction, or what comes next.\n"
                "Rules:\n"
                "- Exactly 3 complete sentences.\n"
                "- Every sentence must be grammatically complete (subject + verb + object).\n"
                "- Write in active voice. Present or past tense only.\n"
                "- No section labels, numbers, bullet points, or introductory/concluding chat.\n\n"
                f"ARTICLE:\n{full_text[:3000]}\n\n"
                "Segment script:"
            )
            # Run Ollama
            for attempt in range(3):
                stdout, _, _ = _run_ollama_model(prompt, "llama3")
                if stdout:
                    segment_script = _normalize_ollama_output(stdout)
                    segment_script = re.sub(r"(?i)^(segment script|script|output)\s*:\s*", "", segment_script).strip()
                    sentence_count = len([s for s in re.split(r"(?<=[.!?])\s+", segment_script) if s.strip()])
                    if segment_script and sentence_count >= 2:
                        break
            if not segment_script:
                print(f"[ScriptGen] Segment {idx} fallback.")
                segment_script = _spacy_fallback_script(full_text, story_doc, story_context)
                sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", segment_script) if s.strip()]
                segment_script = " ".join(sents[:3])
                
        segment_script = clean_caption_text(segment_script)
        script_segments.append(f"[STORY {idx}: {clean_title}]\n{segment_script}")
        
    return "\n\n".join(script_segments)




if __name__ == "__main__":
    samples = {
        "tech": "Artificial intelligence is transforming many industries. Companies around the world are investing heavily in AI research.",
        "war": "Military forces launched airstrikes overnight. Dozens of casualties have been reported by officials.",
    }

    for label, text in samples.items():
        print(f"\nSAMPLE: {label.upper()}")
        result = summarise(text)
        print(f"Result: {result}")
