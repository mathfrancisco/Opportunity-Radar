"""HTML job descriptions to plain text (card R55-B3).

Pure functions, no I/O. ATS payloads carry markup in three shapes: real HTML (Teamtailor,
JobPosting), entity-escaped HTML (Greenhouse `content`, which a board API returns as
`&lt;p&gt;...`), and plain text (Ashby/Lever `descriptionPlain`, manual input). All three
reach the same place, so one function reads all three; text without markup comes back
unchanged, so it is safe to apply to every source.
"""

from __future__ import annotations

import html
import re

#: Version of the rules below. Any change to the patterns bumps it.
HTML_TEXT_VERSION = "html-text-v1"

# Entity-escaped markup: `&lt;p&gt;`, or `&amp;lt;p&amp;gt;` when escaped twice.
_ESCAPED_TAG = re.compile(r"&(?:amp;)*lt;\s*/?\s*[a-z!]", re.IGNORECASE)
_TAG = re.compile(r"</?[a-z!][^>]*>", re.IGNORECASE)
_ENTITY = re.compile(r"&(?:#\d{1,7}|#x[0-9a-f]{1,6}|[a-z][a-z0-9]{1,31});", re.IGNORECASE)
_MAX_UNESCAPE_ROUNDS = 3

_DROPPED_BLOCKS = re.compile(
    r"<\s*(script|style|noscript|template)\b[^>]*>.*?<\s*/\s*\1\s*>|<!--.*?-->",
    re.IGNORECASE | re.DOTALL,
)
_HEADING_OPEN = re.compile(r"<\s*h[1-6]\b[^>]*>", re.IGNORECASE)
_LIST_ITEM_OPEN = re.compile(r"<\s*li\b[^>]*>", re.IGNORECASE)
_BLOCK_TAGS = re.compile(
    r"<\s*/?\s*(?:br|p|div|li|ul|ol|dl|dt|dd|tr|table|section|article|header|footer"
    r"|blockquote|pre|hr|h[1-6])\b[^>]*>",
    re.IGNORECASE,
)
_CELL_TAGS = re.compile(r"<\s*/?\s*(?:td|th)\b[^>]*>", re.IGNORECASE)
_TAGS = re.compile(r"</?[a-z!][^>]*>", re.IGNORECASE)
_SPACES = re.compile(r"[ \t ​]+")
_BLANK_LINES = re.compile(r"\n{3,}")


def has_markup(value: str) -> bool:
    """Whether `value` holds a tag or a character entity."""
    return bool(_TAG.search(value) or _ESCAPED_TAG.search(value) or _ENTITY.search(value))


def html_to_text(value: str | None, *, heading_marker: str = "", bullet: str = "- ") -> str | None:
    """Plain text from an HTML, entity-escaped HTML or plain-text description.

    Entities are decoded (repeatedly, while they still hide tags) before tags are stripped
    and once more after, so a literal `&amp;` in text stays `&`. `script`, `style` and
    comments are dropped with their content; block tags (`p`, `div`, `br`, `li`, headings)
    become line breaks and `li` starts its line with `bullet`, so paragraphs and lists keep
    their shape; inline tags vanish without splitting a word. `heading_marker` prefixes a
    heading line, for callers that tell headings apart. Whitespace is collapsed per line
    and blank lines to one.

    `None` stays `None` and text with neither tag nor entity is returned unchanged.
    """
    if value is None or not has_markup(value):
        return value
    text = value
    for _ in range(_MAX_UNESCAPE_ROUNDS):
        if not _ESCAPED_TAG.search(text):
            break
        text = html.unescape(text)
    text = _DROPPED_BLOCKS.sub(" ", text)
    text = _HEADING_OPEN.sub(f"\n{heading_marker}", text)
    text = _LIST_ITEM_OPEN.sub(f"\n{bullet}", text)
    text = _BLOCK_TAGS.sub("\n", text)
    text = _CELL_TAGS.sub(" ", text)
    text = html.unescape(_TAGS.sub("", text))
    lines = [_SPACES.sub(" ", line).strip() for line in text.replace("\r", "").split("\n")]
    return _BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()


__all__ = ("HTML_TEXT_VERSION", "has_markup", "html_to_text")
