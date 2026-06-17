# long_form_script_generator.py -- News narration script generator for landscape (16:9) format

import re
from config import OLLAMA_MODEL, LONG_SCENE_TARGET_MIN
from utils import clean_caption_text
from script_generator import (
    nlp, detect_context, _run_ollama_model, _normalize_ollama_output
)

def generate_long_form_script(input_text: str, target_scenes: int = 15,
                              context: str = None, channel_profile=None, top_performing_templates: list = None) -> str:
    cleaned_input = clean_caption_text(input_text)
    if not cleaned_input:
        return ""

    if not context:
        doc = nlp(cleaned_input)
        context = detect_context(doc)
    else:
        doc = nlp(cleaned_input)

    # If input is very short, try to expand it first
    if len(cleaned_input.split()) < 150:
        print(f"[LongFormScriptGen] Short input ({len(cleaned_input.split())} words) "
              f"-- attempting DDG expansion")
        try:
            from news_fetcher import _ddg_article_search
            # Extract headline from first sentence
            _headline = cleaned_input.split(".")[0].strip()
            _extra = _ddg_article_search(_headline, "", max_chars=2500)
            if _extra and len(_extra.split()) > 50:
                cleaned_input = cleaned_input.strip() + " " + _extra
                doc = nlp(cleaned_input)
                print(f"[LongFormScriptGen] Expanded to {len(cleaned_input.split())} words")
        except Exception as _e:
            print(f"[LongFormScriptGen] DDG expansion failed: {_e}")

    print(f"[LongFormScriptGen] Starting script generation. "
          f"Context: {context}, Target: {target_scenes}")

    if channel_profile and getattr(channel_profile, "language", "en") == "hi":
        script = _generate_hindi_long_with_ollama(cleaned_input, target_scenes, context)
        if script:
            sentences = [s.strip() for s in re.split(r"(?<=[.!?।])\s+", script) if s.strip()]
            if len(sentences) >= min(10, target_scenes):
                print(f"[LongFormScriptGen][Hindi] Ollama: {len(sentences)} sentences.")
                return script
        print("[LongFormScriptGen][Hindi] Falling back to source extract; verify Hindi LLM output for production.")

    script = _generate_with_ollama(cleaned_input, doc, target_scenes, context, top_performing_templates=top_performing_templates)
    if script:
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", script)
                     if s.strip()]
        if len(sentences) >= LONG_SCENE_TARGET_MIN:
            print(f"[LongFormScriptGen] Ollama: {len(sentences)} sentences.")
            return script
        print(f"[LongFormScriptGen] Sentence count {len(sentences)} below minimum.")

    print("[LongFormScriptGen] Falling back to SpaCy extractive summary.")
    return _spacy_fallback_long_script(cleaned_input, doc, target_scenes)


def _generate_hindi_long_with_ollama(input_text: str, target_scenes: int, context: str) -> str:
    prompt = (
        "You are writing a professional Hindi long-form YouTube news narration.\n"
        "Use Devanagari Hindi for the full script. Use only facts from the article.\n"
        "Do not invent people, numbers, timelines, quotes, or claims.\n"
        f"Write exactly {target_scenes} complete sentences for a 16:9 long video.\n"
        "Structure: first 3 sentences hook and headline; next 6 give background; next 6 explain details, evidence, and reaction; final sentences explain impact and what comes next.\n"
        "Every sentence must be complete, broadcast-ready, and free of labels or numbering.\n"
        f"Story tone: {context or 'neutral'}.\n\n"
        f"ARTICLE:\n{input_text[:5000]}\n\n"
        "Hindi long-form script:"
    )
    for attempt in range(3):
        stdout, _, _ = _run_ollama_model(prompt, OLLAMA_MODEL)
        if stdout:
            normalized = _normalize_ollama_output(stdout)
            normalized = re.sub(r"(?i)^(hindi long-form script|hindi script|script)\s*:\s*", "", normalized).strip()
            if normalized and len(normalized.split()) >= 90:
                return normalized
        print(f"[LongFormScriptGen][Hindi] Attempt {attempt + 1} failed/invalid. Retrying...")
    return ""

def _generate_with_ollama(input_text: str, doc, target_scenes: int, context: str, top_performing_templates: list = None) -> str:
    template_block = ""
    if top_performing_templates:
        template_block = "SUCCESSFUL PAST SCRIPTS FOR REFERENCE:\n"
        for idx, item in enumerate(top_performing_templates, 1):
            template_block += f"Example {idx} (Retention Score: {item.get('retention', 0.0)}%):\n"
            template_block += f"Hook: {item.get('hook_text', '')}\n"
            template_block += f"Script: {item.get('script_text', '')}\n"
            template_block += "-" * 30 + "\n"
        template_block += "STUDY THE ABOVE EXAMPLES. Write your new script to mirror the pacing, structure, and direct styling that made them successful.\n\n"
    # Build entity block from doc
    persons   = [e.text for e in doc.ents if e.label_ == "PERSON"][:8]
    orgs      = [e.text for e in doc.ents if e.label_ == "ORG"][:6]
    gpes      = [e.text for e in doc.ents if e.label_ == "GPE"][:5]

    entity_block = ""
    if persons:
        entity_block += f"NAMED INDIVIDUALS (must appear in script): {', '.join(persons)}\n"
    if orgs:
        entity_block += f"KEY ORGANISATIONS (must appear in script): {', '.join(orgs)}\n"
    if gpes:
        entity_block += f"LOCATIONS: {', '.join(gpes)}\n"

    prompt = (
        "You are writing a comprehensive, deep-dive global news broadcast narration script (200 to 300 words) for a widescreen (16:9) video.\n"
        "Your style is highly authoritative, premium, and professional -- like a BBC or Sky News anchor.\n\n"
        "ONLY use facts from the ARTICLE below. Do NOT invent any new people, numbers, events, claims, or details.\n\n"
        "MANDATORY NARRATIVE STRUCTURE:\n"
        "You MUST structurally layer the script exactly into the following five parts, sequentially:\n"
        "1. Urgent Hook: Grab attention immediately with an urgent, specific headline fact or major breaking development.\n"
        "2. Core News Event: State the central news event, locations, key actors, and core actions.\n"
        "3. Official Statements and Direct Quotes: Provide official statements, social media posts, or document evidence. You MUST tag this evidence explicitly using string markers in the text output:\n"
        "   - Wrap direct quotes in: [QUOTE: \"exact quote text\"]\n"
        "   - Wrap social posts/tweets in: [TWEET: \"@username: post content\"]\n"
        "   - Wrap official report/statistics in: [DOCUMENT: \"exact fact or statistical data\"]\n"
        "4. Geopolitical Fallout and Contextual Backstory: Explain the history, underlying tensions, debate, or broader significance of this event.\n"
        "5. Anchored Engagement Call-To-Action: Provide a direct CTA inviting viewers to subscribe and comment on the situation.\n\n"
        "MANDATORY ENTITY GROUNDING RULES:\n"
        "- Do not use any named entities that are not in the names/locations block below.\n"
        f"{entity_block}\n\n"
        "STRICT RULES:\n"
        "- Every single sentence must be grammatically complete (subject + verb + specific object).\n"
        "- Never end a sentence on a preposition (to, of, in, on, by, for), a conjunction (and, but, or), or a loose adjective.\n"
        "- Do not output any meta-commentary, headers, section labels (such as '[Urgent Hook]' or '1.'), numbering, or notes. Output ONLY the raw script text with the source tags embedded.\n"
        "- Avoid passive voice. Speak with confident authority.\n\n"
        f"LENGTH: 200 to 300 words total.\n\n"
        f"{template_block}"
        f"ARTICLE:\n{input_text}"
    )

    for attempt in range(3):
        stdout, stderr, rc = _run_ollama_model(prompt, OLLAMA_MODEL)
        if stdout:
            normalized = _normalize_ollama_output(stdout)
            if normalized:
                # Validate that we have a good length script (at least 150 words/10 sentences)
                sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", normalized) if s.strip()]
                if len(sents) >= 8:
                    return normalized
        print(f"[LongFormScriptGen] Attempt {attempt+1} failed/invalid. Retrying...")

    return ""

def _spacy_fallback_long_script(text: str, doc, target_scenes: int) -> str:
    """Extractive spaCy summarization for long-form scripts when Ollama fails."""
    import heapq

    _BOILERPLATE_STARTERS = {
        "sky news", "bbc news", "al jazeera", "ndtv", "times of india",
        "politics, entertainment", "subscribe", "watch live", "follow us",
        "download the", "for breaking news", "sign up",
    }
    
    # Extract all candidate sentences
    all_sents = [sent.text.strip() for sent in doc.sents]
    candidates = []
    for s in all_sents:
        s_clean = clean_caption_text(s)
        words = s_clean.split()
        if len(words) >= 8 and len(words) <= 25:
            if not any(s_clean.lower().startswith(bp) for bp in _BOILERPLATE_STARTERS):
                candidates.append(s_clean)

    if len(candidates) <= target_scenes:
        return " ".join(candidates)

    # Score sentences by term frequency
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
    for sent in candidates:
        for word in sent.lower().split():
            if word in word_freq:
                sent_scores[sent] = sent_scores.get(sent, 0) + word_freq[word]

    # Select the top scoring sentences
    top_sents = heapq.nlargest(target_scenes, sent_scores, key=sent_scores.get)

    # Sort them in their original order in the article
    ordered = [s for s in candidates if s in top_sents][:target_scenes]
    
    return " ".join(ordered)


def generate_context_explainer_script(
    article: dict, 
    context: str,
    channel_profile=None
) -> str:
    """
    Generate a deep-context explainer script.
    This is NOT a news report — it is editorial analysis.
    The script must answer WHY, not just WHAT.
    """
    
    headline = article.get("title", "")
    full_text = article.get("full_article_text", "")
    if not full_text:
        full_text = article.get("summary", "") or headline
    
    prompt = (
        "You are writing an editorial analysis script for a news channel. "
        "This is NOT a news report. This is an EXPLAINER video that "
        "teaches the viewer why this news matters.\n\n"
        
        "MANDATORY STRUCTURE — follow this exactly:\n"
        "Paragraph 1 (HOOK): Start with a thought-provoking question "
        "about the broader issue this news reveals. Do not state the "
        "news fact yet. Create curiosity.\n\n"
        
        "Paragraph 2 (THE NEWS): In 3 sentences, summarize what happened "
        "today. Be specific: names, numbers, locations.\n\n"
        
        "Paragraph 3 (THE HISTORY): In 4 sentences, give essential "
        "background. Start with: 'This is not happening in isolation.' "
        "Reference at least one historical parallel or precedent.\n\n"
        
        "Paragraph 4 (THE PLAYERS): In 3 sentences, explain the key "
        "actors and their motivations. Use phrases like "
        "'[Person] has consistently [pattern]' to show pattern recognition.\n\n"
        
        "Paragraph 5 (THE STAKES): In 4 sentences, present two possible "
        "outcomes. Use the structure: "
        "'If [scenario A], then [consequence A]. "
        "If [scenario B], then [consequence B].'\n\n"
        
        "Paragraph 6 (THE VERDICT): In 2 sentences, state the channel's "
        "clear editorial position. Start with: "
        "'The News Cup assessment:' followed by a direct, confident "
        "statement. This is the most important part — it must be "
        "a genuine opinion, not a hedged statement.\n\n"
        
        "RULES:\n"
        "- Total length: 280-320 words\n"
        "- Never use passive voice\n"
        "- Every paragraph must begin with a different sentence structure\n"
        "- The VERDICT must take a clear position — no 'on the other hand'\n"
        "- Do not use the word 'complex' or 'complicated'\n\n"
        
        f"TRIGGERING NEWS ARTICLE:\n{full_text[:3000]}\n\n"
        "Write the explainer script now:"
    )
    
    stdout, _, rc = _run_ollama_model(prompt, "llama3")
    if stdout:
        return _normalize_ollama_output(stdout)
    return ""

