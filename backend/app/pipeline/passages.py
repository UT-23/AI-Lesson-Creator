"""Choose the parts of a long web page that matter for the lesson.

Why: authoritative pages are often huge (RFC 9110 is ~450k characters) and
start with navigation and front matter. Storing "the first N characters"
would keep the table of contents and drop the definitions we need.

How (deterministic, no LLM):
1. Drop site chrome before the page's first top-level heading.
2. Split into paragraphs (blank-line separated); remember each paragraph's section heading.
3. Score each prose paragraph by the topic keywords it contains. Keywords that
   are rare on this page count more (a page about HTTP says "request"
   everywhere, but "POST" only where it matters), and keywords in the
   paragraph's section heading count extra ("9.3.3. POST" is the definition).
4. Always keep the page's first prose paragraph (its own summary), then add the
   best-scoring paragraphs with their headings until the character budget is used.
5. Emit the chosen paragraphs in their original order with "[…]" where text
   was skipped, so an excerpt never pretends to be continuous.
Pages already within budget are kept whole (minus chrome).
"""

import math
import re

STOPWORDS = {
    # function words
    "the", "and", "for", "with", "from", "into", "onto", "that", "this", "these", "those", "their", "there",
    "what", "when", "where", "which", "while", "how", "why", "who", "are", "was", "were", "been", "being",
    "has", "have", "had", "can", "could", "should", "would", "will", "may", "might", "must", "its", "you",
    "your", "our", "they", "them", "not", "but", "all", "any", "each", "such", "than", "then", "also",
    "between", "versus", "using", "use", "used", "given", "about", "over", "under", "more", "most",
    # instruction verbs and research-query filler
    "explain", "distinguish", "calculate", "describe", "define", "identify", "compare", "apply", "understand",
    "definition", "definitions", "characteristics", "difference", "differences", "example", "examples",
    "common", "misconceptions", "misconception", "explained", "guide", "tutorial", "introduction", "basics",
    "overview", "beginners", "learn", "learning", "lesson", "worked", "step",
    # source names that appear in queries and in navigation menus
    "mdn", "rfc", "web", "docs", "documentation", "reference", "wikipedia", "investopedia",
}

_TOKEN = re.compile(r"[a-z0-9]+")
_SEARCH_OPERATOR = re.compile(r"\b(?:site|inurl|intitle|filetype):\S+")
_HEADING = re.compile(r"^#{1,6}\s+\S")
_H1 = re.compile(r"^# \S", re.MULTILINE)
_SENTENCE_PUNCT = re.compile(r"[.!?:;]")
GAP = "[…]"
HEADING_WEIGHT = 2.0
LABEL_MAX_CHARS = 100  # a short non-prose paragraph right before a chosen one (e.g. a term) comes with it


def topic_keywords(texts: list[str]) -> set[str]:
    """Meaningful lowercase tokens: 3+ letters, or short tokens with digits like '2xx' / '404'."""
    keywords = set()
    text = _SEARCH_OPERATOR.sub(" ", " ".join(texts).lower())  # "site:edu" is not a topic word
    for token in _TOKEN.findall(text):
        if token in STOPWORDS:
            continue
        has_digit = any(c.isdigit() for c in token)
        if has_digit and token.isdigit() and len(token) > 3:
            continue  # e.g. "9110", "2026": identifiers and years, not topic words
        if len(token) >= 3 or has_digit:
            keywords.add(token)
    return keywords


def strip_chrome(text: str) -> str:
    """Remove menus/banners before the first "# Title" if that prefix has no real sentences."""
    match = _H1.search(text)
    if not match or match.start() == 0:
        return text
    prefix = [p for p in re.split(r"\n\s*\n", text[: match.start()]) if p.strip()]
    if any(_is_prose(p.strip()) and len(p.split()) >= 20 for p in prefix):
        return text  # real content before the title: keep it
    return text[match.start():]


def _is_heading(paragraph: str) -> bool:
    return bool(_HEADING.match(paragraph)) and len(paragraph) < 200


_CODE_CHARS = set('{}[]"\\_<>=|$')


def _is_prose(paragraph: str) -> bool:
    """Sentence-like text; excludes menu items, buttons, lone labels and page-template code."""
    if len(paragraph.split()) < 8 or not _SENTENCE_PUNCT.search(paragraph):
        return False
    code_ratio = sum(c in _CODE_CHARS for c in paragraph) / len(paragraph)
    return code_ratio < 0.05  # e.g. LibreTexts' serialised MindTouch menu is ~15% braces/quotes/backslashes


MAX_PARAGRAPH = 1500  # longer "paragraphs" (e.g. PDF text with no blank lines) are split into sentence chunks


def _split_long(paragraph: str) -> list[str]:
    if len(paragraph) <= MAX_PARAGRAPH:
        return [paragraph]
    sentences = re.split(r"(?<=[.!?])\s+", paragraph)
    chunks, current = [], ""
    for sentence in sentences:
        if current and len(current) + len(sentence) + 1 > MAX_PARAGRAPH:
            chunks.append(current)
            current = ""
        current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current)
    return [c[:MAX_PARAGRAPH] for c in chunks]  # a single run-on "sentence" is hard-cut


def select_passages(text: str, keywords: set[str], budget: int) -> tuple[str, str]:
    """Return (excerpt, method) where method is "whole", "passages" or "truncated"."""
    text = strip_chrome(text)
    if len(text) <= budget:
        return text, "whole"

    paragraphs = [chunk for p in re.split(r"\n\s*\n", text) if p.strip() for chunk in _split_long(p.strip())]
    heading_of: list[int | None] = []
    current: int | None = None
    for i, p in enumerate(paragraphs):
        if _is_heading(p):
            current = i
        heading_of.append(current)

    prose = [i for i, p in enumerate(paragraphs) if not _is_heading(p) and _is_prose(p)]
    tokens = {i: set(_TOKEN.findall(paragraphs[i].lower())) & keywords for i in prose}

    # Rarity weight per keyword, computed over this page's prose paragraphs.
    n = len(prose)
    df = {k: sum(1 for i in prose if k in tokens[i]) for k in keywords}
    idf = {k: math.log(1 + n / (1 + df[k])) for k in keywords}

    def score(i: int) -> float:
        own = sum(idf[k] for k in tokens[i])
        h = heading_of[i]
        in_heading = set(_TOKEN.findall(paragraphs[h].lower())) & keywords if h is not None else set()
        return own + HEADING_WEIGHT * sum(idf[k] for k in in_heading)

    scored = [(score(i), i) for i in prose if score(i) > 0]
    ranked = [i for _, i in sorted(scored, key=lambda s: (-s[0], s[1]))]
    # The page's own opening summary goes first, but only if it is on topic
    # (otherwise the first prose paragraph is often a cookie banner or a search-box message).
    opening = next((i for i in prose if tokens[i]), None)
    order = ([opening] if opening is not None else []) + ranked

    chosen: set[int] = set()
    used = 0
    for i in order:
        if i in chosen:
            continue
        extra = [h for h in [heading_of[i]] if h is not None and h not in chosen]
        label = i - 1
        if label >= 0 and label not in chosen and not _is_prose(paragraphs[label]) \
                and not _is_heading(paragraphs[label]) and len(paragraphs[label]) <= LABEL_MAX_CHARS:
            extra.append(label)
        cost = sum(len(paragraphs[j]) + 2 for j in [i, *extra])
        if used + cost > budget:
            continue  # try smaller paragraphs further down the ranking
        chosen.update([i, *extra])
        used += cost

    if not any(i in chosen for i in prose):
        return text[:budget], "truncated"  # nothing matched: better the start of the page than nothing

    out: list[str] = []
    previous: int | None = None
    for i in sorted(chosen):
        if previous is not None and i != previous + 1:
            out.append(GAP)
        out.append(paragraphs[i])
        previous = i
    return "\n\n".join(out), "passages"
