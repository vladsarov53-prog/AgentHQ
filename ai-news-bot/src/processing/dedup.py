from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse


TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "ref", "fbclid", "gclid", "mc_cid", "mc_eid", "source", "via",
}

# Common filler words to strip for title comparison (English + Russian)
_STOP_WORDS = frozenset({
    # English
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall",
    "should", "may", "might", "can", "could", "must", "to", "of", "in",
    "for", "on", "with", "at", "by", "from", "as", "into", "through",
    "and", "but", "or", "nor", "not", "so", "yet", "both", "either",
    "neither", "each", "every", "all", "any", "few", "more", "most",
    "other", "some", "such", "no", "only", "own", "same", "than", "too",
    "very", "just", "about", "that", "this", "it", "its", "new",
    # Russian
    "и", "в", "на", "с", "по", "из", "за", "от", "до", "для", "при",
    "не", "что", "как", "это", "все", "она", "так", "его", "но", "да",
    "ты", "вы", "мы", "они", "она", "он", "уже", "или", "бы", "ли",
    "же", "вот", "ещё", "нет", "тоже", "также", "более", "менее",
    "о", "об", "без", "под", "над", "между", "через",
    "нового", "новых", "новый", "новая", "новые", "свой", "свои",
})


def normalize_url(url: str) -> str:
    parsed = urlparse(url)

    hostname = parsed.hostname or ""
    hostname = hostname.lower()
    if hostname.startswith("www."):
        hostname = hostname[4:]

    # Reddit normalization
    hostname = hostname.replace("old.reddit.com", "reddit.com")
    hostname = hostname.replace("new.reddit.com", "reddit.com")

    # Strip tracking params
    params = parse_qs(parsed.query, keep_blank_values=False)
    clean_params = {
        k: v for k, v in params.items()
        if k.lower() not in TRACKING_PARAMS
    }
    clean_query = urlencode(clean_params, doseq=True)

    # Remove trailing slash
    path = parsed.path.rstrip("/")

    # Remove fragment
    normalized = urlunparse((
        "https",
        hostname,
        path,
        "",
        clean_query,
        "",
    ))

    return normalized


def compute_content_hash(title: str, content: str) -> str:
    title = title or ""
    content = content or ""
    text = f"{title.lower().strip()}|{content[:500].lower().strip()}"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_STEM_LEN = 6  # Truncate words to this length for crude stemming


def _title_keywords(title: str) -> set[str]:
    """Extract meaningful keywords from a title for similarity comparison.

    Uses truncation to first 6 chars as a simple language-agnostic stemmer.
    Works well for both English and Russian word forms.
    """
    words = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9]+", title.lower())
    result = set()
    for w in words:
        if w in _STOP_WORDS:
            continue
        # Keep numbers (version numbers like "5", "3.0" are important for dedup)
        # but skip very short text words
        if not w.isdigit() and len(w) <= 2:
            continue
        # Truncate long words for crude stemming
        stem = w[:_STEM_LEN] if len(w) > _STEM_LEN else w
        result.add(stem)
    return result


def titles_are_similar(title_a: str, title_b: str, threshold: float = 0.35) -> bool:
    """Check if two titles describe the same topic using Jaccard similarity on keywords.

    Threshold is intentionally low (0.35) because news about the same event
    can have very different wording across sources.
    """
    kw_a = _title_keywords(title_a)
    kw_b = _title_keywords(title_b)
    if not kw_a or not kw_b:
        return False

    # If titles contain different version numbers, they are about different things
    nums_a = {w for w in kw_a if w.isdigit()}
    nums_b = {w for w in kw_b if w.isdigit()}
    if nums_a and nums_b and nums_a != nums_b:
        return False

    intersection = kw_a & kw_b
    union = kw_a | kw_b
    jaccard = len(intersection) / len(union)
    # Also check: if a significant portion of the SMALLER set is shared
    overlap_ratio = len(intersection) / min(len(kw_a), len(kw_b))
    return jaccard >= threshold or (overlap_ratio >= 0.5 and len(intersection) >= 2)
