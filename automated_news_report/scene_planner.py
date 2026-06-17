# modules/scene_planner.py — Split script into scenes and extract keywords

import sys
import re
import spacy  # type: ignore
from utils import clean_caption_text

# Environment lock
import os as _os_env_check
if "VIRTUAL_ENV" not in _os_env_check.environ and ".venv" not in sys.executable and "venv" not in sys.executable:
    print(f"[WARN] Running outside a virtual environment: {sys.executable}")


MIN_WORDS = 8
MAX_WORDS = 28    # Increased from 18 to allow full sentences to survive
IDEAL_WORDS = 18  # Increased from 12 to stop aggressive chopping

# Scene duration bounds
MIN_SCENE_DURATION = 4
MAX_SCENE_DURATION = 8  # Increased slightly to accommodate longer text chunks

BAD_ENDINGS = {"the", "a", "an", "of", "to", "in", "on", "at", "for", "with", "from", "by", "and", "but", "or", "so", "yet", "nor", "as", "is", "are", "was", "were", "has", "have", "had", "will", "would", "should", "could"}

ORPHAN_STARTERS = {"to", "in", "on", "at", "of", "for", "by", "with", "from", "including", "following", "according", "citing", "noting", "adding", "saying", "suggesting", "indicating", "marking", "seeking", "urging", "calling", "warning"}

CONTINUATION_WORDS = {
    "would", "could", "should", "will", "can", "shall", "may", "might", "must",
    "that", "which", "who", "whose", "whom",
    "and", "but", "or", "nor",
    "is", "are", "was", "were", "has", "have", "had",
    "to",
    "officials", "authorities", "forces", "troops", "military",
    "government", "authorities", "parliament", "ministry",
    "president", "minister", "official", "spokesman", "spokesperson",
    "attack", "attacks", "strike", "strikes", "bombing", "bombings",
    "invasion", "offensive", "operation", "operations", "response",
    "decision", "agreement", "deal", "talks", "sanctions", "arrest",
    "election", "referendum", "vote", "summit", "meeting", "visit",
}

SCENE_BAD_FINALS = {
    "at", "in", "on", "of", "for", "to", "by", "with", "from", "into", "onto", "over", "under", "than", "about", "through", "between", "among", "against", "during", "before", "after", "within", "without", "along", "across", "behind", "toward", "a", "an", "the", "and", "or", "but", "so", "yet", "nor", "as", "that", "which", "when", "while", "where", "whether", "what", "who", "if", "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "will", "would", "should", "could", "may", "might", "shall", "must", "can", "do", "did", "does", "no", "gun", "its", "their", "his", "her", "our", "your", "this", "these", "those", "such", "any", "some", "not", "high-profile", "well-known", "long-term", "short-term", "large-scale", "small-scale", "full-scale", "ever-present", "high-level", "top-level", "low-level", "work", "live", "travel", "move", "act", "help", "meet", "fight", "run", "come", "go", "stay", "leave", "join", "continue", "remain", "begin", "start", "end", "stop", "support", "oppose", "push", "pull", "cut", "raise", "lower", "more", "less", "greater", "fewer", "higher", "lower", "further", "significant", "substantial", "major", "notable", "including", "such", "especially", "particularly", "notably", "impose", "determine", "consider", "decide", "establish", "create", "build", "form", "make", "take", "give", "provide", "deliver", "produce", "generate", "develop", "implement", "execute", "conduct", "introduce", "propose", "suggest", "recommend", "require", "demand", "seek", "pursue", "achieve", "complete", "finish", "conclude", "announce", "declare", "confirm", "deny", "reject", "accept", "approve", "oppose", "challenge", "question", "investigate", "secure", "protect", "defend", "attack", "target", "strike", "strategic", "critical", "essential", "vital", "necessary", "important", "key", "initial", "primary", "secondary", "potential", "possible", "likely", "unprecedented", "catastrophic", "severe", "extreme", "urgent", "revealed", "stressed", "condemned", "insisted", "its", "their", "release", "demanding", "whose",
    "leaving", "claiming", "taking", "causing", "bringing",
    "killing", "injuring", "wounding", "destroying",
    "highlighting", "threatening", "affecting", "including",
    "regarding", "concerning", "following", "during",
    "near", "around", "outside", "inside", "within",
    "throughout", "across", "between", "among", "against",
    "driven", "risen", "fallen", "grown", "shrunk",
    "go", "let", "make", "take", "give", "keep",
    "itself", "themselves", "himself", "herself",
    "public",
    "reduce", "increase", "prevent", "ensure", "address", "achieve",
    "maintain", "support", "promote", "protect", "develop", "improve",
    "provide", "establish",
    "private", "official", "local", "national", "international",
    "economic", "political",
    "and", "or", "but", "nor", "a", "an", "the", "of", "in", "on",
    "at", "to", "for", "from", "by", "with", "into", "onto", "upon",
    "military", "young", "village", "hebrew", "camp", "occupied",
    "northern", "eastern", "western", "southern",
    "26", "27", "28", "29", "30", "31", "been",
}

_NATIONALITY_ADJECTIVES = {
    "russian", "ukrainian", "iranian", "israeli", "palestinian",
    "chinese", "american", "british", "french", "german", "indian",
    "pakistani", "turkish", "syrian", "libyan", "yemeni", "sudanese",
    "lebanese", "belarusian", "nato", "georgian",
    "azerbaijani", "armenian", "moldovan", "japanese", "korean",
    "north", "south",
}
SCENE_BAD_FINALS.update(_NATIONALITY_ADJECTIVES)

_COUNTRY_NAMES = {
    "iran", "russia", "ukraine", "china", "israel", "gaza", "iraq",
    "syria", "afghanistan", "pakistan", "india", "turkey", "taiwan",
    "myanmar", "ethiopia", "sudan", "lebanon", "jordan", "egypt",
    "libya", "yemen", "somalia", "france", "germany", "britain",
    "japan", "australia", "canada", "brazil", "mexico", "venezuela",
    "cuba",
}
SCENE_BAD_FINALS.update(_COUNTRY_NAMES)

_TIME_TRUNCATIONS = {
    "late", "early", "recent", "previous", "former",
    "current", "past", "next", "upcoming", "initial", "final",
    "last", "first", "second", "third", "over", "under", "some",
    "more", "less", "most", "many", "few", "several", "various",
    "multiple", "another", "other",
}
SCENE_BAD_FINALS.update(_TIME_TRUNCATIONS)

_NEW_BAD_FINALS = {
    # Adjectives that cannot end a sentence (require a following noun)
    "thick", "thin", "dense", "dark", "black", "white", "bright", "deep",
    "heavy", "light", "large", "small", "vast", "huge", "massive", "tiny",
    "long", "short", "high", "low", "wide", "narrow", "sharp", "blunt",
    "quick", "slow", "cold", "warm", "hot", "fresh", "raw", "full", "empty",
    "open", "clear", "dark", "loud", "quiet", "hard", "soft", # "closed" is excluded since it can end a sentence
    "strong", "weak", "rich", "poor", "safe", "dangerous", "severe",
    "critical", "urgent", "significant", "major", "minor", "primary",
    "secondary", "direct", "indirect", "initial", "final", "total",
    "partial", "potential", "possible", "likely", "unlikely",

    # Transitive verbs requiring an object (cannot end a scene)
    "proposing", "suggesting", "recommending", "requesting", "demanding",
    "claiming", "stating", "arguing", "alleging", "asserting", "declaring",
    "announcing", "confirming", "denying", "rejecting", "accepting",
    "approving", "opposing", "supporting", "targeting", "attacking",
    "defending", "protecting", "threatening", "warning", "urging",
    "calling", "asking", "telling", "showing", "describing", "explaining",
    "discussing", "addressing", "raising", "highlighting", "emphasizing",
    "noting", "citing", "referencing", "mentioning", "including",
    "excluding", "representing", "indicating", "suggesting", "implying",

    # Preposition-like phrase starters that need completion
    "amid", "despite", "following", "regarding", "concerning", "including",
    "excluding", "involving", "affecting", "covering", "spanning",

    # Additional verb fragments and gerunds to prevent bad ends
    "ending", "making", "having", "aimed", "trying", "attempting",
}
SCENE_BAD_FINALS.update(_NEW_BAD_FINALS)


def extract_context_entities(script: str) -> dict:
    """
    Use spaCy NER to extract named entities from the full script.
    Returns a rich entity dict used by image_fetcher for query anchoring.
    """
    try:
        doc = nlp(script)
    except NameError:
        # Fallback if nlp is not defined
        return {
            "location": "", "person": "", "org": "",
            "all_persons": [], "all_locations": [], "all_orgs": [], "all_events": [],
            "country_context": ""
        }

    persons   = []
    locations = []
    orgs      = []
    events    = []

    for ent in doc.ents:
        if ent.label_ == "PERSON":
            tokens = ent.text.split()
            PERSON_DISQUALIFIERS = {
                "set", "amid", "amidst", "tensions", "address", "congress",
                "senate", "parliament", "despite", "following", "marking",
                "including", "after", "before", "during", "against", "between",
                "among", "says", "said", "told", "warns", "claims", "urges",
                "calls", "faces", "holds", "takes", "makes", "gives", "puts",
            }
            if len(tokens) > 3 or len(tokens) < 2:
                continue
            if any(t.lower() in PERSON_DISQUALIFIERS for t in tokens):
                continue
            if ent.text not in persons:
                persons.append(ent.text)

        elif ent.label_ == "GPE" and ent.text not in locations:
            locations.append(ent.text)
        elif ent.label_ == "ORG" and ent.text not in orgs:
            orgs.append(ent.text)
        elif ent.label_ == "EVENT" and ent.text not in events:
            events.append(ent.text)

    # Disambiguate "Tripoli" — use Lebanese context if story mentions Lebanon/Lebanese
    _script_text_lower = script.lower() if isinstance(script, str) else ""
    _locations_lower = [l.lower() for l in locations]
    if "tripoli" in _locations_lower and not country_context:
        if "lebanon" in _script_text_lower or "lebanese" in _script_text_lower:
            # Replace "Tripoli" with "Lebanon" in locations to ensure correct map
            locations = ["Lebanon" if l == "Tripoli" else l for l in locations]
            country_context = "Lebanon"
            print(f"[NER] Disambiguated 'Tripoli' → Lebanon (script mentions Lebanon)")

    TITLE_PREFIXES = {
        "king", "queen", "prince", "princess", "duke", "duchess",
        "president", "vice-president", "prime minister", "premier",
        "minister", "secretary", "senator", "congressman",
        "sir", "lord", "lady", "baron", "earl", "count",
        "general", "colonel", "captain", "admiral", "chancellor",
        "governor", "mayor", "ambassador", "director", "chief",
    }
    PERSON_DISQUALIFIERS_TITLE = {
        "set", "amid", "amidst", "tensions", "address", "congress",
        "senate", "parliament", "despite", "following", "marking",
        "including", "after", "before", "during", "against",
    }
    for ent in doc.ents:
        if ent.label_ in ("ORG", "NORP", "FAC"):
            tokens = ent.text.split()
            if 2 <= len(tokens) <= 4:
                first_lower = tokens[0].lower()
                if first_lower in TITLE_PREFIXES:
                    if not any(t.lower() in PERSON_DISQUALIFIERS_TITLE
                               for t in tokens):
                        if ent.text not in persons:
                            persons.append(ent.text)
                            print(f"[NER] Title-person rescued: '{ent.text}'")

    primary_person   = persons[0]   if persons   else ""
    primary_location = locations[0] if locations else ""
    primary_org      = orgs[0]      if orgs      else ""

    COUNTRY_MAP = {
        "washington": "United States", "washington dc": "United States",
        "new york": "United States", "los angeles": "United States",
        "london": "United Kingdom", "beijing": "China",
        "moscow": "Russia", "kyiv": "Ukraine", "kiev": "Ukraine",
        "paris": "France", "berlin": "Germany", "tokyo": "Japan",
        "new delhi": "India", "delhi": "India", "mumbai": "India",
        "islamabad": "Pakistan", "kabul": "Afghanistan",
        "tehran": "Iran", "riyadh": "Saudi Arabia",
        "jerusalem": "Israel", "tel aviv": "Israel",
        "golders green":    "United Kingdom",
        "north london":     "United Kingdom",
        "uk":               "United Kingdom",
        "england":          "United Kingdom",
        "scotland":         "United Kingdom",
        "wales":            "United Kingdom",
        "northern ireland": "United Kingdom",
        "manchester":       "United Kingdom",
        "birmingham":       "United Kingdom",
        "glasgow":          "United Kingdom",
        "edinburgh":        "United Kingdom",
        "leeds":            "United Kingdom",
        "liverpool":        "United Kingdom",
        "bristol":          "United Kingdom",
    }
    country_context = ""
    if primary_location:
        country_context = COUNTRY_MAP.get(primary_location.lower(), "")

    if not country_context:
        ORG_COUNTRY_MAP = {
            "labour":          "United Kingdom",
            "conservative":    "United Kingdom",
            "lib dem":         "United Kingdom",
            "liberal democrat":"United Kingdom",
            "snp":             "United Kingdom",
            "parliament":      "United Kingdom",
            "westminster":     "United Kingdom",
            "downing":         "United Kingdom",
            "commons":         "United Kingdom",
            "lords":           "United Kingdom",
            "bbc":             "United Kingdom",
            "nhs":             "United Kingdom",
            "10 downing":      "United Kingdom",
            "democrat":        "United States",
            "republican":      "United States",
            "senate":          "United States",
            "u.s. congress":   "United States",
            "trinamool congress": "India",
            "trinamool":       "India",
            "pentagon":        "United States",
            "white house":     "United States",
            "fbi":             "United States",
            "cia":             "United States",
            "nsa":             "United States",
            "state department":"United States",
            "european union":  "Europe",
            "eu commission":   "Europe",
            "nato":            "Europe",
            "bundestag":       "Germany",
            "bundesrat":       "Germany",
            "élysée":          "France",
            "kremlin":         "Russia",
            "knesset":         "Israel",
            "likud":           "Israel",
            "hamas":           "Gaza",
            "idf":             "Israel",
            "taliban":         "Afghanistan",
            "hezbollah":       "Lebanon",
            "sinwar":          "Gaza",
            "bjp":              "India",
            "bharatiya janata": "India",
            "lok sabha":        "India",
            "rajya sabha":      "India",
            "modi":             "India",
            "indian national":  "India",
            "aam aadmi":        "India",
            "supreme court of india": "India",
        }
        all_org_text = " ".join(orgs).lower()
        # India Priority - if any Indian GPE was found, lock it in before ORG logic
        _indian_gpes = ["india", "delhi", "mumbai", "bangalore", "chennai", "kolkata"]
        if any(g.lower() in _indian_gpes for g in locations):
            country_context = "India"
            print(f"[NER] India Priority: Locked context to India based on GPE list")
        else:
            for org_key, country_val in ORG_COUNTRY_MAP.items():
                if org_key in all_org_text:
                    country_context = country_val
                    print(f"[NER] Country context derived from ORG '{org_key}': '{country_val}'")
                    break

        if not country_context:
            PERSON_COUNTRY_MAP = {
                "starmer":    "United Kingdom",
                "sunak":      "United Kingdom",
                "mandelson":  "United Kingdom",
                "farage":     "United Kingdom",
                "macron":     "France",
                "scholz":     "Germany",
                "putin":      "Russia",
                "zelensky":   "Ukraine",
                "netanyahu":  "Israel",
                "modi":       "India",
                "xi":         "China",
                "trudeau":    "Canada",
                "albanese":   "Australia",
                "sinwar":     "Gaza",
                "nasrallah":  "Lebanon",
            }
            cleaned_persons = [
                p.lower().replace("'s", "").replace("\u2019s", "").strip()
                for p in persons
            ]
            all_person_text = " ".join(cleaned_persons)
            for person_key, country_val in PERSON_COUNTRY_MAP.items():
                if person_key in all_person_text:
                    country_context = country_val
                    print(f"[NER] Country context derived from PERSON '{person_key}': '{country_val}'")
                    break

    persons = [p.replace("'s", "").replace("\u2019s", "").strip() for p in persons]
    persons = [p for p in persons if len(p) >= 2]

    return {
        "location":        primary_location,
        "person":          primary_person,
        "org":             primary_org,
        "all_persons":     persons[:3],
        "all_locations":   locations[:3],
        "all_orgs":        orgs[:3],
        "all_events":      events[:2],
        "country_context": country_context,
    }

try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    raise OSError(
        "[ScenePlanner] spaCy model not found. Run: python -m spacy download en_core_web_sm"
    )

def _detect_scene_type(sentence: str) -> str:
    import re
    def _match(keywords: list, text: str) -> bool:
        for kw in keywords:
            pattern = r'\b' + re.escape(kw) + r'\b'
            if re.search(pattern, text):
                return True
        return False
    s = sentence.lower()
    if _match(["government", "president", "minister", "election", "policy", "parliament", "legislation", "congress", "senate", "cabinet", "senator"], s):
        return "politics"
    if _match(["war", "conflict", "military", "attack", "ceasefire", "artillery", "troops", "soldiers", "combat", "gunshot", "gunfire", "shooting", "shooter", "assailant", "weapon", "armed", "hostage", "bomb", "explosion", "airstrike", "invasion"], s):
        return "war"
    if _match(["technology", "artificial intelligence", "software", "startup", "innovation", "algorithm", "neural network", "machine learning", "robot", "cybersecurity", "semiconductor", "drone technology", "digital", "internet", "app store", "smartphone"], s):
        return "technology"
    if _match(["market", "economy", "finance", "stock", "business", "trade", "commerce", "sales", "investment", "revenue", "profit", "gdp", "inflation", "recession", "unemployment", "exports", "imports"], s):
        return "business"
    if _match(["flood", "earthquake", "climate", "disaster", "storm", "hurricane", "tsunami", "wildfire", "drought", "emergency", "tornado", "avalanche", "landslide", "famine", "evacuation"], s):
        return "disaster"
    if _match(["football", "soccer", "cricket", "basketball", "olympics", "championship", "tournament", "match", "game", "league", "cup", "player", "coach", "transfer"], s):
        return "sports"
    return "general"

def detect_visual_context(text: str) -> str:
    import re
    def _match(keywords: list, text: str) -> bool:
        for kw in keywords:
            pattern = r'\b' + re.escape(kw) + r'\b'
            if re.search(pattern, text):
                return True
        return False
    t = text.lower()
    if _match(["war", "conflict", "battle", "military", "attack", "shooting", "shooter", "gunfire", "assailant", "armed", "weapon", "airstrike", "bomb", "troops"], t):
        return "war"
    if _match(["president", "king", "government", "minister", "election", "senator", "parliament", "congress"], t):
        return "politics"
    if _match(["technology", "artificial intelligence", "startup", "cybersecurity", "software", "algorithm", "robot"], t):
        return "technology"
    if _match(["people", "family", "community", "victim", "witness", "survivor", "crowd", "civilians"], t):
        return "people"
    if _match(["football", "soccer", "cricket", "basketball", "olympics", "championship", "tournament", "match", "game", "league", "cup", "player", "coach", "transfer", "stadium"], t):
        return "sports"
    return "general"

def extract_keywords(text: str) -> str:
    import re
    words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
    STOPWORDS = {"the","is","are","was","were","this","that","and","but","for","with","have","has","had","you","your","his","her","its","our","their","from","into","over","under","again","further","then","once","here","there","why","how","all","any","both","each","few","more","most","other","some","such","only","own","same","than","too","very"}
    words = [w for w in words if w not in STOPWORDS]
    return " ".join(words[:4])

def ends_with_terminal_punctuation(text: str) -> bool:
    return text.rstrip().endswith((".", "!", "?"))

def _strict_chunk_sentence(sentence: str) -> list[str]:
    words = sentence.split()
    if len(words) <= MAX_WORDS:
        return [sentence]
    
    # Generate all candidate split points
    # We need both left and right chunks to have at least MIN_WORDS
    min_split = MIN_WORDS
    max_split = len(words) - MIN_WORDS
    
    if min_split <= max_split:
        candidates = list(range(min_split, max_split + 1))
        # Sort candidates by distance from IDEAL_WORDS
        candidates.sort(key=lambda x: abs(x - IDEAL_WORDS))
        
        for c in candidates:
            left_last = words[c - 1].lower().rstrip(".,;:!?\"'")
            right_first = words[c].lower().rstrip(".,;:!?\"'")
            
            # 1. Skip if right starts with orphan/continuation
            if right_first in ORPHAN_STARTERS or right_first in CONTINUATION_WORDS:
                continue
            # 2. Skip if left ends with bad endings/finals
            if left_last in BAD_ENDINGS or left_last in SCENE_BAD_FINALS:
                continue
            # 3. Skip if right starts with an uppercase letter but left doesn't end with punctuation
            if (words[c][0].isupper() and 
                not words[c - 1].rstrip().endswith((",", ".", ";", ":")) and 
                right_first not in ("the", "a", "an", "he", "she", "they", "it", "his", "her", "their", "its", "this", "that", "these", "those")):
                continue
            # 4. Skip adjective endings
            _ADJ_SUFFIXES = ("ful", "less", "ous", "ive", "ble", "al", "ary", "ory", "ic")
            _SAFE_ADJ_ENDINGS = {
                "special", "general", "central", "federal", "natural",
                "national", "international", "local", "global", "original",
                "critical", "medical", "political", "historical"
            }
            if (left_last.endswith(_ADJ_SUFFIXES)
                    and left_last not in _SAFE_ADJ_ENDINGS
                    and len(left_last) > 5):
                continue
            # 5. Skip open quotes
            left_text = " ".join(words[:c])
            open_quotes = (left_text.count('"') +
                           left_text.count('\u201c') -
                           left_text.count('\u201d'))
            if open_quotes > 0:
                continue
            
            # 6. Skip open brackets/square brackets (to preserve quote/tweet/document tags)
            open_brackets = left_text.count('[') - left_text.count(']')
            if open_brackets > 0:
                continue
                
            # If we pass all checks, we split here
            left_text = left_text.rstrip(" ,;:")
            right_text = " ".join(words[c:])
            if not ends_with_terminal_punctuation(left_text):
                left_text += "."
            
            print(f"[CHUNK] Clean split at word {c}: "
                  f"'{left_text[:40]}' | '{right_text[:30]}'")
            
            right_chunks = _strict_chunk_sentence(right_text) if len(right_text.split()) > MAX_WORDS else [right_text]
            return [left_text] + right_chunks

    # If no clean split was found
    if len(words) <= 20:
        _whole = " ".join(words).rstrip(" ,;:")
        if not ends_with_terminal_punctuation(_whole):
            _whole += "."
        print(f"[CHUNK] Keeping {len(words)}-word sentence whole (no clean split found): '{_whole[:40]}...'")
        return [_whole]
        
    # Hard fallback: split at IDEAL_WORDS
    split_at = min(max(IDEAL_WORDS, MIN_WORDS), len(words) - 1)
    left_text = " ".join(words[:split_at]).rstrip(" ,;:")
    right_text = " ".join(words[split_at:])
    if not ends_with_terminal_punctuation(left_text):
        left_text += "."
    if right_text and right_text[0].islower():
        right_text = right_text[0].upper() + right_text[1:]
        
    print(f"[CHUNK] Hard-split fallback at word {split_at}: '{left_text[:40]}' | '{right_text[:30]}'")
    right_chunks = _strict_chunk_sentence(right_text) if len(right_text.split()) > MAX_WORDS else [right_text]
    return [left_text] + right_chunks


def calculate_scene_count(script: str) -> int:
    words = len(script.split())
    est_duration = words / 2.5
    scene_count = int(est_duration / 5)
    return max(6, min(scene_count, 12))

def merge_short_scenes(scenes):
    merged = []
    buffer = ""
    buffer_meta = None
    for scene in scenes:
        text = scene["text"].strip()
        words = len(text.split())
        if words < MIN_WORDS:
            buffer += " " + text
            if buffer_meta is None: buffer_meta = scene
            elif scene.get("type", "general") != "general": buffer_meta = scene
        else:
            if buffer:
                candidate = buffer.strip() + " " + text
                if len(candidate.split()) <= MAX_WORDS:
                    text = candidate
                    buffer = ""
                    buffer_meta = None
                else:
                    buf_text = buffer.strip()
                    if len(buf_text.split()) >= 3:
                        merged.append({**(buffer_meta or scene), "text": buf_text})
                    buffer = ""
                    buffer_meta = None
            merged.append({**scene, "text": text})
    if buffer.strip():
        buf_words = buffer.strip().split()
        if buf_words and len(buf_words) >= 3:
            if merged and len(merged[-1]["text"].split()) + len(buf_words) <= MAX_WORDS:
                merged[-1]["text"] += " " + buffer.strip()
            else:
                merged.append({**(buffer_meta or (merged[-1] if merged else {})), "text": buffer.strip()})
    return merged

def safe_split(words):
    if len(words) > 12:
        mid = len(words) // 2
        return [" ".join(words[:mid]), " ".join(words[mid:])]
    return [" ".join(words)]

def _clean_scene_text(text: str) -> str:
    text = text.strip()
    starts_lowercase = bool(text and text[0].islower())
    if starts_lowercase and len(text.split()) < 8:
        return ""
    text = re.sub(r'^[A-Z]{1,5}\s*,\s*', '', text)
    text = re.sub(r'^[,.\s;:]+', '', text)
    COORD_CONJUNCTIONS = r'^(and|or|but|so|yet|nor|both|either)\s+'
    text = re.sub(COORD_CONJUNCTIONS, '', text, flags=re.IGNORECASE)
    if re.match(r'^[Tt]o\s+["\u201c\u2018a-z]', text):
        text = re.sub(r'^[Tt]o\s+', '', text)
        if text and text[0].islower(): text = text[0].upper() + text[1:]
    if len(text.split()) <= 3:
        LEADING_PREP_ARTIFACT = r'^(?i:of|to|from|with|by|at|in|on|for|into|onto|upon|over|under|through|about|after|before|during|among|between|against|along|across|behind|toward|within|without|beyond)\s+(?=[A-Z])'
        text = re.sub(LEADING_PREP_ARTIFACT, '', text)
    text = re.sub(r'\bof The\b', 'of the', text); text = re.sub(r'\bto A\b', 'to a', text); text = re.sub(r'\bto The\b', 'to the', text); text = re.sub(r'\bof A\b', 'of a', text); text = re.sub(r'\bin The\b', 'in the', text); text = re.sub(r'\bby The\b', 'by the', text); text = re.sub(r'\bfor The\b', 'for the', text)
    SUBORD_CONJUNCTIONS = r'^(before|after|while|although|though|since|because|despite|following|amid|amidst|regarding|concerning|given|provided|unless|until|whenever|wherever|as long as|even though|even if)\s+'
    stripped_test = re.sub(SUBORD_CONJUNCTIONS, '', text, flags=re.IGNORECASE)
    if len(stripped_test.split()) < MIN_WORDS: text = stripped_test
    text = text.rstrip(" ,;").strip()
    import re as _paren_re
    text = _paren_re.sub(r'\s*\([A-Z][A-Z0-9\s\-]{1,10}\)', '', text)
    text = _paren_re.sub(r'\s{2,}', ' ', text).strip()
    if text and text[-1] not in ".!?,;:": text += "."
    if text and text[0].islower(): text = text[0].upper() + text[1:]
    FRAGMENT_STARTERS = {"who", "which", "that", "whose", "whom", "where", "whereby", "while", "although", "though", "whereas", "whenever", "wherever", "and", "but", "or", "nor", "yet", "so", "also", "additionally", "furthermore", "moreover", "however", "therefore", "consequently", "subsequently", "meanwhile", "nevertheless", "limit", "reduce", "minimize", "maximize", "ensure", "provide", "implement", "establish", "maintain", "increase", "decrease", "allow", "prevent", "avoid", "consider", "note", "follow", "aimed", "designed", "intended", "expected", "planned", "called", "built", "made", "taken", "said", "told", "given", "seen", "reported", "confirmed", "stated", "announced", "described", "was", "were", "is", "are", "has", "have", "had", "will", "would", "could", "should", "shall", "must", "can", "may", "might", "does", "did", "do", "results", "action", "note", "warning", "update", "breaking", "summary", "context", "background", "timeline", "analysis", "about", "nearly", "almost", "roughly", "approximately", "over", "under", "more", "less", "fewer", "greater", "noted", "added", "continued", "explained", "warned", "urged", "ordered", "issued", "working", "calling", "building", "having", "being", "going", "coming", "taking", "making", "putting", "setting", "getting", "running", "moving", "pushing", "leading", "trying", "using", "buildup", "buildup of", "outbreak", "reports", "consumption", "production", "distribution", "implementation", "development", "deployment", "establishment", "reduction", "increase", "decrease", "expansion", "contraction", "instance,", "for instance,", "however,", "white", "black", "red", "blue", "green", "yellow", "orange", "purple", "pink", "grey", "gray", "brown", "dark", "light", "new", "old", "large", "small", "major", "minor", "main", "key", "core", "top", "high", "low", "full", "half", "both", "the", "their", "this", "its", "release", "demanding", "whose", "due", "due to", "owing", "owing to",
        # Expanded fragment starters from logs
        "hearing", "sparking", "fueling", "causing", "hitting", "striking",
        "targeting", "killing", "wounding", "injuring", "destroying", "damaging",
        "burning", "collapsing", "erupting", "threatening", "warning", "urging",
        "forcing", "allowing", "preventing", "requiring", "enabling", "creating",
        "driving", "triggering", "igniting", "disrupting", "crippling", "halting",
        "breaking", "shaking", "placing", "leaving", "finding", "keeping",
        "starting", "ending", "moving", "taking", "making", "giving", "being",
        "having", "showing", "representing", "according", "following", "citing",
        # Third-person singular present verbs (no subject)
        "coincides", "signals", "marks", "shows", "reveals", "suggests", "indicates",
        "appears", "remains", "continues", "comes", "goes", "leads", "follows",
        "affects", "involves", "raises", "lowers", "increases", "decreases", "grows",
        "falls", "highlights", "underscores", "reflects", "demonstrates",
        "impacts", "triggers", "ignites", "strains", "complicates", "escalates",
    }
    first_word_raw = text.split()[0] if text.split() else ""
    first_word = first_word_raw.lower().rstrip(",.;:")
    if first_word_raw.endswith("'s") or first_word_raw.endswith("s'"): return ""
    import re as _num_re
    if _num_re.match(r'^[\d\$\£\€\%]', first_word): return ""
    if text.split() and text.split()[0].rstrip().endswith(":"): return ""
    if text.startswith(('"', "'", "\u201c", "\u2018")) and len(text.split()) < 6: return ""
    if first_word in FRAGMENT_STARTERS: return ""
    return text

def _plan_scenes_core(script: str) -> list[dict]:
    script = clean_caption_text(script)
    context = extract_context_entities(script)
    protected = re.sub(r'\b([A-Z])\.\s([A-Z])\.', r'\1\2', script)
    protected = re.sub(r'\b([A-Z])\.\s([A-Z])\.\s([A-Z])\.', r'\1\2\3', protected)
    ABBREV_MAP = {"D.C.": "DC", "U.S.": "US", "U.K.": "UK", "U.N.": "UN", "E.U.": "EU", "U.A.E.": "UAE", "Dr.": "Dr", "Mr.": "Mr", "Mrs.": "Mrs", "Ms.": "Ms", "Jr.": "Jr", "Sr.": "Sr", "St.": "St", "vs.": "vs", "approx.": "approx", "govt.": "govt", "dept.": "dept", "No.": "No", "Pres.": "President", "Gen.": "General", "Lt.": "Lieutenant", "Sgt.": "Sergeant", "Rep.": "Representative", "Sen.": "Senator", "Ave.": "Avenue", "Blvd.": "Boulevard"}
    for abbrev, safe in ABBREV_MAP.items(): protected = protected.replace(abbrev, safe)
    raw_sentences = re.split(r"(?<=[.!?])\s+", protected.strip())
    sentences = [s.strip() for s in raw_sentences if s.strip() and len(s.split()) >= MIN_WORDS]
    scenes = []
    for i, sent in enumerate(sentences):
        sentence_fragments = _strict_chunk_sentence(sent)
        for j, fragment in enumerate(sentence_fragments):
            if len(fragment.split()) > MAX_WORDS: fragment = " ".join(fragment.split()[:MAX_WORDS])
            scene_type = _detect_scene_type(fragment)
            scene_context = detect_visual_context(fragment)
            scene_keyword = extract_keywords(fragment) or "breaking news event"

            # Check for primary source markers
            is_evidence = False
            if "[QUOTE:" in fragment:
                scene_type = "quote_card"
                scene_context = "quote"
                scene_keyword = "editorial direct quote card overlay design"
                is_evidence = True
            elif "[TWEET:" in fragment:
                scene_type = "tweet_overlay"
                scene_context = "social"
                scene_keyword = "official social media tweet post card graphic"
                is_evidence = True
            elif "[DOCUMENT:" in fragment:
                scene_type = "evidence_graphic"
                scene_context = "document"
                scene_keyword = "geopolitical document report evidence graphic chart"
                is_evidence = True

            if not is_evidence:
                if context["location"] or context["person"]: scene_keyword = f"{context['location']} {context['person']} {scene_keyword} news event realistic"
                else: scene_keyword = f"{scene_keyword} breaking news event realistic photo"
                if i == 0 and j == 0: scene_keyword = f"{scene_keyword} breaking news dramatic real photo"

            cleaned_fragment = _clean_scene_text(fragment)
            if not cleaned_fragment:
                if scenes and fragment.strip():
                    _rescue_words = fragment.strip().split()
                    _rescue_stops = {"a", "an", "the", "is", "are", "was", "were", "in", "on"}
                    _meaningful = [w for w in _rescue_words if w.lower().rstrip(".,") not in _rescue_stops]
                    _dangling_verbs = {"imports", "exports", "produces", "consumes", "generates", "requires", "contains", "represents", "accounts", "comprises", "constitutes", "affects", "involves", "includes", "excludes", "covers", "shows", "indicates", "suggests", "reveals", "reports", "confirms", "states"}
                    _prev_last = scenes[-1]["text"].rstrip(".!?,; ").split()[-1].lower()
                    if (_prev_last in _dangling_verbs and re.match(r'^[\d\$\£\€\%]', fragment.strip())):
                        _merged = scenes[-1]["text"].rstrip(".!?") + " " + fragment.strip()
                        if len(_merged.split()) <= MAX_WORDS: scenes[-1]["text"] = _merged; continue
                    if len(_meaningful) >= 3 and len(_rescue_words) >= 4:
                        _merged = f"{scenes[-1]['text'].rstrip('.!?')}, {fragment.strip().lower()}"
                        if len(_merged.split()) <= MAX_WORDS: scenes[-1]["text"] = _merged
                continue
            if len(cleaned_fragment.split()) >= 3:
                scenes.append({"text": cleaned_fragment, "keyword": scene_keyword, "type": scene_type, "context": scene_context, "entities": context})
    scenes = merge_short_scenes(scenes)
    DANGLING_VERB_ENDINGS = {"imports", "exports", "produces", "consumes", "generates", "requires", "contains", "represents", "accounts", "comprises", "constitutes", "affects", "involves", "includes", "excludes", "covers", "shows", "indicates", "suggests", "reveals", "reports", "confirms", "states"}
    import re as _sc_re
    repaired = []; i = 0
    while i < len(scenes):
        s = scenes[i]
        last_word = s["text"].rstrip(".!?,; ").split()[-1].lower() if s["text"].split() else ""
        if (last_word in DANGLING_VERB_ENDINGS and i + 1 < len(scenes) and _sc_re.match(r'^[\d\$\£\€\%]', scenes[i + 1]["text"].strip())):
            merged_text = s["text"].rstrip(".!?") + " " + scenes[i + 1]["text"].lstrip()
            repaired.append({**s, "text": merged_text, "type": s["type"] if s["type"] != "general" else scenes[i+1]["type"]})
            i += 2
        else: repaired.append(s); i += 1
    scenes = repaired
    def _scene_ends_incomplete(text: str) -> bool:
        clean = text.rstrip(".!?,;: ")
        if not clean: return False
        words_list = clean.split()
        last_word = words_list[-1].lower()

        # Bare numbers as last word = truncated date/reference
        import re as _ni_re
        if _ni_re.match(r'^\d+$', last_word) and int(last_word) < 200:
            return True

        # ALWAYS_INCOMPLETE set of phrase-initiating/connecting words that cannot end a scene.
        # "closed" is explicitly excluded from here because "The border was closed." is a valid ending.
        # Downstream checks will merge "closed due to damage" correctly because the sentence will continue.
        _ALWAYS_INCOMPLETE = {
            "at", "in", "on", "of", "for", "to", "by", "with", "from", "into", "onto", 
            "over", "under", "than", "about", "through", "between", "among", "against", 
            "during", "before", "after", "within", "without", "along", "across", 
            "behind", "toward", "a", "an", "the", "and", "or", "but", "so", "yet", 
            "nor", "as", "that", "which", "when", "while", "where", "whether", "what", 
            "who", "if", "be", "been", "being", "have", "has", "had", "will", "would", 
            "should", "could", "may", "might", "shall", "must", "can", "do", "did", 
            "does", "its", "their", "his", "her", "our", "your", "this", "these", 
            "those", "such", "any", "some", "not", "high-profile", "well-known", 
            "long-term", "short-term", "large-scale", "small-scale", "full-scale", 
            "ever-present", "high-level", "top-level", "low-level", "amid", "despite", 
            "following", "regarding", "concerning", "including", "excluding", 
            "involving", "affecting", "covering", "spanning", "due", "owing",
            "facing", "posing", "challenging", "directing", "leaving", "claiming",
            "taking", "causing", "bringing", "killing", "injuring", "wounding",
            "destroying", "highlighting", "threatening"
        }

        if last_word in _ALWAYS_INCOMPLETE:
            return True

        # Check for dangling noun phrase starters
        # e.g., sentences starting with "Direct talks...", "Efforts to..." but lacking a verb
        _SUBJECT_MISSING_STARTERS = {
            "direct", "efforts", "talks", "negotiations", "discussions", "plans", "proposals", "steps", 
            "measures", "attempts", "actions", "investigations", "operations", "attacks", "strikes", "clashes"
        }
        first_word = words_list[0].lower() if words_list else ""
        if first_word in _SUBJECT_MISSING_STARTERS:
            try:
                doc = nlp(clean)
                has_verb = any(t.pos_ in ("VERB", "AUX") for t in doc)
                if not has_verb:
                    return True
            except Exception:
                pass

        if not text.rstrip().endswith((".", "!", "?")):
            if last_word in SCENE_BAD_FINALS: return True
        return last_word in SCENE_BAD_FINALS

    fixed_scenes = []; i = 0
    while i < len(scenes):
        scene = scenes[i]
        if _scene_ends_incomplete(scene["text"]) and i + 1 < len(scenes):
            next_scene = scenes[i + 1]
            merged_text = scene["text"].rstrip() + " " + next_scene["text"].lstrip()
            merged = {**next_scene, "text": merged_text, "type": scene["type"] if scene["type"] != "general" else next_scene["type"], "keyword": scene["keyword"]}
            if len(merged["text"].split()) > 20:
                sub_chunks = _strict_chunk_sentence(merged["text"])
                if len(sub_chunks) > 1:
                    valid_chunks = []; rescued_text = ""
                    for chunk in sub_chunks:
                        if len(chunk.split()) >= MIN_WORDS:
                            if rescued_text: chunk = rescued_text.strip() + " " + chunk; rescued_text = ""
                            valid_chunks.append(chunk)
                        else:
                            if valid_chunks: valid_chunks[-1] = valid_chunks[-1].rstrip() + " " + chunk
                            else: rescued_text += " " + chunk
                    if rescued_text.strip():
                        if valid_chunks: valid_chunks[-1] = valid_chunks[-1].rstrip() + " " + rescued_text.strip()
                        else: valid_chunks = [" ".join(merged["text"].split()[:20])]
                    for chunk in valid_chunks:
                        import re as _ra
                        _boundary = _ra.split(r'\.\s+(?=[A-Z])', chunk)
                        if len(_boundary) > 1: chunk = _boundary[0].strip(); chunk += "." if not chunk.endswith((".", "!", "?")) else ""
                        if _scene_ends_incomplete(chunk): continue
                        chunk = _clean_scene_text(chunk)
                        if chunk and len(chunk.split()) >= 3: fixed_scenes.append({**merged, "text": chunk})
                else: fixed_scenes.append(merged)
            else: fixed_scenes.append(merged)
            i += 2
        else:
            # Fix 6: Backward merge last scene if it ends incomplete
            if i == len(scenes) - 1 and _scene_ends_incomplete(scene["text"]) and fixed_scenes:
                print(f"[ORPHAN RESCUE] Backward merging last scene: '{scene['text'][:40]}'")
                prev_scene = fixed_scenes[-1]
                prev_scene["text"] = prev_scene["text"].rstrip() + " " + scene["text"].lstrip()
                if not prev_scene["text"].endswith((".", "!", "?")):
                    prev_scene["text"] += "."
            else:
                fixed_scenes.append(scene)
            i += 1

    # Final word count enforcement -- split any scene > MAX_WORDS
    # This prevents 10.80s audio scenes that cause overlap in build_video()
    _enforced = []
    for _s in fixed_scenes:
        _words = _s["text"].split()
        if len(_words) > MAX_WORDS:
            # Search backwards from MAX_WORDS for a clean grammatical break
            _cut = None
            for _ci in range(MAX_WORDS, max(MIN_WORDS, MAX_WORDS - 8), -1):
                if _ci < len(_words):
                    _pw = _words[_ci - 1].lower().rstrip(",.;:'\"")
                    _cw = _words[_ci].lower().rstrip(",.;:'\"")
                    if (_pw not in SCENE_BAD_FINALS and _pw not in BAD_ENDINGS) and \
                       (_cw not in CONTINUATION_WORDS and _cw not in ORPHAN_STARTERS):
                        _cut = _ci
                        break

            if _cut is not None:
                _left  = " ".join(_words[:_cut])
                _right = " ".join(_words[_cut:])
                if not _left.rstrip().endswith((".", "!", "?")): _left += "."
                if not _right.rstrip().endswith((".", "!", "?")): _right += "."

                # Only split if both halves are meaningful
                if len(_left.split()) >= MIN_WORDS and len(_right.split()) >= 3:
                    _enforced.append({**_s, "text": _left})
                    _enforced.append({**_s, "text": _right})
                    print(f"[WORD CAP] Grammar split: '{_s['text'][:60]}' -> 2 scenes")
                else:
                    _enforced.append(_s)
            else:
                _enforced.append(_s)
        else:
            _enforced.append(_s)
    scenes = _enforced
    if len(scenes) >= 3:
        scenes[0]["flow_role"] = "hook"; scenes[1]["flow_role"] = "context"; scenes[2]["flow_role"] = "event"
        for i in range(3, len(scenes)): scenes[i]["flow_role"] = "body"
    if len(scenes) > 14: scenes = scenes[:14]
    TARGET_MIN_SCENES = 8; TARGET_MAX_SCENES = 9; MAX_SPLIT_WORDS = 13; MIN_MERGE_WORDS = 6
    if len(scenes) < TARGET_MIN_SCENES:
        expanded = []
        for s in scenes:
            words = s["text"].split()
            if len(words) > MAX_SPLIT_WORDS and len(scenes) + len(expanded) < TARGET_MIN_SCENES + 2:
                mid = len(words) // 2
                left, right = " ".join(words[:mid]), " ".join(words[mid:])
                if not left.rstrip().endswith((".", "!", "?")): left += "."
                if not right.rstrip().endswith((".", "!", "?")): right += "."
                if len(left.split()) >= MIN_WORDS and len(right.split()) >= MIN_WORDS:
                    expanded.append({**s, "text": left}); expanded.append({**s, "text": right}); continue
            expanded.append(s)
        scenes = expanded
    if len(scenes) > TARGET_MAX_SCENES:
        shrunk = []; i = 0
        while i < len(scenes):
            s = scenes[i]
            if (len(s["text"].split()) <= MIN_MERGE_WORDS and i + 1 < len(scenes) and len(shrunk) + (len(scenes) - i) > TARGET_MAX_SCENES):
                next_s = scenes[i + 1]
                merged_text = s["text"].rstrip(".!?") + ", " + next_s["text"].lstrip()
                if not merged_text.rstrip().endswith((".", "!", "?")): merged_text += "."
                shrunk.append({**next_s, "text": merged_text, "type": s["type"] if s["type"] != "general" else next_s["type"]})
                i += 2
            else: shrunk.append(s); i += 1
        scenes = shrunk
    return scenes


def plan_scenes(script: str, pacing_style: dict | None = None) -> list[dict]:
    global MAX_WORDS, IDEAL_WORDS
    if pacing_style and "visual_cut_threshold" in pacing_style:
        t = pacing_style["visual_cut_threshold"]
        MAX_WORDS = max(14, min(int(t * 10), 32))
        IDEAL_WORDS = max(10, min(int(t * 6.5), 22))
        print(f"[ScenePlanner] Dynamic pacing adaptation: visual_cut_threshold={t}s -> MAX_WORDS={MAX_WORDS}, IDEAL_WORDS={IDEAL_WORDS}")

    script = clean_caption_text(script)
    
    # Check if this is a compilation script
    if "[STORY " in script:
        # Split by story markers: [STORY X: TITLE]
        story_blocks = re.split(r'\[STORY\s+\d+:\s*(.*?)\]', script)
        # Re.split with group returns: [prefix, title1, text1, title2, text2, ...]
        scenes = []
        i = 1
        story_idx = 1
        while i < len(story_blocks):
            title = story_blocks[i].strip()
            text = story_blocks[i + 1].strip() if i + 1 < len(story_blocks) else ""
            
            # Transition scene for story segment
            scenes.append({
                "text": f"STORY {story_idx}: {title}",
                "keyword": "transition title card",
                "type": "transition",
                "context": "transition",
                "entities": {
                    "location": "", "person": "", "org": "",
                    "all_persons": [], "all_locations": [], "all_orgs": [], "all_events": [],
                    "country_context": "",
                },
                "headline": title,
                "news_source": "Breaking News",
                "article_url": "",
                "og_image_url": "",
                "is_transition": True,
                "story_title": title,
                "story_index": story_idx,
            })
            
            # Plan scenes for this story segment
            story_scenes = _plan_scenes_core(text)
            for s in story_scenes:
                s["story_index"] = story_idx
                s["story_title"] = title
                
            scenes.extend(story_scenes)
            
            i += 2
            story_idx += 1
            
        # Tag special scenes (split-screen, social mockups)
        tag_special_scenes(scenes)
        return scenes
        
    else:
        scenes = _plan_scenes_core(script)
        tag_special_scenes(scenes)
        return scenes


def tag_special_scenes(scenes: list[dict]):
    for scene in scenes:
        if scene.get("type") == "transition":
            continue
            
        text = scene["text"]
        doc = nlp(text)
        words = {w.lower().rstrip(".,;:!?") for w in text.split()}
        
        # 1. Social Mockups (visual artifacts)
        social_triggers = {
            "tweet", "tweeted", "unfollowed", "instagram", "post", "whatsapp",
            "chat", "quote", "statement", "reported", "posted", "shared",
            "unfollow", "lafdas", "lafda"
        }
        if words & social_triggers:
            ents = [e.text for e in doc.ents if e.label_ in ("PERSON", "ORG")][:2]
            if ents:
                scene["is_social_mockup"] = True
                scene["social_entity"] = ents[0]
                scene["social_text"] = clean_caption_text(text)
                print(f"[Planner] Tagged social mockup: '{ents[0]}' -> '{text[:40]}'")
                
        # 2. Split Screens (visual collages)
        distinct_ents = []
        for ent in doc.ents:
            if ent.label_ in ("PERSON", "ORG", "GPE"):
                e_text = ent.text.strip()
                if len(e_text) > 2 and e_text.lower() not in ["bbc", "news", "reuters"]:
                    if e_text not in distinct_ents:
                        distinct_ents.append(e_text)
                        
        split_indicators = {"vs", "versus", "against", "clashed", "row", "dispute", "spat", "lafda", "compare"}
        if len(distinct_ents) >= 2 or (len(distinct_ents) == 1 and (words & split_indicators)):
            if scene.get("type") != "sports":
                scene["is_split_screen"] = True
                if len(distinct_ents) < 2:
                    ctx_country = scene.get("entities", {}).get("country_context", "")
                    if ctx_country and ctx_country != distinct_ents[0]:
                        distinct_ents.append(ctx_country)
                    else:
                        distinct_ents.append(scene.get("type", "news"))
                scene["split_entities"] = distinct_ents[:2]
                print(f"[Planner] Tagged split screen: {distinct_ents[:2]} -> '{text[:40]}'")


if __name__ == "__main__":
    sample_script = "The United Nations warned about rising sea levels in coastal cities. Scientists published new research on renewable energy storage. NASA announced a new mission to explore the surface of Mars."
    for s in plan_scenes(sample_script): print(s)
