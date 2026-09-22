"""
nlp_loader.py -- Safe loader for spaCy with resilient fallback when
Windows Application Control or missing binaries block C-extensions.
"""

from __future__ import annotations
import re

class FallbackToken:
    def __init__(self, text: str):
        self.text = text
        self.is_alpha = text.isalpha()
        self.pos_ = "NOUN" if text[:1].isupper() else "VERB"
        self.dep_ = "ROOT"
        self.lemma_ = text.lower()
        self.head = self

class FallbackSent:
    def __init__(self, text: str):
        self.text = text

class FallbackEnt:
    def __init__(self, text: str, label: str):
        self.text = text
        self.label_ = label

class FallbackDoc:
    def __init__(self, text: str):
        self.text = text or ""
        
        # Split sentences
        raw_sents = re.split(r"(?<=[.!?])\s+", self.text.strip())
        self.sents = [FallbackSent(s.strip()) for s in raw_sents if s.strip()]
        
        # Tokens
        words = re.findall(r"\b[\w'-]+\b|[^\w\s]", self.text)
        self._tokens = [FallbackToken(w) for w in words]
        
        # Extract entities
        self.ents = self._extract_entities(self.text)
        
        # Noun chunks
        self.noun_chunks = [
            FallbackSent(m.group(0))
            for m in re.finditer(r"\b(?:[Tt]he|[Aa]n?|[Tt]his|[Tt]hat)?\s*(?:[A-Za-z]+ )*[A-Za-z]+\b", self.text)
            if len(m.group(0).split()) <= 4
        ]

    def __iter__(self):
        return iter(self._tokens)

    def __len__(self):
        return len(self._tokens)

    def _extract_entities(self, text: str) -> list[FallbackEnt]:
        ents = []
        seen = set()
        
        # Known GPEs
        GPES = {
            "india", "united states", "us", "usa", "uk", "united kingdom", "russia", "ukraine",
            "china", "israel", "france", "germany", "gaza", "lebanon", "iran", "saudi arabia",
            "pakistan", "afghanistan", "canada", "australia", "japan", "delhi", "new delhi",
            "mumbai", "london", "washington", "moscow", "kyiv", "beijing", "paris", "berlin",
            "tokyo", "jerusalem", "tel aviv", "tehran", "riyadh"
        }
        
        # Known Orgs
        ORGS = {
            "brics", "nato", "un", "united nations", "eu", "european union", "who", "idf",
            "hamas", "hezbollah", "taliban", "bjp", "congress", "parliament", "senate",
            "white house", "kremlin", "pentagon", "bbc", "al jazeera", "sky news", "reuters",
            "al-jazeera", "supreme court"
        }

        # Match known GPEs and ORGs (case-insensitive boundary check)
        for gpe in sorted(GPES, key=len, reverse=True):
            for m in re.finditer(r"\b" + re.escape(gpe) + r"\b", text, re.IGNORECASE):
                match_text = m.group(0)
                if match_text.lower() not in seen:
                    ents.append(FallbackEnt(match_text, "GPE"))
                    seen.add(match_text.lower())

        for org in sorted(ORGS, key=len, reverse=True):
            for m in re.finditer(r"\b" + re.escape(org) + r"\b", text, re.IGNORECASE):
                match_text = m.group(0)
                if match_text.lower() not in seen:
                    ents.append(FallbackEnt(match_text, "ORG"))
                    seen.add(match_text.lower())

        # Title Case Sequences (2-3 words, e.g. "Joe Biden", "Narendra Modi", "Xi Jinping")
        for m in re.finditer(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b", text):
            cand = m.group(1).strip()
            cand_lower = cand.lower()
            if cand_lower not in seen and len(cand) > 3:
                # Disqualify common sentence starters
                starters = {"breaking news", "urgent news", "good morning", "in addition", "according to"}
                if cand_lower not in starters:
                    ents.append(FallbackEnt(cand, "PERSON"))
                    seen.add(cand_lower)
                    
        return ents


class FallbackNLP:
    def __call__(self, text: str) -> FallbackDoc:
        return FallbackDoc(text)


def get_nlp():
    """Returns spacy en_core_web_sm if available, otherwise FallbackNLP."""
    try:
        import spacy
        return spacy.load("en_core_web_sm")
    except Exception as e:
        print(f"[NLP Loader] Using built-in FallbackNLP (spaCy load bypassed: {e})")
        return FallbackNLP()
